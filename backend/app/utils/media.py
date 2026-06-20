"""媒体相关工具（口播字数估算等）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.media.ffmpeg_utils import probe_duration, probe_video_size

# 中文口播约 7.5 字/秒（12s ≈ 90 字）
NARRATION_CHARS_PER_SEC = 7.5
NARRATION_FILL_RATIO = 0.92
NARRATION_MIN_CHARS = 200
NARRATION_MAX_CHARS = 3000


def estimate_narration_target_words(duration_sec: float) -> int:
    target = int(duration_sec * NARRATION_CHARS_PER_SEC * NARRATION_FILL_RATIO)
    return max(NARRATION_MIN_CHARS, min(NARRATION_MAX_CHARS, target))


def _read_base_meta(media_dir: Path) -> dict:
    meta_path = media_dir / "base_meta.json"
    if not meta_path.is_file():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        coerced = int(value)
        return coerced if coerced > 0 else None
    return None


def _pair_from_meta(data: dict) -> tuple[int, int] | None:
    width = _coerce_positive_int(data.get("width"))
    height = _coerce_positive_int(data.get("height"))
    if width and height:
        return width, height
    return None


def base_video_size(*, job: dict, media_dir: Path) -> tuple[int, int] | None:
    """素材任务基底视频分辨率；优先 base_meta，其次探测 base.mp4。"""
    size = _pair_from_meta(_read_base_meta(media_dir))
    if size:
        return size

    base_path = job.get("base_path")
    if base_path:
        path = Path(str(base_path))
        if path.is_file():
            return probe_video_size(path)

    fallback = media_dir / "base.mp4"
    if fallback.is_file():
        return probe_video_size(fallback)
    return None


def base_video_duration_sec(*, job: dict, media_dir: Path) -> float | None:
    base_path = job.get("base_path")
    if base_path:
        path = Path(str(base_path))
        if path.is_file():
            return probe_duration(path)

    data = _read_base_meta(media_dir)
    if data:
        duration = data.get("duration_sec")
        if isinstance(duration, (int, float)) and duration > 0:
            return float(duration)

    fallback = media_dir / "base.mp4"
    if fallback.is_file():
        return probe_duration(fallback)
    return None
