import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select

from aftercare.agent.runtime import run_turn
from aftercare.agent.tools import ALLOWED
from aftercare.config import Settings
from aftercare.domain.contracts import BusinessError
from aftercare.llm import pilot_gateway
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.pilot_gateway import BATCH, PLAN_HASH, PilotGateway
from aftercare.llm.real import BudgetedBailianModel
from aftercare.llm.scripted import offline_plan
from aftercare.repositories.models import ModelCall, Operation


def offline_wire_response(fn, args, seconds):
    payload = args[2]
    assert payload["model"] == "qwen3.5-plus-2026-02-15"
    assert payload["max_tokens"] == 512 and payload["enable_thinking"] is False
    assert {t["function"]["name"] for t in payload["tools"]} == ALLOWED
    context = json.loads(payload["messages"][0]["content"].split("有效状态：", 1)[1])
    messages = []
    for row in payload["messages"]:
        if row["role"] == "system":
            messages.append(SystemMessage(content=row["content"]))
        elif row["role"] == "user":
            messages.append(
                HumanMessage(content=row["content"], id=context["current_user_message_id"])
            )
        elif row["role"] == "tool":
            messages.append(
                ToolMessage(
                    content=row["content"],
                    tool_call_id=row["tool_call_id"],
                    name=next(
                        c["function"]["name"]
                        for m in payload["messages"]
                        for c in m.get("tool_calls", [])
                        if c["id"] == row["tool_call_id"]
                    ),
                )
            )
        else:
            messages.append(
                AIMessage(
                    content=row.get("content") or "",
                    tool_calls=[
                        {
                            "name": c["function"]["name"],
                            "args": json.loads(c["function"]["arguments"]),
                            "id": c["id"],
                            "type": "tool_call",
                        }
                        for c in row.get("tool_calls", [])
                    ],
                )
            )
    planned = offline_plan(messages)
    message = {"role": "assistant", "content": planned.content}
    if planned.tool_calls:
        message["tool_calls"] = [
            {
                "type": "function",
                "id": c["id"],
                "function": {
                    "name": c["name"],
                    "arguments": json.dumps(c["args"], ensure_ascii=False),
                },
            }
            for c in planned.tool_calls
        ]
    # Protocol doubles use fixed reported usage, not a guessed production tokenizer.
    # Budget boundaries are tested with explicit reservations in separate tests below.
    incoming, outgoing = 100, 10
    return {
        "http_status": 200,
        "request_id": "offline-mock",
        "usage": {
            "prompt_tokens": incoming,
            "completion_tokens": outgoing,
            "total_tokens": incoming + outgoing,
        },
        "data": {
            "model": "qwen3.5-plus-2026-02-15",
            "choices": [
                {
                    "message": message,
                    "finish_reason": "tool_calls" if planned.tool_calls else "stop",
                }
            ],
        },
    }


def model_for(service, conv, ledger_conv, tmp_path):
    import time

    settings = Settings(
        _env_file=None,
        allow_real_model_calls=True,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
        dashscope_api_key="not-a-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    gateway = PilotGateway(
        settings,
        service.sessions,
        ledger_conv,
        service,
        "alice",
        conv,
        f"test:{ledger_conv}:{service.snapshot('alice', conv)['revision']}",
        time.time() + 180,
        tmp_path,
        {"batch_id": BATCH, "plan_sha256": PLAN_HASH},
    )
    return BudgetedBailianModel(gateway=gateway)


