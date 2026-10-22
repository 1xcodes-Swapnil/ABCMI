"""Read-only snapshot of saved manual attempts, including failures; no inference.

Run on the existing instance with --since-meeting UUID --output NEW_JSON.
Never exports authentication payloads or connection settings.
"""
import argparse,asyncio,hashlib,json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))

async def export(args):
 from dotenv import load_dotenv
 load_dotenv(ROOT/'backend/.env',override=True)
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import async_sessionmaker
 from app.infrastructure.database import init_database,close_database_connections
 from app.cli import sanitize_error_text
 rows=[]
 async with async_sessionmaker(init_database())() as db:
  await db.execute(text('SET TRANSACTION READ ONLY'))
  cutoff=(await db.execute(text('SELECT created_at FROM meetings WHERE id=:id'),{'id':args.since_meeting})).scalar_one()
  meetings=(await db.execute(text('SELECT id,title,status,language,created_at FROM meetings WHERE created_at>=:cutoff ORDER BY created_at'),{'cutoff':cutoff})).mappings().all()
  for m in meetings:
   mid=m['id']
   audio=(await db.execute(text('SELECT id,file_name,file_path,duration_seconds,sample_rate,channels,meta_data FROM audio_recordings WHERE meeting_id=:id ORDER BY created_at DESC LIMIT 1'),{'id':mid})).mappings().first()
   canon=(await db.execute(text('SELECT id,version,full_text,provenance,is_final FROM transcripts WHERE meeting_id=:id ORDER BY version DESC,created_at DESC LIMIT 1'),{'id':mid})).mappings().first()
   segs=(await db.execute(text('SELECT id,sequence_number,start_time_ms,end_time_ms,speaker_label,original_text,language FROM transcript_segments WHERE meeting_id=:id ORDER BY sequence_number'),{'id':mid})).mappings().all()
   jobs=(await db.execute(text('SELECT id,kind,status,error,started_at,finished_at,result FROM inference_jobs WHERE meeting_id=:id ORDER BY created_at'),{'id':mid})).mappings().all()
   a=dict(audio) if audio else None
   if a:
    path=Path(a.pop('file_path'));stored=a.pop('meta_data') or {}
    a['sha256']=stored.get('audio_sha256');a['audio_exists']=path.is_file()
    a['sha256_source']='persisted_upload_checksum' if a['sha256'] else None
    if path.is_file():
     digest=hashlib.sha256()
     with path.open('rb') as f:
      for block in iter(lambda:f.read(1048576),b''):digest.update(block)
     actual=digest.hexdigest()
     if a['sha256'] and a['sha256'] != actual:raise RuntimeError('Stored upload checksum mismatch')
     a['sha256']=actual;a['sha256_source']='existing_audio_file'
   actual_jobs=[]
   for j in jobs:
    j=dict(j)
    if j['error']:j['error']=sanitize_error_text(j['error'])
    actual_jobs.append(j)
   rows.append({'meeting':dict(m),'audio':a,'canonical':dict(canon) if canon else None,
                'segments':[dict(s) for s in segs],'jobs':actual_jobs})
  await db.rollback()
 await close_database_connections()
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open('x',encoding='utf-8') as f:
  json.dump({'timestamp_utc':datetime.now(timezone.utc).isoformat(),'since_meeting':str(args.since_meeting),
             'read_only':True,'inference_executed':False,'includes_failures':True,'meetings':rows},f,ensure_ascii=False,indent=2,default=str)
 print(json.dumps({'meetings':len(rows),'with_canonical':sum(bool(x['canonical']) for x in rows),
                   'failed_meetings':sum(x['meeting']['status']=='failed' for x in rows),'inference_executed':False}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--since-meeting',type=uuid.UUID,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 if a.output.exists():p.error('Preserve previous evidence; choose a new output file')
 asyncio.run(export(a))
