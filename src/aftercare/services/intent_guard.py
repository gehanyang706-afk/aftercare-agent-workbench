"""Conservative user evidence, independent of model-written case facts.

Unsupported phrasing asks for clarification; purchase/stock data are never evidence.
This is a safety recognizer, not a general natural language intent classifier.
"""

import re

from sqlalchemy import select

from aftercare.domain.rules import require
from aftercare.repositories.models import Message


def explicit_quantity(text):
    numbers = set()
    for match in re.finditer(r"数量\s*(\d+)|(?<!\d)(\d+)\s*件", text):
        prefix = text[: match.start()]
        if re.search(r"(?:买了?|购买|收到|库存|订单数量|原数量)[^，。；;!?？]{0,12}$", prefix):
            continue
        numbers.add(int(match.group(1) or match.group(2)))
    return next(iter(numbers)) if len(numbers) == 1 else None


def user_evidence(messages):
    evidence = {}
    for msg in messages:
        text = msg.text if hasattr(msg, "text") else msg["text"]
        source = msg.id if hasattr(msg, "text") else msg["id"]
        orders = re.findall(r"\bS\d{4}\b", text, re.I)
        if orders:
            order = orders[-1].upper()
            if order != evidence.get("order_id"):
                evidence = {"order_id": order}
        action = (
            "return"
            if "退" in text
            else "exchange"
            if "换" in text and "不换了" not in text
            else "cancel"
            if "取消" in text
            else None
        )
        withdrawal = bool(
            re.search(
                r"不换了|不要换|不退了|不要退|不要取消|不取消了|不要办理|暂不办理|暂不提交|停止办理",
                text,
            )
        )
        if withdrawal:
            evidence.pop("action", None)
        elif action:
            evidence["action"] = action
        qty = explicit_quantity(text)
        if qty is not None:
            evidence["quantity"] = qty
            evidence["quantity_source"] = source
    return evidence


def validate_case_for_preview(session, conv, action):
    case = conv.case or {}
    facts = case.get("facts", {})
    require(
        case.get("intent_revision") == conv.revision,
        "CASE_UPDATE_REQUIRED",
        "本轮诉求尚未建立；请 update_case 后重试 preview_action（不重试提交）。",
    )

    def value(key):
        return facts.get(key, {}).get("value")

    require(
        value("current_order_id") == action.order_id and value("intent") == action.action,
        "CASE_ACTION_MISMATCH",
        "预览与有效订单/动作不一致，请核对最新用户消息并更新诉求。",
    )
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id, Message.role == "user")
            .order_by(Message.revision)
        )
    )
    evidence = user_evidence(messages)
    require(
        evidence.get("order_id") == action.order_id and evidence.get("action") == action.action,
        "USER_INTENT_CLARIFICATION_REQUIRED",
        "无法从用户表达确认该订单和动作，请先澄清。",
    )
    if action.action != "cancel":
        require(value("current_line_id") in (None, action.line_id), "CASE_ACTION_MISMATCH")
        quantity = evidence.get("quantity")
        require(
            quantity is not None,
            "QUANTITY_CLARIFICATION_REQUIRED",
            "请询问本次申请几件；购买数量和库存不能代替用户回答。",
        )
        require(
            quantity == action.quantity
            and (value("constraints") or {}).get("quantity") == quantity,
            "CASE_QUANTITY_MISMATCH",
            "预览数量必须与用户明确表达及有效诉求一致。",
        )
