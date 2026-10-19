"""A bounded explicit stop is an application event, not a new action selection."""

import re


def explicit_pause(text):
    # Conditional, quoted, negated, and mixed-order/action messages do not match.
    return bool(
        re.fullmatch(
            r"\s*(?:保留[一二两三四五六七八九十\d]+件)?(?:等待补货|等补货)?"
            r"[，,。；;\s]*(?:暂不提交|暂不办理|停止办理|不要办理)[。！!\s]*",
            text,
        )
    )


def pause_message(service, principal, conversation, message_id):
    from aftercare.domain.rules import require
    from aftercare.repositories.models import Message

    with service.sessions.begin() as s:
        conv = service._conversation(s, principal, conversation)
        message = s.get(Message, message_id)
        require(
            message is not None and message.conversation_id == conv.id and message.role == "user",
            "MESSAGE_NOT_FOUND",
        )
        if not explicit_pause(message.text):
            return False
        require(message.revision == conv.revision, "INTENT_CHANGED")
        return True
