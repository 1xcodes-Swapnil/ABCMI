"""
Phase 4.12B AI Processing Layer Tests
Validates Transcript Intelligence and Context Intelligence services, provenance preservation,
confidence propagation, low-confidence threshold flagging, SKW Knowledge Object conversion,
and idempotency.
"""

import uuid
import pytest

from app.ai.multilingual_asr import ASRResult, ASRSegment, ASRWordTimestamp
from app.ai.code_switch_intelligence import CodeSwitchBoundary, NormalizedRepresentation
from app.ai.transcript_intelligence import (
    TranscriptIntelligenceEngine,
    TranscriptIntelligenceResult,
    CleanedTranscriptSegment,
    ConversationalTurn,
    TranscriptUnit,
)
from app.ai.context_intelligence import (
    ContextIntelligenceEngine,
    ContextIntelligenceResult,
    SpeakerRelationship,
    ContextualDependency,
)
from app.schemas.knowledge_object import KnowledgeObjectCreate
from app.models.knowledge_object import KnowledgeObjectStatus


@pytest.fixture
def sample_asr_result():
    meeting_id = uuid.uuid4()
    words = [
        ASRWordTimestamp(word="Namaste", start_time=0.0, end_time=0.5, confidence=0.96, language_code="hi"),
        ASRWordTimestamp(word="team", start_time=0.6, end_time=0.9, confidence=0.98, language_code="en"),
        ASRWordTimestamp(word="today", start_time=1.0, end_time=1.4, confidence=0.95, language_code="en"),
        ASRWordTimestamp(word="um", start_time=1.45, end_time=1.55, confidence=0.80, language_code="en"),
        ASRWordTimestamp(word="hum", start_time=1.6, end_time=1.8, confidence=0.92, language_code="hi"),
        ASRWordTimestamp(word="architecture", start_time=1.9, end_time=2.5, confidence=0.97, language_code="en"),
        ASRWordTimestamp(word="discuss", start_time=2.6, end_time=3.0, confidence=0.94, language_code="en"),
        ASRWordTimestamp(word="karenge", start_time=3.1, end_time=3.6, confidence=0.95, language_code="hi"),
    ]

    seg1 = ASRSegment(
        speaker_id="speaker_0",
        start_time=0.0,
        end_time=3.6,
        transcript="Namaste team today um hum architecture discuss karenge",
        detected_language="hinglish",
        words=words,
        confidence=0.94,
    )

    seg2 = ASRSegment(
        speaker_id="speaker_1",
        start_time=4.0,
        end_time=6.5,
        transcript="Yes we we should finalize the action items today.",
        detected_language="en",
        words=[],
        confidence=0.92,
    )

    return ASRResult(
        meeting_id=meeting_id,
        full_transcript="Namaste team today um hum architecture discuss karenge Yes we we should finalize the action items today.",
        detected_languages=["hinglish", "en"],
        language_distribution={"hinglish": 0.6, "en": 0.4},
        segments=[seg1, seg2],
        overall_confidence=0.93,
        metadata={
            "model_name": "openai/whisper-large-v3",
            "model_version": "v3-turbo",
            "provenance": "ASR:openai/whisper-large-v3:v3-turbo",
        },
    )


@pytest.mark.asyncio
async def test_transcript_intelligence_cleaning_and_turn_segmentation(sample_asr_result):
    """Validates transcript artifact cleaning (fillers/stutters), turn building, and speaker preservation."""
    engine = TranscriptIntelligenceEngine()

    norm_cs = NormalizedRepresentation(
        original_text=sample_asr_result.full_transcript,
        normalized_text=sample_asr_result.full_transcript,
        canonical_text=sample_asr_result.full_transcript,
        source_languages=["hi", "en"],
        code_switch_boundaries=[
            CodeSwitchBoundary(token_index=0, source_language="en", target_language="hi", confidence=0.95)
        ],
        confidence=0.95,
    )

    res = await engine.process_transcript(
        asr_result=sample_asr_result,
        code_switch_norm=norm_cs,
        correlation_id="corr-ti-1",
    )

    assert isinstance(res, TranscriptIntelligenceResult)
    assert res.meeting_id == sample_asr_result.meeting_id
    assert len(res.cleaned_segments) == 2

    # Check filler word "um" removed from segment 1
    assert "um" not in res.cleaned_segments[0].cleaned_transcript.lower().split()
    assert len(res.cleaned_segments[0].removed_artifacts) > 0

    # Check stutter repetition "we we" cleaned in segment 2
    assert "we we" not in res.cleaned_segments[1].cleaned_transcript.lower()

    # Check turns and speaker preservation
    assert len(res.conversational_turns) == 2
    assert res.conversational_turns[0].speaker_id == "speaker_0"
    assert res.conversational_turns[1].speaker_id == "speaker_1"

    # Check timestamps and confidence preservation
    assert res.cleaned_segments[0].start_time == 0.0
    assert res.cleaned_segments[0].end_time == 3.6
    assert res.overall_confidence > 0.90


