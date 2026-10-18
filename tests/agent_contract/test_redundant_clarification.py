"""A premature natural-language stop is waiting, never an implicit business approval."""

from langchain_core.messages import ToolMessage
from sqlalchemy import select

from aftercare.agent.runtime import run_turn, setup_checkpoints
from aftercare.config import Settings
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel, call, response
from aftercare.repositories.models import Application, Event, Operation, Reservation
from evaluation.evaluator.diagnostics_v4 import diagnose


def test_redundant_fact_question_does_not_manufacture_preview_or_receipt(service):
    def replay(messages):
        reads = {m.name for m in messages if isinstance(m, ToolMessage)}
        if "get_order" not in reads:
            return response(calls=[call("get_order", {"order_id": "S1002"})])
        return response("您想将其中 1 件换大一码，对吗？请确认换货数量：1 件。")

    settings = Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )
    setup_checkpoints(settings)
    conv = service.create_conversation("alice")
    message = service.append_message("alice", conv, "S1002 中 1 件换大一码", "first")
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="replay", planner=replay
    )
    result = run_turn(settings, service, "alice", conv, message["id"], model=model)
    assert result["task_state"] == "WAITING_USER"
    assert result["graph_state"] == "ENDED"
    assert not result.get("receipt")
    assert not service.snapshot("alice", conv)["previews"]
    with service.sessions() as s:
        for table in (Operation, Application, Reservation):
            assert s.scalar(select(table)) is None
        events = [
            {"id": e.id, "event_type": e.event_type, "payload": e.payload}
            for e in s.scalars(
                select(Event).where(Event.conversation_id == conv).order_by(Event.id)
            )
        ]
    diagnosis = diagnose({"events": events})
    assert len(diagnosis["redundant_quantity_clarifications"]) == 1
    assert not diagnosis["actual_wrong_side_effects"]
