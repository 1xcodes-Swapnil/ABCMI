"""
Long-Audio Chunk Processing Engine (Phase 4.26)
MOSS-Transcribe-Diarize + pyannote + Long-Meeting Chunk Processing Architecture.

Provides:
- Audio splitting/chunking with configurable duration and overlap windows
- Chunk state persistence and retry/resumption capability
- Global timestamp reconstruction from local chunk offsets
- Boundary-aware overlap deduplication to eliminate stuttering/repeated speech
- Cross-chunk speaker reconciliation and global speaker tracking
- Real-time chunk progress reporting via Redis Event Bus
- High-level orchestrator for processing 1-2+ hour meeting recordings
"""

from datetime import datetime
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from pydantic import Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.schemas.base import CoreBaseModel
from app.ai.multilingual_asr import (
    ASRResult,
    ASRSegment,
    ASRWordTimestamp,
    validate_audio,
)

logger = get_logger("ai.long_audio_processor")


def execution_identity(settings) -> Dict[str, Any]:
    """Bind resumed chunks to the actual local runtime and decoding contract."""
    import hashlib
    from importlib.metadata import PackageNotFoundError, version
    from app.ai.model_inventory import configure_cache, snapshot_for
    from app.ai.asr_selection import batch_asr_identity
    selected = batch_asr_identity(settings)
    from app.ai.speech_frontend import speech_frontend_identity
    versions = {}
    for package in ("torch", "transformers", "moss-transcribe-diarize", "bitsandbytes", "pyannote.audio"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "NOT AVAILABLE"
    snapshot = snapshot_for(selected["model_id"], configure_cache())
    sources = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
               for name in ("multilingual_asr.py", "long_audio_processor.py", "speaker_diarization.py", "audio_reader.py", "speech_frontend.py")}
    if selected["provider"] == "whisper":
        for name in ("whisper_provider.py", "asr_selection.py"):
            sources[name] = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
    return {"schema": 1, "model_revision": snapshot.name if snapshot else "NOT AVAILABLE",
            "device": settings.OPENMOSS_DEVICE, "precision": selected["precision"],
            "batch_provider": selected, "speech_frontend": speech_frontend_identity(settings),
            "max_new_tokens": 440 if selected["provider"] == "whisper" else settings.OPENMOSS_MAX_NEW_TOKENS, "do_sample": False,
            "pyannote_window": settings.PYANNOTE_WINDOW_SECONDS,
            "pyannote_overlap": settings.PYANNOTE_WINDOW_OVERLAP_SECONDS,
            "speaker_match_threshold": settings.PYANNOTE_SPEAKER_MATCH_THRESHOLD,
            "packages": versions, "source_sha256": sources}


class ChunkMetadata(CoreBaseModel):
    """Metadata representing an individual audio chunk within a long recording."""
    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    chunk_index: int = Field(..., ge=0, description="Sequential zero-based chunk index")
    total_chunks: int = Field(..., ge=1, description="Total number of chunks in the audio")
    start_time: float = Field(..., ge=0.0, description="Global start time in seconds")
    end_time: float = Field(..., ge=0.0, description="Global end time in seconds")
    duration: float = Field(..., ge=0.0, description="Duration of this chunk in seconds")
    overlap_start_seconds: float = Field(default=0.0, ge=0.0, description="Overlap with preceding chunk")
    overlap_end_seconds: float = Field(default=0.0, ge=0.0, description="Overlap with subsequent chunk")
    status: str = Field(default="pending", description="pending, processing, completed, failed")
    retry_count: int = Field(default=0, ge=0)
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    speech_activity: Dict[str, Any] = Field(default_factory=dict)


