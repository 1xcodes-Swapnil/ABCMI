"""
Unit and Integration Tests for Phase 4.3: Context and Metadata Enrichment in SKW.
Verifies successful enrichment, missing optional metadata, content and timestamp preservation,
provenance preservation, meeting & speaker association, and idempotent enrichment.
"""

import uuid
import pytest
from datetime import datetime

from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.services.enrichment_service import DefaultKnowledgeEnrichmentService


@pytest.mark.asyncio
async def test_successful_enrichment_with_context() -> None:
    """Verify knowledge object is successfully enriched with meeting metadata and speaker association."""
    service = DefaultKnowledgeEnrichmentService()
    meeting_id = uuid.uuid4()
    ko = CanonicalKnowledgeObject(
        meeting_id=meeting_id,
        object_type="decision",
        source_module="AudioIntelligence",
        content="Approve the proposed Q3 budget.",
        confidence_score=0.92,
        lifecycle_state=SKWLifecycleState.ACCEPTED,
    )

    original_content = ko.content
    original_id = ko.knowledge_id
    original_meeting_id = ko.meeting_id

    context = {
        "meeting": {
            "title": "Quarterly Planning",
            "status": "active",
            "language": "en",
            "actual_start": datetime.utcnow().isoformat(),
        },
        "participants": [
            {
                "id": str(uuid.uuid4()),
                "display_name": "Alice Smith",
                "role": "host",
                "speaker_label": "SPEAKER_01",
            }
        ],
        "speaker_label": "SPEAKER_01",
        "processing_stage": "semantic_enrichment",
    }

    enriched = await service.enrich_object(ko, context)

    # Verify preservation of original core fields
    assert enriched.content == original_content
    assert enriched.knowledge_id == original_id
    assert enriched.meeting_id == original_meeting_id

    # Verify enrichment additions
    assert enriched.metadata["language"] == "en"
    assert enriched.metadata["custom_attributes"]["meeting_title"] == "Quarterly Planning"
    assert enriched.metadata["custom_attributes"]["processing_stage"] == "semantic_enrichment"
    assert enriched.metadata["custom_attributes"]["speaker_info"]["display_name"] == "Alice Smith"
    assert enriched.provenance["enrichment_context"]["enriched"] is True


@pytest.mark.asyncio
async def test_enrichment_with_missing_optional_metadata() -> None:
    """Verify enrichment completes successfully when optional context metadata is missing."""
    service = DefaultKnowledgeEnrichmentService()
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        object_type="insight",
        source_module="MeetingAnalytics",
        content="Meeting participation was high.",
        lifecycle_state=SKWLifecycleState.ACCEPTED,
        metadata={"language": "es"},
    )

    enriched = await service.enrich_object(ko, context={})

    # Preserves existing metadata language and adds defaults without error
    assert enriched.metadata["language"] == "es"
    assert enriched.metadata["custom_attributes"]["processing_stage"] == "enrichment"
    assert enriched.provenance["enrichment_context"]["enriched"] is True


@pytest.mark.asyncio
async def test_provenance_and_timestamp_preservation() -> None:
    """Verify provenance producing modules, initial creation timestamps, and tracking are preserved."""
    service = DefaultKnowledgeEnrichmentService()
    created_time = datetime(2026, 8, 1, 10, 0, 0)
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        object_type="action_item",
        source_module="VerificationEngine",
        content="Review security audit report.",
        provenance={"producing_module": "VerificationEngine", "model_name": "gpt-4"},
        created_at=created_time,
    )

    enriched = await service.enrich_object(ko, context={"processing_stage": "audit"})

    assert enriched.provenance["producing_module"] == "VerificationEngine"
    assert enriched.provenance["model_name"] == "gpt-4"
    assert enriched.created_at == created_time
    assert enriched.provenance["enrichment_context"]["processing_stage"] == "audit"


@pytest.mark.asyncio
async def test_idempotent_enrichment() -> None:
    """Verify running enrichment multiple times is idempotent and produces consistent state."""
    service = DefaultKnowledgeEnrichmentService()
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        object_type="topic",
        source_module="TranscriptIntelligence",
        content="Project Roadmap Discussion",
        lifecycle_state=SKWLifecycleState.ACCEPTED,
    )

    context = {
        "meeting": {"title": "Roadmap Sync", "language": "en"},
        "processing_stage": "stage_1",
    }

    enriched_once = await service.enrich_object(ko, context)
    stage_1_timestamp = enriched_once.metadata["custom_attributes"]["enriched_at"]

    enriched_twice = await service.enrich_object(enriched_once, context)

    # Core content unchanged, custom attributes stable
    assert enriched_twice.content == "Project Roadmap Discussion"
    assert enriched_twice.metadata["custom_attributes"]["meeting_title"] == "Roadmap Sync"
    assert enriched_twice.provenance["enrichment_context"]["enriched"] is True
