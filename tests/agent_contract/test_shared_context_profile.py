from sqlalchemy import select

from aftercare.agent.runtime import run_turn, setup_checkpoints
from aftercare.config import Settings
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel
from aftercare.repositories.models import Event, Operation


def test_opt_in_shared_policy_preserves_product_confirmation_and_provenance(service):
    url = service.sessions.kw["bind"].url.render_as_string(hide_password=False)
    settings = Settings(_env_file=None, database_url=url)
    setup_checkpoints(settings)
    conv = service.create_conversation("alice")
    message = service.append_message("alice", conv, "S1002 中 1 件换大一码", "first")
    result = run_turn(
        settings,
        service,
        "alice",
        conv,
        message["id"],
        profile="harness-evidence-v1",
        model=ScriptedModel(
            ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="shared-test"
        ),
    )
    snap = service.snapshot("alice", conv)
    assert result.get("__interrupt__")
    assert len(snap["previews"]) == 1
    with service.sessions() as session:
        assert session.scalar(select(Operation)) is None
    event = service.confirm("alice", snap["previews"][0]["id"], True)
    result = run_turn(
        settings,
        service,
        "alice",
        conv,
        resume=True,
        confirmation=event["confirmation"],
        profile="harness-evidence-v1",
        model=ScriptedModel(
            ledger=BudgetLedger(service.sessions), conversation_id=conv, run_id="shared-test"
        ),
    )
    assert result["receipt"]["preview_id"] == snap["previews"][0]["id"]
    with service.sessions() as s:
        assert s.scalar(select(Event).where(Event.event_type == "context_prepared"))
        profiles = list(s.scalars(select(Event).where(Event.event_type == "runtime_profile")))
        assert all(e.payload["retrieval_profile"] == "bm25" for e in profiles)
