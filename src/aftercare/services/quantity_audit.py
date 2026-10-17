"""Conservative assertion diagnostic; never a grading or authorization rule."""

import re

from aftercare.services.intent_guard import explicit_quantity


def quantity_claims(text, evidence):
    # A question/example is not an assertion of a user requirement.
    claims = []
    for sentence in re.split(r"[。！\n]", text):
        if any(w in sentence for w in ("？", "?", "例如", "请问", "几件", "多少件")):
            continue
        qty = explicit_quantity(sentence)
        if qty is not None and re.search(
            r"(您|你|用户).{0,18}(申请|要求|希望|想|要|换|退)", sentence
        ):
            if qty != evidence.get("quantity"):
                claims.append(
                    {
                        "text": sentence,
                        "quantity": qty,
                        "trusted_quantity": evidence.get("quantity"),
                    }
                )
    return claims
