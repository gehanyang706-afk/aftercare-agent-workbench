import json
import time
from threading import Event

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from aftercare.agent.runtime import factory, run_turn, setup_checkpoints
from aftercare.agent.tools import ALLOWED
from aftercare.config import Settings
from aftercare.domain.contracts import BusinessError
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel, call, response
from aftercare.llm.supervisor import bounded


def settings(service):
    return Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )


def test_scripted_real_tool_roundtrip_parallel_and_hitl(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 换大一码", "first")
    graph, model = factory(service, "alice", conv, InMemorySaver())
    config = {"configurable": {"thread_id": conv}, "recursion_limit": 96}
    result = graph.invoke({"messages": [HumanMessage(content=msg["text"], id=msg["id"])]}, config)
    assert result.get("__interrupt__")
    assert set(model.shared["tool_names"]) == ALLOWED
    snapshot = service.snapshot("alice", conv)
    pid = snapshot["previews"][0]["id"]
    assert snapshot["status"] == "WAITING_CONFIRMATION"
    service.confirm("alice", pid, True)
    result = graph.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
    assert "EXCHANGE_REQUESTED" in result["messages"][-1].content
    receipt = service.get_operation("alice", preview_id=pid)
    assert receipt["status"] == "COMMITTED"
    calls = {c["id"] for m in result["messages"] if hasattr(m, "tool_calls") for c in m.tool_calls}
    replies = {m.tool_call_id for m in result["messages"] if isinstance(m, ToolMessage)}
    assert calls == replies


def test_persistent_restart_and_new_message_reject_old_interrupt(service):
    config = settings(service)
    setup_checkpoints(config)
    conv = service.create_conversation("alice")
    first = service.append_message("alice", conv, "S1002 换大一码", "1")
    assert run_turn(config, service, "alice", conv, first["id"]).get("__interrupt__")
    old = service.snapshot("alice", conv)["previews"][0]["id"]
    second = service.append_message("alice", conv, "改成退货", "2")
    result = run_turn(config, service, "alice", conv, second["id"])
    assert result.get("__interrupt__")
    previews = service.snapshot("alice", conv)["previews"]
    assert next(p for p in previews if p["id"] == old)["status"] == "INVALIDATED"
    current = next(p for p in previews if p["status"] == "PENDING")
    assert current["payload"]["action"] == "return"
    service.confirm("alice", current["id"], True)
    # Rebuild a new graph/checkpointer instance: approval remains a business fact.
    result = run_turn(config, service, "alice", conv, resume=True)
    assert service.get_operation("alice", preview_id=current["id"])["result"] == "RETURN_REQUESTED"


def test_graph_approval_cannot_forge_business_approval(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 换大一码", "1")
    graph, _ = factory(service, "alice", conv, InMemorySaver())
    config = {"configurable": {"thread_id": conv}}
    graph.invoke({"messages": [HumanMessage(content=msg["text"], id=msg["id"])]}, config)
    graph.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
    pid = service.snapshot("alice", conv)["previews"][0]["id"]
    with pytest.raises(BusinessError, match="NOT_FOUND"):
        service.get_operation("alice", preview_id=pid)


def test_forbidden_tool_and_forged_arguments_produce_paired_errors(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "查询订单", "1")
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conv,
        run_id="bad-tools",
        responses=[
            response(
                calls=[
                    call("write_file", {"file_path": "/x", "content": "malicious"}),
                    call("get_order", {"order_id": "S1002", "principal": "bob", "approved": True}),
                ]
            ),
            response("停止非法操作"),
        ],
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
        {"configurable": {"thread_id": conv}},
    )
    replies = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(replies) == 2
    assert {json.loads(m.content)["error_code"] for m in replies} == {
        "TOOL_FORBIDDEN",
        "INVALID_TOOL_ARGUMENTS",
    }


def block_forever():
    while True:
        time.sleep(60)


def test_hard_deadline_and_cancel_cleanup():
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="DEADLINE"):
        bounded(block_forever, seconds=0.3)
    assert time.monotonic() - start < 3
    cancel = Event()
    cancel.set()
    with pytest.raises(TimeoutError, match="CANCELLED"):
        bounded(block_forever, seconds=5, cancel=cancel)


def test_schema_recovery_is_bounded(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "查询订单", "x")
    invalid = response(calls=[call("get_order", {"order_id": "S1002", "amount": 1})])
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conv,
        run_id="invalid",
        responses=[invalid, invalid, invalid],
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
        {"configurable": {"thread_id": conv}},
    )
    assert model.shared["calls"] == 2
    assert "停止" in result["messages"][-1].content


def test_no_reservation_means_no_model_invocation(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "查询", "a")
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="cap", cap=1
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    with pytest.raises(BusinessError, match="BUDGET_EXHAUSTED"):
        graph.invoke(
            {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
            {"configurable": {"thread_id": conv}},
        )
    assert model.shared["calls"] == 0


def test_commit_survives_checkpoint_not_yet_written(service):
    cfg = settings(service)
    setup_checkpoints(cfg)
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 换大一码", "first")
    run_turn(cfg, service, "alice", conv, msg["id"])
    pid = service.snapshot("alice", conv)["previews"][0]["id"]
    service.confirm("alice", pid, True)
    receipt = service.commit("alice", pid)
    # Restart at the still-pending interrupt as if the process died before graph checkpoint.
    run_turn(cfg, service, "alice", conv, resume=True)
    assert service.get_operation("alice", preview_id=pid) == receipt
    from sqlalchemy import func, select

    from aftercare.repositories.models import Application

    with service.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Application)) == 1
