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
        supplementary_info: str | None = None,
        job: dict | None = None,
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

    def optimize_script_title(
        self,
        draft_title: str,
        narration: str,
        *,
        max_title_length: int | None = None,
    ) -> str:
        raise NotImplementedError

    def generate_video_description(
        self,
        title: str,
        narration: str,
    ) -> str:
        raise NotImplementedError

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
    ) -> dict[str, Any]:
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
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        return self._get_client().generate_script(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
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

    def optimize_script_title(
        self,
        draft_title: str,
        narration: str,
        *,
        max_title_length: int | None = None,
    ) -> str:
        settings = get_settings()
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        logger.info("[SCRIPT] optimize title start draft=%r max_len=%d", draft_title, max_len)
        started = time.perf_counter()
        try:
            title = self._get_client().optimize_script_title(
                draft_title,
                narration,
                max_title_length=max_len,
            )
        except Exception:
            logger.exception("[SCRIPT] optimize title failed draft=%r", draft_title)
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] optimize title done draft=%r title=%r elapsed=%.1fs",
            draft_title,
            title,
            elapsed,
        )
        return title

    def generate_video_description(
        self,
        title: str,
        narration: str,
    ) -> str:
        logger.info("[SCRIPT] generate video description start title=%r", title)
        started = time.perf_counter()
        try:
            description = self._get_client().generate_video_description(title, narration)
        except Exception:
            logger.exception("[SCRIPT] generate video description failed title=%r", title)
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] generate video description done title=%r chars=%d elapsed=%.1fs",
            title,
            len(description),
            elapsed,
        )
        return description

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
    ) -> dict[str, Any]:
        return self._get_client().generate_material_script(
            title,
            feedback=feedback,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
        )


llm_mgr = LLMMgr()
