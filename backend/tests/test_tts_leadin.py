"""TTS 句首引导词（复刻音色弱启动）。"""

from __future__ import annotations

from app.services.tts.phrase_timing import TimedWord
from app.services.tts.tts_leadin import (
    CLONED_VOICE,
    prepare_lead_in,
    strip_tts_lead_in,
)


def test_prepare_lead_in_for_cloned_voice_weak_start():
    text, lead = prepare_lead_in("可是，真相是", voice=CLONED_VOICE)
    assert lead == "那，"
    assert text == "那，可是，真相是"


def test_prepare_lead_in_skips_other_voices():
    text, lead = prepare_lead_in("可是", voice="longwan_v3")
    assert lead is None
    assert text == "可是"


def test_prepare_lead_in_for_any_cloned_segment():
    text, lead = prepare_lead_in("其实呀，地震发生时", voice=CLONED_VOICE)
    assert lead == "那，"
    assert text == "那，其实呀，地震发生时"


def test_strip_tts_lead_in_shifts_words_without_file(tmp_path):
    path = tmp_path / "seg.mp3"
    path.write_bytes(b"fake")
    words = [
        TimedWord("那", 500, 800),
        TimedWord("，", 800, 900),
        TimedWord("可", 900, 1100),
        TimedWord("是", 1100, 1300),
    ]

    def fake_trim(_path, plan):
        assert plan.leading_ms == 885
        assert plan.trailing_ms == 0

    import app.services.tts.tts_leadin as leadin_mod

    orig = leadin_mod._trim_audio
    leadin_mod._trim_audio = fake_trim
    try:
        out = strip_tts_lead_in(path, words, "那，")
    finally:
        leadin_mod._trim_audio = orig

    assert [w.text for w in out] == ["可", "是"]
    assert out[0].begin_time_ms == 15
    assert out[1].begin_time_ms == 215
