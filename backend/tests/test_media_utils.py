from app.utils.media import (
    assign_segment_timings,
    default_narration_target_words,
    DEFAULT_NARRATION_TARGET_WORDS,
    estimate_narration_target_words,
    estimate_segment_duration_sec,
    material_final_min_duration_sec,
    material_min_audio_duration_sec,
    narration_accept_min_chars,
    segment_narration_chars,
    segment_text_shrink_max,
    narration_target_for_minutes,
    narration_writing_plan,
    narration_writing_target_chars,
    segment_comfort_chars,
    segment_text_char_cap,
    split_narration_to_segments,
)


def test_default_narration_target_words_is_six_minutes():
    assert default_narration_target_words() == DEFAULT_NARRATION_TARGET_WORDS
    assert DEFAULT_NARRATION_TARGET_WORDS == narration_target_for_minutes(6.0)


def test_segment_text_char_cap():
    assert segment_text_char_cap(16) == 65
    assert segment_text_char_cap(5) == 20
    assert segment_text_char_cap(28) == 65  # 口播硬顶 16s


def test_effective_segment_narration_sec_caps_at_sixteen():
    from app.utils.media import MAX_SEGMENT_NARRATION_SEC, effective_segment_narration_sec

    assert effective_segment_narration_sec(28) == MAX_SEGMENT_NARRATION_SEC
    assert effective_segment_narration_sec(10) == 10


def test_narration_target_for_minutes_uses_default_speech_rate():
    # 6 分钟成片：358s 正文 × 4.1 × 0.92 × 1.1 = 1485
    assert narration_target_for_minutes(6.0) == 1485


def test_narration_accept_min_chars():
    assert narration_accept_min_chars(1485) == 1262
    assert narration_accept_min_chars(404) == 343


def test_segment_text_shrink_max():
    assert segment_text_shrink_max(15.0) == 95  # hard_cap 70 + 25


def test_narration_writing_target_chars_is_ninety_five_percent():
    assert narration_writing_target_chars(404) == 383
    assert narration_writing_target_chars(1485) == 1410


def test_narration_writing_plan_15s_prefers_more_segments():
    """15s 单镜下按舒适段长估算，段数应多于仅用 cap 整除。"""
    plan = narration_writing_plan(404, 15.0)
    assert plan["segment_cap"] == 61
    assert plan["per_seg_hi"] == segment_comfort_chars(61)
    assert plan["seg_count_min"] >= 7
    assert plan["per_seg_min"] <= plan["per_seg_hi"]


def test_estimate_narration_target_words_clamps():
    assert estimate_narration_target_words(5) == 20
    assert estimate_narration_target_words(30) == 124
    assert estimate_narration_target_words(700) == 2904
    assert estimate_narration_target_words(10_000) == 3000


def test_material_duration_bounds_for_short_base():
    assert material_min_audio_duration_sec(30) == 21.0
    assert material_final_min_duration_sec(30) == 25.5
    assert material_final_min_duration_sec(30, intro_duration_sec=3) == 28.05


def test_assign_segment_timings_from_narration_chars():
    script = {
        "segments": [
            {"segment_index": 1, "text": "一二三四五"},  # 5 chars -> ~1.22s
            {"segment_index": 2, "text": "一二三四五六七八九十"},  # 10 chars -> ~2.44s
        ]
    }
    assign_segment_timings(script, segment_target_sec=28.0)
    assert script["segments"][0]["start_sec"] == 0.0
    assert script["segments"][0]["end_sec"] == 1.22
    assert script["segments"][1]["start_sec"] == 1.22
    assert script["segments"][1]["end_sec"] == 3.659
    assert script["total_duration_sec"] == 3.659


def test_estimate_segment_duration_sec():
    assert estimate_segment_duration_sec("一二三四五") == 1.22


def test_split_narration_to_segments_by_sentence_when_no_duration_cap():
    narration = "第一句。第二句！第三句？"
    segments = split_narration_to_segments(narration, 0)
    assert len(segments) == 3
    assert "".join(seg["text"] for seg in segments) == narration


def test_split_narration_to_segments_respects_duration_cap():
    cap = segment_text_char_cap(15.0)
    sentence = "一" * (cap + 10)
    narration = f"{sentence}。短句。"
    segments = split_narration_to_segments(narration, 15.0)
    assert all(segment_narration_chars(seg["text"]) <= cap for seg in segments)
    joined = "".join(seg["text"] for seg in segments)
    assert segment_narration_chars(joined) == segment_narration_chars(narration)


def test_split_narration_to_segments_long_1350_chars():
    cap = segment_text_char_cap(15.0)
    parts = [f"科普点{i}：" + "字" * 18 + "。" for i in range(60)]
    narration = "".join(parts)
    segments = split_narration_to_segments(narration, 15.0)
    assert len(segments) >= 20
    assert all(segment_narration_chars(seg["text"]) <= cap for seg in segments)
    assert "".join(seg["text"] for seg in segments) == narration


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
                description="scene A",
                max_chars=44,
            ),
            TimelineSlot(
                index=2,
                start_sec=8.0,
                end_sec=14.0,
                duration_sec=6.0,
                scene="B",
                description="scene B",
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
