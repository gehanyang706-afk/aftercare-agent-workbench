"""Small public development set. These are retrieval questions, not business holdout tasks."""

from datetime import UTC, datetime

QUESTIONS = [
    ("钱付了还没发货能取消吗", "cancel", "cancel@v1#rule"),
    ("收到十天了能换大一码吗", "exchange", "exchange-window@v1#rule"),
    ("七天内退货可以吗", "return", "return-window@v1#rule"),
    ("定制的衣服穿过能退吗", "return", "unused-return@v1#rule"),
    ("换鞋是不是必须同价同系列", "exchange", "same-family@v1#rule"),
    ("退货邮费谁出多少钱", "return", "return-fee@v1#rule"),
    ("换货运费多少", "exchange", "exchange-fee@v1#rule"),
    ("大码没库存能直接给我退吗", "exchange", "fallback@v1#rule"),
    ("同一件衣服能同时申请退和换吗", "return", "quantity-return@v1#rule"),
    ("取消后钱是否马上到账", "cancel", "refund@v1#rule"),
    ("换货申请撤回库存怎么释放", "exchange", "release@v1#rule"),
    ("质量有争议怎么办", "all", "dispute@v1#rule"),
]


def evaluate_profiles(engine, profiles):
    result = {}
    for profile in profiles:
        rows = []
        for query, action, expected in QUESTIONS:
            references = [
                c["policy_ref"]
                for c in engine.search(
                    query, action, profile, now=datetime(2026, 10, 17, tzinfo=UTC)
                )
            ]
            rows.append(
                {
                    "query": query,
                    "expected": expected,
                    "top5": references,
                    "hit": expected in references,
                }
            )
        result[profile] = {
            "hits": sum(r["hit"] for r in rows),
            "questions": len(rows),
            "rows": rows,
        }
    return {"kind": "public-retrieval-dev", "profiles": result, "corpus_hash": engine.corpus_hash}
