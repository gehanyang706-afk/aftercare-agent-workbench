"""Explicit approved train execution; no official default CLI, no task retries."""

import csv
import hashlib
import json
import time
from pathlib import Path

from sqlalchemy import select, text

from aftercare.config import Settings
from aftercare.harness.contracts import digest
from aftercare.llm.experiment_gateway import ExperimentLedger
from aftercare.llm.experiment_scope import authorize, plan_hash
from aftercare.repositories.database import session_factory
from aftercare.repositories.models import Budget, ModelCall
from evaluation.benchmarks.tau_retail.metrics import summarize
from evaluation.benchmarks.tau_retail.source_guard import (
    ROOT,
    load_train_tasks,
    source_fingerprint,
    upstream,
)
from evaluation.benchmarks.tau_retail.trace import Trace


def validate_stage(plan, pool):
    allowed = {
        "calibration": ("calibration", ["official_tc", "harness_full_history"]),
        "tune": ("tune_run", ["official_tc", "harness_evidence"]),
        "tool_visibility": ("tool_visibility_pilot", ["official_tc", "tool_visibility_v1"]),
    }
    if plan.get("stage") not in allowed:
        raise ValueError("ONLY_FROZEN_TRAIN_STAGES_SUPPORTED")
    if plan.get("stage") == "tune":
        raise ValueError("TUNE_V1_SUSPENDED")
    key, variants = allowed[plan["stage"]]
    if (
        plan.get("split") != "train"
        or plan["task_ids"] != pool[key]
        or plan["variants"] != variants
    ):
        raise ValueError("FIXED_STAGE_SCOPE_MISMATCH")


def validate_project_capacity(budget, plan):
    if budget is None or budget.paused:
        raise ValueError("PROJECT_BUDGET_UNAVAILABLE")
    if budget.cap - budget.settled - budget.reserved < plan["total_token_cap"]:
        raise ValueError("PROJECT_CAP_INCREASE_REQUIRES_SEPARATE_APPROVAL")


