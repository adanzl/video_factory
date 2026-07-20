"""MOCK_MODE：仅显式开启，不因缺 Key 静默强制。"""

from __future__ import annotations

from app.config import config


def test_mock_mode_only_explicit(monkeypatch):
    # 避免 reload 用真实 .env 覆盖 monkeypatch
    monkeypatch.setattr("app.config.load_dotenv", lambda *_a, **_k: None)
    monkeypatch.delenv("MOCK_MODE", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_FREE_API_KEY", raising=False)

    config.reload()
    assert config.mock_mode is False
    assert config.missing_provider_keys()

    monkeypatch.setenv("MOCK_MODE", "true")
    config.reload()
    assert config.mock_mode is True

    monkeypatch.setenv("MOCK_MODE", "false")
    config.reload()
    assert config.mock_mode is False
