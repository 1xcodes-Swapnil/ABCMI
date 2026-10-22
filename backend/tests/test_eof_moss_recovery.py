"""No-model contract checks for the production final-chunk recovery closure."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'app/ai/multilingual_asr.py'

def recovery(tmp_path, generated_attempt=None):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'recover_with_context')
    calls = []
    async def transcribe(options):
        calls.append(options)
        return ['actual-provider-result-contract']
    provider = SimpleNamespace(last_inference={})
    namespace = dict(validate_audio=lambda path: {'duration': 100.}, audio_file_path='unused-contract-path',
        settings=SimpleNamespace(AUDIO_CHUNK_OVERLAP_SECONDS=4.),
        chunk_meta=SimpleNamespace(end_time=100.,start_time=96.,duration=4.,chunk_id='last'),
        history=tmp_path,chunk_digest='unit-contract-only',json=json,real_provider=provider,
        transcribe_recovery=transcribe,journal_generation=lambda value: None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(SOURCE),'exec'),namespace)
    return namespace['recover_with_context'],calls,provider

def test_final_chunk_retries_original_audio_once(tmp_path):
    function,calls,provider = recovery(tmp_path)
    generated={'recovery_attempt':'bounded_bounds_beam_v5','raw_text':'unit contract'}
    assert asyncio.run(function(generated)) == ['actual-provider-result-contract']
    assert len(calls)==1 and calls[0]['recover_format'] is True
    assert 'boundary_context' not in calls[0]
    assert json.loads((tmp_path/'generation_failed_eof_last.json').read_text())==generated
    assert provider.last_inference['end_of_recording_recovery']=='bounded_format_original_audio'

def test_final_format_failure_does_not_loop(tmp_path):
    function,calls,_ = recovery(tmp_path)
    with pytest.raises(RuntimeError,match='recording end'):
        asyncio.run(function({'recovery_attempt':'bounded_format_prompt_v3'}))
    assert not calls
