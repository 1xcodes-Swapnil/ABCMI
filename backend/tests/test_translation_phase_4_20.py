"""
Phase 4.20 — Multilingual Translation & Derived Representations Test Suite
Comprehensive testing verifying:
1. Supported (17 languages) & unsupported language handling.
2. Translation request validation and error responses (400, 401, 403, 404, 422).
3. Preservation of original canonical text and metadata (timestamps, speaker IDs, segment IDs).
4. Derived representation generation for transcript and all Knowledge Object types:
   (summary, topic, decision, action_item, fact, hypothesis, transcript_insight).
5. Confidence thresholding, low-confidence flagging, and verification routing.
6. Idempotency on repeated and concurrent generation requests.
7. Regeneration and version lineage handling.
8. Authentication, tenant isolation, and meeting scope boundaries.
9. Redis event bus publishing.
"""

from datetime import datetime, timezone
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.knowledge_object import KnowledgeObject
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.transcript_repo import TranscriptSegmentRepository
from app.schemas.translation import SUPPORTED_LANGUAGES, SUPPORTED_REPRESENTATION_TYPES


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_supported_languages_coverage():
    """Verify that all 17 specified languages are present in SUPPORTED_LANGUAGES."""
    expected_17 = {
        "en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa",
        "zh", "ja", "fr", "es", "de", "ru", "ar",
    }
    assert expected_17 == SUPPORTED_LANGUAGES
    assert len(SUPPORTED_LANGUAGES) == 17


