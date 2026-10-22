"""Export manuscript pilot results without merged recordings or new inference."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'benchmark results/target_assessment_20261022/research_recheck'
OUT = ROOT/'benchmark results/individual_manuscript_20261022'


def main():
    OUT.mkdir(exist_ok=False)
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(SOURCE.glob('sample_*.json'))]
    # Fixed original cohort, not a subset chosen by achieved error rate.
    cohort = rows[:10]
    assert all(r['run_id'] == 'benchmark_fleurs_en_us_20261008T115951Z' for r in cohort)
    assert len({r['audio_sha256'] for r in cohort}) == 10
    assert all(r['configuration'] == cohort[0]['configuration'] for r in cohort)
    selected = [r for r in cohort if r['WER']['rate'] < .15 and r['CER']['rate'] < .08]
    def counts(metric):
        keys = ['substitutions', 'deletions', 'insertions', 'reference_count', 'errors']
        out = {k: sum(r[metric][k] for r in cohort) for k in keys}
        out['rate'] = out['errors']/out['reference_count']
        return out
    manual_path = ROOT/'benchmark results/target_assessment_20261022/manual_recheck/summary.json'
    manual = json.loads(manual_path.read_text(encoding='utf-8'))
    vox = next(r for r in manual['samples'] if r['title'] == 'Test 2')
    assert vox['audio_identity'] == 'VERIFIED_HASH_MATCH'
    assert vox['diarization_status'] == 'FINAL_TRANSCRIPT_TURN_PROTOCOL'
    details = []
    for r in rows:
        item = {k:r.get(k) for k in ['dataset','language','sample_id','run_id','audio_sha256','source','metric_status','diarization_status']}
        item['configuration_json'] = json.dumps(r.get('configuration',{}), ensure_ascii=False)
        for metric, threshold in [('WER',.15),('CER',.08)]:
            value = r.get(metric)
            item[metric] = value['rate'] if value else None
            item[metric+'_status'] = ('Pass' if value['rate'] < threshold else 'Fail') if value else 'Unavailable'
        details.append(item)
    with (OUT/'all_individual_attempts.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(details[0]));w.writeheader();w.writerows(details)
    summary = {'scope':'Historical individual-file pilot; selected best cases are not held-out aggregate acceptance',
        'new_inference_executed':False,'merged_recordings_included':False,
        'cohort_sample_ids':[r['sample_id'] for r in cohort],
        'cohort_audio_seconds':sum(r['duration_seconds'] for r in cohort),
        'cohort_configuration':cohort[0]['configuration'],
        'WER':counts('WER'),'CER':counts('CER'),'passing_both':len(selected),
        'selected_passing_cases':[{k:r[k] for k in ['sample_id','audio_sha256','WER','CER']} for r in selected],
        'selected_diarization_case':{k:vox[k] for k in ['meeting_id','canonical_transcript_id','audio_sha256','duration_seconds','DER','JER','diarization_status']},
        'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'summary.json',manual_path]},
        'unverified':['code-switching error','timestamp error','overlap detection F1','independent acoustic LID accuracy']}
    with (OUT/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    text = '''# Results and Analysis

## Evaluation protocol

We evaluated previously generated outputs for individually processed recordings; concatenated or merged recordings were excluded. The principal ASR pilot comprised ten distinct English FLEURS test utterances (sample IDs 00000–00009), processed with the same recorded MOSS configuration. These are historical convenience samples rather than a preregistered held-out acceptance study. Source audio identity and reference pairing were verified using saved hashes. Duplicate copies of experiments were not treated as independent observations. Other configurations and languages are retained separately in the supplementary individual-attempt inventory.

WER and CER were calculated from Levenshtein substitutions, deletions and insertions using jiwer, with exact-distance crosschecks using RapidFuzz. Corpus rates were obtained by dividing summed edit counts by summed reference units. Both texts received NFC Unicode normalization, case folding, punctuation-to-space conversion and whitespace normalization while retaining Unicode letters, marks and numbers. CER excluded spaces. No translation, guessed spelling correction or transliteration was applied.

Diarization was evaluated for a separately identified VoxConverse recording using pyannote.metrics, the full recording as the evaluation region, a 0.25-second collar and overlapping speech included. Same-speaker overlapping intervals were unioned. These values assess speaker-labeled final transcript intervals, not an isolated raw PyAnnote output or overlap detector.

## Overall individual-file ASR pilot

| Evaluation set | Files | WER (%) | CER (%) | WER <15%, CER <8% |
|---|---:|---:|---:|---|
| English FLEURS, individually processed | 10 | 15.57 | 12.61 | Neither corpus target met |

The cohort contained 212 reference words and 1,007 reference characters. Word errors consisted of nine substitutions, 24 deletions and no insertions (33 errors). Character errors consisted of 13 substitutions, 111 deletions and three insertions (127 errors). Deletions therefore constituted 72.7% of word errors and 87.4% of character errors. This identifies omissions as the dominant error category in this pilot, without establishing their causal mechanism.

Five of the ten files satisfied both ASR thresholds. This 5/10 threshold-pass count is descriptive and is not a statistical estimate of generalization across FLEURS languages. In particular, the corpus-level result does not satisfy the intended targets despite several successful individual outputs.

## Selected passing cases (post hoc; not aggregate benchmarks)

The following table provides the requested best observed individual-file results. Selection was based on achieved error rates and must be disclosed as such; these cases must not replace the complete-cohort table.

| Dataset | Individual file/sample | WER (%) | CER (%) | Interpretation |
|---|---|---:|---:|---|
'''
    for r in selected:
        text += f"| FLEURS English | {r['sample_id']} | {r['WER']['rate']*100:.2f} | {r['CER']['rate']*100:.2f} | Both thresholds met |\n"
    text += f'''
Two selected utterances exhibited exact normalized reference agreement (WER=0%, CER=0%). This is a file-specific observation and does not imply perfect recognition, 100% language-wide accuracy, or robustness to spontaneous multilingual meetings.

| Dataset | Individual recording | Duration (s) | DER (%) | JER (%) | Interpretation |
|---|---|---:|---:|---:|---|
| VoxConverse | vox_00002.wav | {vox['duration_seconds']:.2f} | {vox['DER']*100:.2f} | {vox['JER']*100:.2f} | DER <10% and JER <20% met for this recording |

The selected VoxConverse output met both diarization thresholds. Other evaluated recordings retained unresolved speaker identities and substantially higher diagnostic error rates. Thus, this successful recording does not establish dataset-wide diarization performance. The ASR and diarization successes were obtained on different recordings; they do not demonstrate that a single meeting satisfies all targets simultaneously.

## Multilingual scope and unavailable metrics

The broader saved inventory includes native-reference FLEURS and IndicSUPERB/Kathbath pilot attempts under multiple configurations. Their sample sizes and settings differ and include exploratory alternative-provider trials. They are not pooled into the MOSS cohort above. Several manually tested Hindi examples produced low errors, but missing original-upload hashes prevent treating those filename-matched examples as definitive publication benchmarks. IndicSUPERB/Kathbath audio must not be counted twice as independent corpora. No validated scores were established here for every supported language or every dataset listed in the interface.

Code-switching error rate, timestamp error below 50 ms, overlap detection F1 and independent acoustic language-identification accuracy remain unavailable. The required language-tagged references, reliable acoustic boundary correspondence, detector/reference interval pairs and blind LID predictions have not been established. A declared-language prompt or script-consistency check is not independent LID. The diarization collar does not demonstrate sub-50-ms boundary precision.

## Interpretation and limitations

These results demonstrate that the implementation can produce accurate transcripts and speaker assignments for selected individual inputs. However, the complete ten-file ASR cohort misses both recognition targets. The evidence therefore supports a preliminary feasibility claim, rather than a claim that the application consistently achieves the proposed multilingual and diarization criteria. Sample counts are small, configurations vary across historical experiments, and no controlled baseline comparison or confidence interval was established. Current fixes made after the saved inference runs are not validated by these results.

For manuscript reporting, retain the complete-cohort table as the principal result, label the best-case table as qualitative/selected-case evidence, and state unavailable metrics explicitly. Further held-out, fixed-configuration, language-stratified testing is required before making general multilingual accuracy or superiority claims.

## Reproducibility supplement

- `summary.json`: selected cases, cohort edit counts, audio hashes, configuration and source hashes.
- `all_individual_attempts.csv`: all 39 saved individual-file attempts, including failures of thresholds and separate configurations; repeated audio across configurations is not an independent sample.
- Reproduce with `.runtime/python/python.exe backend/scripts/write_individual_manuscript_results.py` into a fresh output folder (the script refuses to overwrite this folder).
- No merged recordings were scored or included. No new inference or model modification was performed.
'''
    (OUT/'RESULTS_AND_ANALYSIS.md').write_text(text,encoding='utf-8')
    print(json.dumps({'individual_attempts':len(rows),'fixed_cohort':len(cohort),'passing_both':len(selected),'output':str(OUT)}))


if __name__=='__main__':main()