def preflight(plan, approval=None, account=None):
    upstream()
    errors = []
    if plan.get("plan_sha256") != plan_hash(plan):
        errors.append("PLAN_HASH_MISMATCH")
    lock = json.loads((ROOT / "benchmarks/tau_retail/upstream.lock.json").read_text())
    if plan.get("upstream_commit") != lock["commit"]:
        errors.append("UPSTREAM_COMMIT_MISMATCH")
    actual_lock = hashlib.sha256(
        (ROOT / "benchmarks/tau_retail/requirements.lock").read_bytes()
    ).hexdigest()
    if plan.get("dependency_lock_hash") != actual_lock:
        errors.append("DEPENDENCY_LOCK_HASH_MISMATCH")
    required = (
        "run_id",
        "batch_id",
        "experiment_version",
        "source_commit",
        "source_tree_hash",
        "upstream_commit",
        "dependency_lock_hash",
        "task_ids",
        "task_content_hash",
        "variants",
        "trial",
        "episodes",
        "roles",
        "total_token_cap",
        "request_cap",
        "episode_token_cap",
        "episode_request_cap",
        "episode_seconds",
        "wall_clock_seconds",
        "max_steps",
        "max_errors",
        "request_seconds",
        "consecutive_request_cap",
        "concurrency",
        "retries",
        "additional_paid_cost_cap_cny",
        "auto_review",
        "evaluation_type",
        "scorer_hash",
        "policy_hash",
        "tools_hash",
        "order_seed",
        "account_confirmation_id",
        "environment_versions",
    )
    for key in required:
        if key not in plan or plan[key] is None:
            errors.append("MISSING:" + key)
    if plan.get("source_tree_hash") != source_fingerprint():
        errors.append("SOURCE_HASH_MISMATCH")
    if plan.get("stage") == "tune":
        errors.append("TUNE_V1_SUSPENDED")
    if plan.get("stage") == "tool_visibility":
        from evaluation.benchmarks.tau_retail.tool_visibility import RULE_VERSION, rule_hash

        if (
            plan.get("tool_visibility_rule_hash") != rule_hash()
            or plan.get("tool_visibility_version") != RULE_VERSION
        ):
            errors.append("TOOL_VISIBILITY_RULE_HASH_MISMATCH")
        if plan.get("tool_visibility_catalog_hash") != plan.get("tools_hash"):
            errors.append("TOOL_VISIBILITY_CATALOG_HASH_MISMATCH")
        evidence_path = (
            ROOT / "evaluation/manifests/benchmark-v1/tool-visibility-offline-evidence-v1.json"
        )
        if not evidence_path.exists() or digest(json.loads(evidence_path.read_text())) != plan.get(
            "offline_evidence_hash"
        ):
            errors.append("OFFLINE_VISIBILITY_EVIDENCE_CHANGED")
        if plan.get("offline_screen_passed") is not True:
            errors.append("OFFLINE_VISIBILITY_SCREEN_NOT_PASSED")
    if approval is None or account is None:
        errors.append("HUMAN_APPROVAL_AND_CURRENT_ACCOUNT_REQUIRED")
    elif not errors:
        try:
            authorize(plan, approval, account, source_fingerprint())
            from evaluation.benchmarks.tau_retail.cli import configure

            configure()
            import platform
            from importlib.metadata import version

            from tau2.domains.retail.environment import get_environment

            environment = get_environment()
            tasks = load_train_tasks(plan["task_ids"])
            actual_versions = {
                name: version(name) for name in plan["environment_versions"] if name != "python"
            }
            actual_versions["python"] = platform.python_version()
            if actual_versions != plan["environment_versions"]:
                raise ValueError("ENVIRONMENT_VERSION_MISMATCH")
            if digest([t.model_dump(mode="json") for t in tasks]) != plan["task_content_hash"]:
                raise ValueError("TASK_CONTENT_HASH_MISMATCH")
            if (
                digest(environment.get_policy()) != plan["policy_hash"]
                or digest([t.openai_schema for t in environment.get_tools()]) != plan["tools_hash"]
            ):
                raise ValueError("POLICY_OR_SCHEMA_MISMATCH")
            needs_judge = [
                t.id
                for t in tasks
                if t.evaluation_criteria.nl_assertions
                and any(b.value == "NL_ASSERTION" for b in t.evaluation_criteria.reward_basis)
            ]
            judge = plan["roles"].get("judge", {})
            if needs_judge and (not judge.get("enabled") or judge.get("task_ids") != needs_judge):
                raise ValueError("JUDGE_REQUIRES_EXPLICIT_ROLE_PLAN")
            if plan["stage"] == "tool_visibility" and (
                needs_judge
                or judge.get("enabled")
                or plan["roles"].get("auxiliary", {}).get("enabled")
            ):
                raise ValueError("VISIBILITY_PILOT_UNEXPECTED_ROLE")
            pool = json.loads(
                (ROOT / "evaluation/manifests/benchmark-v1/development-pool.json").read_text()
            )
            validate_stage(plan, pool)
            pairs = [(e["task_id"], e["variant"]) for e in plan["episodes"]]
            expected = {(t, v) for t in plan["task_ids"] for v in plan["variants"]}
            if len(pairs) != len(expected) or set(pairs) != expected:
                raise ValueError("FIXED_EPISODES_MISMATCH")
            sessions = session_factory(Settings())
            try:
                with sessions() as session:
                    if not session.scalar(text("SELECT to_regclass('experiment_runs')")):
                        raise ValueError("EXPERIMENT_LEDGER_MIGRATION_REQUIRED")
                    validate_project_capacity(session.get(Budget, "project"), plan)
                    unresolved = list(
                        session.scalars(select(ModelCall).where(ModelCall.usage.is_(None)))
                    )
                    models = {c["exact_model"] for c in plan["roles"].values() if c.get("enabled")}
                    if any(c.exact_model in models for c in unresolved):
                        raise ValueError("UNRESOLVED_MODEL_USAGE")
                    prior = list(
                        session.scalars(select(ModelCall).where(ModelCall.exact_model.in_(models)))
                    )
                    if any(session.get(Budget, c.budget_id).paused for c in prior):
                        raise ValueError("LEGACY_MODEL_BUDGET_PAUSED")
            finally:
                sessions.kw["bind"].dispose()

        except (ValueError, KeyError, TypeError) as e:
            errors.append(str(e))
    return {"executable": not errors, "errors": errors, "real_requests": 0}


