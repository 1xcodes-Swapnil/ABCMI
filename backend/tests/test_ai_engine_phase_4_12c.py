"""
Phase 4.12C Comprehensive AI Intelligence Tests
Validates Confidence Fusion, Verification Engine, Meeting Understanding, Meeting Analytics,
Knowledge Memory, Hardware/Model Verification, End-to-End Pipeline Execution, and Failure Isolation.
"""

from datetime import datetime
import uuid
import pytest

from app.ai.confidence_fusion import ConfidenceFusionEngine, ConfidenceFusionResult
from app.ai.verification_engine import VerificationEngine, VerificationResult
from app.ai.meeting_understanding import MeetingUnderstandingEngine, MeetingUnderstandingResult
from app.ai.meeting_analytics import MeetingAnalyticsEngine, MeetingAnalyticsResult
from app.ai.knowledge_memory import KnowledgeMemoryEngine, KnowledgeMemoryQueryRequest
from app.ai.model_verification import ModelVerificationService
from app.ai.multilingual_asr import MultilingualASREngine
from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
from app.ai.speaker_diarization import SpeakerDiarizationEngine
from app.ai.overlap_resolution import OverlapResolutionEngine
from app.ai.transcript_intelligence import TranscriptIntelligenceEngine
from app.ai.context_intelligence import ContextIntelligenceEngine
from app.models.knowledge_object import KnowledgeObjectStatus
from app.schemas.knowledge_object import KnowledgeObjectCreate, ProvenanceMetadataSchema
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.orchestration.skw_client import BlackboardSKWClient
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine


# ============================================================================
# 1. CONFIDENCE FUSION TESTS
# ============================================================================

def test_confidence_fusion_normalized_output():
    engine = ConfidenceFusionEngine(confidence_threshold=0.70)
    meeting_id = uuid.uuid4()
    correlation_id = "corr_fusion_001"

    signals = {
        "asr_confidence": 0.95,
        "language_confidence": 0.90,
        "diarization_confidence": 0.92,
        "timestamp_confidence": 0.88,
        "code_switch_confidence": 0.85,
        "context_confidence": 0.89,
        "extraction_confidence": 0.91,
    }

    result = engine.fuse_signals(
        meeting_id=meeting_id,
        signals=signals,
        correlation_id=correlation_id,
    )

    assert isinstance(result, ConfidenceFusionResult)
    assert result.meeting_id == meeting_id
    assert 0.0 <= result.fused_confidence <= 1.0
    assert result.is_low_confidence is False
    assert result.correlation_id == correlation_id
    assert result.provenance.producing_module == "confidence_fusion"
    assert "asr_confidence" in result.signal_breakdown


def test_confidence_fusion_low_confidence_flagging():
    engine = ConfidenceFusionEngine(confidence_threshold=0.70)
    meeting_id = uuid.uuid4()

    low_signals = {
        "asr_confidence": 0.40,
        "diarization_confidence": 0.45,
        "timestamp_confidence": 0.50,
    }

    result = engine.fuse_signals(
        meeting_id=meeting_id,
        signals=low_signals,
        correlation_id="corr_low_001",
    )

    assert result.fused_confidence < 0.70
    assert result.is_low_confidence is True
    assert "low_asr_penalty" in result.penalties_applied


# ============================================================================
# 2. VERIFICATION ENGINE TESTS
# ============================================================================

def test_verification_engine_high_confidence_flow():
    engine = VerificationEngine(confidence_threshold=0.70)
    meeting_id = uuid.uuid4()

    ko, verif = engine.evaluate_output(
        meeting_id=meeting_id,
        object_type="decision",
        content="High confidence architectural decision",
        confidence_score=0.92,
        correlation_id="corr_verif_001",
    )

    assert isinstance(ko, KnowledgeObjectCreate)
    assert ko.status == KnowledgeObjectStatus.ACTIVE
    assert verif.verification_passed is True
    assert verif.requires_verification is False


def test_verification_engine_low_confidence_flow():
    engine = VerificationEngine(confidence_threshold=0.70)
    meeting_id = uuid.uuid4()

    ko, verif = engine.evaluate_output(
        meeting_id=meeting_id,
        object_type="action_item",
        content="Uncertain action item extraction",
        confidence_score=0.55,
        correlation_id="corr_verif_002",
    )

    assert ko.status == KnowledgeObjectStatus.DRAFT
    assert ko.payload["requires_verification"] is True
    assert verif.verification_passed is False
    assert verif.requires_verification is True


