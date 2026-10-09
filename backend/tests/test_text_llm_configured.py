"""text_llm_configured 与 provider 门禁。"""

from __future__ import annotations

from app.config import config


def test_text_llm_configured_by_provider(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", False, raising=False)

    monkeypatch.setattr(config, "llm_provider", "deepseek", raising=False)
    monkeypatch.setattr(config, "deepseek_api_key", "k", raising=False)
    assert config.text_llm_configured() is True
    monkeypatch.setattr(config, "deepseek_api_key", None, raising=False)
    assert config.text_llm_configured() is False

    monkeypatch.setattr(config, "llm_provider", "opencode_go", raising=False)
    monkeypatch.setattr(config, "opencode_go_api_key", "oc", raising=False)
    assert config.text_llm_configured() is True
    monkeypatch.setattr(config, "opencode_go_api_key", None, raising=False)
    assert config.text_llm_configured() is False

    monkeypatch.setattr(config, "mock_mode", True, raising=False)
    assert config.text_llm_configured() is True
