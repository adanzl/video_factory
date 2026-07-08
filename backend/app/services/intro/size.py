"""片头输出尺寸：竖屏 / 横屏 / 自动（素材基底）。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings
from app.repositories import repo_material_video
from app.repositories.connection import connection
from app.services.media.ffmpeg_utils import probe_video_size
from app.utils.media import _coerce_positive_int, base_video_size

logger = logging.getLogger(__name__)

INTRO_ORIENTATION_PORTRAIT = "portrait"
INTRO_ORIENTATION_LANDSCAPE = "landscape"
PIPELINE_MATERIAL = "material"


def parse_intro_orientation(value: str | None) -> str | None:
    """解析 orientation 参数，返回 portrait / landscape / None（自动）。"""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized in {"auto", "自动", "default"}:
        return None
    if normalized in {INTRO_ORIENTATION_PORTRAIT, "竖屏", "vertical", "9:16", "9x16"}:
        return INTRO_ORIENTATION_PORTRAIT
    if normalized in {INTRO_ORIENTATION_LANDSCAPE, "横屏", "horizontal", "16:9", "16x9"}:
        return INTRO_ORIENTATION_LANDSCAPE
    raise ValueError(f"无效的片头方向: {value!r}，可选 portrait / landscape / auto")


def is_material_job(job: dict) -> bool:
    if (job.get("pipeline") or "standard").strip() == PIPELINE_MATERIAL:
        return True
    return job.get("material_id") is not None


def portrait_size(settings: Settings) -> tuple[int, int]:
    w, h = settings.video_width, settings.video_height
    if w > h:
        w, h = h, w
    return w, h


def landscape_size(settings: Settings) -> tuple[int, int]:
    w, h = settings.video_width, settings.video_height
    if h > w:
        w, h = h, w
    return w, h


def design_size_for_source(
    source_width: int,
    source_height: int,
    settings: Settings,
) -> tuple[int, int]:
    """按源视频横竖屏选择设计画布（竖屏 9:16 / 横屏 16:9）。"""
    if source_width > source_height:
        return landscape_size(settings)
    return portrait_size(settings)


def _material_record_size(job: dict) -> tuple[int, int] | None:
    material_id = job.get("material_id")
    if not material_id:
        return None
    try:
        with connection() as conn:
            material = repo_material_video.get_material_video(conn, int(material_id))
    except (KeyError, TypeError, ValueError):
        return None

    width = _coerce_positive_int(material.get("width"))
    height = _coerce_positive_int(material.get("height"))
    if width and height:
        return width, height

    file_path = material.get("file_path")
    if file_path:
        path = Path(str(file_path))
        if path.is_file():
            try:
                return probe_video_size(path)
            except Exception as exc:
                logger.warning("probe material source failed: %s", exc)
    return None


def resolve_auto_intro_size(
    *,
    settings: Settings,
    job: dict,
    media_dir: Path,
) -> tuple[int, int] | None:
    """自动模式：已归一化的任务基底 → 素材库原始尺寸推断设计画布。"""
    try:
        size = base_video_size(job=job, media_dir=media_dir)
        if size:
            return size
    except Exception as exc:
        logger.warning("base_video_size failed for job %s: %s", job.get("id"), exc)

    raw = _material_record_size(job)
    if raw:
        return design_size_for_source(raw[0], raw[1], settings)
    return None


def resolve_intro_size(
    *,
    settings: Settings,
    orientation: str | None,
    job: dict,
    media_dir: Path,
) -> tuple[int, int]:
    """确定片头宽高。orientation 为 None 时：素材任务跟基底，其余跟全局竖屏配置。"""
    if orientation == INTRO_ORIENTATION_PORTRAIT:
        return portrait_size(settings)
    if orientation == INTRO_ORIENTATION_LANDSCAPE:
        return landscape_size(settings)

    if is_material_job(job):
        size = resolve_auto_intro_size(settings=settings, job=job, media_dir=media_dir)
        if size:
            return size
        logger.warning(
            "intro auto size fallback to portrait for material job %s "
            "(no base_meta/base.mp4/material dimensions)",
            job.get("id"),
        )
    return portrait_size(settings)
