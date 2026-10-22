"""Manifest-driven REAL MOSS ASR-component benchmark; never full app acceptance.

One provider is reused sequentially. Results and raw generations persist per
attempt. Existing completed/failed samples are never inferred again; an interrupted
sample blocks restart until its saved evidence is reviewed. No downloads/fallback.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
SCOPE = 'ASR component only; no production meeting, PyAnnote, semantic stages or speaker accuracy verification'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    temporary.replace(path)


def local_audio(sample):
    path = (ROOT / sample['audio_path']).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError('Manifest audio must exist inside this repository')
    return path


def validate_sample(sample):
    import soundfile as sf
    from app.benchmarks.metrics import normalize_text
    path = local_audio(sample)
    info = sf.info(path)
    if not 0 < info.duration <= 30 or info.samplerate != 16000 or info.channels != 1 or info.subtype != 'PCM_16':
        raise ValueError('Only original bounded 0–30s 16kHz mono PCM16 utterances are supported')
    if sha(path) != sample['sha256']:
        raise ValueError('Manifest audio hash differs')
    if abs(info.duration - sample['duration_seconds']) > 1 / info.samplerate:
        raise ValueError('Manifest duration differs from actual audio')
    if not normalize_text(sample.get('reference_text', '')):
        raise ValueError('Missing or normalized-empty reference; accuracy undefined')
    if sample.get('metadata', {}).get('split') != 'test':
        raise ValueError('This individual FLEURS runner requires a declared test split')
    annotation = sample.get('metadata', {}).get('annotation_source')
    expected = sample.get('metadata', {}).get('annotation_sha256')
    if not annotation or not expected:
        raise ValueError('Annotation source/hash missing')
    source = (ROOT / annotation).resolve()
    if not source.is_relative_to(ROOT.resolve()) or not source.is_file() or sha(source) != expected:
        raise ValueError('Annotation artifact identity differs')
    return path, info


def metrics(reference, hypothesis):
    from app.benchmarks.metrics import calculate_wer, calculate_cer, normalize_text
    from rapidfuzz.distance import Levenshtein
    ref, hyp = normalize_text(reference), normalize_text(hypothesis)
    if not ref:
        raise ValueError('Empty normalized ground truth')
    word, character = calculate_wer(reference, hypothesis), calculate_cer(reference, hypothesis)
    word_errors = sum(word[key] for key in ('substitutions', 'deletions', 'insertions'))
    char_errors = sum(character[key] for key in ('substitutions', 'deletions', 'insertions'))
    if word_errors != Levenshtein.distance(ref.split(), hyp.split()):
        raise RuntimeError('Word metric implementation cross-check failed')
    if char_errors != Levenshtein.distance(ref.replace(' ', ''), hyp.replace(' ', '')):
        raise RuntimeError('Character metric implementation cross-check failed')
    return word, character


def aggregate(rows):
    groups = {}
    for row in rows:
        key = (row['dataset'], row['language'])
        group = groups.setdefault(key, {'dataset': key[0], 'language': key[1], 'attempted': 0,
            'completed': 0, 'failed': 0, 'WER': None, 'CER': None, 'edit_counts': {}})
        group['attempted'] += 1
        group['completed' if row['status'] == 'COMPLETED' else 'failed'] += 1
    for key, group in groups.items():
        successful = [row for row in rows if (row['dataset'], row['language']) == key and row['status'] == 'COMPLETED']
        for name, denominator in [('WER', 'ref_word_count'), ('CER', 'ref_char_count')]:
            counts = {k: sum(row[name][k] for row in successful) for k in ('substitutions', 'deletions', 'insertions', denominator)}
            group['edit_counts'][name] = counts
            group[name] = sum(counts[k] for k in ('substitutions', 'deletions', 'insertions')) / counts[denominator] if counts[denominator] else None
        duration = sum(row['duration_seconds'] for row in successful)
        group['successful_only_RTF'] = sum(row['processing_seconds'] for row in successful) / duration if duration else None
        group['accuracy_scope'] = 'Successful outputs only; failures counted separately, never assigned zero error'
    return list(groups.values())


async def production_idle():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    try:
        async with async_sessionmaker(init_database())() as database:
            count = (await database.execute(text("SELECT count(*) FROM inference_jobs WHERE status IN ('queued','running')"))).scalar_one()
        return count == 0
    finally:
        await close_database_connections()


def fatal_error(exc, provider):
    text = str(exc).casefold()
    return (isinstance(exc, (ImportError, ModuleNotFoundError, OSError)) or
        getattr(provider, '_cached_model', None) is None or
        any(term in text for term in ('out of memory', 'cuda error', 'device-side assert',
            'no cuda', 'no space left', 'metric implementation cross-check failed')))


async def execute(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'backend/.env', override=True)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    from app.core.config import get_settings
    from app.ai.multilingual_asr import OpenMOSSProvider
    from app.ai.model_inventory import snapshot_for, configure_cache
    from app.cli import sanitize_error_text
    import torch
    import psutil

    settings = get_settings()
    if settings.EXECUTION_MODE != 'REAL' or settings.BATCH_ASR_PROVIDER != 'moss':
        raise RuntimeError('Existing REAL primary MOSS configuration required; no provider override')
    if not settings.OPENMOSS_DEVICE.startswith('cuda') or not torch.cuda.is_available():
        raise RuntimeError('Actual CUDA required; CPU fallback forbidden')
    manifest = read(args.manifest)
    if manifest.get('status') not in {'PREPARED_NOT_EXECUTED', 'PARTIAL_PREPARATION'}:
        raise ValueError('Unsupported or unvalidated manifest status')
    samples = manifest['samples']
    if not samples or len({sample['sample_id'] for sample in samples}) != len(samples):
        raise ValueError('Manifest must contain unique real sample IDs')
    if len({sample['sha256'] for sample in samples}) != len(samples):
        raise ValueError('Manifest contains duplicate audio hashes')
    # Validate before creating any attempt/model; shortfall stays explicit in manifest.
    for sample in samples:
        validate_sample(sample)
    snapshot = snapshot_for(settings.OPENMOSS_MODEL_ID, configure_cache())
    if snapshot is None:
        raise RuntimeError('Existing cached MOSS snapshot unavailable; no download')
    identity = {'execution_mode': 'REAL', 'provider': 'moss', 'model': settings.OPENMOSS_MODEL_ID,
        'model_revision': snapshot.name, 'device': settings.OPENMOSS_DEVICE,
        'precision': settings.OPENMOSS_PRECISION, 'prompt_policy': settings.OPENMOSS_PROMPT_POLICY,
        'max_new_tokens': settings.OPENMOSS_MAX_NEW_TOKENS,
        'configured_chunk_duration_seconds': settings.AUDIO_CHUNK_DURATION_SECONDS,
        'configured_overlap_seconds': settings.AUDIO_CHUNK_OVERLAP_SECONDS,
        'configured_chunk_threshold_seconds': settings.AUDIO_CHUNK_THRESHOLD_SECONDS,
        'configured_chunk_concurrency': settings.AUDIO_CHUNK_CONCURRENCY,
        'chunking_scope': 'Bounded individual utterance provider call; configured long-audio planner not invoked',
        'manifest_sha256': sha(args.manifest), 'runner_sha256': sha(__file__),
        'provider_source_sha256': sha(ROOT/'backend/app/ai/multilingual_asr.py'),
        'metrics_source_sha256': sha(ROOT/'backend/app/benchmarks/metrics.py'), 'scope': SCOPE}
    args.run.mkdir(parents=True, exist_ok=True)
    pin = args.run/'identity.json'
    if pin.exists() and read(pin) != identity:
        raise RuntimeError('Frozen identity differs; preserve this run and use a different directory')
    if not pin.exists():
        save(pin, identity)
    runfile = args.run/'run.json'
    if not runfile.exists():
        save(runfile, {'benchmark_run_id': str(uuid.uuid4()), 'timestamp': now(), 'scope': SCOPE,
            'requested_samples': len(samples), 'source_manifest': str(args.manifest),
            'prepared_groups': manifest.get('groups', []), 'inference_not_started_by_preparation': True})
    run_id = read(runfile)['benchmark_run_id']
    provider = OpenMOSSProvider({'model_id': settings.OPENMOSS_MODEL_ID,
        'device': settings.OPENMOSS_DEVICE, 'cache_dir': settings.OPENMOSS_CACHE_DIR,
        'precision': settings.OPENMOSS_PRECISION})
    rows = []
    for sample in samples[:args.max_samples] if args.max_samples else samples:
        folder = args.run/sample['sample_id']
        folder.mkdir(exist_ok=True)
        result_path = folder/'result.json'
        if result_path.exists():
            previous = read(result_path)
            if previous.get('identity') != identity or previous.get('audio_sha256') != sample['sha256']:
                raise RuntimeError('Existing sample identity differs')
            rows.append(previous)  # Includes saved failures; no automatic rerun.
            continue
        if (folder/'attempt.json').exists():
            raise RuntimeError('Interrupted sample exists; inspect saved attempt/generations before any rerun: '+sample['sample_id'])
        save(args.run/'status.json', {'timestamp': now(), 'status': 'WAITING_FOR_IDLE', 'current_sample': sample['sample_id'], 'saved_results': len(rows)})
        # Snapshot admission check, not a global lock shared with the application.
        while not await production_idle():
            await asyncio.sleep(10)
        path, info = validate_sample(sample)
        attempt_id = str(uuid.uuid4())
        base = {'benchmark_run_id': run_id, 'benchmark_sample_id': sample['sample_id'], 'attempt_id': attempt_id,
            'dataset': sample['dataset'], 'language': sample['language'], 'identity': identity,
            'audio_sha256': sample['sha256'], 'audio_filename': path.name,
            'duration_seconds': info.duration, 'sample_rate': info.samplerate, 'channels': info.channels,
            'reference': sample['reference_text'], 'reference_metadata': sample.get('metadata', {}),
            'scope': SCOPE, 'meeting_id': 'NOT AVAILABLE', 'canonical_transcript_id': 'NOT AVAILABLE',
            'DER': None, 'JER': None, 'timestamp_error': None, 'started_at': now()}
        save(folder/'attempt.json', base)
        save(args.run/'status.json', {'timestamp': now(), 'status': 'RUNNING', 'current_sample': sample['sample_id'], 'saved_results': len(rows)})
        generation_count = 0
        def journal(value):
            nonlocal generation_count
            generation_count += 1
            save(folder/f'generation_{generation_count:03}.json', value)
        provider.last_raw_output = None
        provider.last_inference = {}
        torch.cuda.reset_peak_memory_stats(settings.OPENMOSS_DEVICE)
        started = time.perf_counter()
        failure = None
        try:
            # Reference text never enters generation options/prompt.
            segments = await provider.transcribe(str(path), {'language_hint': sample['language'],
                'prompt_policy': settings.OPENMOSS_PROMPT_POLICY,
                'max_new_tokens': settings.OPENMOSS_MAX_NEW_TOKENS, 'generation_journal': journal})
            elapsed = time.perf_counter()-started
            hypothesis = ' '.join(segment.transcript for segment in segments)
            if not segments or not hypothesis.strip():
                raise ValueError('Actual provider returned empty parsed transcript')
            word, character = metrics(sample['reference_text'], hypothesis)
            result = {**base, 'status': 'COMPLETED', 'hypothesis': hypothesis,
                'segments': [segment.model_dump(mode='json') for segment in segments],
                'WER': word, 'CER': character, 'processing_seconds': elapsed,
                'RTF': elapsed/info.duration,
                'metric_crosscheck': 'Existing edit counts equal RapidFuzz exact Levenshtein'}
        except Exception as exc:
            failure = exc
            result = {**base, 'status': 'FAILED', 'WER': None, 'CER': None,
                'error_type': type(exc).__name__, 'reason': sanitize_error_text(str(exc)),
                'processing_seconds': time.perf_counter()-started}
        result.update(finished_at=now(), generation_count=generation_count,
            inference=provider.last_inference, gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(settings.OPENMOSS_DEVICE),
            gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved(settings.OPENMOSS_DEVICE), cpu_rss_after_bytes=psutil.Process().memory_info().rss,
            telemetry_scope='Torch allocation peaks and process RSS after attempt, not total system/instantaneous GPU peak',
            normalization='NFC, casefold, Unicode L/M/N, punctuation->spaces, collapse whitespace; CER ignores spaces; no transliteration')
        save(folder/'last_raw_output.json', {'raw_moss_output': provider.last_raw_output, 'inference': provider.last_inference})
        save(result_path, result)
        # Verify persisted JSON can be read back before continuing.
        if read(result_path)['attempt_id'] != attempt_id:
            raise RuntimeError('Saved result readback differs')
        rows.append(result)
        save(args.run/'summary.json', {'timestamp': now(), 'benchmark_run_id': run_id,
            'scope': SCOPE, 'saved_results': len(rows), 'requested_samples': len(samples),
            'groups': aggregate(rows), 'configuration_identity': identity})
        print(json.dumps({key: result.get(key) for key in ('benchmark_sample_id', 'language', 'status', 'WER', 'reason')}), flush=True)
        if failure is not None and fatal_error(failure, provider):
            raise RuntimeError('Fatal resource/model/infrastructure failure; saved current sample, stopped without retry') from failure
    status = 'FINISHED' if len(rows) == len(samples) else 'BOUNDED_SUBSET_FINISHED'
    save(args.run/'status.json', {'timestamp': now(), 'status': status, 'saved_results': len(rows),
        'successful': sum(row['status']=='COMPLETED' for row in rows), 'failed': sum(row['status']=='FAILED' for row in rows),
        'requested_samples': len(samples), 'scope': SCOPE})
    return 0 if all(row['status']=='COMPLETED' for row in rows) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--max-samples', type=int, help='Initial bounded execution; no different profile/prompt')
    args = parser.parse_args()
    if args.max_samples is not None and args.max_samples < 1:
        parser.error('--max-samples must be positive')
    args.run.mkdir(parents=True, exist_ok=True)
    lock = args.run/'controller.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print('Existing controller.lock: inspect the saved PID and attempts; no second controller or automatic stale-lock removal.', file=sys.stderr)
        return 1
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        json.dump({'pid': os.getpid(), 'timestamp': now(), 'scope': SCOPE}, handle)
    try:
        return asyncio.run(execute(args))
    except Exception as exc:
        args.run.mkdir(parents=True, exist_ok=True)
        # Do not dump dependency/config messages that could contain credentials.
        try:
            from app.cli import sanitize_error_text
            reason = sanitize_error_text(str(exc))
        except Exception:
            reason = 'Infrastructure/dependency error; inspect configured environment safely'
        save(args.run/'blocked.json', {'timestamp': now(), 'status': 'BLOCKED',
            'error_type': type(exc).__name__, 'reason': reason,
            'scope': SCOPE})
        return 1
    finally:
        # This controller alone created this lock. A crash preserves it for review.
        if lock.exists():
            lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
