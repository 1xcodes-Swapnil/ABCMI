"""Resumable REAL production speech-stage benchmark; no UI or model changes."""
import argparse, asyncio, csv, hashlib, json, os, sys, time, uuid
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/scripts')]

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8');tmp.replace(path)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def overlapping(turns,duration):
    events=[]
    # Distinct speakers, not overlapping turns of the same speaker.
    for t in turns:
        a=max(0,float(t['start']));b=min(duration,float(t['end']))
        if b>a:events.extend([(a,t['speaker'],1),(b,t['speaker'],-1)])
    from collections import Counter
    counts=Counter();regions=[];last=0
    for at in sorted({x[0] for x in events}):
        if sum(v>0 for v in counts.values())>=2 and at>last:regions.append((last,at))
        for _,speaker,delta in (x for x in events if x[0]==at):counts[speaker]+=delta
        last=at
    return regions

def overlap_score(ref,hyp,duration):
    r,h=overlapping(ref,duration),overlapping(hyp,duration)
    tp=sum(max(0,min(b,d)-max(a,c)) for a,b in r for c,d in h)
    rs=sum(b-a for a,b in r);hs=sum(b-a for a,b in h)
    return {'protocol':'time-weighted distinct-speaker overlap, full audio UEM, no collar; raw PyAnnote turns',
            'TP_seconds':tp,'FP_seconds':hs-tp,'FN_seconds':rs-tp,
            'precision':tp/hs if hs else None,'recall':tp/rs if rs else None,
            'F1':2*tp/(rs+hs) if rs+hs else None}

