"""Single Deep Agent; HITL checkpoint is separate from committed business receipts."""

from contextlib import contextmanager

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from aftercare.agent.middleware import BusinessBoundary
from aftercare.agent.tools import toolset
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel
from aftercare.repositories.models import Message
from aftercare.retrieval.engine import PolicySearch

EXCLUDED = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "task", "write_todos"}
)


def factory(
    service, principal, conversation, checkpointer, run_id=None, model=None, profile="full"
):
    model = model or ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conversation,
        run_id=run_id or f"{conversation}:{service.snapshot(principal, conversation)['revision']}",
    )
    register_harness_profile(
        "aftercare:scripted",
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools=EXCLUDED,
            excluded_middleware=frozenset({"SummarizationMiddleware"}),
        ),
    )
    search = PolicySearch()
    tools = toolset(
        service,
        principal,
        conversation,
        search,
        retrieval_profile="full-policy" if profile == "react-full-policy" else "bm25",
    )
    graph = create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        middleware=[BusinessBoundary(service, principal, conversation, profile)],
        interrupt_on={"commit_action": {"allowed_decisions": ["approve", "reject"]}},
        checkpointer=checkpointer,
        name="aftercare-main",
    )
    return graph, model


@contextmanager
def agent_runtime(
    settings, service, principal, conversation, run_id=None, model=None, profile="full"
):
    url = service.sessions.kw["bind"].url
    conn_string = url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://"
    )
    with PostgresSaver.from_conn_string(conn_string) as saver:
        graph, bound_model = factory(
            service, principal, conversation, saver, run_id, model, profile
        )
        yield graph, bound_model


def setup_checkpoints(settings):
    from aftercare.repositories.database import session_factory

    sessions = session_factory(settings)
    url = (
        sessions.kw["bind"]
        .url.render_as_string(hide_password=False)
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    sessions.kw["bind"].dispose()


def run_turn(
    settings,
    service,
    principal,
    conversation,
    message_id=None,
    resume=False,
    run_id=None,
    profile="full",
    decision="approve",
):
    if profile == "fixed-workflow":
        from aftercare.agent.workflow import run_workflow

        return run_workflow(service, principal, conversation, message_id, resume, decision)
    if profile not in {"full", "retrieval", "react-full-policy"}:
        raise ValueError("UNKNOWN_AGENT_PROFILE")
    config = {"configurable": {"thread_id": conversation}, "recursion_limit": 96}
    with agent_runtime(
        settings, service, principal, conversation, run_id=run_id, profile=profile
    ) as (graph, model):
        state = graph.get_state(config)
        if state.next and not resume:
            last_human = next(
                (
                    m
                    for m in reversed(state.values.get("messages", []))
                    if isinstance(m, HumanMessage)
                ),
                None,
            )
            if last_human is not None and last_human.id == message_id:
                interrupts = [i for task in state.tasks for i in task.interrupts]
                if interrupts:
                    return {**state.values, "__interrupt__": interrupts}
                return graph.invoke(None, config)
            # Reject the old interrupt only after the new message invalidates its business preview.
            graph.invoke(
                Command(
                    resume={
                        "decisions": [{"type": "reject", "message": "用户已更新诉求，旧方案失效"}]
                    }
                ),
                config,
            )
        if resume:
            if not state.next:
                return state.values
            result = graph.invoke(Command(resume={"decisions": [{"type": decision}]}), config)
        else:
            with service.sessions() as s:
                msg = s.get(Message, message_id)
                if not msg or msg.conversation_id != conversation:
                    raise ValueError("MESSAGE_NOT_FOUND")
                human = HumanMessage(
                    content=msg.text, id=msg.id, additional_kwargs={"intent_revision": msg.revision}
                )
            result = graph.invoke({"messages": [human]}, config)
        return result
