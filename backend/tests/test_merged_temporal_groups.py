"""Pure grouping contracts; no audio inference or generated benchmark data."""
import ast
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'scripts/evaluate_saved_merged_fleurs.py'
tree=ast.parse(path.read_text(encoding='utf-8'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='alignment_groups')
scope={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),scope)
groups=scope['alignment_groups']
refs=[{'start_time':0.,'end_time':10.},{'start_time':10.,'end_time':20.}]

def test_boundary_spanning_text_is_not_split():
    result=groups(refs,[{'start_time_ms':8000,'end_time_ms':12000}])
    assert len(result)==1 and result[0]['reference_indexes']==[0,1]
    assert result[0]['hypothesis_indexes']==[0]

def test_touching_edges_do_not_create_overlap():
    result=groups(refs,[{'start_time_ms':0,'end_time_ms':10000}])
    assert len(result)==2 and result[0]['reference_indexes']==[0]
    assert result[1]['hypothesis_indexes']==[]

def test_unmatched_hypothesis_is_retained():
    result=groups(refs,[{'start_time_ms':21000,'end_time_ms':22000}])
    assert any(g['reference_indexes']==[] and g['hypothesis_indexes']==[0] for g in result)
