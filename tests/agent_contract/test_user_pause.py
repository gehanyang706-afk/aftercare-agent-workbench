"""A direct no-submit instruction must end this turn without model proposals."""

import pytest
from sqlalchemy import func, select

from aftercare.agent.runtime import run_turn
from aftercare.repositories.models import Application, ModelCall, Operation, Reservation
from tests.agent_contract.test_confirmation_continuation import config, start


@pytest.mark.parametrize("pending", [False, True])
def test_no_submit_does_not_invoke_graph_or_model(service, monkeypatch, pending):
    if pending:
        settings, conv, pid, _ = start(service, False)
    else:
        settings = config(service)
        conv = service.create_conversation("alice")
        service.append_message("alice", conv, "S1002 两件换白色 L 码", "first")
        pid = None
    msg = service.append_message("alice", conv, "保留两件等待补货，暂不提交。", "pause")

    def forbidden(*args, **kwargs):
        pytest.fail("Explicit pause must not construct or invoke a model graph")

    monkeypatch.setattr("aftercare.agent.runtime.agent_runtime", forbidden)
    for _ in range(2):
        result = run_turn(settings, service, "alice", conv, msg["id"])
        assert result["task_state"] == "PAUSED_BY_USER"
        assert result["receipt"] is None
        assert "暂不提交" in result["communications"][-1]
        assert "请问" not in result["communications"][-1]
        assert "？" not in result["communications"][-1]
    snap = service.snapshot("alice", conv)
    assert snap["task_state"] == "PAUSED_BY_USER"
    if pid:
        assert next(p for p in snap["previews"] if p["id"] == pid)["status"] == "INVALIDATED"
    with service.sessions() as s:
        for table in (Operation, Application, Reservation):
            assert s.scalar(select(func.count()).select_from(table)) == 0
        if not pending:
            assert s.scalar(select(func.count()).select_from(ModelCall)) == 0


def test_pause_recognizer_is_bounded():
    from aftercare.services.user_pause import explicit_pause

    for text in ("暂不提交。", "保留两件等待补货，暂不提交。", "停止办理"):
        assert explicit_pause(text)
    for text in (
        "如果缺货就暂不提交",
        "不是暂不提交，我要办理",
        "不要理解成暂不提交",
        "另一个订单暂不提交，S1002 退一件",
        "请问暂不提交是什么意思？",
    ):
        assert not explicit_pause(text)


def test_workbench_pause_uses_same_runtime(service):
    from fastapi.testclient import TestClient

    from aftercare.agent.runtime import setup_checkpoints
    from aftercare.api.app import create_app
    from aftercare.domain.contracts import utc_now
    from aftercare.workers.worker import run_once

    service.clock = utc_now
    settings = config(service)
    setup_checkpoints(settings)
    app = create_app(settings)
    app.state.business = service
    client = TestClient(app)
    who = client.post("/api/demo-sessions", json={"customer_id": "alice"}).json()
    client.headers["X-CSRF-Token"] = who["csrf_token"]
    conv = service.create_conversation("alice")
    reply = client.post(
        f"/api/conversations/{conv}/messages",
        json={
            "text": "暂不提交。",
            "client_message_id": "pause-api",
        },
    )
    assert reply.status_code == 202
    assert run_once(settings)
    snap = client.get(f"/api/conversations/{conv}").json()
    assert snap["task_state"] == "PAUSED_BY_USER"
    assert snap["graph_state"] == "NOT_INVOKED"
    assert not snap["previews"]
    with service.sessions() as s:
        assert s.scalar(select(func.count()).select_from(ModelCall)) == 0


def test_old_pause_cannot_override_new_intent(service):
    from aftercare.domain.contracts import BusinessError

    settings = config(service)
    conv = service.create_conversation("alice")
    old = service.append_message("alice", conv, "暂不提交。", "pause")
    service.append_message("alice", conv, "S1002 退其中一件", "new")
    with pytest.raises(BusinessError, match="INTENT_CHANGED"):
        run_turn(settings, service, "alice", conv, old["id"])


def test_pause_after_previous_submission_does_not_cancel_it(service):
    from tests.agent_contract.test_confirmation_continuation import counts, resume

    settings, conv, pid, _ = start(service)
    confirmed = service.confirm("alice", pid, True)
    receipt = resume(settings, service, conv, confirmed)["receipt"]
    msg = service.append_message("alice", conv, "暂不提交。", "pause")
    result = run_turn(settings, service, "alice", conv, msg["id"])
    assert counts(service) == (1, 1, 1)
    assert service.get_operation("alice", preview_id=pid) == receipt
    assert "不会因此撤销" in result["communications"][-1]
