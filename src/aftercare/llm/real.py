"""Budgeted Qwen chat protocol adapter. Only the approved pilot gateway can send."""

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from aftercare.agent.tools import ALLOWED
from aftercare.domain.rules import require


def wire_messages(messages):
    rows = []
    for message in messages:
        roles = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
        require(message.type in roles, "WIRE_ROLE_INVALID")
        row = {"role": roles[message.type], "content": message.content or ""}
        if message.type == "ai" and message.tool_calls:
            row["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"], ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.type == "tool":
            row["tool_call_id"] = message.tool_call_id
        rows.append(row)
    return rows


class BudgetedBailianModel(BaseChatModel):
    # Provider-qualified harness key; exact wire model is always enforced by the gateway.
    model_name: str = "aftercare:approved-bailian"
    gateway: Any = Field(exclude=True)
    bound_tools: list = Field(default_factory=list, exclude=True)
    profile: dict = Field(default_factory=lambda: {"tool_calling": True, "max_input_tokens": 32768})

    @property
    def _llm_type(self):
        return "aftercare"

    def get_num_tokens(self, text):
        return len(text.encode())

    def bind_tools(self, tools, **kwargs):
        converted = [convert_to_openai_tool(tool) for tool in tools]
        require(
            {t["function"]["name"] for t in converted} == ALLOWED, "NINE_TOOL_WHITELIST_REQUIRED"
        )
        return self.model_copy(update={"bound_tools": converted})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        result, usage = self.gateway.invoke(wire_messages(messages), self.bound_tools)
        try:
            return self._decode(result, usage)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            require(False, "PROVIDER_PROTOCOL_MESSAGE")

    def _decode(self, result, usage):
        data = result["data"]
        choices = data.get("choices", [])
        require(len(choices) == 1, "PROVIDER_PROTOCOL_CHOICES")
        choice = choices[0]
        require(choice.get("finish_reason") in {"stop", "tool_calls"}, "PROVIDER_PROTOCOL_FINISH")
        message = choice.get("message", {})
        calls = []
        try:
            for call in message.get("tool_calls") or []:
                require(call.get("type") == "function" and call.get("id"), "PROVIDER_PROTOCOL_TOOL")
                args = json.loads(call["function"]["arguments"])
                require(isinstance(args, dict), "PROVIDER_PROTOCOL_ARGUMENTS")
                name = call["function"]["name"]
                if name not in ALLOWED or set(args) & {
                    "approved",
                    "principal",
                    "customer_id",
                    "user_id",
                    "amount_fen",
                    "refund_fen",
                }:
                    self.gateway.security_attempt(name, args)
                calls.append({"name": name, "args": args, "id": call["id"], "type": "tool_call"})
        except (ValueError, KeyError, TypeError):
            require(False, "PROVIDER_PROTOCOL_TOOL_JSON")
        ai = AIMessage(
            content=message.get("content") or "",
            tool_calls=calls,
            usage_metadata={
                "input_tokens": usage[0],
                "output_tokens": usage[1],
                "total_tokens": usage[2],
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])
