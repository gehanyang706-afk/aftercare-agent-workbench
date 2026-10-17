"""Fixed order baseline: same offline intent model + deterministic read/preview/commit gates."""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select

from aftercare.agent.tools import toolset
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.scripted import ScriptedModel
from aftercare.repositories.models import Message
from aftercare.retrieval.engine import PolicySearch


def run_workflow(service, principal, conversation, message_id, resume, decision):
    snapshot = service.snapshot(principal, conversation)
    tools = {t.name: t for t in toolset(service, principal, conversation, PolicySearch())}
    if resume:
        candidates = [
            p for p in snapshot["previews"] if p["status"] in {"CONFIRMED", "COMMITTED", "REJECTED"}
        ]
        if decision == "reject" or not candidates:
            return {"messages": [AIMessage(content="方案已拒绝，未执行。")]}
        preview = candidates[-1]
        result = json.loads(tools["commit_action"].invoke({"preview_id": preview["id"]}))
        if result.get("error_code") == "WRITE_RESULT_UNKNOWN":
            result = json.loads(tools["get_operation"].invoke({"preview_id": preview["id"]}))
        return {"messages": [AIMessage(content=json.dumps(result, ensure_ascii=False))]}
    with service.sessions() as s:
        msg = s.get(Message, message_id)
        if not msg or msg.conversation_id != conversation:
            raise ValueError("MESSAGE_NOT_FOUND")
        humans = list(
            s.scalars(
                select(Message)
                .where(Message.conversation_id == conversation, Message.role == "user")
                .order_by(Message.revision)
            )
        )
    # Intent extraction is the same exact offline model; its function schema remains unchanged.
    model = ScriptedModel(
        ledger=BudgetLedger(service.sessions),
        conversation_id=conversation,
        run_id=f"workflow:{conversation}:{snapshot['revision']}",
    )
    messages = [
        SystemMessage(
            content="有效状态："
            + json.dumps(
                {"case": snapshot["case"], "intent_revision": snapshot["revision"]},
                ensure_ascii=False,
            )
        )
    ]
    messages.extend(HumanMessage(content=h.text, id=h.id) for h in humans)
    model = model.bind_tools(list(tools.values()))
    stages = {
        "update_case": 0,
        "list_orders": 0,
        "get_order": 1,
        "search_policies": 1,
        "get_inventory": 2,
        "preview_action": 3,
        "request_handoff": 3,
        "commit_action": 4,
    }
    stage = 0
    for _ in range(8):
        response = model.invoke(messages)
        messages.append(response)
        if not response.tool_calls:
            return {"messages": messages}
        for call in response.tool_calls:
            name = call["name"]
            next_stage = stages.get(name, -1)
            if next_stage < stage:
                return {"messages": [AIMessage(content="固定流程阶段不能回退，请重新说明诉求。")]}
            stage = next_stage
            if name == "commit_action":
                return {"messages": messages, "__interrupt__": ["trusted-confirmation-required"]}
            result = tools[name].invoke(call["args"])
            messages.append(ToolMessage(content=result, name=name, tool_call_id=call["id"]))
    raise RuntimeError("FIXED_WORKFLOW_LIMIT")
