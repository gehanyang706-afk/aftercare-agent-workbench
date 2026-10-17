"""Bailian request adapter; execution remains disabled through phase 5."""

import httpx
import yaml
from pydantic import SecretStr

from aftercare.config import PROJECT_ROOT
from aftercare.llm.gateway import RealModelCallsDisabled


class BailianAdapter:
    def __init__(self, base_url: str, key: SecretStr):
        parsed = httpx.URL(base_url)
        if parsed.scheme != "https" or not parsed.host or not parsed.path.endswith("/v1"):
            raise ValueError("INVALID_BAILIAN_BASE_URL")
        self.base_url, self.key = base_url.rstrip("/"), key
        self.models = yaml.safe_load((PROJECT_ROOT / "configs/models.yaml").read_text())["models"]

    def prepare(self, model, messages, tools=None, stream=False, max_tokens=512):
        if model not in self.models:
            raise ValueError("UNAPPROVED_EXACT_MODEL")
        capabilities = self.models[model]
        if not 1 <= max_tokens <= capabilities["max_output_tokens"]:
            raise ValueError("OUTPUT_CAP_INVALID")
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": stream}
        if tools:
            payload["tools"] = tools
        if "enable_thinking" in capabilities:
            payload["enable_thinking"] = capabilities["enable_thinking"]
        if "tool_stream" in capabilities and tools:
            payload["tool_stream"] = capabilities["tool_stream"]
        if stream:
            if not capabilities.get("stream_usage"):
                raise ValueError("STREAM_USAGE_UNVERIFIED")
            payload["stream_options"] = {"include_usage": True}
        return httpx.Request(
            "POST",
            self.base_url + "/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer " + self.key.get_secret_value()},
        )

    def invoke(self, *args, **kwargs):
        # Phase 6 will require an audited human approval + ledger permit, never just an env flag.
        raise RealModelCallsDisabled("REAL_MODEL_CALLS_DISABLED_PHASES_0_TO_5")
