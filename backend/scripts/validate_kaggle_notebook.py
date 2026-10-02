"""Cheap artifact checks only. Never execute notebook inference or downloads."""
import ast
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

root=Path(__file__).resolve().parents[2]
path=root/'notebooks/ABCI_MI_Full_Application_Kaggle_REAL.ipynb'
data=path.read_bytes()
notebook=json.loads(data)
code_cells=[c for c in notebook['cells'] if c['cell_type']=='code']
constants={}
for index,cell in enumerate(code_cells):
    source=''.join(cell['source'])
    tree=ast.parse(source)
    compile(tree,f'notebook_cell_{index}','exec')
    assert cell['execution_count'] is None and not cell['outputs']
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            if node.targets[0].id in ('BACKEND_SOURCE_ZIP_B64','SOURCE_ARCHIVE_SHA256','SOURCE_MANIFEST','SOURCE_COMMIT'):
                constants[node.targets[0].id]=ast.literal_eval(node.value)
    # Runtime line separators must be newlines, not literal backslash-n strings.
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write_text':
            if node.args and isinstance(node.args[0],ast.JoinedStr):
                fragments=[v.value for v in node.args[0].values if isinstance(v,ast.Constant) and isinstance(v.value,str)]
                assert not any('\\n' in v for v in fragments), 'Literal backslash-n in runtime text file'
archive=base64.b64decode(constants['BACKEND_SOURCE_ZIP_B64'])
assert hashlib.sha256(archive).hexdigest()==constants['SOURCE_ARCHIVE_SHA256']
embedded=[]
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    assert set(z.namelist())==set(constants['SOURCE_MANIFEST'])
    for name in z.namelist():
        assert not name.startswith('/') and '..' not in Path(name).parts
        assert '.env' not in Path(name).parts and '.git' not in Path(name).parts
        content=z.read(name)
        assert hashlib.sha256(content).hexdigest()==constants['SOURCE_MANIFEST'][name]
        assert content==(root/name).read_bytes(), 'Embedded source is stale: '+name
        if name.endswith('.py'): compile(content,name,'exec')
        assert not re.search(rb'hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{25,}',content)
        embedded.append(content)
for env in (root/'.env',root/'backend/.env'):
    if not env.exists(): continue
    for line in env.read_text(encoding='utf-8').splitlines():
        if '=' not in line or line.lstrip().startswith('#'): continue
        key,value=line.split('=',1); value=value.strip().strip('"\'')
        if len(value)>=12 and any(k in key.upper() for k in ('TOKEN','PASSWORD','API_KEY')):
            secret=value.encode()
            assert secret not in data and all(secret not in content for content in embedded), 'Private credential embedded'
schema='NOT AVAILABLE'
try:
    import nbformat
except ImportError:
    pass
else:
    nbformat.validate(nbformat.from_dict(notebook)); schema='PASSED'
report={'timestamp':datetime.now(timezone.utc).isoformat(),'artifact':str(path.relative_to(root)),
    'notebook_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'cells':len(notebook['cells']),
    'compiled_code_cells':len(code_cells),'embedded_source_files':len(constants['SOURCE_MANIFEST']),
    'embedded_source_python_compile':'PASSED','archive_integrity':'PASSED','current_source_matches':'PASSED',
    'credential_exclusion':'PASSED','nbformat_schema':schema,'source_archive_sha256':constants['SOURCE_ARCHIVE_SHA256'],
    'git_commit':constants['SOURCE_COMMIT'],'kaggle_execution':'NOT EXECUTED','real_inference':'NOT VERIFIED',
    'end_to_end':'NOT VERIFIED','validation_scope':'Artifact syntax/integrity only; no model, audio, network or service execution'}
out=root/'e2e_validation/diagnostics'/('kaggle_notebook_build_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
out.parent.mkdir(parents=True,exist_ok=True)
with out.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
print(json.dumps(report,indent=2))
print('Evidence:',out)
