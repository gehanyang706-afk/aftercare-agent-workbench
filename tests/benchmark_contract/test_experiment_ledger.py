from concurrent.futures import ThreadPoolExecutor

import pytest

from aftercare.domain.contracts import BusinessError
from aftercare.llm.experiment_gateway import ExperimentLedger
from aftercare.llm.experiment_scope import model_identity
from aftercare.repositories.models import ActorBudget, Budget, ModelCall, SharedModelQuota

MODEL = "qwen3.5-plus-2026-02-15"


def setup(service, run="bench", cap=1000, quota=1000):
    ledger = ExperimentLedger(service.sessions)
    role = dict(
        enabled=True,
        provider="qwen",
        region="beijing",
        exact_model=MODEL,
        batch_token_cap=cap,
        batch_request_cap=20,
        episode_token_cap=cap,
        request_cap=10,
        output_cap=10,
    )
    plan = dict(
        plan_sha256="frozen",
        total_token_cap=cap,
        request_cap=20,
        wall_clock_seconds=100,
        episode_seconds=50,
        episode_token_cap=cap,
        episode_request_cap=20,
        roles={"agent": role, "user": role, "judge": {"enabled": False}},
    )
    ledger.create_run(
        run, plan, {"models": {model_identity("qwen", "beijing", MODEL): {"remaining": quota}}}
    )
    ledger.create_episode(
        run, run + "-1", dict(task_id="synthetic", variant="official_tc", trial=0)
    )
    return ledger


def test_settle_includes_roles_without_double_counting(service):
    ledger = setup(service)
    for i, role in enumerate(("agent", "user")):
        call = ledger.reserve("bench", "bench-1", role, str(i), 30, 10)
        ledger.settle(call, 25, {"input_tokens": 20, "output_tokens": 5})
    with service.sessions() as s:
        assert s.get(Budget, "project").settled == 50
        assert s.get(ActorBudget, "bench:batch").requests == 2
        assert s.get(ActorBudget, "bench:batch").reserved == 0
    with pytest.raises(BusinessError, match="ROLE_NOT_APPROVED"):
        ledger.reserve("bench", "bench-1", "judge", "bad", 1, 10)


def test_unknown_pauses_same_model_other_batch_role_restart(service):
    ledger = setup(service)
    setup(service, "other")
    call = ledger.reserve("bench", "bench-1", "agent", "one", 30, 10)
    ledger.settle(call, None)
    with service.sessions() as s:
        assert s.get(ModelCall, call).reserved == 40
        assert s.get(SharedModelQuota, model_identity("dashscope", "beijing", MODEL)).paused
    restarted = ExperimentLedger(service.sessions)
    with pytest.raises(BusinessError, match="SHARED_MODEL_PAUSED"):
        restarted.reserve("other", "other-1", "user", "two", 10, 10)


def test_atomic_shared_quota_and_project_limit(service):
    ledger = setup(service, quota=70)

    def attempt(i):
        try:
            return ledger.reserve("bench", "bench-1", "agent", str(i), 40, 10)
        except BusinessError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert len([r for r in results if r.startswith("call_")]) == 1
    assert any(r in {"SHARED_QUOTA_EXHAUSTED", "UNRESOLVED_MODEL_USAGE"} for r in results)
    with service.sessions() as s:
        assert s.get(Budget, "project").reserved == 50


def test_restart_cannot_reset_or_replay_attempt(service):
    ledger = setup(service)
    call = ledger.reserve("bench", "bench-1", "agent", "same", 1, 10)
    ledger.settle(call, 2)
    with pytest.raises(BusinessError, match="ATTEMPT_REPLAY"):
        ledger.reserve("bench", "bench-1", "agent", "same", 1, 10)
    with pytest.raises(ValueError, match="RUN_RESTART_READ_ONLY"):
        setup(service)


def test_current_lower_quota_and_watermark_do_not_double_subtract(service):
    ledger = setup(service, quota=1000)
    call = ledger.reserve("bench", "bench-1", "agent", "first", 30, 10)
    ledger.settle(call, 25)
    setup(service, "next", quota=975)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.confirmed_remaining == 975
        assert call in quota.watermark["call_ids"]
    setup(service, "lower", quota=100)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.confirmed_remaining == 100


