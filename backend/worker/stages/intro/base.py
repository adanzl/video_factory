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
    from PIL import Image, ImageDraw, ImageFont
    from app.config import get_settings
    from app.services.visual.image_agnes import AgnesImageProvider

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
    cw = min(width, 1280)
    ch = min(height, 720)
    cover_prompt = (
        f"视频封面，{cw}x{ch}，标题文字区域留白于下方三分之一区域。"
        f"画面内容与视频一致：{first_prompt or visual_style or title}"
    )
    size = f"{cw}x{ch}"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        AgnesImageProvider().generate(cover_prompt, tmp_path, size=size)
        img = Image.open(tmp_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font_path = str(get_settings().font_path)
        font_size = max(24, min(cw, ch) // 20)
        font = ImageFont.truetype(font_path, font_size)
        lines = _wrap_text(title, font, cw - 80)
        line_h = font_size * 3 // 2
        text_h = len(lines) * line_h + 20
        bar_y = ch - text_h - 40
        bar = Image.new("RGBA", (cw, text_h + 40), (0, 0, 0, 160))
        img.paste(bar, (0, bar_y), bar)
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            _, _, tw, _ = draw.textbbox((0, 0), line, font=font)
            x = (width - tw) / 2
            y = bar_y + 20 + i * line_h
            _draw_stroke(draw, x, y, line, font)
        img.convert("RGB").save(cover_path, quality=92)
    finally:
        tmp_path.unlink(missing_ok=True)


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for seg in text.split("\n"):
        buf = ""
        for ch in seg:
            test = buf + ch
            if font.getlength(test) > max_width and buf:
                lines.append(buf)
                buf = ch
            else:
                buf = test
        if buf:
            lines.append(buf)
    return lines


def _draw_stroke(draw, x: float, y: float, text: str, font) -> None:
    stroke_ranges = [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]
    for dx, dy in stroke_ranges:
        draw.text((x + dx, y + dy), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="white")


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
