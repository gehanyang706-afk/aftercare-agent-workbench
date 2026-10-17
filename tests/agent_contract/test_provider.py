import json

import pytest
from pydantic import SecretStr

from aftercare.llm.gateway import RealModelCallsDisabled
from aftercare.llm.provider import BailianAdapter


def test_offline_request_shapes_and_real_send_is_disabled():
    adapter = BailianAdapter(
        "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", SecretStr("not-a-key")
    )
    request = adapter.prepare(
        "qwen3.5-plus-2026-02-15", [{"role": "user", "content": "测试"}], stream=True
    )
    data = json.loads(request.content)
    assert data["enable_thinking"] is False and data["stream_options"] == {"include_usage": True}
    assert data["model"] == "qwen3.5-plus-2026-02-15" and data["max_tokens"] == 512
    with pytest.raises(RealModelCallsDisabled):
        adapter.invoke()
    with pytest.raises(ValueError, match="EXACT_MODEL"):
        adapter.prepare("other-model", [])
