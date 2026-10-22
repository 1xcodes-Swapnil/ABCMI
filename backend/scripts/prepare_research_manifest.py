"""Prepare unused native FLEURS test utterances; never runs models or downloads.

Exclude previously recorded audio and alternate recordings of the same sentence
within each language. The currently running merged experiment is also excluded.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import wave

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ('en_us', 'hi_in', 'ta_in')
FILE_RE = re.compile(r'\b([a-z]{2}_[a-z]{2}_\d{5}\.(?:wav|flac))\b', re.I)
HASH_RE = re.compile(r'^[0-9a-f]{64}$')
NAME_KEYS = {'audio_path', 'audio_filename', 'file_name', 'filename', 'sample_id', 'benchmark_sample_id', 'relative_audio'}
HASH_KEYS = {'sha256', 'audio_sha256', 'source_audio_sha256'}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def relative(path):
    return str(Path(path).resolve().relative_to(ROOT)).replace('\\', '/')

def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

def tables():
    result = {}
    for config in CONFIGS:
        path = ROOT / 'data/benchmarks/fleurs' / config / 'test.tsv'
        rows = []
        with path.open(encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
            if not {'path', 'id', 'transcription'}.issubset(reader.fieldnames or []):
                raise ValueError('Missing required TSV header: ' + config)
            for index, row in enumerate(reader):
                row['_line'] = index + 2
                rows.append(row)
        result[config] = (path, rows)
    return result

def historical_exclusions(extra_paths=()):
    hashes, names, sources = {}, {}, []
    base = ROOT / 'benchmark results'
    candidates = []
    for path in base.rglob('*.json'):
        if path.name in {'metrics.json', 'result.json', 'fix_verification.json', 'input.json', 'measured_summary.json'} or path.name.startswith('saved_database_exports') or re.fullmatch(r'sample_\d+\.json', path.name):
            candidates.append(path)

    def visit(value, source):
        if isinstance(value, list):
            for child in value:
                visit(child, source)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in HASH_KEYS and isinstance(child, str) and HASH_RE.fullmatch(child.lower()):
                    hashes.setdefault(child.lower(), set()).add(source)
                if key in NAME_KEYS and isinstance(child, str):
                    # Stable adapter sample IDs omit the filename extension.
                    text = child + '.wav' if key in {'sample_id', 'benchmark_sample_id'} else child
                    for match in FILE_RE.finditer(text):
                        names.setdefault(match[1].lower(), set()).add(source)
                    # Adapter IDs can prefix an additional fleurs_<config>_.
                    for config in CONFIGS:
                        match = re.search(r'(' + re.escape(config) + r'_\d{5})(?:\b|_)', text)
                        if match:
                            names.setdefault(match[1].lower() + '.wav', set()).add(source)
                if isinstance(child, (list, dict)):
                    visit(child, source)

    candidates.extend(Path(path).resolve() for path in extra_paths)
    for path in sorted(set(candidates)):
        source = relative(path)
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError):
            sources.append({'source': source, 'status': 'UNREADABLE_NOT_USED'})
            continue
        visit(data, source)
        sources.append({'source': source, 'sha256': sha(path), 'status': 'INSPECTED'})

    merged = base / 'merged_fleurs_20261021/merged_manifest.json'
    if not merged.is_file():
        raise ValueError('Current merged exclusion manifest is missing')
    data = json.loads(merged.read_text(encoding='utf-8'))
    if data.get('status') != 'VERIFIED':
        raise ValueError('Merged reference mapping not verified')
    for sample in data['samples']:
        for interval in sample['reference_intervals']:
            name = Path(interval['source_audio']).name.lower()
            names.setdefault(name, set()).add(relative(merged))
            hashes.setdefault(interval['source_audio_sha256'], set()).add(relative(merged))
    sources.append({'source': relative(merged), 'sha256': sha(merged), 'status': 'CURRENT_MERGED_COHORT_EXCLUDED'})
    return hashes, names, sources

def main():
    global CONFIGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'benchmark results/individual_fleurs_next_20261021')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--seed', default='ABCI-MI-FLEURS-20261021-v1')
    parser.add_argument('--configs', nargs='+', default=list(CONFIGS),
                        help='Local native test-language configurations')
    parser.add_argument('--extra-exclusions', action='append', type=Path, default=[],
                        help='Current read-only upload snapshot or diagnostic control manifest; repeatable')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[a-z]{2}_[a-z]{2}', name) for name in args.configs):
        parser.error('Configuration must be a local language code such as en_us')
    if any(not path.is_file() for path in args.extra_exclusions):
        parser.error('Every extra exclusion must be an existing JSON file')
    CONFIGS = tuple(dict.fromkeys(args.configs))
    if not 1 <= args.count <= 500:
        parser.error('Count must be between 1 and 500 per language')
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output/'manifest.json').exists():
        raise SystemExit('Existing immutable manifest preserved; use a new output folder')
    annotations = tables()
    hashes, names, evidence = historical_exclusions(args.extra_exclusions)
    sentence_ids = {config: set() for config in CONFIGS}
    for config, (_, rows) in annotations.items():
        for row in rows:
            if row.get('path') and Path(row['path']).name.lower() in names and row.get('id'):
                sentence_ids[config].add(str(row['id']))
    samples, excluded, groups = [], [], []
    for config, (tsv, rows) in annotations.items():
        eligible, selected_sentences = [], set()
        for row in rows:
            name = Path(row.get('path') or '').name
            item = {'configuration': config, 'filename': name, 'source_row_id': row.get('id'), 'source_line': row['_line']}
            if not name or not row.get('transcription', '').strip() or not row.get('id'):
                excluded.append({**item, 'reason': 'missing_or_malformed_reference_record'})
                continue
            if name.lower() in names:
                excluded.append({**item, 'reason': 'already_recorded_audio_or_current_merged_constituent', 'evidence': sorted(names[name.lower()])})
                continue
            if str(row['id']) in sentence_ids[config]:
                excluded.append({**item, 'reason': 'alternate_recording_of_previously_used_sentence_in_same_language'})
                continue
            audio = tsv.parent/'audio/test'/name
            if not audio.is_file():
                excluded.append({**item, 'reason': 'audio_missing'})
                continue
            try:
                with wave.open(str(audio), 'rb') as f:
                    rate, frames, channels, width = f.getframerate(), f.getnframes(), f.getnchannels(), f.getsampwidth()
                duration = frames/rate
                if rate != 16000 or channels != 1 or width != 2 or not 0 < duration <= 30:
                    excluded.append({**item, 'reason': 'outside_native_16k_mono_PCM16_or_bounded_0_to_30_second_gate', 'duration_seconds': duration})
                    continue
            except (wave.Error, EOFError, OSError):
                excluded.append({**item, 'reason': 'audio_header_unreadable'})
                continue
            audio_sha = sha(audio)
            if audio_sha in hashes:
                excluded.append({**item, 'reason': 'audio_hash_already_seen', 'evidence': sorted(hashes[audio_sha])})
                continue
            rank = hashlib.sha256((args.seed+'|'+config+'|'+str(row['id'])+'|'+name).encode()).hexdigest()
            eligible.append((rank, row, audio, audio_sha, duration, rate, channels, frames))
        available_unique_sentences = len({str(x[1]['id']) for x in eligible})
        selected = []
        for rank, row, audio, audio_sha, duration, rate, channels, frames in sorted(eligible, key=lambda x:x[0]):
            sid = str(row['id'])
            if sid in selected_sentences:
                continue
            if len(selected) >= args.count:
                break
            selected_sentences.add(sid)
            selected.append({'dataset':'fleurs', 'language':config.split('_')[0],
                'sample_id':'fleurs_'+config+'_'+audio.stem, 'audio_path':relative(audio),
                'sha256':audio_sha, 'duration_seconds':duration, 'sample_rate':rate, 'channels':channels,
                'frames':frames, 'reference_text':row['transcription'].strip(), 'reference_turns':[],
                'metadata':{'configuration':config, 'split':'test', 'annotation_source':relative(tsv),
                    'annotation_sha256':sha(tsv), 'source_row_id':sid, 'source_row_idx':row.get('idx'),
                    'source_line':row['_line'], 'selection_rank_sha256':rank,
                    'selection_policy':'seeded hash rank, one recording per sentence per language, no outcome-based selection',
                    'audio_subtype':'PCM16', 'same_language_previously_used_sentence_excluded':True,
                    'scope':'prepared individual ASR test utterance; inference NOT EXECUTED'}})
        samples.extend(selected)
        groups.append({'dataset':'fleurs','configuration':config,'language':config.split('_')[0],
            'requested':args.count,'selected':len(selected),'eligible_recordings':len(eligible),
            'eligible_unique_sentence_ids':available_unique_sentences,
            'status':'PREPARED_NOT_EXECUTED' if len(selected)==args.count else 'INSUFFICIENT_UNUSED_SENTENCES',
            'duration_seconds':sum(x['duration_seconds'] for x in selected)})
    save(args.output/'exclusions.json', {'audio_hashes':sorted(hashes), 'filenames':sorted(names),
        'excluded_sentence_ids_by_configuration':{k:sorted(v) for k,v in sentence_ids.items()},
        'excluded_candidate_records':excluded,'historical_evidence':evidence})
    manifest={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'source_code_sha256':sha(__file__),
        'status':'PREPARED_NOT_EXECUTED' if all(x['selected']==args.count for x in groups) else 'PARTIAL_PREPARATION',
        'inference_executed':False,'downloads':False,'seed':args.seed,'requested_per_language':args.count,
        'groups':groups,'samples':samples,'exclusion_artifact':'exclusions.json',
        'protocol':'Original PCM16 test clips. Exclude known historical audio and current704-clip merged cohort plus alternate same-language recordings of their sentence IDs. Cross-language parallel sentences are not assumed acoustically equivalent.',
        'execution_gate':'Prepared cohort only: use a frozen explicitly approved REAL profile; diagnostic controls remain excluded. No completion or accuracy claim follows from preparation.'}
    save(args.output/'manifest.json',manifest)
    report=['# Prepared next individual FLEURS cohort','',
        'No inference, downloads or pipeline/configuration changes. Original native16-bit audio only.','',
        '| Language | Requested | Selected | Available unique unused sentences | Duration (s) | Status |',
        '|---|---:|---:|---:|---:|---|']
    for g in groups:
        report.append(f"| {g['configuration']} | {g['requested']} | {g['selected']} | {g['eligible_unique_sentence_ids']} | {g['duration_seconds']:.3f} | {g['status']} |")
    report.extend(['','This preparation does not certify official provenance beyond the existing local test mirror. No recognition accuracy is claimed. Historical convenience samples and altered merged results remain separate. Missing capacity is explicit; no duplicate or fabricated samples fill a shortfall.','',
        'The exclusion snapshot cannot include manual tests performed after its timestamp. Refresh exclusions before launching if additional manual tests occur.',''])
    (args.output/'PREPARATION.md').write_text('\n'.join(report),encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'samples':len(samples),'groups':groups,'artifact':relative(args.output/'manifest.json')}))

if __name__=='__main__':
    main()
