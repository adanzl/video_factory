"""LLM 模块总入口。"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

__all__ = ["LLMClient", "LLMMgr", "llm_mgr"]


class LLMClient:
    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        raise NotImplementedError


class LLMMgr:
    """LLM 管理器。"""

    def _get_client(self) -> LLMClient:
        from app.services.llm.llm_deepseek import DeepSeekClient
        from app.services.llm.llm_mock import MockLLMClient

        if get_settings().mock_mode:
            return MockLLMClient()
        return DeepSeekClient()

    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        return self._get_client().generate_script(title, feedback=feedback)

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        return self._get_client().generate_topics(
            theme,
            count=count,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


llm_mgr = LLMMgr()
