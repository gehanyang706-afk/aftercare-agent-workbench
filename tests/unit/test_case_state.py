import pytest

from aftercare.domain.contracts import BusinessError
from aftercare.services.case_state import CaseUpdate, assemble_context, update_case


def test_changes_supersede_constraints_without_destroying_history(service):
    conv = service.create_conversation("alice")
    first = service.append_message("alice", conv, "白色换大一码", "one")
    update_case(
        service,
        "alice",
        conv,
        CaseUpdate(
            expected_revision=1,
            source_message_id=first["id"],
            changes={
                "current_order_id": "S1002",
                "intent": "exchange",
                "constraints": {"size": "L"},
            },
        ),
    )
    second = service.append_message("alice", conv, "改成黑色原码", "two")
    case = update_case(
        service,
        "alice",
        conv,
        CaseUpdate(
            expected_revision=2,
            source_message_id=second["id"],
            changes={"constraints": {"size": "M", "color": "黑色"}},
        ),
    )
    assert case["facts"]["constraints"]["value"] == {"size": "M", "color": "黑色"}
    assert any(x["value"] == {"size": "L"} for x in case["superseded"])
    snapshot = service.snapshot("alice", conv)
    context = assemble_context(snapshot, [])
    assert len(snapshot["messages"]) == 2 and context["intent_revision"] == 2
    with pytest.raises(BusinessError, match="INTENT_CHANGED"):
        update_case(
            service, "alice", conv, CaseUpdate(expected_revision=1, source_message_id=first["id"])
        )
    with pytest.raises(BusinessError, match="CASE_FIELD_FORBIDDEN"):
        update_case(
            service,
            "alice",
            conv,
            CaseUpdate(
                expected_revision=2, source_message_id=second["id"], changes={"approved": True}
            ),
        )


def test_new_order_clears_old_line_and_provenance(service):
    conv = service.create_conversation("alice")
    first = service.append_message("alice", conv, "退S1002", "a")
    update_case(
        service,
        "alice",
        conv,
        CaseUpdate(
            expected_revision=1,
            source_message_id=first["id"],
            changes={"current_order_id": "S1002", "current_line_id": "S1002-1", "intent": "return"},
        ),
    )
    second = service.append_message("alice", conv, "不是这单，是S1003", "b")
    state = update_case(
        service,
        "alice",
        conv,
        CaseUpdate(
            expected_revision=2,
            source_message_id=second["id"],
            changes={"current_order_id": "S1003"},
        ),
    )
    assert "current_line_id" not in state["facts"]
    assert state["facts"]["current_order_id"]["source_message_id"] == second["id"]
