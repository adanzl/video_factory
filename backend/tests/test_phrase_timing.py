from app.services.tts.phrase_timing import (
    build_segment_tts_text,
    normalize_word_timestamps,
    phrase_durations_from_words,
    TimedWord,
)
from app.services.visual.text_render import split_phrase_chunks


def test_build_segment_tts_text_matches_source():
    text = "很多人以为，不锈钢就一定不会被磁铁吸住。"
    phrases = split_phrase_chunks(text)
    assert build_segment_tts_text(phrases) == text


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
