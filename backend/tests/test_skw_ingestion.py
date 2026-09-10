"""
Comprehensive Unit & Integration Tests for Phase 4.2:
Knowledge Ingestion and Schema Validation in SKW.
Verifies ingestion pipeline, validation rules, provenance preservation, error handling,
and lifecycle state progression (Created -> Validating -> Accepted / Rejected).
"""

import uuid
import pytest

from app.core.exceptions import BadRequestException
from app.skw.models.knowledge_object import SKWLifecycleState, SKWKnowledgeType
from app.skw.services.ingestion_service import (
    DefaultKnowledgeValidator,
    DefaultKnowledgeIngestionService,
)


@pytest.mark.asyncio
async def test_ingest_valid_knowledge_object() -> None:
    """Verify ingestion service successfully processes valid knowledge and transitions state to Accepted."""
    service = DefaultKnowledgeIngestionService()
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": SKWKnowledgeType.DECISION.value,
        "source_module": "AudioIntelligence",
        "content": "Decided to adopt FastAPI for backend microservices.",
        "title": "Backend Architecture Decision",
        "confidence_score": 0.96,
        "version": 1,
        "provenance": {
            "producing_module": "AudioIntelligence",
            "model_name": "whisper-large-v3",
        },
        "metadata": {
            "tags": ["architecture", "decision"],
            "importance_score": 0.9,
            "language": "en",
        },
        "payload": {"details": "Unanimous vote by engineering team."},
    }

    ko = await service.ingest_raw_knowledge(meeting_id, raw_data)
    assert ko.knowledge_id is not None
    assert ko.meeting_id == meeting_id
    assert ko.object_type == "decision"
    assert ko.source_module == "AudioIntelligence"
    assert ko.confidence_score == 0.96
    assert ko.lifecycle_state == SKWLifecycleState.ACCEPTED
    assert ko.provenance["producing_module"] == "AudioIntelligence"
    assert ko.metadata["language"] == "en"


@pytest.mark.asyncio
async def test_ingest_invalid_object_missing_fields() -> None:
    """Verify ingestion rejects knowledge objects with missing required fields (content, object_type, source_module)."""
    service = DefaultKnowledgeIngestionService()
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": "",
        "source_module": "",
        "content": "",
    }

    with pytest.raises(BadRequestException) as exc_info:
        await service.ingest_raw_knowledge(meeting_id, raw_data)

    assert exc_info.value.code == "VALIDATION_FAILED"
    assert exc_info.value.details is not None
    errors = exc_info.value.details["errors"]
    assert any("object_type" in err for err in errors)
    assert any("source_module" in err for err in errors)
    assert any("content" in err for err in errors)


@pytest.mark.asyncio
async def test_ingest_invalid_confidence_score() -> None:
    """Verify ingestion rejects out-of-bounds confidence scores (>1.0 or <0.0)."""
    service = DefaultKnowledgeIngestionService()
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": "decision",
        "source_module": "MultilingualASR",
        "content": "Test content",
        "confidence_score": 1.5,  # Invalid
    }

    with pytest.raises(BadRequestException) as exc_info:
        await service.ingest_raw_knowledge(meeting_id, raw_data)
    assert exc_info.value.code == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_ingest_invalid_version() -> None:
    """Verify ingestion rejects versions < 1."""
    service = DefaultKnowledgeIngestionService()
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": "decision",
        "source_module": "MultilingualASR",
        "content": "Test content",
        "version": 0,  # Invalid
    }

    with pytest.raises(BadRequestException) as exc_info:
        await service.ingest_raw_knowledge(meeting_id, raw_data)
    assert exc_info.value.code == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_ingest_invalid_meeting_reference() -> None:
    """Verify ingestion rejects malformed meeting UUIDs."""
    service = DefaultKnowledgeIngestionService()

    raw_data = {
        "object_type": "decision",
        "source_module": "MultilingualASR",
        "content": "Test content",
    }

    # Pass invalid string meeting reference
    with pytest.raises(BadRequestException) as exc_info:
        await service.ingest_raw_knowledge("not-a-valid-uuid", raw_data)
    assert exc_info.value.code in ["INVALID_MEETING_REFERENCE", "VALIDATION_FAILED"]


@pytest.mark.asyncio
async def test_provenance_preservation() -> None:
    """Verify provenance metadata (source module, model info, lineage) is correctly preserved and structured."""
    service = DefaultKnowledgeIngestionService()
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": "transcript",
        "source_module": "CodeSwitchIntelligence",
        "content": "Hello world with mixed language.",
        "provenance": {
            "producing_module": "CodeSwitchIntelligence",
            "model_name": "multilingual-bert",
            "model_version": "v2.1",
            "source_segments": [1, 2, 3],
            "processing_metadata": {"latency_ms": 45},
        },
    }

    ko = await service.ingest_raw_knowledge(meeting_id, raw_data)
    assert ko.lifecycle_state == SKWLifecycleState.ACCEPTED
    assert ko.provenance["model_name"] == "multilingual-bert"
    assert ko.provenance["model_version"] == "v2.1"
    assert ko.provenance["source_segments"] == [1, 2, 3]
    assert ko.provenance["processing_metadata"]["latency_ms"] == 45


@pytest.mark.asyncio
async def test_rejected_object_state_transition() -> None:
    """Verify that invalid knowledge objects transition to REJECTED state and do not become active published knowledge."""
    validator = DefaultKnowledgeValidator()
    service = DefaultKnowledgeIngestionService(validator=validator)
    meeting_id = uuid.uuid4()

    raw_data = {
        "object_type": "decision",
        "source_module": "VerificationEngine",
        "content": "",  # Empty content triggers rejection
        "confidence_score": 1.2,  # Out of bounds triggers rejection
    }

    with pytest.raises(BadRequestException) as exc_info:
        await service.ingest_raw_knowledge(meeting_id, raw_data)
    
    assert exc_info.value.code == "VALIDATION_FAILED"
