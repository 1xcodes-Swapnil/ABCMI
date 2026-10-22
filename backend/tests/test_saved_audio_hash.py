"""Byte identity contract only; no audio generated or processed."""
import ast
import hashlib
from pathlib import Path

def test_bounded_saved_upload_hash(tmp_path):
    path=Path(__file__).resolve().parents[1]/'app/services/meeting_service.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_saved_audio_sha256')
    scope={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),scope)
    payload=b'byte-identity-contract' * 60000
    saved=tmp_path/'bytes.bin';saved.write_bytes(payload)
    assert scope['_saved_audio_sha256'](saved)==hashlib.sha256(payload).hexdigest()
    assert saved.read_bytes()==payload
