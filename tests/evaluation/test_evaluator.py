import json

import pytest

from evaluation.evaluator.grader import grade, verify_mutations
from evaluation.evaluator.plan import compatibility_plan
from evaluation.evaluator.runner import load_dev, validate


def test_assets_and_mutations():
    result = validate()
    assert result["count"] == 60
    assert set(result["categories"].values()) == {15}
    assert verify_mutations()["passed"]
    scenario = load_dev()[0]
    scenario.expected_state_invariants["unknown_success_flag"] = True
    with pytest.raises(ValueError, match="Unsupported oracle"):
        grade(scenario, {})


def test_dry_run_never_calls_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run attempted inference")

    monkeypatch.setattr("aftercare.llm.provider.BailianAdapter.invoke", forbidden)
    plan = compatibility_plan()
    assert plan["real_api_calls"] == 0
    assert plan["planned_requests"] + plan["retry_slots"] == 8
    assert plan["conservative_reservation"] <= plan["total_token_hard_cap"] == 20000
    assert all(r["request"]["model"] == plan["exact_model"] for r in plan["requests"])
    assert "DRY-RUN" not in json.dumps(plan)


def test_actor_protocol_excludes_answers():
    # Actor only knows business session, message ID and resume. No scenario import/read exists.
    import inspect

    from evaluation.evaluator import actor

    source = inspect.getsource(actor)
    assert "hidden_user_goal" not in source
    assert "expected_state_invariants" not in source
    assert "holdout" not in source


@pytest.mark.parametrize("profile", ["fixed-workflow", "react-full-policy", "retrieval"])
def test_profiles_keep_confirmation_boundary(service, profile):
    from aftercare.agent.runtime import run_turn, setup_checkpoints
    from aftercare.config import Settings

    settings = Settings(
        _env_file=None,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
    )
    setup_checkpoints(settings)
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 中 1 件换大一码", "profile-first")
    result = run_turn(settings, service, "alice", conv, msg["id"], profile=profile)
    assert result.get("__interrupt__")
    snapshot = service.snapshot("alice", conv)
    preview = next(p for p in snapshot["previews"] if p["status"] == "PENDING")
    # Even an approved graph decision cannot create a trusted API approval.
    from aftercare.domain.contracts import BusinessError

    with pytest.raises(BusinessError, match="CONFIRMATION_EVENT_REQUIRED"):
        run_turn(settings, service, "alice", conv, resume=True, profile=profile)
    from sqlalchemy import func, select

    from aftercare.repositories.models import Operation

    with service.sessions() as s:
        assert s.scalar(select(func.count()).select_from(Operation)) == 0
    service.confirm("alice", preview["id"], True)
    # A fresh ordinary turn must invalidate the confirmed preview in every profile.
    service.append_message("alice", conv, "改为退货", "profile-second")
    assert service.snapshot("alice", conv)["previews"][0]["status"] == "INVALIDATED"


def test_metrics_distinguish_blocked_attempt_from_actual_side_effect():
    from evaluation.evaluator.metrics import metrics

    case = load_dev()[0]
    row = {
        "result": {"success": False, "process_failures": ["unauthorized_commit_attempt"]},
        "observed": {"operations": [], "previews": [], "handoffs": [], "events": []},
        "latency_seconds": 0.5,
    }
    result = metrics([row], [case])
    assert result["unauthorized_attempt_tasks"] == {"n": 1, "N": 1}
    assert result["wrong_actual_side_effect_tasks"] == {"n": 0, "N": 1}
    assert result["real_model_tokens_and_cost"] is None