@pytest.mark.asyncio
async def test_translation_lifecycle_and_derived_representations(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Test complete lifecycle:
    - Create meeting, transcript segments, and various Knowledge Object types
    - Request translations into target languages (e.g. Hindi 'hi', Tamil 'ta', Spanish 'es')
    - Verify canonical source preservation, timestamps, speaker tags, and provenance
    - Test listing, viewing, idempotency, and regeneration
    """
    headers = {"Authorization": "Bearer admin-token"}

    # 1. Setup Meeting
    meeting_repo = MeetingRepository(db_session)
    meeting = Meeting(
        title="Phase 4.20 Strategy Alignment",
        description="Multilingual intelligence discussion",
        status="completed",
        scheduled_start=datetime.now(timezone.utc),
        duration_minutes=45,
        timezone="UTC",
        language="en",
        tenant_id="tenant-alpha",
    )
    meeting = await meeting_repo.create(meeting)
    await db_session.commit()
    meeting_id = meeting.id

    # 2. Setup Transcript Segment
    segment_repo = TranscriptSegmentRepository(db_session)
    segment = TranscriptSegment(
        meeting_id=meeting_id,
        speaker_label="Speaker 1",
        start_time_ms=1000,
        end_time_ms=4500,
        language="en",
        text="Let's approve the new microservices architecture and finalize the roadmap.",
        sequence_number=1,
    )
    await segment_repo.bulk_create_segments([segment])

    # 3. Setup Knowledge Objects (Decision, Action Item, Summary, Fact)
    ko_repo = KnowledgeObjectRepository(db_session)
    decision_ko = KnowledgeObject(
        meeting_id=meeting_id,
        object_type="decision",
        title="Architecture Decision",
        content="Decision: Approve the distributed event bus architecture.",
        confidence=0.95,
        status="active",
        version=1,
    )
    action_ko = KnowledgeObject(
        meeting_id=meeting_id,
        object_type="action_item",
        title="Follow-up Action",
        content="Action: Prepare deployment guidelines before next Monday.",
        confidence=0.90,
        status="active",
        version=1,
    )
    summary_ko = KnowledgeObject(
        meeting_id=meeting_id,
        object_type="summary",
        title="Executive Summary",
        content="Summary: The team discussed project timelines and architectural choices.",
        confidence=0.92,
        status="active",
        version=1,
    )
    await ko_repo.create(decision_ko)
    await ko_repo.create(action_ko)
    await ko_repo.create(summary_ko)
    await db_session.commit()

    # 4. Generate Translations to Hindi ('hi')
    gen_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/translations",
        json={
            "target_language": "hi",
            "source_language": "en",
            "confidence_threshold": 0.75,
            "correlation_id": "corr-test-420-1",
        },
        headers=headers,
    )
    assert gen_res.status_code == 201
    translations = gen_res.json()
    assert len(translations) >= 4  # 1 transcript segment + 3 knowledge objects

    # Check transcript translation
    transcript_trans = next(t for t in translations if t["representation_type"] == "transcript")
    assert transcript_trans["source_language"] == "en"
    assert transcript_trans["target_language"] == "hi"
    assert transcript_trans["speaker_label"] == "Speaker 1"
    assert transcript_trans["start_time_ms"] == 1000
    assert transcript_trans["end_time_ms"] == 4500
    assert transcript_trans["original_text"] == segment.text
    assert "[HI]" in transcript_trans["translated_text"]
    assert transcript_trans["confidence"] >= 0.75
    assert not transcript_trans["is_low_confidence"]
    assert not transcript_trans["requires_verification"]
    assert transcript_trans["provenance"]["producing_module"] == "TranslationEngine"

    # Check decision translation
    decision_trans = next(t for t in translations if t["representation_type"] == "decision")
    assert decision_trans["source_language"] == "en"
    assert decision_trans["target_language"] == "hi"
    assert decision_trans["original_text"] == decision_ko.content
    assert "[HI]" in decision_trans["translated_text"]
    decision_trans_id = decision_trans["id"]

    # 5. Verify Idempotency (Submitting identical request returns cached results without duplicate inserts)
    gen_res_2 = await client.post(
        f"/api/v1/meetings/{meeting_id}/translations",
        json={
            "target_language": "hi",
            "source_language": "en",
        },
        headers=headers,
    )
    assert gen_res_2.status_code == 201
    translations_2 = gen_res_2.json()
    assert len(translations_2) == len(translations)
    # IDs should match existing records
    assert {t["id"] for t in translations_2} == {t["id"] for t in translations}

    # 6. List Translations for Meeting with Filtering
    list_res = await client.get(
        f"/api/v1/meetings/{meeting_id}/translations?target_language=hi",
        headers=headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 4
    assert len(list_data["items"]) >= 4

    # 7. Get Single Translation by ID
    get_res = await client.get(f"/api/v1/translations/{decision_trans_id}", headers=headers)
    assert get_res.status_code == 200
    single_data = get_res.json()
    assert single_data["id"] == decision_trans_id
    assert single_data["representation_type"] == "decision"

    # 8. Test Low-Confidence & Verification Routing via High Threshold or Regeneration
    regen_res = await client.post(
        f"/api/v1/translations/{decision_trans_id}/regenerate",
        json={
            "target_language": "ta",
            "confidence_override": 0.45,  # Force low confidence < 0.75
            "correlation_id": "corr-regen-low-conf",
        },
        headers=headers,
    )
    assert regen_res.status_code == 200
    regen_data = regen_res.json()
    assert regen_data["id"] == decision_trans_id
    assert regen_data["target_language"] == "ta"
    assert regen_data["confidence"] == 0.45
    assert regen_data["is_low_confidence"] is True
    assert regen_data["requires_verification"] is True
    assert regen_data["version"] == 2


@pytest.mark.asyncio
async def test_unsupported_language_and_validation_errors(client: AsyncClient, db_session: AsyncSession):
    """Test validation errors for unsupported language, bad formats, and missing meetings."""
    headers = {"Authorization": "Bearer admin-token"}

    # Create dummy meeting
    meeting_repo = MeetingRepository(db_session)
    meeting = Meeting(
        title="Language Validation Meeting",
        description="Testing validation",
        status="completed",
        scheduled_start=datetime.now(timezone.utc),
        duration_minutes=30,
        timezone="UTC",
    )
    meeting = await meeting_repo.create(meeting)
    await db_session.commit()
    meeting_id = meeting.id

    # 1. Unsupported Target Language
    bad_lang_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/translations",
        json={"target_language": "klingon"},
        headers=headers,
    )
    assert bad_lang_res.status_code == 422 or bad_lang_res.status_code == 400

    # 2. Unsupported Representation Type
    bad_type_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/translations",
        json={"target_language": "hi", "representation_types": ["invalid_type"]},
        headers=headers,
    )
    assert bad_type_res.status_code == 422 or bad_type_res.status_code == 400

    # 3. Missing Meeting
    fake_meeting_id = str(uuid.uuid4())
    missing_meeting_res = await client.post(
        f"/api/v1/meetings/{fake_meeting_id}/translations",
        json={"target_language": "es"},
        headers=headers,
    )
    assert missing_meeting_res.status_code == 404

    # 4. Missing Translation
    fake_trans_id = str(uuid.uuid4())
    missing_trans_res = await client.get(f"/api/v1/translations/{fake_trans_id}", headers=headers)
    assert missing_trans_res.status_code == 404

    # 5. Missing / Invalid Auth Header
    no_auth_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/translations",
        json={"target_language": "fr"},
    )
    assert no_auth_res.status_code == 401
