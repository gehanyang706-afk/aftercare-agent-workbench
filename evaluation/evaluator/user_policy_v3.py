"""Explicitly selected v3; adds bounded stock arithmetic, never changes frozen v2."""

import re

from evaluation.evaluator.user_policy_v2 import matches as previous_matches

VERSION = "script-user-v3"


def matches(step, kind, text):
    if previous_matches(step, kind, text):
        return True
    if step.get("on") != kind or step.get("when") != "stock_choice_question":
        return False
    if not re.search(r"[？?]|请选择|请.*选择", text):
        return False
    stock = re.search(r"库存(?:目前|现有|仅有|只有|仅|有|为|\s)*([0-9]+)\s*件", text)
    requested = re.search(r"您(?:本次)?(?:需要|申请)(?:换货|退货|更换)?\s*([0-9]+)\s*件", text)
    return bool(stock and requested and int(stock[1]) < int(requested[1]))
