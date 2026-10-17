"""Strictly local ONNX inference; tokenizer never truncates policy clauses."""

import json
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

from aftercare.config import PROJECT_ROOT


class WeightsUnavailable(RuntimeError):
    pass


class LocalModels:
    def __init__(self, root=None):
        self.root = Path(root or PROJECT_ROOT / "runtime/models")
        self.sessions = {}
        self.tokenizers = {}

    def tokenizer(self, role):
        if role not in self.tokenizers:
            path = self.root / role / "tokenizer.json"
            if not path.exists():
                raise WeightsUnavailable(f"{role}: tokenizer missing")
            self.tokenizers[role] = Tokenizer.from_file(str(path))
            self.tokenizers[role].no_truncation()
            self.tokenizers[role].no_padding()
        return self.tokenizers[role]

    def session(self, role):
        if role not in self.sessions:
            import onnxruntime as ort

            ort.disable_telemetry_events()

            path = self.root / role / ("model.onnx" if role == "embedding" else "onnx/model.onnx")
            if not path.exists():
                raise WeightsUnavailable(f"{role}: weights missing")
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self.sessions[role] = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        return self.sessions[role]

    def inputs(self, role, texts):
        tokenizer = self.tokenizer(role)
        encoded = tokenizer.encode_batch(texts)
        if any(len(e.ids) > 512 for e in encoded):
            raise ValueError("CLAUSE_EXCEEDS_TOKEN_LIMIT")
        length = max(len(e.ids) for e in encoded)
        pad = (
            tokenizer.token_to_id("[PAD]")
            if role == "embedding"
            else tokenizer.token_to_id("<pad>")
        )
        feed = {
            "input_ids": np.array(
                [e.ids + [pad] * (length - len(e.ids)) for e in encoded], dtype=np.int64
            ),
            "attention_mask": np.array(
                [e.attention_mask + [0] * (length - len(e.ids)) for e in encoded], dtype=np.int64
            ),
            "token_type_ids": np.array(
                [e.type_ids + [0] * (length - len(e.ids)) for e in encoded], dtype=np.int64
            ),
        }
        return feed

    def encode(self, texts, query=False):
        if query:
            texts = ["为这个句子生成表示以用于检索相关文章：" + t for t in texts]
        session = self.session("embedding")
        feed = self.inputs("embedding", texts)
        feed = {i.name: feed[i.name] for i in session.get_inputs()}
        result = session.run(None, feed)[0][:, 0, :]
        return result / np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-12)

    def rerank(self, query, texts):
        if not texts:
            return []
        session = self.session("reranker")
        feed = self.inputs("reranker", [(query, t) for t in texts])
        feed = {i.name: feed[i.name] for i in session.get_inputs()}
        return session.run(None, feed)[0].reshape(-1).tolist()

    def revision(self):
        path = PROJECT_ROOT / "configs/local-models.lock.json"
        if not path.exists():
            return "weights-unavailable"
        return {k: v["revision"] for k, v in json.loads(path.read_text()).items()}
