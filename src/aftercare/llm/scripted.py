"""Offline protocol model. Rule-based planner is explicitly not an LLM quality claim."""

import json
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from aftercare.domain.rules import require
from aftercare.services.business import new_id


def call(name, args):
    return {"name": name, "args": args, "id": new_id("tc"), "type": "tool_call"}


def response(text="", calls=None):
    return AIMessage(content=text, tool_calls=calls or [])


def offline_plan(messages):
    human_index = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    human = messages[human_index]
    text = str(human.content)
    context = json.loads(str(messages[0].content).split("有效状态：", 1)[-1])
    facts = context.get("case", {}).get("facts", {})
    if not facts:
        # Full-history baselines reconstruct from visible prior update results, not server memory.
        for prior in messages[1:human_index]:
            if isinstance(prior, ToolMessage) and prior.name == "update_case":
                try:
                    update = json.loads(str(prior.content))
                    if update.get("ok"):
                        facts = update["data"].get("facts", {})
                except (ValueError, TypeError):
                    pass

    def value(k, default=None):
        return facts.get(k, {}).get("value", default)

    results = {}
    for msg in messages[human_index + 1 :]:
        if isinstance(msg, ToolMessage):
            try:
                results[msg.name] = json.loads(str(msg.content))
            except (ValueError, TypeError):
                results[msg.name] = {"ok": False, "error_code": "USER_REJECTED"}
    # A rejected HITL call is protocol feedback, never a successful business receipt.
    if "get_operation" in results and results["get_operation"].get("ok"):
        return response(
            "查询原回执：" + json.dumps(results["get_operation"]["data"], ensure_ascii=False)
        )
    if "commit_action" in results:
        item = results["commit_action"]
        if item.get("ok"):
            receipt = item["data"]
            return response(
                f"已提交：{receipt['result']}。操作编号 {receipt['operation_id']}。"
                f"{receipt['notice']}"
            )
        if item.get("error_code") == "WRITE_RESULT_UNKNOWN" and "get_operation" not in results:
            return response(
                calls=[
                    call("get_operation", {"preview_id": results["preview_action"]["data"]["id"]})
                ]
            )
        if item.get("error_code") == "WRITE_RESULT_UNKNOWN":
            return response("尚未查到原提交回执，当前不宣称成功。请稍后查询或转人工处理。")
        return response("旧方案未执行。请继续说明当前诉求，必要时重新生成预览。")
    if "request_handoff" in results:
        return response("已创建人工接管工单；状态 HANDOFF_PENDING，尚未判定责任。")
    for name, item in results.items():
        if not item.get("ok"):
            code = item.get("error_code", "INVALID_TOOL_RESULT")
            if name == "preview_action" and code in [
                "OUT_OF_STOCK",
                "OUTSIDE_POLICY_WINDOW",
                "ITEM_INELIGIBLE",
            ]:
                return response(
                    calls=[
                        call(
                            "request_handoff",
                            {
                                "reason_code": code,
                                "summary": "当前自动办理受限，请人工复核；无自动退货或退款。",
                            },
                        )
                    ]
                )
            return response(f"暂未执行：{code}。请核对对象或补充信息后重新办理。")
    if "preview_action" in results:
        return response(
            calls=[call("commit_action", {"preview_id": results["preview_action"]["data"]["id"]})]
        )
    order_match = re.search(r"\bS\d{4}\b", text, re.I)
    order = order_match.group().upper() if order_match else value("current_order_id")
    intent = (
        "cancel"
        if any(w in text for w in ["取消订单", "取消这", "取消S", "取消s"])
        else "return"
        if "退" in text
        else "exchange"
        if "换" in text
        else value("intent")
    )
    if "不换了" in text and "退" not in text:
        intent = None
    constraints = dict(value("constraints", {}))
    if order_match and value("current_order_id") and order != value("current_order_id"):
        constraints = {}
    if "大一码" in text:
        constraints = {"size_delta": 1}
    if "小一码" in text:
        constraints = {"size_delta": -1}
    if "原码" in text:
        constraints = {**constraints, "size_delta": 0}
        constraints.pop("size", None)
    size = re.search(r"\b(XXL|XL|L|M|S|40|41)\b", text, re.I)
    if size:
        constraints["size"] = size.group().upper()
        constraints.pop("size_delta", None)
    for color in ["白色", "黑色"]:
        if color in text:
            constraints["color"] = color
    if any(w in text for w in ["穿过了", "使用过", "已经穿过"]):
        constraints["unused"] = False
    quantity = re.search(r"数量\s*(\d+)|(?<!\d)(\d+)\s*件", text)
    if quantity:
        constraints["quantity"] = int(quantity.group(1) or quantity.group(2))
    if "update_case" not in results:
        changes = {"constraints": constraints}
        if order:
            changes["current_order_id"] = order
        if intent:
            changes["intent"] = intent
        return response(
            calls=[
                call(
                    "update_case",
                    {
                        "expected_revision": context["intent_revision"],
                        "source_message_id": human.id,
                        "changes": changes,
                    },
                ),
                call("list_orders", {}),
            ]
        )
    if any(w in text for w in ["质量", "破损", "投诉", "人工", "坏了"]):
        return response(
            calls=[
                call("request_handoff", {"reason_code": "QUALITY_OR_MANUAL", "summary": text[:500]})
            ]
        )
    if not order:
        orders = results.get("list_orders", {}).get("data", [])
        return response(
            "请明确订单编号和要办理的事项。可选订单：" + ", ".join(o["id"] for o in orders)
        )
    if "get_order" not in results:
        requests = [call("get_order", {"order_id": order})]
        if intent:
            requests.append(call("search_policies", {"query": text, "action": intent}))
        return response(calls=requests)
    data = results["get_order"]["data"]
    if not intent:
        return response("订单当前状态：" + data["status"] + "。请说明要取消、退货还是换货。")
    if constraints.get("unused") is False:
        return response(
            calls=[
                call(
                    "request_handoff",
                    {
                        "reason_code": "ITEM_USED",
                        "summary": "用户表示已使用，不能按普通未使用售后办理。",
                    },
                )
            ]
        )
    line = data["lines"][0] if len(data["lines"]) == 1 else None
    if intent != "cancel" and line is None:
        return response("请明确要办理的商品行和数量。")
    args = {"action": intent, "order_id": order, "reason": "用户当前诉求"}
    if intent != "cancel":
        args["quantity"] = constraints.get("quantity", 1)
        args["line_id"] = line["id"]
    if intent == "exchange":
        if "get_inventory" not in results:
            return response(
                calls=[call("get_inventory", {"product_id": line["variant"]["product_id"]})]
            )
        inventory = results["get_inventory"]["data"]
        original = line["variant"]
        desired_size = constraints.get("size")
        if desired_size is None and "size_delta" in constraints:
            sizes = (
                ["S", "M", "L", "XL", "XXL"]
                if not original["size"].isdigit()
                else [str(i) for i in range(30, 49)]
            )
            pos = sizes.index(original["size"]) + constraints["size_delta"]
            desired_size = sizes[pos] if 0 <= pos < len(sizes) else None
        if desired_size is None and "color" not in constraints:
            return response("请说明希望的尺码或颜色，例如大一码、白色 L 或黑色原码。")
        desired_size = desired_size or original["size"]
        color = constraints.get("color", original["color"])
        matches = [v for v in inventory if v["size"] == desired_size and v["color"] == color]
        if not matches:
            return response("没有匹配的同系列变体，请选择其他尺码颜色或转人工。")
        args["target_variant"] = matches[0]["id"]
    return response(calls=[call("preview_action", args)])


