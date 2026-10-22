"""REAL VAD component check on an existing short recording; no ASR/GPU inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    audio = Path(args.audio).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Evidence already exists; choose a new output before executing inference")
    evidence = {"run_id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
                "scope": "REAL speech-activity component only; no ASR, accuracy or E2E claim",
                "execution_mode": "REAL", "audio_file": str(audio),
                "meeting_id": "NOT AVAILABLE", "canonical_transcript_id": "NOT AVAILABLE"}
    evidence["status"] = "RUNNING"
    with output.open("x", encoding="utf-8") as destination:
        json.dump(evidence, destination, indent=2, ensure_ascii=False)
    try:
        from app.ai.multilingual_asr import validate_audio
        from app.ai.speech_frontend import SpeechFrontend
        from app.core.config import get_settings
        info = validate_audio(str(audio))
        if info["duration"] > 30:
            raise ValueError("This component check is limited to existing recordings of at most 30 seconds")
        before = hashlib.sha256(audio.read_bytes()).hexdigest()
        settings = get_settings().model_copy(update={"EXECUTION_MODE": "REAL", "AUDIO_VAD_MODE": "observe",
                                                     "AUDIO_VAD_MODEL_PATH": str(Path(args.model).resolve())})
        result = SpeechFrontend(settings).analyze(str(audio))
        after = hashlib.sha256(audio.read_bytes()).hexdigest()
        if before != after:
            raise RuntimeError("Source audio changed during component validation")
        evidence.update(status="COMPLETED", audio_sha256=before, audio_metadata=info,
                        source_unchanged=True, speech_activity=result,
                        accuracy="NOT VERIFIED", asr_inference="NOT EXECUTED")
    except Exception as exc:
        evidence.update(status="BLOCKED", error_type=type(exc).__name__, reason=str(exc))
    temporary = output.with_name(output.stem + "_" + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as destination:
        json.dump(evidence, destination, indent=2, ensure_ascii=False)
    temporary.replace(output)
    print(json.dumps({"status": evidence["status"], "run_id": evidence["run_id"],
                      "speech_detected": evidence.get("speech_activity", {}).get("speech_detected"),
                      "evidence": str(output)}))
    return 0 if evidence["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
