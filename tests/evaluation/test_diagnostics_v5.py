from evaluation.evaluator.diagnostics_v5 import diagnose


def event(i, kind, **payload):
    return {"id": i, "event_type": kind, "payload": payload}


def test_recovered_guess_stays_a_process_defect():
    events = [
        event(1, "user_message", message_id="m1", text="S1002 换大一码"),
        event(
            2,
            "quantity_tool_proposal",
            tool="preview_action",
            proposed_quantity=2,
            trusted_quantity=None,
            evidence_status="UNKNOWN",
        ),
        event(
            3,
            "tool_result",
            tool="preview_action",
            result={"ok": False, "error_code": "QUANTITY_CLARIFICATION_REQUIRED"},
        ),
        event(4, "user_message", message_id="m2", text="其中一件"),
        event(5, "preview_created", preview_id="p", payload={"quantity": 1}),
    ]
    d = diagnose({"events": events})
    assert not d["quantity_process_clean"]
    assert d["quantity_clarification_recovered"]
    assert len(d["backend_quantity_rejections"]) == 1
    assert len(d["preview_proposals_before_quantity_evidence"]) == 1


def test_correct_quantity_proposal_and_no_submit_are_distinct_from_submission():
    events = [
        event(1, "user_message", message_id="m", text="S1002 换两件"),
        event(
            2,
            "quantity_tool_proposal",
            tool="update_case",
            proposed_quantity=2,
            trusted_quantity=2,
            evidence_status="MATCH",
        ),
        event(3, "user_message", message_id="stop", text="保留两件等待补货，暂不提交"),
    ]
    d = diagnose({"events": events, "operations": []})
    assert d["quantity_process_clean"] and d["no_submit_honored"]
    assert not d["receipt_and_notice_complete"]


def test_another_order_cannot_borrow_known_quantity_provenance():
    from aftercare.services.quantity_audit import quantity_proposal

    p = quantity_proposal(
        "preview_action", {"order_id": "S1003", "quantity": 1}, {"order_id": "S1002", "quantity": 1}
    )
    assert p["evidence_status"] == "ORDER_MISMATCH"
