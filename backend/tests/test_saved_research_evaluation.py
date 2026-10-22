"""No-model contracts for reuse-only scoring."""
import importlib.util
from pathlib import Path
import pytest

p=Path(__file__).resolve().parents[1]/'scripts/evaluate_saved_research.py'
spec=importlib.util.spec_from_file_location('saved_eval',p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_identical_and_unicode():
 assert module.edit_metrics('CAFÉ नमस्ते','cafe\u0301 नमस्ते')['WER']['rate']==0

@pytest.mark.parametrize('ref,hyp,s,d,i',[('a b','a c',1,0,0),('a b','a',0,1,0),('a','a b',0,0,1)])
def test_edit_counts(ref,hyp,s,d,i):
 m=module.edit_metrics(ref,hyp)['WER']
 assert (m['substitutions'],m['deletions'],m['insertions'])==(s,d,i)

def test_empty_reference_is_undefined():
 with pytest.raises(ValueError):module.edit_metrics('!!!','words')
 assert module.edit_metrics('words','')['WER']['rate']==1

def test_no_guessed_transliteration():
 assert module.edit_metrics('नमस्ते friend','namaste friend')['WER']['substitutions']==1

def test_aggregate_counts_not_rates():
 rows=[]
 for ref,hyp in [('a','b'),('a a a a a a a a a','a a a a a a a a a')]:
  rows.append({'configuration':{},'dataset':'x','language':'en','metric_status':'x','sample_id':ref,**module.edit_metrics(ref,hyp)})
 assert module.aggregate(rows)[0]['WER']['rate']==.1

def test_geometry_reports_overlap_and_invalid():
 _,q=module.geometry([{'start_time':0,'end_time':2,'speaker_id':'A'},
                      {'start_time':1,'end_time':3,'speaker_id':'UNRESOLVED'},
                      {'start_time':4,'end_time':3,'speaker_id':'B'}])
 assert q['invalid_intervals']==1 and q['segments_with_prior_overlap']==1 and q['unresolved_segments']==1

def test_diarization_same_speaker_overlap_is_union():
 ref=[{'start':0.,'end':3.,'speaker':'A'}]
 hyp=[{'start':0.,'end':2.,'speaker':'X'},{'start':1.,'end':3.,'speaker':'X'}]
 m=module.diarization(ref,hyp,3.)
 assert m['overlap_included']['DER']==0 and m['overlap_included']['JER']==0

def test_diarization_different_speakers_remain_overlap():
 ref=[{'start':0.,'end':3.,'speaker':'A'}]
 hyp=[{'start':0.,'end':3.,'speaker':'X'},{'start':1.,'end':2.,'speaker':'Y'}]
 assert module.diarization(ref,hyp,3.)['overlap_included']['DER']>0
