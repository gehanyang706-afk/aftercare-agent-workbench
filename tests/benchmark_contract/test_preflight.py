from copy import deepcopy
from datetime import UTC, datetime

import pytest

from aftercare.llm.experiment_scope import authorize, model_identity, plan_hash


def values():
    role = dict(
        enabled=True,
        provider="qwen",
        region="beijing",
        exact_model="exact",
        batch_token_cap=50,
        episode_token_cap=20,
        request_cap=4,
        output_cap=5,
    )
    plan = dict(
        source_tree_hash="hash",
        additional_paid_cost_cap_cny=0,
        concurrency=1,
        retries=0,
        auto_review=False,
        account_confirmation_id="current",
        roles={"agent": role, "user": deepcopy(role), "judge": {"enabled": False}},
    )
    plan["plan_sha256"] = plan_hash(plan)
    approval = dict(plan_sha256=plan["plan_sha256"], source="Explicit user message in this chat")
    account = dict(
        plan_sha256=plan["plan_sha256"],
        FreeTierOnly=True,
        confirmation_id="current",
        confirmed_at=datetime.now(UTC).isoformat(),
        models={model_identity("dashscope", "beijing", "exact"): {"remaining": 100}},
    )
    return plan, approval, account


def test_account_aggregates_roles_same_model_and_expires():
    plan, approval, account = values()
    assert list(authorize(plan, approval, account, "hash").values()) == [100]
    account["models"][model_identity("dashscope", "beijing", "exact")]["remaining"] = 99
    with pytest.raises(ValueError, match="INSUFFICIENT_SHARED"):
        authorize(plan, approval, account, "hash")
    account["confirmed_at"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="EXPIRED"):
        authorize(plan, approval, account, "hash")


def test_plan_mutation_or_old_account_cannot_authorize():
    plan, approval, account = values()
    plan["roles"]["agent"]["output_cap"] = 100
    with pytest.raises(ValueError, match="HASH"):
        authorize(plan, approval, account, "hash")
    plan, approval, account = values()
    account["FreeTierOnly"] = False
    with pytest.raises(ValueError, match="ACCOUNT"):
        authorize(plan, approval, account, "hash")


def test_tune_scope_cannot_switch_split_variants_or_fixed_tasks():
    from evaluation.benchmarks.tau_retail.runner import validate_stage

    pool = {"calibration": ["a", "b"], "tune_run": ["a", "b", "c", "d"]}
    plan = dict(
        stage="tune",
        split="train",
        task_ids=pool["tune_run"],
        variants=["official_tc", "harness_evidence"],
    )
    with pytest.raises(ValueError, match="SUSPENDED"):
        validate_stage(plan, pool)
    plan = dict(
        plan,
        stage="tool_visibility",
        task_ids=["a"],
        variants=["official_tc", "tool_visibility_v1"],
    )
    pool["tool_visibility_pilot"] = ["a"]
    validate_stage(plan, pool)
    for field, value in [
        ("split", "test"),
        ("variants", ["official_tc", "harness_fixed_window"]),
        ("task_ids", ["c", "d"]),
        ("stage", "validation"),
    ]:
        with pytest.raises(ValueError):
            validate_stage(dict(plan, **{field: value}), pool)


def test_new_plan_cannot_silently_raise_project_budget():
    from types import SimpleNamespace

    from evaluation.benchmarks.tau_retail.runner import validate_project_capacity

    budget = SimpleNamespace(cap=100, settled=20, reserved=10, paused=False)
    validate_project_capacity(budget, {"total_token_cap": 70})
    with pytest.raises(ValueError, match="SEPARATE_APPROVAL"):
        validate_project_capacity(
            budget, {"total_token_cap": 71, "project_cap_change_authorized": True}
        )
    assert budget.cap == 100
    budget.paused = True
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        validate_project_capacity(budget, {"total_token_cap": 1})
