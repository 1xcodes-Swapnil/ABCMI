"""Staged REAL validation through the existing ABCI-MI AI adapters.

Artifacts are evidence, never fixture inputs to the production transcription path.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
import uuid

from app.core.config import get_settings


def write(path: Path, data):
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def evidence_directory(audio: Path, start: float, duration: float, base: Path) -> Path:
    fingerprint = hashlib.sha256(audio.read_bytes()).hexdigest()
    destination = base / f"{audio.stem}_{start:g}_{duration:g}_{fingerprint[:12]}"
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "input.json", {"file": audio.name, "sha256": fingerprint,
        "start_seconds": start, "duration_seconds": duration, "execution_mode": "REAL"})
    return destination


def extract_audio(audio: Path, start: float, duration: float, destination: Path):
    from app.ai.long_audio_processor import LongAudioProcessor, ChunkMetadata
    from app.ai.multilingual_asr import validate_audio
    metadata = validate_audio(str(audio))
    if start < 0 or duration <= 0 or start + duration > metadata["duration"]:
        raise ValueError("Requested real audio interval is outside the source recording")
    chunk = ChunkMetadata(chunk_index=0, total_chunks=1, start_time=start, end_time=start+duration, duration=duration)
    path = destination / "real_excerpt.wav"
    if not path.is_file():
        generated = Path(LongAudioProcessor().slice_audio_file(str(audio), chunk, str(destination)))
        generated.replace(path)
    excerpt = validate_audio(str(path))
    if abs(excerpt["duration"] - duration) > 1/excerpt["sample_rate"]:
        raise ValueError("Existing real excerpt duration differs from requested interval")
    return path, chunk, excerpt


async def moss(path, chunk, metadata, destination, trace):
    import torch
    from app.ai.multilingual_asr import OpenMOSSProvider
    settings = get_settings()
    provider = OpenMOSSProvider({"model_id": settings.OPENMOSS_MODEL_ID, "device": settings.OPENMOSS_DEVICE,
        "cache_dir": settings.OPENMOSS_CACHE_DIR, "token": settings.HF_TOKEN})
    started = time.perf_counter()
    provider._load_model()
    trace.update(model_loaded=True, processor_loaded=True, model_load_seconds=time.perf_counter()-started,
        parameter_devices=sorted({str(p.device) for p in provider.model.parameters()}),
        quantized_4bit=bool(getattr(provider.model, "is_loaded_in_4bit", False)))
    torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
    try:
        segments = await provider.transcribe(str(path), {"chunk_meta": chunk})
    finally:
        trace.update(provider.last_inference)
        if provider.last_raw_output is not None:
            (destination / "moss_raw.txt").write_text(provider.last_raw_output, encoding="utf-8")
            trace.update(moss_called=True, generation_completed=True, raw_output_exists=bool(provider.last_raw_output))
        if torch.cuda.is_available():
            trace["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
    trace.update(parsed_segments=len(segments), model_timestamps_present=bool(segments),
        out_of_window_segments=sum(s.end_time > metadata["duration"] or s.start_time >= metadata["duration"] for s in segments),
        confidence_verification="NOT_VERIFIED", language_verification="NOT_VERIFIED")
    write(destination / "moss_segments.json", [s.model_dump(mode="json") for s in segments])
    assert segments, "REAL MOSS parsed no segments"
    assert trace["out_of_window_segments"] == 0, "REAL MOSS returned out-of-window segments"


async def pyannote(path, destination, trace):
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    result = await SpeakerDiarizationEngine().diarize_audio(path.read_bytes(), uuid.uuid4())
    trace.update(result.metadata)
    trace.update(pipeline_loaded=True, pyannote_called=True, speaker_turns=len(result.speaker_turns),
        speakers=result.num_speakers, embeddings_real=bool(result.voiceprints),
        embedding_dimensions=[len(v.embedding_vector) for v in result.voiceprints], confidence_verification="NOT_VERIFIED")
    write(destination / "pyannote_result.json", result.model_dump(mode="json"))
    assert result.speaker_turns, "REAL PyAnnote returned no speaker turns"


async def sarvam(destination, trace):
    from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
    from app.ai.multilingual_asr import ASRSegment
    from app.ai.model_inventory import inspect_snapshot, snapshot_for, cache_directory, MODELS
    prior = json.loads((destination / "moss.json").read_text())
    if prior["status"] != "passed":
        raise ValueError("Sarvam validation requires successful REAL MOSS audio transcription")
    segments = [ASRSegment.model_validate(s) for s in json.loads((destination / "moss_segments.json").read_text())]
    transcript = " ".join(s.transcript for s in segments)
    engine = CodeSwitchIntelligenceEngine()
    started = time.perf_counter()
    engine._load_sarvam_model()
    trace.update(model_loaded=True, model_load_seconds=time.perf_counter()-started,
        input_source="REAL MOSS transcription of local audio", model="sarvamai/sarvam-1")
    output = await engine.map_to_canonical(transcript)
    trace.update(engine.last_inference)
    write(destination / "sarvam_output.json", {"input": transcript, "output": output,
        "model": "sarvamai/sarvam-1", "confidence": None, "accuracy": "NOT_VERIFIED"})
    assert output.strip(), "REAL Sarvam generated no text"


async def chunked(path, destination, trace):
    from app.ai.multilingual_asr import MultilingualASREngine
    from app.ai.long_audio_processor import LongAudioProcessor
    prior = json.loads((destination/"production_meeting.json").read_text())
    if prior["status"] != "passed":
        raise ValueError("Chunked validation requires the passed production meeting")
    planner = LongAudioProcessor(chunk_duration=8, overlap_duration=3)
    chunks = planner.plan_chunks(trace["audio_duration"])
    trace.update(chunk_duration=8, overlap_seconds=3, step_seconds=5,
                 chunk_count=len(chunks), coverage=[(c.start_time, c.end_time) for c in chunks])
    result = await MultilingualASREngine().transcribe_audio(path.read_bytes(), uuid.uuid4(),
        force_chunked=True, chunk_duration=8, overlap_duration=3, use_fixture=False)
    write(destination/"chunked_result.json", result.model_dump(mode="json"))
    trace.update(final_segments=len(result.segments), inference=result.metadata["inference"],
        deduplicated_segments=result.metadata["deduplicated_segments_count"],
        global_speakers=result.metadata["global_speakers"], is_fixture=result.metadata["is_fixture"])
    assert result.segments and not result.metadata["is_fixture"]
    assert all(0 <= s.start_time < s.end_time <= trace["audio_duration"] for s in result.segments)
    assert [s.start_time for s in result.segments] == sorted(s.start_time for s in result.segments)


def reconciliation(chunk, metadata, destination, trace):
    from app.ai.multilingual_asr import ASRSegment
    from app.ai.speaker_diarization import SpeakerDiarizationEngine, DiarizationResult
    from app.ai.long_audio_processor import LongAudioProcessor
    for gate in ["moss", "pyannote", "sarvam"]:
        if json.loads((destination / (gate + ".json")).read_text())["status"] != "passed":
            raise ValueError(f"Reconciliation is gated on successful REAL {gate}")
    segments = [ASRSegment.model_validate(s) for s in json.loads((destination / "moss_segments.json").read_text())]
    diarization = DiarizationResult.model_validate(json.loads((destination / "pyannote_result.json").read_text()))
    report = SpeakerDiarizationEngine().verify_moss_with_pyannote(segments, diarization.speaker_turns)
    # This is inter-model agreement, not accuracy against ground truth.
    report["agreement_ratio"] = report.pop("accuracy", None)
    processor = LongAudioProcessor()
    global_segments = processor.offset_segments_to_global_time(segments, chunk.start_time)
    global_turns = [t.model_copy(update={"start_time": t.start_time+chunk.start_time,
                                      "end_time": t.end_time+chunk.start_time}) for t in diarization.speaker_turns]
    reconciled, mapping = processor.reconcile_speakers_across_chunks([(chunk, global_segments)])
    final, deduplicated = processor.merge_and_deduplicate_chunks([chunk], reconciled)
    classifications = []
    mapped = report["speaker_mapping"]
    for segment in global_segments:
        overlaps = [t for t in global_turns if min(t.end_time, segment.end_time) > max(t.start_time, segment.start_time)]
        if not overlaps:
            classification = "MOSS-ONLY"
        elif segment.speaker_id not in mapped:
            classification = "UNRESOLVED"
        elif all(t.speaker_id == mapped[segment.speaker_id] for t in overlaps):
            classification = "MOSS AGREES"
        else:
            classification = "MOSS DIFFERS"
        classifications.append(dict(start=segment.start_time, end=segment.end_time, speaker=segment.speaker_id,
                                    classification=classification))
    for turn in global_turns:
        if not any(min(turn.end_time, s.end_time) > max(turn.start_time, s.start_time) for s in global_segments):
            classifications.append(dict(start=turn.start_time, end=turn.end_time, speaker=turn.speaker_id,
                                        classification="PYANNOTE-ONLY"))
    write(destination / "reconciliation_result.json", {"comparison": report, "classifications": classifications,
        "chunk_speaker_mapping": mapping, "final_segments": [s.model_dump(mode="json") for s in final],
        "pyannote_global_turns": [t.model_dump(mode="json") for t in global_turns], "deduplicated_segments": deduplicated})
    trace.update(final_segments=len(final), offset_seconds=chunk.start_time, deduplicated_segments=deduplicated,
                 inter_model_agreement=report["agreement_ratio"], ground_truth_accuracy="NOT_VERIFIED")
    assert final and all(s.start_time >= 0 and s.end_time >= s.start_time for s in final)


def rttm_comparison(audio, chunk, destination, trace):
    prior = json.loads((destination / "reconcile.json").read_text())
    if prior["status"] != "passed":
        raise ValueError("RTTM comparison requires successful reconciliation")
    rttm = audio.with_name(audio.name.split(".")[0] + ".rttm")
    if not rttm.is_file():
        raise FileNotFoundError("Actual recording RTTM annotation is missing")
    reference = []
    for line in rttm.read_text().splitlines():
        fields = line.split()
        if fields and fields[0] == "SPEAKER" and len(fields) >= 8:
            start, duration = float(fields[3]), float(fields[4])
            if min(start + duration, chunk.end_time) > max(start, chunk.start_time):
                reference.append(dict(start_time=start, end_time=start+duration, speaker_id=fields[7]))
    if not reference:
        raise ValueError("Actual RTTM contains no annotations for the requested interval")
    actual = json.loads((destination / "reconciliation_result.json").read_text())
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    comparison = SpeakerDiarizationEngine().verify_moss_with_pyannote(actual["final_segments"], reference)
    comparison["agreement_ratio"] = comparison.pop("accuracy", None)
    errors, used_references = [], set()
    for segment in actual["final_segments"]:
        candidates = []
        for index, ref in enumerate(reference):
            if comparison["speaker_mapping"].get(segment["speaker_id"]) != ref["speaker_id"]:
                continue
            overlap = max(0, min(segment["end_time"], ref["end_time"]) - max(segment["start_time"], ref["start_time"]))
            union = max(segment["end_time"], ref["end_time"]) - min(segment["start_time"], ref["start_time"])
            if union > 0 and overlap / union >= 0.5:
                candidates.append((index, ref, overlap, overlap / union))
        # No forced segment splitting or matching a long segment to multiple reference turns.
        if len(candidates) == 1 and candidates[0][0] not in used_references:
            index, ref, overlap, iou = candidates[0]
            used_references.add(index)
            errors.append(dict(model_start=segment["start_time"], model_end=segment["end_time"],
                reference_start=ref["start_time"], reference_end=ref["end_time"], overlap=overlap, iou=iou,
                start_error=segment["start_time"]-ref["start_time"], end_error=segment["end_time"]-ref["end_time"]))
    write(destination / "rttm_result.json", {"reference_file": rttm.name, "comparison": comparison,
        "reference_turns": reference, "comparable_intervals": errors,
        "accuracy_scope": "Selected short interval only; no benchmark/general timestamp accuracy claim"})
    trace.update(reference_turns=len(reference), comparable_intervals=len(errors),
                 timestamp_accuracy="selected intervals only" if errors else "NOT_VERIFIED", benchmark="NOT_VERIFIED")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m backend.cli real-smoke")
    parser.add_argument("--stage", choices=["moss", "pyannote", "sarvam", "reconcile", "rttm", "chunked"], required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float, default=15)
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parents[3]/"e2e_validation/real_local")
    args = parser.parse_args(argv)
    if get_settings().EXECUTION_MODE.upper() != "REAL":
        raise RuntimeError("real-smoke requires EXECUTION_MODE=REAL")
    audio = args.audio.resolve()
    allowed = Path(__file__).resolve().parents[3]/"data/audio/raw"
    if not audio.is_file() or not audio.is_relative_to(allowed.resolve()):
        raise ValueError("REAL validation requires an existing audio file under data/audio/raw")
    from app.ai.model_inventory import configure_cache
    configure_cache()
    destination = evidence_directory(audio, args.start, args.duration, args.artifacts)
    trace = {"stage": args.stage, "execution_mode": "REAL", "status": "started", "input_audio_exists": True}
    started = time.perf_counter()
    try:
        path, chunk, metadata = extract_audio(audio, args.start, args.duration, destination)
        trace.update(audio_loaded=True, audio_duration=metadata["duration"], sample_rate=metadata["sample_rate"],
                     channels=metadata["channels"], chunk_count=1)
        if args.stage == "moss":
            asyncio.run(moss(path, chunk, metadata, destination, trace))
        elif args.stage == "pyannote":
            if json.loads((destination / "moss.json").read_text())["status"] != "passed":
                raise ValueError("PyAnnote smoke is gated on successful REAL MOSS inference")
            asyncio.run(pyannote(path, destination, trace))
        elif args.stage == "sarvam":
            asyncio.run(sarvam(destination, trace))
        elif args.stage == "reconcile":
            reconciliation(chunk, metadata, destination, trace)
        elif args.stage == "chunked":
            asyncio.run(chunked(path, destination, trace))
        else:
            rttm_comparison(audio, chunk, destination, trace)
        trace["status"] = "passed"
    except Exception as exc:
        from app.cli import sanitize_error_text
        trace.update(status="BLOCKED", error_type=type(exc).__name__, error=sanitize_error_text(str(exc)))
    trace["processing_seconds"] = time.perf_counter()-started
    trace["rtf"] = trace["processing_seconds"] / args.duration
    write(destination / (args.stage + ".json"), trace)
    print(json.dumps(trace, indent=2))
    return 0 if trace["status"] == "passed" else 1
