"""Thin executable gates around existing ABCI-MI providers, CLI and repositories.

Notebook cells orchestrate this script in separate processes. Inference and
reconstruction remain in app.ai and the existing ACE/meeting/SKW architecture.
"""
import argparse
import asyncio
import contextlib
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import logging
import math
import os
import re
from pathlib import Path
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'backend'))
sys.path.insert(0,str(REPO/'backend/scripts'))
from app.core.config import get_settings

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as file:
        json.dump(value,file,indent=2,default=str)

def safe(message):
    for key,value in os.environ.items():
        if value and any(part in key for part in ('TOKEN','SECRET','PASSWORD','URL','API_KEY')):
            message=message.replace(value,'[REDACTED]')
    message=re.sub(r'hf_[A-Za-z0-9]{12,}','[REDACTED]',message)
    return re.sub(r'(://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',message)

def audio_metadata(path):
    import soundfile as sf
    info=sf.info(path)
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''): digest.update(block)
    if info.duration<=0: raise ValueError('Actual audio has no positive duration')
    return {'audio_path':str(path.resolve()),'audio_filename':path.name,'audio_sha256':digest.hexdigest(),
        'audio_duration':info.duration,'sample_rate':info.samplerate,'channels':info.channels,'audio_size':path.stat().st_size}

def diagnostics(run):
    import torch
    from app.ai.model_inventory import inventory
    packages={}
    for name in ('torch','torchaudio','transformers','accelerate','safetensors','numpy','soundfile',
                 'librosa','av','soxr','pyannote.audio','bitsandbytes','moss-transcribe-diarize','fastapi',
                 'sqlalchemy','asyncpg','psycopg2-binary','redis','qdrant-client'):
        try: packages[name]=metadata.version(name)
        except metadata.PackageNotFoundError: packages[name]='MISSING'
    settings=get_settings()
    hardware={'cuda_available':torch.cuda.is_available(),'torch_cuda':torch.version.cuda}
    if torch.cuda.is_available():
        gpu=torch.cuda.get_device_properties(0)
        hardware.update(gpu=gpu.name,vram_bytes=gpu.total_memory,device='cuda:0')
    write(run/'hardware.json',hardware)
    write(run/'environment.json',{'python':sys.version.split()[0],'packages':packages,
        'execution_mode':settings.EXECUTION_MODE,'device':settings.OPENMOSS_DEVICE,
        'secrets':{k:'present' if os.environ.get(k) else 'missing' for k in ('HF_TOKEN','DATABASE_URL_ASYNC','REDIS_URL','QDRANT_URL')},
        'chunk_duration':settings.AUDIO_CHUNK_DURATION_SECONDS,'overlap':settings.AUDIO_CHUNK_OVERLAP_SECONDS,
        'concurrency':settings.AUDIO_CHUNK_CONCURRENCY})
    write(run/'model_status.json',inventory())
    if settings.EXECUTION_MODE!='REAL' or not hardware['cuda_available'] or settings.OPENMOSS_DEVICE!='cuda':
        raise RuntimeError('REAL CUDA execution required; no CPU/model-fixture fallback permitted')
    if os.environ.get('TESTING')=='true' or os.environ.get('PYTEST_CURRENT_TEST'):
        raise RuntimeError('Test storage flags forbidden for REAL production')
    return {'status':'VERIFIED','gpu':hardware.get('gpu'),'vram_bytes':hardware.get('vram_bytes')}

