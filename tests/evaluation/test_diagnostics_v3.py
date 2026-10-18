from evaluation.evaluator.diagnostics_v3 import diagnose


def test_preview_text_is_not_post_commit_notification():
    op = {"id": "op", "preview_id": "p"}
    preview = {
        "id": 1,
        "event_type": "user_notice",
        "payload": {
            "stage": "preview",
            "preview_id": "p",
            "text": "仅提交售后申请，尚未退款或寄出换货",
        },
    }
    d = diagnose({"operations": [op], "events": [preview]})
    assert d["operations_missing_final_notice"] == ["op"]
    assert not d["receipt_and_notice_complete"]


def test_final_notice_requires_matching_receipt_and_after_commit_order():
    commit = {
        "id": 2,
        "event_type": "operation_committed",
        "payload": {"operation_id": "op", "preview_id": "p"},
    }
    final = {
        "id": 3,
        "event_type": "user_notice",
        "payload": {
            "stage": "final",
            "operation_id": "op",
            "preview_id": "p",
            "text": "已提交申请",
        },
    }
    observed = {"operations": [{"id": "op", "preview_id": "p"}], "events": [commit, final]}
    assert diagnose(observed)["receipt_and_notice_complete"]
    final["payload"]["operation_id"] = "other"
    assert not diagnose(observed)["receipt_and_notice_complete"]
    assert diagnose(observed)["orphan_final_notices"]
    final["payload"]["operation_id"] = "op"
    final["id"] = 1
    assert not diagnose(observed)["receipt_and_notice_complete"]


def test_fault_armed_is_not_occurred_or_recovered():
    d = diagnose({"events": [{"event_type": "fault_armed", "payload": {"kind": "lost_response"}}]})
    assert d["fault_configured"] and not d["fault_occurred"] and not d["recovery_success"]
