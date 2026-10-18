import json

import pytest
from langchain_core.messages import ToolMessage
from sqlalchemy import func, select

from aftercare.agent.runtime import run_turn, setup_checkpoints
from aftercare.agent.tools import toolset
from aftercare.config import Settings
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel, call, offline_plan, response
from aftercare.repositories.models import Application, Approval, Event, Operation, Preview
from aftercare.retrieval.engine import PolicySearch
from aftercare.services.business import columns
from evaluation.evaluator.diagnostics_v5 import diagnose


def tools_case(service, text, action, quantity):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, text, "first")
    tools = {t.name: t for t in toolset(service, "alice", conv, PolicySearch())}
    result = json.loads(
        tools["update_case"].invoke(
            {
                "expected_revision": 1,
                "source_message_id": msg["id"],
                "changes": {
                    "current_order_id": "S1002",
                    "current_line_id": "S1002-1",
                    "intent": action,
                    "constraints": {"quantity": quantity},
                },
            }
        )
    )
    assert result["ok"]
    return conv, tools


def test_chinese_partial_return_reaches_real_transaction(service):
    conv, tools = tools_case(service, "S1002 只退其中一件，另一件保留", "return", 1)
    preview = json.loads(
        tools["preview_action"].invoke(
            {"action": "return", "order_id": "S1002", "line_id": "S1002-1", "quantity": 1}
        )
    )
    assert preview["ok"]
    service.confirm("alice", preview["data"]["id"], True)
    service.commit("alice", preview["data"]["id"])
    with service.sessions() as s:
        assert s.scalar(select(Application)).quantity == 1
        assert s.scalar(select(func.count()).select_from(Operation)) == 1


@pytest.mark.parametrize("quantity", [1, 2])
def test_purchase_count_never_authorizes_request_preview(service, quantity):
    conv, tools = tools_case(service, "S1002 买了两件，想换大一码", "exchange", quantity)
    preview = json.loads(
        tools["preview_action"].invoke(
            {
                "action": "exchange",
                "order_id": "S1002",
                "line_id": "S1002-1",
                "quantity": quantity,
                "target_variant": "tee-white-L",
            }
        )
    )
    assert preview["error_code"] == "QUANTITY_CLARIFICATION_REQUIRED"
    assert not service.snapshot("alice", conv)["previews"]


@pytest.mark.parametrize("preview_stop", [False, True])
def test_final_notice_is_bound_to_receipt_even_if_model_final_text_is_wrong(service, preview_stop):
    def planner(messages):
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if any(m.name == "commit_action" and json.loads(m.content).get("ok") for m in results):
            return response("已寄出两件且退款到账。")
        if preview_stop and any(
            m.name == "preview_action" and json.loads(m.content).get("ok") for m in results
        ):
            return response("请确认是否提交。")
        return offline_plan(messages)

    settings = Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )
    setup_checkpoints(settings)
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 其中一件换大一码", "first")
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conv,
        run_id="notice",
        planner=planner,
    )
    initial = run_turn(settings, service, "alice", conv, msg["id"], model=model)
    assert bool(initial.get("__interrupt__")) != preview_stop
    pid = service.snapshot("alice", conv)["previews"][0]["id"]
    binding = service.confirm("alice", pid, True)["confirmation"]
    calls = model.shared["calls"]
    result = run_turn(
        settings, service, "alice", conv, resume=True, confirmation=binding, model=model
    )
    assert result["task_state"] == "COMPLETED"
    assert result["receipt"]["preview_id"] == pid
    assert "数量 1 件" in result["communications"][0]
    assert "已寄出两件" not in result["communications"][0]
    assert "退款到账" not in result["communications"][0]
    assert model.shared["calls"] == calls + (0 if preview_stop else 1)


def test_unproven_proposals_are_audited_even_after_clarification_recovery(service):
    # No scenario IDs or hidden evaluator goals enter this product runtime.
    queue = []
    settings = Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )
    setup_checkpoints(settings)
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 换大一码", "first")
    queue.extend(
        [
            response(
                calls=[
                    call(
                        "update_case",
                        {
                            "expected_revision": 1,
                            "source_message_id": msg["id"],
                            "changes": {
                                "current_order_id": "S1002",
                                "current_line_id": "S1002-1",
                                "intent": "exchange",
                                "constraints": {"quantity": 2, "size_delta": 1},
                            },
                        },
                    )
                ]
            ),
            response(
                calls=[
                    call(
                        "preview_action",
                        {
                            "action": "exchange",
                            "order_id": "S1002",
                            "line_id": "S1002-1",
                            "quantity": 2,
                            "target_variant": "tee-white-L",
                        },
                    )
                ]
            ),
            response("请问本次申请几件？"),
        ]
    )
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conv,
        run_id="audit",
        planner=lambda messages: queue.pop(0) if queue else offline_plan(messages),
    )
    run_turn(settings, service, "alice", conv, msg["id"], model=model)
    msg = service.append_message("alice", conv, "其中一件", "answer")
    run_turn(settings, service, "alice", conv, msg["id"], model=model)
    pid = service.snapshot("alice", conv)["previews"][0]["id"]
    binding = service.confirm("alice", pid, True)["confirmation"]
    run_turn(settings, service, "alice", conv, resume=True, confirmation=binding, model=model)
    with service.sessions() as s:
        events = [
            {"id": e.id, "event_type": e.event_type, "payload": e.payload}
            for e in s.scalars(
                select(Event).where(Event.conversation_id == conv).order_by(Event.id)
            )
        ]
        observed = {
            "events": events,
            "operations": [columns(r) for r in s.scalars(select(Operation))],
            "previews": [columns(r) for r in s.scalars(select(Preview))],
            "approvals": [columns(r) for r in s.scalars(select(Approval))],
        }
    d = diagnose(observed)
    assert d["receipt_and_notice_complete"]
    assert len(d["unsupported_quantity_proposals"]) == 2
    assert len(d["preview_proposals_before_quantity_evidence"]) == 1
    assert len(d["backend_quantity_rejections"]) == 1
    assert d["quantity_clarification_recovered"]
    assert not d["quantity_process_clean"]  # a correct end state does not erase guessing
