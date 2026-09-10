"""
Phase 4.26 — Open-MOSS and pyannote Integration & Research Evaluation Test Suite
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.core.config import get_settings
from app.ai.multilingual_asr import MultilingualASREngine, ASRSegment, ASRWordTimestamp
from app.ai.speaker_diarization import SpeakerDiarizationEngine, SpeakerTurn
from app.ai.model_verification import ModelVerificationService


@pytest.mark.asyncio
async def test_moss_no_fallback_in_real_mode():
    """Verifies that in REAL mode, MultilingualASREngine raises error if dependencies are missing instead of falling back."""
    settings = get_settings()
    
    with patch.object(settings, "EXECUTION_MODE", "REAL"):
        asr_engine = MultilingualASREngine()
        # Mock OpenMOSSProvider's transcribe to raise RuntimeError (simulating missing weights/GPU)
        with patch("app.ai.multilingual_asr.OpenMOSSProvider.transcribe", side_effect=RuntimeError("CUDA memory error")):
            with pytest.raises(RuntimeError) as exc_info:
                await asr_engine.transcribe_audio(
                    audio_payload=b"fake_riff_wave_bytes",
                    meeting_id=uuid.uuid4(),
                    use_fixture=False
                )
            assert "CUDA memory error" in str(exc_info.value)


def test_verify_moss_with_pyannote_matching():
    """Verifies successful speaker comparison mapping and accuracy calculation."""
    sd_engine = SpeakerDiarizationEngine()

    moss_segments = [
        ASRSegment(
            speaker_id="S01",
            start_time=0.0,
            end_time=5.0,
            transcript="Hello from speaker one.",
            confidence=0.95
        ),
        ASRSegment(
            speaker_id="S02",
            start_time=5.0,
            end_time=10.0,
            transcript="Hello from speaker two.",
            confidence=0.95
        ),
    ]

    pyannote_turns = [
        SpeakerTurn(speaker_id="SPEAKER_00", start_time=0.0, end_time=4.8, confidence=0.95),
        SpeakerTurn(speaker_id="SPEAKER_01", start_time=5.1, end_time=10.0, confidence=0.95),
    ]

    report = sd_engine.verify_moss_with_pyannote(moss_segments, pyannote_turns)

    assert report["accuracy"] == 1.0
    assert report["matches"] == 2
    assert report["total_checks"] == 2
    assert report["speaker_mapping"] == {"S01": "SPEAKER_00", "S02": "SPEAKER_01"}
    assert len(report["disagreements"]) == 0


def test_verify_moss_with_pyannote_disagreement():
    """Verifies SPEAKER_MISMATCH detection when MOSS speaker previously mapped to a different pyannote speaker overlaps."""
    sd_engine = SpeakerDiarizationEngine()

    moss_segments = [
        ASRSegment(
            speaker_id="S01",
            start_time=0.0,
            end_time=5.0,
            transcript="S01 speaking first.",
            confidence=0.95
        ),
        ASRSegment(
            speaker_id="S01",
            start_time=10.0,
            end_time=15.0,
            transcript="S01 speaking again.",
            confidence=0.95
        ),
    ]

    pyannote_turns = [
        # First turn: S01 mapped to SPEAKER_00
        SpeakerTurn(speaker_id="SPEAKER_00", start_time=0.0, end_time=5.0, confidence=0.95),
        # Second turn: S01 suddenly overlaps with SPEAKER_01 instead of SPEAKER_00 (disagreement)
        SpeakerTurn(speaker_id="SPEAKER_01", start_time=10.0, end_time=15.0, confidence=0.95),
    ]

    report = sd_engine.verify_moss_with_pyannote(moss_segments, pyannote_turns)

    assert report["accuracy"] == 0.5
    assert report["matches"] == 1
    assert report["total_checks"] == 2
    assert len(report["disagreements"]) == 1
    assert report["disagreements"][0]["type"] == "SPEAKER_MISMATCH"
    assert "SPEAKER_MISMATCH" in report["disagreements"][0]["message"]


def test_verify_moss_with_pyannote_conflict():
    """Verifies SPEAKER_CONFLICT detection when different MOSS speakers map to the same pyannote speaker."""
    sd_engine = SpeakerDiarizationEngine()

    moss_segments = [
        ASRSegment(
            speaker_id="S01",
            start_time=0.0,
            end_time=5.0,
            transcript="S01 speaking.",
            confidence=0.95
        ),
        ASRSegment(
            speaker_id="S02",
            start_time=5.0,
            end_time=10.0,
            transcript="S02 speaking.",
            confidence=0.95
        ),
    ]

    pyannote_turns = [
        # Both overlap with SPEAKER_00
        SpeakerTurn(speaker_id="SPEAKER_00", start_time=0.0, end_time=5.0, confidence=0.95),
        SpeakerTurn(speaker_id="SPEAKER_00", start_time=5.0, end_time=10.0, confidence=0.95),
    ]

    report = sd_engine.verify_moss_with_pyannote(moss_segments, pyannote_turns)

    assert report["accuracy"] == 0.5
    assert report["matches"] == 1
    assert len(report["disagreements"]) == 1
    assert report["disagreements"][0]["type"] == "SPEAKER_CONFLICT"


def test_model_verification_moss_service():
    """Verifies MOSS config checks and hardware requirements on ModelVerificationService."""
    config_info = ModelVerificationService.verify_moss_config()
    assert "configured_model_name" in config_info
    assert config_info["expected_model_name"] == "fnlp/moss-transcribe-diarize-0.9b"
    
    hw_info = ModelVerificationService.verify_moss_hardware_requirements()
    assert "blocked" in hw_info
    assert "status_code" in hw_info
    assert "message" in hw_info
