"""Behavior regressions: service transactions, not prompt ordering, own preview safety."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from aftercare.agent.tools import toolset
from aftercare.retrieval.engine import PolicySearch
from aftercare.services.case_state import CaseUpdate, update_case


def setup(service, text="S1002 中 1 件换大一码"):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, text, "first")
    change = CaseUpdate(
        expected_revision=1,
        source_message_id=msg["id"],
        changes={
            "current_order_id": "S1002",
            "intent": "exchange",
            "constraints": {"quantity": 1, "size_delta": 1},
        },
    )
    tools = {t.name: t for t in toolset(service, "alice", conv, PolicySearch())}
    return conv, msg, change, tools


ARGS = {
    "action": "exchange",
    "order_id": "S1002",
    "line_id": "S1002-1",
    "quantity": 1,
    "target_variant": "tee-white-L",
}


def invoke(tools, name, args):
    return json.loads(tools[name].invoke(args))


def test_dependency_is_enforced_by_tool_handler_not_only_middleware(service):
    conv, msg, change, tools = setup(service)
    result = invoke(tools, "preview_action", ARGS)
    assert result["error_code"] == "CASE_UPDATE_REQUIRED"
    assert service.snapshot("alice", conv)["previews"] == []
    update_case(service, "alice", conv, change)
    assert invoke(tools, "preview_action", ARGS)["ok"]  # recover in same turn


def test_same_state_update_preserves_preview_and_confirmation(service):
    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    preview = invoke(tools, "preview_action", ARGS)["data"]
    service.confirm("alice", preview["id"], True)
    first = service.snapshot("alice", conv)["case"]
    update_case(service, "alice", conv, change)
    snap = service.snapshot("alice", conv)
    assert snap["case"] == first
    assert snap["previews"][0]["status"] == "CONFIRMED"
    assert service.commit("alice", preview["id"])["status"] == "COMMITTED"


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"current_order_id": "S1001", "intent": "cancel"},
        {"current_order_id": "S1002", "intent": "return"},
        {"current_order_id": "S1002", "intent": "exchange", "constraints": {"quantity": 2}},
    ],
)
def test_current_marker_does_not_authorize_missing_or_conflicting_facts(service, changes):
    conv, msg, change, tools = setup(service)
    change.changes = changes
    update_case(service, "alice", conv, change)
    result = invoke(tools, "preview_action", ARGS)
    assert not result["ok"]
    assert service.snapshot("alice", conv)["previews"] == []


@pytest.mark.parametrize("quantity", [1, 2])
def test_quantity_requires_user_evidence_not_purchased_quantity_or_stock(service, quantity):
    conv, msg, change, tools = setup(service, "S1002 换大一码")
    change.changes["constraints"]["quantity"] = quantity
    update_case(service, "alice", conv, change)
    result = invoke(tools, "preview_action", {**ARGS, "quantity": quantity})
    assert result["error_code"] == "QUANTITY_CLARIFICATION_REQUIRED"
    assert not service.snapshot("alice", conv)["previews"]


def test_parallel_update_preview_is_serializable_and_duplicate_safe(service):
    conv, msg, change, tools = setup(service)

    def update():
        return update_case(service, "alice", conv, change)

    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(update)
        b = pool.submit(invoke, tools, "preview_action", ARGS)
        a.result()
        result = b.result()
    if not result["ok"]:
        assert result["error_code"] == "CASE_UPDATE_REQUIRED"
        result = invoke(tools, "preview_action", ARGS)
    update()
    assert result["ok"]
    assert service.snapshot("alice", conv)["previews"][0]["status"] == "PENDING"


@pytest.mark.parametrize("new_text", ["其中 2 件", "改为退其中 1 件", "取消订单 S1001", "好的"])
def test_new_message_invalidates_old_confirm_even_without_intent_change(service, new_text):
    from aftercare.domain.contracts import BusinessError

    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    preview = invoke(tools, "preview_action", ARGS)["data"]
    service.confirm("alice", preview["id"], True)
    service.append_message("alice", conv, new_text, "second")
    assert not service.snapshot("alice", conv)["previews"][0]["confirmation_available"]
    with pytest.raises(BusinessError):
        service.confirm("alice", preview["id"], True)
    with pytest.raises(BusinessError):
        service.commit("alice", preview["id"])


@pytest.mark.parametrize(
    "changes",
    [
        {"constraints": {"quantity": 2}},
        {"intent": "return"},
        {"current_order_id": "S1001"},
        {"current_line_id": "S1002-other"},
    ],
)
def test_changed_effective_state_invalidates_in_same_user_revision(service, changes):
    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    invoke(tools, "preview_action", ARGS)
    update_case(service, "alice", conv, change.model_copy(update={"changes": changes}))
    assert service.snapshot("alice", conv)["previews"][0]["status"] == "INVALIDATED"


def test_actual_graph_parallel_batch_and_wrong_order_recover(service):
    from langchain_core.messages import HumanMessage, ToolMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from aftercare.agent.runtime import factory
    from aftercare.llm.budget import BudgetLedger
    from aftercare.llm.scripted import ScriptedModel, call, response

    conv, msg, change, tools = setup(service)
    replies = [
        response(calls=[call("preview_action", ARGS)]),
        response(calls=[call("update_case", change.model_dump()), call("preview_action", ARGS)]),
        response(calls=[call("preview_action", ARGS)]),
    ]

    def plan(messages):
        if replies:
            return replies.pop(0)
        return response(
            calls=[
                call(
                    "commit_action",
                    {
                        "preview_id": next(
                            p["id"]
                            for p in service.snapshot("alice", conv)["previews"]
                            if p["confirmation_available"]
                        )
                    },
                )
            ]
        )

    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="parallel", planner=plan
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
        {"configurable": {"thread_id": conv}},
    )
    assert result.get("__interrupt__")
    errors = [
        json.loads(m.content).get("error_code")
        for m in result["messages"]
        if isinstance(m, ToolMessage)
    ]
    assert "CASE_UPDATE_REQUIRED" in errors
    assert (
        len([p for p in service.snapshot("alice", conv)["previews"] if p["confirmation_available"]])
        == 1
    )


def test_stale_commit_proposal_does_not_reach_hitl_and_agent_repreviews(service):
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from aftercare.agent.runtime import factory
    from aftercare.llm.budget import BudgetLedger
    from aftercare.llm.scripted import ScriptedModel, call, response

    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    old = invoke(tools, "preview_action", ARGS)["data"]["id"]
    update_case(
        service,
        "alice",
        conv,
        change.model_copy(update={"changes": {"constraints": {"quantity": 2}}}),
    )
    replies = [
        response(calls=[call("commit_action", {"preview_id": old})]),
        response(calls=[call("update_case", change.model_dump())]),
        response(calls=[call("preview_action", ARGS)]),
    ]

    def plan(messages):
        if replies:
            return replies.pop(0)
        pid = next(
            p["id"]
            for p in service.snapshot("alice", conv)["previews"]
            if p["confirmation_available"]
        )
        return response(calls=[call("commit_action", {"preview_id": pid})])

    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="stale", planner=plan
    )
    graph, _ = factory(service, "alice", conv, InMemorySaver(), model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content=msg["text"], id=msg["id"])]},
        {"configurable": {"thread_id": conv}},
    )
    assert result.get("__interrupt__")
    # Pending HITL names only the new valid preview.
    pending = str(result["__interrupt__"])
    assert old not in pending


@pytest.mark.parametrize(
    "text",
    [
        "S1002 买了 2 件，想换大一码",
        "S1002 购买数量 2，想换大一码",
        "S1002 库存只有 1 件，我想换大一码",
    ],
)
def test_purchase_and_stock_mentions_are_not_requested_quantity(service, text):
    conv, msg, change, tools = setup(service, text)
    update_case(service, "alice", conv, change)
    assert invoke(tools, "preview_action", ARGS)["error_code"] == "QUANTITY_CLARIFICATION_REQUIRED"


def test_user_withdrawal_cannot_be_overwritten_by_model_facts(service):
    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    msg2 = service.append_message("alice", conv, "不换了，暂时不要办理", "next")
    change.expected_revision = 2
    change.source_message_id = msg2["id"]
    update_case(service, "alice", conv, change)
    assert (
        invoke(tools, "preview_action", ARGS)["error_code"] == "USER_INTENT_CLARIFICATION_REQUIRED"
    )


def test_new_message_cannot_race_between_preview_gate_and_creation(service, monkeypatch):
    from threading import Event

    from aftercare.services import intent_guard

    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    entered, release = Event(), Event()
    original = intent_guard.validate_case_for_preview

    def gate(session, conversation, action):
        original(session, conversation, action)
        entered.set()
        assert release.wait(3)

    monkeypatch.setattr(intent_guard, "validate_case_for_preview", gate)
    with ThreadPoolExecutor(2) as pool:
        preview = pool.submit(invoke, tools, "preview_action", ARGS)
        assert entered.wait(3)
        new_message = pool.submit(service.append_message, "alice", conv, "改为退其中 1 件", "next")
        # Preview still owns the row lock. The message can only invalidate AFTER creation.
        assert not new_message.done()
        release.set()
        assert preview.result()["ok"]
        new_message.result()
    assert not any(p["confirmation_available"] for p in service.snapshot("alice", conv)["previews"])


@pytest.mark.parametrize("preview_first", [True, False])
def test_state_change_and_preview_in_same_batch_never_leave_valid_stale_card(
    service, preview_first
):
    from threading import Event

    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    change.changes = {"constraints": {"quantity": 1, "size_delta": 1, "unused": False}}
    first_done = Event()

    def first():
        try:
            return (
                invoke(tools, "preview_action", ARGS)
                if preview_first
                else update_case(service, "alice", conv, change)
            )
        finally:
            first_done.set()

    def second():
        assert first_done.wait(3)
        return (
            update_case(service, "alice", conv, change)
            if preview_first
            else invoke(tools, "preview_action", ARGS)
        )

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(first), pool.submit(second)
        a.result()
        b.result()
    assert not any(p["confirmation_available"] for p in service.snapshot("alice", conv)["previews"])


@pytest.mark.parametrize(
    "latest,action",
    [
        ("不是退货，是换货", "return"),
        ("换货或者退货都可以吗", "return"),
        ("查询一下订单状态", "exchange"),
        ("好的", "exchange"),
    ],
)
def test_negation_ambiguous_options_and_ack_are_not_new_action_authority(service, latest, action):
    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    msg2 = service.append_message("alice", conv, latest, "next")
    change.expected_revision = 2
    change.source_message_id = msg2["id"]
    change.changes["intent"] = action
    update_case(service, "alice", conv, change)
    args = {**ARGS, "action": action}
    if action == "return":
        args["target_variant"] = None
    assert (
        invoke(tools, "preview_action", args)["error_code"] == "USER_INTENT_CLARIFICATION_REQUIRED"
    )
