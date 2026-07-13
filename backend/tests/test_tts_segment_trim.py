"""TTS 段首/段尾裁切（字级时间戳）。"""

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


def test_plan_trims_leading_based_on_first_word_position():
    words = [TimedWord("可", 400, 800), TimedWord("是", 800, 1100)]
    plan = plan_tts_segment_trim(words, duration_ms=2_000)
    # first_begin=400, head_pad_ms=50 => 400-50=350
    assert plan.leading_ms == 350
    assert plan.trailing_ms == 0


def test_plan_trims_leading_for_late_first_word():
    words = [TimedWord("你", 1280, 1600), TimedWord("让", 1600, 1900)]
    plan = plan_tts_segment_trim(words, duration_ms=8_000)
    # first_begin=1280, head_pad_ms=50 => 1280-50=1230
    assert plan.leading_ms == 1230
    assert plan.trailing_ms == 0


def test_plan_skips_leading_trim_when_first_word_starts_very_early():
    words = [TimedWord("可", 50, 400)]
    plan = plan_tts_segment_trim(words, duration_ms=1_000)
    # first_begin=50, head_pad_ms=50 => max(0,50-50)=0
    assert plan.leading_ms == 0


def test_plan_skips_leading_trim_when_first_word_at_zero():
    words = [TimedWord("啊", 0, 5000)]
    plan = plan_tts_segment_trim(words, duration_ms=10_000)
    assert plan.leading_ms == 0
    assert plan.trailing_ms == 0


def test_plan_skips_punctuation_to_find_first_real_word():
    words = [
        TimedWord("，", 0, 50),
        TimedWord("。", 50, 80),
        TimedWord("我", 300, 500),
    ]
    plan = plan_tts_segment_trim(words, duration_ms=2_000)
    # first real word "我" at 300ms => 300-50=250
    assert plan.leading_ms == 250


def test_apply_trim_shifts_words_when_leading_trimmed():
    sample = TMP / "01_segment.mp3"
    if not sample.is_file() or not shutil.which("ffmpeg"):
        return

    work = TMP / "trim_test_segment.mp3"
    shutil.copy(sample, work)
    # first word at 622ms, head_pad_ms=50 => leading=572ms
    words = [
        TimedWord("可", 622, 900),
        TimedWord("是", 900, 1066),
        TimedWord("，", 1066, 1511),
    ]
    trimmed = apply_tts_segment_trim(work, words)
    # leading trim = 622 - 50 = 572ms, words shifted by 572ms
    assert trimmed[0].begin_time_ms == 50
    assert trimmed[1].begin_time_ms == 328
    assert trimmed[2].begin_time_ms == 494
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(work),
        ],
        text=True,
    )
    assert float(out.strip()) > 0