def summarize(out,manifest):
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('*/metrics.json'))]
    groups=[]
    for key in sorted({(r['dataset'],r['language'],r['split']) for r in rows}):
        subset=[r for r in rows if (r['dataset'],r['language'],r['split'])==key]
        g=dict(zip(['dataset','language','split'],key));g.update(samples=len(subset),completed=sum(r['status']=='COMPLETED' for r in subset),failed=sum(r['status']!='COMPLETED' for r in subset),audio_hours=sum(r['duration_seconds'] for r in subset)/3600)
        for metric in ['WER','CER']:
            scored=[r[metric] for r in subset if r.get(metric)]
            n=sum(v['reference_count'] for v in scored);errors=sum(v['errors'] for v in scored)
            g[metric]={'rate':errors/n if n else None,'reference_count':n,'errors':errors,'scored_samples':len(scored)}
        ds=[r['diarization']['overlap_included'] for r in subset if r.get('diarization')]
        if ds:
            c=[d['DER_components_seconds'] for d in ds];total=sum(v['total'] for v in c)
            g['DER_micro']=sum(v['false alarm']+v['missed detection']+v['confusion'] for v in c)/total if total else None
            g['JER_macro_clip']=sum(d['JER'] for d in ds)/len(ds);g['diarization_scored_samples']=len(ds)
        measured=[r for r in subset if r['status']=='COMPLETED'];dur=sum(r['duration_seconds'] for r in measured)
        g['RTF_completed']=sum(r['processing_seconds'] for r in measured)/dur if dur else None
        groups.append(g)
    save(out/'summary.json',{'scope':manifest['scope'],'requested':len(manifest['samples']),'saved_results':len(rows),'groups':groups,'blockers':manifest.get('blockers',[]),'failures':[{'sample_id':r['sample_id'],'errors':r['errors']} for r in rows if r['errors']]})
    if rows:
        fields=['sample_id','dataset','language','split','status','duration_seconds','processing_seconds','RTF','WER_rate','CER_rate','DER','JER','overlap_F1','gpu_peak_allocated_bytes','cpu_rss_bytes']
        with (out/'per_clip.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for r in rows:
                d={k:r.get(k) for k in fields};d.update(WER_rate=(r.get('WER') or {}).get('rate'),CER_rate=(r.get('CER') or {}).get('rate'),DER=(r.get('diarization') or {}).get('overlap_included',{}).get('DER'),JER=(r.get('diarization') or {}).get('overlap_included',{}).get('JER'),overlap_F1=(r.get('overlap_detection') or {}).get('F1'));w.writerow(d)
    report=['# REAL individual-recording speech-stage benchmarks','',manifest['scope'],'','No merged recordings; no mock/fixture provider; no Gemini or standalone Sarvam comparison. Different historical profiles are not pooled.','',f"Saved {len(rows)} of {len(manifest['samples'])} requested results.",'','| Dataset | Language | Saved | Completed | WER | CER | DER micro | JER macro clip |','|---|---|---:|---:|---:|---:|---:|---:|']
    pct=lambda v:'Unavailable' if v is None else f'{v:.2%}'
    for g in groups:report.append(f"| {g['dataset']} | {g['language']} | {g['samples']} | {g['completed']} | {pct(g['WER']['rate'])} | {pct(g['CER']['rate'])} | {pct(g.get('DER_micro'))} | {pct(g.get('JER_macro_clip'))} |")
    report+=['','## Protocol and limitations','WER/CER: jiwer edit counts crosschecked with RapidFuzz; NFC/casefold, Unicode L/M/N retained, punctuation to spaces, CER excludes spaces; no transliteration. AMI chronological word order is an overlap-sensitive proxy, not official speaker-attributed WER. DER/JER: pyannote.metrics, 0.25 s collar, full audio UEM, overlap included/excluded separately. Raw PyAnnote scores are explicitly separate from final reconciled transcript scores. JER aggregation is a macro mean over clips, not pooled speaker JER. Timestamp error is unavailable without reliable utterance/word correspondence; no nearest-boundary proxy accepted. Declared language hints are not independent LID accuracy. Overlap F1 uses duration-weighted distinct-speaker regions and no collar; absent reference overlap can make recall undefined. Missing scores are not zero. Torch memory peaks cover this process, RSS is an end-of-clip observation, not system peak. Failures remain in saved outcomes; no success-only accuracy claim.','', '## Blockers']+['- '+v for v in manifest.get('blockers',[])]
    (out/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')

async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    os.environ.update(EXECUTION_MODE='REAL',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    import torch,psutil,soundfile as sf
    from app.core.config import get_settings
    from app.ai.multilingual_asr import MultilingualASREngine
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    from evaluate_saved_research import edit_metrics,diarization
    from app.cli import sanitize_error_text
    s=get_settings();assert s.EXECUTION_MODE=='REAL' and s.BATCH_ASR_PROVIDER=='moss' and s.OPENMOSS_DEVICE.startswith('cuda') and torch.cuda.is_available()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'));out=args.output;out.mkdir(parents=True,exist_ok=True)
    identity={'manifest_sha256':sha(args.manifest),'runner_sha256':sha(__file__),'model':s.OPENMOSS_MODEL_ID,'precision':s.OPENMOSS_PRECISION,'prompt_policy':s.OPENMOSS_PROMPT_POLICY,'max_new_tokens':s.OPENMOSS_MAX_NEW_TOKENS,'chunk_seconds':s.AUDIO_CHUNK_DURATION_SECONDS,'overlap_seconds':s.AUDIO_CHUNK_OVERLAP_SECONDS,'chunk_threshold':s.AUDIO_CHUNK_THRESHOLD_SECONDS,'device':torch.cuda.get_device_name(),'sources':{n:sha(ROOT/'backend/app/ai'/n) for n in ['multilingual_asr.py','speaker_diarization.py','long_audio_processor.py']}}
    if (out/'identity.json').exists():assert json.loads((out/'identity.json').read_text())==identity,'Configuration changed; use a new run'
    else:save(out/'identity.json',identity)
    asr=MultilingualASREngine();speaker=SpeakerDiarizationEngine()
    for sample in manifest['samples']:
        folder=out/sample['sample_id'];folder.mkdir(exist_ok=True)
        if (folder/'metrics.json').exists():continue
        path=ROOT/sample['audio_path'].replace('\\','/');assert sha(path)==sample['sha256'],'Input hash mismatch'
        mid=uuid.uuid5(uuid.NAMESPACE_URL,str(out)+sample['sample_id']);start=time.perf_counter();torch.cuda.reset_peak_memory_stats()
        record={k:sample[k] for k in ['sample_id','dataset','language','split','duration_seconds','sha256']};record.update(meeting_id=str(mid),benchmark_sample_id=str(uuid.uuid5(mid,'benchmark')),errors=[],timestamp_error=None,timestamp_status='NOT VERIFIED: correspondence unavailable')
        save(out/'status.json',{'status':'RUNNING','sample_id':sample['sample_id'],'timestamp':datetime.now(timezone.utc).isoformat()})
        for stage in ['asr','pyannote']:
            target=folder/(stage+'.json')
            if target.exists():continue
            at=time.perf_counter()
            try:
                if stage=='asr':result=await asr.transcribe_audio(b'',mid,target_languages=[sample['language']],use_fixture=False,audio_file_path=str(path))
                else:result=await speaker.diarize_audio(b'',mid,audio_file_path=str(path))
                save(target,{'status':'COMPLETED','seconds':time.perf_counter()-at,'result':result.model_dump(mode='json')})
            except Exception as exc:save(target,{'status':'FAILED','seconds':time.perf_counter()-at,'error_type':type(exc).__name__,'error':sanitize_error_text(str(exc))})
        a=json.loads((folder/'asr.json').read_text(encoding='utf-8'));d=json.loads((folder/'pyannote.json').read_text(encoding='utf-8'))
        for name,v in [('asr',a),('pyannote',d)]:
            if v['status']!='COMPLETED':record['errors'].append({'stage':name,'error':v['error']})
        record.update(status='FAILED' if record['errors'] else 'COMPLETED',processing_seconds=a['seconds']+d['seconds'],asr_seconds=a['seconds'],pyannote_seconds=d['seconds'],gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved(),cpu_rss_bytes=psutil.Process().memory_info().rss)
        record['RTF']=record['processing_seconds']/record['duration_seconds']
        if a['status']=='COMPLETED':
            hypothesis=a['result']['full_transcript'];record['hypothesis']=hypothesis
            if sample.get('reference_text'):
                metrics=edit_metrics(sample['reference_text'],hypothesis);record.update({k:metrics[k] for k in ['WER','CER']});save(folder/'error_analysis.json',metrics)
        refs=[{'start':v.get('start',v.get('start_time')),'end':v.get('end',v.get('end_time')),'speaker':v.get('speaker',v.get('speaker_id'))} for v in sample.get('reference_turns') or []]
        if d['status']=='COMPLETED' and refs:
            hyp=[{'start':v['start_time'],'end':v['end_time'],'speaker':v['speaker_id']} for v in d['result']['speaker_turns']]
            record['raw_pyannote_diarization']=diarization(refs,hyp,sample['duration_seconds']);record['overlap_detection']=overlap_score(refs,hyp,sample['duration_seconds'])
            if a['status']=='COMPLETED':
                from app.ai.multilingual_asr import ASRSegment
                segments=[ASRSegment.model_validate(v) for v in a['result']['segments']]
                final,mapping=speaker.reconcile_moss_identities(segments,d['result']['speaker_turns'])
                save(folder/'final_segments.json',{'segments':[v.model_dump(mode='json') for v in final],'mapping':mapping})
                turns=[{'start':v.start_time,'end':v.end_time,'speaker':v.speaker_id} for v in final]
                record['diarization']=diarization(refs,turns,sample['duration_seconds']);record['unresolved_turns']=sum(v.speaker_id in [None,'UNRESOLVED','UNKNOWN'] for v in final)
                record['diarization_scope']='final MOSS turns with existing acoustic identity reconciliation; unresolved bucket is diagnostic'
        save(folder/'metrics.json',record);summarize(out,manifest)
        print(json.dumps({k:record.get(k) for k in ['sample_id','status','WER','RTF','errors']}),flush=True)
    save(out/'status.json',{'status':'FINISHED','samples':len(manifest['samples'])});summarize(out,manifest)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    asyncio.run(run(args))