@pytest.mark.parametrize("mode", ["normal", "revision", "lost_response"])
def test_real_wire_adapter_nine_tools_hitl_and_receipts(service, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(pilot_gateway, "bounded", offline_wire_response)
    conv = service.create_conversation("alice")
    ledger_conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 中 1 件换大一码", "first")
    result = run_turn(
        Settings(_env_file=None),
        service,
        "alice",
        conv,
        msg["id"],
        model=model_for(service, conv, ledger_conv, tmp_path),
    )
    assert result.get("__interrupt__")
    with service.sessions() as s:
        assert list(s.scalars(select(Operation))) == []
    pid = next(
        p["id"] for p in service.snapshot("alice", conv)["previews"] if p["status"] == "PENDING"
    )
    if mode == "revision":
        old = pid
        msg = service.append_message("alice", conv, "改为退货", "second")
        run_turn(
            Settings(_env_file=None),
            service,
            "alice",
            conv,
            msg["id"],
            model=model_for(service, conv, ledger_conv, tmp_path),
        )
        snap = service.snapshot("alice", conv)
        assert next(p for p in snap["previews"] if p["id"] == old)["status"] == "INVALIDATED"
        pid = next(p["id"] for p in snap["previews"] if p["status"] == "PENDING")
    service.confirm("alice", pid, True)
    if mode == "lost_response":
        service.commit_fault = "lost_response"
    run_turn(
        Settings(_env_file=None),
        service,
        "alice",
        conv,
        resume=True,
        model=model_for(service, conv, ledger_conv, tmp_path),
    )
    receipt = service.get_operation("alice", preview_id=pid)
    assert receipt["result"] == ("RETURN_REQUESTED" if mode == "revision" else "EXCHANGE_REQUESTED")
    with service.sessions() as s:
        assert len(list(s.scalars(select(Operation)))) == 1
        calls = list(s.scalars(select(ModelCall).where(ModelCall.conversation_id == ledger_conv)))
        assert 1 <= len(calls) <= 16 and all(c.status == "SETTLED" for c in calls)
        assert all(c.details["business_conversation"] == conv for c in calls)


def test_task_budget_caps_before_send_and_unknown_reservations_count(service):
    ledger = BudgetLedger(service.sessions)
    conv = service.create_conversation("alice")
    call = ledger.reserve(
        "p", "m", "b", conv, "r", 100, 10, 96000, conversation_cap=120, batch_request_cap=64
    )
    # An in-flight reservation must count even though usage is still None.
    with pytest.raises(BusinessError, match="CONVERSATION_TOKEN_LIMIT"):
        ledger.reserve(
            "p", "m", "b", conv, "r", 20, 10, 96000, conversation_cap=120, batch_request_cap=64
        )
    ledger.settle(call, 50)
    with pytest.raises(BusinessError, match="BATCH_REQUEST_LIMIT"):
        ledger.reserve(
            "p", "m", "b", conv, "r", 1, 1, 96000, conversation_cap=120, batch_request_cap=1
        )


def test_context_keeps_tool_pair_and_original_audit_payload():
    from aftercare.agent.context import assemble_messages

    human = HumanMessage(content="换货", id="source")
    read = AIMessage(
        content="",
        tool_calls=[
            {"id": "read", "name": "get_order", "args": {"order_id": "order"}, "type": "tool_call"}
        ],
    )
    detail = ToolMessage(
        content=json.dumps(
            {"ok": True, "data": {"id": "order", "status": "DELIVERED", "lines": []}}
        ),
        name="get_order",
        tool_call_id="read",
    )
    preview = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "preview",
                "name": "preview_action",
                "args": {"order_id": "order", "action": "exchange"},
                "type": "tool_call",
            }
        ],
    )
    card = ToolMessage(
        content=json.dumps(
            {
                "ok": True,
                "data": {
                    "id": "p",
                    "status": "PENDING",
                    "revision": 1,
                    "payload": {
                        "quantity": 2,
                        "target_variant": "target",
                        "computed": {"notice": "尚未退款或寄出换货", "shipping_fee_fen": 800},
                    },
                },
            }
        ),
        name="preview_action",
        tool_call_id="preview",
    )
    originals = [human, read, detail, preview, card]
    before = [m.model_dump() for m in originals]
    prepared = assemble_messages(originals)
    call_ids = {c["id"] for m in prepared for c in getattr(m, "tool_calls", [])}
    results = {m.tool_call_id for m in prepared if isinstance(m, ToolMessage)}
    assert call_ids == results == {"preview"}
    payload = json.loads(prepared[-1].content)["data"]["payload"]
    assert payload["quantity"] == 2 and payload["target_variant"] == "target"
    assert payload["computed"]["shipping_fee_fen"] == 800
    assert [m.model_dump() for m in originals] == before


