"""Only actual branch replies are disclosed. No hidden goals enter product commands."""

import re

VERSION = "script-user-v2"


def matches(step, kind, text):
    if step.get("on") != kind:
        return False
    condition = step.get("when")
    if condition is None:
        return True
    if condition == "quantity_question":
        return bool(re.search(r"几件|多少件|件数|数量[^。\n]{0,30}[？?]", text))
    if condition == "stock_choice_question":
        return bool(re.search(r"库存不足|缺货", text) and re.search(r"[？?]|请选择|请.*选择", text))
    raise ValueError("UNKNOWN_USER_BRANCH_CONDITION")
