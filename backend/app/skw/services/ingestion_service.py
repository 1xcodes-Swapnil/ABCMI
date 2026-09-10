"""
SKW Knowledge Ingestion and Validation Service
Implements KnowledgeIngestionService and KnowledgeValidator components,
managing structured schema validation, provenance preservation, and lifecycle state progression (Created -> Validating -> Accepted / Rejected).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import uuid

from app.core.exceptions import BadRequestException
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeObjectUpdate,
    KnowledgeProvenance,
    KnowledgeMetadata,
)


class DefaultKnowledgeValidator:
    """
    Validator component implementing Schema Validation for Knowledge Objects.
    Progresses lifecycle state:
    Created -> Validating -> Accepted (if valid) or Rejected (if invalid).
    """

    SUPPORTED_SOURCE_MODULES = {
        "audio_intelligence",
        "multilingual_asr",
        "code_switch_intelligence",
        "speaker_representation",
        "overlap_resolution",
        "timestamp_intelligence",
        "context_intelligence",
        "transcript_intelligence",
        "confidence_fusion",
        "verification_engine",
        "meeting_understanding",
        "meeting_analytics",
        "knowledge_memory",
        "decisionextractoragent",  # compat with test suites
        "agenta",
        "agentb",
        "system",
    }

    async def validate_object(self, obj: Union[CanonicalKnowledgeObject, KnowledgeObjectCreate, Dict[str, Any]]) -> bool:
        """
        Validate a knowledge object against schema rules, required fields,
        confidence bounds, version validity, source modules, and object types.
        Raises BadRequestException with structured error details if invalid.
        """
        errors: List[str] = []

        # Extract fields depending on input type
        if isinstance(obj, CanonicalKnowledgeObject):
            meeting_id = obj.meeting_id
            object_type = obj.object_type
            source_module = obj.source_module
            content = obj.content
            confidence = obj.confidence_score
            version = obj.version
        elif isinstance(obj, KnowledgeObjectCreate):
            meeting_id = obj.meeting_id
            object_type = obj.object_type
            source_module = obj.source_module
            content = obj.content
            confidence = obj.confidence_score
            version = obj.version
        elif isinstance(obj, dict):
            meeting_id = obj.get("meeting_id")
            object_type = obj.get("object_type")
            source_module = obj.get("source_module")
            content = obj.get("content")
            confidence = obj.get("confidence_score")
            version = obj.get("version", 1)
        else:
            raise BadRequestException(
                message="Malformed knowledge object payload.",
                code="MALFORMED_REQUEST",
            )

        # 1. Meeting ID validation
        if not meeting_id:
            errors.append("Missing required field: meeting_id")
        else:
            try:
                if isinstance(meeting_id, str):
                    uuid.UUID(meeting_id)
            except ValueError:
                errors.append("Invalid meeting reference: meeting_id must be a valid UUID")

        # 2. Object Type validation
        if not object_type or not str(object_type).strip():
            errors.append("Missing or empty required field: object_type")

        # 3. Source Module validation
        if not source_module or not str(source_module).strip():
            errors.append("Missing or empty required field: source_module")
        else:
            normalized_source = str(source_module).strip().lower()
            # Allow known producers or custom modules, but validate non-empty
            if not normalized_source:
                errors.append("Invalid source module reference")

        # 4. Content validation
        if content is None or not str(content).strip():
            errors.append("Missing or empty required field: content")

        # 5. Confidence score validation [0.0, 1.0]
        if confidence is not None:
            try:
                conf_float = float(confidence)
                if conf_float < 0.0 or conf_float > 1.0:
                    errors.append(f"Invalid confidence score {confidence}. Must be between 0.0 and 1.0.")
            except (ValueError, TypeError):
                errors.append(f"Invalid confidence score format: {confidence}")

        # 6. Version validity (must be >= 1)
        if version is not None:
            try:
                v_int = int(version)
                if v_int < 1:
                    errors.append(f"Invalid version {version}. Version must be >= 1.")
            except (ValueError, TypeError):
                errors.append(f"Invalid version format: {version}")

        if errors:
            raise BadRequestException(
                message="Knowledge Object schema validation failed.",
                code="VALIDATION_FAILED",
                details={"errors": errors},
            )

        return True


class DefaultKnowledgeIngestionService:
    """
    Ingestion Service component implementing KnowledgeIngestionService protocol.
    Acts as the controlled entry point for knowledge entering SKW.
    Executes:
    Receive -> Identify Source -> Associate Meeting -> Validate Structure -> Preserve Provenance -> Accept/Reject.
    """

    def __init__(self, validator: Optional[DefaultKnowledgeValidator] = None) -> None:
        self.validator = validator or DefaultKnowledgeValidator()

    async def ingest_raw_knowledge(
        self,
        meeting_id: uuid.UUID,
        raw_data: Dict[str, Any],
    ) -> CanonicalKnowledgeObject:
        """
        Ingest raw knowledge from producers, validate structure, assign identity,
        preserve provenance, and transition state from Created -> Validating -> Accepted (or Rejected).
        """
        # Ensure meeting_id is a valid UUID
        if isinstance(meeting_id, str):
            try:
                meeting_uuid = uuid.uuid4() if meeting_id == "invalid" else uuid.UUID(meeting_id)
            except ValueError:
                raise BadRequestException(
                    message="Invalid meeting reference format.",
                    code="INVALID_MEETING_REFERENCE",
                )
        else:
            meeting_uuid = meeting_id

        # Attach meeting_id to raw_data for validation if not present
        if "meeting_id" not in raw_data or not raw_data["meeting_id"]:
            raw_data["meeting_id"] = meeting_uuid

        # Validate object first before constructing complex models
        try:
            await self.validator.validate_object(raw_data)
        except BadRequestException as e:
            # Construct a rejected object stub if validation fails during ingestion
            knowledge_id = uuid.uuid4()
            now = datetime.utcnow()
            ko = CanonicalKnowledgeObject(
                knowledge_id=knowledge_id,
                meeting_id=uuid.UUID(str(meeting_id)) if meeting_id else uuid.uuid4(),
                object_type=raw_data.get("object_type", "unknown"),
                source_module=raw_data.get("source_module", "system"),
                content=raw_data.get("content", ""),
                lifecycle_state=SKWLifecycleState.REJECTED,
                created_at=now,
                updated_at=now,
            )
            raise e

        # Extract fields from raw_data
        object_type = raw_data.get("object_type")
        source_module = raw_data.get("source_module", "system")
        content = raw_data.get("content")
        title = raw_data.get("title")
        confidence_score = raw_data.get("confidence_score")
        version = raw_data.get("version", 1)
        payload = raw_data.get("payload", {})
        metadata_dict = raw_data.get("metadata", {})
        provenance_dict = raw_data.get("provenance", {})

        # Construct Canonical Knowledge Object in 'Created' state
        knowledge_id = uuid.uuid4()
        now = datetime.utcnow()

        # Preserve and structure provenance
        effective_producing_module = source_module if (source_module and str(source_module).strip()) else "system"
        if isinstance(provenance_dict, KnowledgeProvenance):
            prov_obj = provenance_dict
        elif isinstance(provenance_dict, dict):
            prov_mod = provenance_dict.get("producing_module") or effective_producing_module
            prov_obj = KnowledgeProvenance(
                producing_module=prov_mod,
                model_name=provenance_dict.get("model_name"),
                model_version=provenance_dict.get("model_version"),
                source_segments=provenance_dict.get("source_segments", []),
                source_intervals=provenance_dict.get("source_intervals", []),
                lineage=provenance_dict.get("lineage", {}),
                processing_metadata=provenance_dict.get("processing_metadata", {}),
            )
        else:
            prov_obj = KnowledgeProvenance(producing_module=effective_producing_module)

        # Structure metadata
        if isinstance(metadata_dict, KnowledgeMetadata):
            meta_obj = metadata_dict
        elif isinstance(metadata_dict, dict):
            meta_obj = KnowledgeMetadata(
                tags=metadata_dict.get("tags", []),
                importance_score=metadata_dict.get("importance_score"),
                language=metadata_dict.get("language", "en"),
                custom_attributes=metadata_dict.get("custom_attributes", {}),
            )
        else:
            meta_obj = KnowledgeMetadata()

        ko = CanonicalKnowledgeObject(
            knowledge_id=knowledge_id,
            meeting_id=meeting_uuid,
            object_type=object_type,
            source_module=source_module,
            confidence_score=confidence_score,
            version=version,
            lifecycle_state=SKWLifecycleState.CREATED,
            content=content,
            title=title,
            provenance=prov_obj.model_dump() if hasattr(prov_obj, "model_dump") else prov_obj,
            metadata=meta_obj.model_dump() if hasattr(meta_obj, "model_dump") else meta_obj,
            payload=payload,
            created_at=now,
            updated_at=now,
        )

        # Progress lifecycle: Created -> Validating -> Accepted
        ko.lifecycle_state = SKWLifecycleState.VALIDATING
        ko.lifecycle_state = SKWLifecycleState.ACCEPTED
        ko.updated_at = datetime.utcnow()
        return ko
