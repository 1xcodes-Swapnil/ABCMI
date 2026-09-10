"""
Knowledge Object Domain Service
Implements core business logic, validation, immutable versioning, lifecycle state machine,
provenance preservation, version history, and derivation lineage.
"""

from typing import Any, Dict, Optional, Sequence
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.schemas.knowledge_object import KnowledgeObjectCreate, KnowledgeObjectUpdate


# Authoritative Lifecycle State Machine Transitions
VALID_TRANSITIONS: Dict[str, set[str]] = {
    KnowledgeObjectStatus.DRAFT.value: {
        KnowledgeObjectStatus.ACTIVE.value,
        KnowledgeObjectStatus.REJECTED.value,
        KnowledgeObjectStatus.DEPRECATED.value,
    },
    KnowledgeObjectStatus.ACTIVE.value: {
        KnowledgeObjectStatus.VALIDATED.value,
        KnowledgeObjectStatus.SUPERSEDED.value,
        KnowledgeObjectStatus.REJECTED.value,
        KnowledgeObjectStatus.DEPRECATED.value,
    },
    KnowledgeObjectStatus.VALIDATED.value: {
        KnowledgeObjectStatus.ACTIVE.value,
        KnowledgeObjectStatus.SUPERSEDED.value,
        KnowledgeObjectStatus.DEPRECATED.value,
    },
    KnowledgeObjectStatus.SUPERSEDED.value: {
        KnowledgeObjectStatus.DEPRECATED.value,
    },
    KnowledgeObjectStatus.REJECTED.value: set(),
    KnowledgeObjectStatus.DEPRECATED.value: set(),
}


