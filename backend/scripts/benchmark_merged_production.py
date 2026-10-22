"""Durable sequential REAL application benchmark of an immutable merged-audio manifest.

Uses existing API, worker, persistence and fresh-process readback. No new worker,
provider substitution, automatic failed-job retry or benchmark transcript fabrication.
"""
import argparse, asyncio, hashlib, json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env',override=True)
os.environ.update(EXECUTION_MODE='REAL',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',DEBUG='false',LOG_LEVEL='ERROR')

def now():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
 tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8');tmp.replace(p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

async def idle():
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import async_sessionmaker
 from app.infrastructure.database import init_database,close_database_connections
 async with async_sessionmaker(init_database())() as db:
  count=(await db.execute(text("SELECT count(*) FROM inference_jobs WHERE status IN ('queued','running')"))).scalar_one()
 await close_database_connections()
 return count==0

async def observe(mid,folder):
 """Resume observation of an already submitted meeting; never resubmit it."""
 import httpx
 from sqlalchemy.ext.asyncio import async_sessionmaker
 from app.infrastructure.database import init_database,close_database_connections
 from app.models.meeting import Meeting
 from app.models.user import User
 from app.core.security import create_access_token
 async with async_sessionmaker(init_database())() as db:
  m=await db.get(Meeting,uuid.UUID(mid));u=await db.get(User,m.host_id)
  if not u or not u.is_active:raise RuntimeError('Authorized host unavailable')
  token=create_access_token({'sub':str(u.id),'role':u.role,'tenant_id':m.tenant_id})
 await close_database_connections()
 async with httpx.AsyncClient(base_url='http://127.0.0.1:3000/api/v1',headers={'Authorization':'Bearer '+token},timeout=60) as client:
  while True:
   r=await client.get('/meetings/'+mid+'/pipeline');r.raise_for_status();p=r.json()
   save(folder/'observed_pipeline.json',{'timestamp':now(),'pipeline':p})
   if p['status'] in ('completed','failed','cancelled'):return p['status']
   await asyncio.sleep(10)

async def main(args):
 import benchmark_production as existing
 import resume_uploaded_meeting as submit
 from app.benchmarks.datasets.base import BenchmarkSample
 from app.core.config import get_settings
 from app.ai.model_inventory import snapshot_for,configure_cache
 from app.benchmarks.metrics import calculate_wer,calculate_cer,normalize_text
 from rapidfuzz.distance import Levenshtein
 s=get_settings()
 snapshot=snapshot_for(s.OPENMOSS_MODEL_ID,configure_cache())
 if s.EXECUTION_MODE!='REAL' or not s.OPENMOSS_DEVICE.startswith('cuda'):raise RuntimeError('REAL CUDA profile required')
 manifest=read(args.manifest);samples=manifest['samples'];args.run.mkdir(parents=True,exist_ok=True)
 if manifest.get('status')!='VERIFIED' or any(x.get('status')!='VERIFIED' or not x.get('reference_order_verified') for x in samples):
  raise RuntimeError('Merged waveform/reference correspondence not verified')
 identity={'manifest_sha256':sha(args.manifest),'runner_sha256':sha(__file__),'mode':'REAL','model':s.OPENMOSS_MODEL_ID,
  'model_revision':snapshot.name if snapshot else 'NOT AVAILABLE',
  'precision':s.OPENMOSS_PRECISION,'device':s.OPENMOSS_DEVICE,'chunk_seconds':s.AUDIO_CHUNK_DURATION_SECONDS,
  'overlap_seconds':s.AUDIO_CHUNK_OVERLAP_SECONDS,'concurrency':s.AUDIO_CHUNK_CONCURRENCY,
  'max_new_tokens':s.OPENMOSS_MAX_NEW_TOKENS,'prompt_policy':s.OPENMOSS_PROMPT_POLICY,
  'source_sha256':{n:sha(ROOT/n) for n in ['backend/app/ai/multilingual_asr.py','backend/app/ai/long_audio_processor.py','backend/app/ai/code_switch_intelligence.py']}}
 pin=args.run/'identity.json'
 if pin.exists() and read(pin)!=identity:raise RuntimeError('Frozen benchmark identity differs; preserve old run')
 if not pin.exists():save(pin,identity)
 results=[]
 for sample in samples:
  sid=sample['sample_id'];folder=args.run/sid;folder.mkdir(exist_ok=True)
  if (folder/'result.json').exists():results.append(read(folder/'result.json'));continue
  path=ROOT/sample['audio_path']
  if sha(path)!=sample['sha256']:raise RuntimeError('Input audio hash differs')
  save(args.run/'status.json',{'timestamp':now(),'status':'WAITING_FOR_IDLE','current_sample':sid,'completed_files':len(results),'total_files':len(samples)})
  record=None
  if (folder/'input.json').exists():
   record=read(folder/'input.json');await observe(record['meeting_id'],folder)
  elif (folder/'created.json').exists():
   raise RuntimeError('Existing partially uploaded meeting; inspect created.json, do not recreate')
  else:
   while not await idle():await asyncio.sleep(10)
   item=BenchmarkSample(sample_id=sid,dataset_name='FLEURS merged PCM_U8',dataset_version='local_test_concatenation',
    audio_path=str(path),audio_format='wav',duration_seconds=sample['duration_seconds'],language=sample['language'],
    reference_transcript=sample.get('reference_text'),audio_sha256=sample['sha256'],metadata=sample.get('metadata',{}))
   record=await existing.prepare(item,folder,args.run.name)
   save(args.run/'status.json',{'timestamp':now(),'status':'RUNNING','current_sample':sid,'meeting_id':record['meeting_id'],'completed_files':len(results),'total_files':len(samples)})
   await submit.run(argparse.Namespace(run=folder,meeting=uuid.UUID(record['meeting_id']),observation_seconds=86400,worker_pid=args.worker_pid))
  started=time.perf_counter()
  proc=await asyncio.to_thread(subprocess.run,[sys.executable,str(ROOT/'backend/scripts/capture_workspace_run.py'),'--run',str(folder),'--meeting',record['meeting_id']],cwd=ROOT,capture_output=True,text=True)
  save(folder/'capture_process.json',{'timestamp':now(),'exit_code':proc.returncode,'seconds':time.perf_counter()-started})
  rbfiles=sorted(folder.glob('readback_*.json'));rbfiles=[p for p in rbfiles if not p.name.startswith('readback_failed_')]
  result={'timestamp':now(),'benchmark_run_id':args.run.name,'benchmark_sample_id':sid,'meeting_id':record['meeting_id'],
   'language':sample['language'],'audio_sha256':sample['sha256'],'duration_seconds':sample['duration_seconds'],
   'scope':'Merged quantized FLEURS through full production architecture; not original per-utterance benchmark',
   'status':'NOT VERIFIED','WER':None,'CER':None,'DER':None,'JER':None,'timestamp_error':None,'source_identity':identity}
  if rbfiles:
   rb=read(rbfiles[-1]);segments=rb.get('database_segments',[]);text=' '.join(x['original_text'] for x in segments)
   result.update(canonical_transcript_id=rb.get('canonical_transcript_id'),final_segments=len(segments),
    fresh_readback_matches_api=rb.get('fresh_readback_matches_api',False),meeting_status=rb.get('meeting_status'),
    readback_artifact=str(rbfiles[-1].relative_to(ROOT)),hypothesis=text,
    pipeline=rb.get('pipeline',{}).get('body',{}))
   result['status']='COMPLETED' if rb.get('meeting_status')=='completed' and segments and result['fresh_readback_matches_api'] else 'FAILED_OR_PARTIAL'
   save(folder/'transcript.json',segments)
   (folder/'transcript.txt').write_text(text,encoding='utf-8')
   jobs=result['pipeline'].get('jobs',[])
   sourcejobs=[j for j in jobs if j.get('kind')=='batch']
   if sourcejobs:
    j=sourcejobs[-1];result['job_id']=j['id'];elapsed=(j.get('result') or {}).get('elapsed_seconds')
    result.update(processing_seconds=elapsed,RTF=elapsed/sample['duration_seconds'] if elapsed else None)
   if text.strip() and sample.get('reference_text') and sample.get('reference_order_verified') and sample.get('status')=='VERIFIED':
    ref=sample['reference_text'];w=calculate_wer(ref,text);c=calculate_cer(ref,text)
    if not normalize_text(ref):raise RuntimeError('Empty normalized ground truth')
    assert sum(w[k] for k in ('substitutions','deletions','insertions'))==Levenshtein.distance(normalize_text(ref).split(),normalize_text(text).split())
    assert sum(c[k] for k in ('substitutions','deletions','insertions'))==Levenshtein.distance(normalize_text(ref).replace(' ',''),normalize_text(text).replace(' ',''))
    result.update(WER=w,CER=c,metric_crosscheck='Existing exact edit counts == RapidFuzz Levenshtein',accuracy_status='VERIFIED_ON_ALTERED_MERGED_INPUT')
   else:result['accuracy_status']='NOT VERIFIED: validated reference or non-empty hypothesis unavailable'
  save(folder/'result.json',result);results.append(result)
  save(args.run/'summary.json',{'timestamp':now(),'results':results,'completed_files':len(results),'requested_files':len(samples),'no_cross_language_aggregation':True})
  print(json.dumps({k:result.get(k) for k in ['benchmark_sample_id','meeting_id','status','final_segments','accuracy_status']}),flush=True)
 save(args.run/'status.json',{'timestamp':now(),'status':'FINISHED','files':len(results),'successful':sum(x['status']=='COMPLETED' for x in results),'failed_or_partial':sum(x['status']!='COMPLETED' for x in results)})
 return 0 if all(x['status']=='COMPLETED' for x in results) else 1

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--worker-pid',type=int)
 a=p.parse_args()
 try:raise SystemExit(asyncio.run(main(a)))
 except Exception as exc:
  a.run.mkdir(parents=True,exist_ok=True)
  from app.cli import sanitize_error_text
  save(a.run/'blocked.json',{'timestamp':now(),'status':'BLOCKED','error_type':type(exc).__name__,'reason':sanitize_error_text(str(exc))})
  raise SystemExit(1)
