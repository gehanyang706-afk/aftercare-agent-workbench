"""Two named future scopes. A plan is not approval; no permit is generated here."""

import hashlib
import json

from aftercare.config import PROJECT_ROOT
from aftercare.domain.rules import require

SCOPES = {
    "business-loop-regression-v3": (4, 40000, 160000, 64, 1200),
    "quantity-clarification-regression-v2": (2, 32000, 64000, 32, 600),
}
CLOSED_OR_SUPERSEDED = {"business-loop-regression-v2", "quantity-clarification-regression-v1"}


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
    }
    require(
        all(plan.get(k) == v and permit.get(k) == v for k, v in bounds.items()),
        "REGRESSION_SCOPE_MISMATCH",
    )
    require(
        code_fingerprint()[0] == plan["candidate_source_tree_sha256"],
        "REGRESSION_CODE_VERSION_MISMATCH",
    )
    return plan
