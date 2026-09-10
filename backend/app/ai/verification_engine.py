"""
Verification Engine (Phase 4.12C)
Evaluates AI outputs against confidence thresholds, manages lifecycle state transitions,
routes low-confidence artifacts for verification, and triggers SKW rejection/recovery flows.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
from pydantic import Field

from app.models.knowledge_object import KnowledgeObjectStatus
from app.schemas.base import CoreBaseModel
from app.schemas.knowledge_object import KnowledgeObjectCreate, ProvenanceMetadataSchema


class VerificationResult(CoreBaseModel):
    """Verification assessment output model."""

    verification_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    meeting_id: uuid.UUID
    target_object_id: Optional[uuid.UUID] = None
    target_object_type: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_threshold: float = Field(default=0.70)
    verification_passed: bool
    status: KnowledgeObjectStatus
    requires_verification: bool
    rejection_reason: Optional[str] = None
    verification_notes: Optional[str] = None
    correlation_id: Optional[str] = None
    provenance: ProvenanceMetadataSchema
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VerificationEngine:
    """
    Verification Engine Service.
    Enforces confidence validation pipelines and manages Knowledge Object lifecycle state transitions:
    - High Confidence (>= 0.70): Status = ACTIVE / VALIDATED
    - Low Confidence (< 0.70): Status = DRAFT with requires_verification = True
    - Human / Automated Verification Approval: Status -> VALIDATED / ACTIVE
    - Verification Rejection: Status -> REJECTED (triggers SKW rejection/ACE recovery)
    """

    CONFIDENCE_THRESHOLD = 0.70

    def __init__(self, confidence_threshold: float = 0.70) -> None:
        self.confidence_threshold = confidence_threshold

    def evaluate_output(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        content: str,
        confidence_score: float,
        title: Optional[str] = None,
        correlation_id: Optional[str] = None,
        source_module: str = "verification_engine",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[KnowledgeObjectCreate, VerificationResult]:
        """
        Evaluates AI output confidence score and builds a compliant KnowledgeObjectCreate schema.
        Routes output to ACTIVE state if confidence >= threshold, or DRAFT state if < threshold.
        """
        confidence = max(0.0, min(1.0, float(confidence_score)))
        is_high_confidence = confidence >= self.confidence_threshold

        lifecycle_status = (
            KnowledgeObjectStatus.ACTIVE if is_high_confidence else KnowledgeObjectStatus.DRAFT
        )
        requires_verification = not is_high_confidence

        payload_data = dict(payload or {})
        payload_data["requires_verification"] = requires_verification
        payload_data["correlation_id"] = correlation_id

        prov = ProvenanceMetadataSchema(
            producing_module=source_module,
            model_name="verification_engine_v1",
            model_version="1.0.0",
            source_segments=[],
            source_intervals=[],
            lineage={"confidence_score": confidence, "evaluated_at": datetime.utcnow().isoformat()},
            processing_metadata={
                "correlation_id": correlation_id,
                "confidence_threshold": self.confidence_threshold,
                "is_high_confidence": is_high_confidence,
            },
        )

        ko_create = KnowledgeObjectCreate(
            meeting_id=meeting_id,
            object_type=object_type,
            title=title or f"{object_type.replace('_', ' ').title()} Extraction",
            content=content,
            confidence=confidence,
            status=lifecycle_status,
            version=1,
            provenance=prov,
            payload=payload_data,
        )

        verif_res = VerificationResult(
            meeting_id=meeting_id,
            target_object_type=object_type,
            confidence_score=confidence,
            confidence_threshold=self.confidence_threshold,
            verification_passed=is_high_confidence,
            status=lifecycle_status,
            requires_verification=requires_verification,
            verification_notes=(
                "Passed automatic confidence verification threshold"
                if is_high_confidence
                else "Confidence below threshold; queued for verification review"
            ),
            correlation_id=correlation_id,
            provenance=prov,
        )

        return ko_create, verif_res

    def verify_and_promote(
        self,
        ko_create: KnowledgeObjectCreate,
        verifier_id: Optional[str] = None,
        notes: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[KnowledgeObjectCreate, VerificationResult]:
        """
        Promotes a low-confidence/DRAFT Knowledge Object to VALIDATED state upon successful verification.
        """
        promoted_payload = dict(ko_create.payload or {})
        promoted_payload["requires_verification"] = False
        promoted_payload["verifier_id"] = verifier_id or "system_verifier"
        promoted_payload["verified_at"] = datetime.utcnow().isoformat()

        promoted_ko = KnowledgeObjectCreate(
            meeting_id=ko_create.meeting_id,
            object_type=ko_create.object_type,
            title=ko_create.title,
            content=ko_create.content,
            confidence=max(ko_create.confidence or 0.85, 0.85),
            status=KnowledgeObjectStatus.VALIDATED,
            version=ko_create.version,
            parent_id=ko_create.parent_id,
            provenance=ko_create.provenance,
            payload=promoted_payload,
            qdrant_point_id=ko_create.qdrant_point_id,
        )

        status_str = ko_create.status.value if hasattr(ko_create.status, "value") else str(ko_create.status)

        prov = ProvenanceMetadataSchema(
            producing_module="verification_engine",
            model_name="verification_engine_v1",
            model_version="1.0.0",
            lineage={"promoted_from_status": status_str},
            processing_metadata={"correlation_id": correlation_id, "verifier": verifier_id},
        )

        res = VerificationResult(
            meeting_id=ko_create.meeting_id,
            target_object_type=ko_create.object_type,
            confidence_score=promoted_ko.confidence or 0.85,
            confidence_threshold=self.confidence_threshold,
            verification_passed=True,
            status=KnowledgeObjectStatus.VALIDATED,
            requires_verification=False,
            verification_notes=notes or "Successfully verified and promoted to VALIDATED status",
            correlation_id=correlation_id,
            provenance=prov,
        )

        return promoted_ko, res

    def reject_object(
        self,
        ko_create: KnowledgeObjectCreate,
        rejection_reason: str,
        reviewer_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[KnowledgeObjectCreate, VerificationResult]:
        """
        Rejects a Knowledge Object, transitioning its status to REJECTED.
        Triggers SKW rejection and recovery flow without deleting existing valid knowledge.
        """
        rejected_payload = dict(ko_create.payload or {})
        rejected_payload["rejection_reason"] = rejection_reason
        rejected_payload["rejected_by"] = reviewer_id or "system_verifier"
        rejected_payload["rejected_at"] = datetime.utcnow().isoformat()

        rejected_ko = KnowledgeObjectCreate(
            meeting_id=ko_create.meeting_id,
            object_type=ko_create.object_type,
            title=ko_create.title,
            content=ko_create.content,
            confidence=ko_create.confidence or 0.0,
            status=KnowledgeObjectStatus.REJECTED,
            version=ko_create.version,
            parent_id=ko_create.parent_id,
            provenance=ko_create.provenance,
            payload=rejected_payload,
        )

        prov = ProvenanceMetadataSchema(
            producing_module="verification_engine",
            model_name="verification_engine_v1",
            model_version="1.0.0",
            lineage={"rejected_reason": rejection_reason},
            processing_metadata={"correlation_id": correlation_id, "rejected_by": reviewer_id},
        )

        res = VerificationResult(
            meeting_id=ko_create.meeting_id,
            target_object_type=ko_create.object_type,
            confidence_score=ko_create.confidence or 0.0,
            confidence_threshold=self.confidence_threshold,
            verification_passed=False,
            status=KnowledgeObjectStatus.REJECTED,
            requires_verification=False,
            rejection_reason=rejection_reason,
            verification_notes=f"Object rejected during verification: {rejection_reason}",
            correlation_id=correlation_id,
            provenance=prov,
        )

        return rejected_ko, res
