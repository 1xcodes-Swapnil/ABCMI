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

    @staticmethod
    def _cluster_window_speakers(clustering, observations):
        """Link retained real voiceprints with the configured pipeline clustering.

        Distinct speakers in one window must never collapse into one identity.
        Colliding assignments remain explicitly unresolved, as do missing vectors.
        No participant count is supplied to the clustering algorithm.
        """
        import numpy as np
        from collections import Counter
        mappings, evidence = {}, []
        bank, keys = [], []
        for index, labels, vectors in observations:
            vectors = np.asarray(vectors, dtype=np.float32)
            if vectors.ndim != 2 or len(vectors) != len(labels):
                raise RuntimeError("Invalid retained PyAnnote window embeddings")
            for label, vector in zip(labels, vectors):
                key = (index, label)
                mappings[key] = f"window_{index}:{label}"
                norm = np.linalg.norm(vector)
                if np.isfinite(vector).all() and np.isfinite(norm) and norm > 0:
                    keys.append(key)
                    bank.append(vector / norm)
        if not bank:
            return mappings, {}, evidence
        vectors = np.stack(bank)
        groups = (np.zeros(1, dtype=int) if len(bank) == 1 else
                  clustering.cluster(vectors.copy(), min_clusters=1,
                                     max_clusters=len(bank), num_clusters=None))
        counts = Counter((index, int(group)) for (index, _), group in zip(keys, groups))
        voiceprints = {}
        for key, vector, group in zip(keys, vectors, groups):
            index, label = key
            collision = counts[(index, int(group))] > 1
            if not collision:
                mappings[key] = f"pyannote_global_{int(group)}"
            identity = mappings[key]
            voiceprints.setdefault(identity, []).append(vector)
            evidence.append({"window": index, "local_speaker": label,
                             "global_speaker": identity, "cluster_index": int(group),
                             "status": "UNRESOLVED_COLLISION" if collision else "CLUSTERED",
                             "accuracy": "NOT VERIFIED"})
        centroids = {label: np.mean(rows, axis=0) for label, rows in voiceprints.items()}
        return mappings, centroids, evidence

    @staticmethod
    def _bounded_inference(pipeline, path, settings, expected_speakers, cancel_check=None):
        """Bound waveform memory and reconcile actual window speaker embeddings.

        Overlap is trimmed at each midpoint so windows own disjoint time ranges.
        Matching similarities are diagnostics, never fabricated confidence values.
        """
        import numpy as np
        import soundfile as sf
        import torch
        from scipy.optimize import linear_sum_assignment
        from pyannote.core import Annotation, Segment
        from types import SimpleNamespace
        window = settings.PYANNOTE_WINDOW_SECONDS
        overlap = settings.PYANNOTE_WINDOW_OVERLAP_SECONDS
        step = window - overlap
        merged = Annotation()
        prototypes, labels, evidence = [], [], []
        observations, retained_turns = [], []
        from app.ai.audio_reader import AudioWindowReader
        with AudioWindowReader(path) as source:
            rate, frames = source.samplerate, len(source)
            duration = frames / rate
            start, index, previous_owned_end = 0.0, 0, 0.0
            while start < duration:
                if cancel_check is not None and cancel_check():
                    raise RuntimeError("Meeting processing cancelled at PyAnnote window boundary")
                end = min(start + window, duration)
                first, last = int(round(start * rate)), min(frames, int(round(end * rate)))
                source.seek(first)
                waveform = source.read(last-first, dtype="float32", always_2d=True)
                output = pipeline({"waveform": torch.from_numpy(waveform.T), "sample_rate": rate},
                                  max_speakers=expected_speakers)
                annotation = getattr(output, "speaker_diarization", output)
                embeddings = getattr(output, "speaker_embeddings", None)
                local_labels = annotation.labels()
                next_start = min(start + step, max(0.0, duration-window))
                owned_start = previous_owned_end
                owned_end = end if end == duration else (end + next_start) / 2
                mapping, matches, unavailable = {}, [], []
                if local_labels:
                    if embeddings is None or len(embeddings) != len(local_labels):
                        raise RuntimeError("Bounded PyAnnote requires actual per-speaker embeddings")
                    vectors = np.asarray(embeddings, dtype=np.float32)
                    if vectors.ndim != 2 or len(vectors) != len(local_labels):
                        raise RuntimeError(f"Invalid actual PyAnnote speaker embeddings at window {index} ({start}-{end}s), shape={vectors.shape}")
                    observations.append((index, local_labels, vectors.copy()))
                    norms = np.linalg.norm(vectors, axis=1)
                    valid_rows = np.flatnonzero(np.isfinite(vectors).all(axis=1) & np.isfinite(norms) & (norms > 0))
                    normalized = vectors[valid_rows] / norms[valid_rows, None]
                    if prototypes and len(valid_rows):
                        similarities = normalized @ np.asarray(prototypes).T
                        # Dummy columns let every speaker remain unmatched. Each
                        # real prototype can be assigned at most once per window.
                        gains = np.maximum(similarities-settings.PYANNOTE_SPEAKER_MATCH_THRESHOLD, 0)
                        gains = np.concatenate([gains, np.zeros((len(valid_rows), len(valid_rows)))], axis=1)
                        rows, columns = linear_sum_assignment(-gains)
                        for row, column in zip(rows, columns):
                            if column < len(prototypes) and gains[row, column] > 0:
                                local_label = local_labels[valid_rows[row]]
                                mapping[local_label] = labels[column]
                                matches.append({"local_speaker": local_label, "global_speaker": labels[column],
                                                "cosine_similarity": float(similarities[row, column])})
                    for row, label in enumerate(local_labels):
                        if label not in mapping:
                            global_label = f"window_{index}:{label}"
                            mapping[label] = global_label
                            if row in valid_rows:
                                labels.append(global_label)
                                prototypes.append(vectors[row] / norms[row])
                            else:
                                # Retain the actual model's window-local turns.
                                # No cross-window identity or voiceprint can be
                                # inferred from a zero/nonfinite embedding.
                                unavailable.append({"local_speaker": label, "global_speaker": global_label,
                                                    "reason": "nonfinite" if not np.isfinite(vectors[row]).all() else "zero_norm"})
                    for turn, track, label in annotation.itertracks(yield_label=True):
                        left, right = max(owned_start, start+float(turn.start)), min(owned_end, start+float(turn.end))
                        if right > left:
                            merged[Segment(left, right), f"{index}:{track}"] = mapping[label]
                            retained_turns.append((index, track, label, left, right))
                evidence.append({"index": index, "start": start, "end": end, "owned_start": owned_start,
                                 "owned_end": owned_end, "local_speakers": len(local_labels),
                                 "speaker_mapping": mapping, "matches": matches,
                                 "unavailable_embeddings": unavailable})
                del waveform, output
                if end == duration:
                    break
                # Keep a full context for the final window rather than running
                # the embedding model on a tiny tail. Ownership uses the actual
                # overlap, which may be larger than the nominal profile.
                if next_start <= start:
                    raise RuntimeError("PyAnnote window planner did not advance")
                previous_owned_end = owned_end
                start = next_start
                index += 1
        # Revisit the small voiceprint bank globally after bounded inference.
        # Fixed first-window prototypes fragment returning speakers; reuse the
        # actual pipeline's configured clustering instead of a new threshold.
        mapping, centroids, clustering_evidence = SpeakerDiarizationEngine._cluster_window_speakers(
            pipeline.clustering, observations)
        merged = Annotation()
        for index, track, label, left, right in retained_turns:
            merged[Segment(left, right), f"{index}:{track}"] = mapping[(index, label)]
        for item in evidence:
            item["provisional_speaker_mapping"] = item["speaker_mapping"]
            item["speaker_mapping"] = {label: identity for (index, label), identity in mapping.items()
                                       if index == item["index"]}
            item["global_clustering"] = [row for row in clustering_evidence if row["window"] == item["index"]]
            for unavailable in item["unavailable_embeddings"]:
                unavailable["global_speaker"] = mapping[(item["index"], unavailable["local_speaker"])]
        # Return only actual usable embeddings in the declared label order.
        kept_labels = merged.labels()
        embedding_labels = [label for label in kept_labels if label in centroids]
        kept_vectors = np.asarray([centroids[label] for label in embedding_labels], dtype=np.float32)
        return SimpleNamespace(speaker_diarization=merged, speaker_embeddings=kept_vectors,
                               embedding_labels=embedding_labels), evidence

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
        audio_file_path: Optional[str] = None,
        cancel_check=None,
    ) -> DiarizationResult:
        """
        Segments audio into speaker turns and extracts speaker voiceprints.
        Supports REAL mode with PyAnnote and FIXTURE/MOCK modes.
        """
        if not audio_payload and not audio_file_path:
            raise ValueError("Audio payload cannot be empty.")

        settings = get_settings()
        exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()

        if exec_mode == "REAL":
            # 1. Run real PyAnnote diarization
            # Save audio payload to a temporary file
            owns_temp_file = audio_file_path is None
            tmp_path = audio_file_path
            if owns_temp_file:
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
                    import time
                    started = time.perf_counter()
                    window_evidence = []
                    if validate_audio(tmp_path)["duration"] > settings.PYANNOTE_WINDOW_SECONDS:
                        diarization, window_evidence = self._bounded_inference(pipeline, tmp_path, settings, expected_speakers, cancel_check)
                    else:
                        from app.ai.audio_reader import AudioWindowReader
                        with AudioWindowReader(tmp_path) as source:
                            sample_rate = source.samplerate
                            waveform = source.read(len(source), dtype="float32", always_2d=True)
                        waveform = torch.from_numpy(waveform.T)
                        diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate}, num_speakers=expected_speakers)
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
                        labels = getattr(diarization, "embedding_labels", annotation.labels())
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
                                  "windows": window_evidence,
                                  "unavailable_speaker_embeddings": [item for window in window_evidence
                                                                     for item in window["unavailable_embeddings"]],
                                  "speaker_match_threshold": settings.PYANNOTE_SPEAKER_MATCH_THRESHOLD,
                                  "speaker_match_threshold_scope": "provisional_window_matching" if window_evidence else "NOT_APPLICABLE",
                                  "speaker_reconciliation": "configured_global_clustering_with_collision_guard" if window_evidence else "single_window",
                                  "speaker_count_status": "UNVERIFIED_MODEL_IDENTITIES",
                                  "speaker_match_accuracy": "NOT_VERIFIED" if window_evidence else "NOT_APPLICABLE",
                                  "confidence_status": "NOT_VERIFIED"},
                    )
                except Exception as ex:
                    raise RuntimeError(f"PyAnnote diarization inference failed: {ex}") from ex

            finally:
                if owns_temp_file and os.path.exists(tmp_path):
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
                    # Chunk-local MOSS identities can fragment one returning
                    # voice. Multiple MOSS IDs matching one PyAnnote identity
                    # are not evidence of a conflict. Retain MOSS output and
                    # still report inconsistent matches for the same MOSS ID.
                    speaker_mapping[m_spk] = best_p_spk
                    matches += 1
            else:
                # MOSS speaker segment has no overlapping PyAnnote speaker segment
                disagreements.append({
                    "type": "NO_PYANNOTE_OVERLAP",
                    "timestamp": f"{m_start:.2f}-{m_end:.2f}",
                    "moss_speaker": m_spk,
                    "message": f"MOSS:\nSpeaker {m_spk} -> {m_start:.2f}–{m_end:.2f}\n\npyannote:\nNo overlapping speech detected\n\nVerification:\nSPEAKER_MISMATCH"
                })

        accuracy = matches / total_checks if total_checks > 0 else None

        return {
            "speaker_mapping": speaker_mapping,
            "disagreements": disagreements,
            "matches": matches,
            "total_checks": total_checks,
            "accuracy": accuracy,
        }

    def reconcile_moss_identities(self, segments, pyannote_turns):
        """Alias fragmented MOSS IDs only on consistent global model agreement.

        MOSS remains the transcript source. Uncovered, conflicting, or unresolved
        window-local identities are unchanged. Agreement is not measured accuracy.
        """
        report = self.verify_moss_with_pyannote(segments, pyannote_turns)
        blocked = {item["moss_speaker"] for item in report["disagreements"]}
        representatives, aliases, changes = {}, {}, []
        for segment in segments:
            speaker = segment.speaker_id
            reference = report["speaker_mapping"].get(speaker)
            if speaker in blocked or not reference or not reference.startswith("pyannote_global_"):
                continue
            representatives.setdefault(reference, speaker)
            aliases[speaker] = representatives[reference]
        result = []
        for segment in segments:
            speaker = aliases.get(segment.speaker_id, segment.speaker_id)
            result.append(segment.model_copy(update={"speaker_id": speaker}))
            if speaker != segment.speaker_id:
                changes.append({"segment_id": str(segment.segment_id), "original_moss_speaker": segment.speaker_id,
                                "final_speaker": speaker, "pyannote_identity": report["speaker_mapping"][segment.speaker_id]})
        return result, {"method": "consistent_global_pyannote_agreement", "aliases": aliases,
                        "changed_segments": changes, "unresolved_moss_ids": sorted(blocked),
                        "accuracy": "NOT VERIFIED"}
