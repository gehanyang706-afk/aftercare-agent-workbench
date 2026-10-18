"""One-shot four-task pilot, business resets isolated from durable real-call ledger."""

import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.domain.rules import require
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.pilot_gateway import PLAN_HASH
from aftercare.llm.smoke import MODEL, now, write_json
from aftercare.repositories.database import is_local_database, session_factory
from aftercare.repositories.models import ModelCall
from aftercare.services.business import BusinessService, columns
from evaluation.evaluator.runner import load_dev, run_case


def preflight(settings, approval, account, plan):
    p = dict(plan)
    declared = p.pop("plan_sha256")
    digest = hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    require(digest == declared == PLAN_HASH, "PILOT_PLAN_HASH_MISMATCH")
    require(
        approval.get("plan_sha256") == digest
        and approval.get("source") == "Explicit user message in this chat",
        "PILOT_HUMAN_APPROVAL_REQUIRED",
    )
    bounds = {
        "exact_model": MODEL,
        "unique_tasks": 4,
        "max_conversations": 4,
        "max_requests_per_conversation_including_retries": 16,
        "max_http_requests_including_retries": 64,
        "max_token_per_conversation_including_input_output": 24000,
        "total_token_hard_cap": 96000,
        "concurrency": 1,
        "batch_wall_seconds": 1200,
        "additional_paid_cost_cap_cny": 0,
        "profile": "full",
    }
    require(
        all(plan.get(k) == v and approval.get(k) == v for k, v in bounds.items()),
        "PILOT_SCOPE_MISMATCH",
    )
    verify_account_connection(settings, account, digest)
    path = PROJECT_ROOT / "evaluation/dev/scenarios.jsonl"
    require(
        hashlib.sha256(path.read_bytes()).hexdigest() == plan["development_file_sha256"],
        "DEV_VERSION_MISMATCH",
    )
    all_cases = {c.scenario_id: c for c in load_dev()}
    cases = []
    for item in plan["tasks"]:
        case = all_cases[item["scenario_id"]]
        # Raw task JSON has equivalent date formatting frozen by its author.
        raw = next(
            json.loads(line)
            for line in path.read_text().splitlines()
            if json.loads(line)["scenario_id"] == case.scenario_id
        )
        require(
            hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            == item["task_sha256"],
            "TASK_VERSION_MISMATCH",
        )
        cases.append(case)
    require(
        [c.scenario_id for c in cases] == ["d-001", "d-003", "d-016", "d-048"],
        "FIXED_TASK_SET_REQUIRED",
    )
    return cases


def verify_account_connection(settings, account, digest):
    require(
        account.get("plan_sha256") == digest
        and all(
            account.get(k) is True
            for k in (
                "beijing_key_confirmed",
                "free_tier_only_confirmed",
                "sufficient_quota_confirmed",
            )
        ),
        "ACCOUNT_CONFIRMATION_REQUIRED",
    )
    require(
        settings.allow_real_model_calls and settings.dashscope_api_key.get_secret_value().strip(),
        "REAL_FLAG_AND_KEY_REQUIRED",
    )
    url = urlsplit(settings.dashscope_base_url.get_secret_value().strip())
    require(
        url.scheme == "https"
        and not url.query
        and not url.fragment
        and not url.username
        and not url.password
        and url.port in {None, 443},
        "HTTPS_ENDPOINT_REQUIRED",
    )
    require(
        (
            url.hostname == "dashscope.aliyuncs.com"
            or bool(url.hostname and url.hostname.endswith(".cn-beijing.maas.aliyuncs.com"))
        )
        and url.path.rstrip("/") == "/compatible-mode/v1",
        "BEIJING_COMPATIBLE_ENDPOINT_REQUIRED",
    )
    db = make_url(settings.database_url.get_secret_value())
    require(
        is_local_database(db) and db.database == "aftercare_demo", "DURABLE_DEMO_LEDGER_REQUIRED"
    )


