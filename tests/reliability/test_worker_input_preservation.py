from sqlalchemy import select

from aftercare.config import Settings
from aftercare.repositories.models import Job
from aftercare.workers import worker
from evaluation.reliability.cases import prepare


def test_failed_execution_preserves_original_trusted_binding(service, monkeypatch):
    conv, pid, event = prepare(service, job=True)

    def fail(*args, **kwargs):
        raise EOFError("execution child died")

    monkeypatch.setattr(worker, "bounded", fail)
    settings = Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )
    assert worker.run_once(settings)
    with service.sessions() as session:
        job = session.scalar(select(Job).where(Job.conversation_id == conv))
        assert job.status == "FAILED"
        assert job.result["confirmation"] == event["confirmation"]
        assert job.result["error_code"] == "WORKER_FAILED"
