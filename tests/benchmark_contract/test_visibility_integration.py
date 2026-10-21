import copy
import json

import pytest

pytest.importorskip("tau2")
from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import ToolMessage, UserMessage
from tau2.domains.retail.environment import get_environment

from aftercare.harness.contracts import digest
from evaluation.benchmarks.tau_retail.adapter import create_agent
from evaluation.benchmarks.tau_retail.model_bridge import CompletionBridge, official_bridge
from evaluation.benchmarks.tau_retail.tool_visibility import ALWAYS, rule_hash
from evaluation.benchmarks.tau_retail.trace import Trace


class Ledger:
    def __init__(self):
        self.reserved = []
        self.settled = []

    def reserve(self, *args):
        self.reserved.append(args)
        return str(len(self.reserved))

    def settle(self, *args):
        self.settled.append(args)
        return True


def response(tool_name=None):
    return {
        "model": "fixture",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if tool_name else "stop",
                "message": {
                    "role": "assistant",
                    "content": "Checking." if tool_name else "Please confirm the next step.",
                    "tool_calls": [
                        {
                            "id": "hidden",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": "{}"},
                        }
                    ]
                    if tool_name
                    else None,
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


def scope(catalog, variant="tool_visibility_v1"):
    return dict(
        catalog=catalog, catalog_hash=digest(catalog), rule_hash=rule_hash(), variant=variant
    )


def test_actual_transport_receives_subset_and_environment_keeps_full_catalog(tmp_path, monkeypatch):
    env = get_environment()
    catalog = [t.openai_schema for t in env.get_tools()]
    trace = Trace(tmp_path, "synthetic", "synthetic:0", "tool_visibility_v1")
    ledger = Ledger()
    sent = []

    def transport(payload, timeout):
        sent.append(copy.deepcopy(payload))
        return response()

    cfg = dict(enabled=True, exact_model="fixture", output_cap=1024, request_seconds=1, seed=17)
    bridge = CompletionBridge(
        ledger, "r", "e", {"agent": cfg}, transport, trace, 10**12, scope(catalog)
    )
    args = dict(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        llm="fixture",
        llm_args={"num_retries": 0, "max_tokens": 1024},
    )
    candidate = create_agent(**args, tool_visibility=True, trace=trace)
    from tau2.utils import llm_utils

    original_generate = llm_utils.generate
    passed_objects = []

    def generated(**kwargs):
        passed_objects.append(kwargs["tools"])
        return original_generate(**kwargs)

    monkeypatch.setattr(llm_utils, "generate", generated)
    with official_bridge(bridge):
        candidate.set_seed(17)
        _, state = candidate.generate_next_message(
            UserMessage(role="user", content="Order A; I say it is pending."),
            candidate.get_init_state(),
        )
    assert {t["function"]["name"] for t in sent[0]["tools"]} == ALWAYS
    assert len(env.get_tools()) == len(catalog) and candidate.tools is args["tools"]
    assert [t.openai_schema for t in env.get_tools()] == catalog
    assert all(any(t is original for original in args["tools"]) for t in passed_objects[0])
    assert len(ledger.reserved) == len(ledger.settled) == 1
    # Same visible initial input baseline keeps all original schemas; no prompt rewrite.
    baseline = LLMAgent(**args)
    captured = []
    with official_bridge(
        lambda **kw: captured.append(kw) or __import__("litellm").ModelResponse(**response())
    ):
        baseline.set_seed(17)
        baseline.generate_next_message(
            UserMessage(role="user", content="Order A; I say it is pending."),
            baseline.get_init_state(),
        )
    assert captured[0]["messages"] == sent[0]["messages"]
    assert captured[0]["tools"] == catalog
    assert candidate.policy.policy_id == "full_history"


@pytest.mark.parametrize(
    "change", ["schema", "catalog_hash", "rule_hash", "variant", "baseline_subset"]
)
def test_gateway_rejects_scope_drift_before_reservation(monkeypatch, tmp_path, change):
    from evaluation.benchmarks.tau_retail import model_bridge

    monkeypatch.setattr(model_bridge, "role_at_boundary", lambda: "agent")
    catalog = [t.openai_schema for t in get_environment().get_tools()]
    cfg = dict(enabled=True, exact_model="fixture", output_cap=1024, request_seconds=1)
    ts = copy.deepcopy(catalog)
    sc = scope(catalog)
    if change == "schema":
        ts[0]["function"]["description"] = "mutated"
    elif change == "variant":
        sc["variant"] = "unapproved"
    elif change == "baseline_subset":
        sc["variant"] = "official_tc"
        ts = ts[:-1]
    else:
        sc[change] = "bad"
    ledger = Ledger()
    sent = []
    with pytest.raises(ValueError):
        bridge = CompletionBridge(
            ledger,
            "r",
            "e",
            {"agent": cfg},
            lambda *x: sent.append(x),
            Trace(tmp_path, "r", "e", "synthetic"),
            10**12,
            sc,
        )
        bridge(model="fixture", messages=[], tools=ts, max_tokens=1024, num_retries=0)
    assert not ledger.reserved and not sent


def test_hidden_and_outside_catalog_proposals_are_diagnostics_not_retries(monkeypatch, tmp_path):
    from evaluation.benchmarks.tau_retail import model_bridge

    monkeypatch.setattr(model_bridge, "role_at_boundary", lambda: "agent")
    catalog = [t.openai_schema for t in get_environment().get_tools()]
    visible = [t for t in catalog if t["function"]["name"] in ALWAYS]
    ledger = Ledger()
    cfg = dict(enabled=True, exact_model="fixture", output_cap=1024, request_seconds=1)
    trace = Trace(tmp_path, "r", "e", "tool_visibility_v1")
    for name in ["cancel_pending_order", "unknown_tool"]:
        bridge = CompletionBridge(
            ledger,
            "r",
            "e",
            {"agent": cfg},
            lambda *x, name=name: response(name),
            trace,
            10**12,
            scope(catalog),
        )
        result = bridge(model="fixture", messages=[], tools=visible, max_tokens=1024, num_retries=0)
        assert result.choices[0].message.tool_calls[0].function.name == name
    assert len(ledger.reserved) == 2
    events = [json.loads(x) for x in trace.path.read_text().splitlines()]
    signals = [
        json.loads(__import__("pathlib").Path(x["payload_ref"]).read_text())
        for x in events
        if x["event_type"] == "tools.unexposed_proposal"
    ]
    assert [x["kind"] for x in signals] == ["official_but_hidden", "outside_catalog"]


def test_user_and_judge_not_routed_and_unknown_usage_keeps_original_pause_semantics(
    monkeypatch, tmp_path
):
    from evaluation.benchmarks.tau_retail import model_bridge

    catalog = [t.openai_schema for t in get_environment().get_tools()]
    ledger = Ledger()
    sent = []
    cfg = dict(enabled=True, exact_model="fixture", output_cap=1024, request_seconds=1)
    trace = Trace(tmp_path, "r", "e", "tool_visibility_v1")
    for role in ["user", "judge"]:
        monkeypatch.setattr(model_bridge, "role_at_boundary", lambda role=role: role)
        bridge = CompletionBridge(
            ledger,
            "r",
            "e",
            {role: cfg},
            lambda p, t: sent.append(p) or response(),
            trace,
            10**12,
            scope(catalog),
        )
        bridge(
            model="fixture",
            messages=[{"role": "system", "content": "ROLE_PRIVATE_CANARY"}],
            max_tokens=1024,
            num_retries=0,
        )
        assert "tools" not in sent[-1]
        with pytest.raises(ValueError, match="AGENT_ONLY"):
            bridge(model="fixture", messages=[], tools=catalog, max_tokens=1024, num_retries=0)
    monkeypatch.setattr(model_bridge, "role_at_boundary", lambda: "agent")
    raw = response()
    raw.pop("usage")
    bridge = CompletionBridge(
        ledger, "r", "e", {"agent": cfg}, lambda *x: raw, trace, 10**12, scope(catalog)
    )
    with pytest.raises(ValueError, match="USAGE_UNKNOWN"):
        bridge(model="fixture", messages=[], tools=catalog, max_tokens=1024, num_retries=0)
    assert ledger.settled[-1][1] is None


@pytest.mark.parametrize("path", ["queried", "hidden_then_unknown"])
def test_official_orchestrator_query_opens_write_and_executes_only_once(tmp_path, path):
    from tau2.data_model.tasks import Task
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    from tau2.orchestrator.orchestrator import Orchestrator
    from tau2.user.user_simulator import UserSimulator

    from evaluation.benchmarks.tau_retail.model_bridge import role_at_boundary
    from evaluation.benchmarks.tau_retail.trace import attach_environment_trace

    env = get_environment()
    oid = next(o.order_id for o in env.tools.db.orders.values() if o.status == "pending")
    args = {"order_id": oid, "reason": "ordered by mistake"}
    task = Task(
        id="SYNTHETIC_VISIBILITY",
        user_scenario={"instructions": "Cancel the order, explicitly confirm."},
        evaluation_criteria={
            "reward_basis": ["DB"],
            "actions": [{"action_id": "cancel", "name": "cancel_pending_order", "arguments": args}],
        },
    )
    trace = Trace(tmp_path, "synthetic", "synthetic:0", "tool_visibility_v1")
    metrics = attach_environment_trace(env, trace)
    catalog = [t.openai_schema for t in env.get_tools()]
    ledger = Ledger()
    agent_count = 0
    sent = []

    def transport(payload, timeout):
        nonlocal agent_count
        who = role_at_boundary()
        if who == "user":
            raw = response()
            raw["choices"][0]["message"]["content"] = (
                "###STOP###"
                if agent_count >= 3
                else "Cancel this order for ordered by mistake; yes I confirm."
            )
            return raw
        agent_count += 1
        sent.append(copy.deepcopy(payload))
        if agent_count == 3:
            raw = response()
            raw["choices"][0]["message"]["content"] = (
                "Cancellation requested successfully; the original payment refund follows policy."
            )
            return raw
        chosen = "get_order_details" if agent_count == 1 else "cancel_pending_order"
        if path == "hidden_then_unknown":
            chosen = "cancel_pending_order" if agent_count == 1 else "unknown_tool"
        raw = response(chosen)
        raw["choices"][0]["message"]["tool_calls"][0]["id"] = str(agent_count)
        arguments = {"order_id": oid} if chosen == "get_order_details" else args
        raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
            arguments
        )
        return raw

    cfg = dict(enabled=True, exact_model="fixture", output_cap=1024, request_seconds=1, seed=17)
    bridge = CompletionBridge(
        ledger, "r", "e", {"agent": cfg, "user": cfg}, transport, trace, 10**12, scope(catalog)
    )
    kwargs = dict(llm="fixture", llm_args={"num_retries": 0, "max_tokens": 1024})
    agent = create_agent(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        tool_visibility=True,
        trace=trace,
        **kwargs,
    )
    user = UserSimulator(instructions="Synthetic confirmed cancellation.", **kwargs)
    with official_bridge(bridge):
        simulation = Orchestrator(
            domain="retail",
            agent=agent,
            user=user,
            environment=env,
            task=task,
            max_steps=10,
            seed=17,
        ).run()
        reward = evaluate_simulation(simulation, task, EvaluationType.ALL, False, "retail")
    assert reward.reward == 1 and env.tools.db.orders[oid].status == "cancelled"
    assert metrics["executed"] == 2
    assert metrics["mutation_sequence"] == (1 if path == "queried" else 2)
    if path == "hidden_then_unknown":
        errors = [m for m in simulation.messages if isinstance(m, ToolMessage) and m.error]
        assert len(errors) == 1 and "unknown_tool" in errors[0].content
        events = [json.loads(x) for x in trace.path.read_text().splitlines()]
        assert sum(x["event_type"] == "tools.unexposed_proposal" for x in events) == 2
    assert "cancel_pending_order" not in {t["function"]["name"] for t in sent[0]["tools"]}
    assert "cancel_pending_order" in {t["function"]["name"] for t in sent[1]["tools"]}
    assert len(ledger.reserved) == 5
