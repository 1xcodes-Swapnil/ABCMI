"""Offline saved-output evaluation. Never imports an AI provider or runs inference.

Run from the repository: python backend/scripts/evaluate_saved_research.py --output <new-folder>
Sources are immutable; copied attempts deduplicate by original run/sample/config/text identity.
"""
import argparse, csv, hashlib, json, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import version
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.benchmarks.metrics import normalize_text

@lru_cache(maxsize=2048)
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
 with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str)
def rel(path):return str(Path(path).relative_to(ROOT)).replace('\\','/')

def edit_metrics(reference,hypothesis):
 import jiwer
 from rapidfuzz.distance import Levenshtein
 r,h=normalize_text(reference),normalize_text(hypothesis)
 if not r:raise ValueError('Empty normalized ground truth: metric undefined')
 w=jiwer.process_words(r,h);c=jiwer.process_characters(r.replace(' ',''),h.replace(' ',''))
 def record(v,n):
  errors=v.substitutions+v.deletions+v.insertions
  return {'substitutions':v.substitutions,'deletions':v.deletions,'insertions':v.insertions,
          'reference_count':n,'errors':errors,'rate':errors/n}
 wm,cm=record(w,len(r.split())),record(c,len(r.replace(' ','')))
 assert wm['errors']==Levenshtein.distance(r.split(),h.split())
 assert cm['errors']==Levenshtein.distance(r.replace(' ',''),h.replace(' ',''))
 return {'WER':wm,'CER':cm,'normalized_reference':r,'normalized_hypothesis':h,
         'implementation_crosscheck':'jiwer edit counts == RapidFuzz exact distances'}

def geometry(segments):
 turns=[];bad=0
 for s in segments:
  start=s.get('start_time_ms',0)/1000 if 'start_time_ms' in s else s.get('start_time')
  end=s.get('end_time_ms',0)/1000 if 'end_time_ms' in s else s.get('end_time')
  speaker=s.get('speaker_label',s.get('speaker_id'))
  if start is None or end is None or start<0 or end<=start:bad+=1;continue
  turns.append({'start':start,'end':end,'speaker':speaker})
 overlaps=sum(1 for i,t in enumerate(turns) if any(p['end']>t['start'] and p['start']<t['end'] for p in turns[:i]))
 return turns,{'invalid_intervals':bad,'segments_with_prior_overlap':overlaps,
  'out_of_order':sum(b['start']<a['start'] for a,b in zip(turns,turns[1:])),
  'unresolved_segments':sum(t['speaker'] in (None,'UNRESOLVED','UNKNOWN') for t in turns),
  'distinct_literal_labels':len(set(t['speaker'] for t in turns))}

def diarization(ref,hyp,duration):
 from pyannote.core import Annotation,Segment,Timeline
 from pyannote.metrics.diarization import DiarizationErrorRate,JaccardErrorRate
 def ann(turns):
  a=Annotation()
  for i,t in enumerate(turns):a[Segment(t['start'],t['end']),i]=t['speaker'] or 'UNRESOLVED'
  # Multiple transcript turns from the SAME literal speaker may overlap.
  # Speaker activity is a union, not two simultaneous people. Preserve different labels.
  return a.support(collar=0.0)
 a,b=ann(ref),ann(hyp);uem=Timeline([Segment(0,duration)])
 # Separate standard scores: overlap included/excluded. Full audio UEM is explicit.
 out={}
 for overlap in [True,False]:
  key='overlap_included' if overlap else 'overlap_excluded'
  d=DiarizationErrorRate(collar=.25,skip_overlap=not overlap)(a,b,uem=uem,detailed=True)
  j=JaccardErrorRate(collar=.25,skip_overlap=not overlap)(a,b,uem=uem)
  out[key]={'DER':d.pop('diarization error rate'),'JER':j,'DER_components_seconds':d}
 return out

