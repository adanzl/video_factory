"""TTS 段音频尾裁切：按 CosyVoice 字级时间戳去掉段尾空白。

段首不裁：首字 begin 常远滞后于真实发音起点，裁段首易切掉句首（如「可是」）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.services.media.ffmpeg_utils import probe_duration, run_ffmpeg
from app.services.tts.phrase_timing import TimedWord

logger = logging.getLogger(__name__)

__all__ = [
    "TrimPlan",
    "apply_tts_segment_trim",
    "plan_tts_segment_trim",
    "shift_word_timestamps",
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
    head_pad_ms: int = 150,
    tail_pad_ms: int = 20,
    min_leading_ms: int = 80,
    min_trailing_ms: int = 50,
) -> TrimPlan:
    """计算裁切计划：仅裁段尾，段首 leading_ms 恒为 0。

    head_pad_ms / min_leading_ms 保留参数兼容，段首不再使用。
    """
    _ = head_pad_ms, min_leading_ms
    if not words or duration_ms <= 0:
        return TrimPlan(leading_ms=0, trailing_ms=0)

    leading_ms = 0

    trailing_ms = 0
    tail_gap = duration_ms - words[-1].end_time_ms
    if tail_gap >= min_trailing_ms:
        trailing_ms = max(0, tail_gap - tail_pad_ms)

    keep_ms = 120
    max_trim = max(0, duration_ms - keep_ms)
    trailing_ms = min(trailing_ms, max_trim)
    return TrimPlan(leading_ms=leading_ms, trailing_ms=trailing_ms)


def _trim_audio(path: Path, plan: TrimPlan) -> None:
    if plan.total_ms <= 0:
        return
    start_sec = plan.leading_ms / 1000.0
    tmp = path.with_name(f"{path.stem}.trim{path.suffix}")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(path),
        "-ss",
        f"{start_sec:.3f}",
    ]
    if plan.trailing_ms > 0:
        duration_sec = probe_duration(path) - start_sec - plan.trailing_ms / 1000.0
        if duration_sec > 0.05:
            cmd.extend(["-t", f"{duration_sec:.3f}"])
    if path.suffix.lower() == ".wav":
        cmd.extend(["-acodec", "pcm_s16le", str(tmp)])
    else:
        tmp_wav = path.with_name(f"{path.stem}.trim.wav")
        cmd.extend(["-acodec", "pcm_s16le", str(tmp_wav)])
        run_ffmpeg(cmd)
        try:
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-i",
                    str(tmp_wav),
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(tmp),
                ]
            )
            tmp.replace(path)
        finally:
            tmp_wav.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)
        return
    run_ffmpeg(cmd)
    tmp.replace(path)


def apply_tts_segment_trim(
    path: Path,
    words: list[TimedWord],
    *,
    head_pad_ms: int = 150,
    tail_pad_ms: int = 20,
) -> list[TimedWord]:
    """就地裁切段尾静音；字级时间戳仅在裁过段首时平移（当前段首不裁）。"""
    duration_ms = int(round(probe_duration(path) * 1000))
    plan = plan_tts_segment_trim(
        words,
        duration_ms=duration_ms,
        head_pad_ms=head_pad_ms,
        tail_pad_ms=tail_pad_ms,
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
