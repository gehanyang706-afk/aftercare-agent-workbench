"""Conservative user evidence, independent of model-written case facts.

Unsupported phrasing asks for clarification; purchase/stock data are never evidence.
This is a safety recognizer, not a general natural language intent classifier.
"""

import re

from sqlalchemy import select

from aftercare.domain.rules import require
from aftercare.repositories.models import Message
from aftercare.services.quantity_evidence import explicit_quantity as explicit_quantity
from aftercare.services.quantity_evidence import quantity_details


def user_evidence(messages):
    evidence = {}
    for msg in messages:
        text = msg.text if hasattr(msg, "text") else msg["text"]
        source = msg.id if hasattr(msg, "text") else msg["id"]
        orders = re.findall(r"\bS\d{4}\b", text, re.I)
        if len(set(o.upper() for o in orders)) > 1:
            evidence = {}
            continue
        if orders:
            order = orders[-1].upper()
            if order != evidence.get("order_id"):
                evidence = {"order_id": order}
        previous_action = evidence.get("action")
        qty, quantity_unknown = quantity_details(text)
        positive = re.sub(
            r"(?:不(?:是|需要|要|想|打算|准备|用)?(?:再)?|别|无需)(?:换货?|退货?|取消)(?:了)?",
            "",
            text,
        )
        actions = {
            value
            for token, value in (("退", "return"), ("换", "exchange"), ("取消", "cancel"))
            if token in positive
        }
        withdrawal = bool(re.search(r"不要办理|暂不办理|暂不提交|停止办理", text))
        # Multiple alternatives or a question about options are not an action selection.
        ambiguous = len(actions) != 1 or bool(re.search(r"或者|还是|都可以|能否|可以吗", positive))
        if not ambiguous and not withdrawal:
            evidence["action"] = next(iter(actions))
        elif actions or withdrawal:
            evidence.pop("action", None)
        elif qty is None and not re.search(
            r"大一码|小一码|原码|白色|黑色|尺码|未使用|没穿过|另(?:外)?一件.*保留", text
        ):
            evidence.pop("action", None)
        if len(actions) > 1:
            qty, quantity_unknown = None, True
        changed_action_without_count = (
            qty is None
            and previous_action is not None
            and evidence.get("action") not in (None, previous_action)
            and bool(re.search(r"(?:不(?:想|要|再|打算|准备)?|别)(?:换|退)", text))
        )
        if quantity_unknown or changed_action_without_count:
            evidence.pop("quantity", None)
            evidence.pop("quantity_source", None)
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
