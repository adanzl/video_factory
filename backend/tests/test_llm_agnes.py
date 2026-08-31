"""Agnes LLM 客户端测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

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
    monkeypatch.setattr(config, "agnes_api_base_url", "https://apihub.agnes-ai.cn/v1", raising=False)
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


def test_post_chat_failover_on_timeout(monkeypatch) -> None:
    from app.config import config
    from app.services.llm.llm_agnes import _post_chat

    monkeypatch.setattr(
        config, "agnes_api_base_url", "https://apihub.agnes-ai.com/v1", raising=False
    )
    com_url = "https://apihub.agnes-ai.com/v1/chat/completions"
    cn_url = "https://apihub.agnes-ai.cn/v1/chat/completions"

    ok_resp = MagicMock()
    ok_resp.ok = True
    ok_resp.status_code = 200
    ok_resp.raise_for_status = MagicMock()

    with patch(
        "app.services.llm.llm_agnes.requests.post",
        side_effect=[requests.Timeout("timed out"), ok_resp],
    ) as mock_post:
        resp = _post_chat(
            api_key=AgnesApiKey("primary", "k"),
            base_url="https://apihub.agnes-ai.com/v1",
            payload={"model": "m"},
            max_retries=2,
            connect_timeout=1.0,
            read_timeout=1.0,
        )

    assert resp is ok_resp
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[0].args[0] == com_url
    assert mock_post.call_args_list[1].args[0] == cn_url
    # failover 仅当前请求生效，不持久化全局 base_url
    assert config.agnes_api_base_url == "https://apihub.agnes-ai.com/v1"


def test_chat_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_FREE_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_CN_FREE_API_KEY", raising=False)
    from app.config import config

    monkeypatch.setattr(config, "agnes_free_api_key", None, raising=False)
    monkeypatch.setattr(config, "agnes_api_key", None, raising=False)
    monkeypatch.setattr(config, "agnes_cn_free_api_key", None, raising=False)
    with pytest.raises(RuntimeError, match="AGNES_API_KEY"):
        _chat_with_key_fallback(system="sys", user="usr")
