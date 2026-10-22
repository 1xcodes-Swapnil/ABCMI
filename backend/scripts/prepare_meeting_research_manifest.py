"""Prepare deterministic REAL meeting benchmark inputs; never executes AI inference.

Uses only local VoxConverse audio/cache annotations, AMI timed XML and genuine
AISHELL official test files when present. Catalog transcripts are never used.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path('F:/hf-cache/hub')


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    return str(Path(path).relative_to(ROOT)).replace('\\', '/')


def exclusions(path):
    """Accept a hash list or a nested saved-results/inventory JSON structure."""
    if path is None:
        return set()
    output = set()

    def visit(value):
        if isinstance(value, str) and re.fullmatch('[0-9a-fA-F]{64}', value):
            output.add(value.lower())
        elif isinstance(value, dict):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    return output


def ordered(paths, seed, dataset):
    return sorted(paths, key=lambda path: (
        hashlib.sha256(f'{seed}:{dataset}:{path.name}'.encode()).hexdigest(), path.name))


def audio_record(path, dataset, language, sample_id, info, digest):
    return dict(dataset=dataset, language=language, sample_id=sample_id,
                audio_path=relative(path), sha256=digest, duration=float(info.duration),
                reference_text=None, reference_turns=[],
                metadata={'sample_rate': info.samplerate, 'channels': info.channels,
                          'frames': info.frames, 'full_recording': True,
                          'audio_size_bytes': path.stat().st_size})


def voxconverse(excluded, count, seed):
    import pyarrow.parquet as pq
    import soundfile as sf
    root = ROOT / 'data/benchmarks/voxconverse'
    candidates = ordered(root.glob('audio/test/*.wav'), seed, 'voxconverse')
    targets, excluded_samples = {}, []
    for path in candidates:
        digest = sha_file(path)
        if digest in excluded:
            excluded_samples.append({'audio_path': relative(path), 'sha256': digest,
                                     'reason': 'already processed audio exclusion'})
            continue
        info = sf.info(path)
        if info.duration <= 0:
            raise ValueError('Real VoxConverse recording has no measured duration')
        waveform, _ = sf.read(path, dtype='float32', always_2d=True)
        targets[path.name] = {'path': path, 'info': info, 'sha256': digest,
                             'waveform_sha256': hashlib.sha256(waveform.tobytes()).hexdigest()}
        del waveform
        if len(targets) == count:
            break
    selected = []
    cache = CACHE / 'datasets--diarizers-community--voxconverse'
    for shard in sorted(cache.glob('snapshots/**/test-*.parquet')):
        for index, batch in enumerate(pq.ParquetFile(shard).iter_batches(batch_size=1)):
            if not targets:
                break
            row = batch.to_pylist()[0]
            payload = row.get('audio', {}).get('bytes')
            if not payload:
                continue
            info = sf.info(io.BytesIO(payload))
            matching = [target for target in targets.values()
                        if (target['info'].samplerate, target['info'].frames, target['info'].channels)
                        == (info.samplerate, info.frames, info.channels)]
            if not matching:
                continue
            waveform, _ = sf.read(io.BytesIO(payload), dtype='float32', always_2d=True)
            waveform_digest = hashlib.sha256(waveform.tobytes()).hexdigest()
            del waveform
            for target in matching:
                if target['waveform_sha256'] != waveform_digest:
                    continue
                starts, ends, speakers = (row.get('timestamps_start'), row.get('timestamps_end'),
                                         row.get('speakers'))
                if not starts or not (len(starts) == len(ends) == len(speakers)):
                    raise ValueError('Exact matched VoxConverse row has malformed reference arrays')
                if any(not 0 <= a < b <= info.duration + .1 for a, b in zip(starts, ends)):
                    raise ValueError('Exact matched VoxConverse reference exceeds 100ms tail tolerance')
                path = target['path']
                record = audio_record(path, 'voxconverse', 'en', path.stem, info, target['sha256'])
                record['reference_turns'] = [dict(start=float(a), end=float(b), speaker=str(s))
                                             for a, b, s in zip(starts, ends, speakers)]
                record['metadata'].update(
                    split='test', split_verification='cached test shard + exact waveform match',
                    language_verification='NOT VERIFIED',
                    waveform_sha256=waveform_digest, cache_shard=str(shard), cache_row=index,
                    cached_audio_path=row['audio'].get('path'),
                    cache_revision=shard.parts[-3],
                    annotation_sha256=hashlib.sha256(json.dumps(record['reference_turns'],
                                                    sort_keys=True).encode()).hexdigest(),
                    annotation_tail_seconds=max(0.0, max(ends) - info.duration),
                    reference_timestamps_modified=False, scoring_uem=[0.0, info.duration],
                    WER='NOT VERIFIED: no word reference in this diarization corpus')
                selected.append(record)
                del targets[path.name]
        if not targets:
            break
    selected.sort(key=lambda record: hashlib.sha256(
        f"{seed}:voxconverse:{Path(record['audio_path']).name}".encode()).hexdigest())
    group = dict(dataset='voxconverse', requested=count, selected=len(selected),
                 status='READY' if len(selected) == count else 'BLOCKED',
                 exclusions=excluded_samples, unmatched_audio=list(targets),
                 blocker=None if len(selected) == count else 'Not enough exact waveform-matched local annotations')
    return selected, group


def ami(excluded, count, seed):
    import soundfile as sf
    annotations = ROOT / 'data/benchmarks/ami'
    paths = [path for path in (ROOT / 'data/audio/raw').glob('*.Mix-Headset.wav')
             if re.fullmatch('[A-Z]{2}[0-9]{4}[a-z]\\.Mix-Headset\\.wav', path.name)]
    selected, skipped = [], []
    for path in ordered(paths, seed, 'ami'):
        digest = sha_file(path)
        if digest in excluded:
            skipped.append({'audio_path': relative(path), 'sha256': digest,
                            'reason': 'already processed audio exclusion'})
            continue
        meeting = path.name.split('.')[0]
        words, turns, source_files, missing_time = [], [], [], 0
        for source in sorted(annotations.rglob(meeting + '.*.words.xml')):
            source_files.append({'path': relative(source), 'sha256': sha_file(source)})
            for node in ET.parse(source).getroot().iter():
                if node.tag.split('}')[-1] != 'w':
                    continue
                word = ''.join(node.itertext()).strip()
                if not word:
                    continue
                if 'starttime' not in node.attrib or 'endtime' not in node.attrib:
                    missing_time += 1
                    continue
                start, end = float(node.attrib['starttime']), float(node.attrib['endtime'])
                if not 0 <= start <= end:
                    raise ValueError('AMI official word XML has invalid timestamps')
                words.append((start, end, word))
        for source in sorted(annotations.rglob(meeting + '.*.segments.xml')):
            source_files.append({'path': relative(source), 'sha256': sha_file(source)})
            for node in ET.parse(source).getroot().iter():
                start = node.attrib.get('transcriber_start', node.attrib.get('starttime'))
                end = node.attrib.get('transcriber_end', node.attrib.get('endtime'))
                if node.tag.split('}')[-1] == 'segment' and start is not None and end is not None:
                    if float(end) > float(start) >= 0:
                        turns.append(dict(start=float(start), end=float(end), speaker=source.name.split('.')[1]))
        if not words or not turns:
            skipped.append({'audio_path': relative(path), 'reason': 'missing actual official word/segment XML'})
            continue
        info = sf.info(path)
        record = audio_record(path, 'ami', 'en', meeting, info, digest)
        record.update(reference_text=' '.join(word for _, _, word in sorted(words)),
                      reference_turns=turns)
        record['metadata'].update(
            split='NOT VERIFIED', publication_blocker='Official evaluation partition mapping absent locally',
            execution_ready=True, reference_sources=source_files,
            words_missing_timestamps=missing_time,
            WER_protocol='chronological word proxy; overlapping speech requires a separately validated ASR scoring protocol',
            timestamp_error='NOT VERIFIED until correspondence is validated',
            scoring_uem=[0.0, info.duration])
        selected.append(record)
        if len(selected) == count:
            break
    return selected, dict(dataset='ami', requested=count, selected=len(selected),
                          status='READY_WITH_PUBLICATION_LIMITATION' if len(selected) == count else 'BLOCKED',
                          publication_blocker='Official evaluation partition NOT VERIFIED', exclusions=skipped)


def aishell(excluded, count, seed):
    import soundfile as sf
    root = ROOT / 'data/benchmarks/aishell'
    # Only actual OpenSLR test paths and official transcript; never catalog fallbacks.
    candidates = list(root.glob('**/wav/test/**/*.wav')) if root.is_dir() else []
    transcripts = list(root.glob('**/aishell_transcript_v0.8.txt')) if root.is_dir() else []
    if not candidates or len(transcripts) != 1:
        return [], dict(dataset='aishell', requested=count, selected=0, status='BLOCKED',
                        blocker='Official test audio and a unique actual transcript file unavailable; cache contains refs/main only')
    source = transcripts[0]
    table = {}
    for line in source.read_text(encoding='utf-8').splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            table[parts[0]] = parts[1].replace(' ', '')
    selected = []
    for path in ordered(candidates, seed, 'aishell'):
        digest = sha_file(path)
        if digest in excluded or path.stem not in table:
            continue
        info = sf.info(path)
        record = audio_record(path, 'aishell', 'zh', path.stem, info, digest)
        record.update(reference_text=table[path.stem])
        record['metadata'].update(split='test', reference_source=relative(source),
                                  reference_sha256=sha_file(source), speaker_id=path.parent.name,
                                  primary_metric='CER', DER='NOT VERIFIED: no timed speaker annotation',
                                  timestamp_error='NOT VERIFIED')
        selected.append(record)
        if len(selected) == count:
            break
    return selected, dict(dataset='aishell', requested=count, selected=len(selected),
                          status='READY' if len(selected) == count else 'BLOCKED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude', type=Path)
    parser.add_argument('--seed', type=int, default=20261020)
    parser.add_argument('--vox-count', type=int, default=30)
    parser.add_argument('--ami-count', type=int, default=3)
    parser.add_argument('--aishell-count', type=int, default=300)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Preserve existing manifest; select a new output path')
    if not 1 <= args.vox_count <= 232 or not 1 <= args.ami_count <= 5 or not 1 <= args.aishell_count <= 500:
        parser.error('Requested counts outside bounded scope')
    excluded = exclusions(args.exclude)
    samples, groups = [], []
    for function, count in [(voxconverse, args.vox_count), (ami, args.ami_count), (aishell, args.aishell_count)]:
        records, group = function(excluded, count, args.seed)
        samples.extend(records)
        groups.append(group)
    result = dict(created_at=datetime.now(timezone.utc).isoformat(), seed=args.seed,
                  selection='SHA256(seed:dataset:audio-basename) rank, excluding already processed audio hashes; no outcome selection',
                  inference_executed=False, downloads=False, excluded_hash_count=len(excluded),
                  exclude_source=str(args.exclude) if args.exclude else None,
                  exclude_source_sha256=sha_file(args.exclude) if args.exclude else None,
                  source_sha256=sha_file(__file__), groups=groups, samples=samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'artifact': str(args.output), 'groups': groups}, ensure_ascii=False))


if __name__ == '__main__':
    main()
