"""LLM 模块总入口。"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import get_settings

__all__ = ["LLMClient", "LLMMgr", "llm_mgr"]

logger = logging.getLogger(__name__)


class LLMClient:
    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
    ) -> dict[str, Any]:
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

    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
    ) -> dict[str, Any]:
        return self._get_client().generate_script(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
        )

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        count = max(1, min(count, 20))
        custom_prompt = bool(system_prompt or user_prompt)
        logger.info(
            "[TOPIC] generate start theme=%r count=%d custom_prompt=%s mock=%s",
            theme,
            count,
            custom_prompt,
            get_settings().mock_mode,
        )
        started = time.perf_counter()
        try:
            topics = self._get_client().generate_topics(
                theme,
                count=count,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception:
            logger.exception(
                "[TOPIC] generate failed theme=%r count=%d",
                theme,
                count,
            )
            raise
        elapsed = time.perf_counter() - started
        titles = [item["title"] for item in topics]
        logger.info(
            "[TOPIC] generate done count=%d elapsed=%.1fs titles=%s",
            len(topics),
            elapsed,
            titles,
        )
        return topics


llm_mgr = LLMMgr()
