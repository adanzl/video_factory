"""LLM 模块总入口。"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

TopicLlmOperation = Literal["generate", "save", "optimize"]

from app.config import get_settings
from app.services.topic.parsers import is_topic_parse_retryable

__all__ = ["LLMClient", "LLMMgr", "TopicLlmOperation", "llm_mgr"]

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

    def generate_board(
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
        return self.generate_storyboard(
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
        raise NotImplementedError

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
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
        category: str | None = None,
        keywords: str | list[str] | None = None,
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

    def generate_tags(
        self,
        title: str,
        narration: str,
    ) -> list[str]:
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
        job: dict | None = None,
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

    def generate_daily_story(
        self,
        theme: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_daily_story_themes(
        self,
        count: int = 2,
    ) -> list[str]:
        raise NotImplementedError

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class LLMMgr:
    """LLM 管理器。"""

    def _get_client(self) -> LLMClient:
        from app.services.llm.llm_mock import MockLLMClient

        if get_settings().mock_mode:
            return MockLLMClient()
        provider = get_settings().llm_provider
        if provider == "deepseek":
            from app.services.llm.llm_deepseek import DeepSeekClient

            return DeepSeekClient()
        if provider == "agnes":
            from app.services.llm.llm_agnes import AgnesClient

            return AgnesClient()
        raise ValueError(f"unsupported LLM_PROVIDER: {provider!r} (use deepseek or agnes)")

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

    def generate_board(
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
        return self.generate_storyboard(
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

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
    ) -> dict[str, Any]:
        return self._get_client().shrink_segment_texts(
            script,
            segment_indices=segment_indices,
            segment_target_sec=segment_target_sec,
            job=job,
        )

    def fill_image_prompts_with_retries(
        self,
        script: dict[str, Any],
        *,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
        max_attempts: int | None = None,
        skip_quality_check: bool = False,
    ) -> dict[str, Any]:
        """补全文生图提示词，过短时带 feedback 重试（与 script 阶段逻辑对齐）。"""
        from app.utils.job_cancel import raise_if_job_cancelled

        if skip_quality_check:
            self.fill_image_prompts(
                script,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=segment_indices,
                include_sd15_prompt=include_sd15_prompt,
            )
            return script

        from app.quality.quality_mgr import check_image_prompt
        from app.quality.image_prompt import (
            MIN_SD15_PROMPT_EN_WORDS,
            TARGET_SD15_PROMPT_EN_WORDS,
            format_image_prompt_retry_warning,
            image_prompt_min_chars,
            image_prompt_target_chars,
        )

        feedback: str | None = None
        target_indices = segment_indices
        min_chars = image_prompt_min_chars(sd15_mode=include_sd15_prompt)
        target_chars = image_prompt_target_chars(sd15_mode=include_sd15_prompt)
        attempts = max_attempts if max_attempts is not None else get_settings().script_qa_max_attempts
        for attempt in range(attempts):
            raise_if_job_cancelled(job)
            self.fill_image_prompts(
                script,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=target_indices,
                include_sd15_prompt=include_sd15_prompt,
            )
            report = check_image_prompt(
                script,
                sd15_mode=include_sd15_prompt,
                segment_indices=segment_indices,
            )
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
            reason = report.details.get("reason", "image_prompt too short")
            feedback = (
                f"{reason}: {target_indices}; "
                f"need image_prompt >={min_chars} chars each (target {target_chars})"
            )
            if include_sd15_prompt:
                feedback += (
                    f"; ensure each segment has sd15_prompt_en "
                    f"(>={MIN_SD15_PROMPT_EN_WORDS} English words, target {TARGET_SD15_PROMPT_EN_WORDS}); "
                    "image_prompt must cover six dimensions concisely "
                    "(subject, scene, style, lighting, composition, quality)"
                )
            else:
                feedback += (
                    "; expand prompt dimensions (subject, scene/environment, "
                    "style, lighting, composition, quality) with concrete visible details"
                )
            logger.warning(
                "%s",
                format_image_prompt_retry_warning(
                    attempt=attempt + 1,
                    reason=reason,
                    segments=too_short,
                    sd15_mode=include_sd15_prompt,
                ),
            )
        return script

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        category: str | None = None,
        keywords: str | list[str] | None = None,
        operation: TopicLlmOperation = "generate",
    ) -> list[dict[str, str]]:
        count = max(1, min(count, 20))
        custom_prompt = bool(system_prompt or user_prompt)
        theme_suffix = f" theme={theme!r}" if theme else ""
        logger.info(
            "[TOPIC] llm start operation=%s%s category=%r count=%d custom_prompt=%s mock=%s",
            operation,
            theme_suffix,
            category,
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
                category=category,
                keywords=keywords,
            )
        except ValueError as exc:
            if is_topic_parse_retryable(exc):
                logger.warning(
                    "[TOPIC] llm rejected operation=%s%s count=%d reason=%s",
                    operation,
                    theme_suffix,
                    count,
                    exc,
                )
            else:
                logger.exception(
                    "[TOPIC] llm failed operation=%s%s count=%d",
                    operation,
                    theme_suffix,
                    count,
                )
            raise
        except Exception:
            logger.exception(
                "[TOPIC] llm failed operation=%s%s count=%d",
                operation,
                theme_suffix,
                count,
            )
            raise
        elapsed = time.perf_counter() - started
        titles = [item["title"] for item in topics]
        logger.info(
            "[TOPIC] llm done operation=%s count=%d elapsed=%.1fs titles=%s",
            operation,
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

    def generate_tags(
        self,
        title: str,
        narration: str,
    ) -> list[str]:
        logger.info("[SCRIPT] generate tags start title=%r", title)
        started = time.perf_counter()
        try:
            tags = self._get_client().generate_tags(title, narration)
        except Exception:
            logger.exception("[SCRIPT] generate tags failed title=%r", title)
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] generate tags done title=%r tags=%s elapsed=%.1fs",
            title,
            tags,
            elapsed,
        )
        return tags

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        return self._get_client().generate_material_script(
            title,
            feedback=feedback,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            job=job,
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

    def generate_daily_story(
        self,
        theme: str,
    ) -> dict[str, Any]:
        logger.info("[DAILY_STORY] generate start theme=%r", theme)
        started = time.perf_counter()
        try:
            story = self._get_client().generate_daily_story(theme)
        except Exception:
            logger.exception("[DAILY_STORY] generate failed theme=%r", theme)
            raise
        elapsed = time.perf_counter() - started
        logger.info("[DAILY_STORY] generate done theme=%r elapsed=%.1fs", theme, elapsed)
        return story

    def generate_daily_story_themes(
        self,
        count: int = 2,
    ) -> list[str]:
        logger.info("[DAILY_STORY] generate themes start count=%d", count)
        started = time.perf_counter()
        try:
            themes = self._get_client().generate_daily_story_themes(count)
        except Exception:
            logger.exception("[DAILY_STORY] generate themes failed")
            raise
        elapsed = time.perf_counter() - started
        logger.info("[DAILY_STORY] generate themes done count=%d elapsed=%.1fs", len(themes), elapsed)
        return themes

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
    ) -> dict[str, Any]:
        logger.info("[DAILY_STORY] generate script start")
        started = time.perf_counter()
        try:
            result = self._get_client().generate_daily_script(
                dialogue_script,
                job=job,
            )
        except Exception:
            logger.exception("[DAILY_STORY] generate script failed")
            raise
        elapsed = time.perf_counter() - started
        logger.info("[DAILY_STORY] generate script done elapsed=%.1fs", elapsed)
        return result


llm_mgr = LLMMgr()
