"""Offline development runner. Product child has no access to evaluator fields via protocol."""

import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from datetime import timedelta

from sqlalchemy import select, text

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.repositories.database import session_factory
from aftercare.repositories.models import (
    Application,
    Approval,
    Base,
    Event,
    Handoff,
    Inventory,
    ModelCall,
    Operation,
    Order,
    OrderLine,
    Preview,
    Refund,
    Variant,
)
from aftercare.services.business import BusinessService, columns
from aftercare.services.demo import seed, ship_order
from evaluation.evaluator.grader import grade
from evaluation.evaluator.user import ScriptedUser
from evaluation.schema.scenario import Scenario

DEV = PROJECT_ROOT / "evaluation/dev/scenarios.jsonl"


def load_dev():
    cases = [Scenario.model_validate_json(line) for line in DEV.read_text().splitlines() if line]
    if len({c.scenario_id for c in cases}) != len(cases) or any(c.split != "dev" for c in cases):
        raise ValueError("Invalid development IDs/split")
    from evaluation.evaluator.grader import ASSERTIONS

    if any(set(c.expected_state_invariants) - ASSERTIONS for c in cases):
        raise ValueError("Unknown oracle keys")
    return cases


def validate():
    cases = load_dev()
    return {
        "count": len(cases),
        "families": len({c.family_id for c in cases}),
        "categories": {
            kind: sum(c.category == kind for c in cases)
            for kind in ("basic", "revision", "boundary", "recovery")
        },
        "sha256": hashlib.sha256(DEV.read_bytes()).hexdigest(),
        "valid": True,
    }


def reset(sessions, scenario):
    # Exact dedicated test DB only. Never truncates the user-facing demo DB.
    if sessions.kw["bind"].url.database != "aftercare_test":
        raise ValueError("EVALUATION_REQUIRES_AFTERCARE_TEST")
    names = ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
    with sessions.begin() as s:
        s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    seed(sessions, lambda: scenario.clock)
    tables = {
        "orders": Order,
        "order_lines": OrderLine,
        "inventory": Inventory,
        "variants": Variant,
    }
    with sessions.begin() as s:
        for change in scenario.fixture_changes:
            cls = tables[change["table"]]
            row = s.get(cls, change["id"])
            if row is None:
                raise ValueError("Unknown fixture ID")
            for key, value in change["fields"].items():
                if key == "delivered_age_hours" and cls is Order:
                    row.delivered_at = scenario.clock - timedelta(hours=value)
                elif key in cls.__table__.columns and key not in {
                    "id",
                    "variant_id",
                    "customer_id",
                }:
                    setattr(row, key, value)
                else:
                    raise ValueError("Unsupported fixture field")


def observe(sessions, communications, error=None):
    with sessions() as s:

        def rows(cls):
            return [columns(row) for row in s.scalars(select(cls))]

        return {
            "orders": {r["id"]: r for r in rows(Order)},
            "inventory": {r["variant_id"]: r for r in rows(Inventory)},
            "operations": rows(Operation),
            "applications": rows(Application),
            "refunds": rows(Refund),
            "handoffs": rows(Handoff),
            "previews": rows(Preview),
            "approvals": rows(Approval),
            "events": rows(Event),
            "model_calls": rows(ModelCall),
            "communications": communications,
            "system_error": error,
        }


class Actor:
    def __init__(self, log):
        self.log = log.open("w")
        self.child = subprocess.Popen(
            [sys.executable, "-m", "evaluation.evaluator.actor"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            bufsize=1,
        )

    def invoke(self, command):
        self.child.stdin.write(json.dumps(command) + "\n")
        self.child.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.child.stdout, selectors.EVENT_READ)
            if not selector.select(180):
                self.close()
                raise TimeoutError("ACTOR_HARD_DEADLINE")
        line = self.child.stdout.readline()
        if not line:
            raise RuntimeError("ACTOR_EXITED")
        return json.loads(line)

    def close(self):
        self.child.terminate()
        try:
            self.child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait()
        self.log.close()