class ChunkProcessingState(CoreBaseModel):
    """Persistent tracking state for meeting chunked audio processing."""
    meeting_id: uuid.UUID
    audio_file_path: Optional[str] = None
    total_duration_seconds: float = Field(default=0.0, ge=0.0)
    chunk_duration_seconds: float = Field(default=600.0, ge=1.0)
    overlap_duration_seconds: float = Field(default=30.0, ge=0.0)
    total_chunks: int = Field(default=1, ge=1)
    chunks: List[ChunkMetadata] = Field(default_factory=list)
    completed_chunks_count: int = Field(default=0, ge=0)
    audio_sha256: Optional[str] = None
    model_id: Optional[str] = None
    execution_identity: Dict[str, Any] = Field(default_factory=dict)
    chunk_segments: Dict[str, List[ASRSegment]] = Field(default_factory=dict)
    checkpoint_version: int = 0
    global_speaker_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps 'chunk_{i}:{local_speaker}' -> 'global_speaker'"
    )
    overall_status: str = Field(default="pending", description="pending, processing, completed, failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LongAudioReconstructionResult(CoreBaseModel):
    """Result of full meeting transcript and speaker reconciliation across all chunks."""
    meeting_id: uuid.UUID
    asr_result: ASRResult
    total_chunks: int
    completed_chunks: int
    duration_seconds: float
    reconciled_speakers_count: int
    deduplicated_segments_count: int
    provenance_metadata: Dict[str, Any] = Field(default_factory=dict)


class LongAudioProcessor:
    """
    Orchestrates chunked audio processing for long meetings (1-2+ hours).
    Splits audio into overlapping windows, runs MOSS/pyannote on each chunk,
    reconstructs global timestamps, reconciles speaker labels across chunks,
    removes overlap duplication at boundaries, and persists state.
    """

    def __init__(
        self,
        chunk_duration: Optional[float] = None,
        overlap_duration: Optional[float] = None,
        concurrency: Optional[int] = None,
        event_bus: Optional[RedisEventBus] = None,
    ) -> None:
        settings = get_settings()
        self.chunk_duration = float(
            chunk_duration
            if chunk_duration is not None
            else getattr(settings, "AUDIO_CHUNK_DURATION_SECONDS", 600.0)
        )
        self.overlap_duration = float(
            overlap_duration
            if overlap_duration is not None
            else getattr(settings, "AUDIO_CHUNK_OVERLAP_SECONDS", 30.0)
        )
        if self.chunk_duration <= 0 or not 0 < self.overlap_duration < self.chunk_duration:
            raise ValueError("Require chunk duration > 0 and 0 < overlap < chunk duration.")

        self.concurrency = int(
            concurrency
            if concurrency is not None
            else getattr(settings, "AUDIO_CHUNK_CONCURRENCY", 1)
        )
        self.event_bus = event_bus or RedisEventBus()

    # -------------------------------------------------------------------------
    # 1. Audio Planning & Slicing
    # -------------------------------------------------------------------------

    def plan_chunks(self, total_duration: float) -> List[ChunkMetadata]:
        """
        Calculates time intervals for overlapping chunks covering the full audio duration.
        Formula:
          Step size = chunk_duration - overlap_duration
          Chunk k starts at: k * step_size
          Chunk k ends at: min(k * step_size + chunk_duration, total_duration)
        """
        if total_duration <= 0.0:
            return []

        # If audio is within single chunk duration, return single chunk with 0 overlap
        if total_duration <= self.chunk_duration:
            return [
                ChunkMetadata(
                    chunk_index=0,
                    total_chunks=1,
                    start_time=0.0,
                    end_time=total_duration,
                    duration=total_duration,
                    overlap_start_seconds=0.0,
                    overlap_end_seconds=0.0,
                )
            ]

        step_size = self.chunk_duration - self.overlap_duration
        chunks: List[ChunkMetadata] = []
        current_start = 0.0
        chunk_index = 0

        # Tentatively generate chunk intervals
        raw_intervals: List[Tuple[float, float]] = []
        while current_start < total_duration:
            current_end = min(current_start + self.chunk_duration, total_duration)
            raw_intervals.append((current_start, current_end))
            if current_end >= total_duration:
                break
            current_start += step_size

        total_chunks = len(raw_intervals)
        for idx, (c_start, c_end) in enumerate(raw_intervals):
            c_dur = c_end - c_start
            ov_start = self.overlap_duration if idx > 0 else 0.0
            ov_end = self.overlap_duration if idx < (total_chunks - 1) else 0.0

            chunks.append(
                ChunkMetadata(
                    chunk_index=idx,
                    total_chunks=total_chunks,
                    start_time=round(c_start, 3),
                    end_time=round(c_end, 3),
                    duration=round(c_dur, 3),
                    overlap_start_seconds=round(ov_start, 3),
                    overlap_end_seconds=round(ov_end, 3),
                )
            )

        return chunks

    def slice_audio_file(
        self,
        audio_file_path: str,
        chunk: ChunkMetadata,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Extracts a chunk interval [start_time, end_time] from an audio file and
        writes it to a temporary WAV file.
        Uses `soundfile` with a clean fallback to `wave`.
        """
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file does not exist: {audio_file_path}")

        target_dir = output_dir or tempfile.gettempdir()
        os.makedirs(target_dir, exist_ok=True)
        out_filename = f"chunk_{chunk.chunk_index}_{uuid.uuid4().hex[:8]}.wav"
        out_path = os.path.join(target_dir, out_filename)

        import soundfile as sf
        from app.ai.audio_reader import AudioWindowReader
        try:
            with AudioWindowReader(audio_file_path) as source:
                sr = source.samplerate
                start = max(0, min(int(chunk.start_time * sr), len(source)))
                end = max(start, min(int(chunk.end_time * sr), len(source)))
                source.seek(start)
                data = source.read(end-start, dtype="float32", always_2d=True)
                if not len(data):
                    raise RuntimeError("Audio chunk contains no actual samples")
                sf.write(out_path, data, sr, format="WAV")
                return out_path
        except Exception as exc:
            if os.path.exists(out_path):
                os.remove(out_path)
            raise RuntimeError(f"Failed to decode audio chunk {chunk.chunk_index}") from exc

    # -------------------------------------------------------------------------
    # 2. Global Timestamp Reconstruction
    # -------------------------------------------------------------------------

    @staticmethod
    def _cleanup_temporary_chunk(path, pending):
        """Remove only an owned chunk; defer transient Windows locks to final cleanup."""
        if path not in pending:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
            pending.remove(path)
        except OSError as exc:
            logger.debug("Temporary chunk cleanup deferred: %s", exc)

    @staticmethod
    def offset_segments_to_global_time(
        segments: List[ASRSegment],
        chunk_start_time: float,
    ) -> List[ASRSegment]:
        """
        Offsets local segment and word timestamps by chunk_start_time:
          t_global = t_local + chunk_start_time
        """
        offset_segments: List[ASRSegment] = []
        for seg in segments:
            global_start = round(seg.start_time + chunk_start_time, 3)
            global_end = round(seg.end_time + chunk_start_time, 3)

            offset_words: List[ASRWordTimestamp] = []
            for w in seg.words:
                offset_words.append(
                    ASRWordTimestamp(
                        word=w.word,
                        start_time=round(w.start_time + chunk_start_time, 3),
                        end_time=round(w.end_time + chunk_start_time, 3),
                        confidence=w.confidence,
                        language_code=w.language_code,
                    )
                )

            offset_segments.append(
                ASRSegment(
                    segment_id=seg.segment_id,
                    speaker_id=seg.speaker_id,
                    start_time=global_start,
                    end_time=global_end,
                    transcript=seg.transcript,
                    detected_language=seg.detected_language,
                    words=offset_words,
                    confidence=seg.confidence,
                    metadata=dict(seg.metadata),
                )
            )
        return offset_segments

    # -------------------------------------------------------------------------
    # 3. Cross-Chunk Speaker Reconciliation
    # -------------------------------------------------------------------------

    def reconcile_speakers_across_chunks(
        self,
        chunk_results: List[Tuple[ChunkMetadata, List[ASRSegment]]],
        existing_speaker_mapping: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[List[ASRSegment]], Dict[str, str]]:
        """
        Reconciles local speaker IDs across consecutive chunks into unified global speaker IDs.
        For Chunk 0:
          maps local speakers S01, S02 -> SPEAKER_00, SPEAKER_01, etc.
        For Chunk k (k >= 1):
          Analyzes the overlap interval between Chunk k-1 and Chunk k.
          Calculates temporal overlap between local speakers in Chunk k and already-mapped
          speakers in Chunk k-1.
          Maps local speakers to the best-matching global speaker with maximum overlapping speech.
          Any local speaker not present in the overlap is assigned a new global speaker identifier.
        """
        global_speaker_map: Dict[str, str] = dict(existing_speaker_mapping or {})
        assigned_global_speakers: List[str] = sorted(list(set(global_speaker_map.values())))
        reconciled_chunks: List[List[ASRSegment]] = []

        def get_next_global_speaker() -> str:
            idx = len(assigned_global_speakers)
            new_id = f"SPEAKER_{idx:02d}"
            assigned_global_speakers.append(new_id)
            return new_id

        prev_chunk_meta: Optional[ChunkMetadata] = None
        prev_segments: Optional[List[ASRSegment]] = None

        for chunk_meta, segments in chunk_results:
            c_idx = chunk_meta.chunk_index
            local_to_global: Dict[str, str] = {}

            if c_idx == 0 or prev_chunk_meta is None or prev_segments is None:
                # First chunk: assign new global speakers for every distinct speaker in this chunk
                for seg in segments:
                    spk = seg.speaker_id or "SPEAKER_UNKNOWN"
                    if spk in {"UNRESOLVED", "SPEAKER_UNKNOWN"}:
                        continue  # No model identity exists to reconcile.
                    map_key = f"chunk_{c_idx}:{spk}"
                    if map_key in global_speaker_map:
                        local_to_global[spk] = global_speaker_map[map_key]
                    elif spk not in local_to_global:
                        g_spk = get_next_global_speaker()
                        local_to_global[spk] = g_spk
                        global_speaker_map[map_key] = g_spk
            else:
                # Subsequent chunk: calculate overlap interval with preceding chunk
                # Overlap zone in global time: [chunk_meta.start_time, prev_chunk_meta.end_time]
                overlap_start = chunk_meta.start_time
                overlap_end = prev_chunk_meta.end_time

                # Identify speech turns in the overlap window for both chunks
                overlap_matrix: Dict[Tuple[str, str], float] = {}  # (prev_global_spk, curr_local_spk) -> duration

                if overlap_end > overlap_start:
                    for p_seg in prev_segments:
                        p_spk = p_seg.speaker_id
                        if p_spk in {None, "UNRESOLVED", "SPEAKER_UNKNOWN"}:
                            continue
                        p_s = max(p_seg.start_time, overlap_start)
                        p_e = min(p_seg.end_time, overlap_end)
                        if p_e <= p_s:
                            continue

                        for c_seg in segments:
                            c_spk = c_seg.speaker_id or "SPEAKER_UNKNOWN"
                            if c_spk in {"UNRESOLVED", "SPEAKER_UNKNOWN"}:
                                continue
                            c_s = max(c_seg.start_time, overlap_start)
                            c_e = min(c_seg.end_time, overlap_end)
                            if c_e <= c_s:
                                continue

                            # Compute speech overlap between p_seg and c_seg
                            inter_s = max(p_s, c_s)
                            inter_e = min(p_e, c_e)
                            if inter_e > inter_s:
                                dur = inter_e - inter_s
                                key = (p_spk, c_spk)
                                overlap_matrix[key] = overlap_matrix.get(key, 0.0) + dur

                # Map current chunk's local speakers to global speakers based on highest overlap
                curr_local_speakers = {seg.speaker_id for seg in segments
                    if seg.speaker_id not in {None, "UNRESOLVED", "SPEAKER_UNKNOWN"}}
                used_prev_speakers = set()

                # Sort matches by duration descending
                sorted_matches = sorted(overlap_matrix.items(), key=lambda x: x[1], reverse=True)
                for (prev_spk, curr_spk), ov_dur in sorted_matches:
                    if curr_spk not in local_to_global and prev_spk not in used_prev_speakers:
                        local_to_global[curr_spk] = prev_spk
                        used_prev_speakers.add(prev_spk)
                        global_speaker_map[f"chunk_{c_idx}:{curr_spk}"] = prev_spk

                # Any remaining unmapped speakers in current chunk get a new or preserved global ID
                for spk in curr_local_speakers:
                    map_key = f"chunk_{c_idx}:{spk}"
                    if map_key in global_speaker_map:
                        local_to_global[spk] = global_speaker_map[map_key]
                    elif spk not in local_to_global:
                        g_spk = get_next_global_speaker()
                        local_to_global[spk] = g_spk
                        global_speaker_map[map_key] = g_spk

            # Re-label current chunk segments with their assigned global speaker IDs
            reconciled_curr: List[ASRSegment] = []
            for seg in segments:
                spk = seg.speaker_id or "SPEAKER_UNKNOWN"
                g_spk = local_to_global.get(spk, spk)
                reconciled_curr.append(
                    ASRSegment(
                        segment_id=seg.segment_id,
                        speaker_id=g_spk,
                        start_time=seg.start_time,
                        end_time=seg.end_time,
                        transcript=seg.transcript,
                        detected_language=seg.detected_language,
                        words=seg.words,
                        confidence=seg.confidence,
                        metadata=dict(seg.metadata),
                    )
                )

            reconciled_chunks.append(reconciled_curr)
            prev_chunk_meta = chunk_meta
            prev_segments = reconciled_curr

        return reconciled_chunks, global_speaker_map

    # -------------------------------------------------------------------------
    # 4. Overlap Deduplication & Boundary Merging
    # -------------------------------------------------------------------------

    @staticmethod
    def _text_similarity(s1: str, s2: str) -> float:
        """Compare ordered Unicode tokens without discarding vowel marks."""
        import unicodedata
        from difflib import SequenceMatcher
        def tokens(text):
            text = unicodedata.normalize("NFC", text).casefold()
            return "".join(c if c.isspace() or unicodedata.category(c)[0] in "LMN"
                           else " " for c in text).split()
        w1, w2 = tokens(s1), tokens(s2)
        if not w1 or not w2:
            return 0.0
        return SequenceMatcher(None, w1, w2, autojunk=False).ratio()

    @classmethod
    def _same_observed_turn(cls, left, right) -> bool:
        """Only deduplicate text that also describes the same temporal event."""
        # Equal unknown buckets do not establish that two observations belong
        # to the same person. Preserve ambiguous boundary text for review.
        unknown = {"", "UNRESOLVED", "SPEAKER_UNKNOWN", "UNKNOWN"}
        if any(speaker is None or str(speaker).strip().upper() in unknown
               for speaker in (left.speaker_id, right.speaker_id)):
            return False
        if left.speaker_id != right.speaker_id:
            return False
        intersection = min(left.end_time, right.end_time) - max(left.start_time, right.start_time)
        shorter = min(left.end_time-left.start_time, right.end_time-right.start_time)
        return (shorter > 0 and intersection > 0 and intersection/shorter >= 0.5
                and cls._text_similarity(left.transcript, right.transcript) >= 0.9)

    def merge_and_deduplicate_chunks(
        self,
        chunk_metas: List[ChunkMetadata],
        reconciled_chunks: List[List[ASRSegment]],
    ) -> Tuple[List[ASRSegment], int]:
        """
        Merges speech segments from all chunks, deduplicating the overlap regions.
        Eliminates duplicate sentences or repeated phrases at chunk boundaries.
        
        Boundary-Aware Algorithm:
        For each boundary between Chunk k-1 and Chunk k:
          1. Overlap window is [chunk_k.start_time, chunk_k-1.end_time]
          2. Compute midpoint T_mid = (chunk_k.start_time + chunk_k-1.end_time) / 2
          3. Check for exact/high text similarity duplicates between segments in chunk_k-1 and chunk_k.
          4. Transition boundary: retain segments from chunk_k-1 that start before T_mid (or natural pause),
             and transition to chunk_k for segments after.
          5. Filter out near-identical repeated segments that overlap chronologically.
        """
        self.last_dedup_decisions = []
        if not reconciled_chunks:
            return [], 0

        if len(reconciled_chunks) == 1:
            return reconciled_chunks[0], 0

        merged_segments: List[ASRSegment] = []
        dedup_count = 0

        # Start with all segments from chunk 0
        current_stream = list(reconciled_chunks[0])

        for idx in range(1, len(reconciled_chunks)):
            prev_meta = chunk_metas[idx - 1]
            curr_meta = chunk_metas[idx]
            curr_segs = reconciled_chunks[idx]

            overlap_start = curr_meta.start_time
            overlap_end = prev_meta.end_time

            if overlap_end <= overlap_start or not current_stream or not curr_segs:
                # No temporal overlap, append directly
                current_stream.extend(curr_segs)
                continue

            # Determine boundary transition time T_boundary
            # Ideal boundary is the midpoint of the overlap window
            t_mid = (overlap_start + overlap_end) / 2.0

            # Scan overlap region in current_stream (from previous chunks)
            kept_prev: List[ASRSegment] = []
            for seg in current_stream:
                # If segment ends well before overlap start, keep it
                if seg.end_time <= overlap_start:
                    kept_prev.append(seg)
                # If segment ends before or close to midpoint, keep it
                elif seg.start_time < t_mid and seg.end_time <= overlap_end:
                    kept_prev.append(seg)
                elif seg.end_time <= t_mid:
                    kept_prev.append(seg)
                else:
                    # Segment lies past midpoint in overlap zone, prune if duplicate exists in curr_segs
                    # Check text match in curr_segs
                    has_match = any(self._same_observed_turn(seg, c) for c in curr_segs)
                    if has_match:
                        dedup_count += 1
                        self.last_dedup_decisions.append({"segment_id": str(seg.segment_id),
                            "chunk_index": idx - 1, "decision": "removed_text_duplicate",
                            "start_time": seg.start_time, "end_time": seg.end_time})
                    else:
                        kept_prev.append(seg)

            # Now select segments from curr_segs to append
            kept_curr: List[ASRSegment] = []
            last_kept_time = kept_prev[-1].end_time if kept_prev else overlap_start

            for seg in curr_segs:
                # If segment is in the overlap region
                if seg.start_time < overlap_end:
                    # Check if already covered by kept_prev with high text similarity
                    is_duplicate = False
                    for prev_s in kept_prev:
                        if self._same_observed_turn(prev_s, seg):
                            is_duplicate = True
                            dedup_count += 1
                            self.last_dedup_decisions.append({"segment_id": str(seg.segment_id),
                                "chunk_index": idx, "decision": "removed_text_duplicate",
                                "matched_segment_id": str(prev_s.segment_id),
                                "start_time": seg.start_time, "end_time": seg.end_time})
                            break
                    if not is_duplicate:
                        previous_end = last_kept_time
                        uncertain_matches = [p for p in kept_prev
                            if p.speaker_id == seg.speaker_id
                            and min(p.end_time, seg.end_time) > max(p.start_time, seg.start_time)]
                        kept_curr.append(seg)
                        last_kept_time = max(last_kept_time, seg.end_time)
                        self.last_dedup_decisions.append({"segment_id": str(seg.segment_id),
                            "chunk_index": idx, "decision": "retained_without_verified_duplicate",
                            "start_time": seg.start_time, "end_time": seg.end_time,
                            "previous_end_time": previous_end,
                            "overlapping_segment_ids": [str(p.segment_id) for p in uncertain_matches],
                            "requires_boundary_review": bool(uncertain_matches),
                            "duplicate_verified": False})
                else:
                    # Beyond overlap region: unconditionally keep
                    kept_curr.append(seg)

            current_stream = kept_prev + kept_curr

        # Final pass: ensure strict temporal monotonicity
        current_stream.sort(key=lambda s: (s.start_time, s.end_time))
        return current_stream, dedup_count

    # -------------------------------------------------------------------------
    # 5. Full Long-Audio Pipeline Execution & Resumption
    # -------------------------------------------------------------------------

    async def process_long_audio(
        self,
        audio_file_path: str,
        meeting_id: uuid.UUID,
        transcribe_chunk_func: Callable[[str, ChunkMetadata], Any],
        initial_state: Optional[ChunkProcessingState] = None,
        correlation_id: Optional[str] = None,
        cancel_check=None,
        transcription_context: Optional[Dict[str, Any]] = None,
    ) -> LongAudioReconstructionResult:
        """
        Main entry point for processing long audio files.
        1. Validates audio duration and plans chunk boundaries.
        2. Maintains state for fault-tolerance and retryability.
        3. Transcribes each chunk (using provided MOSS/Whisper callable).
        4. Offsets local chunk timestamps to global meeting timestamps.
        5. Reconciles speakers across chunk boundaries.
        6. Removes overlap duplicates to produce a smooth global transcript.
        7. Publishes real-time chunk progress events.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        audio_meta = validate_audio(audio_file_path)
        total_duration = audio_meta["duration"]

        import hashlib
        import json
        settings = get_settings()
        state_root = Path(settings.AUDIO_CHUNK_STATE_DIR) if settings.AUDIO_CHUNK_STATE_DIR else None
        runtime_identity = execution_identity(settings)
        from app.ai.asr_selection import batch_asr_identity
        active_model_id = batch_asr_identity(settings)["model_id"]
        if transcription_context is not None:
            runtime_identity = {**runtime_identity, "transcription_context": transcription_context}
        digest = None
        history = state_root / str(meeting_id) if state_root else None
        if history:
            hasher = hashlib.sha256()
            with open(audio_file_path, "rb") as source:
                for data in iter(lambda: source.read(1024 * 1024), b""):
                    hasher.update(data)
            digest = hasher.hexdigest()
            checkpoints = sorted(history.glob("state_*.json")) if history.exists() else []
            if not initial_state and checkpoints:
                initial_state = ChunkProcessingState.model_validate_json(checkpoints[-1].read_text(encoding="utf-8"))
            if initial_state and (initial_state.audio_sha256 != digest or
                initial_state.chunk_duration_seconds != self.chunk_duration or
                initial_state.overlap_duration_seconds != self.overlap_duration or
                initial_state.model_id != active_model_id or
                initial_state.execution_identity != runtime_identity):
                raise RuntimeError("Saved chunk checkpoint differs from actual audio/model/configuration; refusing stale resume")
            if initial_state:
                # A crash can occur after a transcript journal is committed but
                # before its manifest. Recover that actual output without inference.
                for chunk in initial_state.chunks:
                    key = str(chunk.chunk_id)
                    journal = history / f"segments_{key}.json"
                    if key not in initial_state.chunk_segments and journal.is_file():
                        initial_state.chunk_segments[key] = [ASRSegment.model_validate(row)
                            for row in json.loads(journal.read_text(encoding="utf-8"))]
                    if key in initial_state.chunk_segments:
                        chunk.status = "completed"
                    elif chunk.status == "completed":
                        raise RuntimeError("Completed chunk has no durable transcript journal")
                initial_state.completed_chunks_count = sum(c.status == "completed" for c in initial_state.chunks)
                if checkpoints:
                    initial_state.checkpoint_version = max(initial_state.checkpoint_version,
                        int(checkpoints[-1].stem.removeprefix("state_")))

        # 1. State initialization or resumption
        if initial_state and initial_state.chunks:
            state = initial_state
            logger.info(f"Resuming long-audio processing for meeting {meeting_id} from saved state.")
        else:
            chunks = self.plan_chunks(total_duration)
            state = ChunkProcessingState(
                meeting_id=meeting_id,
                audio_file_path=audio_file_path,
                total_duration_seconds=total_duration,
                chunk_duration_seconds=self.chunk_duration,
                overlap_duration_seconds=self.overlap_duration,
                total_chunks=len(chunks),
                chunks=chunks,
                overall_status="processing",
                audio_sha256=digest,
                model_id=active_model_id,
                execution_identity=runtime_identity,
            )

        def save_state():
            if history:
                history.mkdir(parents=True, exist_ok=True)
                for key, segments in state.chunk_segments.items():
                    journal = history / f"segments_{key}.json"
                    if not journal.exists():
                        temporary = journal.with_name(f"{journal.stem}_{uuid.uuid4().hex}.tmp")
                        temporary.write_text(json.dumps([s.model_dump(mode="json") for s in segments]), encoding="utf-8")
                        temporary.replace(journal)
                state.checkpoint_version += 1
                target = history / f"state_{state.checkpoint_version:08d}.json"
                temporary = target.with_name(f"{target.stem}_{uuid.uuid4().hex}.tmp")
                with temporary.open("x", encoding="utf-8") as output:
                    output.write(state.model_dump_json(indent=2, exclude={"chunk_segments"}))
                temporary.replace(target)
        save_state()

        async def check_cancellation():
            if cancel_check is not None and await cancel_check():
                state.overall_status = "cancelled"
                state.updated_at = datetime.utcnow()
                save_state()
                await self._emit_chunk_event(meeting_id, "chunk_processing_cancelled", {
                    "completed_chunks": state.completed_chunks_count, "total_chunks": state.total_chunks,
                    "correlation_id": corr_id})
                raise RuntimeError("Meeting processing cancelled at chunk boundary; actual journals preserved")

        # Emit initial processing event
        await self._emit_chunk_event(
            meeting_id=meeting_id,
            event_type="chunk_processing_started",
            payload={
                "total_duration": total_duration,
                "total_chunks": state.total_chunks,
                "chunk_duration": self.chunk_duration,
                "overlap_duration": self.overlap_duration,
                "correlation_id": corr_id,
            },
        )

        chunk_results: List[Tuple[ChunkMetadata, List[ASRSegment]]] = []
        temp_chunk_files: List[str] = []
        from app.ai.speech_frontend import SpeechFrontend
        frontend = SpeechFrontend(settings) if settings.EXECUTION_MODE.upper() == "REAL" else None

        try:
            # 2. Process chunks sequentially or with bounded concurrency
            for idx, chunk_meta in enumerate(state.chunks):
                await check_cancellation()
                if chunk_meta.status == "completed":
                    restored = state.chunk_segments.get(str(chunk_meta.chunk_id))
                    if restored is None and get_settings().EXECUTION_MODE.upper() == "REAL":
                        raise RuntimeError("REAL resume requires saved actual chunk transcripts")
                    if restored is not None:
                        chunk_results.append((chunk_meta, restored))
                    logger.info(f"Chunk {idx}/{state.total_chunks} already completed. Skipping.")
                    continue

                chunk_meta.status = "processing"
                state.updated_at = datetime.utcnow()

                await self._emit_chunk_event(
                    meeting_id=meeting_id,
                    event_type="chunk_started",
                    payload={
                        "chunk_index": idx,
                        "total_chunks": state.total_chunks,
                        "start_time": chunk_meta.start_time,
                        "end_time": chunk_meta.end_time,
                        "progress_percentage": round((idx / state.total_chunks) * 100, 1),
                        "correlation_id": corr_id,
                    },
                )

                # Slice chunk into temporary audio file
                chunk_audio_path = self.slice_audio_file(audio_file_path, chunk_meta)
                temp_chunk_files.append(chunk_audio_path)

                try:
                    # Execute transcription callback
                    if frontend is not None:
                        chunk_meta.speech_activity = frontend.analyze(chunk_audio_path)
                        if chunk_meta.speech_activity.get("status") == "COMPLETED":
                            chunk_meta.speech_activity["global_speech_intervals"] = [
                                {"start": chunk_meta.start_time + interval["start"],
                                 "end": chunk_meta.start_time + interval["end"]}
                                for interval in chunk_meta.speech_activity["speech_intervals"]]
                        save_state()  # Preserve the actual decision before ASR or a crash.
                    skip_no_speech = (settings.EXECUTION_MODE.upper() == "REAL"
                                      and settings.AUDIO_VAD_MODE == "filter"
                                      and chunk_meta.speech_activity.get("status") == "COMPLETED"
                                      and chunk_meta.speech_activity.get("speech_detected") is False)
                    if skip_no_speech:
                        chunk_meta.speech_activity["decision"] = "skipped_no_neural_speech"
                        raw_segments = []
                    else:
                        raw_segments = await transcribe_chunk_func(chunk_audio_path, chunk_meta)
                    if isinstance(raw_segments, ASRResult):
                        local_segments = raw_segments.segments
                    elif isinstance(raw_segments, list):
                        local_segments = raw_segments
                    else:
                        raise TypeError("Chunk provider must return ASRResult or a list of actual ASR segments")

                    # Reconstruct global timestamps for this chunk
                    global_segments = self.offset_segments_to_global_time(
                        segments=local_segments,
                        chunk_start_time=chunk_meta.start_time,
                    )

                    chunk_results.append((chunk_meta, global_segments))
                    state.chunk_segments[str(chunk_meta.chunk_id)] = global_segments

                    chunk_meta.status = "completed"
                    chunk_meta.processed_at = datetime.utcnow()
                    state.completed_chunks_count += 1
                    state.updated_at = datetime.utcnow()
                    save_state()

                    await self._emit_chunk_event(
                        meeting_id=meeting_id,
                        event_type="chunk_completed",
                        payload={
                            "chunk_index": idx,
                            "total_chunks": state.total_chunks,
                            "segments_extracted": len(global_segments),
                            "speech_activity": chunk_meta.speech_activity,
                            "progress_percentage": round((state.completed_chunks_count / state.total_chunks) * 100, 1),
                            "correlation_id": corr_id,
                        },
                    )

                except Exception as chunk_err:
                    chunk_meta.status = "failed"
                    chunk_meta.error_message = str(chunk_err)
                    chunk_meta.retry_count += 1
                    state.updated_at = datetime.utcnow()
                    save_state()

                    logger.error(f"Error processing chunk {idx} for meeting {meeting_id}: {chunk_err}")
                    await self._emit_chunk_event(
                        meeting_id=meeting_id,
                        event_type="chunk_failed",
                        payload={
                            "chunk_index": idx,
                            "error": str(chunk_err),
                            "correlation_id": corr_id,
                        },
                    )
                    raise chunk_err
                finally:
                    self._cleanup_temporary_chunk(chunk_audio_path, temp_chunk_files)

            await check_cancellation()
            # 3. Cross-chunk Speaker Reconciliation
            reconciled_chunks, global_spk_map = self.reconcile_speakers_across_chunks(
                chunk_results=chunk_results,
                existing_speaker_mapping=state.global_speaker_mapping,
            )
            state.global_speaker_mapping = global_spk_map

            # 4. Overlap Deduplication and Transcript Merging
            final_segments, dedup_count = self.merge_and_deduplicate_chunks(
                chunk_metas=[m for m, _ in chunk_results],
                reconciled_chunks=reconciled_chunks,
            )

            # 5. Construct full transcript and language distribution
            full_transcript = " ".join([s.transcript for s in final_segments if s.transcript])
            detected_languages = sorted(list(set(s.detected_language for s in final_segments if s.detected_language)))

            lang_distribution: Dict[str, float] = {}
            if final_segments:
                for s in final_segments:
                    if s.detected_language:
                        lang = s.detected_language
                        lang_distribution[lang] = lang_distribution.get(lang, 0.0) + 1.0
                for l in lang_distribution:
                    lang_distribution[l] = round(lang_distribution[l] / len(final_segments), 4)

            # Overall confidence from segments
            measured_confidences = [s.confidence for s in final_segments if s.confidence is not None]
            overall_conf = (sum(measured_confidences) / len(measured_confidences)
                            if measured_confidences else None)

            asr_result = ASRResult(
                meeting_id=meeting_id,
                full_transcript=full_transcript,
                detected_languages=detected_languages,
                language_distribution=lang_distribution,
                segments=final_segments,
                overall_confidence=round(overall_conf, 4) if overall_conf is not None else None,
                metadata={
                    "is_chunked": True,
                    "total_chunks": state.total_chunks,
                    "chunk_duration_seconds": self.chunk_duration,
                    "overlap_duration_seconds": self.overlap_duration,
                    "deduplicated_segments_count": dedup_count,
                    "deduplication_decisions": self.last_dedup_decisions,
                    "quality_warnings": (["Unresolved overlapping chunk hypotheses remain. Review boundary text; no cross-script equivalence or word deletion was assumed."]
                        if any(d.get("requires_boundary_review") for d in self.last_dedup_decisions) else []),
                    "global_speakers": sorted(list(set(global_spk_map.values()))),
                    "provenance": "ASR:ChunkedLongAudioProcessor",
                    "chunks": [chunk.model_dump(mode="json") for chunk in state.chunks],
                    "speaker_mapping": global_spk_map,
                    "correlation_id": corr_id,
                },
            )

            state.overall_status = "completed"
            state.updated_at = datetime.utcnow()
            save_state()

            await self._emit_chunk_event(
                meeting_id=meeting_id,
                event_type="chunk_processing_completed",
                payload={
                    "total_chunks": state.total_chunks,
                    "deduplicated_segments_count": dedup_count,
                    "total_segments": len(final_segments),
                    "correlation_id": corr_id,
                },
            )

            return LongAudioReconstructionResult(
                meeting_id=meeting_id,
                asr_result=asr_result,
                total_chunks=state.total_chunks,
                completed_chunks=state.completed_chunks_count,
                duration_seconds=total_duration,
                reconciled_speakers_count=len(set(global_spk_map.values())),
                deduplicated_segments_count=dedup_count,
                provenance_metadata={
                    "total_chunks": state.total_chunks,
                    "chunk_duration_seconds": self.chunk_duration,
                    "overlap_duration_seconds": self.overlap_duration,
                    "speaker_mapping": global_spk_map,
                },
            )

        finally:
            # Clean up temporary sliced chunk WAV files safely
            for path in temp_chunk_files:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as clean_err:
                        logger.debug(f"Could not remove temp chunk file {path}: {clean_err}")

    async def _emit_chunk_event(
        self,
        meeting_id: uuid.UUID,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Publishes real-time chunk status and progress events to Redis."""
        try:
            event_data = {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "meeting_id": str(meeting_id),
                "timestamp": datetime.utcnow().isoformat(),
                "payload": payload,
            }
            channel = f"events:meetings:{str(meeting_id)}:chunks"
            await self.event_bus.publish(channel, event_data)
        except Exception as ex:
            logger.debug(f"Redis chunk event emission warning ({event_type}): {ex}")
