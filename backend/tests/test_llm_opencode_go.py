"""OpenCode Go LLM 传输层测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.llm_opencode_go import OpenCodeGoClient, _session_id_for_chat


def test_session_id_stable_for_same_prompt() -> None:
    a = _session_id_for_chat("sys", "usr")
    b = _session_id_for_chat("sys", "usr")
    assert a == b
    assert a.startswith("vf-")


@pytest.mark.parametrize("pro_value", [None, "", "deepseek-v4.1-flash"])
def test_flash_config_reaches_default_planning_and_multiturn_requests(monkeypatch, pro_value):
    import importlib
    config_module = importlib.import_module("app.config")
    from app.services.gold_story.gold_chat import expand

    monkeypatch.setattr(config_module, "load_dotenv", lambda *_a, **_kw: None)
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4.1-flash")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "opencode_go")
    if pro_value is None:
        monkeypatch.delenv("DEEPSEEK_PRO_MODEL", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_PRO_MODEL", pro_value)
    settings = config_module.Config()
    monkeypatch.setattr(config_module, "config", settings)
    assert settings.deepseek_pro_model == settings.deepseek_model == "deepseek-v4.1-flash"
    assert expand._source_plan_model() == "deepseek-v4.1-flash"
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}
    with patch("requests.post", return_value=response) as post:
        client = OpenCodeGoClient()
        client._chat("system", "user")
        client._chat("system", "user", model=client._pro_model)
        client._chat("system", "user", model=expand._source_plan_model())
        client.chat_messages([{"role": "user", "content": "test"}], model=client._pro_model)
    assert len(post.call_args_list) == 4
    assert all(call.kwargs["json"]["model"] == "deepseek-v4.1-flash" for call in post.call_args_list)


@pytest.mark.parametrize("base_url", [
    "https://opencode.ai/zen/go/v1",
    " https://opencode.ai/zen/go/v1/ ",
    "https://opencode.ai/inference/go/openai/v1",
    "https://proxy.example/v1/",
])
def test_opencode_chat_headers_and_url(monkeypatch, base_url) -> None:
    from app.config import config

    monkeypatch.setattr(config, "opencode_go_api_key", "oc-test-key", raising=False)
    monkeypatch.setattr(
        config,
        "opencode_go_base_url",
        base_url,
        raising=False,
    )
    monkeypatch.setattr(config, "opencode_go_user_agent", "video-factory-test/1", raising=False)
    monkeypatch.setattr(config, "deepseek_api_key", "ds-key", raising=False)
    monkeypatch.setattr(config, "deepseek_model", "deepseek-v4.1-flash", raising=False)
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
    expected_base = (
        "https://proxy.example/v1" if "proxy.example" in base_url
        else "https://opencode.ai/inference/go/openai/v1"
    )
    assert _args[0] == f"{expected_base}/chat/completions"
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer oc-test-key"
    assert headers["User-Agent"] == "video-factory-test/1"
    assert headers["x-opencode-session"] == _session_id_for_chat("system", "user")
    body = kwargs["json"]
    assert body["model"] == "deepseek-v4.1-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    assert body["temperature"] == 0.5

    messages = [{"role": "user", "content": "hello"}]
    with patch("requests.post", return_value=ok_resp) as post:
        client.chat_messages(messages)
        client.chat_messages(messages)
    first, retry = post.call_args_list
    assert first.args[0] == f"{expected_base}/chat/completions"
    assert first.kwargs["headers"]["Authorization"] == "Bearer oc-test-key"
    assert first.kwargs["headers"]["x-opencode-session"]
    assert first.kwargs["headers"]["x-opencode-session"] == retry.kwargs["headers"]["x-opencode-session"]


@pytest.mark.parametrize("env_value, expected", [
    (None, "https://opencode.ai/inference/go/openai/v1"),
    ("", "https://opencode.ai/inference/go/openai/v1"),
    (" https://opencode.ai/zen/go/v1/ ", "https://opencode.ai/inference/go/openai/v1"),
    ("https://opencode.ai/inference/go/openai/v1/", "https://opencode.ai/inference/go/openai/v1"),
    ("https://proxy.example/zen/go/v1/", "https://proxy.example/zen/go/v1"),
])
def test_opencode_config_migrates_retired_url(monkeypatch, env_value, expected):
    import importlib

    config_module = importlib.import_module("app.config")
    monkeypatch.setattr(config_module, "load_dotenv", lambda *_a, **_kw: None)
    if env_value is None:
        monkeypatch.delenv("OPENCODE_GO_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OPENCODE_GO_BASE_URL", env_value)
    assert config_module.Config().opencode_go_base_url == expected


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


def test_hard_deadline_interrupts_dripping_http_in_cli_and_gevent():
    """慢响应一直有数据时，read timeout 不触发，整次请求仍须被截止时间中断。"""
    import subprocess
    import sys
    script = r"""
import sys
mode = sys.argv[1]
if mode == 'gevent':
    from gevent import monkey
    monkey.patch_all(thread=False)
import time
import requests
from app.services.llm.llm_mgr import llm_deadline, llm_request_timeout, start_llm_deadline_timer, LLMDeadlineExpired
if mode == 'gevent':
    import gevent
    from gevent.pywsgi import WSGIServer
    def application(environ, start_response):
        start_response('200 OK', [('Content-Length', '20')])
        for _ in range(20):
            yield b'x'
            gevent.sleep(.03)
    server = WSGIServer(('127.0.0.1', 0), application, log=None)
    server.start()
    port = server.server_port
else:
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header('Content-Length', '20')
            self.end_headers()
            try:
                for _ in range(20):
                    self.wfile.write(b'x')
                    self.wfile.flush()
                    time.sleep(.03)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    port = server.server_port
started = time.monotonic()
token = llm_deadline.set(started + .15)
cancel = start_llm_deadline_timer()
try:
    try:
        requests.post('http://127.0.0.1:' + str(port), timeout=llm_request_timeout())
    except LLMDeadlineExpired:
        pass
    else:
        raise AssertionError('slow response escaped total deadline')
finally:
    cancel()
    cancel()
    llm_deadline.reset(token)
assert time.monotonic() - started < .4
if mode == 'gevent':
    server.stop()
else:
    server.server_close()
assert llm_deadline.get() == 0
print(mode + ': deadline enforced')
"""
    for mode in ("sync", "gevent"):
        result = subprocess.run([sys.executable, "-c", script, mode], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deadline enforced" in result.stdout