def export(run_dir, rows):
    run_dir = Path(run_dir)
    with (run_dir / "episodes.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (run_dir / "episodes.csv").open("w") as f:
        fields = [
            "task_id",
            "variant",
            "trial",
            "status",
            "official_reward",
            "execution_stop",
            "seconds",
        ]
        role_fields = (
            "input_tokens",
            "output_tokens",
            "known_tokens",
            "unknown_reserved",
            "http_requests",
            "model_wait_seconds",
        )
        fields += [
            role + "_" + field
            for role in ("agent", "user", "judge", "auxiliary")
            for field in role_fields
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for role, values in row.get("roles", {}).items():
                flat.update({role + "_" + k: v for k, v in values.items()})
            writer.writerow(flat)
    summary = summarize(rows)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run_dir / "report.md").write_text(
        "# Fixed Retail run\n\n" + json.dumps(summary, indent=2) + "\n"
    )
    reconcile = {
        role: {
            key: sum(r.get("roles", {}).get(role, {}).get(key, 0) for r in rows)
            for key in ("known_tokens", "unknown_reserved", "http_requests")
        }
        for role in ("agent", "user", "judge", "auxiliary")
    }
    (run_dir / "ledger-reconciliation.json").write_text(json.dumps(reconcile, indent=2) + "\n")
    hashes = {
        str(p.relative_to(run_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in run_dir.rglob("*.json*")
        if p.name != "raw-trace-hashes.json"
    }
    (run_dir / "raw-trace-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return summary


def execute(plan, approval, account):
    from tau2.domains.retail.environment import get_environment
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    from tau2.orchestrator.orchestrator import Orchestrator
    from tau2.user.user_simulator import UserSimulator

    from aftercare.llm.smoke import send_once
    from aftercare.llm.supervisor import bounded
    from aftercare.offline import install_offline_guard
    from evaluation.benchmarks.tau_retail.model_bridge import (
        CompletionBridge,
        official_bridge,
        official_judge_configuration,
    )
    from evaluation.benchmarks.tau_retail.registry import VARIANTS

    settings = Settings()
    if not settings.allow_real_model_calls:
        raise ValueError("EXPLICIT_REAL_CALL_FLAG_REQUIRED")
    endpoint = settings.dashscope_base_url.get_secret_value().rstrip("/")
    if endpoint != "https://dashscope.aliyuncs.com/compatible-mode/v1":
        raise ValueError("BEIJING_ENDPOINT_REQUIRED")
    key = settings.dashscope_api_key.get_secret_value()
    if not key:
        raise ValueError("KEY_MISSING")
    check = preflight(plan, approval, account)
    if not check["executable"]:
        raise ValueError("PREFLIGHT_DENIED:" + str(check["errors"]))
    install_offline_guard()  # Parent cannot leak via default SDK/telemetry/unknown role.
    directory = ROOT / "runtime/retail-runs" / plan["run_id"]
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
    (directory / "preflight.json").write_text(json.dumps(check, indent=2) + "\n")
    tasks = {t.id: t for t in load_train_tasks(plan["task_ids"])}
    sessions = session_factory(settings)
    ledger = ExperimentLedger(sessions)
    ledger.create_run(plan["run_id"], plan, account)
    deadline = time.time() + plan["wall_clock_seconds"]
    rows = [
        dict(
            experiment_version=plan["experiment_version"],
            task_id=e["task_id"],
            variant=e["variant"],
            trial=plan["trial"],
            status="not_run",
            official_reward=None,
            execution_stop="not_started",
            roles={},
        )
        for e in plan["episodes"]
    ]
    for index, row in enumerate(rows):
        episode_id = f"{plan['run_id']}:{index}"
        episode_start = time.monotonic()
        ledger.create_episode(
            plan["run_id"], episode_id, {k: row[k] for k in ("task_id", "variant", "trial")}
        )
        trace = Trace(
            directory / str(index), plan["run_id"], episode_id, row["variant"], plan["trial"]
        )
        task = tasks[row["task_id"]]

        def args(role):
            c = plan["roles"][role]
            return dict(
                num_retries=0,
                max_tokens=c["output_cap"],
                temperature=c["temperature"],
                extra_body={"enable_thinking": c["thinking"]},
            )

        env = get_environment()
        from evaluation.benchmarks.tau_retail.trace import attach_environment_trace

        tool_metrics = attach_environment_trace(env, trace)
        agent = VARIANTS[row["variant"]](
            tools=env.get_tools(),
            domain_policy=env.get_policy(),
            llm=plan["roles"]["agent"]["exact_model"],
            llm_args=args("agent"),
        )
        if row["variant"] != "official_tc":
            agent.trace = trace  # Audit only; baseline keeps its original class and prompt.
        user = UserSimulator(
            llm=plan["roles"]["user"]["exact_model"],
            instructions=str(task.user_scenario),
            llm_args=args("user"),
        )

        original_user_generate = user.generate_next_message

        def observed_user(message, state, generate=original_user_generate, trace=trace):
            result, new_state = generate(message, state)
            trace.emit("user.message", result.model_dump(mode="json"), role="user")
            return result, new_state

        user.generate_next_message = observed_user

        def transport(payload, timeout):
            response = bounded(send_once, (endpoint, key, payload), seconds=timeout)
            if response.get("http_status") != 200:
                return {
                    "usage": response.get("usage"),
                    "choices": [],
                    "error": "HTTP_ERROR",
                    "http_status": response.get("http_status"),
                    "request_id": response.get("request_id"),
                    "transport_error": response.get("error"),
                }
            return response["data"]

        bridge = CompletionBridge(
            ledger,
            plan["run_id"],
            episode_id,
            plan["roles"],
            transport,
            trace,
            min(deadline, time.time() + plan["episode_seconds"]),
            tool_scope=dict(
                variant=row["variant"],
                catalog=[t.openai_schema for t in env.get_tools()],
                catalog_hash=plan["tool_visibility_catalog_hash"],
                rule_hash=plan["tool_visibility_rule_hash"],
            )
            if plan["stage"] == "tool_visibility"
            else None,
        )
        stop = False
        try:
            row["status"] = "attempted"
            with (
                official_bridge(bridge),
                official_judge_configuration(plan["roles"].get("judge", {})),
            ):
                simulation = Orchestrator(
                    domain="retail",
                    agent=agent,
                    user=user,
                    environment=env,
                    task=task,
                    max_steps=plan["max_steps"],
                    max_errors=plan["max_errors"],
                    seed=plan["order_seed"],
                    timeout=plan["episode_seconds"],
                ).run()
                trace.emit("env.terminated", simulation.model_dump(mode="json"), role="system")
                reward = evaluate_simulation(simulation, task, EvaluationType.ALL, False, "retail")
                row.update(
                    status="completed",
                    official_reward=reward.reward,
                    official_components=reward.model_dump(mode="json"),
                    execution_stop=str(simulation.termination_reason),
                )
                trace.emit("eval.completed", row["official_components"], role="system")
        except Exception as error:
            # Any transport/protocol/budget exception is hard; ordinary reward=0 continues.
            row.update(status="stopped", execution_stop=type(error).__name__ + ":" + str(error))
            trace.emit("run.stopped", {"reason": row["execution_stop"]}, role="system")
            stop = True
        row["tools"] = {k: v for k, v in tool_metrics.items() if k != "reads"}
        row["seconds"] = time.monotonic() - episode_start
        with sessions() as s:
            calls = list(s.scalars(select(ModelCall).where(ModelCall.run_id == episode_id)))
            for role in ("agent", "user", "judge", "auxiliary"):
                rc = [c for c in calls if c.details.get("role") == role]
                row["roles"][role] = dict(
                    known_tokens=sum(c.usage or 0 for c in rc),
                    unknown_reserved=sum(c.reserved for c in rc if c.usage is None),
                    http_requests=len(rc),
                    model_wait_seconds=sum(c.details.get("model_wait_seconds", 0) for c in rc),
                    input_tokens=sum(
                        c.details.get("usage_details", {}).get("prompt_tokens", 0) for c in rc
                    ),
                    output_tokens=sum(
                        c.details.get("usage_details", {}).get("completion_tokens", 0) for c in rc
                    ),
                )
        ledger.finish_episode(
            episode_id,
            "STOPPED" if stop else "COMPLETED",
            stop_batch=stop,
            complete_batch=index == len(rows) - 1,
        )
        export(directory, rows)
        if stop:
            for remaining in rows[index + 1 :]:
                remaining["execution_stop"] = "batch_hard_stopped"
            break
    export(directory, rows)
    sessions.kw["bind"].dispose()
    return rows