def discover():
 rows=[];excluded=[];seen={};references={}
 for tsv in sorted((ROOT/'data/benchmarks/fleurs').glob('*/test.tsv')):
  with tsv.open(encoding='utf-8') as f:
   for index,r in enumerate(csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE)):
    if not r.get('path') or not r.get('transcription'):
     excluded.append({'source':rel(tsv),'row':index,'reason':'malformed/missing TSV path or reference'});continue
    references[Path(r['path']).name]=(r['transcription'],tsv,tsv.parent/'audio/test'/Path(r['path']).name,r.get('id'))
 bases=[ROOT/'benchmark results/suite_20261008T121103Z',ROOT/'benchmark results/benchmark_fleurs_en_us_20261008T115951Z',
        ROOT/'benchmark results/research_reuse_20261020/sources']
 for base in bases:
  for p in sorted(base.rglob('*.json')):
   if p.name not in ('metrics.json','result.json','fix_verification.json'):continue
   d=load(p)
   if not isinstance(d,dict):continue
   reference=d.get('reference_transcript',d.get('reference',d.get('ground_truth_transcript')))
   hyp=d.get('predicted_transcript',d.get('hypothesis',d.get('text')))
   if reference is None or hyp is None:
    if d.get('status')=='FAILED':excluded.append({'source':rel(p),'reason':'FAILED saved attempt; no score fabricated'})
    continue
   identity=d.get('identity') or {k:d.get(k) for k in ('model','model_name','device','precision','chunk_duration','chunk_overlap','max_new_tokens')}
   identity.update(prompt_policy=d.get('prompt_policy'),source_family=base.name if 'sources'!=base.name else p.relative_to(base).parts[0])
   sid=d.get('benchmark_sample_id',d.get('sample_id','NOT AVAILABLE'))
   sha=d.get('audio_sha256',d.get('sha256'));run=d.get('benchmark_run_id',d.get('run_id','NOT AVAILABLE'))
   row={'run_id':run,'sample_id':sid,'dataset':d.get('dataset',d.get('dataset_name','FLEURS' if 'fleurs' in sid else 'NOT AVAILABLE')),
        'language':d.get('language'),'audio_sha256':sha,'reference':reference,'hypothesis':hyp,'configuration':identity,
        'duration_seconds':d.get('duration_seconds',d.get('duration')),'processing_seconds':d.get('processing_seconds',d.get('processing_time_seconds')),
        'source':rel(p),'source_sha256':digest(p),'canonical_transcript_id':d.get('canonical_transcript_id'),
        'metric_status':'VERIFIED_SAVED_TEXT_PAIR','scope':'historical exploratory output, not held-out acceptance'}
   # Establish ground-truth correspondence separately from a valid edit calculation.
   reference_match=None
   if 'fleurs' in sid.lower():
    names=[name for name in references if sid.endswith(Path(name).stem)]
    if len(names)==1:
     ref,refpath,audiopath,rid=references[names[0]]
     reference_match=(ref,refpath,audiopath)
     row['reference_row_id']=rid
     if not row['language']:row['language']=names[0].split('_')[0]
   elif sid.startswith('indicsuperb_'):
    lang=sid.split('_')[1];name=sid.removeprefix('indicsuperb_'+lang+'_')
    refpath=ROOT/'data/benchmarks/indicsuperb'/lang/'known/transcript.txt'
    if refpath.is_file():
     table=dict(line.rstrip('\n').split('\t',1) for line in refpath.read_text(encoding='utf-8').splitlines() if '\t' in line)
     if name in table:reference_match=(table[name],refpath,refpath.parent/'audio'/(name+'.wav'))
     row['dataset_relationship']='Kathbath ASR within IndicSUPERB; not an independent second dataset'
   if not sha and (p.parent/'input.json').is_file():
    inp=load(p.parent/'input.json');sha=inp.get('sha256',inp.get('audio_sha256'));row['audio_sha256']=sha
   if reference_match:
    ref,refpath,audiopath=reference_match
    row['reference_source']=rel(refpath);row['reference_sha256']=digest(refpath)
    row['reference_text_matches_annotation']=normalize_text(ref)==normalize_text(reference)
    row['audio_matches_reference_file']=bool(sha and audiopath.is_file() and digest(audiopath)==sha)
    row['metric_status']='VERIFIED_HASH_MATCHED_NATIVE_REFERENCE' if row['reference_text_matches_annotation'] and row['audio_matches_reference_file'] else 'SAVED_PAIR_ONLY_REFERENCE_IDENTITY_NOT_VERIFIED'
   # Original stable IDs and actual text remove copies, never deduplicate different hypotheses/configurations.
   key=json.dumps([run,sid,sha,reference,hyp,d.get('prompt_policy')],ensure_ascii=False,sort_keys=True)
   if key in seen:
    excluded.append({'source':rel(p),'reason':'copied attempt already counted','original':seen[key]});continue
   seen[key]=rel(p);rows.append(row)
 dbpath=ROOT/'benchmark results/research_reuse_20261020/sources/research_reuse_20261020/saved_database_exports.json'
 known_canon={r['canonical_transcript_id'] for r in rows if r['canonical_transcript_id']}
 for v in load(dbpath)['meetings']:
  a=v['audio'];m=v['meeting'];c=v['canonical'];fname=a['file_name'];segs=v['segments'];sha=a['sha256']
  if c['id'] in known_canon:
   excluded.append({'meeting_id':m['id'],'reason':'same canonical transcript already evaluated'});continue
  row={'run_id':c['id'],'sample_id':fname,'dataset':'NOT VERIFIED','language':m['language'],
       'meeting_id':m['id'],'canonical_transcript_id':c['id'],'audio_sha256':sha,
       'duration_seconds':a['duration_seconds'],'source':rel(dbpath),'source_sha256':digest(dbpath),
       'segments':segs,'configuration':{'saved_model_provenance':c.get('provenance',{}).get('model',{}),
        'scope':'persisted final transcript; full inference identity may be incomplete'},
       'hypothesis':' '.join(s['original_text'] for s in segs),'reference':None,
       'metric_status':'NOT VERIFIED','scope':'saved application output, no inference executed'}
  if fname in references:
   ref,path,audiopath,rid=references[fname]
   if not sha or not audiopath.is_file() or digest(audiopath)!=sha:
    excluded.append({'meeting_id':m['id'],'reason':'cannot prove audio hash correspondence; no reference assigned'});continue
   row.update(dataset='FLEURS',reference=ref,reference_source=rel(path),reference_sha256=digest(path),reference_row_id=rid,metric_status='VERIFIED_HASH_MATCHED_NATIVE_REFERENCE')
  elif fname and fname.startswith('vox_'):
   audio=ROOT/'data/benchmarks/voxconverse/audio/test'/fname;rttm=ROOT/'data/benchmarks/voxconverse/rttm_recovered'/Path(fname).with_suffix('.rttm')
   if not sha or not audio.is_file() or digest(audio)!=sha or not rttm.is_file():
    excluded.append({'meeting_id':m['id'],'reason':'VoxConverse matched audio/non-empty annotation unavailable'});continue
   turns=[]
   for line in rttm.read_text().splitlines():
    x=line.split();turns.append({'start':float(x[3]),'end':float(x[3])+float(x[4]),'speaker':x[7]})
   row.update(dataset='VoxConverse',reference_turns=turns,reference_source=rel(rttm),reference_sha256=digest(rttm),metric_status='VERIFIED_WAVEFORM_MATCHED_REFERENCE')
  elif fname in ('ES2002a.Mix-Headset.wav','ES2014d.Mix-Headset.wav'):
   name=fname.split('.')[0];evidence=ROOT/('benchmark results/jarvislabs_'+name+('_20261015' if name=='ES2002a' else '_20261016'))/'development_result.json'
   old=load(evidence);audio=ROOT/'data/audio/raw'/fname;expected=old['audio']['audio_sha256']
   if not audio.is_file() or digest(audio)!=expected:
    excluded.append({'meeting_id':m['id'],'reason':'AMI source audio/canonical identity mismatch'});continue
   if old['canonical_transcript_id']!=c['id']:
    saved=load(evidence.parent/'fresh_readback.json')
    if old['meeting_id']!=m['id'] or saved['canonical_transcript']['full_text']!=c['full_text']:
     excluded.append({'meeting_id':m['id'],'reason':'AMI changed canonical text cannot be linked to saved inference'});continue
    row['posthoc_speaker_correction']=True
    row['original_canonical_transcript_id']=old['canonical_transcript_id']
    row['canonical_text_unchanged_from_original_run']=True
   words=[];refturns=[];src=[]
   for p in sorted((ROOT/'data/benchmarks/ami').rglob(name+'.*.words.xml')):
    src.append({'path':rel(p),'sha256':digest(p)})
    for n in ET.parse(p).getroot().iter():
     if n.tag.split('}')[-1]=='w' and 'starttime' in n.attrib and 'endtime' in n.attrib and ''.join(n.itertext()).strip():
      words.append((float(n.attrib['starttime']),float(n.attrib['endtime']),''.join(n.itertext()).strip()))
   for p in sorted((ROOT/'data/benchmarks/ami').rglob(name+'.*.segments.xml')):
    src.append({'path':rel(p),'sha256':digest(p)})
    for n in ET.parse(p).getroot().iter():
     start=n.attrib.get('transcriber_start',n.attrib.get('starttime'));end=n.attrib.get('transcriber_end',n.attrib.get('endtime'))
     if n.tag.split('}')[-1]=='segment' and start is not None and end is not None and float(end)>float(start):
      refturns.append({'start':float(start),'end':float(end),'speaker':p.name.split('.')[1]})
   row.update(dataset='AMI',audio_sha256=expected,reference=' '.join(w[2] for w in sorted(words)),reference_turns=refturns,
              reference_sources=src,metric_status='EXPLORATORY_CHRONOLOGICAL_WORD_PROXY',
              limitation='Reference simultaneous words interleave; chronological WER is not standardized speaker-attributed AMI WER; official partition NOT VERIFIED')
  else:
   excluded.append({'meeting_id':m['id'],'reason':'no matched full-recording ground truth; not scored'});continue
  rows.append(row)
 return rows,excluded

