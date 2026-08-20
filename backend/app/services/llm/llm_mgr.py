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

    def fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def review_image_prompts(
        self,
        script: dict[str, Any],
        *,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> list[dict]:
        """L2 语义审核：LLM reviewer 审查已拼装的 image_prompt。"""
        raise NotImplementedError

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
        chars_per_sec: float | None = None,
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
        *,
        content_style: str | None = None,
    ) -> str:
        raise NotImplementedError

    def generate_tags(
        self,
        title: str,
        narration: str,
        *,
        content_style: str | None = None,
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
        *,
        story_type: str | None = None,
        avoid: list[str] | None = None,
        framework: dict | None = None,
        opening: list | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_daily_story_themes(
        self,
        count: int = 15,
        *,
        avoid: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
        chars_per_sec: float | None = None,
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

    def fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        return self._get_client().fill_visual_briefs(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
        )

    def review_image_prompts(
        self,
        script: dict[str, Any],
        *,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> list[dict]:
        """L2 语义审核入口（provider 无关）。"""
        return self._get_client().review_image_prompts(
            script,
            job=job,
            segment_indices=segment_indices,
        )

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        return self._get_client().shrink_segment_texts(
            script,
            segment_indices=segment_indices,
            segment_target_sec=segment_target_sec,
            job=job,
            chars_per_sec=chars_per_sec,
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
        style = None
        if job:
            from app.utils.job_info import content_style_from_job

            style = content_style_from_job(job)
            script["content_style"] = style
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
                content_style=style,
            )
            if report.level != "major":
                l2 = self._run_image_prompt_l2(
                    script,
                    job=job,
                    segment_indices=segment_indices,
                    l1_level=report.level,
                )
                if l2 is None:
                    return script
                l2_feedback, l2_indices = l2
                if not l2_indices or attempt + 1 >= attempts:
                    return script
                feedback = l2_feedback
                target_indices = l2_indices
                logger.warning(
                    "[SCRIPT] image_prompt L2 retry attempt=%d segments=%s",
                    attempt + 1,
                    l2_indices,
                )
                continue
            too_short = report.details.get("segments") or []
            target_indices = [
                int(item["segment_index"])
                for item in too_short
                if item.get("segment_index") is not None
            ]
            if not target_indices:
                break
            reason = report.details.get("reason", "image_prompt too short")
            if reason == "daily speaker leak in image_prompt":
                issues = report.details.get("issues") or []
                feedback = (
                    f"{reason}: {'; '.join(str(x) for x in issues[:5])}。"
                    "只画本段 speakers/同场粘性可入画角色；"
                    "忽略 visual_brief 里未授权角色。"
                )
            else:
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

    def _run_image_prompt_l2(
        self,
        script: dict[str, Any],
        *,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        l1_level: str = "pass",
    ) -> tuple[str, list[int]] | None:
        """L2 语义审核档位。返回 None=放行；(feedback, indices)=发现矛盾需重试。"""
        import random

        from app.quality.image_prompt import register_opposite_pair

        mode = get_settings().image_prompt_l2_mode
        if mode == "off":
            return None
        if mode == "on_l1_hit" and l1_level == "pass":
            return None
        if mode == "sample":
            if random.random() >= get_settings().image_prompt_l2_sample_ratio:
                return None
        try:
            reviews = self.review_image_prompts(
                script,
                job=job,
                segment_indices=segment_indices,
            )
        except Exception as exc:  # reviewer 故障不阻断主流水线
            logger.warning("image_prompt L2 reviewer failed, skip: %s", exc)
            return None
        indices: list[int] = []
        details: list[str] = []
        for r in reviews:
            idx = r.get("segment_index")
            for issue in r.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                kind = str(issue.get("kind") or "")
                detail = str(issue.get("detail") or "")
                if kind == "contradiction":
                    pair = issue.get("pair")
                    if (
                        isinstance(pair, list)
                        and len(pair) == 2
                        and all(isinstance(p, str) and p for p in pair)
                    ):
                        register_opposite_pair(pair[0], pair[1])
                    if idx is not None:
                        indices.append(int(idx))
                        details.append(f"segment {idx}: {kind} {detail}")
        if not indices:
            return None
        feedback = (
            "上次审核发现自相矛盾，请修正后重写："
            + "；".join(details[:5])
            + "。同一物体的状态/位置/数量须全句一致，不要自相矛盾。"
        )
        return feedback, sorted(set(indices))

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
        *,
        content_style: str | None = None,
    ) -> str:
        logger.info("[SCRIPT] generate video description start title=%r", title)
        started = time.perf_counter()
        try:
            description = self._get_client().generate_video_description(
                title,
                narration,
                content_style=content_style,
            )
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
        *,
        content_style: str | None = None,
    ) -> list[str]:
        logger.info("[SCRIPT] generate tags start title=%r", title)
        started = time.perf_counter()
        try:
            tags = self._get_client().generate_tags(
                title,
                narration,
                content_style=content_style,
            )
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
        *,
        story_type: str | None = None,
        review: bool = True,
        avoid: list[str] | None = None,
    ) -> dict[str, Any]:
        """出稿后固定走一遍人读审稿：审读→定点修→复审，不回环重生成。

        review=False 仅给本地预览调提示用，跳过慢审读。
        avoid：正文层避雷（与库内已有稿撞车的判据/开场理由/挑刺动作），
        生成与修订环节都注入提示词。
        """
        from app.services.daily_story.review import run_daily_story_review

        story = self._generate_daily_story_scored(
            theme,
            story_type=story_type,
            avoid=avoid,
        )
        hard_fail = bool(
            isinstance(story, dict) and story.pop("_hard_card_failed", False)
        )
        if not review or hard_fail:
            if hard_fail:
                logger.warning(
                    "[DAILY_STORY] review skipped (hard card failed)",
                )
            if isinstance(story, dict):
                story.pop("_beats_theme_object", None)
            return story
        result = run_daily_story_review(self._get_client(), theme, story)
        result.pop("_beats_theme_object", None)
        return result

    def _generate_daily_story_scored(
        self,
        theme: str,
        *,
        story_type: str | None = None,
        avoid: list[str] | None = None,
    ) -> dict[str, Any]:
        logger.info("[DAILY_STORY] generate start theme=%r", theme)
        started = time.perf_counter()
        from app.services.daily_story.quality import (
            attach_daily_story_quality,
            build_quality_revision_hints,
            structure_score_of,
        )
        from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
        from app.services.daily_story.story_types import parse_story_type_code

        def _dialogue_char_count(payload: dict) -> int:
            dialogue = payload.get("dialogue")
            if not isinstance(dialogue, list):
                return 0
            return sum(
                len(str(d.get("line") or ""))
                for d in dialogue
                if isinstance(d, dict)
            )

        type_code = (
            parse_story_type_code(story_type=story_type)
            if story_type
            else ""
        )
        c_strict = type_code == "C"
        # 结构残缺稿不入 degraded 池（GPT P2 2026-08-21）
        degraded_min_chars = 220

        client = self._get_client()
        best_story: dict[str, Any] | None = None
        best_score = -1
        target = 75
        # 生成循环只追结构分（≤80 封顶）；好笑分由审读阶段 LLM 评定
        # （review.apply_review_to_quality 注入 funny_score 0-20），最终发布线 =
        # 结构≥75 且 LLM 好笑≥HUMOR_PUBLISH_MIN（10）。整稿 3 次（全 Flash 高温发散）+ refine 兜底；
        # 外层失败缓存框架+开场，只重抽正文。refine 已切 Flash 关 thinking。
        # attach 默认会 finalize 总分=结构+好笑，比较 target 必须用 structure_score。
        max_full = 4 if c_strict else 3
        max_refine = 2
        last_exc: Exception | None = None
        cached_framework: dict[str, Any] | None = None
        cached_opening: list | None = None

        def _cache_from_story(payload: dict[str, Any] | None) -> None:
            nonlocal cached_framework, cached_opening
            if not isinstance(payload, dict):
                return
            fw = {
                k: payload.get(k)
                for k in ("scene_title", "setting", "conflict_core", "key")
                if payload.get(k)
            }
            if fw:
                cached_framework = fw
            opening = payload.get("discovery_opening")
            if isinstance(opening, list) and opening:
                cached_opening = opening

        def _cache_from_exc(exc: BaseException) -> None:
            nonlocal cached_framework, cached_opening
            fw = getattr(exc, "_framework", None)
            op = getattr(exc, "_opening", None)
            if isinstance(fw, dict) and fw:
                cached_framework = fw
            if isinstance(op, list) and op:
                cached_opening = op
            _cache_from_story(getattr(exc, "_failed_body", None))

        for attempt in range(max_full):
            try:
                if cached_framework or cached_opening:
                    logger.info(
                        "[DAILY_STORY] reuse cached framework+opening "
                        "attempt=%d/%d",
                        attempt + 1,
                        max_full,
                    )
                story = client.generate_daily_story(
                    theme,
                    story_type=story_type,
                    avoid=avoid,
                    framework=cached_framework,
                    opening=cached_opening,
                )
                _cache_from_story(story)
                attach_daily_story_quality(story, theme=theme)
            except ValueError as exc:
                last_exc = exc
                _cache_from_exc(exc)
                # 降级安全网：正文 3 次全败时，把最后一次被拒稿当候选保留，
                # 避免整条 FAIL（宁可给低分稿，不给 0 产出）。
                failed_body = getattr(exc, "_failed_body", None)
                if isinstance(failed_body, dict):
                    char_n = _dialogue_char_count(failed_body)
                    if char_n < degraded_min_chars:
                        logger.warning(
                            "[DAILY_STORY] skip degraded candidate "
                            "chars=%d < %d (结构残缺)",
                            char_n,
                            degraded_min_chars,
                        )
                    elif c_strict:
                        logger.warning(
                            "[DAILY_STORY] C类 skip degraded fallback "
                            "(validate FAIL=FAIL)",
                        )
                    else:
                        try:
                            attach_daily_story_quality(failed_body, theme=theme)
                            f_score = structure_score_of(
                                failed_body.get("quality"),
                            )
                            if f_score > best_score:
                                best_score = f_score
                                failed_body["_hard_card_failed"] = True
                                best_story = failed_body
                                logger.warning(
                                    "[DAILY_STORY] degraded fallback candidate "
                                    "structure=%d (kept instead of FAIL)",
                                    f_score,
                                )
                        except Exception:
                            pass
                logger.warning(
                    "[DAILY_STORY] attempt %d/%d validation failed: %s",
                    attempt + 1, max_full, exc,
                )
                continue
            except Exception:
                raise

            score = structure_score_of(story.get("quality"))
            if score > best_score:
                best_score = score
                best_story = story

            if score >= target:
                elapsed = time.perf_counter() - started
                logger.info(
                    "[DAILY_STORY] hit target structure=%d >= %d "
                    "attempt=%d/%d elapsed=%.1fs",
                    score, target, attempt + 1, max_full, elapsed,
                )
                return story

            refine = getattr(client, "refine_daily_story_for_quality", None)
            for _ri in range(max_refine):
                revision_hints = build_quality_revision_hints(
                    story.get("quality") or {},
                    story=story,
                )
                if not (revision_hints and callable(refine)):
                    break
                try:
                    refined = refine(
                        theme,
                        story,
                        revision_hints,
                        story_type=story_type,
                        avoid=avoid,
                    )
                    attach_daily_story_quality(refined, theme=theme)
                    r_score = structure_score_of(refined.get("quality"))
                    if r_score > best_score:
                        best_score = r_score
                        best_story = refined
                    if r_score >= target:
                        elapsed = time.perf_counter() - started
                        logger.info(
                            "[DAILY_STORY] quality refine hit structure=%d "
                            "attempt=%d/%d elapsed=%.1fs",
                            r_score, attempt + 1, max_full, elapsed,
                        )
                        return refined
                    story = refined
                    score = r_score
                except ValueError as exc:
                    logger.warning(
                        "[DAILY_STORY] quality refine failed attempt=%d: %s",
                        attempt + 1,
                        exc,
                    )
                    break

        elapsed = time.perf_counter() - started
        if best_story is not None:
            if c_strict and best_story.get("_hard_card_failed"):
                logger.warning(
                    "[DAILY_STORY] C类无合格候选（degraded 已关闭）"
                    " best_structure=%d elapsed=%.1fs",
                    best_score,
                    elapsed,
                )
                raise last_exc or ValueError(
                    "C类日常故事生成失败：无通过 validate 的候选稿",
                )
            if c_strict and _dialogue_char_count(best_story) < DAILY_STORY_BODY_CHARS_MIN:
                logger.warning(
                    "[DAILY_STORY] C类 skip best candidate "
                    "chars=%d < %d",
                    _dialogue_char_count(best_story),
                    DAILY_STORY_BODY_CHARS_MIN,
                )
                raise last_exc or ValueError(
                    "C类日常故事生成失败：最佳稿未达字数硬卡",
                )
            logger.warning(
                "[DAILY_STORY] best structure=%d < %d after %d full attempts "
                "elapsed=%.1fs",
                best_score, target, max_full, elapsed,
            )
            return best_story

        raise last_exc or RuntimeError(
            f"daily story generation failed after {max_full} attempts"
        )

    def generate_daily_story_themes(
        self,
        count: int = 15,
        *,
        avoid: list[str] | None = None,
    ) -> list[dict]:
        logger.info(
            "[DAILY_STORY] generate themes start count=%d avoid=%d",
            count,
            len(avoid or []),
        )
        started = time.perf_counter()
        try:
            themes = self._get_client().generate_daily_story_themes(
                count,
                avoid=avoid,
            )
        except ValueError as exc:
            logger.error("[DAILY_STORY] generate themes failed: %s", exc)
            raise
        except Exception:
            logger.exception("[DAILY_STORY] generate themes failed")
            raise
        elapsed = time.perf_counter() - started
        logger.info(
            "[DAILY_STORY] generate themes done count=%d elapsed=%.1fs",
            len(themes),
            elapsed,
        )
        return themes

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        logger.info("[DAILY_STORY] generate script start")
        started = time.perf_counter()
        try:
            result = self._get_client().generate_daily_script(
                dialogue_script,
                job=job,
                chars_per_sec=chars_per_sec,
            )
        except ValueError as exc:
            logger.error("[DAILY_STORY] generate script failed: %s", exc)
            raise
        except Exception:
            logger.exception("[DAILY_STORY] generate script failed")
            raise
        elapsed = time.perf_counter() - started
        logger.info("[DAILY_STORY] generate script done elapsed=%.1fs", elapsed)
        return result


llm_mgr = LLMMgr()
