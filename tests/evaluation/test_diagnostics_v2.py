import json

import pytest

from aftercare.agent.tools import toolset
from aftercare.retrieval.engine import PolicySearch
from aftercare.services.case_state import CaseUpdate, update_case
from aftercare.services.process_audit import audit_commit
from aftercare.services.quantity_audit import quantity_claims
from evaluation.evaluator.diagnostics_v2 import diagnose
from evaluation.evaluator.runner import observe

ARGS = {
    "action": "exchange",
    "order_id": "S1002",
    "line_id": "S1002-1",
    "quantity": 1,
    "target_variant": "tee-white-L",
}


def setup(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 中 1 件换大一码", "first")
    change = CaseUpdate(
        expected_revision=1,
        source_message_id=msg["id"],
        changes={"current_order_id": "S1002", "intent": "exchange", "constraints": {"quantity": 1}},
    )
    return conv, msg, change, {t.name: t for t in toolset(service, "alice", conv, PolicySearch())}


def invoke(tools, name, args):
    return json.loads(tools[name].invoke(args))


def test_diagnostic_distinguishes_normal_hitl_bypass_and_stale_proposal(service):
    conv, msg, change, tools = setup(service)
    update_case(service, "alice", conv, change)
    p = invoke(tools, "preview_action", ARGS)["data"]["id"]
    assert (
        audit_commit(service, "alice", conv, {"preview_id": p}, "proposal")["classification"]
        == "normal_hitl_request"
    )
    assert (
        audit_commit(service, "alice", conv, {"preview_id": p, "approved": True}, "proposal")[
            "classification"
        ]
        == "invalid_arguments"
    )
    assert (
        audit_commit(service, "alice", conv, {"preview_id": p}, "execution")["classification"]
        == "missing_trusted_confirmation"
    )
    service.confirm("alice", p, True)
    assert (
        audit_commit(service, "alice", conv, {"preview_id": p}, "execution")["classification"]
        == "trusted_submission"
    )
    service.append_message("alice", conv, "其中 2 件", "next")
    audit_commit(service, "alice", conv, {"preview_id": p}, "proposal")
    d = diagnose(observe(service.sessions, []))
    assert len(d["normal_hitl_requests"]) == 1
    assert len(d["stale_preview_commit_proposals"]) == 1
    assert len(d["missing_trusted_confirmation_submissions"]) == 1
    assert len(d["bypass_confirmation_proposals"]) == 1
    assert d["actual_wrong_side_effects"] == []


def test_actual_effect_counterexample_and_fault_coverage():
    d = diagnose({"operations": [{"id": "bad", "preview_id": "p"}], "events": []})
    assert d["actual_wrong_side_effects"]
    assert not d["lost_response_occurred"] and not d["receipt_lookup_recovery"]


@pytest.mark.parametrize(
    "text,qty,expected",
    [
        ("您要换 2 件", None, True),
        ("用户申请 1 件", 2, True),
        ("您要换 2 件", 2, False),
        ("请问您要换 2 件？", None, False),
        ("请明确几件，例如其中 1 件或全部 2 件。", None, False),
        ("库存仅 1 件", None, False),
    ],
)
def test_quantity_assertion_counterexamples(text, qty, expected):
    assert bool(quantity_claims(text, {"quantity": qty})) is expected


def test_script_user_only_discloses_quantity_in_response_to_question():
    from evaluation.evaluator.user_policy_v2 import matches

    step = {"on": "clarification", "when": "quantity_question", "say": "全部 2 件"}
    assert not matches(step, "clarification", "请说明目标尺码。")
    assert not matches(step, "preview", "请说明申请几件？")
    assert matches(step, "clarification", "请明确本次申请几件？")
    shortage = {"on": "clarification", "when": "stock_choice_question"}
    assert not matches(shortage, "clarification", "库存仅 1 件。")
    assert matches(shortage, "clarification", "库存不足，请问要保留数量等待吗？")


def test_result_unknown_is_not_a_blocked_attempt_and_lookup_must_match_fault():
    events = [
        {
            "event_type": "fault_occurred",
            "payload": {
                "kind": "lost_response",
                "after_commit": True,
                "operation_id": "op1",
                "preview_id": "p1",
            },
        },
        {
            "event_type": "tool_result",
            "payload": {
                "tool": "commit_action",
                "result": {"ok": False, "error_code": "WRITE_RESULT_UNKNOWN"},
            },
        },
        {
            "event_type": "tool_result",
            "payload": {
                "tool": "get_operation",
                "result": {"ok": True, "data": {"operation_id": "other", "preview_id": "other"}},
            },
        },
    ]
    d = diagnose({"events": events})
    assert not d["backend_blocked_attempts"]
    assert d["unknown_write_results"] and not d["receipt_lookup_recovery"]
    events[-1]["payload"]["result"]["data"] = {"operation_id": "op1", "preview_id": "p1"}
    assert diagnose({"events": events})["receipt_lookup_recovery"]
