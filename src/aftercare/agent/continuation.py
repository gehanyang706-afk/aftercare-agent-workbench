"""An exact trusted event, never an arbitrary CONFIRMED row, selects the continuation."""

import json

from aftercare.agent.presentation import state_event
from aftercare.agent.tools import toolset
from aftercare.domain.rules import require
from aftercare.retrieval.engine import PolicySearch
from aftercare.services.confirmation import latest_event, validate


def pending_calls(state):
    return [
        action
        for task in state.tasks
        for interrupt in task.interrupts
        for action in interrupt.value.get("action_requests", [])
    ]


def continue_confirmation(
    graph, state, config, service, principal, conversation, binding, decision
):
    actions = pending_calls(state)
    if binding is None:
        require(
            len(actions) == 1 and actions[0]["name"] == "commit_action",
            "CONFIRMATION_EVENT_REQUIRED",
        )
        binding = latest_event(
            service, principal, conversation, actions[0]["args"].get("preview_id")
        )
    preview = validate(service, principal, conversation, binding)
    pid = binding["preview_id"]
    require(binding["decision"] == decision, "CONFIRMATION_DECISION_MISMATCH")
    tools = {t.name: t for t in toolset(service, principal, conversation, PolicySearch())}

    def invoke(name):
        return json.loads(tools[name].invoke({"preview_id": pid}))

    if decision == "reject":
        if actions:
            require(
                len(actions) == 1
                and actions[0]["name"] == "commit_action"
                and actions[0]["args"] == {"preview_id": pid},
                "CONFIRMATION_INTERRUPT_MISMATCH",
            )
            from langgraph.types import Command

            result = graph.invoke(Command(resume={"decisions": [{"type": "reject"}]}), config)
        else:
            result = {"messages": state.values.get("messages", [])}
        return {**result, "_rejected": True}, None, None, False, pid
    from sqlalchemy import select

    from aftercare.repositories.models import Event

    with service.sessions() as session:
        previous = session.scalar(
            select(Event)
            .where(Event.conversation_id == conversation, Event.event_type == "runtime_state")
            .order_by(Event.id.desc())
        )
        was_unknown = bool(
            previous
            and previous.payload.get("preview_id") == pid
            and previous.payload.get("task_state") == "EXECUTION_UNKNOWN"
        )
    if was_unknown:
        receipt = invoke("get_operation")
        if receipt["ok"]:
            return state.values, receipt["data"], None, True, pid
        return state.values, None, {"error_code": "WRITE_RESULT_UNKNOWN"}, False, pid
    state_event(
        service,
        principal,
        conversation,
        "INTERRUPTED" if actions else "ENDED",
        "WAITING_SUBMISSION",
        confirmation_event_id=binding["event_id"],
        preview_id=pid,
    )
    if preview["status"] == "COMMITTED":
        outcome = invoke("get_operation")
        require(outcome["ok"], "RECEIPT_NOT_FOUND")
        return (
            {**state.values, "_graph_state": "INTERRUPTED" if state.next else "ENDED"},
            outcome["data"],
            None,
            False,
            pid,
        )
    if state.next:
        require(
            len(actions) == 1
            and actions[0]["name"] == "commit_action"
            and actions[0]["args"] == {"preview_id": pid},
            "CONFIRMATION_INTERRUPT_MISMATCH",
        )
        from langgraph.types import Command

        result = graph.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
        # The graph may have caught the unknown write result. Resolve only this event's receipt.
        receipt = invoke("get_operation")
        if receipt["ok"]:
            from sqlalchemy import select

            from aftercare.repositories.models import Event

            with service.sessions() as s:
                recovered = any(
                    e.payload.get("kind") == "lost_response" and e.payload.get("preview_id") == pid
                    for e in s.scalars(
                        select(Event).where(
                            Event.conversation_id == conversation,
                            Event.event_type == "fault_occurred",
                        )
                    )
                )
            return result, receipt["data"], None, recovered, pid
        results = [
            json.loads(m.content)
            for m in result.get("messages", [])
            if m.type == "tool"
            and getattr(m, "name", None) == "commit_action"
            and str(m.content).startswith("{")
        ]
        outcome = (
            results[-1] if results else {"ok": False, "error_code": "SUBMISSION_NOT_COMPLETED"}
        )
    else:
        # Application continuation after a graph END. No fake user message or Command(resume).
        result = {"messages": state.values.get("messages", [])}
        outcome = invoke("commit_action")
    if outcome["ok"]:
        return result, outcome["data"], None, False, pid
    if outcome["error_code"] == "WRITE_RESULT_UNKNOWN":
        state_event(service, principal, conversation, "ENDED", "EXECUTION_UNKNOWN", preview_id=pid)
        receipt = invoke("get_operation")
        if receipt["ok"]:
            return result, receipt["data"], None, True, pid
    else:
        from aftercare.repositories.models import Preview

        with service.sessions.begin() as s:
            conv = service._conversation(s, principal, conversation)
            row = s.get(Preview, pid)
            if conv.revision == binding["intent_revision"] and row.status in {
                "PENDING",
                "CONFIRMED",
            }:
                row.status = "INVALIDATED"
                conv.status = "FAILED"
    return result, None, outcome, False, pid
