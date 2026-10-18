"""Bounded requested-count recognition; no purchase/stock arithmetic or defaults."""

import re

VERSION = "quantity-evidence-v2"
_NUM = r"\d+|[零〇一二两三四五六七八九十百千万]+"
_TOKEN = re.compile(
    rf"(?<![\d零〇一二两三四五六七八九十百千万负第])"
    rf"(?:数量\s*[：:]?\s*(?P<bare>{_NUM})(?![\d零〇一二两三四五六七八九十百千万])\s*件?|(?P<units>{_NUM})\s*件)"
)
_CN = {c: n for n, c in enumerate("一二三四五六七八九十", 1)} | {"两": 2}
_UNCERTAIN = re.compile(
    r"还是|或者|或是|也许|大概|可能|例如|比如|至少|至多|左右|一两件|几件|多少件|数量.*(?:不确定|没想好|不知道)"
)
_NEGATIVE = re.compile(
    r"不是|不要|不需要|不想|不打算|不准备|不用|不再|不退|不换|不申请|不办理|无需|别退|别换"
)
_HISTORY = re.compile(r"买了?|购买|收到|库存|订单(?:里|中)?(?:有|共|总共)|原数量|购入|下单")
_REQUEST = re.compile(r"申请|本次|其中|全部|退|换")


def quantity_details(text):
    """Return (count, invalidates_previous_count); retained/factual counts are not requests."""
    if _UNCERTAIN.search(text) or re.search(r"\d+\s*[-~～至到]\s*\d+\s*件", text):
        return None, True
    values = set()
    invalid = bool(re.search(r"另(?:外)?一件", text) and "保留" not in text)
    for match in _TOKEN.finditer(text):
        left = re.split(r"[，,。；;！？?!\n]", text[: match.start()])[-1]
        right = re.split(r"[，,。；;！？?!\n]", text[match.end() :])[0]
        # 'another one', ordinal references and retained items are not requested units.
        if re.search(r"另(?:外)?$|第$|保留[^，。]{0,8}$", left) or re.match(
            r"\s*(?:都)?保留", right
        ):
            continue
        if re.match(r"\s*(?:中(?:的)?|里(?:的)?)", right):
            continue
        if _NEGATIVE.search(left) or re.match(
            r"\s*(?:都)?(?:不要|不想|不打算|不准备|不再|不|别|无需)(?:退|换|申请|办理)", right
        ):
            invalid = True
            continue
        if match.group("bare") and re.search(r"订单\s*$|原\s*$", left):
            continue
        history = list(_HISTORY.finditer(left))
        request = list(_REQUEST.finditer(left))
        if history and (not request or history[-1].start() > request[-1].start()):
            continue
        token = match.group("bare") or match.group("units")
        count = int(token) if token.isascii() and token.isdigit() else _CN.get(token)
        if count is None or count < 1:
            invalid = True
            continue
        values.add(count)
    # Conflicting counts require a reply, never choose the first/last automatically.
    if len(values) != 1:
        return None, invalid or len(values) > 1 or bool(_NEGATIVE.search(text)) or bool(
            re.search(r"全部|所有|都退|都换", text)
        )
    return next(iter(values)), False


def explicit_quantity(text):
    return quantity_details(text)[0]