@pytest.mark.asyncio
async def test_transcript_intelligence_empty_input():
    """Validates resilience when transcript input is empty or None."""
    engine = TranscriptIntelligenceEngine()

    res = await engine.process_transcript(asr_result=None, correlation_id="empty-test")
    assert isinstance(res, TranscriptIntelligenceResult)
    assert res.cleaned_full_transcript == ""
    assert len(res.cleaned_segments) == 0
    assert res.metadata["empty_input"] is True


@pytest.mark.asyncio
async def test_context_intelligence_extraction_and_relationships(sample_asr_result):
    """Validates context intelligence extraction, topic summary, speaker dynamics, and dependencies."""
    ti_engine = TranscriptIntelligenceEngine()
    ci_engine = ContextIntelligenceEngine()

    ti_res = await ti_engine.process_transcript(sample_asr_result)
    ci_res = await ci_engine.extract_context(
        transcript_result=ti_res,
        meeting_id=sample_asr_result.meeting_id,
        correlation_id="corr-ci-1",
    )

    assert isinstance(ci_res, ContextIntelligenceResult)
    assert ci_res.meeting_id == sample_asr_result.meeting_id
    assert "Architecture" in ci_res.topic_context
    assert len(ci_res.speaker_relationships) > 0
    assert ci_res.overall_confidence >= 0.70
    assert ci_res.is_low_confidence is False
    assert ci_res.requires_verification is False


@pytest.mark.asyncio
async def test_context_intelligence_low_confidence_flagging(sample_asr_result):
    """Validates that low-confidence (<0.70) context triggers verification flag and PROVISIONAL status."""
    ti_engine = TranscriptIntelligenceEngine()
    ci_engine = ContextIntelligenceEngine()

    ti_res = await ti_engine.process_transcript(sample_asr_result)
    ci_res = await ci_engine.extract_context(
        transcript_result=ti_res,
        meeting_id=sample_asr_result.meeting_id,
        force_low_confidence=True,
    )

    assert ci_res.overall_confidence < 0.70
    assert ci_res.is_low_confidence is True
    assert ci_res.requires_verification is True

    # Test conversion to SKW Knowledge Objects
    kos = ci_engine.to_knowledge_objects(ci_res)
    assert len(kos) > 0
    for ko in kos:
        assert isinstance(ko, KnowledgeObjectCreate)
        assert ko.status == KnowledgeObjectStatus.DRAFT
        if "requires_verification" in ko.payload:
            assert ko.payload["requires_verification"] is True


@pytest.mark.asyncio
async def test_context_intelligence_to_knowledge_objects_schema_conformance(sample_asr_result):
    """Validates that extracted context converts into fully compliant SKW Knowledge Object schemas."""
    ti_engine = TranscriptIntelligenceEngine()
    ci_engine = ContextIntelligenceEngine()

    ti_res = await ti_engine.process_transcript(sample_asr_result)
    ci_res = await ci_engine.extract_context(
        transcript_result=ti_res,
        meeting_id=sample_asr_result.meeting_id,
    )

    kos = ci_engine.to_knowledge_objects(ci_res)
    assert len(kos) >= 2

    # Check object types present
    object_types = [ko.object_type for ko in kos]
    assert "topic" in object_types
    assert "summary" in object_types

    for ko in kos:
        assert ko.meeting_id == sample_asr_result.meeting_id
        assert ko.confidence > 0.70
        assert ko.provenance.producing_module == "context_intelligence"
        assert ko.provenance.model_name == "gemini-1.5-pro"


@pytest.mark.asyncio
async def test_context_intelligence_idempotency(sample_asr_result):
    """Validates that repeated runs on the same input produce identical deterministic outputs."""
    ti_engine = TranscriptIntelligenceEngine()
    ci_engine = ContextIntelligenceEngine()

    ti_res = await ti_engine.process_transcript(sample_asr_result)

    run1 = await ci_engine.extract_context(ti_res, sample_asr_result.meeting_id, "idemp-1")
    run2 = await ci_engine.extract_context(ti_res, sample_asr_result.meeting_id, "idemp-1")

    assert run1.topic_context == run2.topic_context
    assert run1.conversation_summary == run2.conversation_summary
    assert run1.overall_confidence == run2.overall_confidence