async def services(run):
    from sqlalchemy import inspect, select, text
    from app.infrastructure.database import init_database,get_async_db,close_database_connections
    from app.infrastructure.redis import get_redis_client
    from app.infrastructure.qdrant import get_qdrant_client
    from app.models.user import User
    from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
    from app.orchestration.skw_client import BlackboardSKWClient
    statuses={}
    engine=init_database()
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
            tables=await conn.run_sync(lambda c:inspect(c).get_table_names())
        required={'users','meetings','audio_recordings','transcripts','transcript_segments','knowledge_objects','audit_logs','meeting_reports'}
        missing=sorted(required-set(tables))
        statuses['PostgreSQL']={'status':'AVAILABLE' if not missing else 'UNAVAILABLE','missing_tables':missing}
        if missing: raise RuntimeError('Required existing PostgreSQL schema missing; initialize using repository migrations externally')
        async for session in get_async_db():
            user_id=uuid.UUID(os.environ.get('ABCI_USER_ID','00000000-0000-0000-0000-000000000001'))
            if await session.get(User,user_id) is None:
                raise RuntimeError('Configured existing CLI user does not exist in PostgreSQL; no fabricated identity will be inserted')
            correlation=str(uuid.uuid4())
            client=BlackboardSKWClient(KnowledgeQueryEngine(session))
            await client.request_structured_knowledge(limit=0,auth_context={'authenticated':True,
                'user_id':str(user_id),'tenant_id':os.environ.get('ABCI_TENANT_ID','default-tenant'),'role':'host'},
                correlation_id=correlation)
            await session.commit()
            statuses['SKW']={'status':'AVAILABLE','probe':'existing authorized structured query, limit 0',
                             'user_id':str(user_id),'correlation_id':correlation,'writes':'NOT VERIFIED'}
            break
    except Exception as exc:
        statuses.setdefault('PostgreSQL',{'status':'UNAVAILABLE'})
        statuses.setdefault('SKW',{'status':'UNAVAILABLE'})
        statuses['database_error']=safe(str(exc))
    finally: await close_database_connections()
    try:
        client=await get_redis_client()
        available=client is not None and await client.ping()
        statuses['Redis']={'status':'AVAILABLE' if available else 'FALLBACK'}
    except Exception as exc: statuses['Redis']={'status':'FALLBACK','reason':safe(str(exc))}
    try:
        client=await get_qdrant_client()
        collections=await client.get_collections()
        statuses['Qdrant']={'status':'AVAILABLE','collections':[c.name for c in collections.collections]}
        await client.close()
    except Exception as exc: statuses['Qdrant']={'status':'UNAVAILABLE','reason':safe(str(exc))}
    write(run/'service_status.json',statuses)
    blocked=any(statuses.get(k,{}).get('status')!='AVAILABLE' for k in ('PostgreSQL','SKW','Qdrant'))
    return {'status':'BLOCKED' if blocked else 'VERIFIED','services':{k:v['status'] for k,v in statuses.items() if isinstance(v,dict) and 'status' in v}}

async def probe(run,audio,duration,start,all_models):
    from app.ai.long_audio_processor import LongAudioProcessor,ChunkMetadata
    from app.ai.multilingual_asr import OpenMOSSProvider
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
    import torch
    info=audio_metadata(audio)
    end=min(info['audio_duration'],start+duration)
    if not 0<=start<end: raise ValueError('Invalid real audio probe interval')
    chunk=ChunkMetadata(chunk_index=0,total_chunks=1,start_time=start,end_time=end,duration=end-start)
    path=Path(LongAudioProcessor().slice_audio_file(str(audio),chunk,output_dir=str(run)))
    settings=get_settings()
    provider=OpenMOSSProvider({'model_id':settings.OPENMOSS_MODEL_ID,'device':settings.OPENMOSS_DEVICE,
                              'cache_dir':settings.OPENMOSS_CACHE_DIR,'token':settings.HF_TOKEN})
    started=time.perf_counter()
    result={'status':'BLOCKED','scope':'REAL provider diagnostic, not production success',
            'audio':info,'chunk':chunk.model_dump(mode='json'),'moss_called':True}
    try:
        segments=await provider.transcribe(str(path),options={'chunk_meta':chunk})
        if not segments or not provider.last_raw_output:
            raise RuntimeError('REAL MOSS returned no raw output or parsed transcript segments')
        result.update(status='VERIFIED',moss_generation_completed=True,
            raw_moss_output=provider.last_raw_output,moss_inference=provider.last_inference,
            segments=[s.model_dump(mode='json') for s in segments])
        if all_models:
            meeting=uuid.uuid4()  # diagnostic correlation identifier, not a persisted meeting
            result['diagnostic_meeting_id']=str(meeting)
            diarization=await SpeakerDiarizationEngine().diarize_audio(path.read_bytes(),meeting)
            result['pyannote']=diarization.model_dump(mode='json')
            if not diarization.speaker_turns:
                raise RuntimeError('REAL PyAnnote returned no actual speaker turns')
            engine=CodeSwitchIntelligenceEngine()
            actual_text=' '.join(s.transcript for s in segments)
            result['sarvam']={'output':await engine.map_to_canonical(actual_text),
                'input_text':actual_text,'inference':dict(engine.last_inference),
                'raw_completion':engine.last_raw_completion,'accuracy':'NOT VERIFIED'}
    except Exception as exc:
        reasons=[]; cause=exc
        while cause:
            reasons.append(str(cause)); cause=cause.__cause__
        result.update(status='BLOCKED',error=safe(str(exc)),error_type=type(exc).__name__,
            oom=any('out of memory' in message.lower() for message in reasons),
            raw_moss_output=provider.last_raw_output or 'NOT AVAILABLE',moss_inference=provider.last_inference)
    finally:
        result.update(elapsed_seconds=time.perf_counter()-started,
            gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            gpu_allocated_bytes=torch.cuda.memory_allocated())
        write(run/'probe_result.json',result)
    return {k:result.get(k) for k in ('status','oom','error_type','elapsed_seconds')}