class PilotActor:
    def __init__(self, log, ledger_conversation, deadline, directory, permit):
        self.log = log.open("w")
        self.deadline, self.ledger_conversation = deadline, ledger_conversation
        self.directory, self.permit = directory, permit
        self.child = subprocess.Popen(
            [sys.executable, "-m", "evaluation.evaluator.pilot_actor"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def invoke(self, command):
        remaining = self.deadline - time.time()
        require(remaining > 0, "TASK_DEADLINE_EXCEEDED")
        safe = {
            **command,
            "ledger_conversation": self.ledger_conversation,
            "deadline": self.deadline,
            "trace_directory": str(self.directory),
            "permit": self.permit,
        }
        self.child.stdin.write(json.dumps(safe) + "\n")
        self.child.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.child.stdout, selectors.EVENT_READ)
            if not selector.select(remaining):
                self.close()
                raise TimeoutError("TASK_DEADLINE_EXCEEDED")
        line = self.child.stdout.readline()
        require(bool(line), "ACTOR_EXITED")
        return json.loads(line)

    def close(self):
        if self.child.poll() is None:
            os.killpg(self.child.pid, signal.SIGTERM)
            try:
                self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait()
        self.log.close()


def stop_batch(error):
    return any(
        word in (error or "")
        for word in (
            "USAGE_",
            "PROVIDER_",
            "SECURITY_",
            "BUDGET_",
            "TOKEN_LIMIT",
            "MODEL_CALL_LIMIT",
            "BATCH_REQUEST_LIMIT",
            "DEADLINE",
            "TimeoutError",
            "PermissionError",
        )
    )


def run(settings, approval_path, account_path):
    plan = json.loads((PROJECT_ROOT / "evaluation/manifests/development-pilot.json").read_text())
    approval = json.loads(Path(approval_path).read_text())
    account = json.loads(Path(account_path).read_text())
    cases = preflight(settings, approval, account, plan)
    return run_batch(
        settings, approval, account, plan, cases, PROJECT_ROOT / "runtime/development-pilot-first"
    )


def run_batch(settings, approval, account, plan, cases, directory):
    batch_id, plan_hash = plan["batch_id"], plan["plan_sha256"]
    ledger_sessions = session_factory(settings)
    business_settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test",
    )
    business_sessions = session_factory(business_settings)
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "batch-state.json"
    with ledger_sessions.kw["bind"].connect() as lock:
        require(lock.scalar(text("SELECT pg_try_advisory_lock(62006002)")), "PILOT_ALREADY_RUNNING")
        try:
            require(not state_path.exists(), "PILOT_ALREADY_STARTED_NO_WHOLE_TASK_RERUN")
            with ledger_sessions() as s:
                require(
                    s.scalar(select(ModelCall.id).where(ModelCall.batch_id == batch_id)) is None,
                    "EXISTING_PILOT_CALLS",
                )
            state = {
                "batch_id": batch_id,
                "plan_sha256": plan_hash,
                "status": "RUNNING",
                "started_at": now(),
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
                ).strip(),
                "tasks": [],
                "stop_reason": None,
                "profile": "full",
                "user": plan["user_simulator"],
            }
            write_json(state_path, state)
            start = time.monotonic()
            batch_deadline = time.time() + plan["batch_wall_seconds"]
            ledger_service = BusinessService(ledger_sessions)
            for case in cases:
                if time.time() >= batch_deadline:
                    state["stop_reason"] = "BATCH_DEADLINE"
                    break
                ledger_conv = ledger_service.create_conversation("alice")
                task_start = time.monotonic()
                deadline = min(batch_deadline, time.time() + plan["per_conversation_wall_seconds"])

                def actor_factory(log, ledger_conv=ledger_conv, deadline=deadline):
                    return PilotActor(log, ledger_conv, deadline, directory / "traces", approval)

                result = run_case(
                    case,
                    business_settings,
                    business_sessions,
                    "full",
                    directory,
                    actor_factory=actor_factory,
                )
                BudgetLedger(ledger_sessions).mark_unresolved_unknown(ledger_conv)
                with ledger_sessions() as s:
                    calls = [
                        columns(c)
                        for c in s.scalars(
                            select(ModelCall).where(ModelCall.conversation_id == ledger_conv)
                        )
                    ]
                from evaluation.evaluator.diagnostics_v4 import diagnose, event_chain

                result["diagnostics"] = diagnose(result["observed"])
                result["event_chain"] = event_chain(result["observed"])
                result["ledger_conversation"] = ledger_conv
                result["actual_calls"] = calls
                result["latency_seconds"] = round(time.monotonic() - task_start, 3)
                result["input_tokens"] = sum(c["details"].get("input_tokens", 0) for c in calls)
                result["output_tokens"] = sum(c["details"].get("output_tokens", 0) for c in calls)
                result["request_count"] = len(calls)
                result["unknown_reserved_tokens"] = sum(
                    c["reserved"] for c in calls if c["usage"] is None
                )
                write_json(directory / f"{case.scenario_id}.json", result)
                state["tasks"].append(result)
                error = result["result"].get("system_error") or ""
                if result["unknown_reserved_tokens"] or stop_batch(error):
                    state["stop_reason"] = error or "USAGE_UNKNOWN"
                if result["observed"]["events"] and any(
                    e["event_type"] == "forbidden_tool_attempt"
                    for e in result["observed"]["events"]
                ):
                    state["stop_reason"] = "SECURITY_UNAUTHORIZED_TOOL_ATTEMPT"
                write_json(state_path, state)
                if state["stop_reason"]:
                    break
            state["elapsed_seconds"] = round(time.monotonic() - start, 3)
            state["status"] = "STOPPED" if state["stop_reason"] else "COMPLETED"
            state["attempted_tasks"] = len(state["tasks"])
            state["planned_tasks"] = len(cases)
            state["passed_tasks"] = sum(t["result"]["success"] for t in state["tasks"])
            state["request_count"] = sum(t["request_count"] for t in state["tasks"])
            state["known_input_tokens"] = sum(t["input_tokens"] for t in state["tasks"])
            state["known_output_tokens"] = sum(t["output_tokens"] for t in state["tasks"])
            state["unknown_reserved_tokens"] = sum(
                t["unknown_reserved_tokens"] for t in state["tasks"]
            )
            state["not_run"] = [
                c.scenario_id
                for c in cases
                if c.scenario_id not in {t["scenario_id"] for t in state["tasks"]}
            ]
            write_json(state_path, state)
            return state
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(62006002)"))
            lock.commit()
            business_sessions.kw["bind"].dispose()
            ledger_sessions.kw["bind"].dispose()
