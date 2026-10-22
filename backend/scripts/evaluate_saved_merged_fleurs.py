"""Offline evaluation of saved concatenated FLEURS recordings with source intervals.

Counts source utterances separately from inference recordings. Never reruns ASR,
splits text by guessed word timing, or treats source clip edges as speaker labels.
"""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/scripts'))
from evaluate_saved_research import digest,edit_metrics,geometry,normalize_text

def alignment_groups(reference_intervals,segments):
    """Connected temporal-overlap groups; boundary-spanning text stays whole."""
    n=len(reference_intervals);parent=list(range(n+len(segments)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for j,s in enumerate(segments):
        start,end=s['start_time_ms']/1000,s['end_time_ms']/1000
        for i,r in enumerate(reference_intervals):
            if min(end,r['end_time'])>max(start,r['start_time']):parent[find(n+j)]=find(i)
    groups={}
    for i in range(n+len(segments)):
        group=groups.setdefault(find(i),{'reference_indexes':[],'hypothesis_indexes':[]})
        group['reference_indexes' if i<n else 'hypothesis_indexes'].append(i if i<n else i-n)
    return list(groups.values())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'));saved=json.loads(args.export.read_text(encoding='utf-8'))
    results=[];aligned=[]
    for sample in manifest['samples']:
        refs=sample['reference_intervals'];assert len(refs)==sample['clip_count']
        if not sample['coverage_has_no_gaps'] or not sample['reference_order_verified']:raise ValueError('Unverified concatenation ordering')
        if any(abs(a['end_time']-b['start_time'])>.0001 for a,b in zip(refs,refs[1:])):raise ValueError('Reference interval gap')
        matches=[r for r in saved['meetings'] if (r['audio'] or {}).get('file_name')==sample['audio_filename']]
        result={'sample_id':sample['sample_id'],'language':sample['language'],'source_utterances':len(refs),
            'inference_recordings':len(matches),'duration_seconds':sample['duration_seconds'],'WER':None,'CER':None,
            'status':'NOT VERIFIED','audio_identity':'NOT VERIFIED','DER':'NOT VERIFIED','JER':'NOT VERIFIED',
            'timestamp_accuracy':'NOT VERIFIED: clip boundaries are not acoustic word alignments'}
        if len(matches)!=1:
            result['reason']='Missing or ambiguous saved recording';results.append(result);continue
        row=matches[0];audio=row['audio'];canonical=row['canonical'];segments=row['segments']
        result.update(meeting_id=row['meeting']['id'],meeting_status=row['meeting']['status'],
            canonical_transcript_id=canonical['id'] if canonical else None,job_ids=[j['id'] for j in row['jobs']],
            failures=[j['error'] for j in row['jobs'] if j['error']])
        if abs(audio['duration_seconds']-sample['duration_seconds'])>.03:raise ValueError('Saved merged recording duration mismatch')
        if audio.get('sha256'):
            if audio['sha256']!=sample['sha256']:raise ValueError('Saved merged waveform hash mismatch')
            result['audio_identity']='HASH_VERIFIED'
        else:result['audio_identity']='CONDITIONAL_FILENAME_DURATION_ONLY; original upload hash unavailable'
        if not canonical or not segments:
            result.update(status='FAILED_OR_PARTIAL; no final transcript',scored_source_utterances=0)
            results.append(result);continue
        turns,quality=geometry(segments);result['segment_validation']=quality
        if quality['out_of_order'] or quality['invalid_intervals']:raise ValueError('Saved transcript chronology/bounds invalid')
        text=' '.join(s['original_text'] for s in segments)
        if normalize_text(text)!=normalize_text(canonical['full_text']):raise ValueError('Canonical/segment text mismatch')
        reference=' '.join(r['reference_text'] for r in refs)
        if normalize_text(reference)!=normalize_text(sample['reference_text']):raise ValueError('Manifest full reference mismatch')
        result.update(edit_metrics(reference,text),status='EXPLORATORY_CONCATENATED_RECORDING',scored_source_utterances=len(refs))
        groups=alignment_groups(refs,segments);result['temporal_comparison_groups']=len(groups)
        result['individual_utterance_groups']=sum(len(g['reference_indexes'])==1 for g in groups)
        for index,g in enumerate(groups):
            rr=[refs[i] for i in g['reference_indexes']];hh=[segments[i] for i in g['hypothesis_indexes']]
            rtext=' '.join(r['reference_text'] for r in rr);htext=' '.join(s['original_text'] for s in hh)
            metrics=edit_metrics(rtext,htext) if normalize_text(rtext) else None
            aligned.append({'sample_id':sample['sample_id'],'group':index,'reference_clip_ids':';'.join(r['clip_filename'] for r in rr),
                'reference_count':len(rr),'hypothesis_segment_ids':';'.join(s['id'] for s in hh),
                'alignment_status':'UNMATCHED_HYPOTHESIS' if not rr else ('UNMATCHED_REFERENCE' if not hh else ('SINGLE_UTTERANCE_GROUP' if len(rr)==1 else 'BOUNDARY_SPANNING_GROUP')),
                'reference_text':rtext,'hypothesis_text':htext,'normalized_reference':normalize_text(rtext),'normalized_hypothesis':normalize_text(htext),
                'WER':metrics['WER']['rate'] if metrics else None,'CER':metrics['CER']['rate'] if metrics else None,
                'substitutions':metrics['WER']['substitutions'] if metrics else 0,'deletions':metrics['WER']['deletions'] if metrics else 0,
                'insertions':metrics['WER']['insertions'] if metrics else len(normalize_text(htext).split()),
                'note':'Temporal grouping is exploratory: uncalibrated MOSS turn times; crossing hypotheses never split by guessed word timings'})
        results.append(result)
    summary={'inference_executed':False,'source_export_sha256':digest(args.export),'source_manifest_sha256':digest(args.manifest),
        'evaluator_sha256':digest(__file__),'source_utterances':sum(s['source_utterances'] for s in results),
        'inference_recordings':sum(s['inference_recordings'] for s in results),'samples':results,
        'normalization':'Same native-script NFC/casefold/Unicode punctuation policy as evaluate_saved_research; no transliteration',
        'limitations':['Counts of constituent clips do not equal independent inference trials',
          'Merged input is documented PCM_U8 conversion, not original PCM16 utterance condition',
          'No fixed source speaker identities, calibrated timestamp accuracy, DER or JER',
          'Temporal groups can span multiple clips; no fabricated per-clip word allocation',
          'Failed Hindi/Marathi/Bengali files contribute failures, never zero WER or completed utterance counts',
          'Missing original uploaded hashes make pairing conditional; not held-out publication acceptance']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if aligned:
        with (args.output/'time_aligned_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(aligned[0]));w.writeheader();w.writerows(aligned)
    report=['# Concatenated FLEURS saved-output evaluation','',
      'Source clips are counted individually; inference recordings are counted separately. No audio rerun.','',
      '| Language | Source clips | Recording status | WER | CER |','|---|---:|---|---:|---:|']
    for s in results:
        fmt=lambda k:f"{s[k]['rate']:.2%}" if s[k] else 'NOT VERIFIED'
        report.append(f"| {s['language']} | {s['source_utterances']} | {s['status']} | {fmt('WER')} | {fmt('CER')} |")
    report+=['','## Limitations']+['- '+x for x in summary['limitations']]
    report+=['','Corpus WER/CER use aggregate edit counts over the complete verified reference order. Temporal-group values are supplementary, not blindly averaged into corpus WER. Failed files are retained in the denominator of recording outcomes, without invented text metrics.']
    (args.output/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps({'source_utterances':summary['source_utterances'],'inference_recordings':summary['inference_recordings'],'scored_recordings':sum(bool(r['WER']) for r in results),'inference_executed':False}))
if __name__=='__main__':main()
