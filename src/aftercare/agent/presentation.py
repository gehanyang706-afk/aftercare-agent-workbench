"""Only application-verified outcomes become user-facing completion notices."""

import re

from langchain_core.messages import AIMessage
from sqlalchemy import select

from aftercare.repositories.models import Message, Preview, Variant
from aftercare.services.business import digest, new_id


def state_event(service, principal, conversation, graph_state, task_state, **extra):
    with service.sessions.begin() as s:
        conv = service._conversation(s, principal, conversation)
        service.event(
            s,
            conv.id,
            "runtime_state",
            {
                "revision": conv.revision,
                "graph_state": graph_state,
                "task_state": task_state,
                **extra,
            },
        )


def present(
    service,
    principal,
    conversation,
    result,
    receipt=None,
    preview_id=None,
    error=None,
    recovered=False,
):
    snap = service.snapshot(principal, conversation)
    revision = snap["revision"]
    graph_state = result.get("_graph_state") or (
        "INTERRUPTED" if result.get("__interrupt__") else "ENDED"
    )
    task = "WAITING_USER"
    stage = "clarification"
    pid = preview_id
    operation_id = None
    if receipt:
        pid = receipt["preview_id"]
        operation_id = receipt["operation_id"]
        with service.sessions() as s:
            preview = s.get(Preview, pid)
            if preview.revision != revision:
                from aftercare.domain.contracts import BusinessError

                raise BusinessError("INTENT_CHANGED")
            payload = preview.payload
            target = (
                s.get(Variant, payload["target_variant"]) if payload.get("target_variant") else None
            )
            target_text = f"，目标为 {target.color} {target.size} 码" if target else ""
        action = payload["action"]
        fee = payload["computed"]["shipping_fee_fen"]
        if action == "cancel":
            text = (
                f"订单 {receipt['order_id']} 已取消。仅记录模拟退款请求，不代表退款到账；"
                f"模拟金额 {payload['computed']['refund_fen'] / 100:.2f} 元。"
            )
        else:
            label = "换货" if action == "exchange" else "退货"
            payer = (
                "客户承担" if payload["computed"]["shipping_payer"] == "customer" else "商家承担"
            )
            text = (
                f"已提交{label}申请，数量 {payload['quantity']} 件{target_text}。"
                "仅提交售后申请，尚未退款或寄出换货；"
                f"模拟运费 {fee} 分（{fee / 100:.2f} 元），由{payer}。"
            )
        text += f"操作编号 {operation_id}。" + ("已查询原回执。" if recovered else "")
        task = "COMPLETED"
        stage = "final"
        key = "receipt:" + operation_id
    elif error:
        code = error["error_code"]
        task = "EXECUTION_UNKNOWN" if code == "WRITE_RESULT_UNKNOWN" else "FAILED"
        text = (
            "提交结果尚未确定，当前不宣称成功。请查询原操作记录或转人工。"
            if task == "EXECUTION_UNKNOWN"
            else "本次未完成提交；方案或办理条件已变化，请核对后重新办理。"
        )
        stage = "execution_unknown" if task == "EXECUTION_UNKNOWN" else "failure"
        key = f"error:{pid}:{code}:{revision}"
    elif result.get("_rejected"):
        task = "REJECTED"
        stage = "rejected"
        text = "已拒绝该方案，未提交。"
        key = "reject:" + pid
    else:
        pending = next(
            (
                p
                for p in snap["previews"]
                if p["confirmation_available"] and p["status"] == "PENDING"
            ),
            None,
        )
        if pending:
            pid = pending["id"]
            payload = pending["payload"]
            label = {"cancel": "取消整单", "return": "退货", "exchange": "换货"}[payload["action"]]
            quantity = "整单" if payload["action"] == "cancel" else f"{payload['quantity']} 件"
            target_text = (
                f"，目标为 {pending['target_label']}" if pending.get("target_label") else ""
            )
            text = (
                f"请确认订单 {payload['order_id']} 的{label}方案（{quantity}）{target_text}。"
                "当前仅生成预览，尚未提交。"
            )
            task = "WAITING_CONFIRMATION"
            stage = "preview"
            key = "preview:" + pid
        else:
            raws = [
                str(m.content) for m in result.get("messages", []) if m.type == "ai" and m.content
            ]
            raw = raws[-1] if raws else "请补充希望办理的事项。"
            parts = re.split(r"(?<=[。！？\n])", raw)
            text = "".join(
                x
                for x in parts
                if not re.search(
                    r"可信|API|commit_action|preview_action|PENDING|CONFIRMED|银行通知|账户变动|后续.*(指引|物流|通知)",
                    x,
                )
            ).strip()
            if not text or re.search(r"已.{0,4}(提交|取消|到账|退款|寄出|发货)", text):
                text = "当前尚无提交回执。请补充信息或核对待确认方案。"
            if snap["status"] == "HANDOFF_PENDING":
                task = "HANDOFF_PENDING"
                stage = "handoff"
                text = "已创建人工接管工单；尚未判定责任。"
            key = f"turn:{revision}:{digest(text)}"
    with service.sessions.begin() as s:
        conv = service._conversation(s, principal, conversation)
        if conv.revision != revision:
            from aftercare.domain.contracts import BusinessError

            raise BusinessError("INTENT_CHANGED")
        mid = "notice:" + key
        saved = s.scalar(
            select(Message).where(
                Message.conversation_id == conversation, Message.client_message_id == mid
            )
        )
        if not saved:
            saved = Message(
                id=new_id("msg"),
                conversation_id=conversation,
                client_message_id=mid,
                role="assistant",
                text=text,
                revision=revision,
                created_at=service.clock(),
            )
            s.add(saved)
            service.event(
                s,
                conversation,
                "user_notice",
                {
                    "stage": stage,
                    "revision": revision,
                    "preview_id": pid,
                    "operation_id": operation_id,
                    "text": text,
                    "notice_key": key,
                },
            )
        service.event(
            s,
            conversation,
            "runtime_state",
            {
                "revision": revision,
                "graph_state": graph_state,
                "task_state": task,
                "preview_id": pid,
                "operation_id": operation_id,
            },
        )
    return {
        **result,
        "messages": list(result.get("messages", [])) + [AIMessage(content=text)],
        "communications": [text],
        "notice_saved": True,
        "task_state": task,
        "graph_state": graph_state,
        "receipt": receipt,
        "error": error,
    }
