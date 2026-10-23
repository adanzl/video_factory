"""OpenCode Go LLM 传输层测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.llm.llm_opencode_go import OpenCodeGoClient, _session_id_for_chat


def test_session_id_stable_for_same_prompt() -> None:
    a = _session_id_for_chat("sys", "usr")
    b = _session_id_for_chat("sys", "usr")
    assert a == b
    assert a.startswith("vf-")


def test_opencode_chat_headers_and_url(monkeypatch) -> None:
    from app.config import config

    monkeypatch.setattr(config, "opencode_go_api_key", "oc-test-key", raising=False)
    monkeypatch.setattr(
        config,
        "opencode_go_base_url",
        "https://opencode.ai/zen/go/v1",
        raising=False,
    )
    monkeypatch.setattr(config, "opencode_go_user_agent", "video-factory-test/1", raising=False)
    monkeypatch.setattr(config, "deepseek_api_key", "ds-key", raising=False)
    monkeypatch.setattr(config, "deepseek_model", "deepseek-v4-flash", raising=False)
    monkeypatch.setattr(config, "deepseek_max_tokens", 1024, raising=False)
    monkeypatch.setattr(config, "deepseek_thinking_enabled", False, raising=False)

    ok_resp = MagicMock()
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
    }

    with patch("requests.post", return_value=ok_resp) as mock_post:
        client = OpenCodeGoClient()
        content, finish = client._chat(
            "system",
            "user",
            json_mode=False,
            thinking_enabled=False,
            temperature=0.5,
        )

    assert finish == "stop"
    assert content == "hello"
    mock_post.assert_called_once()
    _args, kwargs = mock_post.call_args
    assert _args[0] == "https://opencode.ai/zen/go/v1/chat/completions"
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer oc-test-key"
    assert headers["User-Agent"] == "video-factory-test/1"
    assert headers["x-opencode-session"] == _session_id_for_chat("system", "user")
    body = kwargs["json"]
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    assert body["temperature"] == 0.5


def test_deadline_limits_each_request_and_expired_budget_makes_no_request(monkeypatch):
    import pytest
    import importlib
    budget = importlib.import_module("app.services.llm.llm_mgr")

    from app.config import config
    monkeypatch.setattr(config, "opencode_go_api_key", "test-key")
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100.0)
    token = budget.llm_deadline.set(107.0)
    try:
        timeout = budget.llm_request_timeout()
        assert isinstance(timeout, tuple)
        assert sum(timeout) == 7.0
        assert min(timeout) > 0
        budget.llm_deadline.set(99.0)
        with patch("requests.post") as post:
            with pytest.raises(budget.LLMTimeBudgetExceeded):
                OpenCodeGoClient()._chat("system", "user", json_mode=False)
        post.assert_not_called()
    finally:
        budget.llm_deadline.reset(token)
    assert budget.llm_request_timeout() == 300.0


def test_deadline_does_not_leak_between_greenlets():
    import gevent
    import importlib
    budget = importlib.import_module("app.services.llm.llm_mgr")

    def isolated(deadline):
        token = budget.llm_deadline.set(deadline)
        try:
            gevent.sleep(0)
            return budget.llm_deadline.get()
        finally:
            budget.llm_deadline.reset(token)

    first = gevent.spawn(isolated, 10.0)
    second = gevent.spawn(isolated, 20.0)
    gevent.joinall([first, second])
    assert [first.value, second.value] == [10.0, 20.0]
    assert budget.llm_deadline.get() == 0.0
