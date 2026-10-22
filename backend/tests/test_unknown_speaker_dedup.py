"""Exercise actual pure dedup methods without importing/loading AI models or audio.

AST extraction isolates the production methods, not a rewritten algorithm. These
are unit contracts only, not transcript/accuracy/REAL-inference evidence.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

source=Path(__file__).resolve().parents[1]/'app/ai/long_audio_processor.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LongAudioProcessor')
cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in
          {'_text_similarity','_same_observed_turn','merge_and_deduplicate_chunks'}]
namespace={'List':list,'Tuple':tuple,'ChunkMetadata':object,'ASRSegment':object}
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(source),'exec'),namespace)
Processor=namespace['LongAudioProcessor']

def segment(speaker,ident):
    return SimpleNamespace(speaker_id=speaker,segment_id=ident,start_time=8.,end_time=12.,transcript='same observed phrase')

@pytest.mark.parametrize('speaker',[None,'','  ','UNRESOLVED','SPEAKER_UNKNOWN','UNKNOWN','unresolved'])
def test_unknown_is_not_identity(speaker):
    assert not Processor._same_observed_turn(segment(speaker,'a'),segment(speaker,'b'))

def test_known_matching_identity_still_deduplicates():
    assert Processor._same_observed_turn(segment('pyannote_global_0','a'),segment('pyannote_global_0','b'))
    assert not Processor._same_observed_turn(segment('pyannote_global_0','a'),segment('pyannote_global_1','b'))

def test_ambiguous_boundary_retains_both_observations():
    p=Processor();a,b=segment('UNRESOLVED','a'),segment('UNRESOLVED','b')
    metas=[SimpleNamespace(start_time=0.,end_time=12.),SimpleNamespace(start_time=8.,end_time=20.)]
    merged,removed=p.merge_and_deduplicate_chunks(metas,[[a],[b]])
    assert len(merged)==2 and removed==0
    assert any(d.get('requires_boundary_review') and not d.get('duplicate_verified') for d in p.last_dedup_decisions)