class ScriptedModel(BaseChatModel):
    model_name: str = "aftercare:scripted"
    ledger: Any = Field(exclude=True)
    conversation_id: str
    run_id: str
    responses: Any = Field(default=None, exclude=True)
    planner: Any = Field(default=offline_plan, exclude=True)
    shared: dict = Field(default_factory=lambda: {"calls": 0, "tool_names": []}, exclude=True)
    bound_tools: list = Field(default_factory=list, exclude=True)
    cap: int = 200000
    output_cap: int = 512
    profile: dict = Field(default_factory=lambda: {"tool_calling": True, "max_input_tokens": 32768})

    @property
    def _llm_type(self):
        return "aftercare"

    def bind_tools(self, tools, **kwargs):
        converted = [convert_to_openai_tool(t) for t in tools]
        self.shared["tool_names"] = [t["function"]["name"] for t in converted]
        return self.model_copy(update={"bound_tools": converted})

    def get_num_tokens(self, text):
        return len(text.encode("utf8"))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        payload = json.dumps(
            {
                "messages": messages_to_dict(messages),
                "tools": self.bound_tools,
                "max_tokens": self.output_cap,
            },
            ensure_ascii=False,
            default=str,
        )
        call_id = self.ledger.reserve(
            "scripted",
            self.model_name,
            "offline",
            self.conversation_id,
            self.run_id,
            len(payload.encode()) + 1024,
            self.output_cap,
            self.cap,
        )
        try:
            index = self.shared["calls"]
            self.shared["calls"] += 1
            message = (
                self.responses[index] if self.responses is not None else self.planner(messages)
            )
            message = message.model_copy(deep=True)
            message.id = None
            if self.responses is not None:
                for tool_call in message.tool_calls:
                    tool_call["id"] = new_id("tc")
            out = max(
                1,
                len(json.dumps(message.model_dump(), ensure_ascii=False, default=str).encode())
                // 4,
            )
            require(out <= self.output_cap, "MODEL_OUTPUT_CAP")
            incoming = max(1, len(payload.encode()) // 4)
            message.usage_metadata = {
                "input_tokens": incoming,
                "output_tokens": out,
                "total_tokens": incoming + out,
            }
            self.ledger.settle(call_id, incoming + out, request_id="offline-" + call_id)
        except BaseException:
            self.ledger.settle(call_id, None)
            raise
        return ChatResult(generations=[ChatGeneration(message=message)])
