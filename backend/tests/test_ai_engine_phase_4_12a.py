"""
Phase 4.12A AI Processing Layer Tests
Validates Multilingual ASR (17 languages), Code-Switch Intelligence, Speaker Diarization, and Overlap Resolution.
"""

import pytest
import uuid

from app.ai.multilingual_asr import MultilingualASREngine, ASRResult, ASRSegment
from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine, NormalizedRepresentation
from app.ai.speaker_diarization import SpeakerDiarizationEngine, DiarizationResult
from app.ai.overlap_resolution import OverlapResolutionEngine, OverlapResolutionResult


@pytest.mark.asyncio
async def test_multilingual_asr_all_17_supported_languages():
    """Validates that MultilingualASREngine supports all 17 target languages and dialects."""
    engine = MultilingualASREngine()

    all_17_languages = [
        "en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa",
        "zh", "ja", "fr", "es", "de", "ru", "ar",
    ]

    for lang in all_17_languages:
        assert lang in engine.SUPPORTED_LANGUAGES, f"Language '{lang}' missing from SUPPORTED_LANGUAGES"
        assert lang in engine.LANGUAGE_NAMES, f"Language name for '{lang}' missing"

    meeting_id = uuid.uuid4()
    dummy_audio = b"\x00" * 1024

    # Test transcribing each of the 7 new languages
    for lang in ["zh", "ja", "fr", "es", "de", "ru", "ar"]:
        res = await engine.transcribe_audio(
            audio_payload=dummy_audio,
            meeting_id=meeting_id,
            target_languages=[lang],
            correlation_id=f"corr-{lang}",
        )
        assert isinstance(res, ASRResult)
        assert res.meeting_id == meeting_id
        assert lang in res.detected_languages
        assert len(res.segments) > 0
        assert res.segments[0].confidence > 0.8
        assert res.metadata["model_name"] == "openai/whisper-large-v3"
        assert res.metadata["model_version"] == "v3-turbo"


@pytest.mark.asyncio
async def test_multilingual_asr_invalid_language_rejection():
    """Validates that requests with unsupported language codes raise ValueError."""
    engine = MultilingualASREngine()
    meeting_id = uuid.uuid4()
    dummy_audio = b"\x00" * 512

    with pytest.raises(ValueError) as exc_info:
        await engine.transcribe_audio(
            audio_payload=dummy_audio,
            meeting_id=meeting_id,
            target_languages=["invalid_lang_code_xyz"],
        )
    assert "Unsupported language code" in str(exc_info.value)


@pytest.mark.asyncio
async def test_multilingual_asr_model_metadata_and_provenance():
    """Validates pretrained model identification and distinction between fixture mode vs real model execution."""
    engine = MultilingualASREngine()
    meeting_id = uuid.uuid4()
    dummy_audio = b"\x00" * 1024

    result = await engine.transcribe_audio(
        audio_payload=dummy_audio,
        meeting_id=meeting_id,
        target_languages=["es", "en"],
        correlation_id="trace-metadata-123",
        use_fixture=True,
    )

    assert result.metadata["model_name"] == "openai/whisper-large-v3"
    assert result.metadata["model_version"] == "v3-turbo"
    assert result.metadata["provenance"] == "ASR:openai/whisper-large-v3:v3-turbo"
    assert result.metadata["is_fixture"] is True
    assert result.metadata["correlation_id"] == "trace-metadata-123"
    assert result.metadata["audio_bytes_length"] == 1024


@pytest.mark.asyncio
async def test_multilingual_asr_regression_original_10_languages():
    """Validates regression support for original 10 languages (en, hi, ta, te, kn, ml, bn, mr, gu, pa)."""
    engine = MultilingualASREngine()
    meeting_id = uuid.uuid4()
    dummy_audio = b"\x00" * 1024

    original_10 = ["en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa"]
    for lang in original_10:
        res = await engine.transcribe_audio(
            audio_payload=dummy_audio,
            meeting_id=meeting_id,
            target_languages=[lang],
        )
        assert isinstance(res, ASRResult)
        assert res.overall_confidence >= 0.90


@pytest.mark.asyncio
async def test_multilingual_asr_engine_process_segment():
    engine = MultilingualASREngine()
    dummy_chunk = b"\x01" * 512

    segment = await engine.process_segment(audio_chunk=dummy_chunk, speaker_id="speaker_test")
    assert isinstance(segment, ASRSegment)
    assert segment.speaker_id == "speaker_test"
    assert segment.confidence > 0.8


@pytest.mark.asyncio
async def test_code_switch_intelligence_expanded_languages():
    """Validates code-switch boundary detection and normalization across multiple languages (Spanish, French, Chinese, Hindi)."""
    engine = CodeSwitchIntelligenceEngine()

    mixed_texts = [
        ("Bonjour l'équipe welcome", "fr", "en"),
        ("Hola equipo meeting", "es", "en"),
        ("Namaste team today hum architecture discuss karenge", "hi", "en"),
    ]

    for text, lang1, lang2 in mixed_texts:
        boundaries = await engine.detect_boundaries(text)
        assert len(boundaries) > 0

        norm = await engine.normalize_text(text)
        assert isinstance(norm, NormalizedRepresentation)
        assert norm.original_text == text
        assert len(norm.canonical_text) > 0
        assert norm.confidence >= 0.90


@pytest.mark.asyncio
async def test_speaker_diarization_engine():
    engine = SpeakerDiarizationEngine()
    meeting_id = uuid.uuid4()
    dummy_audio = b"\x02" * 2048

    result = await engine.diarize_audio(audio_payload=dummy_audio, meeting_id=meeting_id, expected_speakers=2)
    assert isinstance(result, DiarizationResult)
    assert result.meeting_id == meeting_id
    assert result.num_speakers == 2
    assert len(result.speaker_turns) == 2
    assert len(result.voiceprints) == 2

    voiceprint = await engine.extract_voiceprint(audio_chunk=dummy_audio[:100], speaker_id="spk_1")
    assert voiceprint.speaker_id == "spk_1"
    assert len(voiceprint.embedding_vector) == 128


@pytest.mark.asyncio
async def test_overlap_resolution_engine():
    engine = OverlapResolutionEngine()
    meeting_id = uuid.uuid4()
    dummy_audio = b"\x03" * 2048

    result = await engine.resolve_overlaps(audio_payload=dummy_audio, meeting_id=meeting_id)
    assert isinstance(result, OverlapResolutionResult)
    assert result.meeting_id == meeting_id
    assert len(result.overlapping_segments) > 0
    assert len(result.resolved_candidates) > 0
    assert result.adjusted_confidence > 0.80

