from datetime import UTC, datetime

import pytest

from aftercare.retrieval.engine import PolicySearch, tokenize
from aftercare.retrieval.local import LocalModels, WeightsUnavailable


def test_corpus_versions_and_policy_facts():
    engine = PolicySearch()
    assert len(engine.chunks) == 24
    result = engine.search(
        "14天30天退货换货", action="return", limit=30, now=datetime(2026, 10, 17, tzinfo=UTC)
    )
    assert result and all(c["version"] == "v1" for c in result)
    assert "168 小时" in next(
        c["text"] for c in engine.chunks if c["policy_ref"] == "return-window@v1#rule"
    )
    assert "360 小时" in next(
        c["text"] for c in engine.chunks if c["policy_ref"] == "exchange-window@v1#rule"
    )
    assert all(
        "800 分" in next(c["text"] for c in engine.chunks if c["policy_ref"] == f"{a}-fee@v1#rule")
        for a in ["return", "exchange"]
    )
    old = engine.search(
        "退货",
        action="return",
        qualification_version="v0",
        profile="full-policy",
        now=datetime(2026, 10, 17, tzinfo=UTC),
    )
    assert any(c["version"] == "v0" for c in old)
    assert not any(c["version"] == "v1" and c["kind"] == "qualification" for c in old)


def test_chinese_tokenization_and_intact_exception():
    assert "退货" in tokenize("退货政策")
    engine = PolicySearch()
    result = engine.search("缺货直接退货", action="exchange")
    clause = next(c for c in result if c["source_id"] == "fallback")
    assert "仍需满足退货七天时效" in clause["text"]
    assert clause["content_hash"]


def test_missing_weights_are_not_semantic_success(tmp_path):
    with pytest.raises(WeightsUnavailable):
        LocalModels(tmp_path).encode(["换大一码"])


@pytest.mark.model_weights
def test_real_local_onnx_embeddings_and_reranker():
    models = LocalModels()
    vectors = models.encode(["退货政策", "换货时效"])
    assert vectors.shape == (2, 512)
    assert len(models.rerank("收到十天想换货", ["换货支持十五天", "退货支持七天"])) == 2
    with pytest.raises(ValueError, match="TOKEN_LIMIT"):
        models.encode(["退货" * 1000])


def test_pgvector_build_and_query(service):
    engine = PolicySearch(sessions=service.sessions)
    result = engine.build("bm25")
    assert result["vectors_built"] is False
    assert engine.search("退货")