def test_legacy_unknown_provider_alias_blocks_new_roles_without_rewriting_old_call(service):
    from aftercare.llm.budget import BudgetLedger

    old = BudgetLedger(service.sessions)
    conversation = service.create_conversation("alice")
    call = old.reserve(
        "bailian-beijing-compatible", MODEL, "legacy", conversation, "legacy-run", 20, 10, 1000
    )
    old.settle(call, None)
    assert model_identity("bailian-beijing-compatible", "beijing", MODEL) == model_identity(
        "qwen", "beijing", MODEL
    )
    ledger = setup(service)
    with pytest.raises(BusinessError, match="SHARED_MODEL_PAUSED|UNRESOLVED_MODEL_USAGE"):
        ledger.reserve("bench", "bench-1", "user", "new", 1, 10)
    with service.sessions() as s:
        row = s.get(ModelCall, call)
        assert row.provider == "bailian-beijing-compatible" and row.status == "USAGE_UNKNOWN"
        assert row.reserved == 30 and row.usage is None


def test_legacy_settlement_does_not_implicitly_unpause_shared_model(service):
    from aftercare.llm.budget import BudgetLedger

    legacy = BudgetLedger(service.sessions)
    conv = service.create_conversation("alice")
    call = legacy.reserve("bailian-beijing-compatible", MODEL, "old", conv, "old-run", 20, 10, 1000)
    legacy.settle(call, None)
    ledger = setup(service)
    legacy.settle(call, 17)
    with pytest.raises(BusinessError, match="SHARED_MODEL_PAUSED"):
        ledger.reserve("bench", "bench-1", "user", "after-legacy-settlement", 1, 10)


def test_finished_hard_stop_closes_run_without_changing_usage(service):
    from aftercare.repositories.models import ExperimentEpisode, ExperimentRun

    ledger = setup(service)
    call = ledger.reserve("bench", "bench-1", "agent", "one", 10, 10)
    ledger.settle(call, 12)
    ledger.finish_episode("bench-1", "STOPPED", stop_batch=True)
    with service.sessions() as s:
        assert s.get(ExperimentRun, "bench").status == "STOPPED"
        assert s.get(ExperimentEpisode, "bench-1").status == "STOPPED"
        assert s.get(ModelCall, call).usage == 12
    with pytest.raises(BusinessError, match="EXPERIMENT_STOPPED"):
        ledger.reserve("bench", "bench-1", "agent", "two", 1, 10)


def test_fresh_account_snapshot_renews_only_quota_not_batch_or_unknown(service):
    from datetime import UTC, datetime

    from aftercare.repositories.models import ExperimentRun

    ledger = setup(service)
    first = ledger.reserve("bench", "bench-1", "agent", "first", 30, 10)
    ledger.settle(first, 25)
    with service.sessions() as s:
        plan = dict(s.get(ExperimentRun, "bench").config)
    plan["account_confirmation_id"] = "fresh-account"
    account = dict(
        plan_sha256="frozen",
        confirmation_id="fresh-account",
        FreeTierOnly=True,
        confirmed_at=datetime.now(UTC).isoformat(),
        models={model_identity("qwen", "beijing", MODEL): {"remaining": 1000}},
    )
    # Consumption after the human's snapshot must still be subtracted.
    second = ledger.reserve("bench", "bench-1", "user", "second", 30, 10)
    ledger.settle(second, 20)
    ledger.create_run("fresh", plan, account)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.confirmed_remaining == 980
        assert s.get(ActorBudget, "bench:batch").settled == 45
        assert s.get(ActorBudget, "fresh:batch").settled == 0
    # Reusing this snapshot cannot reset consumption a second time.
    setup(service, "later", quota=1000)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.confirmed_remaining == 980

    third = ledger.reserve("bench", "bench-1", "user", "third", 30, 10)
    ledger.settle(third, 10)
    ledger.create_run("reused-snapshot", plan, account)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.confirmed_remaining == 970
    unknown = ledger.reserve("bench", "bench-1", "agent", "unknown", 30, 10)
    ledger.settle(unknown, None)
    renewed = dict(
        account, confirmation_id="newer-account", confirmed_at=datetime.now(UTC).isoformat()
    )
    plan["account_confirmation_id"] = "newer-account"
    ledger.create_run("fresh-but-paused", plan, renewed)
    with service.sessions() as s:
        quota = s.get(SharedModelQuota, model_identity("qwen", "beijing", MODEL))
        assert quota.paused
        assert s.get(ModelCall, unknown).reserved == 40
