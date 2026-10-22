# Architecture implementation and accuracy gates

Updated 2026-10-20. The initial `MODELS_AND_ALGORITHMS.md` is design intent,
not evidence that its listed algorithms or benchmark numbers were achieved.

## Implemented in this step: bounded pre-ASR speech activity

`backend/app/ai/speech_frontend.py` analyzes each original bounded batch chunk
before transcription and short MOSS inputs before model loading. Local Silero
TorchScript only: no runtime network requests and no energy-only fallback.
Model SHA-256, policy, threshold and collar are bound to resume identity.
Chunk state stores actual speech intervals and measured energy/entropy/timing;
completed no-speech chunks remain checkpointed and do not compress the clock.

- `AUDIO_VAD_MODE=off`: compatibility default; neural inference NOT performed.
- `observe`: measure activity, still transcribe every original window.
- `filter`: skip only whole windows with no neural speech frames. Speech-containing
  windows retain all original samples and internal silence; no word onsets cut.
- `AUDIO_VAD_MODEL_PATH`: existing local `silero_vad.jit`; missing artifact fails
  explicitly when enabled. `backend/scripts/provision_silero_vad.py` separately
  provisions only the missing official artifact, bounded to 4 MiB and checked
  against its Git blob. Weights are not committed to source control.
- Default neural probability threshold 0.5, padded collar 0.25 seconds.
  These are initial policy settings, NOT calibrated accuracy guarantees.
- Energy/entropy are diagnostic only: the design specifies no calibrated energy
  threshold, so a guessed threshold must not discard quiet speech.
- Modern Silero uses 512 samples at 16 kHz (32 ms). The document's generic 20 ms
  neural framing is not its supported interface. Recurrent state resets at each
  independent window and is protected from concurrent calls.
- An entirely no-speech recording must not be reported as a successful transcript.
- Live ASR retains its existing window path; this is not continuous streaming VAD.

Official interface: https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py

## Remaining architecture work, in accuracy dependency order

1. Validate `observe` on short multilingual/noise/quiet-speech recordings, then
   compare `filter` with the unchanged baseline. VAD can reduce non-speech
   hallucinations; it cannot fix MOSS recognition of actual speech by itself.
2. Validate longer bounded speech contexts and overlap reconstruction. Existing
   8s/3s versus single-context evidence shows a boundary failure; do not certify
   a larger context or change all runtime settings without a controlled pilot.
3. Preserve PyAnnote as the actual diarizer and calibrate cross-window matching
   against genuine speaker annotation. EEND/ECAPA is a separate unimplemented
   model integration, not a flag to relabel the existing PyAnnote outputs.
4. Independent forced alignment requires an appropriate cached acoustic alignment
   model and language coverage. MOSS turn times are not forced word alignment.
   No inferred word timestamps or claimed 42 ms error.
5. Overlap separation needs an actual separation model and its validation.
   Intersection detection does not constitute separated audio or PIT training.
6. Sarvam text translation, tokenizer behavior and keyword heuristics must not
   be presented as acoustic LID or automatic correction of canonical speech.
7. Calibrated semantic confidence, true RRF/lexical retrieval, alternative embedding
   models and cryptographic audit chaining are separate gates. They do not repair
   ASR words; model/schema changes need migration and retrieval checks.

Keep native MOSS processor/tagged output format. MOSS is not Conformer CTC;
implementing a CTC loss in its inference wrapper would be an incompatible rewrite.
No asserted WER/DER/JER/LID/latency/hallucination target is an achieved result until
measured on held-out real data using the actual selected configuration.

## 2026-10-20 — Evidence before additional accuracy modules

Saved-output evaluation is available at
`benchmark results/research_reuse_20261020/evaluation_04/REPORT.md`.
It uses 39 saved attempts on 25 distinct recordings, with no new audio inference.
The ten historical English FLEURS clips have corpus WER 15.57% and CER 12.61%.
Other languages/configurations remain separate. Existing IndicSUPERB ASR samples
are Kathbath recordings and must not count as a second independent dataset.

The cached MOSS config identifies `MossTranscribeDiarizeForConditionalGeneration`
with a Qwen3 text configuration. Its native processor/tagged-output contract
must remain intact; a Conformer CTC wrapper would not implement this model.
The inspected local model cache contains MOSS, Whisper, Sarvam, PyAnnote
segmentation/diarization, WeSpeaker and MiniLM; no independent separation or
language-specific forced-alignment model was found in that inventory.

Integration decisions:

- Keep existing Silero integration in observation mode until quiet-speech and
  no-speech safety checks support filtering. Do not discard words on an
  uncalibrated energy threshold.
- Retain actual acoustic speaker reconciliation. Calibrate unresolved matches on
  development recordings separately from the final benchmark; do not force the
  reference speaker count into inference or interpret an unresolved bucket as a
  verified person.
- Add an independent aligner only with validated language-specific acoustic
  artifacts. It can refine word timing, not repair incorrect recognized words.
- Add separation only with a real compatible model and short overlap controls
  establishing improved words/speaker attribution without duplicated speech.
  PIT is a training objective, not an inference-time toggle.
- Keep canonical speech verbatim; translation, summaries and readability edits
  cannot serve as ground truth or replace acoustic recognition.

No new ASR/diarization/separation model was integrated during this scoring step.
No improvement from those proposed modules is claimed. The added standard
DER/JER evaluator unions SAME-label activity intervals before scoring, preserves
different-speaker overlap, uses actual audio UEM, and flags unresolved labels.
This is evaluation correctness, not a change to the production transcript.
