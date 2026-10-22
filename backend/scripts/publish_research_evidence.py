"""Publish compact actual metric summaries for the authenticated research UI.

No inference, database mutation, synthetic runs, raw transcript or credential export.
"""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,timezone

def rate(value):
    return value.get('rate') if isinstance(value,dict) else value

def build(manual=None,merged=None,components=()):
    items=[];sources=[]
    for kind,path in [('historical_manual',manual),('concatenated_fleurs',merged)]+[('native_asr_component',p) for p in components]:
        if not path or not path.is_file():continue
        raw=path.read_bytes();data=json.loads(raw)
        sources.append({'kind':kind,'file':path.name,'sha256':hashlib.sha256(raw).hexdigest()})
        if kind=='native_asr_component':
            for group in data.get('groups',[]):
                items.append({'scope':data.get('scope',kind),'dataset':group.get('dataset'),
                    'language':group.get('language'),'attempted':group.get('attempted'),
                    'completed':group.get('completed'),'failed':group.get('failed'),
                    'WER':rate(group.get('WER')),'CER':rate(group.get('CER')),
                    'benchmark_run_id':data.get('benchmark_run_id'),'configuration':data.get('configuration_identity'),
                    'status':'OBSERVED_RESULTS; inspect failures and frozen source identities'})
            continue
        for sample in data.get('samples',[]):
            if kind=='historical_manual' and not sample.get('audio_filename'):continue
            items.append({'scope':kind,'dataset':sample.get('dataset','FLEURS_CONCATENATED'),
                'language':sample.get('language'),'meeting_id':sample.get('meeting_id'),
                'canonical_transcript_id':sample.get('canonical_transcript_id'),
                'label':sample.get('title',sample.get('sample_id')),
                'status':sample.get('accuracy_status',sample.get('status')),
                'meeting_status':sample.get('meeting_status'),'source_utterances':sample.get('source_utterances'),
                'scored_source_utterances':sample.get('scored_source_utterances'),
                'audio_identity':sample.get('audio_identity'),'WER':rate(sample.get('WER')),
                'CER':rate(sample.get('CER')),'DER':sample.get('DER'),'JER':sample.get('JER'),
                'diarization_status':sample.get('diarization_status'),
                'protocol_note':sample.get('ASR_protocol'),'failed_attempts':len(sample.get('failed_attempts',sample.get('failures',[])))})
    return {'timestamp_utc':datetime.now(timezone.utc).isoformat(),'verification':'CALCULATED_EVIDENCE_WITH_QUALIFICATIONS',
        'items':items,'sources':sources,'inference_executed_by_publisher':False,
        'limitations':['Dataset catalog does not mean tested coverage.',
            'Historical tuning/manual tests, native ASR components and concatenated recordings are separate conditions; do not pool them.',
            'Missing metrics are unknown. Read identity/protocol qualifications before using any value in a paper.',
            'IndicSUPERB Kathbath ASR and Kathbath are the same corpus, not independent datasets.',
            'ASR component scores do not establish complete production meeting-intelligence success.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manual',type=Path);p.add_argument('--merged',type=Path)
    p.add_argument('--component',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();value=build(args.manual,args.merged,args.component)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(args.output)
    print(json.dumps({'published_items':len(value['items']),'sources':len(value['sources']),'inference_executed':False}))
if __name__=='__main__':main()
