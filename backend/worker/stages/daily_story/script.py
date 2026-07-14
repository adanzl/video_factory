"""日常故事（对话）分镜生成阶段。"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.repositories import repo_daily_story, repo_job, repo_job_log, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.script.optimize_title import (
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
    （scenes 含 dialogue_lines / visual_description），
    转换为标准 script_json 格式后走 fill_image_prompts 生成提示词，
    供下游 TTS / Segment / Merge 使用。
    """

    name = "script"

    def run(self, ctx: JobContext) -> None:
        job_id = ctx.job["id"]
        info = parse_job_info(ctx.job.get("info"))
        daily_story_id = info.get("daily_story_id")
        if not daily_story_id:
            raise RuntimeError("daily_story_id not found in job info")

        # 从 job.info 读取语速，默认 3.0 字/秒（儿童故事音色）
        chars_per_sec = float(info.get("speech_chars_per_sec") or 3.0)

        with connection() as conn:
            story = repo_daily_story.get_story(conn, daily_story_id)
        story_content = story["story"]  # {scene_title, setting, dialogue, punchline_explain}

        # --- LLM 生成 storyboard ---
        scenes_data = llm_mgr.generate_daily_script(story_content, job=ctx.job)
        scenes = scenes_data.get("scenes") or []
        if not scenes:
            raise RuntimeError("generate_daily_script returned empty scenes")

        # --- 转换为标准格式 ---
        narration_parts: list[str] = []
        segments: list[dict] = []

        for i, scene in enumerate(scenes, start=1):
            job_cancel.raise_if_cancelled(job_id)
            raw_lines = scene.get("dialogue") or scene.get("dialogue_lines") or []
            if raw_lines and isinstance(raw_lines[0], dict):
                # 新格式: [{"speaker": "昭昭", "text": "台词"}, ...]
                segment_text = "".join(str(d.get("text") or d.get("line") or "") for d in raw_lines)
                dialogue = [
                    {"speaker": d.get("speaker", ""), "text": d.get("text") or d.get("line") or ""}
                    for d in raw_lines
                ]
            else:
                # 兼容旧格式: ["台词1", "台词2", ...]
                segment_text = "".join(str(l) for l in raw_lines)
                dialogue = []
            narration_parts.append(segment_text)

            # 按实际字数 ÷ 语速基准 估算分镜时长，不依赖 LLM
            seg_chars = len(segment_text)
            duration_sec = round(seg_chars / chars_per_sec, 1)

            seg: dict = {
                "segment_index": i,
                "text": segment_text,
                "visual_brief": (scene.get("visual_description") or "").strip(),
                "duration_sec": duration_sec,
            }
            if dialogue:
                seg["dialogue"] = dialogue
            segments.append(seg)

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
            "total_chars": total_chars,
            "visual_style": _VISUAL_STYLE_BY_CONTENT_STYLE["daily_story"]
        }

        # --- 标题优化（独立方案：chat 专用提示词，直调 _chat_json） ---
        if not ctx.script_skip_title_optimize:
            max_len = (
                ctx.script_max_title_length
                if ctx.script_max_title_length is not None
                else get_settings().max_title_length
            )
            try:
                prompts = build_chat_title_prompts(
                    title,
                    story_content,
                    max_title_length=max_len,
                )
                client = llm_mgr._get_client()
                raw, _ = client._chat_json(
                    prompts["system"], prompts["user"], thinking_enabled=False
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

        # 用标准流程生成文生图 + 运动提示词（含内部质量校验与重试）
        llm_mgr.fill_image_prompts(script, job=ctx.job)

        with connection() as conn:
            repo_job.update_job(
                conn,
                job_id,
                title=script["title"],
                script_json=script,
            )
            repo_segment.insert_segments(conn, job_id, script["segments"])
            repo_job_log.append_log(
                conn,
                job_id,
                self.name,
                f"daily story script ready: scenes={len(scenes)}, "
                f"narration_chars={len(narration)}, total_chars={total_chars}, total_duration={script['total_duration_seconds']:.1f}s",
            )
