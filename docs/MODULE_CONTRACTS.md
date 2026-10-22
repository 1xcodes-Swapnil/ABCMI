# ABCI-MI module contracts and design assessment

Updated 2026-10-20. OpenMOSS remains the production default. Whisper is an optional comparison adapter, not an automatic fallback. These are implementation contracts, not measured accuracy guarantees.

## Boundary envelope

Every dispatched capability returns an object with `status=SUCCESS`, the requested `capability`, `result_data` as an object and `confidence_score` as a finite value in [0,1] or null. Dispatch adds actual task_id, meeting_id, request_id and correlation_id; supplied conflicting IDs are rejected. REAL envelopes must serialize as JSON without NaN/Infinity or Python UUID objects. Failure raises an exception and must not be recorded as a completed task. This is enforced in both AIModuleRunner and ACE before task completion.

Test confidence/error injection is forbidden in REAL. Missing confidence means unknown; a completed stage does not establish WER/DER, speaker identity accuracy or semantic correctness.

## Model-specific input/output formats

### OpenMOSS: acoustic transcription and local speaker turns

Use the installed official `build_transcription_messages` and `generate_transcription` helpers. The user message contains an audio content item and a text content item. The processor's own chat template is applied by the official helper, with actual `audio=audios`, matching processor sample rate and device/dtype. Do not substitute a generic ChatML prompt or request arbitrary JSON from this model.

The native turn grammar is `[start_seconds][S01] spoken words[end_seconds]`; turn labels may differ. Parse with the installed official `parse_transcript`, then validate actual audio bounds. Keep original language, raw generation, token count, timing and declared-language provenance. Model-local S01 is not a verified global person. Word timing, language confidence and recognition confidence must remain unavailable when not supplied. A token-limited/malformed generation is a failure, not an empty successful transcript. Recorded script inconsistency across overlapping windows is still an unresolved recognition issue; do not repair it by guessed transliteration or deleting coincident turns.

### PyAnnote: acoustic diarization

Use its existing Pipeline and audio adapter, not a text/chat template. Convert actual turn intervals to the existing SpeakerTurn/DiarizationResult schema. Include meeting_id, num_speakers, speaker_turns, voiceprints, overall_confidence and metadata. Global identity needs acoustic embedding reconciliation, overlap constraints and ambiguity handling. Do not equate window-local labels or provide benchmark speaker counts as oracle input. Model agreement with MOSS is not DER or identity accuracy.

### Sarvam-1: derived English text

The current adapter uses a base completion record `Original speech: <actual text>\nEnglish translation:` and generation-only decoding with an end-of-record stop. It is not a MOSS audio processor or an instruction/chat model. A generation that exhausts its token budget is rejected. Store original text and derived translation separately. The legacy name canonical_text in this module means a derived English representation; it must never replace the canonical original-language ASR transcript. Translation accuracy remains NOT_VERIFIED. Keyword language detection and dictionary substitution helpers are fixture-only; REAL cannot manufacture boundary confidence or default language labels.

### Gemini: optional meeting intelligence

Use the existing structured JSON schema in grounded_meeting_text.py and actual source turns. Require valid object types, segment citations and matching quotes. Keep draft status and unknown semantic accuracy. Exact quotes establish evidence links, not factual correctness of every generated claim. The separate queued intelligence path binds a persisted transcript ID and SHA before generation. Do not use an ASR prompt for summaries or let an LLM rewrite the authoritative transcript.

## Contracts for the 13 existing capabilities

