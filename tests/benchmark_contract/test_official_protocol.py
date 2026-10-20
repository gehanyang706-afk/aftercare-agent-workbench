"""Run in the isolated benchmark environment. Synthetic fixture, no task answers."""

import json

import pytest

pytest.importorskip("tau2")
from litellm import ModelResponse
from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import MultiToolMessage, ToolMessage, UserMessage
from tau2.data_model.tasks import Task
from tau2.domains.retail.environment import get_environment
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.user.user_simulator import UserSimulator

from evaluation.benchmarks.tau_retail.adapter import create_agent
from evaluation.benchmarks.tau_retail.model_bridge import official_bridge, role_at_boundary


def wire(text=None, calls=None, usage=None):
    return ModelResponse(
        model="fixture",
        choices=[
            {
                "index": 0,
                "finish_reason": "tool_calls" if calls else "stop",
                "message": {"role": "assistant", "content": text, "tool_calls": calls},
            }
        ],
        usage=usage or {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    )


def call(cid, name, args):
    return {
        "id": cid,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def test_baseline_exact_payload_equivalence_and_input_canary():
    env = get_environment()
    kwargs = dict(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        llm="fixture",
        llm_args={"num_retries": 0, "max_tokens": 1024},
    )
    baseline = LLMAgent(**kwargs)
    candidate = create_agent(
        **kwargs,
        task={"answer": "ORACLE_CANARY"},
        hidden_goal="HIDDEN_CANARY",
        environment={"db": "DB_CANARY"},
    )
    captured = []

    def completion(**kw):
        captured.append(kw)
        return wire("hello")

    with official_bridge(completion):
        for agent in (baseline, candidate):
            agent.generate_next_message(
                UserMessage(role="user", content="hi"), agent.get_init_state()
            )
    assert captured[0] == captured[1]
    assert "CANARY" not in json.dumps(captured)
    assert not hasattr(candidate, "task") and not hasattr(candidate, "environment")


def test_official_orchestrator_executes_once_read_multi_write_error_stop():
    env = get_environment()
    user_id = next(iter(env.tools.db.users))
    args = dict(
        user_id=user_id,
        address1="1 Synthetic St",
        address2="",
        city="Test",
        state="CA",
        country="USA",
        zip="12345",
    )
    task = Task(
        id="SYNTHETIC_PROTOCOL",
        user_scenario={"instructions": "Please update my address; yes I confirm."},
        evaluation_criteria={
            "actions": [dict(action_id="write", name="modify_user_address", arguments=args)],
            "communicate_info": ["address updated"],
        },
    )
    agent = create_agent(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        llm="fixture",
        llm_args={"num_retries": 0, "max_tokens": 1024},
    )
    user = UserSimulator(
        llm="fixture",
        instructions="Synthetic protocol user",
        llm_args={"num_retries": 0, "max_tokens": 1024},
    )
    agent_calls = 0
    roles = []
    requests = []

    def completion(**kw):
        nonlocal agent_calls
        role = role_at_boundary()
        roles.append(role)
        requests.append(kw)
        if role == "user":
            return wire("###STOP###" if agent_calls >= 4 else "Yes, please update my address.")
        agent_calls += 1
        if agent_calls == 1:
            return wire(
                calls=[
                    call("read1", "calculate", {"expression": "2+2"}),
                    call("read2", "calculate", {"expression": "3+3"}),
                ]
            )
        if agent_calls == 2:
            return wire(calls=[call("write1", "modify_user_address", args)])
        if agent_calls == 3:
            return wire(calls=[call("bad1", "get_user_details", {"user_id": "not-a-user"})])
        return wire("address updated")

    with official_bridge(completion):
        simulation = Orchestrator(
            domain="retail",
            agent=agent,
            user=user,
            environment=env,
            task=task,
            max_steps=20,
            max_errors=5,
            seed=17,
        ).run()
        reward = evaluate_simulation(simulation, task, EvaluationType.ALL, False, "retail")
    assert reward.reward == 1
    assert roles.count("agent") == 4 and roles.count("user") == 2
    results = [m for m in simulation.messages if isinstance(m, ToolMessage)]
    assert sorted(m.id for m in results) == ["bad1", "read1", "read2", "write1"]
    assert len([m for m in results if m.id == "write1"]) == 1
    assert all(r["num_retries"] == 0 for r in requests)


def test_out_of_order_multi_result_pairs_by_id_and_empty_text():
    env = get_environment()
    agent = create_agent(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        llm="fixture",
        llm_args={"num_retries": 0},
    )
    state = agent.get_init_state()
    seq = iter(
        [
            wire(
                calls=[
                    call("a", "calculate", {"expression": "1"}),
                    call("b", "calculate", {"expression": "2"}),
                ]
            ),
            wire(""),
        ]
    )
    with official_bridge(lambda **kw: next(seq)):
        first, state = agent.generate_next_message(UserMessage(role="user", content="hello"), state)
        result, state = agent.generate_next_message(
            MultiToolMessage(
                role="tool",
                tool_messages=[
                    ToolMessage(role="tool", id="b", content="2", requestor="assistant"),
                    ToolMessage(role="tool", id="a", content="1", requestor="assistant"),
                ],
            ),
            state,
        )
    assert result.content == ""
    assert [m.id for m in state.messages if isinstance(m, ToolMessage)] == ["b", "a"]