def run_case(scenario, settings, sessions, profile, output, actor_factory=Actor):
    reset(sessions, scenario)
    service = BusinessService(sessions, lambda: scenario.clock)
    principal = scenario.user_known_facts.get("principal", "alice")
    conversation = service.create_conversation(principal)
    base = {
        "database_url": settings.database_url.get_secret_value(),
        "clock": scenario.clock.isoformat(),
        "principal": principal,
        "conversation": conversation,
        "profile": profile,
    }
    actor = actor_factory(output / f"{scenario.scenario_id}.stderr.log")
    visible, used_faults, steps = [], set(), list(scenario.user_behavior_policy)
    error, turns = None, 0
    pending_message = scenario.initial_user_message
    decision = "reject"

    def faults(trigger):
        for i, fault in enumerate(scenario.fault_schedule):
            if i in used_faults or fault.get("trigger", "after_preview") != trigger:
                continue
            used_faults.add(i)
            kind = fault["kind"]
            if kind == "ship_order":
                ship_order(sessions, fault.get("order_id", "S1001"))
            elif kind == "inventory_zero":
                with sessions.begin() as s:
                    stock = s.get(Inventory, fault.get("variant_id", "tee-white-L"))
                    stock.available, stock.version = 0, stock.version + 1
            elif kind in {"lost_response", "before_commit"}:
                base["commit_fault"] = kind
            elif kind == "restart":
                actor.close()
                # New process + persistent checkpoint; next command resumes same thread.
                actor.__init__(output / f"{scenario.scenario_id}.restart.stderr.log")
            else:
                raise ValueError("Unsupported scheduled fault")

    try:
        faults("before_first_turn")
        for turns in range(1, scenario.max_turns + 1):
            if pending_message is not None:
                msg = service.append_message(
                    principal, conversation, pending_message, f"eval-{turns}"
                )
                result = actor.invoke({**base, "message_id": msg["id"]})
                pending_message = None
            else:
                result = actor.invoke({**base, "resume": True, "decision": decision})
            visible.extend(result.get("communications", []))
            if not result["ok"]:
                error = result["error"]
                break
            snapshot = service.snapshot(principal, conversation)
            previews = [p for p in snapshot["previews"] if p["status"] == "PENDING"]
            kind = (
                "preview"
                if previews
                else "after_commit"
                if snapshot["status"] == "COMPLETED"
                else "clarification"
            )
            if previews:
                preview = previews[-1]
                visible.append(json.dumps(preview["payload"], ensure_ascii=False))
                faults("after_preview")
            index = next((i for i, step in enumerate(steps) if step.get("on") == kind), None)
            step = steps.pop(index) if index is not None else None
            if step and step.get("say"):
                pending_message = step["say"]
                continue
            if previews:
                if step and step.get("repeat_message"):
                    with sessions() as s:
                        from aftercare.repositories.models import Message

                        original = s.scalar(
                            select(Message)
                            .where(Message.conversation_id == conversation, Message.role == "user")
                            .order_by(Message.revision.desc())
                        )
                    for _ in range(step["repeat_message"]):
                        duplicate = service.append_message(
                            principal, conversation, original.text, original.client_message_id
                        )
                        if duplicate["id"] != original.id:
                            raise RuntimeError("MESSAGE_DEDUP_FAILED")
                decision = (
                    "approve"
                    if not step or step.get("decision", "accept") == "accept"
                    else "reject"
                )
                # User policy checks disclosed action against their goal before approving.
                if not ScriptedUser(scenario.hidden_user_goal).accepts(preview["payload"]):
                    decision = "reject"
                try:
                    for _ in range(1 + (step or {}).get("repeat_confirmation", 0)):
                        service.confirm(principal, preview["id"], decision == "approve")
                except Exception as e:
                    visible.append("可信确认被拒绝：" + str(e))
                    break
                continue
            break
        else:
            error = "SCENARIO_TURN_LIMIT"
    except Exception as e:
        error = type(e).__name__ + ":" + str(e)
    finally:
        actor.close()
    observed = observe(sessions, visible, error)
    result = grade(scenario, observed)
    return {
        "scenario_id": scenario.scenario_id,
        "category": scenario.category,
        "profile": profile,
        "turns": turns,
        "result": result,
        "observed": observed,
    }