def test_verification_engine_promote_and_reject():
    engine = VerificationEngine(confidence_threshold=0.70)
    meeting_id = uuid.uuid4()

    ko_draft, _ = engine.evaluate_output(
        meeting_id=meeting_id,
        object_type="fact",
        content="Draft technical specification fact",
        confidence_score=0.60,
    )

    # Promote
    ko_promoted, verif_promo = engine.verify_and_promote(
        ko_create=ko_draft,
        verifier_id="human_expert_1",
        notes="Approved by expert reviewer",
    )
    assert ko_promoted.status == KnowledgeObjectStatus.VALIDATED
    assert verif_promo.verification_passed is True

    # Reject
    ko_rejected, verif_rej = engine.reject_object(
        ko_create=ko_draft,
        rejection_reason="Factually inaccurate statement",
        reviewer_id="human_expert_2",
    )
    assert ko_rejected.status == KnowledgeObjectStatus.REJECTED
    assert verif_rej.verification_passed is False
    assert verif_rej.rejection_reason == "Factually inaccurate statement"


# ============================================================================
# 3. MEETING UNDERSTANDING TESTS (ALL 7 KNOWLEDGE OBJECT TYPES)
# ============================================================================

@pytest.mark.asyncio
async def test_meeting_understanding_all_seven_types():
    engine = MeetingUnderstandingEngine()
    meeting_id = uuid.uuid4()
    transcript = "Namaste team today we discuss architecture decisions action items facts hypotheses insights."

    result = await engine.analyze_meeting(
        meeting_id=meeting_id,
        transcript_text=transcript,
        correlation_id="corr_mu_001",
    )

    assert isinstance(result, MeetingUnderstandingResult)
    assert len(result.knowledge_objects) >= 7

    extracted_types = {ko.object_type for ko in result.knowledge_objects}
    required_types = {
        "decision",
        "action_item",
        "topic",
        "summary",
        "fact",
        "hypothesis",
        "transcript_insight",
    }
    assert required_types.issubset(extracted_types)

    for ko in result.knowledge_objects:
        assert isinstance(ko.meeting_id, uuid.UUID)
        assert ko.confidence is not None
        assert ko.version >= 1
        assert ko.status in (KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.DRAFT)


# ============================================================================
# 4. MEETING ANALYTICS TESTS
# ============================================================================

def test_meeting_analytics_computation():
    engine = MeetingAnalyticsEngine()
    meeting_id = uuid.uuid4()

    turns = [
        {"speaker_id": "spk_1", "start_time": 0.0, "end_time": 10.0},
        {"speaker_id": "spk_2", "start_time": 10.0, "end_time": 30.0},
    ]
    langs = {"en": 70, "hi": 30}
    boundaries = [
        {"source_language": "en", "target_language": "hi"},
        {"source_language": "hi", "target_language": "en"},
    ]

    result = engine.compute_analytics(
        meeting_id=meeting_id,
        speaker_turns=turns,
        language_tokens=langs,
        code_switch_boundaries=boundaries,
        meeting_duration_seconds=30.0,
        correlation_id="corr_analytics_001",
    )

    assert isinstance(result, MeetingAnalyticsResult)
    assert len(result.speaker_participation) == 2
    assert result.code_switch_statistics.total_switch_points == 2
    assert result.language_distribution["en"] == 70.0
    assert result.confidence_statistics.mean_confidence > 0.0


# ============================================================================
# 5. KNOWLEDGE MEMORY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_knowledge_memory_isolation_and_auth(db_session):
    query_engine = KnowledgeQueryEngine(db_session)
    skw_client = BlackboardSKWClient(query_engine=query_engine)
    memory_engine = KnowledgeMemoryEngine(skw_client=skw_client)

    meeting_id = uuid.uuid4()
    valid_auth = {"authenticated": True, "auth_token": "valid-jwt-token"}

    # Query without auth context should raise UnauthorizedException
    req_unauth = KnowledgeMemoryQueryRequest(
        meeting_id=meeting_id,
        query="architecture",
        search_mode="hybrid",
        auth_context=None,
    )
    with pytest.raises(UnauthorizedException):
        await memory_engine.query_memory(req_unauth)

    # Query with valid auth context
    req_valid = KnowledgeMemoryQueryRequest(
        meeting_id=meeting_id,
        query="architecture",
        search_mode="hybrid",
        auth_context=valid_auth,
        correlation_id="corr_mem_001",
    )
    res = await memory_engine.query_memory(req_valid)
    assert res.query_mode == "hybrid"
    assert res.correlation_id == "corr_mem_001"


# ============================================================================
# 6. REAL MODEL & HARDWARE CAVEAT VERIFICATION TESTS
# ============================================================================

def test_model_verification_service():
    whisper_info = ModelVerificationService.verify_whisper_config()
    assert whisper_info["configured_model_name"] == "openai/whisper-large-v3"
    assert whisper_info["configured_model_version"] == "v3-turbo"
    assert whisper_info["supported_languages_count"] == 22

    hw_info = ModelVerificationService.check_cuda_hardware()
    assert "cuda_available" in hw_info

    tag = ModelVerificationService.get_execution_provenance_tag(use_fixture=True)
    assert tag == "FIXTURE"

    smoke = ModelVerificationService.run_cuda_smoke_test()
    assert "smoke_test_executed" in smoke


