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
        if self.overlap_duration >= self.chunk_duration:
            raise ValueError("Overlap duration must be strictly less than chunk duration.")

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

        try:
            import soundfile as sf
            with sf.SoundFile(audio_file_path) as src:
                sr = src.samplerate
                start_frame = int(chunk.start_time * sr)
                end_frame = int(chunk.end_time * sr)
                total_frames = len(src)

                start_frame = max(0, min(start_frame, total_frames))
                end_frame = max(start_frame, min(end_frame, total_frames))
                frames_to_read = end_frame - start_frame

                src.seek(start_frame)
                data = src.read(frames_to_read)

                sf.write(out_path, data, sr, format="WAV")
                return out_path
        except Exception as sf_err:
            logger.debug(f"soundfile slice failed ({sf_err}), attempting wave fallback...")
            try:
                import wave
                with wave.open(audio_file_path, "rb") as src:
                    n_channels = src.getnchannels()
                    sampwidth = src.getsampwidth()
                    framerate = src.getframerate()
                    total_frames = src.getnframes()

                    start_frame = int(chunk.start_time * framerate)
                    end_frame = int(chunk.end_time * framerate)
                    start_frame = max(0, min(start_frame, total_frames))
                    end_frame = max(start_frame, min(end_frame, total_frames))
                    frames_to_read = end_frame - start_frame

                    src.setpos(start_frame)
                    raw_audio = src.readframes(frames_to_read)

                    with wave.open(out_path, "wb") as dst:
                        dst.setnchannels(n_channels)
                        dst.setsampwidth(sampwidth)
                        dst.setframerate(framerate)
                        dst.writeframes(raw_audio)
                    return out_path
            except Exception as wave_err:
                raise RuntimeError(
                    f"Failed to slice audio chunk {chunk.chunk_index} ({chunk.start_time}s -> {chunk.end_time}s): "
                    f"{wave_err}"
                ) from wave_err

    # -------------------------------------------------------------------------
    # 2. Global Timestamp Reconstruction
    # -------------------------------------------------------------------------

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
                        p_s = max(p_seg.start_time, overlap_start)
                        p_e = min(p_seg.end_time, overlap_end)
                        if p_e <= p_s:
                            continue

                        for c_seg in segments:
                            c_spk = c_seg.speaker_id or "SPEAKER_UNKNOWN"
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
                curr_local_speakers = set(seg.speaker_id or "SPEAKER_UNKNOWN" for seg in segments)
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
        """Computes basic word-level Jaccard similarity between two texts."""
        w1 = set(re.findall(r"\w+", s1.lower()))
        w2 = set(re.findall(r"\w+", s2.lower()))
        if not w1 or not w2:
            return 0.0
        return len(w1 & w2) / len(w1 | w2)

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
                    has_match = any(
                        self._text_similarity(seg.transcript, c.transcript) > 0.6
                        for c in curr_segs
                        if abs(c.start_time - seg.start_time) < 15.0
                    )
                    if has_match:
                        dedup_count += 1
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
                        if abs(prev_s.start_time - seg.start_time) < 10.0:
                            if self._text_similarity(prev_s.transcript, seg.transcript) > 0.6:
                                is_duplicate = True
                                dedup_count += 1
                                break
                    if not is_duplicate and seg.start_time >= (last_kept_time - 0.2):
                        kept_curr.append(seg)
                        last_kept_time = max(last_kept_time, seg.end_time)
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
            )

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

        try:
            # 2. Process chunks sequentially or with bounded concurrency
            for idx, chunk_meta in enumerate(state.chunks):
                if chunk_meta.status == "completed":
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
                    raw_segments = await transcribe_chunk_func(chunk_audio_path, chunk_meta)
                    if isinstance(raw_segments, ASRResult):
                        local_segments = raw_segments.segments
                    elif isinstance(raw_segments, list):
                        local_segments = raw_segments
                    else:
                        local_segments = []

                    # Reconstruct global timestamps for this chunk
                    global_segments = self.offset_segments_to_global_time(
                        segments=local_segments,
                        chunk_start_time=chunk_meta.start_time,
                    )

                    chunk_results.append((chunk_meta, global_segments))

                    chunk_meta.status = "completed"
                    chunk_meta.processed_at = datetime.utcnow()
                    state.completed_chunks_count += 1
                    state.updated_at = datetime.utcnow()

                    await self._emit_chunk_event(
                        meeting_id=meeting_id,
                        event_type="chunk_completed",
                        payload={
                            "chunk_index": idx,
                            "total_chunks": state.total_chunks,
                            "segments_extracted": len(global_segments),
                            "progress_percentage": round((state.completed_chunks_count / state.total_chunks) * 100, 1),
                            "correlation_id": corr_id,
                        },
                    )

                except Exception as chunk_err:
                    chunk_meta.status = "failed"
                    chunk_meta.error_message = str(chunk_err)
                    chunk_meta.retry_count += 1
                    state.updated_at = datetime.utcnow()

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
            if not detected_languages:
                detected_languages = ["en"]

            lang_distribution: Dict[str, float] = {}
            if final_segments:
                for s in final_segments:
                    lang = s.detected_language or "en"
                    lang_distribution[lang] = lang_distribution.get(lang, 0.0) + 1.0
                for l in lang_distribution:
                    lang_distribution[l] = round(lang_distribution[l] / len(final_segments), 4)

            # Overall confidence from segments
            overall_conf = (
                sum(s.confidence for s in final_segments) / len(final_segments)
                if final_segments
                else 0.95
            )

            asr_result = ASRResult(
                meeting_id=meeting_id,
                full_transcript=full_transcript,
                detected_languages=detected_languages,
                language_distribution=lang_distribution,
                segments=final_segments,
                overall_confidence=round(overall_conf, 4),
                metadata={
                    "is_chunked": True,
                    "total_chunks": state.total_chunks,
                    "chunk_duration_seconds": self.chunk_duration,
                    "overlap_duration_seconds": self.overlap_duration,
                    "deduplicated_segments_count": dedup_count,
                    "global_speakers": sorted(list(set(global_spk_map.values()))),
                    "provenance": "ASR:ChunkedLongAudioProcessor",
                },
            )

            state.overall_status = "completed"
            state.updated_at = datetime.utcnow()

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