| Capability | Input | Output and interpretation |
|---|---|---|
| audio_intelligence | Authorized stored audio | Actual positive duration_seconds, sample_rate, channels, meeting_id; structural validation only |
| multilingual_asr | Same audio + explicit declared languages | meeting_id, transcript, segments, detected_languages, language_distribution, metadata; ASRSegment source IDs retained |
| speaker_representation | Same audio | Actual DiarizationResult fields and global/window provenance; JSON-safe turns/voiceprints |
| overlap_resolution | Actual diarization turns | Overlapping intervals, resolution_status, separation_verified, warnings; unresolved overlap is not invented separation |
| code_switch_intelligence | Original ASR turns | original_text, derived canonical_text, normalized_turns, representation=derived_english_translation; no inferred LID accuracy |
| timestamp_intelligence | ASR + audio duration | Chronological bounded segment validation; does not measure timestamp error against truth |
| transcript_intelligence | ASR + speaker/overlap prerequisites | Verbatim cleaned_segments, conversational_turns, source segment IDs and timing; no removal of genuine fillers/repetitions in REAL |
| confidence_fusion | Actually supplied measured signals | fused_confidence or null; not an estimate of WER/DER |
| context_intelligence | TranscriptIntelligenceResult | Observed verbatim context; inferred semantics unavailable unless a real validated provider supplies them |
| verification_engine | Actual transcript + available confidence | Review/verification state; does not certify acoustic accuracy without reference audio/annotations |
| meeting_understanding | Actual transcript + grounded turns/context | Draft knowledge_objects with source IDs, intervals, model provenance and optional generation metadata |
| meeting_analytics | Observed speaker turns/duration/objects | Descriptive measured aggregates; no invented language/activity distributions |
| knowledge_memory | Grounded objects + authorized SKW | Real persistence status and IDs; must not claim COMMITTED before write/commit succeeds |

## Time, identity and persistence

- ASR/SpeakerTurn/word timestamps are seconds. Add chunk_start once to both local segment and word times. Preserve overlaps; chronological start order does not imply absence of overlapping speech.
- Transcript database start_time_ms/end_time_ms and semantic provenance source_intervals use integer milliseconds, explicitly named start_ms/end_ms. Meeting-understanding handoff converts units at its boundary.
- JSON represents UUIDs as strings. An actual supplied meeting_id cannot silently be replaced with another meeting's ID.
- Canonical transcript persistence remains gated by audio_intelligence, multilingual_asr, speaker_representation, overlap_resolution, timestamp_intelligence, transcript_intelligence, confidence_fusion and verification_engine. Derived English translation and contextual synthesis are not acoustic prerequisites.
- Optional translation/context/semantic failures remain visible and can leave the overall job failed. They no longer unnecessarily prevent publishing otherwise validated audio transcript output. This does not classify a partially failed job as end-to-end success.
- Keep PostgreSQL commit/readback, Redis events and Qdrant/SKW on their existing paths. Do not add a second infrastructure stack or remove authentication.

## Assessment and remaining work

The role separation and checkpointed worker architecture are viable. The measured eight-second boundary problem is not solved merely by changing templates or buying GPU memory: the real 8.22s Hindi comparison had single-context WER25% versus chunked70%, with a conflicting-script overlap tail. Do not force lexical equivalence or claim that NF4 caused it; that run used BF16. Short contexts, speaker match thresholds and token caps need held-out measurement before changing defaults.

Current module boundary fixes were locally syntax/import checked only. This document does not establish model superiority, improved WER/DER, remote deployment or production end-to-end acceptance. Deferred questions include calibration of global voice matching, longer bounded MOSS context, reliable LID, validated Hindi script normalization and semantic grounding against reviewed transcripts. Keep OpenMOSS primary while investigating these; a Whisper comparison alone is not a reason to switch architecture.


## Deployment update — 2026-10-20
Contract fixes deployed; original-language short REAL production and fresh PostgreSQL readback succeeded (meeting e25b8dc1-e5ab-473b-9f16-7b27c24b505b). Common CLI/worker language metadata now reaches ASR. Context uses actual reconciled speaker labels; Gemini generation is deferred to the existing job bound to a persisted canonical transcript. Experimental remote batch profile20s/4s/1024tokens has only8.22s short-file evidence; multi-chunk/long-audio/PRD accuracy remain unverified. See checkpoint and measured summary for scope.
