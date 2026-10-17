"""Only these schemas reach the model. Identity is captured by the server."""

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select

from aftercare.domain.contracts import ActionInput, BusinessError
from aftercare.repositories.models import Policy
from aftercare.services.business import new_id
from aftercare.services.case_state import CaseUpdate, update_case

ALLOWED = frozenset(
    {
        "list_orders",
        "get_order",
        "get_inventory",
        "search_policies",
        "update_case",
        "preview_action",
        "commit_action",
        "get_operation",
        "request_handoff",
    }
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListOrders(Strict):
    status_filter: str | None = None


class GetOrder(Strict):
    order_id: str


class GetInventory(Strict):
    product_id: str
    variant_filters: dict | None = None


class SearchPolicies(Strict):
    query: str
    action: str = "all"


class Commit(Strict):
    preview_id: str


class GetOperation(Strict):
    operation_id: str | None = None
    preview_id: str | None = None


class Handoff(Strict):
    reason_code: str
    summary: str


def toolset(service, principal, conversation, search, retrieval_profile="bm25"):
    def policies(query, action="all"):
        snapshot = service.snapshot(principal, conversation)
        current = snapshot.get("case", {}).get("facts", {}).get("current_order_id", {}).get("value")
        qualification = "v1"
        if current:
            qualification = service.get_order(principal, current)["policy_version"]
        with service.sessions() as s:
            flow = s.scalar(select(Policy).where(Policy.current.is_(True))).id
        return search.search(
            query,
            action,
            profile=retrieval_profile,
            qualification_version=qualification,
            flow_version=flow,
            now=service.clock(),
        )

    routes = {
        "list_orders": (
            ListOrders,
            lambda **kw: service.list_orders(principal, **kw),
            "列出当前用户订单",
        ),
        "get_order": (
            GetOrder,
            lambda **kw: service.get_order(principal, **kw),
            "查看当前用户一个订单",
        ),
        "get_inventory": (GetInventory, service.inventory, "查询实时商品变体库存"),
        "search_policies": (SearchPolicies, policies, "查询适用政策及来源条款"),
        "update_case": (
            CaseUpdate,
            lambda **kw: update_case(service, principal, conversation, CaseUpdate(**kw)),
            "更新有效诉求，必须关联当前用户消息",
        ),
        "preview_action": (
            ActionInput,
            lambda **kw: service.preview(principal, conversation, ActionInput(**kw)),
            "校验资格并生成只读预览，不能代表授权",
        ),
        "commit_action": (
            Commit,
            lambda **kw: service.commit(principal, **kw),
            "仅提交已通过可信API确认的预览",
        ),
        "get_operation": (
            GetOperation,
            lambda **kw: service.get_operation(principal, **kw),
            "按原操作或预览查询真实回执",
        ),
        "request_handoff": (
            Handoff,
            lambda **kw: service.handoff(principal, conversation, **kw),
            "创建本地待人工工单",
        ),
    }
    tools = []
    for name, (schema, handler, description) in routes.items():

        def invoke(_schema=schema, _handler=handler, _name=name, **kwargs):
            trace = new_id("trace")
            try:
                parsed = _schema.model_validate(kwargs)
                data = _handler(**parsed.model_dump())
                result = {
                    "ok": True,
                    "data": data,
                    "error_code": None,
                    "retryable": False,
                    "user_message": "操作完成" if _name == "commit_action" else "查询或处理完成",
                    "trace_id": trace,
                }
            except (BusinessError, ValidationError) as e:
                code = e.code if isinstance(e, BusinessError) else "INVALID_TOOL_ARGUMENTS"
                result = {
                    "ok": False,
                    "data": None,
                    "error_code": code,
                    "retryable": getattr(e, "retryable", False),
                    "user_message": getattr(e, "message", "工具参数不符合约定"),
                    "trace_id": trace,
                }
            except Exception:
                # A failed transport/transaction may have committed. Never retry a write blindly.
                result = {
                    "ok": False,
                    "data": None,
                    "error_code": "WRITE_RESULT_UNKNOWN"
                    if _name == "commit_action"
                    else "SERVICE_UNAVAILABLE",
                    "retryable": False,
                    "user_message": "处理异常，请查询原回执或稍后重试；当前不宣称成功",
                    "trace_id": trace,
                }
            with service.sessions.begin() as s:
                service._conversation(s, principal, conversation)
                service.event(s, conversation, "tool_result", {"tool": _name, "result": result})
            return json.dumps(result, ensure_ascii=False)

        tools.append(
            StructuredTool.from_function(
                invoke, name=name, description=description, args_schema=schema
            )
        )
    return tools
