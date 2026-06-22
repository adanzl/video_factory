"""媒体相关工具（口播字数估算等）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.media.ffmpeg_utils import probe_duration, probe_video_size

if TYPE_CHECKING:
    from app.config import Config

# 中文口播约 5 字/秒（16s ≈ 80 字；与 CosyVoice 实际语速对齐）
NARRATION_CHARS_PER_SEC = 5.0
NARRATION_FILL_RATIO = 0.92
NARRATION_MIN_CHARS = 200
NARRATION_MAX_CHARS = 3000
# 略低于硬性下限时放行（与 LLM 实际产出对齐，避免 90% 附近反复打回）
NARRATION_SOFT_MIN_RATIO = 0.90


def estimate_narration_target_words(duration_sec: float) -> int:
    target = int(duration_sec * NARRATION_CHARS_PER_SEC * NARRATION_FILL_RATIO)
    return max(NARRATION_MIN_CHARS, min(NARRATION_MAX_CHARS, target))


def segment_text_char_cap(segment_target_sec: float) -> int:
    """单镜口播 text 字数上限（5 字/秒 × segment_target_sec）。"""
    return max(20, int(segment_target_sec * NARRATION_CHARS_PER_SEC))


def storyboard_compact_output(
    narration_target: int,
    segment_target_sec: float,
) -> bool:
    """长稿分镜是否用紧凑 JSON（省略 narration/word_count，后端拼接）。"""
    if segment_target_sec <= 0:
        return narration_target >= 900
    cap = segment_text_char_cap(segment_target_sec)
    seg_count = max(5, (narration_target + cap - 1) // cap)
    return narration_target >= 900 or seg_count >= 10


def body_duration_for_target_final(
    target_final_sec: float,
    *,
    intro_budget_sec: float,
) -> float:
    """成片目标时长扣除片头预算后的正文秒数。"""
    return max(30.0, target_final_sec - intro_budget_sec)


def default_narration_target_words(settings: Config | None = None) -> int:
    """standard 线默认口播目标字数（由 TARGET_FINAL_DURATION_SEC 推导）。"""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    body = body_duration_for_target_final(
        settings.target_final_duration_sec,
        intro_budget_sec=settings.intro_duration_budget_sec,
    )
    return estimate_narration_target_words(body)


def min_narration_chars_for_target(narration_target_words: int | None = None) -> int:
    """口播字数校验下限（与 standard script 阶段一致）。"""
    target = max(NARRATION_MIN_CHARS, narration_target_words or default_narration_target_words())
    return max(NARRATION_MIN_CHARS, int(target * 0.67))


def narration_soft_min_chars(required_chars: int) -> int:
    """略低于硬性下限时仍放行（带警告）。"""
    return max(NARRATION_MIN_CHARS, int(required_chars * NARRATION_SOFT_MIN_RATIO))


def narration_target_for_minutes(
    minutes: float,
    *,
    chars_per_sec: float = NARRATION_CHARS_PER_SEC,
    intro_budget_sec: float = 2.0,
) -> int:
    """按成片分钟数估算口播目标字数（5 字/秒）。"""
    body = max(30.0, minutes * 60.0 - intro_budget_sec)
    target = int(body * chars_per_sec * NARRATION_FILL_RATIO)
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
