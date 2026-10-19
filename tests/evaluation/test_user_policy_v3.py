"""New candidate policy only; the first-run v2 transcript and score stay frozen."""

import pytest

from evaluation.evaluator.user_policy_v2 import matches as frozen_matches

ACTUAL = (
    "白色 L 码的 T 恤目前库存只有 1 件，而您需要换货 2 件。"
    "请问您希望如何处理这 1 件的缺口？请告诉我您的选择。"
)


def test_actual_stock_gap_question_without_frozen_keywords():
    from evaluation.evaluator.user_policy_v3 import matches

    step = {"on": "clarification", "when": "stock_choice_question"}
    assert not frozen_matches(step, "clarification", ACTUAL)
    assert matches(step, "clarification", ACTUAL)


@pytest.mark.parametrize(
    "text",
    [
        "库存只有 1 件，您需要换货 1 件，请问是否办理？",
        "库存只有 2 件，您需要换货 1 件，请问是否办理？",
        "库存只有 1 件，您需要换货 2 件。",
        "您想换几件？",
    ],
)
def test_no_hidden_reply_without_actual_shortage_choice(text):
    from evaluation.evaluator.user_policy_v3 import matches

    assert not matches(
        {"on": "clarification", "when": "stock_choice_question"}, "clarification", text
    )
