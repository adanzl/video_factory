"""LLM 模块总入口。"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

__all__ = ["LLMClient", "generate_script"]


class LLMClient:
    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


def _get_client() -> LLMClient:
    from app.services.llm.llm_deepseek import DeepSeekClient
    from app.services.llm.llm_mock import MockLLMClient

    if get_settings().mock_mode:
        return MockLLMClient()
    return DeepSeekClient()


def generate_script(title: str, *, feedback: str | None = None) -> dict[str, Any]:
    return _get_client().generate_script(title, feedback=feedback)
