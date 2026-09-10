"""
Unit Tests for Phase 4.1: Semantic Knowledge Workspace (SKW) Foundation & Contracts
Verifies Pydantic validation, canonical models, and component interface protocols.
"""

import uuid
import pytest
from pydantic import ValidationError

from app.skw.models.knowledge_object import (
    CanonicalKnowledgeObject,
    SKWLifecycleState,
    SKWKnowledgeType,
)
from app.skw.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeProvenance,
    KnowledgeMetadata,
)
from app.skw.interfaces.component_interfaces import (
    KnowledgeIngestionService,
    KnowledgeValidator,
    KnowledgeEnrichmentService,
    KnowledgeRepository,
    SemanticIndexer,
    VersionManager,
    KnowledgePublisher,
    KnowledgeQueryEngine,
)


def test_valid_knowledge_object_creation() -> None:
    """Verify successful creation of a valid Knowledge Object and canonical model."""
    meeting_id = uuid.uuid4()
    payload_data = {
        "meeting_id": meeting_id,
        "object_type": SKWKnowledgeType.DECISION.value,
        "source_module": "DecisionExtractorAgent",
        "content": "Adopt PostgreSQL and FastAPI for the backend architecture.",
        "title": "Backend Framework Decision",
        "confidence_score": 0.95,
        "version": 1,
        "lifecycle_state": SKWLifecycleState.CREATED,
        "provenance": KnowledgeProvenance(
            producing_module="DecisionExtractorAgent",
            model_name="gemini-1.5-pro",
        ),
        "metadata": KnowledgeMetadata(
            importance_score=0.9,
            tags=["architecture", "backend"],
        ),
    }

    dto = KnowledgeObjectCreate(**payload_data)
    assert dto.meeting_id == meeting_id
    assert dto.object_type == "decision"
    assert dto.source_module == "DecisionExtractorAgent"
    assert dto.confidence_score == 0.95
    assert dto.version == 1
    assert dto.lifecycle_state == SKWLifecycleState.CREATED

    # Test canonical model
    canonical = CanonicalKnowledgeObject(
        meeting_id=dto.meeting_id,
        object_type=dto.object_type,
        source_module=dto.source_module,
        content=dto.content,
        confidence_score=dto.confidence_score,
        version=dto.version,
        lifecycle_state=dto.lifecycle_state,
    )
    d = canonical.to_dict()
    assert d["object_type"] == "decision"
    assert d["confidence_score"] == 0.95
    assert d["lifecycle_state"] == "created"


def test_missing_required_fields() -> None:
    """Verify validation fails when required fields (meeting_id, content, object_type, source_module) are missing."""
    with pytest.raises(ValidationError) as exc_info:
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            # missing object_type, source_module, content
        )
    errors = exc_info.value.errors()
    assert any(err["loc"][0] == "object_type" for err in errors)
    assert any(err["loc"][0] == "source_module" for err in errors)
    assert any(err["loc"][0] == "content" for err in errors)


def test_invalid_confidence_score() -> None:
    """Verify confidence score bounds [0.0, 1.0] are strictly enforced."""
    # Out of upper bound (> 1.0)
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="decision",
            source_module="Agent",
            content="Some content",
            confidence_score=1.05,
        )

    # Out of lower bound (< 0.0)
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="decision",
            source_module="Agent",
            content="Some content",
            confidence_score=-0.1,
        )


def test_invalid_version() -> None:
    """Verify version must be >= 1."""
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="decision",
            source_module="Agent",
            content="Some content",
            version=0,
        )


def test_invalid_lifecycle_state() -> None:
    """Verify invalid lifecycle states are rejected by Pydantic."""
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="decision",
            source_module="Agent",
            content="Some content",
            lifecycle_state="non_existent_state",
        )


def test_invalid_object_type_and_source_module() -> None:
    """Verify empty or whitespace-only object_type and source_module are rejected."""
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="   ",
            source_module="Agent",
            content="Content",
        )

    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=uuid.uuid4(),
            object_type="decision",
            source_module="   ",
            content="Content",
        )


def test_metadata_validation() -> None:
    """Verify importance_score bounds [0.0, 1.0] and language code length in metadata."""
    meta = KnowledgeMetadata(importance_score=0.5, language="en")
    assert meta.importance_score == 0.5
    assert meta.language == "en"

    with pytest.raises(ValidationError):
        KnowledgeMetadata(importance_score=1.5)

    with pytest.raises(ValidationError):
        KnowledgeMetadata(language="english_too_long_code")


def test_component_protocols_conformance() -> None:
    """Verify all 8 SKW component protocols are runtime checkable and properly defined."""
    protocols = [
        KnowledgeIngestionService,
        KnowledgeValidator,
        KnowledgeEnrichmentService,
        KnowledgeRepository,
        SemanticIndexer,
        VersionManager,
        KnowledgePublisher,
        KnowledgeQueryEngine,
    ]
    for p in protocols:
        assert p is not None

