"""媒体相关工具（口播字数估算等）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.media.ffmpeg_utils import probe_duration, probe_video_size

if TYPE_CHECKING:
    from app.config import Config
    from app.services.llm.llm_script_timeline import VideoTimeline

# 中文口播约 5 字/秒（16s ≈ 80 字；与 CosyVoice 实际语速对齐）
NARRATION_CHARS_PER_SEC = 5.0
NARRATION_FILL_RATIO = 0.92
NARRATION_MAX_CHARS = 3000
# 口播绝对硬底（仅用于「明显过短」校验，不参与时长估算）
NARRATION_ABS_MIN_CHARS = 20
# 口播验收下限：目标字数的 85%（LLM 重试与 script 校验对齐）
NARRATION_ACCEPT_RATIO = 0.85
# LLM prompt 写作目标：目标字数的 95%（高于验收下限，提高一次写满概率）
NARRATION_WRITING_TARGET_RATIO = 0.95
# 绝对硬底：目标字数的 67%（主题实在撑不满时带警告放行）
NARRATION_HARD_MIN_RATIO = 0.67
# 略低于绝对硬底时放行（避免 90% 硬底附近反复打回）
NARRATION_SOFT_MIN_RATIO = 0.90


def estimate_narration_target_words(duration_sec: float) -> int:
    target = int(duration_sec * NARRATION_CHARS_PER_SEC * NARRATION_FILL_RATIO)
    return max(1, min(NARRATION_MAX_CHARS, target))


def material_min_audio_duration_sec(base_duration_sec: float | None) -> float:
    """素材线配音最短时长：随基底视频缩放，避免短素材被 30s 硬门槛误杀。"""
    if base_duration_sec is None or base_duration_sec <= 0:
        return 5.0
    return max(5.0, base_duration_sec * 0.70)


def material_final_min_duration_sec(
    base_duration_sec: float,
    *,
    intro_duration_sec: float = 0.0,
) -> float:
    """素材线成片最短时长：基底 + 片头，留约 15% 容差。"""
    expected = max(0.0, base_duration_sec) + max(0.0, intro_duration_sec)
    slack = max(2.0, expected * 0.15)
    return max(5.0, expected - slack)


def segment_text_char_cap(segment_target_sec: float) -> int:
    """单镜口播 text 字数上限（5 字/秒 × segment_target_sec）。"""
    return max(20, int(segment_target_sec * NARRATION_CHARS_PER_SEC))


def narration_segment_basis_chars(
    narration: str,
    narration_target_words: int | None = None,
) -> int:
    """规划最少分镜数时用的口播字数（实际 narration 与目标取较大值）。"""
    chars = len(re.sub(r"\s+", "", narration or ""))
    if narration_target_words is None or isinstance(narration_target_words, bool):
        return chars
    target = int(narration_target_words)
    if target <= 0:
        return chars
    return max(chars, target)


def min_segment_count_for_narration(
    narration: str,
    segment_target_sec: float,
    *,
    narration_target_words: int | None = None,
) -> int:
    """按单镜字数上限估算 narration 至少应拆成的段数。"""
    cap = segment_text_char_cap(segment_target_sec)
    basis = narration_segment_basis_chars(narration, narration_target_words)
    return max(1, (basis + cap - 1) // cap)


def segment_narration_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def estimate_segment_duration_sec(
    text: str,
    *,
    segment_target_sec: float | None = None,
) -> float:
    """按口播字数估算单镜时长（秒）。"""
    chars = segment_narration_chars(text)
    duration = chars / NARRATION_CHARS_PER_SEC if chars else 0.0
    if segment_target_sec and segment_target_sec > 0:
        duration = min(duration, float(segment_target_sec))
    return round(max(0.1, duration), 3)


def assign_segment_timings(
    script: dict[str, Any],
    *,
    segment_target_sec: float | None = None,
    video_timeline: VideoTimeline | None = None,
) -> dict[str, Any]:
    """为 script.segments 填充 start_sec / end_sec / duration_sec。"""
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        return script

    slots_by_index: dict[int, object] = {}
    if video_timeline is not None:
        for slot in video_timeline.slots:
            slots_by_index[int(slot.index)] = slot

    cursor = 0.0
    ordered = sorted(segments, key=lambda seg: int(seg.get("segment_index") or 0))
    for seg in ordered:
        if not isinstance(seg, dict):
            continue
        idx = int(seg.get("segment_index") or 0)
        slot = slots_by_index.get(idx)
        if slot is not None:
            start = round(float(slot.start_sec), 3)
            end = round(float(slot.end_sec), 3)
            duration = round(float(slot.duration_sec), 3)
        else:
            duration = estimate_segment_duration_sec(
                str(seg.get("text") or ""),
                segment_target_sec=segment_target_sec,
            )
            start = round(cursor, 3)
            end = round(start + duration, 3)
            cursor = end
        seg["start_sec"] = start
        seg["end_sec"] = end
        seg["duration_sec"] = duration

    script["segments"] = ordered
    if ordered and isinstance(ordered[-1], dict):
        script["total_duration_sec"] = float(ordered[-1].get("end_sec") or 0.0)
    return script


def narration_writing_target_chars(narration_target_words: int | None = None) -> int:
    """LLM prompt 要求的写作目标字数（目标字数的 95%）。"""
    target = narration_target_words or default_narration_target_words()
    return max(1, int(target * NARRATION_WRITING_TARGET_RATIO))


def narration_writing_plan(
    narration_target: int,
    segment_target_sec: float = 0,
) -> dict[str, int]:
    """口播分段写作计划（prompt 字数预算与 LLM 校验共用）。"""
    hard_min = narration_accept_min_chars(narration_target)
    writing_target = narration_writing_target_chars(narration_target)
    if segment_target_sec <= 0:
        seg_count = max(6, (writing_target + 39) // 40)
        cap = 0
        per_min = max(30, (writing_target + seg_count - 1) // seg_count)
        per_lo = per_min
        per_hi = max(per_min + 10, 40)
    else:
        cap = segment_text_char_cap(segment_target_sec)
        seg_count = max(5, (writing_target + cap - 1) // cap)
        per_min = max(20, min(cap - 5, (writing_target + seg_count - 1) // seg_count))
        per_lo = max(20, int(cap * 0.65))
        per_hi = cap
    return {
        "target": narration_target,
        "writing_target": writing_target,
        "hard_min": hard_min,
        "seg_count_min": seg_count,
        "per_seg_min": per_min,
        "per_seg_lo": per_lo,
        "per_seg_hi": per_hi,
        "segment_cap": cap,
    }


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
    """口播绝对硬底（主题撑不满时最低可接受，带警告）。"""
    target = narration_target_words or default_narration_target_words()
    return max(1, int(target * NARRATION_HARD_MIN_RATIO))


def narration_accept_min_chars(narration_target_words: int | None = None) -> int:
    """口播验收下限（LLM 须达到；与 standard script 阶段重试阈值一致）。"""
    target = narration_target_words or default_narration_target_words()
    return max(1, int(target * NARRATION_ACCEPT_RATIO))


def narration_soft_min_chars(required_chars: int) -> int:
    """略低于硬性下限时仍放行（带警告）。"""
    return max(1, int(required_chars * NARRATION_SOFT_MIN_RATIO))


def narration_target_for_minutes(
    minutes: float,
    *,
    chars_per_sec: float = NARRATION_CHARS_PER_SEC,
    intro_budget_sec: float = 2.0,
) -> int:
    """按成片分钟数估算口播目标字数（5 字/秒）。"""
    body = max(30.0, minutes * 60.0 - intro_budget_sec)
    target = int(body * chars_per_sec * NARRATION_FILL_RATIO)
    return max(1, min(NARRATION_MAX_CHARS, target))


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
