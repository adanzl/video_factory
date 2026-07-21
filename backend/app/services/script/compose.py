"""脚本阶段 LLM 提示词组装：汇总各子步骤并写入 script_json。"""

from __future__ import annotations

import re

from app.services.script.image_prompt import build_image_prompts
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_material import build_voiceover_material_prompts
from app.services.script.voiceover_standard import build_voiceover_standard_prompts


def _is_material_job(job: dict) -> bool:
    return job.get("pipeline") == "material"


def _preview_script_stub(
    title: str,
    *,
    narration: str,
    draft_title: str,
) -> dict:
    """无分镜时预览 visual_brief / image_prompts 用的占位 script。"""
    return {
        "title": draft_title or title,
        "narration": narration,
        "visual_style": "（口播生成后将填入全片 visual_style）",
        "segments": [
            {
                "segment_index": 1,
                "text": "（示例：第一段口播，由后端按单镜时长切分后填入）",
            },
            {
                "segment_index": 2,
                "text": "（示例：第二段口播）",
            },
        ],
    }


def collect_prompts(
    job: dict,
    title: str,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    speech_chars_per_sec: float | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    script: dict | None = None,
    skip_title_optimize: bool = False,
    preview_followups: bool = False,
) -> list[dict[str, str]]:
    """组装脚本阶段各步 LLM 提示词；预览模式返回完整四步。"""
    extra = (supplementary_info or "").strip() or None
    if extra is None and script:
        saved = script.get("supplementary_info")
        if isinstance(saved, str) and saved.strip():
            extra = saved.strip()
    timeline_raw = (video_timeline or "").strip() or None
    if timeline_raw is None and script:
        saved_timeline = script.get("video_timeline")
        if isinstance(saved_timeline, str) and saved_timeline.strip():
            timeline_raw = saved_timeline.strip()
    prompts: list[dict[str, str]] = []
    if _is_material_job(job):
        prompts.append(
            build_voiceover_material_prompts(
                title,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=extra,
                video_timeline=timeline_raw,
                script=script,
                chars_per_sec=speech_chars_per_sec,
                job=job,
            )
        )
    else:
        prompts.append(
            build_voiceover_standard_prompts(
                title,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=extra,
                job=job,
            )
        )

    narration = ""
    draft_title = re.sub(r"\s+", "", title.strip())
    if script and isinstance(script, dict):
        narration = str(script.get("narration") or "").strip()
        draft_title = re.sub(
            r"\s+",
            "",
            str(script.get("draft_title") or script.get("title") or draft_title).strip(),
        )

    if preview_followups and not narration:
        narration = "（口播分镜生成后将填入实际 narration，此处仅预览提示词结构）"

    if not _is_material_job(job):
        followup_script = script if isinstance(script, dict) else None
        has_segments = bool(followup_script and followup_script.get("segments"))
        if preview_followups and not has_segments:
            followup_script = _preview_script_stub(
                title,
                narration=narration,
                draft_title=draft_title,
            )
        if followup_script and (has_segments or preview_followups):
            prompts.append(
                build_visual_brief_prompts(followup_script, supplementary_info=extra, job=job)
            )
            prompts.append(
                build_image_prompts(followup_script, supplementary_info=extra, job=job)
            )

    show_title_optimize = bool(narration and draft_title) and (
        preview_followups or not skip_title_optimize
    )
    if show_title_optimize:
        from app.services.script.optimize_title import build_title_optimize_prompts

        prompts.append(
            build_title_optimize_prompts(
                draft_title,
                narration,
                max_title_length=max_title_length,
            )
        )
    return prompts


def attach_prompts(
    script: dict,
    job: dict,
    title: str,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    speech_chars_per_sec: float | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    skip_title_optimize: bool = False,
) -> None:
    script["llm_prompts"] = collect_prompts(
        job,
        title,
        segment_target_sec=segment_target_sec,
        max_title_length=max_title_length,
        narration_target_words=narration_target_words,
        speech_chars_per_sec=speech_chars_per_sec,
        supplementary_info=supplementary_info,
        video_timeline=video_timeline,
        script=script,
        skip_title_optimize=skip_title_optimize,
    )


# 兼容旧名
collect_script_prompts = collect_prompts
attach_llm_prompts_to_script = attach_prompts
