"""
Comprehensive Integration Tests for Phase 4.26 — Real Chunked AI Pipeline.
Tests:
- Chunk planning and interval calculations
- Slicing WAV audio files into overlapping chunk windows
- Global timestamp offset reconstruction
- Cross-chunk speaker reconciliation and global speaker tracking
- Boundary-aware overlap deduplication and seamless transcript merging
- State tracking and resumption
- Real and Fixture pipeline integration via MultilingualASREngine
"""

import asyncio
import os
import tempfile
import uuid
import wave
import pytest

from app.ai.long_audio_processor import (
    LongAudioProcessor,
    ChunkMetadata,
    ChunkProcessingState,
)
from app.ai.multilingual_asr import (
    ASRSegment,
    ASRWordTimestamp,
    MultilingualASREngine,
)


def create_synthetic_wav(path: str, duration_seconds: float, sample_rate: int = 16000) -> None:
    """Helper to generate a valid synthetic WAV file with dummy PCM samples."""
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Write silence / low-amplitude bytes
        wf.writeframes(b"\x00\x00" * num_frames)


class TestLongAudioProcessorPlanning:
    """Tests chunk planning mathematics and edge case handling."""

    def test_plan_chunks_single_chunk(self):
        processor = LongAudioProcessor(chunk_duration=600.0, overlap_duration=30.0)
        chunks = processor.plan_chunks(total_duration=350.0)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
        assert chunks[0].start_time == 0.0
        assert chunks[0].end_time == 350.0
        assert chunks[0].overlap_start_seconds == 0.0
        assert chunks[0].overlap_end_seconds == 0.0

    def test_plan_chunks_multi_chunk_exact(self):
        # 1000s duration with 600s chunk and 30s overlap -> step = 570s
        # Chunk 0: [0.0, 600.0]
        # Chunk 1: [570.0, 1000.0]
        processor = LongAudioProcessor(chunk_duration=600.0, overlap_duration=30.0)
        chunks = processor.plan_chunks(total_duration=1000.0)
        assert len(chunks) == 2
        assert chunks[0].start_time == 0.0
        assert chunks[0].end_time == 600.0
        assert chunks[0].overlap_start_seconds == 0.0
        assert chunks[0].overlap_end_seconds == 30.0

        assert chunks[1].start_time == 570.0
        assert chunks[1].end_time == 1000.0
        assert chunks[1].overlap_start_seconds == 30.0
        assert chunks[1].overlap_end_seconds == 0.0

    def test_plan_chunks_long_meeting_two_hours(self):
        # 7200s (2 hours) with 600s chunks and 30s overlap
        processor = LongAudioProcessor(chunk_duration=600.0, overlap_duration=30.0)
        chunks = processor.plan_chunks(total_duration=7200.0)
        assert len(chunks) >= 12
        # First chunk starts at 0
        assert chunks[0].start_time == 0.0
        # Last chunk ends at 7200
        assert chunks[-1].end_time == 7200.0
        # All consecutive chunks overlap by 30 seconds
        for i in range(len(chunks) - 1):
            assert round(chunks[i].end_time - chunks[i + 1].start_time, 2) == 30.0

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError, match="strictly less than"):
            LongAudioProcessor(chunk_duration=60.0, overlap_duration=60.0)


class TestLongAudioProcessorSlicing:
    """Tests audio file slicing into chunk files."""

    def test_slice_audio_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_wav = os.path.join(tmpdir, "long_meeting.wav")
            create_synthetic_wav(src_wav, duration_seconds=60.0)

            processor = LongAudioProcessor(chunk_duration=30.0, overlap_duration=5.0)
            chunk = ChunkMetadata(
                chunk_index=0,
                total_chunks=2,
                start_time=0.0,
                end_time=30.0,
                duration=30.0,
            )

            sliced_path = processor.slice_audio_file(src_wav, chunk, output_dir=tmpdir)
            assert os.path.exists(sliced_path)

            with wave.open(sliced_path, "rb") as wf:
                dur = wf.getnframes() / wf.getframerate()
                assert abs(dur - 30.0) < 0.1


