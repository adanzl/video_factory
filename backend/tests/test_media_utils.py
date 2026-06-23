from app.utils.media import (
    body_duration_for_target_final,
    default_narration_target_words,
    estimate_narration_target_words,
    narration_accept_min_chars,
    narration_target_for_minutes,
    segment_text_char_cap,
)


def test_body_duration_for_target_final():
    assert body_duration_for_target_final(90, intro_budget_sec=2) == 88.0
    assert body_duration_for_target_final(20, intro_budget_sec=5) == 30.0


def test_default_narration_target_words_uses_config(monkeypatch):
    fake = type(
        "S",
        (),
        {"target_final_duration_sec": 90.0, "intro_duration_budget_sec": 2.0},
    )()
    # 88 * 5 * 0.92 = 404.8 -> 404
    assert default_narration_target_words(fake) == 404


def test_segment_text_char_cap():
    assert segment_text_char_cap(16) == 80
    assert segment_text_char_cap(5) == 25
    assert segment_text_char_cap(28) == 140


def test_narration_target_for_minutes_uses_five_chars_per_sec():
    # 6 分钟成片：358s 正文 × 5 × 0.92 = 1646
    assert narration_target_for_minutes(6.0) == 1646


def test_narration_accept_min_chars():
    assert narration_accept_min_chars(1646) == 1399
    assert narration_accept_min_chars(404) == 343


def test_estimate_narration_target_words_clamps():
    assert estimate_narration_target_words(5) == 200
    assert estimate_narration_target_words(700) == 3000
