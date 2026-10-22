"""Verify actual user-merged FLEURS audio against original clips; no AI inference.

The supplied merges are PCM_U8 conversions of PCM16 inputs. Reference assignment
requires exact equality to that documented conversion for EVERY waveform sample.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ('merged_fleurs_hi_50_200', 'hi', 'hi_in', 50, 200, 'fleur hi-in-50-200(1).wav'),
    ('merged_fleurs_mr_0_100', 'mr', 'mr_in', 0, 100, 'fleur marathi-in-0-100.wav'),
    ('merged_fleurs_bn_0_100', 'bn', 'bn_in', 0, 100, 'fleur bn-in-0-100.wav'),
    ('merged_fleurs_en_50_400', 'en', 'en_us', 50, 400, 'fleur en-us-50-400.wav'),
]

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def rel(path):
    return Path(path).relative_to(ROOT).as_posix()

def verify(case):
    import numpy as np
    import soundfile as sf
    sid, language, config, first, last, filename = case
    folder = ROOT / 'data/benchmarks/fleurs'
    audio = folder / filename
    info = sf.info(audio)
    tsv = folder / config / 'test.tsv'
    with tsv.open(encoding='utf-8') as f:
        refs = {Path(row['path']).name: row for row in
                csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
                if row.get('path') and row.get('transcription')}
    record = {
        'sample_id': sid, 'dataset': 'fleurs_user_merged', 'language': language,
        'audio_path': rel(audio), 'audio_filename': filename,
        'sha256': sha(audio), 'duration_seconds': info.duration,
        'sample_rate': info.samplerate, 'channels': info.channels,
        'frames': info.frames, 'size_bytes': audio.stat().st_size,
        'audio_subtype': info.subtype, 'reference_text': None,
        'reference_turns': [], 'reference_intervals': [],
        'metadata': {
            'configuration': config, 'split': 'test',
            'annotation_source': rel(tsv), 'annotation_sha256': sha(tsv),
            'intended_inclusive_range': [first, last],
            'scope': 'user-concatenated clips with 8-bit quantization; not unaltered official FLEURS utterance protocol',
            'conversion_validated': 'floor signed PCM16 / 256 then multiply 256, compared as int16',
            'audio_time_compressed': False,
            'DER': 'NOT VERIFIED: no speaker ground truth for concatenated utterances',
            'JER': 'NOT VERIFIED: no speaker ground truth for concatenated utterances',
            'timestamp_accuracy': 'NOT VERIFIED: utterance clip edges are not speech/word boundaries',
            'reference_text_is_translation': False,
        },
    }
    if info.channels != 1 or info.samplerate != 16000 or info.subtype != 'PCM_U8':
        record.update(status='BLOCKED', reason='Unexpected merged waveform format; no guessed reference')
        return record
    offset = 0
    mismatches = 0
    text = []
    with sf.SoundFile(audio) as merged:
        for index in range(first, last+1):
            name = f'{config}_{index:05d}.wav'
            source = folder / config / 'audio/test' / name
            original_info = sf.info(source)
            if (original_info.samplerate, original_info.channels, original_info.subtype) != (16000, 1, 'PCM_16'):
                raise ValueError('Unexpected original waveform format: ' + rel(source))
            if name not in refs:
                raise ValueError('Missing actual reference row: ' + name)
            original, _ = sf.read(source, dtype='int16')
            actual = merged.read(len(original), dtype='int16')
            expected = (original.astype(np.int32) // 256 * 256).astype(np.int16)
            diff = len(expected) if len(actual) != len(expected) else int(np.count_nonzero(expected != actual))
            mismatches += diff
            row = refs[name]
            interval = {
                'clip_filename': name, 'source_audio': rel(source),
                'source_audio_sha256': sha(source), 'source_row_id': row.get('id'),
                'source_row_idx': row.get('idx'), 'frames': len(original),
                'start_frame': offset, 'end_frame': offset+len(original),
                'start_time': offset/16000, 'end_time': (offset+len(original))/16000,
                'reference_text': row['transcription'],
                'waveform_mismatching_samples_after_documented_conversion': diff,
            }
            record['reference_intervals'].append(interval)
            text.append(row['transcription'])
            offset += len(original)
        extra = len(merged.read(1, dtype='int16'))
    valid = offset == info.frames and not mismatches and not extra
    record.update(status='VERIFIED' if valid else 'BLOCKED',
                  clip_count=last-first+1, validated_source_frames=offset,
                  mismatching_samples_after_conversion=mismatches,
                  reference_order_verified=valid, coverage_has_no_gaps=valid,
                  exact_original_PCM16_audio=False,
                  reason=None if valid else 'Waveform/order/frame mismatch; no aggregate reference assigned')
    if valid:
        record['reference_text'] = ' '.join(text)
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT/'benchmark results/merged_fleurs_20261021')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'merged_manifest.json'
    if target.exists():
        raise SystemExit('Preserve existing merged_manifest.json; inspect it rather than overwrite')
    samples = [verify(case) for case in CASES]
    result = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'source_code_sha256': sha(__file__), 'inference_executed': False,
        'status': 'VERIFIED' if all(r['status']=='VERIFIED' for r in samples) else 'BLOCKED',
        'samples': samples, 'total_source_clips': sum(r.get('clip_count', 0) for r in samples),
        'total_duration_seconds': sum(r['duration_seconds'] for r in samples),
        'warning': 'All merged files use 8-bit quantization. Do not pool scores with original PCM16 utterance evaluations or claim original FLEURS test protocol.',
    }
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    lines = ['# User-merged FLEURS reference validation', '',
             result['warning'], '',
             '| File | Clips (inclusive) | Duration | Format | Reference order |',
             '|---|---:|---:|---|---|']
    for r in samples:
        lines.append(f"| {r['audio_filename']} | {r.get('clip_count','NOT VERIFIED')} | {r['duration_seconds']:.3f}s | {r['audio_subtype']} | {r['status']} |")
    lines += ['', 'Each complete source waveform was compared sample-for-sample after the explicit PCM16-to-PCM_U8 floor conversion. No resampling, inserted gaps, ordering difference or truncated ending was found when VERIFIED. Sources and merged files were not modified.',
              '', 'Native `transcription` rows are used, not translated English captions. Exact source filenames, TSV row IDs, audio/annotation SHA-256 values, frame offsets and per-clip reference text are retained in merged_manifest.json.',
              '', 'These are independent read-speech clips concatenated as a long recording, not a naturally continuous multi-party meeting. Clip edges are source boundaries, not validated word timing. DER/JER and word timestamp accuracy remain NOT VERIFIED. No AI inference ran during this check.', '']
    with (args.output/'REFERENCE_VALIDATION.md').open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(json.dumps({'status':result['status'], 'clips':result['total_source_clips'],
                      'duration_seconds':result['total_duration_seconds'],
                      'manifest':rel(target), 'inference_executed':False}))

if __name__ == '__main__':
    main()
