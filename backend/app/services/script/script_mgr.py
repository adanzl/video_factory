"""脚本阶段统一入口。

术语：
- **script**：脚本阶段产出的完整 JSON（分镜、口播、文生图提示词等）
- 质检与前端 step id 仍用 ``storyboard``，与口播分镜同义

各子模块职责：
- ``voiceover_standard`` 标准管线自由口播（A1/A4/A5）
- ``voiceover_material`` 素材时间轴口播（B1）
- ``visual_brief`` / ``image_prompt`` 画面概述与文生图（A2/A3）
- ``segment_split`` 口播切分镜
- ``prompt_common`` 跨功能提示词辅助
- ``optimize_title`` / ``description`` / ``tags`` 标题简介标签
- ``board_timeline`` 素材管线分镜时间线约束
- ``compose`` 各子步骤 LLM 提示词组装
"""

from __future__ import annotations

from typing import Any

from app.services.llm.llm_mgr import llm_mgr
from app.quality import image_prompt as quality_image_prompt
from app.services.script import description as script_description
from app.services.script import compose as script_compose
from app.services.script import board_timeline as script_board_timeline
from app.services.script import optimize_title as script_optimize_title
from app.services.script.image_prompt import build_image_prompts
from app.services.script.segment_split import apply_segments_from_voiceover
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_material import build_voiceover_material_prompts
from app.services.script.voiceover_standard import (
    build_voiceover_standard_expand_prompts,
    build_voiceover_standard_prompts,
    build_voiceover_standard_shrink_prompts,
)

__all__ = ["ScriptMgr", "script_mgr"]


class ScriptMgr:
    """脚本阶段业务管理（对外统一收口）。"""

    # --- voiceover / visual / image ---
    build_voiceover_standard_prompts = staticmethod(build_voiceover_standard_prompts)
    build_voiceover_standard_expand_prompts = staticmethod(
        build_voiceover_standard_expand_prompts
    )
    build_voiceover_standard_shrink_prompts = staticmethod(
        build_voiceover_standard_shrink_prompts
    )
    build_voiceover_material_prompts = staticmethod(build_voiceover_material_prompts)
    build_visual_brief_prompts = staticmethod(build_visual_brief_prompts)
    build_image_prompts = staticmethod(build_image_prompts)
    apply_segments_from_voiceover = staticmethod(apply_segments_from_voiceover)

    image_prompt_min_chars = staticmethod(quality_image_prompt.image_prompt_min_chars)
    image_prompt_pass_chars = staticmethod(quality_image_prompt.image_prompt_pass_chars)
    image_prompt_target_chars = staticmethod(quality_image_prompt.image_prompt_target_chars)
    sd15_prompt_en_word_count = staticmethod(quality_image_prompt.sd15_prompt_en_word_count)
    sd15_prompt_en_ok = staticmethod(quality_image_prompt.sd15_prompt_en_ok)
    format_image_prompt_retry_warning = staticmethod(
        quality_image_prompt.format_image_prompt_retry_warning
    )

    # --- title / description ---
    build_title_prompts = staticmethod(script_optimize_title.build_title_optimize_prompts)
    parse_title = staticmethod(script_optimize_title.parse_title_optimize_payload)
    build_description_prompts = staticmethod(script_description.build_video_description_prompts)
    parse_description = staticmethod(script_description.parse_video_description_payload)

    # --- board_timeline ---
    parse_timeline = staticmethod(script_board_timeline.parse_video_timeline)
    validate_timeline = staticmethod(script_board_timeline.validate_timeline_script)
    narration_range_for_timeline = staticmethod(script_board_timeline.narration_range_for_timeline)

    # --- compose：提示词组装 ---
    collect_prompts = staticmethod(script_compose.collect_prompts)
    attach_prompts = staticmethod(script_compose.attach_prompts)
    collect_script_prompts = staticmethod(script_compose.collect_script_prompts)
    attach_llm_prompts_to_script = staticmethod(script_compose.attach_llm_prompts_to_script)

    # --- LLM 生成（委托 llm_mgr）---
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
        """生成口播分镜（board），不含文生图提示词。"""
        return llm_mgr.generate_board(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )

    def generate(
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
        """生成完整 script（board + 文生图提示词等）。"""
        return llm_mgr.generate_script(
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

    def fill_image_prompts(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return llm_mgr.fill_image_prompts(*args, **kwargs)

    def fill_image_prompts_with_retries(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return llm_mgr.fill_image_prompts_with_retries(*args, **kwargs)

    def shrink_segment_texts(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return llm_mgr.shrink_segment_texts(*args, **kwargs)

    def optimize_title(self, *args: Any, **kwargs: Any) -> str:
        return llm_mgr.optimize_script_title(*args, **kwargs)

    def generate_video_description(self, *args: Any, **kwargs: Any) -> str:
        return llm_mgr.generate_video_description(*args, **kwargs)

    def generate_material(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return llm_mgr.generate_material_script(*args, **kwargs)


script_mgr = ScriptMgr()