class TestGlobalTimestampReconstruction:
    """Tests offsetting local segment & word timestamps to global meeting time."""

    def test_offset_segments_to_global_time(self):
        local_segments = [
            ASRSegment(
                segment_id=uuid.uuid4(),
                speaker_id="Speaker 1",
                start_time=1.0,
                end_time=4.5,
                transcript="Action items for Q3.",
                words=[
                    ASRWordTimestamp(word="Action", start_time=1.0, end_time=2.0, confidence=0.95),
                    ASRWordTimestamp(word="items", start_time=2.0, end_time=3.0, confidence=0.95),
                    ASRWordTimestamp(word="for", start_time=3.0, end_time=3.5, confidence=0.95),
                    ASRWordTimestamp(word="Q3.", start_time=3.5, end_time=4.5, confidence=0.95),
                ],
            )
        ]

        chunk_start = 570.0
        global_segments = LongAudioProcessor.offset_segments_to_global_time(
            segments=local_segments,
            chunk_start_time=chunk_start,
        )

        assert len(global_segments) == 1
        seg = global_segments[0]
        assert seg.start_time == 571.0
        assert seg.end_time == 574.5
        assert seg.words[0].start_time == 571.0
        assert seg.words[0].end_time == 572.0
        assert seg.words[-1].end_time == 574.5


class TestSpeakerReconciliation:
    """Tests matching local speaker IDs across chunks to unified global IDs."""

    def test_reconcile_speakers_across_chunks(self):
        processor = LongAudioProcessor(chunk_duration=100.0, overlap_duration=20.0)

        # Chunk 0: [0, 100]
        meta_0 = ChunkMetadata(
            chunk_index=0, total_chunks=2, start_time=0.0, end_time=100.0, duration=100.0
        )
        # Speaker A speaks from 85 to 95 (inside overlap window [80, 100])
        chunk0_segments = [
            ASRSegment(
                speaker_id="Speaker 1",
                start_time=10.0,
                end_time=30.0,
                transcript="Initial discussion.",
            ),
            ASRSegment(
                speaker_id="Speaker 2",
                start_time=85.0,
                end_time=95.0,
                transcript="Wrapping up first hour.",
            ),
        ]

        # Chunk 1: [80, 180]
        meta_1 = ChunkMetadata(
            chunk_index=1, total_chunks=2, start_time=80.0, end_time=180.0, duration=100.0
        )
        # In chunk 1, "Speaker X" speaks from 86 to 94 (overlaps with "Speaker 2")
        chunk1_segments = [
            ASRSegment(
                speaker_id="Speaker X",
                start_time=86.0,
                end_time=94.0,
                transcript="Wrapping up first hour.",
            ),
            ASRSegment(
                speaker_id="Speaker Y",
                start_time=120.0,
                end_time=140.0,
                transcript="Starting second agenda.",
            ),
        ]

        chunk_results = [
            (meta_0, chunk0_segments),
            (meta_1, chunk1_segments),
        ]

        reconciled, spk_map = processor.reconcile_speakers_across_chunks(chunk_results)

        assert len(reconciled) == 2
        # Chunk 0 speakers mapped to SPEAKER_00 and SPEAKER_01
        c0_spks = [s.speaker_id for s in reconciled[0]]
        assert c0_spks[0] == "SPEAKER_00"
        assert c0_spks[1] == "SPEAKER_01"

        # In Chunk 1, "Speaker X" overlaps with "Speaker 2" (SPEAKER_01) -> mapped to SPEAKER_01
        c1_spks = [s.speaker_id for s in reconciled[1]]
        assert c1_spks[0] == "SPEAKER_01"
        # "Speaker Y" is a new speaker -> mapped to SPEAKER_02
        assert c1_spks[1] == "SPEAKER_02"


