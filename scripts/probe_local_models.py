"""Measured CPU resource probe, never remote inference."""

import json
import resource
import sys
import time

from aftercare.config import PROJECT_ROOT
from aftercare.retrieval.local import LocalModels

start = time.monotonic()
models = LocalModels()
vectors = models.encode(["退货七天换货十五天", "收到十天想换大一码"])
embedding_seconds = time.monotonic() - start
start = time.monotonic()
scores = models.rerank("收到十天能换大一码吗", ["交付后十五天内可以换货", "退货限七天内"])
report = {
    "backend": "ONNX CPU, intra_op_threads=2",
    "embedding_first_load_and_2_texts_seconds": embedding_seconds,
    "reranker_first_load_and_2_pairs_seconds": time.monotonic() - start,
    "embedding_shape": list(vectors.shape),
    "reranker_scores": scores,
    "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    * (1 if sys.platform == "darwin" else 1024),
    "weights_bytes": sum(
        p.stat().st_size for p in (PROJECT_ROOT / "runtime/models").rglob("*") if p.is_file()
    ),
    "revisions": models.revision(),
    "remote_inference_calls": 0,
}
(PROJECT_ROOT / "docs/local-model-resource-report.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print(json.dumps(report, indent=2))
