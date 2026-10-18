import pytest
from sqlalchemy import select

from aftercare.config import Settings
from aftercare.domain.contracts import BusinessError
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.pilot_gateway import PilotGateway
from aftercare.llm.regression_scope import bind_task_budget, bound_task_token_cap
from aftercare.repositories.models import Conversation, ModelCall

PLAN = {
    "batch_id": "quantity-priority-development-v1",
    "plan_sha256": "offline-contract",
    "per_task_token_hard_caps": [48000, 40000, 40000, 48000],
    "total_token_hard_cap": 176000,
    "max_http_requests_including_retries": 64,
}


def test_task_binding_survives_reconstruction_and_cannot_be_rebound(service):
    for i, cap in enumerate(PLAN["per_task_token_hard_caps"]):
        conv = service.create_conversation("alice")
        bind_task_budget(PLAN, service.sessions, conv, i)
        assert bound_task_token_cap(PLAN, service.sessions, conv) == cap
        bind_task_budget(PLAN, service.sessions, conv, i)
        with pytest.raises(BusinessError, match="REBIND_FORBIDDEN"):
            bind_task_budget(PLAN, service.sessions, conv, (i + 1) % 4)


def test_tampered_or_missing_budget_does_not_fall_back_to_batch_maximum(service):
    conv = service.create_conversation("alice")
    with pytest.raises(BusinessError, match="BINDING_REQUIRED"):
        bound_task_token_cap(PLAN, service.sessions, conv)
    bind_task_budget(PLAN, service.sessions, conv, 1)
    with service.sessions.begin() as s:
        row = s.get(Conversation, conv)
        row.case = {"evaluation_budget": {**row.case["evaluation_budget"], "token_hard_cap": 48000}}
    with pytest.raises(BusinessError, match="BINDING_MISMATCH"):
        bound_task_token_cap(PLAN, service.sessions, conv)


def test_gateway_uses_bound_40k_and_ledger_does_not_borrow_other_task_headroom(
    service, monkeypatch, tmp_path
):
    from aftercare.llm import regression_scope

    conv = service.create_conversation("alice")
    bind_task_budget(PLAN, service.sessions, conv, 1)
    monkeypatch.setattr(regression_scope, "read_scope", lambda permit: PLAN)
    settings = Settings(
        _env_file=None,
        allow_real_model_calls=True,
        dashscope_api_key="OFFLINE-NOT-A-KEY",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    gateway = PilotGateway(
        settings, service.sessions, conv, service, "alice", conv, "offline", 0, tmp_path, PLAN
    )
    assert gateway.task_cap == 40000
    ledger = BudgetLedger(service.sessions)
    call = ledger.reserve(
        "scripted",
        "offline",
        "offline",
        conv,
        "first",
        39000,
        512,
        176000,
        conversation_cap=gateway.task_cap,
    )
    ledger.settle(call, 39000)
    with pytest.raises(BusinessError, match="CONVERSATION_TOKEN_LIMIT"):
        ledger.reserve(
            "scripted",
            "offline",
            "offline",
            conv,
            "second",
            1000,
            512,
            176000,
            conversation_cap=gateway.task_cap,
        )
    with service.sessions() as s:
        assert len(list(s.scalars(select(ModelCall)))) == 1