def production(run,audio,resume):
    import validate_phase1
    info=audio_metadata(audio)
    from app.ai.long_audio_processor import LongAudioProcessor
    settings=get_settings()
    plan=LongAudioProcessor().plan_chunks(info['audio_duration'])
    # These are actual planning IDs, separate from runtime chunk IDs; save them.
    write(run/'planned_chunks.json',[c.model_dump(mode='json') for c in plan])
    preflight={**info,'run_id':run.name,'timestamp':datetime.now(timezone.utc).isoformat(),
        'execution_mode':'REAL','status':'PREPARED','title':'Kaggle full REAL ABCI-MI production',
        'chunk_duration':settings.AUDIO_CHUNK_DURATION_SECONDS,'overlap':settings.AUDIO_CHUNK_OVERLAP_SECONDS,
        'step':settings.AUDIO_CHUNK_DURATION_SECONDS-settings.AUDIO_CHUNK_OVERLAP_SECONDS,
        'coverage':[[c.start_time,c.end_time] for c in plan],'coverage_has_gaps':any(b.start_time>a.end_time for a,b in zip(plan,plan[1:])),
        'git_commit':os.environ.get('ABCI_SOURCE_COMMIT','NOT AVAILABLE'),
        'source_archive_sha256':os.environ.get('ABCI_SOURCE_ARCHIVE_SHA256','NOT AVAILABLE'),
        'cli_user_id':os.environ.get('ABCI_USER_ID','00000000-0000-0000-0000-000000000001'),
        'cli_tenant_id':os.environ.get('ABCI_TENANT_ID','default-tenant')}
    if resume: preflight['resume_meeting_id']=resume
    write(run/'preflight.json',preflight)
    write(run/'audio_metadata.json',info)
    exit_code=validate_phase1.execute(run)
    return {'status':'VERIFIED' if exit_code==0 else 'BLOCKED','production_exit_code':exit_code}

async def fresh(run):
    from readback_phase1 import readback
    result=await readback(run)
    return {'status':'VERIFIED' if result['status']=='PASSED' else 'BLOCKED',
            'canonical_transcript_id':result.get('canonical_transcript_id','NOT AVAILABLE')}

