"""
Speaker Diarization Engine
Provides speaker diarization, voiceprint embedding clustering, speaker turn segmentation,
overlap resolution, and speaker assignment confidence scoring.
"""

import os
import tempfile
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ai.speaker_diarization")


class SpeakerVoiceprint(CoreBaseModel):
    """Voiceprint embedding vector representation for a speaker."""
    speaker_id: str = Field(..., description="Unique speaker identifier")
    embedding_vector: List[float] = Field(default_factory=list, description="Dimensional voiceprint vector")
    confidence: Optional[float] = Field(default=0.95, ge=0.0, le=1.0)


class SpeakerTurn(CoreBaseModel):
    """Contiguous speaker turn interval with assigned speaker ID."""
    turn_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: str = Field(..., description="Assigned speaker ID")
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    confidence: Optional[float] = Field(default=0.92, ge=0.0, le=1.0)


class DiarizationResult(CoreBaseModel):
    """Output model for speaker diarization processing."""
    meeting_id: uuid.UUID
    num_speakers: int = Field(default=1, ge=1)
    speaker_turns: List[SpeakerTurn] = Field(default_factory=list)
    voiceprints: List[SpeakerVoiceprint] = Field(default_factory=list)
    overall_confidence: Optional[float] = Field(default=0.91, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SpeakerDiarizationEngine:
    """
    Speaker Diarization Engine utilizing voiceprint embeddings and spectral clustering/PyAnnote (REAL mode).
    """

    _cached_pipeline = None
    _cached_pipeline_key = None

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {
            "embedding_dim": 128,
            "min_cluster_size": 2,
            "max_speakers": 10,
        }

    async def diarize_audio(
        self,
        audio_payload: bytes,
        meeting_id: uuid.UUID,
        expected_speakers: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> DiarizationResult:
        """
        Segments audio into speaker turns and extracts speaker voiceprints.
        Supports REAL mode with PyAnnote and FIXTURE/MOCK modes.
        """
        if not audio_payload:
            raise ValueError("Audio payload cannot be empty.")

        settings = get_settings()
        exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()

        if exec_mode == "REAL":
            # 1. Run real PyAnnote diarization
            # Save audio payload to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_payload)
                tmp_path = tmp.name

            try:
                # 2. Local audio validation on the temp file
                from app.ai.multilingual_asr import validate_audio
                validate_audio(tmp_path)

                # 3. Load pyannote pipeline
                try:
                    from pyannote.audio import Pipeline
                    import torch
                except ImportError as ex:
                    raise RuntimeError(
                        f"Missing PyAnnote or Torch dependencies for REAL mode Diarization: {ex}"
                    ) from ex

                if not settings.HF_TOKEN:
                    logger.warning("PYANNOTE BLOCKED: Hugging Face Auth Token (HF_TOKEN) is required in the environment for REAL PyAnnote diarization.")
                    raise RuntimeError(
                        "PYANNOTE BLOCKED: Hugging Face Auth Token (HF_TOKEN) is required in the environment for REAL PyAnnote diarization."
                    )

                try:
                    from app.ai.model_inventory import configure_cache
                    cache = configure_cache()
                    device = torch.device(settings.OPENMOSS_DEVICE if settings.OPENMOSS_DEVICE != "auto" else "cuda:0")
                    if device.type == "cuda" and not torch.cuda.is_available():
                        raise RuntimeError("Configured CUDA device unavailable for REAL PyAnnote")
                    key = (str(cache), str(device))
                    pipeline = self._cached_pipeline if key == self._cached_pipeline_key else None
                    if pipeline is None:
                        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                            token=settings.HF_TOKEN, cache_dir=cache)
                    if pipeline is None:
                        logger.warning("PYANNOTE BLOCKED: PyAnnote pipeline returned None from Hugging Face.")
                        raise ValueError("PYANNOTE BLOCKED: Pipeline returned None from Hugging Face.")
                    pipeline.to(device)
                    SpeakerDiarizationEngine._cached_pipeline = pipeline
                    SpeakerDiarizationEngine._cached_pipeline_key = key
                except Exception as ex:
                    logger.warning("PYANNOTE BLOCKED: Failed to load PyAnnote diarization model: %s", ex)
                    raise RuntimeError(f"PYANNOTE BLOCKED: Failed to load PyAnnote diarization model: {ex}") from ex

                # 4. Perform actual inference
                try:
                    import soundfile as sf
                    waveform, sample_rate = sf.read(tmp_path, dtype="float32", always_2d=True)
                    waveform = torch.from_numpy(waveform.T)
                    diarization_input = {"waveform": waveform, "sample_rate": sample_rate}
                    import time
                    started = time.perf_counter()
                    diarization = pipeline(diarization_input, num_speakers=expected_speakers)
                    inference_seconds = time.perf_counter() - started
                    annotation = getattr(diarization, "speaker_diarization", diarization)
                    embeddings = getattr(diarization, "speaker_embeddings", None)
                    
                    turns = []
                    voiceprints = []
                    speakers_set = set()
                    
                    for turn, _, speaker in annotation.itertracks(yield_label=True):
                        turns.append(
                            SpeakerTurn(
                                speaker_id=str(speaker),
                                start_time=float(turn.start),
                                end_time=float(turn.end),
                                confidence=None
                            )
                        )
                        speakers_set.add(speaker)
                        
                    if not turns:
                        raise ValueError("REAL PyAnnote returned no speaker turns")
                    if embeddings is not None:
                        import numpy as np
                        labels = annotation.labels()
                        if len(embeddings) != len(labels) or not np.isfinite(embeddings).all():
                            raise ValueError("PyAnnote returned invalid speaker embeddings")
                        for spk, embedding in zip(labels, embeddings):
                            voiceprints.append(
                                SpeakerVoiceprint(
                                    speaker_id=str(spk),
                                    embedding_vector=embedding.tolist(),
                                    confidence=None
                                )
                            )
                        
                    return DiarizationResult(
                        meeting_id=meeting_id,
                        num_speakers=max(len(speakers_set), 1),
                        speaker_turns=turns,
                        voiceprints=voiceprints,
                        overall_confidence=None,
                        metadata={"model": "pyannote/speaker-diarization-3.1", "device": str(device),
                                  "raw_output_type": type(diarization).__name__, "inference_seconds": inference_seconds,
                                  "embedding_shape": list(embeddings.shape) if embeddings is not None else None,
                                  "embedding_dtype": str(embeddings.dtype) if embeddings is not None else None,
                                  "confidence_status": "NOT_VERIFIED"},
                    )
                except Exception as ex:
                    raise RuntimeError(f"PyAnnote diarization inference failed: {ex}") from ex

            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            # FIXTURE / MOCK mode
            num_spk = expected_speakers or 2
            turns = [
                SpeakerTurn(speaker_id="speaker_0", start_time=0.0, end_time=3.6, confidence=0.94),
                SpeakerTurn(speaker_id="speaker_1", start_time=3.6, end_time=7.2, confidence=0.91),
            ]
            voiceprints = [
                SpeakerVoiceprint(speaker_id="speaker_0", embedding_vector=[0.1] * 128, confidence=0.96),
                SpeakerVoiceprint(speaker_id="speaker_1", embedding_vector=[-0.1] * 128, confidence=0.93),
            ]
            return DiarizationResult(
                meeting_id=meeting_id,
                num_speakers=num_spk,
                speaker_turns=turns,
                voiceprints=voiceprints,
                overall_confidence=0.93,
            )

    def process_audio(
        self,
        audio_payload: bytes,
        meeting_id: uuid.UUID,
        correlation_id: Optional[str] = None,
    ) -> DiarizationResult:
        """Convenience wrapper for audio processing."""
        if get_settings().EXECUTION_MODE.upper() == "REAL":
            raise RuntimeError("REAL mode requires awaiting diarize_audio; static process_audio output is forbidden")
        turns = [
            SpeakerTurn(speaker_id="speaker_0", start_time=0.0, end_time=3.6, confidence=0.94),
            SpeakerTurn(speaker_id="speaker_1", start_time=3.6, end_time=7.2, confidence=0.91),
        ]
        voiceprints = [
            SpeakerVoiceprint(speaker_id="speaker_0", embedding_vector=[0.1] * 128, confidence=0.96),
            SpeakerVoiceprint(speaker_id="speaker_1", embedding_vector=[-0.1] * 128, confidence=0.93),
        ]
        return DiarizationResult(
            meeting_id=meeting_id,
            num_speakers=2,
            speaker_turns=turns,
            voiceprints=voiceprints,
            overall_confidence=0.93,
        )

    async def extract_voiceprint(
        self,
        audio_chunk: bytes,
        speaker_id: str,
    ) -> SpeakerVoiceprint:
        """
        Extracts voiceprint embedding vector from a short audio snippet.
        """
        if not audio_chunk:
            raise ValueError("Audio chunk cannot be empty.")
        if get_settings().EXECUTION_MODE.upper() == "REAL":
            raise RuntimeError("Standalone REAL voiceprint extraction is not implemented; use actual diarization embeddings")

        return SpeakerVoiceprint(
            speaker_id=speaker_id,
            embedding_vector=[0.05] * 128,
            confidence=0.90,
        )

    def verify_moss_with_pyannote(
        self,
        moss_segments: List[Any],
        pyannote_turns: List[Any]
    ) -> Dict[str, Any]:
        """
        Compare speaker attributions between MOSS and PyAnnote over the meeting timeline.
        Records disagreements and mismatches without automatically overwriting MOSS output.
        """
        disagreements = []
        matches = 0
        total_checks = 0
        speaker_mapping = {}  # moss_spk -> pyannote_spk
        mapped_pyannote_speakers = set()

        for m_seg in moss_segments:
            m_start = getattr(m_seg, "start_time", m_seg.get("start_time") if isinstance(m_seg, dict) else 0.0)
            m_end = getattr(m_seg, "end_time", m_seg.get("end_time") if isinstance(m_seg, dict) else 0.0)
            m_spk = getattr(m_seg, "speaker_id", m_seg.get("speaker_id") if isinstance(m_seg, dict) else "unknown")
            if isinstance(m_spk, str):
                m_spk = m_spk.strip("[]:")

            # Find overlapping pyannote turns
            overlapped = []
            for p_turn in pyannote_turns:
                p_start = getattr(p_turn, "start_time", p_turn.get("start_time") if isinstance(p_turn, dict) else 0.0)
                p_end = getattr(p_turn, "end_time", p_turn.get("end_time") if isinstance(p_turn, dict) else 0.0)
                p_spk = getattr(p_turn, "speaker_id", p_turn.get("speaker_id") if isinstance(p_turn, dict) else "unknown")

                overlap_start = max(m_start, p_start)
                overlap_end = min(m_end, p_end)
                overlap_duration = max(0.0, overlap_end - overlap_start)

                if overlap_duration > 0.05:  # significant overlap (> 50ms)
                    overlapped.append((p_spk, overlap_duration, p_start, p_end))

            if overlapped:
                total_checks += 1
                overlapped.sort(key=lambda x: x[1], reverse=True)
                best_p_spk, max_overlap, p_s, p_e = overlapped[0]

                # Check if we already mapped this MOSS speaker
                if m_spk in speaker_mapping:
                    if speaker_mapping[m_spk] != best_p_spk:
                        # Mismatch! MOSS speaker was previously mapped to speaker_mapping[m_spk], but now overlaps with best_p_spk
                        disagreements.append({
                            "type": "SPEAKER_MISMATCH",
                            "timestamp": f"{m_start:.2f}-{m_end:.2f}",
                            "moss_speaker": m_spk,
                            "pyannote_speaker": best_p_spk,
                            "expected_pyannote_speaker": speaker_mapping[m_spk],
                            "message": f"MOSS:\nSpeaker {m_spk} -> {m_start:.2f}–{m_end:.2f}\n\npyannote:\nSpeaker {best_p_spk} -> {p_s:.2f}–{p_e:.2f}\n\nVerification:\nSPEAKER_MISMATCH"
                        })
                    else:
                        matches += 1
                else:
                    # Check if PyAnnote speaker is already mapped to another MOSS speaker
                    if best_p_spk in mapped_pyannote_speakers:
                        disagreements.append({
                            "type": "SPEAKER_CONFLICT",
                            "timestamp": f"{m_start:.2f}-{m_end:.2f}",
                            "moss_speaker": m_spk,
                            "pyannote_speaker": best_p_spk,
                            "message": f"MOSS:\nSpeaker {m_spk} -> {m_start:.2f}–{m_end:.2f}\n\npyannote:\nSpeaker {best_p_spk} (Conflict with existing mapping)\n\nVerification:\nSPEAKER_MISMATCH"
                        })
                    else:
                        speaker_mapping[m_spk] = best_p_spk
                        mapped_pyannote_speakers.add(best_p_spk)
                        matches += 1
            else:
                # MOSS speaker segment has no overlapping PyAnnote speaker segment
                disagreements.append({
                    "type": "NO_PYANNOTE_OVERLAP",
                    "timestamp": f"{m_start:.2f}-{m_end:.2f}",
                    "moss_speaker": m_spk,
                    "message": f"MOSS:\nSpeaker {m_spk} -> {m_start:.2f}–{m_end:.2f}\n\npyannote:\nNo overlapping speech detected\n\nVerification:\nSPEAKER_MISMATCH"
                })

        accuracy = matches / total_checks if total_checks > 0 else 1.0

        return {
            "speaker_mapping": speaker_mapping,
            "disagreements": disagreements,
            "matches": matches,
            "total_checks": total_checks,
            "accuracy": accuracy,
        }
