# Explicit cached Whisper batch candidate

Status: implemented locally; CUDA inference, end-to-end publication and accuracy NOT VERIFIED for this provider. Existing batch default and live provider remain MOSS. No automatic provider/CPU fallback.

## Enable only for a controlled GPU comparison

Keep existing database, Redis, Qdrant, authentication and model-cache settings. In the selected deployment backend/.env, explicitly set:

```dotenv
EXECUTION_MODE=REAL
BATCH_ASR_PROVIDER=whisper
WHISPER_MODEL_ID=openai/whisper-large-v3
WHISPER_PRECISION=fp16
WHISPER_CHUNK_DURATION_SECONDS=25
WHISPER_CHUNK_OVERLAP_SECONDS=5
WHISPER_WORKER_CUDA_BUDGET_MB=8192
REAL_ALLOW_UNVERIFIED_RESOURCE_PROFILE=true
```

Use the existing CUDA device setting OPENMOSS_DEVICE (e.g. cuda:0). Restart the batch worker after a provider change; do not change providers while a job is running. Live MOSS inference remains independent. The 8192 MiB CUDA budget is an explicit unmeasured admission budget, not measured peak memory or a support guarantee; RAM estimates also require fresh telemetry.

Reuse the existing F:/hf-cache/hub/models--openai--whisper-large-v3 snapshot, tokenizer and processor. Remote deployments must copy this existing cache to their configured HF cache first; this adapter never downloads a replacement. Missing snapshot, CUDA, timestamps or malformed output causes an explicit failure. Do not enable this candidate on the paused instance until it is reachable and the cache is copied.

The existing production chunk planner uses 25s windows, 5s overlap, 20s step, bounded reads, checkpointing, timestamp reconstruction and deduplication. Parser preserves actual model word timings (including zero-duration words), rejects missing/out-of-bounds/out-of-order timestamps and rejects disagreement between text and word records. It does not manufacture speaker identity, detected-language scores or confidence. PyAnnote remains the speaker path. Overlap transcription and complete recovery of every spoken word are NOT guaranteed.

For the existing benchmark CLI, use the exact configured HF model ID and configured CUDA device. Nonmatching model/provider/device fails explicitly. Whisper-only benchmarks have no speaker turns: DER/JER are unavailable, not zero. This is an ASR component benchmark, not production end-to-end evidence. Never pool these results with earlier MOSS results.

## Next validation

Retrieve the pending Bengali native-language-hint pilot before repeating samples. Then compare MOSS and this candidate on identical held-out FLEURS recordings with script-consistent references, separate run IDs and raw outputs. Measure errors and timing before choosing the default. Follow with a small production meeting, PostgreSQL fresh-process readback and existing CLI/API output. Do not rerun BIVA or claim improved WER/DER from code checks. The paused GPU is the remaining external execution dependency.
