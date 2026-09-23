# ABCI-MI End-to-End Validation

## Preconditions

- Apply migrations: `alembic upgrade head`
- Use a CUDA GPU with enough VRAM for the selected model configuration.
- Accept access to `OpenMOSS-Team/MOSS-Transcribe-Diarize` and `pyannote/speaker-diarization-3.1`.
- Set `HF_TOKEN` in the environment. Do not commit tokens or `.env` files.
- Ensure PostgreSQL, Redis, and Qdrant are reachable.

The validator does not modify `.env`; it sets `EXECUTION_MODE=REAL` only for its child processes.

## Run once

From `backend/`:

```powershell
python scripts/run_e2e_validation.py `
  "..\data\audio\raw\ES2004a.Mix-Headset.wav" `
  --output-dir "..\e2e_validation" `
  --chunk-seconds 300 `
  --overlap-seconds 15
```

For a 4 GB GPU, use `--chunk-seconds 60 --overlap-seconds 5`. For a confirmed 24 GB GPU, start with 300 seconds and increase to 600 seconds only after the first run succeeds.

## Outputs

- `e2e_validation/real_mode_check.log`: dependency, CUDA, and model readiness.
- `e2e_validation/pipeline.log`: complete CLI output.
- `e2e_validation/result.json`: meeting/report IDs, status, segment/speaker counts, and exit code.

A run is successful only when the result status is `passed` and the pipeline summary reports `completed`. A persisted report with zero segments is a failed upstream inference run, not a successful E2E result.

## Fine-tuning policy

Run a baseline first and compare against dataset references. Fine-tune only the component whose measured metric misses its target:

- ASR: use `backend/scripts/train_whisper_sarvam.py` with an AISHELL, AMI, or YODAS2 manifest.
- Diarization: evaluate generated RTTM against VoxConverse/AMI references before changing model weights.
- Indic normalization: prepare a code-switched JSONL manifest before Sarvam LoRA training.

Do not train on the same evaluation recordings used for the final validation score.
