"""脚本阶段统一入口。

术语：
- **script**：脚本阶段产出的完整 JSON（分镜、口播、文生图提示词等）
- **board**：口播分镜，script 生成的第一步（segments / narration / visual_brief）
- 质检与前端 step id 仍用 ``storyboard``，与 board 同义

各子模块职责：
- ``board`` 口播分镜、素材口播、扩写/缩字、文生图提示词构建
- ``optimize_title`` / ``description`` 标题与简介
- ``board_timeline`` 素材管线分镜时间线约束
- ``compose`` 各子步骤 LLM 提示词组装
"""

from __future__ import annotations

from typing import Any

from app.services.llm.llm_mgr import llm_mgr
from app.quality import image_prompt
from app.services.script import board as script_board
from app.services.script import description as script_description
from app.services.script import compose as script_compose
from app.services.script import board_timeline as script_board_timeline
from app.services.script import optimize_title as script_optimize_title

__all__ = ["ScriptMgr", "script_mgr"]


class ScriptMgr:
    """脚本阶段业务管理（对外统一收口）。"""

    # --- board：口播分镜 ---
    build_board_prompts = staticmethod(script_board.build_board_prompts)
    build_storyboard_prompts = staticmethod(script_board.build_storyboard_prompts)
    build_narration_prompts = staticmethod(script_board.build_narration_prompts)
    build_visual_brief_prompts = staticmethod(script_board.build_visual_brief_prompts)
    build_material_prompts = staticmethod(script_board.build_material_script_prompts)
    build_narration_expand_prompts = staticmethod(script_board.build_narration_expand_prompts)
    build_segment_shrink_prompts = staticmethod(script_board.build_segment_shrink_prompts)

    # --- image_prompt：文生图提示词 ---
    build_image_prompts = staticmethod(script_board.build_image_prompts_prompts)
    image_prompt_min_chars = staticmethod(image_prompt.image_prompt_min_chars)
    image_prompt_pass_chars = staticmethod(image_prompt.image_prompt_pass_chars)
    image_prompt_target_chars = staticmethod(image_prompt.image_prompt_target_chars)
    sd15_prompt_en_word_count = staticmethod(image_prompt.sd15_prompt_en_word_count)
    sd15_prompt_en_ok = staticmethod(image_prompt.sd15_prompt_en_ok)
    format_image_prompt_retry_warning = staticmethod(
        image_prompt.format_image_prompt_retry_warning
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
