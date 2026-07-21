"""日常故事（对话）分镜生成阶段。"""

from __future__ import annotations

import logging
import re

from app.repositories import repo_daily_story, repo_job, repo_job_log, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.script.optimize_title import (
    CHAT_TITLE_MAX_LEN,
    build_chat_title_prompts,
    parse_title_optimize_payload,
)
from app.utils.job_cancel import job_cancel
from app.utils.job_info import parse_job_info
from app.utils.title_text import collapse_title_whitespace
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)


class DailyScriptStage(StageExecutor):
    """日常对话故事 → 标准分镜 script_json。

    从 job.info.daily_story_id 加载故事，调用 LLM 生成 storyboard
    （scenes 含 dialogue；画面概述走标准 A2 fill_visual_briefs），
    再 fill_image_prompts，供下游 TTS / Segment / Merge 使用。
    """

    name = "script"

    def run(self, ctx: JobContext) -> None:
        job_id = ctx.job["id"]
        info = parse_job_info(ctx.job.get("info"))
        daily_story_id = info.get("daily_story_id")
        if not daily_story_id:
            raise RuntimeError("daily_story_id not found in job info")

        # 语速：统一走 info.script（与 JobContext / 标准链路一致）
        chars_per_sec = ctx.script_speech_chars_per_sec
        if chars_per_sec is None:
            from app.utils.job_info import (
                DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
                content_style_from_job,
                resolve_speech_chars_per_sec,
                script_params_from_info,
            )

            chars_per_sec = resolve_speech_chars_per_sec(
                script_params_from_info(ctx.job.get("info")),
                content_style=content_style_from_job(ctx.job),
                default=DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
            )

        with connection() as conn:
            story = repo_daily_story.get_story(conn, daily_story_id)
        story_content = story["story"]  # {scene_title, setting, dialogue, punchline_explain}

        # --- LLM 生成 storyboard（只切镜+台词，不写画面概述）---
        scenes_data = llm_mgr.generate_daily_script(
            story_content,
            job=ctx.job,
            chars_per_sec=chars_per_sec,
        )
        scenes = scenes_data.get("scenes") or []
        if not scenes:
            raise RuntimeError("generate_daily_script returned empty scenes")

        # --- 转换为标准格式 ---
        narration_parts: list[str] = []
        segments: list[dict] = []
        next_index = 1

        for scene_pos, scene in enumerate(scenes, start=1):
            job_cancel.raise_if_cancelled(job_id)
            raw_lines = scene.get("dialogue") or scene.get("dialogue_lines") or []
            if raw_lines and isinstance(raw_lines[0], dict):
                # 过滤纯标点行（如……TTS 无法合成）
                raw_lines = [
                    d for d in raw_lines
                    if re.search(r"[\u4e00-\u9fff\w]", d.get("text") or d.get("line") or "")
                ]
                if not raw_lines:
                    logger.warning(
                        "scene %d: all dialogue lines are pure punctuation, skipping",
                        scene_pos,
                    )
                    continue
                # 新格式: [{"speaker": "昭昭", "text": "台词"}, ...]
                segment_text = "".join(
                    str(d.get("text") or d.get("line") or "") for d in raw_lines
                )
                dialogue = [
                    {
                        "speaker": d.get("speaker", ""),
                        "text": d.get("text") or d.get("line") or "",
                    }
                    for d in raw_lines
                ]
            else:
                # 兼容旧格式: ["台词1", "台词2", ...]
                segment_text = "".join(str(l) for l in raw_lines)
                dialogue = []
            if not str(segment_text).strip():
                logger.warning("scene %d: empty text after parse, skipping", scene_pos)
                continue
            narration_parts.append(segment_text)

            # 按实际字数 ÷ 语速基准 估算分镜时长，不依赖 LLM
            seg_chars = len(segment_text)
            duration_sec = round(seg_chars / chars_per_sec, 1)

            from app.services.daily_story.prompts import DAILY_SCRIPT_MAX_SEGMENT_SEC

            if duration_sec > DAILY_SCRIPT_MAX_SEGMENT_SEC:
                logger.warning(
                    "segment %d duration=%.1fs exceeds %.0fs limit "
                    "(chars=%d, rate=%.1f): %s",
                    next_index,
                    duration_sec,
                    DAILY_SCRIPT_MAX_SEGMENT_SEC,
                    seg_chars,
                    chars_per_sec,
                    segment_text[:80],
                )

            seg: dict = {
                "segment_index": next_index,
                "text": segment_text,
                "duration_sec": duration_sec,
            }
            shot_type = str(scene.get("shot_type") or "").strip()
            if shot_type:
                seg["shot_type"] = shot_type
            if dialogue:
                seg["dialogue"] = dialogue
            segments.append(seg)
            next_index += 1

        narration = "".join(narration_parts)
        title = (story_content.get("scene_title") or ctx.job.get("title") or "").strip()

        # 从 story 计算总字数
        total_chars = sum(len(d.get("line", "")) for d in (story_content.get("dialogue") or []))

        from app.services.llm.llm_deepseek import _VISUAL_STYLE_BY_CONTENT_STYLE
        script = {
            "title": title,
            "narration": narration,
            "word_count": len(narration),
            "segments": segments,
            "total_duration_seconds": sum(s["duration_sec"] for s in segments),
            "daily_story_id": daily_story_id,
            "daily_story_theme": story.get("theme", ""),
            "setting": str(story_content.get("setting") or "").strip(),
            "total_chars": total_chars,
            "visual_style": _VISUAL_STYLE_BY_CONTENT_STYLE["daily_story"],
            "content_style": "daily_story",
        }

        # --- 画面概述：与主线统一走 A2 ---
        llm_mgr.fill_visual_briefs(script, job=ctx.job)
        from app.services.daily_story.cast import (
            scrub_cast_leaks,
            speakers_from_dialogue,
        )

        for seg in script.get("segments") or []:
            allowed = speakers_from_dialogue(seg.get("dialogue") or [])
            cleaned = scrub_cast_leaks(str(seg.get("visual_brief") or ""), allowed)
            if cleaned != seg.get("visual_brief"):
                logger.warning(
                    "segment %d visual_brief scrubbed cast leaks "
                    "(speakers=%s): %r -> %r",
                    seg.get("segment_index"),
                    sorted(allowed),
                    str(seg.get("visual_brief") or "")[:120],
                    cleaned[:120],
                )
                seg["visual_brief"] = cleaned

        # --- 标题优化（chat 固定 ≤10 字，不跟全局 MAX_TITLE_LENGTH） ---
        if not ctx.script_skip_title_optimize:
            max_len = CHAT_TITLE_MAX_LEN
            try:
                prompts = build_chat_title_prompts(
                    title,
                    story_content,
                    max_title_length=max_len,
                )
                client = llm_mgr._get_client()
                raw, _ = client._chat_json(
                    prompts["system"],
                    prompts["user"],
                    thinking_enabled=False,
                    temperature=0.8,
                )
                optimized = parse_title_optimize_payload(raw, max_title_len=max_len)
                if optimized and optimized != title:
                    script["draft_title"] = title
                    script["title"] = collapse_title_whitespace(optimized)
                    with connection() as conn:
                        repo_job_log.append_log(
                            conn,
                            job_id,
                            self.name,
                            f"chat title optimized: {title!r} -> {script['title']!r}",
                        )
            except Exception as exc:
                with connection() as conn:
                    repo_job_log.append_log(
                        conn,
                        job_id,
                        self.name,
                        f"chat title optimize failed, keep draft: {exc}",
                        level="warning",
                    )
        # 清除 LLM 原生 img2img_prompt / motion_prompt，走标准 fill_image_prompts 流程
        for seg in script["segments"]:
            seg.pop("image_prompt", None)
            seg.pop("motion_prompt", None)

        # 先标关键帧，再 fill：关键帧走人物微动 motion，其余走环境微动
        from app.utils.job_info import (
            CONTENT_STYLE_DAILY_STORY,
            apply_keyframe_video_providers,
        )

        keyframe_indices = apply_keyframe_video_providers(script.get("segments") or [])

        # 用标准流程生成文生图 + 运动提示词（含内部质量校验与重试）
        llm_mgr.fill_image_prompts_with_retries(script, job=ctx.job)

        # 给 image_prompt 添加固定前后缀（LLM 只输出场景核心内容）
        from app.services.script.image_prompt import wrap_image_prompts

        wrap_image_prompts(script.get("segments") or [], content_style=CONTENT_STYLE_DAILY_STORY)

        with connection() as conn:
            repo_job.update_job(
                conn,
                job_id,
                title=script["title"],
                script_json=script,
            )
            repo_segment.insert_segments(conn, job_id, script["segments"])
            keyframe_note = (
                f", keyframes={keyframe_indices}" if keyframe_indices else ""
            )
            repo_job_log.append_log(
                conn,
                job_id,
                self.name,
                f"daily story script ready: scenes={len(scenes)}, "
                f"narration_chars={len(narration)}, total_chars={total_chars}, "
                f"total_duration={script['total_duration_seconds']:.1f}s"
                f"{keyframe_note}",
            )