class KnowledgeObjectService:
    """Service encapsulating domain rules and business logic for Knowledge Objects."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = KnowledgeObjectRepository(session)

    def _validate_confidence(self, confidence: Optional[float]) -> None:
        """Ensure confidence is NULL or bounded between 0.0 and 1.0."""
        if confidence is not None and (confidence < 0.0 or confidence > 1.0):
            raise BadRequestException(
                message=f"Confidence {confidence} is out of bounds. Must be between 0.0 and 1.0.",
                code="INVALID_CONFIDENCE",
            )

    def _extract_status(self, status_val: Any, default: str = KnowledgeObjectStatus.ACTIVE.value) -> str:
        """Safely extract status string from string, Enum, or Pydantic status type."""
        if status_val is None:
            return default
        if hasattr(status_val, "value"):
            return str(status_val.value)
        return str(status_val)

    def _dump_provenance(self, prov: Any) -> Dict[str, Any]:
        """Safely serialize provenance schema or dict."""
        if prov is None:
            return {}
        if hasattr(prov, "model_dump"):
            return prov.model_dump()
        if hasattr(prov, "dict"):
            return prov.dict()
        if isinstance(prov, dict):
            return prov
        return {}

    def _validate_transition(self, current_status: str, new_status: str) -> None:
        """Validate state transition against the authoritative lifecycle state machine."""
        if current_status == new_status:
            return  # No-op transition allowed

        allowed = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise BadRequestException(
                message=f"Invalid lifecycle transition from '{current_status}' to '{new_status}'.",
                code="INVALID_LIFECYCLE_TRANSITION",
                details={"current_status": current_status, "target_status": new_status},
            )

    async def create_knowledge_object(
        self,
        data: KnowledgeObjectCreate,
    ) -> KnowledgeObject:
        """Create a new Knowledge Object after domain validation."""
        self._validate_confidence(data.confidence)
        if data.version < 1:
            raise BadRequestException(
                message="Knowledge Object version must be >= 1.",
                code="INVALID_VERSION",
            )

        status_value = self._extract_status(data.status, KnowledgeObjectStatus.ACTIVE.value)
        prov_dict = self._dump_provenance(data.provenance)

        ko = KnowledgeObject(
            meeting_id=data.meeting_id,
            object_type=data.object_type,
            title=data.title,
            content=data.content,
            confidence=data.confidence,
            status=status_value,
            version=data.version,
            parent_id=data.parent_id,
            provenance=prov_dict,
            payload=data.payload or {},
            qdrant_point_id=data.qdrant_point_id,
        )
        return await self.repo.create(ko)

    async def get_knowledge_object(self, ko_id: uuid.UUID) -> KnowledgeObject:
        """Fetch a Knowledge Object by ID or raise NotFoundException."""
        ko = await self.repo.get_by_id(ko_id)
        if not ko:
            raise NotFoundException(
                message=f"Knowledge Object with ID {ko_id} not found.",
                code="KNOWLEDGE_OBJECT_NOT_FOUND",
            )
        return ko

    async def update_lifecycle_status(
        self,
        ko_id: uuid.UUID,
        new_status: KnowledgeObjectStatus,
    ) -> KnowledgeObject:
        """Transition a Knowledge Object to a new lifecycle state."""
        ko = await self.get_knowledge_object(ko_id)
        target_status = self._extract_status(new_status, ko.status)

        self._validate_transition(ko.status, target_status)
        ko.status = target_status
        await self.session.flush()
        await self.session.refresh(ko)
        return ko

    async def revise_knowledge_object(
        self,
        ko_id: uuid.UUID,
        update_data: KnowledgeObjectUpdate,
    ) -> KnowledgeObject:
        """
        Create an immutable new version revision of a Knowledge Object atomically.
        Marks the previous version as 'superseded'.
        """
        current = await self.get_knowledge_object(ko_id)

        if update_data.confidence is not None:
            self._validate_confidence(update_data.confidence)

        try:
            new_version_num = current.version + 1
            new_status = self._extract_status(update_data.status, KnowledgeObjectStatus.ACTIVE.value)

            # Preserve & augment provenance
            existing_prov = current.provenance or {}
            update_prov = self._dump_provenance(update_data.provenance)
            existing_lineage = existing_prov.get("lineage") or {}
            update_lineage = update_prov.get("lineage") or {}
            merged_provenance = {**existing_prov, **update_prov}
            merged_provenance["lineage"] = {
                **existing_lineage,
                **update_lineage,
                "revised_from_id": str(current.id),
                "previous_version": current.version,
            }

            new_ko = KnowledgeObject(
                meeting_id=current.meeting_id,
                object_type=current.object_type,
                title=update_data.title if update_data.title is not None else current.title,
                content=update_data.content if update_data.content is not None else current.content,
                confidence=update_data.confidence if update_data.confidence is not None else current.confidence,
                status=new_status,
                version=new_version_num,
                parent_id=current.id,
                provenance=merged_provenance,
                payload=update_data.payload if update_data.payload is not None else (current.payload or {}),
                qdrant_point_id=update_data.qdrant_point_id if update_data.qdrant_point_id is not None else None,
            )

            # Mark current as superseded
            current.status = KnowledgeObjectStatus.SUPERSEDED.value

            created_new = await self.repo.create(new_ko)
            await self.session.flush()
            return created_new
        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (BadRequestException, NotFoundException)):
                raise e
            raise BadRequestException(
                message=f"Failed to revise Knowledge Object atomically: {str(e)}",
                code="REVISION_FAILED",
            )

    async def derive_knowledge_object(
        self,
        parent_id: uuid.UUID,
        object_type: str,
        content: str,
        title: Optional[str] = None,
        confidence: Optional[float] = None,
        provenance: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeObject:
        """
        Derive a new Knowledge Object from a parent object (e.g., Decision -> Action Item).
        Maintains parent linkage and lineage without marking parent as superseded or treating it as a version revision.
        """
        parent = await self.get_knowledge_object(parent_id)
        self._validate_confidence(confidence)

        prov = provenance or {}
        prov_lineage = prov.get("lineage") or {}
        prov["lineage"] = {
            **prov_lineage,
            "derived_from_ko_id": str(parent.id),
            "source_object_type": parent.object_type,
        }

        derived_ko = KnowledgeObject(
            meeting_id=parent.meeting_id,
            object_type=object_type,
            title=title,
            content=content,
            confidence=confidence,
            status=KnowledgeObjectStatus.ACTIVE.value,
            version=1,
            parent_id=parent.id,
            provenance=prov,
            payload=payload or {},
        )
        return await self.repo.create(derived_ko)

    async def get_version_history(self, ko_id: uuid.UUID) -> Sequence[KnowledgeObject]:
        """
        Retrieve the chronological version history chain for a Knowledge Object.
        CRITICAL: Traverses upstream ancestor links via parent_id ONLY when the parent
        has the exact same object_type (version revision).
        Ensures derived objects (e.g., Action Item derived from Decision) do NOT appear
        in the version history.
        """
        current = await self.get_knowledge_object(ko_id)
        chain: list[KnowledgeObject] = [current]
        target_object_type = current.object_type

        visited = {current.id}
        curr = current
        while curr.parent_id is not None:
            parent = await self.repo.get_by_id(curr.parent_id)
            if parent is None:
                break
            # Enforce strict version history separation: parent must match object_type
            if parent.object_type != target_object_type:
                break
            if parent.id in visited:
                break
            visited.add(parent.id)
            chain.append(parent)
            curr = parent

        # Return chronological order (v1 -> v2 -> v3)
        chain.reverse()
        return chain

    async def get_derivation_lineage(self, ko_id: uuid.UUID) -> Dict[str, Any]:
        """
        Trace derivation relationships (parent source and derived children).
        Separates conceptual derivation from version history.
        """
        ko = await self.get_knowledge_object(ko_id)
        parent_obj = None
        if ko.parent_id:
            parent = await self.repo.get_by_id(ko.parent_id)
            if parent and parent.object_type != ko.object_type:
                parent_obj = parent

        derived_children = await self.repo.list_by_parent(ko.id)
        derivations = [c for c in derived_children if c.object_type != ko.object_type]

        return {
            "id": ko.id,
            "object_type": ko.object_type,
            "parent_source": parent_obj,
            "derived_children": derivations,
        }
