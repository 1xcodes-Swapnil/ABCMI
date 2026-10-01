"""
Speaker Diarization Engine

Provides speaker diarization, voiceprint embedding clustering,
speaker turn segmentation, overlap resolution, and speaker
assignment confidence scoring.
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

    speaker_id: str = Field(
        ...,
        description="Unique speaker identifier",
    )

    embedding_vector: List[float] = Field(
        default_factory=list,
        description="Dimensional voiceprint vector",
    )

    # REAL PyAnnote does not expose a calibrated confidence value
    # through the current DiarizeOutput contract.
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Speaker confidence when actually provided by the provider",
    )


class SpeakerTurn(CoreBaseModel):
    """Contiguous speaker turn interval with assigned speaker ID."""

    turn_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
    )

    speaker_id: str = Field(
        ...,
        description="Assigned speaker ID",
    )

    start_time: float = Field(
        ...,
        ge=0.0,
    )

    end_time: float = Field(
        ...,
        ge=0.0,
    )

    # REAL PyAnnote does not expose a calibrated turn confidence
    # in the current pipeline output.
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Turn confidence when actually provided by the provider",
    )


class DiarizationResult(CoreBaseModel):
    """Output model for speaker diarization processing."""

    meeting_id: uuid.UUID

    num_speakers: int = Field(
        default=1,
        ge=1,
    )

    speaker_turns: List[SpeakerTurn] = Field(
        default_factory=list,
    )

    voiceprints: List[SpeakerVoiceprint] = Field(
        default_factory=list,
    )

    # Do not fabricate a confidence value in REAL mode.
    overall_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overall confidence when actually provided by the provider",
    )


class SpeakerDiarizationEngine:
    """
    Speaker Diarization Engine utilizing voiceprint embeddings
    and spectral clustering/PyAnnote (REAL mode).
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
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

        REAL mode:
            Uses the actual PyAnnote pipeline and actual embeddings.

        FIXTURE/MOCK mode:
            Preserves the existing deterministic fixture behavior.
        """

        if not audio_payload:
            raise ValueError("Audio payload cannot be empty.")

        settings = get_settings()
        exec_mode = getattr(
            settings,
            "EXECUTION_MODE",
            "FIXTURE",
        ).upper()

        if exec_mode == "REAL":
            return await self._diarize_real(
                audio_payload=audio_payload,
                meeting_id=meeting_id,
                expected_speakers=expected_speakers,
                correlation_id=correlation_id,
            )

        return self._diarize_fixture(
            meeting_id=meeting_id,
            expected_speakers=expected_speakers,
        )

    async def _diarize_real(
        self,
        audio_payload: bytes,
        meeting_id: uuid.UUID,
        expected_speakers: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> DiarizationResult:
        """
        Execute genuine PyAnnote diarization.

        This method intentionally does not fabricate:
        - speaker embeddings
        - confidence values
        - speaker turns
        """

        settings = get_settings()

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as tmp:
            tmp.write(audio_payload)
            tmp_path = tmp.name

        try:
            # ---------------------------------------------------------
            # 1. Validate audio
            # ---------------------------------------------------------
            from app.ai.multilingual_asr import validate_audio

            validate_audio(tmp_path)

            # ---------------------------------------------------------
            # 2. Import runtime dependencies
            # ---------------------------------------------------------
            try:
                from pyannote.audio import Pipeline
                import torch
            except ImportError as ex:
                raise RuntimeError(
                    "Missing PyAnnote or Torch dependencies for "
                    f"REAL mode diarization: {ex}"
                ) from ex

            # ---------------------------------------------------------
            # 3. Require Hugging Face authentication
            # ---------------------------------------------------------
            if not settings.HF_TOKEN:
                message = (
                    "PYANNOTE BLOCKED: Hugging Face Auth Token "
                    "(HF_TOKEN) is required in the environment for "
                    "REAL PyAnnote diarization."
                )

                logger.warning(message)
                raise RuntimeError(message)

            # ---------------------------------------------------------
            # 4. Load REAL PyAnnote pipeline
            # ---------------------------------------------------------
            try:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=settings.HF_TOKEN,
                )

                if pipeline is None:
                    message = (
                        "PYANNOTE BLOCKED: PyAnnote pipeline "
                        "returned None from Hugging Face."
                    )

                    logger.warning(message)
                    raise RuntimeError(message)

                requested_device = getattr(
                    settings,
                    "OPENMOSS_DEVICE",
                    "cpu",
                )

                if (
                    requested_device == "cuda"
                    and torch.cuda.is_available()
                ):
                    device = torch.device("cuda")
                else:
                    device = torch.device("cpu")

                pipeline.to(device)

                logger.info(
                    "REAL PyAnnote pipeline loaded on device=%s",
                    device,
                )

            except Exception as ex:
                logger.warning(
                    "PYANNOTE BLOCKED: Failed to load PyAnnote "
                    "diarization model: %s",
                    ex,
                )

                raise RuntimeError(
                    "PYANNOTE BLOCKED: Failed to load PyAnnote "
                    f"diarization model: {ex}"
                ) from ex

            # ---------------------------------------------------------
            # 5. Perform REAL inference
            # ---------------------------------------------------------
            try:
                import soundfile as sf
                import numpy as np

                waveform, sample_rate = sf.read(
                    tmp_path,
                    dtype="float32",
                    always_2d=True,
                )

                waveform = torch.from_numpy(
                    waveform.T
                )

                diarization_input = {
                    "waveform": waveform,
                    "sample_rate": sample_rate,
                }

                diarization_output = pipeline(
                    diarization_input,
                    num_speakers=expected_speakers,
                )

                # -----------------------------------------------------
                # PyAnnote 4.x returns:
                #
                # DiarizeOutput(
                #   speaker_diarization: Annotation,
                #   exclusive_speaker_diarization: Annotation,
                #   speaker_embeddings: ndarray
                # )
                # -----------------------------------------------------
                annotation = (
                    diarization_output.speaker_diarization
                )

                speaker_embeddings = (
                    diarization_output.speaker_embeddings
                )

                # -----------------------------------------------------
                # 6. Extract REAL speaker turns
                # -----------------------------------------------------
                turns: List[SpeakerTurn] = []
                speaker_ids: List[str] = []

                for (
                    turn,
                    _,
                    speaker,
                ) in annotation.itertracks(
                    yield_label=True,
                ):
                    speaker_id = str(speaker)

                    start_time = float(turn.start)
                    end_time = float(turn.end)

                    if start_time < 0:
                        raise RuntimeError(
                            "PyAnnote produced a negative "
                            f"start timestamp: {start_time}"
                        )

                    if end_time < start_time:
                        raise RuntimeError(
                            "PyAnnote produced an invalid turn: "
                            f"{start_time} -> {end_time}"
                        )

                    turns.append(
                        SpeakerTurn(
                            speaker_id=speaker_id,
                            start_time=start_time,
                            end_time=end_time,
                            confidence=None,
                        )
                    )

                    if speaker_id not in speaker_ids:
                        speaker_ids.append(speaker_id)

                # -----------------------------------------------------
                # 7. Validate REAL speaker embeddings
                # -----------------------------------------------------
                voiceprints: List[SpeakerVoiceprint] = []

                if speaker_embeddings is not None:
                    embeddings = np.asarray(
                        speaker_embeddings
                    )

                    if embeddings.ndim == 1:
                        embeddings = embeddings.reshape(
                            1,
                            -1,
                        )

                    if embeddings.ndim != 2:
                        raise RuntimeError(
                            "PyAnnote returned speaker embeddings "
                            f"with unexpected shape: {embeddings.shape}"
                        )

                    embedding_count = len(embeddings)

                    if embedding_count != len(speaker_ids):
                        raise RuntimeError(
                            "PyAnnote speaker/embedding count mismatch: "
                            f"{len(speaker_ids)} speakers vs "
                            f"{embedding_count} embeddings"
                        )

                    for index, speaker_id in enumerate(
                        speaker_ids
                    ):
                        embedding = embeddings[index]

                        if not np.isfinite(
                            embedding
                        ).all():
                            raise RuntimeError(
                                "PyAnnote returned a non-finite "
                                f"embedding for speaker {speaker_id}"
                            )

                        embedding_values = (
                            embedding.astype(
                                float
                            ).tolist()
                        )

                        voiceprints.append(
                            SpeakerVoiceprint(
                                speaker_id=speaker_id,
                                embedding_vector=embedding_values,
                                confidence=None,
                            )
                        )

                elif speaker_ids:
                    raise RuntimeError(
                        "PyAnnote returned speaker turns but "
                        "no speaker embeddings."
                    )

                # -----------------------------------------------------
                # 8. Validate REAL output consistency
                # -----------------------------------------------------
                if not speaker_ids:
                    logger.warning(
                        "REAL PyAnnote returned no speaker turns."
                    )

                    # DiarizationResult requires num_speakers >= 1.
                    # Do not invent a speaker. Treat this as an
                    # explicit inference failure instead.
                    raise RuntimeError(
                        "REAL PyAnnote returned no speaker turns."
                    )

                # -----------------------------------------------------
                # 9. Return canonical REAL result
                # -----------------------------------------------------
                return DiarizationResult(
                    meeting_id=meeting_id,
                    num_speakers=len(speaker_ids),
                    speaker_turns=turns,
                    voiceprints=voiceprints,
                    overall_confidence=None,
                )

            except Exception as ex:
                logger.warning(
                    "REAL PyAnnote diarization inference failed: %s",
                    ex,
                )

                raise RuntimeError(
                    "PyAnnote diarization inference failed: "
                    f"{ex}"
                ) from ex

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _diarize_fixture(
        self,
        meeting_id: uuid.UUID,
        expected_speakers: Optional[int] = None,
    ) -> DiarizationResult:
        """
        Existing deterministic FIXTURE/MOCK behavior.

        This branch is intentionally separate from REAL mode.
        """

        num_spk = expected_speakers or 2

        turns = [
            SpeakerTurn(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=3.6,
                confidence=0.94,
            ),
            SpeakerTurn(
                speaker_id="speaker_1",
                start_time=3.6,
                end_time=7.2,
                confidence=0.91,
            ),
        ]

        voiceprints = [
            SpeakerVoiceprint(
                speaker_id="speaker_0",
                embedding_vector=[0.1] * 128,
                confidence=0.96,
            ),
            SpeakerVoiceprint(
                speaker_id="speaker_1",
                embedding_vector=[-0.1] * 128,
                confidence=0.93,
            ),
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
        """
        Convenience wrapper for existing fixture behavior.

        The REAL asynchronous path remains diarize_audio().
        """

        turns = [
            SpeakerTurn(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=3.6,
                confidence=0.94,
            ),
            SpeakerTurn(
                speaker_id="speaker_1",
                start_time=3.6,
                end_time=7.2,
                confidence=0.91,
            ),
        ]

        voiceprints = [
            SpeakerVoiceprint(
                speaker_id="speaker_0",
                embedding_vector=[0.1] * 128,
                confidence=0.96,
            ),
            SpeakerVoiceprint(
                speaker_id="speaker_1",
                embedding_vector=[-0.1] * 128,
                confidence=0.93,
            ),
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
        Existing fixture helper.

        REAL voiceprints are obtained from PyAnnote through
        diarize_audio().
        """

        if not audio_chunk:
            raise ValueError(
                "Audio chunk cannot be empty."
            )

        return SpeakerVoiceprint(
            speaker_id=speaker_id,
            embedding_vector=[0.05] * 128,
            confidence=0.90,
        )

    def verify_moss_with_pyannote(
        self,
        moss_segments: List[Any],
        pyannote_turns: List[Any],
    ) -> Dict[str, Any]:
        """
        Compare speaker attributions between MOSS and PyAnnote
        over the meeting timeline.

        Records disagreements and mismatches without automatically
        overwriting MOSS output.
        """

        disagreements = []
        matches = 0
        total_checks = 0
        speaker_mapping = {}
        mapped_pyannote_speakers = set()

        for m_seg in moss_segments:
            m_start = getattr(
                m_seg,
                "start_time",
                m_seg.get("start_time")
                if isinstance(m_seg, dict)
                else 0.0,
            )

            m_end = getattr(
                m_seg,
                "end_time",
                m_seg.get("end_time")
                if isinstance(m_seg, dict)
                else 0.0,
            )

            m_spk = getattr(
                m_seg,
                "speaker_id",
                m_seg.get("speaker_id")
                if isinstance(m_seg, dict)
                else "unknown",
            )

            if isinstance(m_spk, str):
                m_spk = m_spk.strip("[]:")

            overlapped = []

            for p_turn in pyannote_turns:
                p_start = getattr(
                    p_turn,
                    "start_time",
                    p_turn.get("start_time")
                    if isinstance(p_turn, dict)
                    else 0.0,
                )

                p_end = getattr(
                    p_turn,
                    "end_time",
                    p_turn.get("end_time")
                    if isinstance(p_turn, dict)
                    else 0.0,
                )

                p_spk = getattr(
                    p_turn,
                    "speaker_id",
                    p_turn.get("speaker_id")
                    if isinstance(p_turn, dict)
                    else "unknown",
                )

                overlap_start = max(
                    m_start,
                    p_start,
                )

                overlap_end = min(
                    m_end,
                    p_end,
                )

                overlap_duration = max(
                    0.0,
                    overlap_end - overlap_start,
                )

                if overlap_duration > 0.05:
                    overlapped.append(
                        (
                            p_spk,
                            overlap_duration,
                            p_start,
                            p_end,
                        )
                    )

            if overlapped:
                total_checks += 1

                overlapped.sort(
                    key=lambda x: x[1],
                    reverse=True,
                )

                (
                    best_p_spk,
                    max_overlap,
                    p_s,
                    p_e,
                ) = overlapped[0]

                if m_spk in speaker_mapping:
                    if (
                        speaker_mapping[m_spk]
                        != best_p_spk
                    ):
                        disagreements.append(
                            {
                                "type": "SPEAKER_MISMATCH",
                                "timestamp": (
                                    f"{m_start:.2f}-{m_end:.2f}"
                                ),
                                "moss_speaker": m_spk,
                                "pyannote_speaker": best_p_spk,
                                "expected_pyannote_speaker": (
                                    speaker_mapping[m_spk]
                                ),
                                "message": (
                                    "MOSS:\n"
                                    f"Speaker {m_spk} -> "
                                    f"{m_start:.2f}–{m_end:.2f}\n\n"
                                    "pyannote:\n"
                                    f"Speaker {best_p_spk} -> "
                                    f"{p_s:.2f}–{p_e:.2f}\n\n"
                                    "Verification:\n"
                                    "SPEAKER_MISMATCH"
                                ),
                            }
                        )
                    else:
                        matches += 1

                else:
                    if (
                        best_p_spk
                        in mapped_pyannote_speakers
                    ):
                        disagreements.append(
                            {
                                "type": "SPEAKER_CONFLICT",
                                "timestamp": (
                                    f"{m_start:.2f}-{m_end:.2f}"
                                ),
                                "moss_speaker": m_spk,
                                "pyannote_speaker": best_p_spk,
                                "message": (
                                    "MOSS:\n"
                                    f"Speaker {m_spk} -> "
                                    f"{m_start:.2f}–{m_end:.2f}\n\n"
                                    "pyannote:\n"
                                    f"Speaker {best_p_spk} "
                                    "(Conflict with existing mapping)\n\n"
                                    "Verification:\n"
                                    "SPEAKER_MISMATCH"
                                ),
                            }
                        )
                    else:
                        speaker_mapping[m_spk] = (
                            best_p_spk
                        )

                        mapped_pyannote_speakers.add(
                            best_p_spk
                        )

                        matches += 1

            else:
                disagreements.append(
                    {
                        "type": "NO_PYANNOTE_OVERLAP",
                        "timestamp": (
                            f"{m_start:.2f}-{m_end:.2f}"
                        ),
                        "moss_speaker": m_spk,
                        "message": (
                            "MOSS:\n"
                            f"Speaker {m_spk} -> "
                            f"{m_start:.2f}–{m_end:.2f}\n\n"
                            "pyannote:\n"
                            "No overlapping speech detected\n\n"
                            "Verification:\n"
                            "SPEAKER_MISMATCH"
                        ),
                    }
                )

        accuracy = (
            matches / total_checks
            if total_checks > 0
            else 1.0
        )

        return {
            "speaker_mapping": speaker_mapping,
            "disagreements": disagreements,
            "matches": matches,
            "total_checks": total_checks,
            "accuracy": accuracy,
        }
