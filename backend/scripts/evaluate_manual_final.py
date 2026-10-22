"""Score saved manual production outputs only; never invokes an AI model.

Filename/duration matches without a surviving upload hash are explicitly exploratory.
AMI chronological WER is an overlap-sensitive proxy, not official AMI ASR scoring.
"""
import argparse, csv, json, sys
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/scripts'))
from evaluate_saved_research import digest, edit_metrics, geometry, diarization, normalize_text

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    data=json.loads(args.export.read_text(encoding='utf-8'))
    refs={}
    for path in (ROOT/'data/benchmarks/fleurs').glob('*/test.tsv'):
        with path.open(encoding='utf-8') as f:
            for r in csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE):
                if r.get('path') and r.get('transcription'):
                    refs[Path(r['path']).name]=(r['transcription'],path,path.parent/'audio/test'/Path(r['path']).name)
    previous=ROOT/'benchmark results/research_reuse_20261020/sources/research_reuse_20261020/saved_database_exports.json'
    historical={}
    if previous.exists():
        for r in json.loads(previous.read_text(encoding='utf-8'))['meetings']:
            if r.get('canonical') and r.get('audio',{}).get('sha256'):
                historical[r['canonical']['id']]=r
    results=[]
    for item in data['meetings']:
        m=item['meeting'];a=item['audio'] or {};c=item['canonical'];segs=item['segments']
        r={'meeting_id':m['id'],'title':m['title'],'language':m['language'],'meeting_status':m['status'],
           'canonical_transcript_id':c['id'] if c else None,'audio_filename':a.get('file_name'),
           'duration_seconds':a.get('duration_seconds'),'segment_count':len(segs),
           'job_ids':[j['id'] for j in item['jobs']],
           'failed_attempts':[{'job_id':j['id'],'error':j['error']} for j in item['jobs'] if j['status']=='failed'],
           'WER':None,'CER':None,'DER':None,'JER':None,'dataset':'NOT VERIFIED',
           'audio_identity':'NOT VERIFIED: original uploaded file unavailable on replacement instance',
           'timestamp_error':'NOT VERIFIED','accuracy_status':'NOT VERIFIED'}
        if not c or not segs:
            r['reason']='No nonempty final transcript; never scored as zero error';results.append(r);continue
        hyp=' '.join(s['original_text'] for s in segs)
        r['canonical_matches_segment_text']=normalize_text(hyp)==normalize_text(c['full_text'])
        turns,quality=geometry(segs);r['segment_validation']=quality
        r['warnings']=(c.get('provenance') or {}).get('quality_warnings',[])
        r['overlap_resolution']=(c.get('provenance') or {}).get('overlap_resolution')
        old=historical.get(c['id'])
        sha=a.get('sha256')
        if old and old['canonical']['full_text']==c['full_text']:
            sha=old['audio']['sha256'];r['hash_evidence_source']=str(previous.relative_to(ROOT))
        r['audio_sha256']=sha
        fname=a.get('file_name') or '';reference=None;refturns=None;audio=None;annotations=[]
        if fname in refs:
            reference,annotation,audio=refs[fname];annotations=[annotation];r['dataset']='FLEURS'
        elif fname.startswith('hi_'):
            annotation=ROOT/'data/benchmarks/indicsuperb/hi/known/transcript.txt'
            if annotation.exists():
                table=dict(line.split('\t',1) for line in annotation.read_text(encoding='utf-8').splitlines() if '\t' in line)
                reference=table.get(Path(fname).stem)
                audio=annotation.parent/'audio'/fname;annotations=[annotation]
                r.update(dataset='Kathbath within IndicSUPERB',dataset_independence='Not a second independent Kathbath dataset')
        elif fname.startswith('vox_'):
            annotation=ROOT/'data/benchmarks/voxconverse/rttm_recovered'/Path(fname).with_suffix('.rttm')
            candidates=list((ROOT/'data/benchmarks/voxconverse').rglob(fname))
            audio=candidates[0] if len(candidates)==1 else None
            if annotation.exists():
                refturns=[]
                for line in annotation.read_text().splitlines():
                    x=line.split()
                    if x and x[0]=='SPEAKER':refturns.append({'start':float(x[3]),'end':float(x[3])+float(x[4]),'speaker':x[7]})
                annotations=[annotation];r['dataset']='VoxConverse'
        elif fname.startswith('ES') and fname.endswith('.Mix-Headset.wav'):
            name=fname.split('.')[0];audio=ROOT/'data/audio/raw'/fname;words=[];refturns=[]
            for path in sorted((ROOT/'data/benchmarks/ami').rglob(name+'.*.words.xml')):
                annotations.append(path)
                for n in ET.parse(path).getroot().iter():
                    if n.tag.split('}')[-1]=='w' and 'starttime' in n.attrib and 'endtime' in n.attrib:
                        word=''.join(n.itertext()).strip()
                        if word:words.append((float(n.attrib['starttime']),float(n.attrib['endtime']),word))
            for path in sorted((ROOT/'data/benchmarks/ami').rglob(name+'.*.segments.xml')):
                annotations.append(path)
                for n in ET.parse(path).getroot().iter():
                    start=n.attrib.get('transcriber_start',n.attrib.get('starttime'));end=n.attrib.get('transcriber_end',n.attrib.get('endtime'))
                    if n.tag.split('}')[-1]=='segment' and start is not None and end is not None and float(end)>float(start):
                        refturns.append({'start':float(start),'end':float(end),'speaker':path.name.split('.')[1]})
            if words:reference=' '.join(w[2] for w in sorted(words));r['dataset']='AMI'
            r['ASR_protocol']='EXPLORATORY chronological word proxy; simultaneous reference words interleave; not official AMI WER'
        elif fname=='fleur en-us-50-400.wav':
            manifest=ROOT/'benchmark results/merged_fleurs_20261021/merged_manifest.json'
            r['reason']='Merged altered waveform: use dedicated constituent mapping; excluded from native-utterance scores'
        if audio and audio.is_file():
            import soundfile as sf
            info=sf.info(audio);r['reference_audio_duration']=info.duration
            r['filename_duration_match']=bool(a.get('duration_seconds') is not None and abs(info.duration-a['duration_seconds'])<max(.03,1/info.samplerate))
            if sha and digest(audio)==sha:r['audio_identity']='VERIFIED_HASH_MATCH'
            elif not r['filename_duration_match']:
                r['reason']='Reference filename matches but duration differs';results.append(r);continue
        elif reference is not None or refturns:
            r['reason']='Required matching local audio unavailable';results.append(r);continue
        r['reference_annotations']=[{'path':str(x.relative_to(ROOT)),'sha256':digest(x)} for x in annotations]
        r['accuracy_status']='VERIFIED_HASH_MATCHED_TEXT_METRIC' if r['audio_identity']=='VERIFIED_HASH_MATCH' else 'EXPLORATORY_FILENAME_DURATION_MATCH_ONLY'
        if reference is not None and not quality['out_of_order']:
            r.update(edit_metrics(reference,hyp))
        if refturns and turns and a.get('duration_seconds') and not quality['invalid_intervals']:
            scores=diarization(refturns,turns,a['duration_seconds']);r['diarization_metrics']=scores
            r['DER']=scores['overlap_included']['DER'];r['JER']=scores['overlap_included']['JER']
            r['diarization_status']='DIAGNOSTIC_UNRESOLVED_SPEAKER_BUCKET' if quality['unresolved_segments'] else 'FINAL_TRANSCRIPT_TURN_PROTOCOL'
        if not r['WER'] and r['DER'] is None:r['accuracy_status']='NOT VERIFIED'
        results.append(r)
    summary={'source_export_sha256':digest(args.export),'evaluator_sha256':digest(__file__),'inference_executed':False,
      'meetings':len(results),'completed_with_canonical':sum(bool(r['canonical_transcript_id']) for r in results),
      'normalization':'NFC/casefold; retain Unicode letters/marks/numbers, punctuation to spaces, collapse whitespace; CER removes spaces; no transliteration or spelling guesses',
      'metric_implementation':'jiwer counts, RapidFuzz exact-distance crosscheck; rates may exceed 100%; no language/profile pooling',
      'limitations':['Lost uploaded files prevent new hash verification; filename/duration scores are conditional exploratory only',
       'Only current canonical output evaluated, not overwritten historical uploads',
       'AMI WER is chronological proxy, not official speaker-attributed ASR protocol',
       'DER/JER use final transcript spans, collar0.25/fullaudioUEM; unresolved labels remain diagnostic',
       'No representative conference acceptance or accuracy improvement claim'], 'samples':results}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['title','dataset','language','meeting_status','audio_filename','segment_count','WER','CER','DER','JER','accuracy_status','audio_identity','meeting_id','canonical_transcript_id']
    with (args.output/'samples.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in results:
            row={k:r.get(k) for k in fields}
            for k in ['WER','CER']:row[k]=r[k]['rate'] if r[k] else None
            writer.writerow(row)
    report=['# Saved manual test evaluation','',f"{len(results)} meetings; {summary['completed_with_canonical']} with canonical output. No inference rerun.",'',
     '**Conditional exploratory scores:** surviving DB output is real, but new audio hashes are unavailable after replacing the instance. Verified historical hash links are flagged individually. Failed runs are not zero-error results.','',
     '| Meeting | Dataset | WER | CER | DER | JER | Evidence |','|---|---|---:|---:|---:|---:|---|']
    def pct(v):return 'NOT VERIFIED' if v is None else f'{v:.2%}'
    for r in results:
        if not r['audio_filename']:continue
        report.append('| '+ ' | '.join([r['title'],r['dataset'],pct(r['WER']['rate'] if r['WER'] else None),pct(r['CER']['rate'] if r['CER'] else None),pct(r['DER']),pct(r['JER']),r['accuracy_status']])+' |')
    report+=['','## Protocol',summary['normalization'],summary['metric_implementation'],'','## Limitations']+['- '+x for x in summary['limitations']]
    report+=['','## Failures']
    for r in results:
        for j in r['failed_attempts']:report.append(f"- {r['title']} / {j['job_id']}: {j['error']}")
    (args.output/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps({'meetings':len(results),'WER_scored':sum(bool(r['WER']) for r in results),'DER_scored':sum(r['DER'] is not None for r in results),'inference_executed':False}))
if __name__=='__main__':main()
