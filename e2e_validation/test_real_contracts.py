"""Cheap engineering checks; these do not establish REAL inference success."""
import inspect
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.model_inventory import ModelSpec, inspect_snapshot
from app.ai.multilingual_asr import OpenMOSSProvider
from app.ai.long_audio_processor import LongAudioProcessor


def test_official_audio_argument():
    from moss_transcribe_diarize.inference_utils import build_transcription_messages, generate_transcription
    assert "audio_path" in inspect.signature(build_transcription_messages).parameters
    assert "messages" in inspect.signature(generate_transcription).parameters


def test_recorded_real_output_preserves_unknowns_and_offsets():
    import pytest
    raw = (Path(__file__).parent / "local_real_20260930" / "raw_moss.txt").read_text(encoding="utf-8")
    segments = OpenMOSSProvider()._parse_moss_output(raw)
    assert segments
    shifted = LongAudioProcessor().offset_segments_to_global_time(segments, 71)
    for original, global_segment in zip(segments, shifted):
        assert original.confidence is None
        assert original.detected_language is None
        assert not original.words
        assert global_segment.start_time == pytest.approx(71 + original.start_time)
        assert global_segment.end_time == pytest.approx(71 + original.end_time)
        assert global_segment.metadata == original.metadata


def test_incomplete_shard_is_blocked(tmp_path):
    # Cache metadata only, no synthetic audio or inference.
    spec = ModelSpec("check", "check/model", "test", "test", ("config.json",))
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "one.safetensors").write_bytes(b"metadata check only")
    (tmp_path / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"a": "one.safetensors", "b": "missing.safetensors"}}))
    result = inspect_snapshot(spec, tmp_path)
    assert result["status"] == "INCOMPLETE"
    assert result["missing_shards"] == ["missing.safetensors"]


def test_empty_output_fails_explicitly():
    import pytest
    with pytest.raises(ValueError, match="empty output"):
        OpenMOSSProvider()._parse_moss_output("")


def test_recorded_real_bounds_never_retimed():
    raw_path = next((Path(__file__).parent / "real_local").glob("ES2014a.Mix-Headset_71_10_*/moss_raw.txt"))
    parsed = OpenMOSSProvider()._parse_moss_output(raw_path.read_text(encoding="utf-8"))
    valid, rejected = OpenMOSSProvider._validate_audio_bounds(parsed, 10)
    assert valid and rejected
    assert all(s.end_time <= 10 and s.start_time < 10 for s in valid)
    assert all(s.model_dump() in [p.model_dump() for p in parsed] for s in valid)