# ============================================================================
# 7. END-TO-END PIPELINE INTEGRATION TEST
# ============================================================================

@pytest.mark.asyncio
async def test_end_to_end_ai_intelligence_pipeline():
    meeting_id = uuid.uuid4()
    correlation_id = "corr_e2e_phase412c"
    sample_audio = b"RIFF....WAVEfmt ....data...."

    # Step 1: Multilingual ASR
    asr_engine = MultilingualASREngine()
    asr_res = await asr_engine.transcribe_audio(
        audio_payload=sample_audio,
        meeting_id=meeting_id,
        target_languages=["hi", "en", "hinglish"],
        correlation_id=correlation_id,
    )
    assert asr_res.full_transcript is not None

    # Step 2: Code-Switch Intelligence
    cs_engine = CodeSwitchIntelligenceEngine()
    cs_res = cs_engine.process_transcript(
        asr_result=asr_res,
        correlation_id=correlation_id,
    )
    assert cs_res.canonical_text is not None

    # Step 3: Speaker Diarization
    sd_engine = SpeakerDiarizationEngine()
    sd_res = sd_engine.process_audio(
        audio_payload=sample_audio,
        meeting_id=meeting_id,
        correlation_id=correlation_id,
    )
    assert len(sd_res.speaker_turns) > 0

    # Step 4: Overlap Resolution
    ol_engine = OverlapResolutionEngine()
    ol_res = await ol_engine.resolve_overlaps(
        diarization_result=sd_res,
        asr_result=asr_res,
        correlation_id=correlation_id,
    )
    assert ol_res.meeting_id == meeting_id

    # Step 5: Transcript Intelligence
    ti_engine = TranscriptIntelligenceEngine()
    ti_res = await ti_engine.process_transcript(
        asr_result=asr_res,
        diarization_result=sd_res,
        overlap_result=ol_res,
        correlation_id=correlation_id,
    )
    assert len(ti_res.conversational_turns) > 0

    # Step 6: Context Intelligence
    ctx_engine = ContextIntelligenceEngine()
    ctx_res = await ctx_engine.extract_context(
        transcript_result=ti_res,
        meeting_id=meeting_id,
        correlation_id=correlation_id,
    )
    assert ctx_res.meeting_id == meeting_id

    # Step 7: Confidence Fusion
    cf_engine = ConfidenceFusionEngine()
    cf_res = cf_engine.fuse_signals(
        meeting_id=meeting_id,
        signals={
            "asr_confidence": asr_res.overall_confidence,
            "diarization_confidence": sd_res.overall_confidence,
            "context_confidence": ctx_res.overall_confidence,
        },
        correlation_id=correlation_id,
    )
    assert 0.0 <= cf_res.fused_confidence <= 1.0

    # Step 8: Meeting Understanding & Verification
    mu_engine = MeetingUnderstandingEngine()
    mu_res = await mu_engine.analyze_meeting(
        meeting_id=meeting_id,
        transcript_text=asr_res.full_transcript,
        correlation_id=correlation_id,
    )
    assert len(mu_res.knowledge_objects) >= 7

    # Step 9: Analytics
    ma_engine = MeetingAnalyticsEngine()
    ma_res = ma_engine.compute_analytics(
        meeting_id=meeting_id,
        speaker_turns=[{"speaker_id": t.speaker_id, "start_time": t.start_time, "end_time": t.end_time} for t in sd_res.speaker_turns],
        correlation_id=correlation_id,
    )
    assert ma_res.meeting_id == meeting_id


# ============================================================================
# 8. FAILURE & RECOVERY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_failure_handling_malformed_input():
    asr_engine = MultilingualASREngine()
    meeting_id = uuid.uuid4()

    # Empty audio payload should raise ValueError
    with pytest.raises(ValueError):
        await asr_engine.transcribe_audio(
            audio_payload=b"",
            meeting_id=meeting_id,
        )


@pytest.mark.asyncio
async def test_failure_handling_unsupported_language():
    asr_engine = MultilingualASREngine()
    meeting_id = uuid.uuid4()

    # Unsupported language should raise ValueError
    with pytest.raises(ValueError):
        await asr_engine.transcribe_audio(
            audio_payload=b"RIFF....WAVE",
            meeting_id=meeting_id,
            target_languages=["invalid_lang_code"],
        )


def test_failure_handling_verification_rejection():
    v_engine = VerificationEngine()
    meeting_id = uuid.uuid4()

    ko_draft, _ = v_engine.evaluate_output(
        meeting_id=meeting_id,
        object_type="decision",
        content="Controversial decision",
        confidence_score=0.40,
    )

    ko_rejected, verif_res = v_engine.reject_object(
        ko_create=ko_draft,
        rejection_reason="Safety guidelines violation",
    )

    assert ko_rejected.status == KnowledgeObjectStatus.REJECTED
    assert verif_res.verification_passed is False
    assert verif_res.rejection_reason == "Safety guidelines violation"
