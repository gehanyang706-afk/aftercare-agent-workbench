"""A model's message anchor is not proof that the user supplied its field value."""

from aftercare.services.case_state import CaseUpdate, update_case


def test_model_quantity_proposal_cannot_become_trusted_context(service):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 的T恤想换大一码", "first")
    case = update_case(
        service,
        "alice",
        conv,
        CaseUpdate(
            expected_revision=1,
            source_message_id=msg["id"],
            changes={
                "current_order_id": "S1002",
                "intent": "exchange",
                "constraints": {"quantity": 2},
            },
        ),
    )
    assert case["facts"]["constraints"]["provenance"] == "model_proposal"
    from aftercare.agent.context import case_model_context

    context = case_model_context(service.snapshot("alice", conv))
    assert context["facts"]["constraints"]["value"]["quantity"] == 2
    assert context["facts"]["constraints"]["provenance"] == "model_proposal"
    assert context["user_quantity_evidence"] == {"quantity": None, "source_message_id": None}
    reply = service.append_message("alice", conv, "其中一件", "reply")
    context = case_model_context(service.snapshot("alice", conv))
    assert context["user_quantity_evidence"] == {
        "quantity": 1,
        "source_message_id": reply["id"],
    }
    service.append_message("alice", conv, "改为S1003", "other")
    assert case_model_context(service.snapshot("alice", conv))["user_quantity_evidence"] == {
        "quantity": None,
        "source_message_id": None,
    }
