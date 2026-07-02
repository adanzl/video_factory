from app.utils.media import (
    assign_segment_timings,
    body_duration_for_target_final,
    default_narration_target_words,
    estimate_narration_target_words,
    estimate_segment_duration_sec,
    material_final_min_duration_sec,
    material_min_audio_duration_sec,
    narration_accept_min_chars,
    segment_text_shrink_max,
    narration_target_for_minutes,
    narration_writing_plan,
    narration_writing_target_chars,
    segment_comfort_chars,
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


def test_segment_text_shrink_max():
    assert segment_text_shrink_max(15.0) == 111  # hard_cap 86 + 25


def test_narration_writing_target_chars_is_ninety_five_percent():
    assert narration_writing_target_chars(404) == 383
    assert narration_writing_target_chars(1646) == 1563


def test_narration_writing_plan_15s_prefers_more_segments():
    """15s 单镜下按舒适段长估算，段数应多于仅用 cap 整除。"""
    plan = narration_writing_plan(404, 15.0)
    assert plan["segment_cap"] == 75
    assert plan["per_seg_hi"] == segment_comfort_chars(75)
    assert plan["seg_count_min"] >= 7
    assert plan["per_seg_min"] <= plan["per_seg_hi"]


def test_estimate_narration_target_words_clamps():
    assert estimate_narration_target_words(5) == 23
    assert estimate_narration_target_words(30) == 138
    assert estimate_narration_target_words(700) == 3000


def test_material_duration_bounds_for_short_base():
    assert material_min_audio_duration_sec(30) == 21.0
    assert material_final_min_duration_sec(30) == 25.5
    assert material_final_min_duration_sec(30, intro_duration_sec=3) == 28.05


def test_assign_segment_timings_from_narration_chars():
    script = {
        "segments": [
            {"segment_index": 1, "text": "一二三四五"},  # 5 chars -> 1.0s
            {"segment_index": 2, "text": "一二三四五六七八九十"},  # 10 chars -> 2.0s
        ]
    }
    assign_segment_timings(script, segment_target_sec=28.0)
    assert script["segments"][0]["start_sec"] == 0.0
    assert script["segments"][0]["end_sec"] == 1.0
    assert script["segments"][1]["start_sec"] == 1.0
    assert script["segments"][1]["end_sec"] == 3.0
    assert script["total_duration_sec"] == 3.0


def test_assign_segment_timings_from_video_timeline():
    from app.services.script.board_timeline import TimelineSlot, VideoTimeline

    timeline = VideoTimeline(
        duration_sec=14.0,
        slots=(
            TimelineSlot(
                index=1,
                start_sec=0.0,
                end_sec=8.0,
                duration_sec=8.0,
                scene="A",
                max_chars=44,
            ),
            TimelineSlot(
                index=2,
                start_sec=8.0,
                end_sec=14.0,
                duration_sec=6.0,
                scene="B",
                max_chars=33,
            ),
        ),
        raw="{}",
    )
    script = {
        "segments": [
            {"segment_index": 1, "text": "第一段"},
            {"segment_index": 2, "text": "第二段"},
        ]
    }
    assign_segment_timings(script, video_timeline=timeline)
    assert script["segments"][0]["start_sec"] == 0.0
    assert script["segments"][0]["end_sec"] == 8.0
    assert script["segments"][1]["start_sec"] == 8.0
    assert script["segments"][1]["end_sec"] == 14.0

