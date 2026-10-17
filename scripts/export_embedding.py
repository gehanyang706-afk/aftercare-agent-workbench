"""One-time local conversion; no hub lookups, trusted remote code, or inference API."""

import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from transformers import AutoModel

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "runtime/models/embedding"
torch.set_num_threads(2)
model = AutoModel.from_pretrained(
    str(path), local_files_only=True, trust_remote_code=False, attn_implementation="eager"
).eval()


class Encoder(torch.nn.Module):
    def __init__(self, base):
        super().__init__()
        self.base = base

    def forward(self, input_ids, attention_mask, token_type_ids):
        return self.base(
            input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
        ).last_hidden_state


args = (
    torch.ones((1, 8), dtype=torch.long),
    torch.ones((1, 8), dtype=torch.long),
    torch.zeros((1, 8), dtype=torch.long),
)
encoder = Encoder(model).eval()
with torch.no_grad():
    torch.onnx.export(
        encoder,
        args,
        str(path / "model.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            name: {0: "batch", 1: "sequence"}
            for name in ["input_ids", "attention_mask", "token_type_ids", "last_hidden_state"]
        },
        opset_version=17,
        dynamo=False,
    )

ort.disable_telemetry_events()
session = ort.InferenceSession(str(path / "model.onnx"), providers=["CPUExecutionProvider"])
feed = {
    name: value.numpy()
    for name, value in zip(["input_ids", "attention_mask", "token_type_ids"], args, strict=True)
}
actual = session.run(None, feed)[0]
with torch.no_grad():
    expected = encoder(*args).numpy()
max_error = float(np.max(np.abs(actual - expected)))
assert max_error < 1e-4, max_error
record = {
    "export_reference_max_abs_error": max_error,
    "source_revision": "7999e1d3359715c523056ef9478215996d62a620",
    "torch": torch.__version__,
    "exporter": "torch.onnx legacy opset17",
    "sha256": hashlib.file_digest((path / "model.onnx").open("rb"), "sha256").hexdigest(),
}
(ROOT / "configs/embedding-export.json").write_text(json.dumps(record, indent=2) + "\n")
