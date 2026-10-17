import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from aftercare.agent.context import assemble_messages
from aftercare.agent.instructions import BUSINESS_INSTRUCTIONS
from aftercare.agent.tools import ALLOWED


class BusinessBoundary(AgentMiddleware):
    def __init__(self, service, principal, conversation, profile="full"):
        self.service, self.principal, self.conversation = service, principal, conversation
        self.profile = profile
        self.invalid_attempts = 0
        self.tool_attempts = 0
        self.read_retries = 0

    def wrap_model_call(self, request, handler):
        if self.invalid_attempts >= 2:
            return AIMessage(content="工具参数连续校验失败，已停止自动处理，请补充信息或转人工。")
        tools = [t for t in request.tools if getattr(t, "name", None) in ALLOWED]
        snapshot = self.service.snapshot(self.principal, self.conversation)
        humans = [m for m in request.messages if isinstance(m, HumanMessage)]
        users = [m for m in snapshot["messages"] if m["role"] == "user"]
        if humans and users and humans[-1].id != users[-1]["id"]:
            return AIMessage(content="旧方案已废弃，正在处理新诉求。")
        messages = request.messages
        starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        if self.profile == "full" and len(starts) > 4:
            messages = messages[starts[-4] :]
        if self.profile == "full":
            messages = assemble_messages(messages)
        text = (
            BUSINESS_INSTRUCTIONS
            + "有效状态："
            + json.dumps(
                {
                    "case": {
                        "facts": {
                            key: {"value": fact.get("value")}
                            for key, fact in snapshot.get("case", {}).get("facts", {}).items()
                        }
                        if self.profile == "full"
                        else {}
                    },
                    "intent_revision": snapshot["revision"],
                    "current_user_message_id": users[-1]["id"] if users else None,
                },
                ensure_ascii=False,
            )
        )
        return handler(
            request.override(
                tools=tools, messages=messages, system_message=SystemMessage(content=text)
            )
        )

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        self.tool_attempts += 1
        if self.tool_attempts > 24:
            raise RuntimeError("TOOL_CALL_LIMIT")
        if name not in ALLOWED:
            with self.service.sessions.begin() as s:
                self.service._conversation(s, self.principal, self.conversation)
                self.service.event(s, self.conversation, "forbidden_tool_attempt", {"tool": name})
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "TOOL_FORBIDDEN",
                        "retryable": False,
                        "user_message": "此工具不可用",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        try:
            request.tool.args_schema.model_validate(request.tool_call["args"])
        except Exception:
            self.invalid_attempts += 1
            with self.service.sessions.begin() as session:
                self.service._conversation(session, self.principal, self.conversation)
                self.service.event(
                    session, self.conversation, "invalid_tool_attempt", {"tool": name}
                )
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "INVALID_TOOL_ARGUMENTS",
                        "retryable": False,
                        "user_message": "工具参数不符合约定",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        try:
            result = handler(request)
            reads = {
                "list_orders",
                "get_order",
                "get_inventory",
                "search_policies",
                "get_operation",
            }
            while name in reads and self.profile == "full":
                try:
                    payload = json.loads(str(result.content))
                except (ValueError, AttributeError):
                    break
                if not payload.get("retryable"):
                    break
                if self.read_retries >= 2:
                    payload["retryable"] = False
                    return ToolMessage(
                        content=json.dumps(payload),
                        name=name,
                        tool_call_id=request.tool_call["id"],
                        status="error",
                    )
                import time

                self.read_retries += 1
                time.sleep(0.05 * self.read_retries)
                result = handler(request)
            return result
        except Exception as e:
            # Parameter validation may occur before our function. Preserve call/result pairing.
            from pydantic import ValidationError

            if not isinstance(e, ValidationError):
                raise
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "INVALID_TOOL_ARGUMENTS",
                        "retryable": False,
                        "user_message": "工具参数不符合约定",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