def run_development(profile="full", limit=None):
    if profile not in {"full", "retrieval", "react-full-policy", "fixed-workflow"}:
        raise ValueError("Unknown profile")
    settings = Settings(
        _env_file=None,
        database_url=os.getenv(
            "AFTERCARE_TEST_DATABASE_URL",
            "postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test",
        ),
    )
    sessions = session_factory(settings)
    if sessions.kw["bind"].url.database != "aftercare_test":
        raise ValueError("EVALUATION_REQUIRES_AFTERCARE_TEST")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output = PROJECT_ROOT / "runtime/phase-05" / f"dev-{profile}-{stamp}"
    output.mkdir(parents=True)
    cases = load_dev()[:limit]
    results = []
    for scenario in cases:
        start = time.monotonic()
        result = run_case(scenario, settings, sessions, profile, output)
        result["latency_seconds"] = round(time.monotonic() - start, 3)
        (output / f"{scenario.scenario_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, default=str, indent=2)
        )
        results.append(result)
        print(
            f"{len(results)}/{len(cases)} {scenario.scenario_id}: {result['result']['success']}",
            file=sys.stderr,
            flush=True,
        )
    tasks = len(results)
    passed = sum(r["result"]["success"] for r in results)
    eligible = [
        r
        for r, c in zip(results, cases, strict=True)
        if c.expected_state_invariants.get("operation_count", 0) > 0
    ]
    summary = {
        "provider": "scripted",
        "profile": profile,
        "real_api_calls": 0,
        "attempted_tasks": tasks,
        "conversations": tasks,
        "passed_tasks": passed,
        "eligible_completed": sum(r["result"]["success"] for r in eligible),
        "eligible_tasks": len(eligible),
        "categories": {
            k: {
                "passed": sum(r["result"]["success"] for r in results if r["category"] == k),
                "attempted": sum(r["category"] == k for r in results),
            }
            for k in ("basic", "revision", "boundary", "recovery")
        },
        "process_failure_tasks": sum(not r["result"]["process_ok"] for r in results),
        "state_failure_tasks": sum(not r["result"]["state_ok"] for r in results),
        "communication_failure_tasks": sum(not r["result"]["communication_ok"] for r in results),
        "system_error_tasks": sum(bool(r["result"]["system_error"]) for r in results),
        "synthetic_model_calls": sum(len(r["observed"]["model_calls"]) for r in results),
        "synthetic_usage": sum(
            c["usage"] or 0 for r in results for c in r["observed"]["model_calls"]
        ),
        "unknown_usage_calls": sum(
            c["usage"] is None for r in results for c in r["observed"]["model_calls"]
        ),
        "latency_seconds": [r["latency_seconds"] for r in results],
        "raw_directory": str(output),
        "limitations": [
            "规则脚本只验证工程链路，不代表真实语言理解质量",
            "每题导出后重置隔离 test DB；仅允许离线模拟",
            "未运行 holdout 或真实模型",
            "非重复稳定性或统计显著性实验",
        ],
        "tasks": [
            {k: r[k] for k in ("scenario_id", "category", "result", "latency_seconds")}
            for r in results
        ],
    }
    from evaluation.evaluator.metrics import metrics
    from evaluation.evaluator.report import render

    summary["metrics"] = metrics(results, cases)

    render(summary, output)
    sessions.kw["bind"].dispose()
    return summary
