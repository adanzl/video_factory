from __future__ import annotations

import re
from pathlib import Path

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.intro import generate_intro
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


def _generate_cover(job: dict, cover_path: Path, width: int, height: int) -> None:
    import tempfile
    from PIL import Image
    from app.config import get_settings
    from app.services.intro.title_layout import render_feed_title
    from app.services.visual.image_agnes import AgnesImageProvider
    from app.services.visual.text_render import load_cjk_font
    from app.services.visual.title_render import render_text_rgba

    script = job.get("script_json") or {}
    title = resolve_intro_title(job)
    visual_style = (script.get("visual_style") or "").strip()
    segments = script.get("segments") or []
    first_prompt = ""
    for seg in segments:
        ip = (seg.get("image_prompt") or "").strip()
        if ip:
            first_prompt = ip
            break

    if width > height:
        cw, ch = 1280, 720
    else:
        cw, ch = 720, 1280
    is_landscape = cw > ch
    host_visible = 0.58 if is_landscape else 1.0

    cover_prompt = (
        f"视频封面，{cw}x{ch}，标题文字区域留白于下方三分之一区域。"
        f"画面内容与视频一致：{first_prompt or visual_style or title}"
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        AgnesImageProvider().generate(cover_prompt, tmp_path, size=f"{cw}x{ch}")
        img = Image.open(tmp_path).convert("RGBA")

        settings = get_settings()
        host = Image.open(settings.host_intro_path).convert("RGBA")
        max_w = int(cw * (0.72 if is_landscape else 0.94))
        max_h = int(ch * (0.88 if is_landscape else 0.42))
        shrink = min(1.0, max_w / host.size[0], max_h / host.size[1])
        host = host.resize((int(host.size[0]*shrink), int(host.size[1]*shrink)), Image.Resampling.LANCZOS)
        hx = (cw - host.size[0]) // 2
        hy = ch - int(host.size[1] * host_visible) if host_visible < 1.0 else ch - host.size[1]
        img.paste(host, (hx, hy), host)

        brand_font = load_cjk_font(max(24, int(72 * ch / 1080)))
        brand = render_text_rgba(settings.brand_name, brand_font, fill=(255,255,255,255), stroke_width=3, stroke_fill=(60,30,15,255))
        img.paste(brand, ((cw - brand.size[0]) // 2, int(ch * 0.04)), brand)

        moon_diameter = int(min(cw, ch) * 0.52)
        text_max_w = int(moon_diameter * 1.28)
        class _CoverTheme:
            title_fill = (255, 210, 50, 255)
            title_stroke = (60, 30, 15, 255)
        text_block = render_feed_title(title, _CoverTheme(), text_max_w, max_size=200, min_size=90, max_lines=3, max_height=int(ch * 0.45))
        tx = (cw - text_block.size[0]) // 2
        ty = int(ch * 0.36) - text_block.size[1] // 2
        img.paste(text_block, (tx, ty), text_block)

        img.convert("RGB").save(cover_path, quality=92)
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
    _generate_cover(job, cover_path, width, height)

    with connection() as conn:
        updates: dict = {
            "intro_path": str(intro_path.resolve()),
            "cover_path": str(cover_path.resolve()),
        }
        if _normalize_title(str(job.get("title") or "")) != title:
            updates["title"] = title
        job_repo.update_job(conn, ctx.job["id"], **updates)
        detail = (
            f"intro at {intro_path}, cover at {cover_path}, title={title}, "
            f"size={width}x{height}, orientation={orient_label}, category={category_label}"
        )
        if ctx.intro_hold_tail_sec is not None:
            detail += f", hold_tail_sec={ctx.intro_hold_tail_sec:.2f}"
        job_log_repo.append_log(conn, ctx.job["id"], stage.name, detail)
