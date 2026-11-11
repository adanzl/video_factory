"""text_llm_configured 与 provider 门禁。"""

from __future__ import annotations

import pytest

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


def test_agnes_retired_key_does_not_satisfy_provider_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    monkeypatch.setattr(config, "llm_provider", "agnes")
    monkeypatch.setattr(config, "agnes_api_key", None)
    monkeypatch.setattr(config, "agnes_cn_api_key", "retired-key")
    monkeypatch.setattr(config, "agnes_free_api_key", None)
    monkeypatch.setattr(config, "agnes_cn_free_api_key", None)
    assert config.text_llm_configured() is False
    assert (
        "AGNES_API_KEY / AGNES_FREE_API_KEY / AGNES_CN_FREE_API_KEY"
        in config.missing_provider_keys()
    )
    monkeypatch.setattr(config, "agnes_cn_free_api_key", "usable-free-key")
    assert config.text_llm_configured() is True
    assert not any("AGNES" in key for key in config.missing_provider_keys())
