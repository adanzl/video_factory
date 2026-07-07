from __future__ import annotations

import re
from pathlib import Path

from app.repositories import repo_job_log, repo_job
from app.repositories.connection import connection
from app.services.intro import generate_intro
from app.services.intro.cover_layout import (
    build_cover_image_prompt,
    compose_cover_image,
    cover_canvas_size,
)
from app.services.intro.size import is_material_job, resolve_intro_size
from app.utils.job_info import (
    ORIENTATION_AUTO,
    ORIENTATION_PORTRAIT,
    intro_category_from_job,
    intro_generate_category,
    orientation_for_resolve,
)
from app.utils.title_text import prefer_source_punctuation
from worker.context import JobContext
from worker.stages.base import StageExecutor


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", (title or "").strip())


def resolve_intro_title(job: dict) -> str:
    """优先 script_json 定稿标题；若优化仅去掉标点则用 draft_title。"""
    script = job.get("script_json")
    if isinstance(script, dict):
        script_title = _normalize_title(str(script.get("title") or ""))
        draft_title = _normalize_title(str(script.get("draft_title") or ""))
        if script_title:
            if draft_title:
                return prefer_source_punctuation(draft_title, script_title)
            return script_title
    job_title = _normalize_title(str(job.get("title") or ""))
    return job_title or "未命名"


def _orientation_label(
    job: dict,
    *,
    intro_orientation: str | None,
    effective_orientation: str | None,
) -> str:
    if intro_orientation:
        return intro_orientation
    if effective_orientation:
        return effective_orientation
    if is_material_job(job):
        return ORIENTATION_AUTO
    return f"{ORIENTATION_PORTRAIT}(default)"


def _generate_cover_subject_from_narration(title: str, narration: str) -> str:
    """用 LLM 根据标题和口播内容生成封面画面描述。"""
    import logging

    from app.config import get_settings
    from app.services.llm.llm_deepseek import DeepSeekClient

    logger = logging.getLogger(__name__)
    settings = get_settings()
    if not settings.deepseek_api_key:
        logger.warning("no deepseek_api_key, fallback to title for cover subject")
        return title

    system = (
        "你是一个视频封面画面设计师。根据视频标题和口播内容，用一段话描述封面底图应该呈现的画面。\n"
        "要求：\n"
        "1. 描述具体的视觉场景：主体、环境、光照、色调、构图\n"
        "2. 不要出现文字、标题、字幕等元素\n"
        "3. 画面要有冲击力，适合作为视频封面吸引点击\n"
        "4. 风格为写实插画或电影质感\n"
        "5. 80-150字以内\n"
        "仅输出画面描述，不要额外解释。"
    )
    user = f"标题：{title}\n口播内容：{narration}"
    try:
        client = DeepSeekClient()
        result, _ = client._chat(system, user, max_tokens=800, json_mode=False)
        desc = result.strip()
        if desc and len(desc) >= 20:
            logger.info("cover subject generated from narration: '%s'", desc[:80])
            return desc
    except Exception as exc:
        logger.warning("cover subject generation failed: %s", exc)
    logger.warning("cover subject generation returned empty/short result, fallback to title")
    return title


def _cover_subject_from_job(job: dict) -> str:
    """封面底图画面描述：首镜 image_prompt > visual_style > LLM 生成 > 标题。"""
    script = job.get("script_json") or {}
    title = resolve_intro_title(job)
    visual_style = (script.get("visual_style") or "").strip()
    for seg in script.get("segments") or []:
        ip = (seg.get("image_prompt") or "").strip()
        if ip:
            return ip
    if visual_style:
        return visual_style
    # 无 image_prompt 和 visual_style（素材任务）：用 LLM 根据标题+口播生成画面描述
    narration_parts = []
    for seg in script.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if text:
            narration_parts.append(text)
    narration = script.get("narration") or "\n".join(narration_parts)
    if narration and narration.strip():
        return _generate_cover_subject_from_narration(title, narration.strip())
    return title


def _generate_cover(job: dict, cover_path: Path, width: int, height: int) -> None:
    """intro 阶段：Agnes 出底图 + compose_cover_image 叠字，写入 cover.jpg。"""
    import tempfile

    from PIL import Image

    from app.config import get_settings
    from app.services.segment.image.image_agnes import AgnesImageProvider

    settings = get_settings()
    title = resolve_intro_title(job)
    cw, ch, _ = cover_canvas_size(width, height)
    subject = _cover_subject_from_job(job)
    cover_prompt = build_cover_image_prompt(cw=cw, ch=ch, subject=subject)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        AgnesImageProvider().generate(cover_prompt, tmp_path, size=f"{cw}x{ch}")
        img = Image.open(tmp_path)
        composed = compose_cover_image(
            img,
            title,
            brand_name=settings.brand_name,
            host_intro_path=settings.host_intro_path,
        )
        composed.convert("RGB").save(cover_path, quality=92)
    finally:
        tmp_path.unlink(missing_ok=True)


def run_intro_for_category(
    ctx: JobContext,
    job: dict,
    *,
    stage: StageExecutor,
) -> None:
    intro_path = ctx.rel("intro.mp4")
    title = resolve_intro_title(job)
    category_label = intro_category_from_job(job)
    gen_category = intro_generate_category(job)
    effective_orientation = ctx.intro_orientation
    if effective_orientation is None:
        effective_orientation = orientation_for_resolve(job)
    width, height = resolve_intro_size(
        settings=ctx.settings,
        orientation=effective_orientation,
        job=job,
        media_dir=ctx.media_dir,
    )
    orient_label = _orientation_label(
        job,
        intro_orientation=ctx.intro_orientation,
        effective_orientation=effective_orientation,
    )

    generate_intro(
        title,
        intro_path,
        category=gen_category,
        hold_tail_sec=ctx.intro_hold_tail_sec,
        width=width,
        height=height,
    )

    cover_path = ctx.rel("cover.jpg")
    # 与片头同尺寸；合成逻辑见 cover_layout.compose_cover_image
    _generate_cover(job, cover_path, width, height)

    with connection() as conn:
        updates: dict = {
            "intro_path": str(intro_path.resolve()),
            "cover_path": str(cover_path.resolve()),
        }
        if _normalize_title(str(job.get("title") or "")) != title:
            updates["title"] = title
        repo_job.update_job(conn, ctx.job["id"], **updates)
        detail = (
            f"intro at {intro_path}, cover at {cover_path}, title={title}, "
            f"size={width}x{height}, orientation={orient_label}, category={category_label}"
        )
        if ctx.intro_hold_tail_sec is not None:
            detail += f", hold_tail_sec={ctx.intro_hold_tail_sec:.2f}"
        repo_job_log.append_log(conn, ctx.job["id"], stage.name, detail)
