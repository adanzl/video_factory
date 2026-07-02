"""Agnes LLM 客户端测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.llm_agnes import _build_chat_payload, _chat_with_key_fallback
from app.services.llm.llm_agnes import AgnesApiKey, AgnesQuotaExceeded


def test_build_chat_payload_json_mode() -> None:
    payload = _build_chat_payload(
        model="agnes-2.0-flash",
        system="sys",
        user="usr",
        max_tokens=1024,
    )
    assert payload["model"] == "agnes-2.0-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"


def test_chat_with_key_fallback_switches_on_quota(monkeypatch) -> None:
    from app.config import config

    monkeypatch.setattr(config, "agnes_free_api_key", "free-key", raising=False)
    monkeypatch.setattr(config, "agnes_api_key", "main-key", raising=False)
    monkeypatch.setattr(config, "agnes_llm_model", "agnes-2.0-flash", raising=False)
    monkeypatch.setattr(config, "agnes_llm_max_tokens", 1024, raising=False)
    monkeypatch.setattr(config, "agnes_api_base_url", "https://apihub.agnes-ai.com/v1", raising=False)
    monkeypatch.setattr(config, "agnes_http_max_retries", 1, raising=False)
    monkeypatch.setattr(config, "agnes_http_connect_timeout_sec", 1.0, raising=False)
    monkeypatch.setattr(config, "agnes_http_submit_read_timeout_sec", 1.0, raising=False)

    ok_resp = MagicMock()
    ok_resp.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"title":"ok"}'}}],
    }

    with patch(
        "app.services.llm.llm_agnes._post_chat",
        side_effect=[AgnesQuotaExceeded("429"), ok_resp],
    ):
        content, finish = _chat_with_key_fallback(system="sys", user="usr")

    assert finish == "stop"
    assert '"title":"ok"' in content


def test_chat_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_FREE_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    from app.config import config

    monkeypatch.setattr(config, "agnes_free_api_key", None, raising=False)
    monkeypatch.setattr(config, "agnes_api_key", None, raising=False)
    with pytest.raises(RuntimeError, match="AGNES_FREE_API_KEY"):
        _chat_with_key_fallback(system="sys", user="usr")