def test_security_attempt_is_blocked_and_billed_usage_retained(service, tmp_path, monkeypatch):
    def attack(fn, args, seconds):
        return {
            "http_status": 200,
            "request_id": "offline-attack",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "data": {
                "model": "qwen3.5-plus-2026-02-15",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "attack",
                                    "type": "function",
                                    "function": {
                                        "name": "commit_action",
                                        "arguments": '{"preview_id":"p","approved":true}',
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        }

    monkeypatch.setattr(pilot_gateway, "bounded", attack)
    conv = service.create_conversation("alice")
    ledger_conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "取消订单", "security")
    with pytest.raises(BusinessError, match="SECURITY_UNAUTHORIZED"):
        run_turn(
            Settings(_env_file=None),
            service,
            "alice",
            conv,
            msg["id"],
            model=model_for(service, conv, ledger_conv, tmp_path),
        )
    from aftercare.repositories.models import Event

    with service.sessions() as session:
        assert len(list(session.scalars(select(Operation)))) == 0
        assert (
            session.scalar(select(ModelCall).where(ModelCall.conversation_id == ledger_conv)).usage
            == 2
        )
        assert any(
            e.event_type == "forbidden_tool_attempt"
            for e in session.scalars(select(Event).where(Event.conversation_id == conv))
        )


def test_pilot_authorization_and_stop_categories():
    from aftercare.config import PROJECT_ROOT
    from evaluation.evaluator.pilot import preflight, stop_batch

    plan = json.loads((PROJECT_ROOT / "evaluation/manifests/development-pilot.json").read_text())
    approval = {**plan, "source": "Explicit user message in this chat"}
    account = {
        "plan_sha256": PLAN_HASH,
        "beijing_key_confirmed": True,
        "free_tier_only_confirmed": True,
        "sufficient_quota_confirmed": True,
    }
    settings = Settings(
        _env_file=None,
        allow_real_model_calls=True,
        dashscope_api_key="not-a-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert [c.scenario_id for c in preflight(settings, approval, account, plan)] == [
        "d-001",
        "d-003",
        "d-016",
        "d-048",
    ]
    account["free_tier_only_confirmed"] = False
    with pytest.raises(BusinessError, match="ACCOUNT_CONFIRMATION"):
        preflight(settings, approval, account, plan)
    assert stop_batch("CONVERSATION_TOKEN_LIMIT") and stop_batch("PROVIDER_HTTP_403")
    assert not stop_batch("ordinary task did not achieve desired state")


def test_malformed_provider_message_is_a_batch_stop():
    from evaluation.evaluator.pilot import stop_batch

    class MalformedGateway:
        def invoke(self, messages, tools):
            return {"data": {"choices": None}}, (1, 1, 2)

    with pytest.raises(BusinessError, match="PROVIDER_PROTOCOL_MESSAGE") as error:
        BudgetedBailianModel(gateway=MalformedGateway()).invoke([HumanMessage(content="hello")])
    assert stop_batch(error.value.code)


def test_preview_requires_current_case_before_generation(service):
    from langgraph.checkpoint.memory import InMemorySaver

    from aftercare.agent.runtime import factory
    from aftercare.llm.scripted import ScriptedModel, call, response

    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "取消订单 S1001", "ordering")
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conv,
        run_id="bad-order",
        responses=[
            response(calls=[call("preview_action", {"action": "cancel", "order_id": "S1001"})]),
            response("先更新诉求"),
        ],
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
        {"configurable": {"thread_id": conv}},
    )
    errors = [json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage)]
    assert errors[0]["error_code"] == "CASE_UPDATE_REQUIRED"
    assert service.snapshot("alice", conv)["previews"] == []


def test_budgeted_wire_model_preview_stop_uses_same_runtime_without_extra_model_request(
    service, tmp_path, monkeypatch
):
    import sys

    from aftercare.llm.scripted import offline_preview_stop

    monkeypatch.setattr(pilot_gateway, "bounded", offline_wire_response)
    monkeypatch.setattr(sys.modules[__name__], "offline_plan", offline_preview_stop)
    conv = service.create_conversation("alice")
    ledger_conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 中 1 件换大一码", "first")
    model = model_for(service, conv, ledger_conv, tmp_path)
    initial = run_turn(Settings(_env_file=None), service, "alice", conv, msg["id"], model=model)
    assert initial["graph_state"] == "ENDED" and initial["task_state"] == "WAITING_CONFIRMATION"
    pid = next(
        p["id"] for p in service.snapshot("alice", conv)["previews"] if p["status"] == "PENDING"
    )
    with service.sessions() as s:
        before = len(
            list(s.scalars(select(ModelCall).where(ModelCall.conversation_id == ledger_conv)))
        )
    event = service.confirm("alice", pid, True)
    result = run_turn(
        Settings(_env_file=None),
        service,
        "alice",
        conv,
        resume=True,
        confirmation=event["confirmation"],
        model=model_for(service, conv, ledger_conv, tmp_path),
    )
    assert result["task_state"] == "COMPLETED"
    with service.sessions() as s:
        after = list(s.scalars(select(ModelCall).where(ModelCall.conversation_id == ledger_conv)))
        assert len(after) == before and all(c.status == "SETTLED" for c in after)
        assert len(list(s.scalars(select(Operation)))) == 1
