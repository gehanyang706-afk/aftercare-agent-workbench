"""Version prefilter -> fixed Chinese character/bigram BM25 + dense -> RRF -> rerank."""

import hashlib
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from aftercare.config import PROJECT_ROOT
from aftercare.retrieval.local import LocalModels


def tokenize(text):
    pieces = re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", text.lower())
    return pieces + [
        a + b for a, b in zip(pieces, pieces[1:], strict=False) if len(a) == len(b) == 1
    ]


class PolicySearch:
    def __init__(self, directory=None, models=None, sessions=None):
        self.sessions = sessions
        self.directory = Path(directory or PROJECT_ROOT / "data/policies")
        self.models = models or LocalModels()
        self.chunks = []
        self.cache = {}
        for path in sorted(self.directory.glob("*.yaml")):
            doc = yaml.safe_load(path.read_text())
            for clause in doc["sections"]:
                self.chunks.append(
                    {
                        **{k: v for k, v in doc.items() if k != "sections"},
                        **clause,
                        "policy_ref": f"{doc['source_id']}@{doc['version']}#{clause['section']}",
                        "content_hash": hashlib.sha256(clause["text"].encode()).hexdigest(),
                    }
                )
        self.corpus_hash = hashlib.sha256(
            json.dumps(self.chunks, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    def eligible(self, chunk, action, qualification_version, flow_version, now):
        if chunk["action"] not in ["all", action] and action != "all":
            return False
        if chunk["kind"] == "qualification":
            return chunk["version"] == qualification_version
        start = datetime.fromisoformat(chunk["effective_from"].replace("Z", "+00:00"))
        end = chunk.get("effective_to")
        return (
            chunk["version"] == flow_version
            and start <= now
            and (not end or now < datetime.fromisoformat(end.replace("Z", "+00:00")))
        )

    def search(
        self,
        query,
        action="all",
        profile="bm25",
        qualification_version="v1",
        flow_version="v1",
        now=None,
        limit=5,
    ):
        now = now or datetime.now(UTC)
        chunks = [
            c
            for c in self.chunks
            if self.eligible(c, action, qualification_version, flow_version, now)
        ]
        key = hashlib.sha256(
            json.dumps(
                [
                    query,
                    action,
                    profile,
                    qualification_version,
                    flow_version,
                    [c["policy_ref"] for c in chunks],
                    self.corpus_hash,
                    self.models.revision(),
                    limit,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if key in self.cache:
            return self.cache[key]
        if profile == "full-policy":
            return chunks
        if not chunks:
            return []
        if profile not in ["bm25", "dense", "hybrid", "hybrid-rerank"]:
            raise ValueError("UNKNOWN_RETRIEVAL_PROFILE")
        counts = [Counter(tokenize(c["text"] + " " + c["title"])) for c in chunks]
        avg = sum(sum(c.values()) for c in counts) / len(counts)
        query_tokens = tokenize(query)
        scores = []
        for count in counts:
            score = 0
            for token in query_tokens:
                df = sum(token in d for d in counts)
                tf = count[token]
                score += (
                    math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
                    * tf
                    * 2.2
                    / (tf + 1.2 * (0.25 + 0.75 * sum(count.values()) / avg))
                )
            scores.append(score)
        bm25 = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:20]
        rank = bm25
        if profile != "bm25":
            query_vector = self.models.encode([query], query=True)[0]
            if self.sessions:
                from sqlalchemy import select

                from aftercare.repositories.models import PolicyChunk

                revision = self.models.revision()["embedding"]
                with self.sessions() as session:
                    ids = list(
                        session.scalars(
                            select(PolicyChunk.id)
                            .where(
                                PolicyChunk.id.in_([c["policy_ref"] for c in chunks]),
                                PolicyChunk.corpus_hash == self.corpus_hash,
                                PolicyChunk.model_revision == revision,
                                PolicyChunk.embedding.is_not(None),
                            )
                            .order_by(PolicyChunk.embedding.cosine_distance(query_vector.tolist()))
                            .limit(20)
                        )
                    )
                if not ids:
                    raise RuntimeError("VECTOR_INDEX_MISSING_OR_STALE")
                mapping = {c["policy_ref"]: i for i, c in enumerate(chunks)}
                dense = [mapping[ref] for ref in ids]
            else:
                vectors = self.models.encode([c["text"] for c in chunks])
                dense = sorted(
                    range(len(chunks)), key=lambda i: float(vectors[i] @ query_vector), reverse=True
                )[:20]
            if profile == "dense":
                rank = dense
            else:
                rrf = Counter()
                for result in [bm25, dense]:
                    for n, i in enumerate(result, 1):
                        rrf[i] += 1 / (60 + n)
                rank = sorted(rrf, key=rrf.get, reverse=True)
                if profile == "hybrid-rerank":
                    candidates = rank[:10]
                    reranked = self.models.rerank(query, [chunks[i]["text"] for i in candidates])
                    rank = [
                        i for _, i in sorted(zip(reranked, candidates, strict=True), reverse=True)
                    ]
        results = []
        tokens = 0
        for i in rank[:limit]:
            chunk = chunks[i]
            # Conservative context budget with intact clauses; never slice an exception off.
            size = len(chunk["text"])
            if tokens + size > 1800:
                break
            tokens += size
            results.append({**chunk, "rank": len(results) + 1})
        if len(self.cache) >= 256:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = results
        return results

    def build(self, profile="local-lite"):
        from sqlalchemy import delete

        from aftercare.repositories.models import PolicyChunk

        vectors = None
        if profile != "bm25":
            tokenizer = self.models.tokenizer("embedding")
            for chunk in self.chunks:
                if len(tokenizer.encode(chunk["text"]).ids) > 256:
                    raise ValueError("CLAUSE_TOO_LONG_SPLIT_AT_SECTION_BOUNDARY")
            vectors = self.models.encode([c["text"] for c in self.chunks])
        if self.sessions:
            with self.sessions.begin() as s:
                s.execute(delete(PolicyChunk))
                for i, chunk in enumerate(self.chunks):
                    s.add(
                        PolicyChunk(
                            id=chunk["policy_ref"],
                            corpus_hash=self.corpus_hash,
                            model_revision=self.models.revision()["embedding"]
                            if vectors is not None
                            else "bm25",
                            metadata_json=chunk,
                            embedding=vectors[i].tolist() if vectors is not None else None,
                        )
                    )
        return {
            "chunks": len(self.chunks),
            "corpus_hash": self.corpus_hash,
            "vectors_built": vectors is not None,
            "dimensions": 512 if vectors is not None else 0,
        }