def final_report(run):
    get=lambda name:json.loads((run/name).read_text()) if (run/name).exists() else {}
    execution=get('execution.json'); read=get('fresh_readback.json'); tasks=get('blackboard_tasks.json')
    moss=get('moss_calls.json'); pyannote=get('pyannote.json'); sarvam=get('sarvam_calls.json')
    events=get('redis_events.json'); dedup=get('deduplication.json'); reconciliation=get('speaker_reconciliation.json')
    info=get('audio_metadata.json'); cli=get('cli_result.json')
    if not info: info=get('preflight.json')
    chunks=read.get('persisted_chunks',[])
    completed={str(c['chunk_id']):c for c in chunks if c.get('status')=='completed'}
    inferred={c.get('chunk',{}).get('chunk_id') for c in moss if c.get('status')=='COMPLETED'}
    rows=read.get('segments',[])
    bounds=bool(rows) and all(0<=s['start_time_ms']<s['end_time_ms']<=round(info.get('audio_duration',0)*1000) for s in rows)
    chronological=bool(rows) and all(a['start_time_ms']<=b['start_time_ms'] for a,b in zip(rows,rows[1:]))
    coverage=bool(chunks) and chunks[0]['start_time']==0 and abs(chunks[-1]['end_time']-info.get('audio_duration',0))<=.001 and all(b['start_time']<=a['end_time'] for a,b in zip(chunks,chunks[1:]))
    local={s['segment_id']:(c['chunk']['start_time'],s) for c in moss if c.get('chunk') for s in c.get('segments',[])}
    offsets=[abs(s['start_time']-round(local[s['segment_id']][0]+local[s['segment_id']][1]['start_time'],3))<1e-6 and
             abs(s['end_time']-round(local[s['segment_id']][0]+local[s['segment_id']][1]['end_time'],3))<1e-6
             for item in reconciliation.get('inputs',[]) for s in item['global_segments'] if s['segment_id'] in local]
    observed_segments=[s for item in reconciliation.get('inputs',[]) for s in item['global_segments']]
    all_sources_present=bool(observed_segments) and all(s['segment_id'] in local for s in observed_segments)
    qdrant=read.get('qdrant',[])
    gates={'entire_audio_coverage':coverage,'all_chunks_actual_moss':bool(completed) and set(completed)==inferred,
        'pyannote':pyannote.get('status')=='COMPLETED','sarvam':bool(sarvam) and all(c.get('status')=='COMPLETED' for c in sarvam),
        'speaker_reconciliation':bool(reconciliation.get('mapping')) and bool(reconciliation.get('output')),
        'timestamps':bounds and chronological and all_sources_present and bool(offsets) and all(offsets),
        'deduplication_executed':bool(dedup),'ace':bool(tasks) and all(t.get('status')=='COMPLETED' for t in tasks),
        'fresh_process_readback':read.get('status')=='PASSED','cli':execution.get('cli_exit_code')==0 and cli.get('transcript_count',0)>0,
        'qdrant':isinstance(qdrant,list) and bool(qdrant) and all(p['exists'] and p['payload_content_matches'] for p in qdrant),
        'redis_distributed':bool(events) and all(e['delivery_status']=='distributed' for e in events)}
    status='VERIFIED' if all(gates.values()) else ('PARTIALLY VERIFIED' if gates['fresh_process_readback'] and gates['cli'] else 'BLOCKED')
    actual_ids=[]
    def walk(v,location):
        if isinstance(v,dict):
            for k,value in v.items(): walk(value,location+'.'+k)
        elif isinstance(v,list):
            for i,value in enumerate(v): walk(value,location+f'[{i}]')
        elif isinstance(v,str):
            try: uuid.UUID(v)
            except ValueError: return
            actual_ids.append({'id':v,'source':location})
    for file in run.glob('*.json'):
        walk(json.loads(file.read_text()),file.name)
    identifiers={'run_id':run.name,'meeting_id':execution.get('meeting_id','NOT AVAILABLE'),
        'transcript_id':read.get('canonical_transcript_id','NOT AVAILABLE'),'project_id':execution.get('project_id','NOT AVAILABLE'),
        'correlation_ids':sorted({i['id'] for i in actual_ids if 'correlation_id' in i['source']}) or 'NOT AVAILABLE',
        'chunk_ids':sorted({i['id'] for i in actual_ids if 'chunk_id' in i['source']}) or 'NOT AVAILABLE',
        'event_ids':sorted({i['id'] for i in actual_ids if 'event_id' in i['source']}) or 'NOT AVAILABLE',
        'observed_id_fields':actual_ids,'database_ids':read.get('database_record_ids','NOT AVAILABLE'),
        'qdrant_points':qdrant or 'NOT AVAILABLE','git_commit':os.environ.get('ABCI_SOURCE_COMMIT','NOT AVAILABLE')}
    for category in ('query_id','notification_id','benchmark_run_id','benchmark_sample_id','knowledge_object_id'):
        identifiers[category]=sorted({i['id'] for i in actual_ids if category in i['source']}) or 'NOT AVAILABLE'
    identifiers['timestamp']=datetime.now(timezone.utc).isoformat()
    identifiers['redis_stream_id']='NOT AVAILABLE'  # Existing event bus uses Pub/Sub, not Redis streams.
    write(run/'identifiers.json',identifiers)
    # Actual full-file PyAnnote output grouped by production chunk windows.
    # Original global bounds retained; no claim of separate per-chunk inference.
    turns=pyannote.get('output',{}).get('speaker_turns',[])
    write(run/'pyannote_chunk_views.json',{'mode':'observed full-file turns grouped by chunk, not separate inference',
        'chunks':[{'chunk_id':c['chunk_id'],'turns':[t for t in turns if t['end_time']>c['start_time'] and t['start_time']<c['end_time']]} for c in chunks]})
    elapsed=execution.get('processing_seconds')
    result={'STATUS':status,'gates':gates,'AUDIO':info,'CHUNKS':chunks,'MOSS':{'calls':len(moss),'failed':sum(c.get('status')=='FAILED' for c in moss)},
        'SARVAM':'actual per-turn generation recorded' if sarvam else 'NOT VERIFIED',
        'PYANNOTE':pyannote.get('status','NOT VERIFIED'),'POSTGRESQL':read.get('status','NOT VERIFIED'),
        'OVERLAP_RESOLUTION':cli.get('overlap_resolution',{}),
        'QUALITY_WARNINGS':cli.get('quality_warnings',[]),
        'FRESH_READ_BACK':read.get('status','NOT VERIFIED'),'REDIS':'AVAILABLE' if gates['redis_distributed'] else ('FALLBACK' if events else 'NOT VERIFIED'),
        'QDRANT':'VERIFIED' if gates['qdrant'] else 'NOT VERIFIED','PROCESSING_TIME':elapsed or 'NOT AVAILABLE',
        'RTF':elapsed/info['audio_duration'] if isinstance(elapsed,(int,float)) and info.get('audio_duration') else 'NOT AVAILABLE',
        'IDS':{k:v for k,v in identifiers.items() if k not in ('observed_id_fields','database_ids')},
        'FAILURES':[{'call':c.get('call_index'),'error':c.get('error')} for c in moss if c.get('status')=='FAILED'],
        'RETRIES':sum(e.get('event',{}).get('event_type')=='orchestration.retry_requested' for e in events if isinstance(e.get('event'),dict)),
        'RESUME_RETRY_VERIFICATION':'NOT VERIFIED unless separately exercised',
        'SEMANTIC_RETRIEVAL_ACCURACY':'NOT VERIFIED','TRANSCRIPT_ACCURACY':'NOT VERIFIED',
        'REMAINING_GAPS':[k for k,v in gates.items() if not v],
        'ARTIFACTS':[str(file.relative_to(REPO)) for file in run.rglob('*') if file.is_file()]}
    write(run/'final_verification.json',result)
    write(run/'artifact_registry.json',[{'path':str(f.relative_to(REPO)),'bytes':f.stat().st_size,
        'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in run.rglob('*') if f.is_file()])
    with (REPO/'e2e_validation/execution_log.md').open('a',encoding='utf-8') as file:
        file.write('\n## Kaggle full production report\n```json\n'+json.dumps(result,indent=2)+'\n```\n')
    return {'status':status,'gates':gates}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['diagnostics','services','probe','production','readback','report'])
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--audio',type=Path)
    parser.add_argument('--duration',type=float,default=10); parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--all-models',action='store_true'); parser.add_argument('--resume-meeting-id')
    args=parser.parse_args(); args.run.mkdir(parents=True,exist_ok=True)
    stage_log=args.run/f'{args.stage}_worker.log'
    settings=get_settings()
    if settings.EXECUTION_MODE!='REAL' or settings.OPENMOSS_DEVICE!='cuda': raise RuntimeError('REAL CUDA required')
    class SafeStream:
        def __init__(self,file): self.file=file
        def write(self,value): self.file.write(safe(value)); self.file.flush()
        def flush(self): self.file.flush()
        def isatty(self): return False
    if stage_log.exists(): raise RuntimeError('Stage evidence already exists; choose a new run')
    streams=[]
    with stage_log.open('x',encoding='utf-8') as file:
        stream=SafeStream(file)
        for logger in [logging.getLogger(),*[l for l in logging.Logger.manager.loggerDict.values() if isinstance(l,logging.Logger)]]:
            for handler in logger.handlers:
                if isinstance(handler,logging.StreamHandler) and not isinstance(handler,logging.FileHandler):
                    try: original=handler.stream; handler.setStream(stream)
                    except AttributeError: continue
                    streams.append((handler,original))
        try:
            with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
                if args.stage=='diagnostics': result=diagnostics(args.run)
                elif args.stage=='services': result=asyncio.run(services(args.run))
                elif args.stage=='probe': result=asyncio.run(probe(args.run,args.audio,args.duration,args.start,args.all_models))
                elif args.stage=='production': result=production(args.run,args.audio,args.resume_meeting_id)
                elif args.stage=='readback': result=asyncio.run(fresh(args.run))
                else: result=final_report(args.run)
        except Exception as exc:
            result={'status':'BLOCKED','error_type':type(exc).__name__,'reason':safe(str(exc))}
        finally:
            for handler,original in streams: handler.setStream(original)
    write(args.run/f'{args.stage}_stage.json',result)
    print(json.dumps(result))
    return 0 if result['status']=='VERIFIED' else 1

if __name__=='__main__': sys.exit(main())
