"""Cheap contract checks for the internal upload lease exception."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import uuid


def test_only_current_exclusive_finalize_lease_can_bypass_upload_guard():
    path = Path(__file__).resolve().parents[1]/'app/services/meeting_service.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    expr = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'own_finalization' for t in n.targets)
                and isinstance(n.value, ast.Call))
    code = compile(ast.Expression(expr), str(path), 'eval')
    job_id, token = uuid.uuid4(), uuid.uuid4()
    def allowed(**changes):
        fields = dict(id=job_id, lease_token=token, kind='finalize', status='running',
                      lease_until=datetime.now(timezone.utc)+timedelta(seconds=60))
        extra = changes.pop('extra', False)
        fields.update(changes)
        jobs = [SimpleNamespace(**fields)]
        if extra:
            jobs.append(SimpleNamespace(**fields))
        return eval(code, {'active_jobs':jobs, 'job_id':job_id, 'lease_token':token,
                           'datetime':datetime, 'timezone':timezone})
    assert allowed()
    assert not allowed(id=uuid.uuid4())
    assert not allowed(lease_token=uuid.uuid4())
    assert not allowed(kind='batch')
    assert not allowed(status='failed')
    assert not allowed(lease_until=datetime.now(timezone.utc)-timedelta(seconds=1))
    assert not allowed(extra=True)
