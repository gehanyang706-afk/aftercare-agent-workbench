"""Permit counterexamples only: no provider transport or secret is used."""

import json

import pytest

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.domain.contracts import BusinessError
from aftercare.llm.regression_scope import SCOPES, read_scope
from evaluation.evaluator.regression_live import preflight


def plan_for(batch):
    return json.loads((PROJECT_ROOT / f"evaluation/manifests/{batch}.json").read_text())


def account_for(plan):
    return {
        "plan_sha256": plan["plan_sha256"],
        "beijing_key_confirmed": True,
        "free_tier_only_confirmed": True,
        "sufficient_quota_confirmed": True,
        "free_quota_tokens_at_least": plan["total_token_hard_cap"],
    }


def settings():
    return Settings(
        _env_file=None,
        allow_real_model_calls=True,
        dashscope_api_key="not-a-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        database_url="postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_demo",
    )


@pytest.mark.parametrize("batch", list(SCOPES))
def test_frozen_scope_rejects_unapproved_old_expanded_or_unprotected_permits(batch):
    p = plan_for(batch)
    with pytest.raises(BusinessError, match="HUMAN_APPROVAL"):
        read_scope(p)  # a plan itself is not approval
    permit = {**p, "source": "Explicit user message in this chat"}
    assert len(preflight(settings(), permit, account_for(p))[1]) == p["unique_tasks"]
    with pytest.raises(BusinessError, match="SCOPE_MISMATCH"):
        read_scope({**permit, "total_token_hard_cap": p["total_token_hard_cap"] + 1})
    with pytest.raises(BusinessError, match="HASH_MISMATCH"):
        read_scope(
            {
                **permit,
                "plan_sha256": "9eb8329777e719103f86c188bea0d99d84ec4a9250f2a31575e2a76fd810d894",
            }
        )
    with pytest.raises(BusinessError, match="CURRENT_FREE_QUOTA"):
        preflight(settings(), permit, {**account_for(p), "free_quota_tokens_at_least": 0})
    with pytest.raises(BusinessError, match="ACCOUNT_CONFIRMATION"):
        preflight(settings(), permit, {**account_for(p), "free_tier_only_confirmed": False})
    with pytest.raises(BusinessError, match="REAL_FLAG"):
        preflight(
            settings().model_copy(update={"allow_real_model_calls": False}), permit, account_for(p)
        )


def test_no_plan_creates_an_approval_file():
    for batch in SCOPES:
        assert not (PROJECT_ROOT / f"runtime/{batch}/batch-state.json").exists()


def test_old_live_plan_and_old_quantity_hash_cannot_authorize_new_code():
    for batch in [
        "business-loop-regression-v2",
        "quantity-clarification-regression-v1",
        "business-loop-regression-v3",
        "quantity-clarification-regression-v2",
        "business-loop-regression-v4",
        "quantity-clarification-regression-v3",
        "diverse-behaviors-development-v1",
    ]:
        old = plan_for(batch)
        with pytest.raises(BusinessError, match="CLOSED_OR_SUPERSEDED"):
            read_scope({**old, "source": "Explicit user message in this chat"})
