"""TTS 段音频裁切：按 CosyVoice 字级时间戳去掉段首/段尾空白。

段首：按首字时间戳强制裁切前置空白（含伪影），保留 head_pad_ms 余量防止切掉句首。
段尾：当前禁用（返回 0）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.media.ffmpeg_utils import probe_duration, run_ffmpeg
from app.services.tts.phrase_timing import TimedWord

# 标点字符集，用于跳过句首标点定位第一个实字
_PUNCT_RE = re.compile(r"^[。！？；：，,.!?;:…—·~～'\"）】》〉）\]]+$")

logger = logging.getLogger(__name__)

__all__ = [
    "TrimPlan",
    "apply_tts_segment_trim",
    "plan_tts_segment_trim",
    "shift_word_timestamps",
    "trim_audio_trailing",
]


@dataclass(frozen=True)
class TrimPlan:
    leading_ms: int
    trailing_ms: int

    @property
    def total_ms(self) -> int:
        return self.leading_ms + self.trailing_ms


def shift_word_timestamps(words: list[TimedWord], delta_ms: int) -> list[TimedWord]:
    if delta_ms <= 0:
        return list(words)
    shifted: list[TimedWord] = []
    for word in words:
        begin = max(0, word.begin_time_ms - delta_ms)
        end = max(begin, word.end_time_ms - delta_ms)
        shifted.append(
            TimedWord(
                text=word.text,
                begin_time_ms=begin,
                end_time_ms=end,
                begin_index=word.begin_index,
                end_index=word.end_index,
            )
        )
    return shifted


def plan_tts_segment_trim(
    words: list[TimedWord],
    *,
    duration_ms: int,
    head_pad_ms: int = 50,
    tail_pad_ms: int = 20,
    min_leading_silence_ms: int = 500,
    min_trailing_ms: int = 50,
) -> TrimPlan:
    """计算裁切计划：按首字时间戳强制裁切前置空白（含伪影），段尾当前禁用。"""
    _ = tail_pad_ms, min_trailing_ms, min_leading_silence_ms
    if not words or duration_ms <= 0:
        return TrimPlan(leading_ms=0, trailing_ms=0)

    # 跳过句首标点，找到第一个实字
    first_real_idx = 0
    for i, w in enumerate(words):
        if w.text.strip() and not _PUNCT_RE.fullmatch(w.text.strip()):
            first_real_idx = i
            break
    else:
        return TrimPlan(leading_ms=0, trailing_ms=0)

    first_begin = words[first_real_idx].begin_time_ms
    # 始终按首字位置裁切（去掉静音阈值），保留 head_pad_ms 防止切到发音
    leading = max(0, first_begin - head_pad_ms)

    return TrimPlan(leading_ms=leading, trailing_ms=0)


def _trim_audio(path: Path, plan: TrimPlan) -> None:
    """WAV 裁剪：-ss 对未压缩 WAV 是样本级精确。"""
    if plan.total_ms <= 0:
        return
    start_sec = plan.leading_ms / 1000.0
    tmp = path.with_name(f"{path.stem}.trim{path.suffix}")

    cmd = ["ffmpeg", "-y", "-hide_banner"]
    if plan.leading_ms > 0:
        cmd += ["-ss", f"{start_sec:.3f}"]
    cmd += ["-i", str(path)]
    if plan.trailing_ms > 0:
        dur = probe_duration(path) - start_sec - plan.trailing_ms / 1000.0
        if dur > 0.05:
            cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-acodec", "pcm_s16le", str(tmp)]

    run_ffmpeg(cmd)
    tmp.replace(path)


def apply_tts_segment_trim(
    path: Path,
    words: list[TimedWord],
    *,
    head_pad_ms: int = 50,
    tail_pad_ms: int = 20,
    min_leading_silence_ms: int = 500,
) -> list[TimedWord]:
    """就地裁切段首/段尾静音；字级时间戳在裁过段首时平移。"""
    duration_ms = int(round(probe_duration(path) * 1000))
    plan = plan_tts_segment_trim(
        words,
        duration_ms=duration_ms,
        head_pad_ms=head_pad_ms,
        tail_pad_ms=tail_pad_ms,
        min_leading_silence_ms=min_leading_silence_ms,
    )
    if plan.total_ms <= 0:
        return words

    _trim_audio(path, plan)
    result = (
        words
        if plan.leading_ms <= 0
        else shift_word_timestamps(words, plan.leading_ms)
    )
    logger.info(
        "tts segment trim %s leading=%sms trailing=%sms duration %.2fs -> %.2fs",
        path.name,
        plan.leading_ms,
        plan.trailing_ms,
        duration_ms / 1000.0,
        probe_duration(path),
    )
    return result


def trim_audio_trailing(
    path: Path,
    *,
    noise_db: float = -40.0,
    tail_pad_ms: int = 50,
    min_trailing_ms: int = 250,
) -> None:
    """用 ffmpeg silencedetect 检测并裁切 WAV 尾部静音。

    不依赖 word timestamps（其 end_time 往往早于实际发音结束），
    而是通过 silencedetect 找到文件末尾真正的静音段来裁切。
    仅在尾部静音超过 min_trailing_ms 时才执行。
    仅用于 WAV 文件（MP3 上精度不够）。
    """
    from app.services.media.ffmpeg_utils import silence_detect_log

    output = silence_detect_log(path, noise_db=noise_db, min_duration_sec=0.35)
    starts = [float(v) for v in re.findall(r"silence_start:\s*([0-9.]+)", output)]
    durations = [float(v) for v in re.findall(r"silence_duration:\s*([0-9.]+)", output)]
    if not starts or not durations:
        return

    file_duration = probe_duration(path)
    if file_duration <= 0:
        return

    # 确认最后一个静音段在文件末尾（结束位置距末尾 ≤ 0.15s）
    last_end = starts[-1] + durations[-1]
    if file_duration - last_end > 0.15:
        return

    trailing_ms = int(round(durations[-1] * 1000))
    trim_ms = max(0, trailing_ms - tail_pad_ms)
    if trim_ms < min_trailing_ms:
        return

    logger.info(
        "trim trailing silence %s trailing=%sms trim=%sms tail_pad=%sms duration=%.2fs->%.2fs",
        path.name, trailing_ms, trim_ms, tail_pad_ms,
        file_duration,
        file_duration - trim_ms / 1000.0,
    )
    _trim_audio(path, TrimPlan(leading_ms=0, trailing_ms=trim_ms))
