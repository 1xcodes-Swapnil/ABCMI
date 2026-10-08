"""Append Phase 1 report from existing execution evidence; performs no inference."""
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
run=ROOT/'e2e_validation/runs/phase1_20261001T202409Z_11de0a732350'
read=lambda name:json.loads((run/name).read_text())
execution=read('execution.json')
ids=read('identifiers.json')
pyannote=read('pyannote.json')
events=read('redis_events.json')
calls=read('moss_calls.json')
text=(run/'cli.log').read_text(encoding='utf-8')
observed=[]
for line_no,line in enumerate(text.splitlines(),1):
    for value in re.findall(r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b',line):
        observed.append({'id':value,'source':f'cli.log:{line_no}','classification':'observed; may include existing records'})
audio_match=re.search(r'Audio registered ID: ([0-9a-f-]{36})',text)
ids.update(audio_record_id=audio_match.group(1) if audio_match else 'NOT AVAILABLE',
           cli_observed_uuid_fields=observed,
           redis_event_ids=ids['event_ids'],redis_stream_id='NOT AVAILABLE',
           runtime_retry_requests=sum(e['event'].get('event_type')=='orchestration.retry_requested' for e in events if isinstance(e['event'],dict)))
for k,v in list(ids.items()):
    if k.endswith('_ids') and v==[]: ids[k]='NOT AVAILABLE'
(run/'identifiers_complete.json').write_text(json.dumps(ids,indent=2),encoding='utf-8')
for previous in ('phase1_20261001T201723Z_6ac6c596a21c','phase1_20261001T202123Z_32dfcffbb705'):
    folder=run.parent/previous
    old=json.loads((folder/'identifiers.json').read_text())
    for k,v in list(old.items()):
        if k.endswith('_ids') and v==[]: old[k]='NOT AVAILABLE'
    (folder/'identifiers_complete.json').write_text(json.dumps(old,indent=2),encoding='utf-8')
chunks='\n'.join('- '+chunk for chunk in ids['chunk_ids'])
report=f'''# Phase 1 REAL production report — 2026-10-02 (Asia/Calcutta)

STATUS: BLOCKED — configured 600-second MOSS chunk exceeds resources observed on this laptop.
GIT COMMIT: {execution['git_commit']} (working tree changes uncommitted).

RUN ID: {ids['run_id']}
MEETING ID: {ids['meeting_id']} (generated but not committed; absent in fresh process).
CANONICAL TRANSCRIPT ID: NOT AVAILABLE
PROJECT ID: NOT AVAILABLE
CORRELATION ID: {ids['correlation_ids'][0]}
AUDIO RECORD ID: {ids['audio_record_id']} (generated, not committed).
CHUNK IDs: eight generated across four automatic production attempts; none are successful completed chunks:

{chunks}

AUDIO: {execution['audio_filename']}; real existing WAV, {execution['audio_size']} bytes, {execution['sample_rate']} Hz, {execution['channels']} channel.
DURATION: {execution['audio_duration']} seconds.
SHA-256: {execution['audio_sha256']}

CHUNKS: required two under unchanged configuration: [0,600] and [570,1049.3546875] seconds (planner rounds final bound to 1049.355). Duration 600 s, overlap 30 s, step 570 s. 0 < overlap < duration; planned coverage has no gaps. Completion NOT VERIFIED.
MOSS: real CUDA inference attempted on chunk 0; three recorded OOM failures, fourth attempt interrupted. Chunk 1 never reached. No raw generation output or parsed transcript. First failure after {calls[0]['elapsed_seconds']} s: attempted 960 MiB allocation with zero free GPU memory, physical capacity 4 GiB. PyTorch counters reported about 9.06 GiB allocated plus 1.12 GiB reserved at that failure; these counters are not a claim of physical VRAM residency.
PYANNOTE: actual completed DiarizeOutput; {len(pyannote['output']['speaker_turns'])} turns, {pyannote['output']['num_speakers']} speakers; float32 embeddings shape {pyannote['output']['metadata']['embedding_shape']}. Inference {pyannote['output']['metadata']['inference_seconds']} s; elapsed including loading {pyannote['elapsed_seconds']} s. Speaker accuracy NOT VERIFIED.
SPEAKER RECONCILIATION: NOT VERIFIED; multi-chunk MOSS output unavailable.
TIMESTAMPS: chunk math/coverage checked; transcript local-to-global reconstruction NOT VERIFIED.
DEDUP: NOT VERIFIED; execution never reached the merge stage. No lossless/zero-duplication claim.
POSTGRES: fresh-process connection succeeded; zero committed meeting/audio/canonical/segment records for this attempt. The interrupted CLI transaction did not persist its generated meeting. No nonexistent row was inserted or marked failed.
FRESH READBACK: executed in a separate Python process; no persisted transcript found. Evidence fresh_readback.json.
REDIS: {len(events)} observed real distributed publications; actual domain event IDs captured. Redis pub/sub has no Redis stream ID: NOT AVAILABLE. This does not prove delivery to an external subscriber.
QDRANT: indexing/read-back NOT VERIFIED; production path never reached knowledge indexing. Point/vector ID NOT AVAILABLE.
ACE/BLACKBOARD/SKW: existing paths retained. Actual planning/task/retry events saved; prerequisite SKW access occurred. Final blackboard dump/SKW write unavailable because validation process was stopped. Runtime emitted {ids['runtime_retry_requests']} automatic retry requests; Phase 2 retry validation was not started.
CLI: started existing REAL production CLI; final response/CLI exit code NOT AVAILABLE because exact validation Python process was stopped after deterministic failures. Shell exit 1 after process termination is not claimed as the CLI's processing result.

REAL INFERENCE: attempted; MOSS failed, PyAnnote completed. Complete multi-chunk transcript NOT VERIFIED.
MOCK/FIXTURE FALLBACK: none observed in actual provider calls. No CPU fallback, synthetic audio, fake transcript/embedding/confidence or downloads supplied.
METRICS: no WER/CER/DER/JER or timestamp accuracy calculated (later phases not started). MOSS observed failure elapsed times {[c.get('elapsed_seconds','NOT AVAILABLE') for c in calls]}; total pipeline processing time/RTF NOT AVAILABLE after interruption. CPU/GPU allocation snapshots in execution.json; stop process working set in diagnostics. CPU RSS after first failure 8,472,420,352 bytes; PyTorch peak allocation counter 10,703,760,896 bytes.
ARTIFACTS: preflight.json, execution.json, execution_at_interruption.json, chunks.json, moss_calls.json, pyannote.json, redis_events.json, cli.log, fresh_readback.json, timestamp_validation.json, identifiers.json, identifiers_complete.json, phase1_result.json. Process-stop evidence under e2e_validation/diagnostics. IDs not generated are explicitly NOT AVAILABLE; all observed UUIDs, events and artifact references captured in identifiers_complete.json.

PHASE 1: BLOCKED.
REMAINING GAP: current 600-second chunks cannot produce MOSS output on observed GPU/resources; no reconstructed or persisted multi-chunk transcript.
NEXT ACTION: choose a smaller GPU-safe chunk configuration or a larger GPU, then rerun Phase 1 only. Do not start Phase 2. Two recorder setup failures before inference were fixed and retained in separate run folders; no verified small inference was rerun.

Minimal production changes made before execution: preserve actual chunk IDs/state/correlation/speaker mapping in ASR metadata (therefore canonical provenance when persistence succeeds); preserve multi-chunk speaker mapping and dedup count at the existing persistence boundary. Syntax checks passed; successful persistence of these fields is not claimed. No architecture replacement or unrelated Git/cache cleanup.
'''
report_path=ROOT/'e2e_validation/artifacts'/f"{ids['run_id']}_report.md"
report_path.write_text(report,encoding='utf-8')
registry=[]
for file in run.iterdir():
    if file.is_file():
        registry.append({'path':str(file.relative_to(ROOT)),'bytes':file.stat().st_size,
                         'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
(ROOT/'e2e_validation/artifacts'/f"{ids['run_id']}_registry.json").write_text(json.dumps(registry,indent=2),encoding='utf-8')
with (ROOT/'e2e_validation/execution_log.md').open('a',encoding='utf-8') as f:
    f.write('\n'+report+'\n### Complete observed identifier inventory\n```json\n'+json.dumps({k:v for k,v in ids.items() if k not in ('all_observed_uuid_fields','cli_observed_uuid_fields')},indent=2)+'\n```\nUUID field and CLI-line provenance retained in identifiers_complete.json.\n')
with (ROOT/'e2e_validation/CHECKPOINT.md').open('a',encoding='utf-8') as f:
    f.write(f"\n### Phase 1 final checkpoint\n- Phase 1 BLOCKED, run {ids['run_id']}; first configured MOSS chunk CUDA OOM.\n- PyAnnote actual inference completed; no committed meeting/transcript exists for this attempt.\n- Exact process stopped to prevent identical runtime retries. Phase 2 not started.\n- Files changed: long_audio_processor.py, meeting_service.py; new validate_phase1.py/readback_phase1.py/document_phase1.py; evidence files.\n- Next action: select a smaller GPU-safe chunk configuration or larger GPU, then Phase 1 only.\n- Report: {report_path.relative_to(ROOT)}.\n")
development=f'''

## 2026-10-02 — Local REAL transcript integration and Phase 1 validation

- Prior verified short production transcript: ES2014a 71–81 s, three real MOSS segments; actual PyAnnote; all 13 ACE tasks; PostgreSQL commit/fresh-session read-back and CLI success. Processing 60.6572947 s. Separate short two-chunk ASR passed. One cached English FLEURS record scored WER 5.2632%, CER 1.2346%; no dataset-wide accuracy claim.
- Phase 1 under unchanged 600 s / 30 s settings: real ES2004a, 1049.3546875 s; required two chunks. Actual MOSS CUDA OOM on first chunk. Actual PyAnnote completed (264 turns, four speakers). Existing runtime requested repeated identical attempts; exact validation process stopped to prevent further waste. No mock/CPU substitution or downloads.
- PHASE 1 BLOCKED: no reconstructed transcript, canonical persistence, Qdrant indexing or final CLI success. Fresh process confirmed no committed meeting/transcript for this failed attempt. Prior short success does not verify Phase 1.
- Persistent evidence and all observed IDs: e2e_validation/runs/{ids['run_id']}; execution_log.md and CHECKPOINT.md appended. Full report: {report_path.relative_to(ROOT)}.
- Minimal changes: expose actual chunk metadata/speaker mapping in existing ASR provenance and retain mapping/dedup count at existing persistence boundary; evidence recorder setup errors fixed. Changed modules syntax-checked; no successful multi-chunk persistence claim.
- Next action: smaller GPU-safe chunk configuration or larger GPU, then Phase 1 only. Phase 2 and later phases not started. Speaker/semantic accuracy and full dataset coverage remain unverified.
'''
for file in ('DEVELOPMENT_LOG_BOOK.md','docs/DEVELOPMENT_LOG_BOOK.md'):
    with (ROOT/file).open('a',encoding='utf-8') as f: f.write(development)
print(str(report_path))