class TestBoundaryDeduplication:
    """Tests removing repeated phrases across chunk overlaps."""

    def test_merge_and_deduplicate_chunks(self):
        processor = LongAudioProcessor(chunk_duration=100.0, overlap_duration=20.0)

        meta_0 = ChunkMetadata(
            chunk_index=0, total_chunks=2, start_time=0.0, end_time=100.0, duration=100.0
        )
        meta_1 = ChunkMetadata(
            chunk_index=1, total_chunks=2, start_time=80.0, end_time=180.0, duration=100.0
        )

        # Overlap window is [80, 100]
        # Chunk 0 has a segment at [82, 88] and [92, 98]
        c0_segs = [
            ASRSegment(
                speaker_id="SPEAKER_00",
                start_time=10.0,
                end_time=20.0,
                transcript="Welcome to our sync.",
            ),
            ASRSegment(
                speaker_id="SPEAKER_01",
                start_time=82.0,
                end_time=88.0,
                transcript="Let us review the deliverables.",
            ),
            ASRSegment(
                speaker_id="SPEAKER_01",
                start_time=92.0,
                end_time=98.0,
                transcript="Everything looks on track for delivery.",
            ),
        ]

        # Chunk 1 transcribes the overlap region as well:
        # [82.5, 88.2] duplicate of "Let us review the deliverables."
        # [92.1, 98.0] duplicate of "Everything looks on track for delivery."
        # [110.0, 120.0] unique segment in chunk 1
        c1_segs = [
            ASRSegment(
                speaker_id="SPEAKER_01",
                start_time=82.5,
                end_time=88.2,
                transcript="Let us review the deliverables.",
            ),
            ASRSegment(
                speaker_id="SPEAKER_01",
                start_time=92.1,
                end_time=98.0,
                transcript="Everything looks on track for delivery.",
            ),
            ASRSegment(
                speaker_id="SPEAKER_02",
                start_time=110.0,
                end_time=120.0,
                transcript="Moving to the next topic.",
            ),
        ]

        merged, dedup_count = processor.merge_and_deduplicate_chunks(
            chunk_metas=[meta_0, meta_1],
            reconciled_chunks=[c0_segs, c1_segs],
        )

        # Merged transcript should not duplicate the sentences
        transcripts = [s.transcript for s in merged]
        assert transcripts.count("Let us review the deliverables.") == 1
        assert transcripts.count("Moving to the next topic.") == 1
        assert dedup_count >= 1

        # Check temporal monotonicity
        for i in range(len(merged) - 1):
            assert merged[i].start_time <= merged[i + 1].start_time


@pytest.mark.asyncio
class TestFullLongAudioPipeline:
    """Tests end-to-end processing of long audio via MultilingualASREngine."""

    async def test_transcribe_audio_force_chunked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "synthetic_long.wav")
            create_synthetic_wav(audio_path, duration_seconds=45.0)

            with open(audio_path, "rb") as f:
                payload = f.read()

            engine = MultilingualASREngine()
            meeting_id = uuid.uuid4()

            # Execute with forced chunking: 20s chunks, 5s overlap
            # 45s audio -> chunks [0, 20], [15, 35], [30, 45] -> 3 chunks
            result = await engine.transcribe_audio(
                audio_payload=payload,
                meeting_id=meeting_id,
                target_languages=["en"],
                use_fixture=True,
                force_chunked=True,
                chunk_duration=20.0,
                overlap_duration=5.0,
            )

            assert result.meeting_id == meeting_id
            assert result.metadata.get("is_chunked") is True
            assert result.metadata.get("total_chunks") == 3
            assert len(result.segments) > 0
            assert len(result.full_transcript) > 0

            # Verify global timestamps span across the full 45s range
            max_end = max(s.end_time for s in result.segments)
            assert max_end > 30.0

            # Verify speakers are properly formatted
            for s in result.segments:
                assert s.speaker_id.startswith("SPEAKER_")