def score(row):
 if row.get('reference') is not None:
  row.update(edit_metrics(row['reference'],row['hypothesis']))
 if row.get('segments'):
  turns,quality=geometry(row['segments']);row['segment_validation']=quality
  if row.get('reference_turns'):
   if quality['invalid_intervals']:row['diarization_status']='NOT VERIFIED: invalid hypothesis intervals'
   else:
    row['diarization_metrics']=diarization(row['reference_turns'],turns,row['duration_seconds'])
    row['diarization_status']='DIAGNOSTIC_UNRESOLVED_LABEL_BUCKET' if quality['unresolved_segments'] else 'VERIFIED_FINAL_TRANSCRIPT_TURN_PROTOCOL'
    row['diarization_scope']='Final transcript speaker intervals, not raw PyAnnote boundaries. Literal UNRESOLVED is one unknown bucket, not a claimed human identity.'
 row['timestamp_error']='NOT VERIFIED: no validated word/utterance correspondence'
 return row

def aggregate(rows):
 groups={}
 for r in rows:
  # Do not pool versions, dataset/language, component versus production, or unknown profiles.
  cfg=hashlib.sha256(json.dumps(r['configuration'],sort_keys=True,default=str).encode()).hexdigest()[:12]
  key=(r['dataset'],r['language'],cfg,r['metric_status'])
  groups.setdefault(key,[]).append(r)
 out=[]
 for (dataset,lang,cfg,status),rs in groups.items():
  g={'dataset':dataset,'language':lang,'configuration_id':cfg,'status':status,'samples':len(rs),
     'sample_ids':[r['sample_id'] for r in rs],'WER':None,'CER':None}
  for metric in ['WER','CER']:
   ms=[r[metric] for r in rs if r.get(metric)];n=sum(m['reference_count'] for m in ms)
   if n:g[metric]={'rate':sum(m['errors'] for m in ms)/n,'reference_count':n,
                  **{k:sum(m[k] for m in ms) for k in ['substitutions','deletions','insertions','errors']}}
  out.append(g)
 return out

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=4)
 args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 rows,excluded=discover();write(args.output/'input_inventory.json',{'rows':rows,'excluded':excluded})
 with ThreadPoolExecutor(max_workers=min(4,max(1,args.workers))) as pool:scored=list(pool.map(score,rows))
 for i,r in enumerate(scored):write(args.output/f'sample_{i:04}.json',r)
 groups=aggregate(scored)
 summary={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'inference_executed':False,'parallel_cpu_workers':min(4,max(1,args.workers)),
          'source_code_sha256':digest(__file__),'versions':{p:version(p) for p in ['jiwer','rapidfuzz','pyannote.metrics','pyannote.core']},
          'normalization':'NFC, casefold, Unicode L/M/N retained; punctuation->space; collapse whitespace; CER removes spaces. No transliteration, spelling guessing, translation, or reference-based correction.',
          'diarization_protocol':'pyannote.metrics, collar parameter 0.25 s, full actual audio UEM [0,duration], overlap included and excluded reported separately; reference tails retained but excluded by UEM. Same-label intervals unioned via Annotation.support(collar=0); different speakers remain overlapping. Posthoc speaker corrections flagged separately.',
          'evaluated_saved_attempts':len(scored),'unique_audio_hashes':len({r['audio_sha256'] for r in scored if r.get('audio_sha256')}),
          'groups':groups,'excluded':excluded,'failed_saved_attempts_are_not_zero_error':True,
          'publication_status':'EXPLORATORY: historical convenience samples/configuration changes; no claim of representative held-out performance'}
 write(args.output/'summary.json',summary)
 with (args.output/'samples.csv').open('x',encoding='utf-8-sig',newline='') as f:
  fields=['dataset','language','sample_id','run_id','meeting_id','canonical_transcript_id','audio_sha256','metric_status','WER','CER','DER','JER','diarization_status','source']
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for r in scored:
   v={k:r.get(k) for k in fields};v['WER']=r.get('WER',{}).get('rate');v['CER']=r.get('CER',{}).get('rate')
   dm=r.get('diarization_metrics',{}).get('overlap_included',{});v['DER']=dm.get('DER');v['JER']=dm.get('JER');writer.writerow(v)
 report=['# Saved-output research evaluation','',f"Evaluated {len(scored)} saved attempts; {summary['unique_audio_hashes']} distinct audio hashes. No audio inference or pipeline changes.",'',
 '## ASR results','', '| Dataset | Language | Profile | N | WER | CER | Status |','|---|---|---|---:|---:|---:|---|']
 for g in groups:
  if not g['WER']:continue
  report.append(f"| {g['dataset']} | {g['language']} | {g['configuration_id']} | {g['samples']} | {g['WER']['rate']:.2%} | {g['CER']['rate']:.2%} | {g['status']} |")
 report+=['','## Final-transcript diarization','','| Sample | DER (overlap included) | JER | Status |','|---|---:|---:|---|']
 for r in scored:
  dm=r.get('diarization_metrics',{}).get('overlap_included')
  if dm:report.append(f"| {r['sample_id']} | {dm['DER']:.2%} | {dm['JER']:.2%} | {r['diarization_status']} |")
 report+=['','## Interpretation and limits','',summary['normalization'],'',summary['diarization_protocol'],'',
 'WER/CER are corpus edit-count ratios within each compatible profile, not means of utterance percentages. Errors may exceed 100%. WER is not converted to a universal accuracy score. No confidence intervals or significance claims are made from these small convenience samples.',
 '', 'These are historical exploratory results, including clips already used in debugging. They cannot serve as a fresh held-out estimate. AMI chronological word overlap is only a proxy when speech overlaps; no standardized AMI ASR acceptance claim. UNRESOLVED speaker buckets make diarization interpretation provisional. These scores use final transcript spans, not full acoustic diarizer spans.',
 '', 'Missing ground truth is unverified, never zero. AISHELL has no scored saved output in this collection. IndicSUPERB ASR samples are Kathbath recordings: do not count the same audio again as an independent Kathbath dataset. BLEU/language identification/timestamp accuracy are not established by this evaluation.',
 '', 'Next research cohort: FLEURS 100 per language × 3 languages (300 total); Kathbath 100 per selected language (300 total, not duplicated as IndicSUPERB); VoxConverse 30 complete held-out clips; AMI 3 full meetings with proven official split; AISHELL 300 official-test utterances if complete audio/labels exist. Exclude this tuning set. These are proposed resource-bounded subsets, not conference requirements. Freeze settings before inference. Existing outputs count toward historical evidence, not automatically toward a new profile.',
 '', 'Reproduce: `python backend/scripts/evaluate_saved_research.py --output "benchmark results/<new-output>" --workers 4`','']
 (args.output/'REPORT.md').write_text('\n'.join(report),encoding='utf-8')
 print(json.dumps({k:summary[k] for k in ['evaluated_saved_attempts','unique_audio_hashes','inference_executed']}))
if __name__=='__main__':main()
