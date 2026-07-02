"""Agnes LLM 客户端测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.llm_agnes import AgnesClient
from app.services.visual.agnes_api import AgnesApiKey, AgnesQuotaExceeded


def test_agnes_client_build_chat_payload_json_mode() -> None:
    client = AgnesClient.__new__(AgnesClient)
    client._model = "agnes-2.0-flash"  # noqa: SLF001
    payload = client._build_chat_payload(  # noqa: SLF001
        system="sys",
        user="usr",
        max_tokens=1024,
    )
    assert payload["model"] == "agnes-2.0-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"


def test_agnes_client_switches_key_on_quota() -> None:
    client = AgnesClient.__new__(AgnesClient)
    client._api_keys = [  # noqa: SLF001
        AgnesApiKey("free", "free-key"),
        AgnesApiKey("primary", "main-key"),
    ]
    client._model = "agnes-2.0-flash"  # noqa: SLF001
    client._max_tokens_default = 1024  # noqa: SLF001

    ok_resp = MagicMock()
    ok_resp.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"title":"ok"}'}}],
    }

    with patch.object(client, "_post_chat", side_effect=[AgnesQuotaExceeded("429"), ok_resp]):
        content, finish = client._chat("sys", "usr")  # noqa: SLF001

    assert finish == "stop"
    assert '"title":"ok"' in content


def test_agnes_client_init_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_FREE_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    from app.config import config

    monkeypatch.setattr(config, "agnes_free_api_key", None, raising=False)
    monkeypatch.setattr(config, "agnes_api_key", None, raising=False)
    with pytest.raises(RuntimeError, match="AGNES_FREE_API_KEY"):
        AgnesClient()
