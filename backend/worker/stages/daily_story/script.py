"""日常故事（对话）分镜生成阶段。"""

from __future__ import annotations

import logging

from app.repositories import repo_daily_story, repo_job, repo_job_log, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.utils.job_cancel import job_cancel
from app.utils.job_info import parse_job_info
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)


class DailyScriptStage(StageExecutor):
    """日常对话故事 → 标准分镜 script_json。

    从 job.info.daily_story_id 加载故事，调用 LLM 生成 storyboard
    （scenes 含 dialogue_lines / visual_description / img2img_prompt），
    转换为标准 script_json 格式供下游 TTS / Segment / Merge 使用。
    """

    name = "script"

    def run(self, ctx: JobContext) -> None:
        job_id = ctx.job["id"]
        info = parse_job_info(ctx.job.get("info"))
        daily_story_id = info.get("daily_story_id")
        if not daily_story_id:
            raise RuntimeError("daily_story_id not found in job info")

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
            lines = scene.get("dialogue_lines") or []
            segment_text = "".join(str(l) for l in lines)
            narration_parts.append(segment_text)

            segments.append({
                "segment_index": i,
                "text": segment_text,
                "visual_brief": (scene.get("visual_description") or "").strip(),
                "image_prompt": (scene.get("img2img_prompt") or "").strip(),
                "duration_sec": scene.get("duration_seconds", 10),
            })

        narration = "".join(narration_parts)
        title = (story_content.get("scene_title") or ctx.job.get("title") or "").strip()

        # 从 story 计算总字数
        total_chars = sum(len(d.get("line", "")) for d in (story_content.get("dialogue") or []))

        script = {
            "title": title,
            "narration": narration,
            "word_count": len(narration),
            "segments": segments,
            "total_duration_seconds": scenes_data.get("total_duration_seconds", 0),
            "daily_story_id": daily_story_id,
            "daily_story_theme": story.get("theme", ""),
            "total_chars": total_chars,
        }

        with connection() as conn:
            repo_job.update_job(conn, job_id, script_json=script)
            repo_segment.insert_segments(conn, job_id, segments)
            repo_job_log.append_log(
                conn,
                job_id,
                self.name,
                f"daily story script ready: scenes={len(scenes)}, "
                f"narration_chars={len(narration)}, total_chars={total_chars}",
            )
