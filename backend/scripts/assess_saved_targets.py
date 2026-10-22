"""Create a target assessment from immutable offline evaluation results; no inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {'WER': .15, 'CER': .08, 'DER': .10, 'JER': .20}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    folder = args.evidence.resolve()
    sources = [folder/'research_recheck/summary.json', folder/'manual_recheck/summary.json',
               ROOT/'benchmark results/manual_final_20261021/merged_evaluation_01/summary.json']
    records = []
    for source in sources:
        data = json.loads(source.read_text(encoding='utf-8'))
        for row in data.get('groups', data.get('samples', [])):
            for metric, target in TARGETS.items():
                value = row.get(metric)
                value = value.get('rate') if isinstance(value, dict) else value
                if not isinstance(value, (int, float)):
                    continue
                records.append({'source': str(source.relative_to(ROOT)),
                    'dataset': row.get('dataset', 'merged FLEURS'), 'language': row.get('language'),
                    'identity': row.get('audio_identity', row.get('status')),
                    'configuration_id': row.get('configuration_id'),
                    'meeting_id': row.get('meeting_id'),
                    'label': row.get('title', row.get('sample_id', str(row.get('sample_ids')))),
                    'sample_count': row.get('samples', row.get('source_utterances', 1)),
                    'metric': metric, 'value': value, 'percent': value*100,
                    'target_exclusive': target, 'numeric_target_status': 'Pass' if value < target else 'Fail',
                    'qualification': row.get('diarization_status') if metric in ('DER','JER') else row.get('accuracy_status', row.get('status'))})
    table = [
        ['WER', '<15%', '15.57% (English FLEURS, 10 clips); 54.61% merged English (conditional)', 'Fail', '10-clip corpus: 33 edits / 212 reference words; merged is a separate condition.'],
        ['CER', '<8%', '12.61% (same 10 clips); 41.12% merged English (conditional)', 'Fail', '127 edits / 1,007 reference characters; spaces excluded.'],
        ['DER', '<10%', '2.23%, 35.91%, 27.59%, 22.63% (four VoxConverse clips)', 'Fail', 'One clip passes; three fail. Different saved profiles; no pooled application score.'],
        ['JER', '<20%', '0.94%, 69.56%, 51.56%, 76.92% (same clips)', 'Fail', 'One clip passes; unresolved-speaker cases are diagnostic only.'],
        ['Code-switching error rate', '<25%', 'Unavailable', 'Unavailable', 'No validated definition, language-tagged token references and matched predictions. WER is not this metric.'],
        ['Timestamp error', '<50 ms', 'Unavailable', 'Unavailable', 'No reliable corresponding acoustic boundary alignment. RTTM collar is 250 ms and cannot establish 50 ms accuracy.'],
        ['Overlap detection F1', '>=75%', 'Unavailable', 'Unavailable', 'RTTM references exist, but validated, time-aligned detector predictions/scoring protocol are absent. Transcript overlap is not detector F1.'],
        ['LID accuracy', '>90%', 'Unavailable', 'Unavailable', 'Declared language/script validation is not blind acoustic identification. No independent labeled prediction pairs.'],
    ]
    result = {'inference_executed': False, 'model_changes': False,
        'scope': 'Historical saved profiles; not acceptance of current untested changes. No pooling across languages, profiles, or duplicate saved copies.',
        'sources': [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
        'targets': [dict(zip(['metric','target','actual','status','reason'], r)) for r in table],
        'sample_metric_comparisons': records}
    with (folder/'assessment.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with (folder/'sample_target_comparisons.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    report = ['# ABCI-MI measured target assessment — 22 October 2026', '',
        '**Overall: the eight targets are not demonstrated.** Historical measured failures exist for WER, CER, DER and JER; four other targets remain unavailable. A passing clip does not establish application-wide performance.', '',
        result['scope'], '', '| Metric | Target | Measured evidence | Status | Reason |', '|---|---|---|---|---|']
    report += ['| '+' | '.join(r)+' |' for r in table]
    report += ['', '## Scope and reproducibility',
        '- Recomputed saved research outputs (39 attempts, 25 unique audio hashes) and 31 manual meetings. These overlap and must not be added as independent samples. No new GPU inference.',
        '- Manual outputs contain 23 canonical transcripts; only 15 have usable text comparisons and seven have diarization comparisons. Missing references/failed runs are not zero errors.',
        '- Research English FLEURS cohort uses configuration c4c873e408c0. Other historical profiles remain separate in the CSV, including exploratory alternative-model trials; they are not all current MOSS production results.',
        '- WER/CER: jiwer edit counts crosschecked against RapidFuzz; aggregate counts, not mean utterance rates. NFC, casefold, Unicode letters/marks/numbers retained, punctuation to spaces, whitespace collapsed; CER excludes spaces. No guessed transliteration or spelling correction. Rates may exceed 100%.',
        '- DER/JER: pyannote.metrics, full audio UEM, 0.25-second collar; overlap-included values shown, overlap-excluded values saved separately. Same-speaker intervals unioned. Final transcript spans are scored, not independent raw PyAnnote stage accuracy. UNRESOLVED labels remain diagnostic.',
        '- VoxConverse values above are Test2, Test3, Test4, Test5 in that order, linked to historical audio hashes. Posthoc recovered outputs are not a held-out acceptance set.',
        '- Conditional merged English: 351 original utterances in one converted PCM_U8 recording, not 351 independent inference runs. Hindi/Marathi/Bengali merged runs failed and have no final text score.',
        '- AMI latest conditional chronological proxies: ES2004c WER 37.06%, CER 31.77%, DER 37.19%, JER 33.82%; ES2002a 50.58%, 44.40%, 59.25%, 59.09%; ES2002b 39.00%, 34.12%, 43.23%, 38.58%. Missing original upload hashes and overlapping word ordering limit publication use.',
        '- BIVA spreadsheet comparison is not authoritative ASR accuracy: Romanized/native Hindi differences, uncertain utterance alignment and reference speaker inconsistencies. Its exploratory literal error rates are excluded from target acceptance.', '',
        '## Largest gaps and missing evidence',
        '1. Recognition generalization: 10 English clips already miss both targets; merged/long meeting scores are much worse. Short Hindi successes do not establish Bengali, Marathi, Malayalam or German accuracy. Saved Bengali/Tamil pilots have large errors; see profile-specific CSV.',
        '2. Speaker consistency: three of four hash-linked VoxConverse cases miss DER/JER; unresolved cross-window identity and final transcript interval errors limit interpretation. DER is not speaker-count accuracy.',
        '3. Multilingual reliability: script-conflict failures are real failed outputs, not LID estimates or zero-error samples. Sarvam text normalization/translation cannot repair canonical ASR words.',
        '4. Code-switch benchmark needs an explicit metric (e.g. language-tagged token errors or switch-boundary errors), vetted native-script transcript, token language labels and evaluated predictions; MUCS adapter presence is not dataset/evaluation evidence.',
        '5. Timestamp gate needs manually checked acoustic word/utterance boundaries and one-to-one/text-aware alignment, with mean/median/tails and coverage. Existing nearest-boundary helper permits reused matches and returns zero on empty input; its default zeros are not accepted here.',
        '6. Overlap gate needs detector intervals, reference multi-speaker speech regions from RTTM, a declared time-based/event-based protocol, thresholds and TP/FP/FN. Existing interval conflicts and unresolved status do not establish F1.',
        '7. LID gate needs blind predictions compared with FLEURS labels; declared-language prompting leaks the answer and cannot establish independent acoustic LID.',
        '8. Local data/benchmarks contains AMI, FLEURS, IndicSUPERB/Kathbath and VoxConverse. AISHELL cache directory exists but no scored audio/reference pair was established; cache names alone prove neither completeness nor evaluation. DIHARD/Common Voice/MUCS have no scored evidence in these sources. Kathbath within IndicSUPERB is not a second independent corpus.', '',
        '## Models and design evidence',
        '- MOSS remains primary. Production implements its conditional-generation processor/parser; the original Conformer/CTC description is not the implemented model.',
        '- PyAnnote speaker-diarization-3.1 and voice reconciliation exist. EEND-EDA/ECAPA claims in the initial design are not established by implementation evidence.',
        '- Silero VAD exists; no trained PIT separator or independently validated acoustic forced aligner was established. Script checks are validation, not calibrated LID.',
        '- Current worker startup/healthy services are operational evidence only. These saved-output scores do not validate changes made after the corresponding inference runs.', '',
        '## Reproduce', '```powershell',
        '.runtime/python/python.exe backend/scripts/evaluate_saved_research.py --output "benchmark results/<fresh-folder>/research_recheck" --workers 2',
        '.runtime/python/python.exe backend/scripts/evaluate_manual_final.py --export "benchmark results/manual_final_20261021/saved_database_exports.json" --output "benchmark results/<fresh-folder>/manual_recheck"',
        '.runtime/python/python.exe backend/scripts/assess_saved_targets.py --evidence "benchmark results/<fresh-folder>"', '```', '',
        'Existing folders are never overwritten. The merged summary is reused with its hash recorded in assessment.json. All individual values and strict numeric target comparisons are in sample_target_comparisons.csv; numeric passes with conditional identity remain conditional evidence.']
    with (folder/'REPORT.md').open('x', encoding='utf-8') as f:
        f.write('\n'.join(report)+'\n')
    print(json.dumps({'comparisons':len(records),'report':str(folder/'REPORT.md'),'inference_executed':False}))


if __name__ == '__main__':
    main()
