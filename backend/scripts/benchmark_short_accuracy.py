"""Small REAL MOSS prompt comparison. Local cached audio/weights only; no retries."""
import asyncio, datetime, hashlib, json, os, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env',override=True)
os.environ.update(EXECUTION_MODE='REAL',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
OUT=ROOT/'benchmark results/multidataset_short_20261020';OUT.mkdir(parents=True,exist_ok=True)
def save(path,value):
 path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8');tmp.replace(path)
async def main(provider_name="moss"):
 if provider_name not in {"moss","whisper"}:raise ValueError("Explicit provider must be moss or whisper")
 import torch,soundfile as sf,psutil
 from app.core.config import get_settings
 from app.ai.multilingual_asr import OpenMOSSProvider
 from app.ai.model_inventory import snapshot_for,configure_cache
 from app.benchmarks.metrics import calculate_wer,calculate_cer,normalize_text
 from app.benchmarks.config import BenchmarkConfig
 from app.benchmarks.storage import BenchmarkStorage,SampleResultRecord
 from rapidfuzz.distance import Levenshtein
 from app.cli import sanitize_error_text
 s=get_settings()
 if s.EXECUTION_MODE!='REAL' or not s.OPENMOSS_DEVICE.startswith('cuda') or not torch.cuda.is_available():raise RuntimeError('REAL CUDA required; no fallback')
 manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
 source_file=ROOT/('backend/app/ai/whisper_provider.py' if provider_name=='whisper' else 'backend/app/ai/multilingual_asr.py')
 source_hash=hashlib.sha256(source_file.read_bytes()).hexdigest()
 model_id=s.WHISPER_MODEL_ID if provider_name=='whisper' else s.OPENMOSS_MODEL_ID
 snapshot=snapshot_for(model_id,configure_cache())
 identity={'model':model_id,'revision':snapshot.name if snapshot else None,'precision':s.WHISPER_PRECISION if provider_name=='whisper' else s.OPENMOSS_PRECISION,'provider_source_sha256':source_hash,'manifest_sha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest(),'device':s.OPENMOSS_DEVICE,'max_new_tokens':440 if provider_name=='whisper' else 1024}
 config=BenchmarkConfig(results_dir=str(OUT),db_path=str(OUT/'benchmark_runs.db'))
 storage=BenchmarkStorage(config)
 provider=OpenMOSSProvider({'model_id':s.OPENMOSS_MODEL_ID,'device':s.OPENMOSS_DEVICE,'cache_dir':s.OPENMOSS_CACHE_DIR,'precision':s.WHISPER_PRECISION if provider_name=='whisper' else s.OPENMOSS_PRECISION})
 rows=[]
 if provider_name=='whisper':
  from app.ai.whisper_provider import WhisperHFProvider
  provider=WhisperHFProvider()
 for policy in (['whisper_transcribe'] if provider_name=='whisper' else ['verbatim_declared_languages_v2','official_v1']):
  # Official policy is a controlled comparison, never an automatic fallback.
  for sample in manifest['samples']:
   folder=OUT/policy/sample['sample_id'];folder.mkdir(parents=True,exist_ok=True)
   result_path=folder/'result.json'
   if result_path.exists():
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if result.get('identity')!=identity or result.get('audio_sha256')!=sample['sha256']:raise RuntimeError('Existing result identity mismatch; preserve evidence')
    rows.append(result);continue
   audio=ROOT/sample['relative_audio'];info=sf.info(audio)
   if not 0<info.duration<=20 or hashlib.sha256(audio.read_bytes()).hexdigest()!=sample['sha256'] or not normalize_text(sample['reference']):raise RuntimeError('Actual short audio/reference gate failed')
   run_id=str(uuid.uuid4());storage.create_run(run_id=run_id,dataset_name=sample['dataset'],dataset_version=sample['dataset_version'],model_name=model_id,provider=provider_name+' REAL '+policy,device=s.OPENMOSS_DEVICE,language=sample['language'],samples_requested=1)
   result={'benchmark_run_id':run_id,'benchmark_sample_id':sample['sample_id'],'dataset':sample['dataset'],'language':sample['language'],'prompt_policy':policy,'identity':identity,'audio_sha256':sample['sha256'],'audio_filename':audio.name,'duration':info.duration,'sample_rate':info.samplerate,'channels':info.channels,'reference':sample['reference'],'meeting_id':'NOT AVAILABLE','canonical_transcript_id':'NOT AVAILABLE','project_id':'NOT AVAILABLE','correlation_id':'NOT AVAILABLE','event_id':'NOT AVAILABLE','query_id':'NOT AVAILABLE','notification_id':'NOT AVAILABLE','knowledge_object_id':'NOT AVAILABLE','qdrant_point_id':'NOT AVAILABLE','redis_event_id':'NOT AVAILABLE','DER':'NOT VERIFIED','JER':'NOT VERIFIED','timestamp_error':'NOT VERIFIED','scope':'short ASR component pilot, no production meeting'}
   torch.cuda.reset_peak_memory_stats();started=time.perf_counter()
   try:
    if provider_name=='whisper':provider.languages=[sample['language']]
    segments=await provider.transcribe(str(audio),{'language_hint':sample['language'],'prompt_policy':policy,'max_new_tokens':1024,'generation_journal':lambda value:save(folder/'generation.json',value)})
    text=' '.join(x.transcript for x in segments)
    if not segments or not text.strip():raise RuntimeError('Empty actual transcript')
    wer=calculate_wer(sample['reference'],text);cer=calculate_cer(sample['reference'],text)
    exact=Levenshtein.distance(normalize_text(sample['reference']).split(),normalize_text(text).split())
    if exact!=sum(wer[k] for k in ['substitutions','deletions','insertions']):raise RuntimeError('WER implementation cross-check failed')
    elapsed=time.perf_counter()-started
    result.update(status='COMPLETED',hypothesis=text,segments=[x.model_dump(mode='json') for x in segments],inference=provider.last_inference,WER=wer,CER=cer,processing_seconds=elapsed,RTF=elapsed/info.duration,gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),cpu_rss_bytes=psutil.Process().memory_info().rss,word_metric_crosscheck='RapidFuzz exact distance PASSED',normalization='NFC, casefold, Unicode L/M/N, punctuation/whitespace normalization; no transliteration')
    storage.save_sample_result(SampleResultRecord(run_id=run_id,sample_id=sample['sample_id'],dataset_name=sample['dataset'],dataset_version=sample['dataset_version'],audio_path=str(audio),language=sample['language'],duration_seconds=info.duration,model_name=model_id,provider=provider_name+' REAL '+policy,status='SUCCESS',wer=wer['wer'],cer=cer['cer'],processing_time_seconds=elapsed,real_time_factor=elapsed/info.duration,ground_truth_transcript=sample['reference'],predicted_transcript=text))
    storage.finalize_run(run_id,'SUCCESS',{'samples_completed':1,'WER':wer['wer'],'CER':cer['cer']})
   except Exception as exc:
    result.update(status='FAILED',error_type=type(exc).__name__,reason=sanitize_error_text(str(exc)),inference=provider.last_inference,WER=None,CER=None,processing_seconds=time.perf_counter()-started)
    storage.finalize_run(run_id,'FAILED',{'samples_completed':0,'samples_failed':1},error_summary=result['reason'])
   result['timestamp']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(result_path,result);rows.append(result)
   save(OUT/('progress_whisper.json' if provider_name=='whisper' else 'progress.json'),{'status':'RUNNING','completed_attempts':len(rows),'last':{k:result.get(k) for k in ['dataset','language','prompt_policy','status','WER','reason']}})
   print(json.dumps({k:result.get(k) for k in ['dataset','language','prompt_policy','status','WER','CER','reason']}),flush=True)
 summary={'status':'COMPLETED','rows':rows,'scope':'One sample per dataset/language per policy; not dataset-wide acceptance. No cross-language aggregation.','identity':identity,'normalization_limitations':'Literal native-script comparison; no guessed Roman/native Hindi equivalence.','accuracy':'Measured pilot values only; no universal improvement claim'}
 save(OUT/('summary_whisper.json' if provider_name=='whisper' else 'summary.json'),summary)
 print('SHORT_COMPARISON_COMPLETE',flush=True)
if __name__=='__main__':asyncio.run(main(sys.argv[1] if len(sys.argv)>1 else 'moss'))
