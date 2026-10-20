"""Offline-first entry. Installing the official benchmark never starts a model run."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from aftercare.harness.contracts import canonical, digest
from aftercare.llm.experiment_scope import plan_hash
from evaluation.benchmarks.tau_retail.source_guard import ROOT, source_fingerprint, upstream


def configure():
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    os.environ["LITELLM_TELEMETRY"] = "False"
    os.environ["LLM_CACHE_ENABLED"] = "false"
    os.environ["USE_LANGFUSE"] = "false"
    sys.path.insert(0, str(upstream() / "src"))


def make_plan():
    from aftercare.offline import install_offline_guard

    install_offline_guard()
    configure()
    from tau2.agent.llm_agent import LLMAgent
    from tau2.domains.retail.environment import get_environment
    from tau2.user.user_simulator import UserSimulator

    from evaluation.benchmarks.tau_retail.source_guard import load_train_tasks

    pool = json.loads(
        (ROOT / "evaluation/manifests/benchmark-v1/development-pool.json").read_text()
    )
    ids = pool["calibration"]
    tasks = load_train_tasks(ids)
    basis = sorted({b.value for t in tasks for b in t.evaluation_criteria.reward_basis})
    env = get_environment()
    tools = [t.openai_schema for t in env.get_tools()]
    samples = []
    for task in tasks:
        agent = LLMAgent(tools=env.get_tools(), domain_policy=env.get_policy(), llm="not-called")
        user = UserSimulator(llm="not-called", instructions=str(task.user_scenario))
        for role, system, schema, cap in (
            ("agent", agent.system_prompt, tools, 1024),
            ("user", user.system_prompt, [], 512),
        ):
            payload = dict(
                messages=[
                    dict(role="system", content=system),
                    dict(role="user", content="Visible protocol sample"),
                ],
                tools=schema,
                model="qwen3.5-plus-2026-02-15",
                max_tokens=cap,
                enable_thinking=False,
            )
            size = len(canonical(payload).encode())
            samples.append(
                dict(
                    task_id=task.id,
                    role=role,
                    payload_bytes=size,
                    initial_reservation_bound=size + 2048 + cap,
                    simulated_20_messages_2k_each_bound=size + 40000 + 2048 + cap,
                )
            )

    def role(name):
        agent = name == "agent"
        return dict(
            enabled=True,
            provider="dashscope",
            region="beijing",
            exact_model="qwen3.5-plus-2026-02-15",
            thinking=False,
            temperature=0,
            output_cap=1024 if agent else 512,
            request_cap=24 if agent else 16,
            batch_request_cap=96 if agent else 64,
            episode_token_cap=200000 if agent else 100000,
            batch_token_cap=800000 if agent else 400000,
            request_seconds=60,
            seed=20261020,
        )

    needs_judge = [
        t.id
        for t in tasks
        if t.evaluation_criteria.nl_assertions
        and any(b.value == "NL_ASSERTION" for b in t.evaluation_criteria.reward_basis)
    ]
    judge = dict(
        role("user"),
        output_cap=1024,
        request_cap=1,
        batch_request_cap=len(needs_judge) * 2,
        episode_token_cap=100000,
        batch_token_cap=100000 * len(needs_judge) * 2,
        task_ids=needs_judge,
        enabled=bool(needs_judge),
    )
    roles = {
        "agent": role("agent"),
        "user": role("user"),
        "judge": judge,
        "auxiliary": {"enabled": False},
    }
    from random import Random

    random = Random(20261020)
    episodes = []
    for task_id in ids:
        variants = ["official_tc", "harness_full_history"]
        random.shuffle(variants)
        episodes.extend(dict(task_id=task_id, variant=v) for v in variants)
    lock = json.loads((ROOT / "benchmarks/tau_retail/upstream.lock.json").read_text())
    import platform
    from importlib.metadata import version

    versions = {
        name: version(name) for name in ("litellm", "pydantic", "httpx", "psycopg", "sqlalchemy")
    }
    versions["python"] = platform.python_version()
    plan = dict(
        run_id="retail-calibration-v2",
        batch_id="retail-calibration-v2",
        experiment_version="benchmark-v1",
        environment_versions=versions,
        stage="calibration",
        status="pending_human_approval",
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        source_tree_hash=source_fingerprint(),
        upstream_commit=lock["commit"],
        dependency_lock_hash=hashlib.sha256(
            (ROOT / "benchmarks/tau_retail/requirements.lock").read_bytes()
        ).hexdigest(),
        split="train",
        task_ids=ids,
        task_content_hash=digest([t.model_dump(mode="json") for t in tasks]),
        variants=["official_tc", "harness_full_history"],
        trial=0,
        order_seed=20261020,
        episodes=episodes,
        roles=roles,
        total_token_cap=1200000 + judge["batch_token_cap"],
        request_cap=160 + judge["batch_request_cap"],
        episode_token_cap=400000 if needs_judge else 300000,
        episode_request_cap=41 if needs_judge else 40,
        episode_seconds=600,
        wall_clock_seconds=2400,
        max_steps=80,
        max_errors=10,
        request_seconds=60,
        consecutive_request_cap=24,
        concurrency=1,
        retries=0,
        model_switch=False,
        additional_paid_cost_cap_cny=0,
        auto_review=False,
        evaluation_type="ALL",
        reward_basis=basis,
        judge_required_tasks=needs_judge,
        judge_configuration_note=(
            "Official default GPT-4.1 judge replaced by explicitly approved "
            "exact Qwen for both variants; prompts, criteria and reward unchanged."
        ),
        seed_support=(
            "Forward identical seed for agent/user/judge; API behavior uncalibrated, "
            "no determinism guarantee."
        ),
        scorer_hash=lock["source_hashes"]["src/tau2/evaluator/evaluator.py"],
        policy_hash=digest(env.get_policy()),
        tools_hash=digest(tools),
        user_policy_hash=digest(user.system_prompt.split(str(tasks[-1].user_scenario))[0]),
        diagnostic_version="retail-trace-v2",
        account_confirmation_id="retail-calibration-v2-account",
        offline_request_samples=samples,
        estimated_tokens_range={
            "agent_per_episode": [20000, 140000],
            "user_per_episode": [10000, 60000],
            "judge_per_required_episode": [2000, 20000],
            "batch": [124000, 840000],
        },
        estimate_note=(
            "Unvalidated full-episode range; v1 stopped after four HTTP requests "
            "(12233 tokens), with no completed episode. Cold payload bounds do not "
            "predict full trajectories; reservation protections remain unchanged."
        ),
        supersedes="retail-calibration-v1 (protocol-stopped; original records preserved)",
        protocol_policy=(
            "Preserve mixed content and tool_calls; official default environment routing; "
            "record native response before protocol validation. No scorer changes."
        ),
        ordinary_failure="continue_fixed_remaining",
        hard_stop=[
            "auth",
            "quota",
            "protocol",
            "safety",
            "unknown_usage",
            "any_persistent_budget_or_deadline",
        ],
        restart="read_only_reconcile",
        freeze_note=(
            "New post-repair batch: no v1 authorization or remaining batch budget transfers. "
            "Fresh plan-bound account confirmation and explicit agent/user/judge approval "
            "are required; no approval/account file generated."
        ),
    )
    plan["plan_sha256"] = plan_hash(plan)
    return plan


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "contract-test"):
        sub.add_parser(name).add_argument("--offline", action="store_true", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--stage", choices=["calibration"], required=True)
    plan.add_argument("--dry-run", action="store_true", required=True)
    plan.add_argument("--output")
    run = sub.add_parser("run")
    run.add_argument("--manifest", required=True)
    run.add_argument("--approval")
    run.add_argument("--account")
    run.add_argument("--execute", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        root = upstream()
        print(
            json.dumps(
                {
                    "upstream": str(root),
                    "verified": True,
                    "source_tree_hash": source_fingerprint(),
                    "real_requests": 0,
                },
                indent=2,
            )
        )
    elif args.command == "contract-test":
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "src") + os.pathsep + str(upstream() / "src"),
            LITELLM_LOCAL_MODEL_COST_MAP="True",
        )
        result = subprocess.run(
            [
                str(ROOT / "runtime/benchmark-deps/venv/bin/python"),
                "-m",
                "pytest",
                "tests/benchmark_contract",
                "-q",
            ],
            cwd=ROOT,
            env=env,
        )
        raise SystemExit(result.returncode)
    elif args.command == "plan":
        value = make_plan()
        if args.output:
            Path(args.output).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(value, ensure_ascii=False, indent=2))
    elif args.command == "run":
        from evaluation.benchmarks.tau_retail.runner import execute, preflight

        value = json.loads(Path(args.manifest).read_text())
        approval = json.loads(Path(args.approval).read_text()) if args.approval else None
        account = json.loads(Path(args.account).read_text()) if args.account else None
        if not args.execute or approval is None or account is None:
            print(json.dumps(preflight(value, approval, account), indent=2))
            return
        configure()
        execute(value, approval, account)
    else:
        root = ROOT / "runtime/retail-runs" / args.run_id
        if Path(args.run_id).name != args.run_id:
            raise ValueError("INVALID_RUN_ID")
        from evaluation.benchmarks.tau_retail.runner import export

        rows = [json.loads(line) for line in (root / "episodes.jsonl").read_text().splitlines()]
        print(json.dumps(export(root, rows), indent=2))


if __name__ == "__main__":
    main()
