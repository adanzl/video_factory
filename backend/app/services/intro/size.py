"""片头输出尺寸：竖屏 / 横屏 / 自动（素材基底）。"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.utils.media import base_video_size

INTRO_ORIENTATION_PORTRAIT = "portrait"
INTRO_ORIENTATION_LANDSCAPE = "landscape"


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

    pipeline = (job.get("pipeline") or "standard").strip()
    if pipeline == "material":
        size = base_video_size(job=job, media_dir=media_dir)
        if size:
            return size
    return portrait_size(settings)
