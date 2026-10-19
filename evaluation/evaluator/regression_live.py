"""Frozen seen-development entry. Requires NEW human approval; never invoked by default."""

import hashlib
import json
from pathlib import Path

from aftercare.config import PROJECT_ROOT
from aftercare.domain.rules import require
from aftercare.llm.regression_scope import read_scope
from evaluation.evaluator.pilot import run_batch, verify_account_connection
from evaluation.schema.scenario import Scenario


def preflight(settings, approval, account):
    plan = read_scope(approval)
    manifest = PROJECT_ROOT / plan["scenario_versions_manifest"]
    require(
        hashlib.sha256(manifest.read_bytes()).hexdigest()
        == plan["scenario_versions_manifest_sha256"],
        "SCENARIO_MANIFEST_VERSION_MISMATCH",
    )
    require(
        account.get("free_quota_tokens_at_least", 0) >= plan["total_token_hard_cap"],
        "CURRENT_FREE_QUOTA_CONFIRMATION_REQUIRED",
    )
    verify_account_connection(settings, account, plan["plan_sha256"])
    path = PROJECT_ROOT / plan["development_file"]
    require(
        hashlib.sha256(path.read_bytes()).hexdigest() == plan["development_file_sha256"],
        "DEV_VERSION_MISMATCH",
    )
    raw = [json.loads(line) for line in path.read_text().splitlines()]
    require(
        [x["scenario_id"] for x in raw] == [x["scenario_id"] for x in plan["tasks"]],
        "FIXED_TASK_SET_REQUIRED",
    )
    for case, item in zip(raw, plan["tasks"], strict=True):
        require(
            hashlib.sha256(
                json.dumps(case, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            == item["task_sha256"],
            "TASK_VERSION_MISMATCH",
        )
    cases = [Scenario.model_validate(c) for c in raw]
    require(all(c.split == "dev" for c in cases), "DEV_ONLY")
    return plan, cases


def run(settings, approval_path, account_path):
    approval = json.loads(Path(approval_path).read_text())
    account = json.loads(Path(account_path).read_text())
    plan, cases = preflight(settings, approval, account)
    return run_batch(
        settings, approval, account, plan, cases, PROJECT_ROOT / "runtime" / plan["batch_id"]
    )
