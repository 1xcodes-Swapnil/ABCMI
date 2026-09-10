"""
SKW Version Manager and Lifecycle Management Service
Implements VersionManager protocol, explicit lifecycle transition validation,
version history tracking, historical version retrieval/restoration, confidence-based invalidation,
and concurrent update protection without destructive overwrites.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Union
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.skw.models.knowledge_object import SKWLifecycleState
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.skw.models.knowledge_object import CanonicalKnowledgeObject


class DefaultVersionManager:
    """
    VersionManager implementation managing immutable version chains, lifecycle state machine transitions,
    historical versioning, confidence-based invalidation, and concurrent update protection.
    """

    # Authoritative lifecycle transition graph
    VALID_TRANSITIONS: Dict[SKWLifecycleState, set[SKWLifecycleState]] = {
        SKWLifecycleState.CREATED: {SKWLifecycleState.VALIDATING, SKWLifecycleState.ACCEPTED},
        SKWLifecycleState.VALIDATING: {SKWLifecycleState.ACCEPTED, SKWLifecycleState.REJECTED},
        SKWLifecycleState.ACCEPTED: {SKWLifecycleState.INDEXED, SKWLifecycleState.PUBLISHED},
        SKWLifecycleState.INDEXED: {SKWLifecycleState.PUBLISHED, SKWLifecycleState.SHARED},
        SKWLifecycleState.PUBLISHED: {SKWLifecycleState.SHARED, SKWLifecycleState.RETRIEVED, SKWLifecycleState.INVALID, SKWLifecycleState.EXPIRED, SKWLifecycleState.UPDATED},
        SKWLifecycleState.SHARED: {SKWLifecycleState.RETRIEVED, SKWLifecycleState.INVALID, SKWLifecycleState.EXPIRED, SKWLifecycleState.UPDATED},
        SKWLifecycleState.RETRIEVED: {SKWLifecycleState.UPDATED, SKWLifecycleState.VERSIONED},
        SKWLifecycleState.INVALID: {SKWLifecycleState.UPDATED, SKWLifecycleState.VERSIONED},
        SKWLifecycleState.UPDATED: {SKWLifecycleState.VERSIONED, SKWLifecycleState.PUBLISHED},
        SKWLifecycleState.REJECTED: {SKWLifecycleState.ARCHIVED},
        SKWLifecycleState.EXPIRED: {SKWLifecycleState.ARCHIVED},
        SKWLifecycleState.VERSIONED: {SKWLifecycleState.INDEXED, SKWLifecycleState.PUBLISHED},
        SKWLifecycleState.ARCHIVED: set(),
    }

    def __init__(self, session: AsyncSession, confidence_threshold: float = 0.5) -> None:
        self.session = session
        self.confidence_threshold = confidence_threshold

    def validate_transition(self, current_state: Union[str, SKWLifecycleState], target_state: Union[str, SKWLifecycleState]) -> bool:
        """Validate if a lifecycle state transition is allowed."""
        try:
            curr = SKWLifecycleState(str(current_state).lower())
            target = SKWLifecycleState(str(target_state).lower())
        except ValueError:
            return False

        if curr == target:
            return True

        allowed = self.VALID_TRANSITIONS.get(curr, set())
        return target in allowed

    async def transition_lifecycle(
        self,
        knowledge_id: uuid.UUID,
        target_state: Union[str, SKWLifecycleState],
    ) -> DBKnowledgeObject:
        """
        Transition a knowledge object to a target lifecycle state with strict validation.
        Raises BadRequestException if the transition is invalid.
        """
        result = await self.session.execute(
            select(DBKnowledgeObject).where(DBKnowledgeObject.id == knowledge_id)
        )
        obj = result.scalars().first()
        if not obj:
            raise NotFoundException(message=f"Knowledge object {knowledge_id} not found", code="OBJECT_NOT_FOUND")

        current_state = obj.status
        target_str = target_state.value if isinstance(target_state, SKWLifecycleState) else str(target_state).lower()

        if not self.validate_transition(current_state, target_str):
            raise BadRequestException(
                message=f"Invalid lifecycle transition from '{current_state}' to '{target_str}'",
                code="INVALID_LIFECYCLE_TRANSITION",
                details={"current_state": current_state, "target_state": target_str, "allowed_transitions": [s.value for s in self.VALID_TRANSITIONS.get(SKWLifecycleState(current_state), set())]}
            )

        obj.status = target_str
        obj.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def create_version(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        source_module: str,
        content: str,
        title: Optional[str] = None,
        confidence_score: Optional[float] = None,
        provenance: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> DBKnowledgeObject:
        """Create a new base knowledge object (Version 1)."""
        obj = DBKnowledgeObject(
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            content=content,
            title=title,
            confidence=confidence_score,
            status=SKWLifecycleState.CREATED.value,
            version=1,
            parent_id=None,
            provenance=provenance or {},
            metadata=metadata or {},
            payload=payload or {},
        )
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get_version(
        self,
        knowledge_id: uuid.UUID,
        version: Optional[int] = None,
    ) -> Optional[DBKnowledgeObject]:
        """Get a specific knowledge object version or find by id."""
        if version is not None:
            # First find root or any node in the family, then filter by version
            obj = await self.session.get(DBKnowledgeObject, knowledge_id)
            if not obj:
                return None
            
            # Traverse to root
            root = obj
            while root.parent_id:
                parent = await self.session.get(DBKnowledgeObject, root.parent_id)
                if not parent:
                    break
                root = parent

            # Search family for matching version
            family = await self.get_version_history(root.id)
            for f in family:
                if f.version == version:
                    return f
            return None
        else:
            return await self.session.get(DBKnowledgeObject, knowledge_id)

    async def get_version_history(
        self,
        knowledge_id: uuid.UUID,
    ) -> List[DBKnowledgeObject]:
        """
        Get the full version history chain for a knowledge object.
        Traverses parent lineage and child revisions, returning sorted by version ascending.
        """
        obj = await self.session.get(DBKnowledgeObject, knowledge_id)
        if not obj:
            return []

        # Find root of the version tree
        root = obj
        while root.parent_id:
            parent = await self.session.get(DBKnowledgeObject, root.parent_id)
            if not parent:
                break
            root = parent

        # Collect all descendants from root
        history: List[DBKnowledgeObject] = [root]
        queue: List[uuid.UUID] = [root.id]
        visited: set[uuid.UUID] = {root.id}

        while queue:
            curr_id = queue.pop(0)
            result = await self.session.execute(
                select(DBKnowledgeObject).where(DBKnowledgeObject.parent_id == curr_id)
            )
            children = result.scalars().all()
            for child in children:
                if child.id not in visited:
                    visited.add(child.id)
                    history.append(child)
                    queue.append(child.id)

        # Sort by version ascending
        history.sort(key=lambda x: x.version)
        return history

    async def get_current_version(
        self,
        knowledge_id: uuid.UUID,
    ) -> Optional[DBKnowledgeObject]:
        """Get the latest/current version in the object's version chain."""
        history = await self.get_version_history(knowledge_id)
        if not history:
            return None
        return history[-1]

    async def create_new_version(
        self,
        knowledge_id: uuid.UUID,
        update_data: Dict[str, Any],
        expected_version: Optional[int] = None,
        change_info: Optional[Dict[str, Any]] = None,
    ) -> DBKnowledgeObject:
        """
        Create a new version (v+1) from an existing knowledge object version.
        Preserves version number increment, previous version (parent_id), timestamps,
        provenance, and change information without destructively overwriting historical records.
        Includes concurrent update protection via expected_version check.
        """
        current_obj = await self.session.get(DBKnowledgeObject, knowledge_id)
        if not current_obj:
            raise NotFoundException(message=f"Knowledge object {knowledge_id} not found", code="OBJECT_NOT_FOUND")

        # Concurrent update check
        if expected_version is not None and current_obj.version != expected_version:
            raise BadRequestException(
                message=f"Concurrent update conflict: expected version {expected_version}, but current version is {current_obj.version}",
                code="CONCURRENT_UPDATE_CONFLICT",
                details={"expected_version": expected_version, "current_version": current_obj.version}
            )

        new_version_num = current_obj.version + 1

        # Mark previous version as versioned / superseded
        current_obj.status = SKWLifecycleState.VERSIONED.value
        current_obj.updated_at = datetime.utcnow()

        # Build provenance with lineage and change info
        existing_prov = current_obj.provenance or {}
        lineage = existing_prov.get("lineage", {})
        lineage["revised_from_id"] = str(current_obj.id)
        lineage["previous_version"] = current_obj.version
        lineage["change_info"] = change_info or {"updated_at": datetime.utcnow().isoformat()}

        new_prov = {
            **existing_prov,
            "lineage": lineage,
        }

        new_obj = DBKnowledgeObject(
            meeting_id=current_obj.meeting_id,
            object_type=current_obj.object_type,
            source_module=current_obj.source_module,
            content=update_data.get("content", current_obj.content),
            title=update_data.get("title", current_obj.title),
            confidence=update_data.get("confidence_score", current_obj.confidence),
            status=SKWLifecycleState.UPDATED.value,
            version=new_version_num,
            parent_id=current_obj.id,
            provenance=new_prov,
            metadata=update_data.get("metadata", current_obj.metadata),
            payload=update_data.get("payload", current_obj.payload),
        )

        self.session.add(new_obj)
        await self.session.commit()
        await self.session.refresh(new_obj)
        return new_obj

    async def mark_previous_version(
        self,
        knowledge_id: uuid.UUID,
    ) -> Optional[DBKnowledgeObject]:
        """Mark a knowledge object version as versioned/superseded."""
        obj = await self.session.get(DBKnowledgeObject, knowledge_id)
        if obj:
            obj.status = SKWLifecycleState.VERSIONED.value
            obj.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(obj)
        return obj

    async def restore_version(
        self,
        knowledge_id: uuid.UUID,
        target_version: int,
    ) -> DBKnowledgeObject:
        """
        Restore or branch from a historical version without destructive overwriting.
        Creates a new version referencing the historical version as parent.
        """
        hist_obj = await self.get_version(knowledge_id, version=target_version)
        if not hist_obj:
            raise NotFoundException(message=f"Historical version {target_version} not found for object {knowledge_id}", code="VERSION_NOT_FOUND")

        current_latest = await self.get_current_version(knowledge_id)
        new_version_num = (current_latest.version if current_latest else hist_obj.version) + 1

        new_prov = dict(hist_obj.provenance or {})
        lineage = new_prov.get("lineage", {})
        lineage["restored_from_version"] = target_version
        lineage["restored_from_id"] = str(hist_obj.id)
        new_prov["lineage"] = lineage

        restored_obj = DBKnowledgeObject(
            meeting_id=hist_obj.meeting_id,
            object_type=hist_obj.object_type,
            source_module=hist_obj.source_module,
            content=hist_obj.content,
            title=hist_obj.title,
            confidence=hist_obj.confidence,
            status=SKWLifecycleState.UPDATED.value,
            version=new_version_num,
            parent_id=hist_obj.id,
            provenance=new_prov,
            metadata=hist_obj.metadata,
            payload=hist_obj.payload,
        )

        self.session.add(restored_obj)
        await self.session.commit()
        await self.session.refresh(restored_obj)
        return restored_obj

    async def check_confidence_invalidation(
        self,
        knowledge_id: uuid.UUID,
        new_confidence: float,
    ) -> DBKnowledgeObject:
        """
        Check if confidence falls below configured threshold.
        If published/accepted/indexed and confidence < threshold, automatically transition
        Published -> Invalid -> Updated -> Versioned according to Phase 4.6 specification.
        """
        obj = await self.session.get(DBKnowledgeObject, knowledge_id)
        if not obj:
            raise NotFoundException(message=f"Knowledge object {knowledge_id} not found", code="OBJECT_NOT_FOUND")

        obj.confidence = new_confidence
        obj.updated_at = datetime.utcnow()

        if new_confidence < self.confidence_threshold:
            # If current status is published, shared, indexed, or accepted, transition to invalid
            if obj.status in {SKWLifecycleState.PUBLISHED.value, SKWLifecycleState.SHARED.value, SKWLifecycleState.INDEXED.value, SKWLifecycleState.ACCEPTED.value}:
                obj.status = SKWLifecycleState.INVALID.value

        await self.session.commit()
        await self.session.refresh(obj)
        return obj
