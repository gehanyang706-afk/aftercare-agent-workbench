"""Named development scopes. A plan is not approval; no permit is generated here."""

import hashlib
import json

from aftercare.config import PROJECT_ROOT
from aftercare.domain.rules import require

SCOPES = {
    "final-development-acceptance-v1": (6, 56000, 264000, 96, 1800),
}
TASK_TOKEN_CAPS = {"final-development-acceptance-v1": (40000, 40000, 40000, 48000, 40000, 56000)}

CLOSED_OR_SUPERSEDED = {
    "quantity-priority-development-v1",
    "diverse-behaviors-development-v1",
    "business-loop-regression-v2",
    "quantity-clarification-regression-v1",
    "business-loop-regression-v3",
    "quantity-clarification-regression-v2",
    "business-loop-regression-v4",
    "quantity-clarification-regression-v3",
}


def code_fingerprint():
    roots = ("src", "evaluation/evaluator", "evaluation/schema", "tests", "configs")
    paths = sorted(
        p
        for root in roots
        for p in (PROJECT_ROOT / root).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}
    )
    paths += [PROJECT_ROOT / "requirements.lock", PROJECT_ROOT / "pyproject.toml"]
    entries = {
        str(p.relative_to(PROJECT_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest(), entries


def read_scope(permit):
    batch = permit.get("batch_id")
    require(batch not in CLOSED_OR_SUPERSEDED, "BATCH_CLOSED_OR_SUPERSEDED")
    require(batch in SCOPES, "REGRESSION_BATCH_NOT_ALLOWED")
    plan = json.loads((PROJECT_ROOT / f"evaluation/manifests/{batch}.json").read_text())
    unsigned = dict(plan)
    declared = unsigned.pop("plan_sha256")
    actual = hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    require(actual == declared == permit.get("plan_sha256"), "REGRESSION_PLAN_HASH_MISMATCH")
    require(
        permit.get("source") == "Explicit user message in this chat",
        "REGRESSION_HUMAN_APPROVAL_REQUIRED",
    )
    tasks, task_tokens, tokens, requests, seconds = SCOPES[batch]
    bounds = {
        "batch_id": batch,
        "exact_model": "qwen3.5-plus-2026-02-15",
        "profile": "full",
        "unique_tasks": tasks,
        "max_conversations": tasks,
        "total_token_hard_cap": tokens,
        "max_token_per_conversation_including_input_output": task_tokens,
        "max_http_requests_including_retries": requests,
        "max_requests_per_conversation_including_retries": 16,
        "concurrency": 1,
        "batch_wall_seconds": seconds,
        "per_conversation_wall_seconds": 300,
        "max_output_tokens_per_request": 512,
        "sdk_retries": 0,
        "additional_paid_cost_cap_cny": 0,
        "enable_thinking": False,
        "repetitions": 1,
        "user_policy_version": "script-user-v3",
        "diagnostics_version": "process-diagnostic-v5",
        "quantity_evidence_version": "quantity-evidence-v2",
        "max_requests_per_user_turn_including_auxiliary_reasoning": 8,
        "http_retries": 0,
        "whole_task_reruns": 0,
        "model_user_calls": 0,
        "no_holdout_access": True,
        "no_formal_comparison": True,
        "old_budget_carryover": 0,
    }
    require(
        all(plan.get(k) == v and permit.get(k) == v for k, v in bounds.items()),
        "REGRESSION_SCOPE_MISMATCH",
    )
    caps = TASK_TOKEN_CAPS[batch]
    require(
        tuple(plan.get("per_task_token_hard_caps", [])) == caps
        and permit.get("per_task_token_hard_caps") == list(caps)
        and tuple(t.get("token_hard_cap") for t in plan["tasks"]) == caps
        and sum(caps) == tokens,
        "REGRESSION_TASK_CAPS_MISMATCH",
    )
    require(
        code_fingerprint()[0] == plan["candidate_source_tree_sha256"],
        "REGRESSION_CODE_VERSION_MISMATCH",
    )
    return plan


def bind_task_budget(plan, sessions, conversation, task_index):
    from aftercare.repositories.models import Conversation

    expected = {
        "batch_id": plan["batch_id"],
        "plan_sha256": plan["plan_sha256"],
        "task_index": task_index,
        "token_hard_cap": plan["per_task_token_hard_caps"][task_index],
    }
    with sessions.begin() as session:
        row = session.get(Conversation, conversation, with_for_update=True)
        require(row is not None, "TASK_BUDGET_CONVERSATION_REQUIRED")
        existing = (row.case or {}).get("evaluation_budget")
        require(existing in (None, expected), "TASK_BUDGET_REBIND_FORBIDDEN")
        row.case = {**(row.case or {}), "evaluation_budget": expected}


def bound_task_token_cap(plan, sessions, conversation):
    from aftercare.repositories.models import Conversation

    with sessions() as session:
        row = session.get(Conversation, conversation)
        bound = (row.case or {}).get("evaluation_budget") if row else None
    require(isinstance(bound, dict), "TASK_BUDGET_BINDING_REQUIRED")
    index = bound.get("task_index")
    caps = plan["per_task_token_hard_caps"]
    require(type(index) is int and 0 <= index < len(caps), "TASK_BUDGET_BINDING_MISMATCH")
    require(
        bound.get("batch_id") == plan["batch_id"]
        and bound.get("plan_sha256") == plan["plan_sha256"]
        and bound.get("token_hard_cap") == caps[index],
        "TASK_BUDGET_BINDING_MISMATCH",
    )
    return caps[index]
