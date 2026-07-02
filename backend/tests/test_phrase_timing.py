from app.services.tts.phrase_timing import (
    build_segment_tts_text,
    match_phrase_words,
    normalize_word_timestamps,
    phrase_durations_from_words,
    TimedWord,
)
from app.services.render.text_render import split_phrase_chunks


def test_build_segment_tts_text_matches_source():
    text = "很多人以为，不锈钢就一定不会被磁铁吸住。"
    phrases = split_phrase_chunks(text)
    assert build_segment_tts_text(phrases) == text


def test_phrase_durations_include_inter_phrase_pause():
    phrases = [
        ("很多人以为，", "很多人以为"),
        ("不锈钢就一定不会被磁铁吸住。", "不锈钢就一定不会被磁铁吸住"),
    ]
    words = normalize_word_timestamps(
        [
            {"text": "很", "begin_time": 100, "end_time": 180},
            {"text": "多", "begin_time": 180, "end_time": 260},
            {"text": "人", "begin_time": 260, "end_time": 340},
            {"text": "以", "begin_time": 340, "end_time": 420},
            {"text": "为", "begin_time": 420, "end_time": 500},
            {"text": "，", "begin_time": 500, "end_time": 520},
            {"text": "不", "begin_time": 600, "end_time": 680},
            {"text": "锈", "begin_time": 680, "end_time": 760},
            {"text": "钢", "begin_time": 760, "end_time": 840},
        ]
    )
    durations = phrase_durations_from_words(phrases, words, segment_duration_sec=3.0)
    assert len(durations) == 2
    assert durations[0] == 0.5
    assert durations[1] >= 0.05


def test_normalize_handles_out_of_order_timestamps():
    raw = [
        {"text": "烫", "begin_index": 63, "end_index": 64, "begin_time": 18400, "end_time": 18666},
        {"text": "行", "begin_index": 64, "end_index": 65, "begin_time": 17882, "end_time": 17971},
        {"text": "人", "begin_index": 65, "end_index": 66, "begin_time": 18060, "end_time": 18326},
    ]
    words = normalize_word_timestamps(raw)
    assert [word.text for word in words] == ["烫", "行", "人"]
    assert words[0].end_time_ms == 18666
    assert words[1].begin_time_ms >= words[0].end_time_ms
    assert words[-1].end_time_ms > words[-1].begin_time_ms
    assert words[-1].end_time_ms < 20_000


def test_match_phrase_words_uses_begin_index():
    phrases = [
        ("AB，", "AB"),
        ("CD。", "CD"),
    ]
    words = normalize_word_timestamps(
        [
            {"text": "A", "begin_index": 0, "end_index": 1, "begin_time": 100, "end_time": 180},
            {"text": "B", "begin_index": 1, "end_index": 2, "begin_time": 180, "end_time": 260},
            {"text": "，", "begin_index": 2, "end_index": 3, "begin_time": 260, "end_time": 300},
            {"text": "C", "begin_index": 3, "end_index": 4, "begin_time": 400, "end_time": 480},
            {"text": "D", "begin_index": 4, "end_index": 5, "begin_time": 480, "end_time": 560},
            {"text": "。", "begin_index": 5, "end_index": 6, "begin_time": 560, "end_time": 600},
        ]
    )
    matched = match_phrase_words(phrases, words)
    assert [word.text for word in matched[0]] == ["A", "B", "，"]
    assert [word.text for word in matched[1]] == ["C", "D", "。"]


def test_match_phrase_words_when_api_omits_period():
    phrases = [
        ("难受。", "难受"),
        ("阳光", "阳光"),
    ]
    words = normalize_word_timestamps(
        [
            {"text": "难", "begin_index": 0, "end_index": 1, "begin_time": 100, "end_time": 180},
            {"text": "受", "begin_index": 1, "end_index": 2, "begin_time": 180, "end_time": 260},
            {"text": "阳", "begin_index": 2, "end_index": 3, "begin_time": 400, "end_time": 480},
            {"text": "光", "begin_index": 3, "end_index": 4, "begin_time": 480, "end_time": 560},
        ]
    )
    matched = match_phrase_words(phrases, words)
    assert [word.text for word in matched[0]] == ["难", "受"]
    assert [word.text for word in matched[1]] == ["阳", "光"]


def test_phrase_durations_cover_segment():
    text = "很多人以为，不锈钢就一定不会被磁铁吸住。"
    phrases = split_phrase_chunks(text)
    words = normalize_word_timestamps(
        [
            {"text": "很", "begin_time": 100, "end_time": 180},
            {"text": "多", "begin_time": 180, "end_time": 260},
            {"text": "人", "begin_time": 260, "end_time": 340},
            {"text": "以", "begin_time": 340, "end_time": 420},
            {"text": "为", "begin_time": 420, "end_time": 500},
            {"text": "不", "begin_time": 600, "end_time": 680},
            {"text": "锈", "begin_time": 680, "end_time": 760},
            {"text": "钢", "begin_time": 760, "end_time": 840},
        ]
    )
    durations = phrase_durations_from_words(phrases, words, segment_duration_sec=3.0)
    assert len(durations) == len(phrases)
    assert abs(sum(durations) - 3.0) < 0.2
