"""TTS 段尾裁切（字级时间戳）。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.services.tts.phrase_timing import TimedWord
from app.services.tts.segment_trim import (
    apply_tts_segment_trim,
    plan_tts_segment_trim,
    shift_word_timestamps,
)

TMP = Path(__file__).resolve().parents[1] / "tmp" / "tts_segment_test"


def test_shift_word_timestamps_clamps_to_zero():
    words = [
        TimedWord("哇", 88, 533),
        TimedWord("，", 533, 888),
    ]
    shifted = shift_word_timestamps(words, 88)
    assert shifted[0].begin_time_ms == 0
    assert shifted[0].end_time_ms == 445


def test_plan_never_trims_leading_even_when_first_word_starts_late():
    words = [TimedWord("可", 400, 800), TimedWord("是", 800, 1100)]
    plan = plan_tts_segment_trim(words, duration_ms=2_000)
    assert plan.leading_ms == 0
    assert plan.trailing_ms == 880


def test_plan_skips_leading_trim_when_first_word_starts_early():
    words = [TimedWord("可", 50, 400)]
    plan = plan_tts_segment_trim(words, duration_ms=1_000)
    assert plan.leading_ms == 0


def test_plan_trailing_from_last_word_end():
    words = [TimedWord("啊", 0, 5000)]
    plan = plan_tts_segment_trim(words, duration_ms=10_000, min_trailing_ms=50)
    assert plan.leading_ms == 0
    assert plan.trailing_ms == 4980


def test_apply_trim_keeps_first_word_timestamps_when_only_trailing():
    sample = TMP / "01_segment.mp3"
    if not sample.is_file() or not shutil.which("ffmpeg"):
        return

    work = TMP / "trim_test_segment.mp3"
    shutil.copy(sample, work)
    words = [
        TimedWord("可", 622, 900),
        TimedWord("是", 900, 1066),
        TimedWord("，", 1066, 1511),
    ]
    trimmed = apply_tts_segment_trim(work, words)
    assert trimmed[0].begin_time_ms == 622
    assert trimmed[1].begin_time_ms == 900
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(work),
        ],
        text=True,
    )
    assert float(out.strip()) > 0
