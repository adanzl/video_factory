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
        existing_script: dict | None = None,
        retry_scope: str | None = None,
        generate_image_prompts: bool = True,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_storyboard(
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

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
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

    def rewrite_pixabay_query(
        self,
        query: str,
        *,
        language: str | None = None,
    ) -> str:
        raise NotImplementedError

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
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
        existing_script: dict | None = None,
        retry_scope: str | None = None,
        generate_image_prompts: bool = True,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        return self._get_client().generate_script(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
            existing_script=existing_script,
            retry_scope=retry_scope,
            generate_image_prompts=generate_image_prompts,
            include_sd15_prompt=include_sd15_prompt,
        )

    def generate_storyboard(
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
        return self._get_client().generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        return self._get_client().fill_image_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
            include_sd15_prompt=include_sd15_prompt,
        )

    def fill_image_prompts_with_retries(
        self,
        script: dict[str, Any],
        *,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        max_attempts: int = 4,
    ) -> dict[str, Any]:
        """补全文生图提示词，过短时带 feedback 重试（与 script 阶段逻辑对齐）。"""
        from app.quality.checkers import check_image_prompts
        from app.services.llm.llm_script_prompts import (
            IMAGE_PROMPT_TARGET_CHARS,
            MIN_IMAGE_PROMPT_CHARS,
        )

        feedback: str | None = None
        target_indices = segment_indices
        for attempt in range(max_attempts):
            self.fill_image_prompts(
                script,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=target_indices,
            )
            report = check_image_prompts(script)
            if report.level != "major":
                return script
            too_short = report.details.get("segments") or []
            target_indices = [
                int(item["segment_index"])
                for item in too_short
                if item.get("segment_index") is not None
            ]
            if not target_indices:
                break
            feedback = (
                f"image_prompt too short: {target_indices}; "
                f"need >={MIN_IMAGE_PROMPT_CHARS} chars each "
                f"(target {IMAGE_PROMPT_TARGET_CHARS}); "
                "expand all six layers (composition, subject, environment, lighting, color, scope)"
            )
            logger.warning(
                "[SCRIPT] image_prompt retry attempt=%d short=%s",
                attempt + 1,
                target_indices,
            )
        return script

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

    def rewrite_pixabay_query(
        self,
        query: str,
        *,
        language: str | None = None,
    ) -> str:
        logger.info("[CLIP] rewrite pixabay query start query=%r language=%s", query[:80], language)
        started = time.perf_counter()
        try:
            rewritten = self._get_client().rewrite_pixabay_query(query, language=language)
        except Exception:
            logger.exception("[CLIP] rewrite pixabay query failed query=%r", query[:80])
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[CLIP] rewrite pixabay query done query=%r rewritten=%r elapsed=%.1fs",
            query[:80],
            rewritten[:80],
            elapsed,
        )
        return rewritten

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
        logger.info(
            "[SD15] prepare prompt start chars=%s business_override=%s",
            len(prompt),
            business_override,
        )
        started = time.perf_counter()
        try:
            result = self._get_client().prepare_sd15_image_prompt(
                prompt,
                size_hint=size_hint,
                business_override=business_override,
            )
        except Exception:
            logger.exception("[SD15] prepare prompt failed chars=%s", len(prompt))
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[SD15] prepare prompt done business=%s lora=%s prompt_en=%s elapsed=%.1fs",
            result["business"],
            result["lora"],
            result["prompt_en"],
            elapsed,
        )
        return result


llm_mgr = LLMMgr()
