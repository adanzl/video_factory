"""气口：字级时间戳句间停顿。"""

from app.services.tts.breath_cue import (
    build_phrase_breath_cues,
    pause_after_ms,
    phrase_pauses_from_matched,
)
from app.services.tts.phrase_timing import TimedWord


def test_pause_after_ms_between_phrases():
    cur = [TimedWord("难", 100, 200), TimedWord("受", 200, 300)]
    nxt = [TimedWord("阳", 389, 450)]
    assert pause_after_ms(cur, nxt) == 89


def test_pause_after_ms_excludes_trailing_punctuation():
    cur = [TimedWord("吗", 200, 300), TimedWord("？", 300, 400)]
    nxt = [TimedWord("欧", 500, 600)]
    assert pause_after_ms(cur, nxt) == 200


def test_phrase_pauses_from_matched():
    matched = [
        [TimedWord("A", 0, 100)],
        [TimedWord("B", 150, 250)],
        [TimedWord("C", 250, 350)],
    ]
    assert phrase_pauses_from_matched(matched) == [50, 0, None]


def test_build_phrase_breath_cues_includes_pause_in_duration():
    phrases = [
        ("很多人以为，", "很多人以为"),
        ("不锈钢就一定不会被磁铁吸住。", "不锈钢就一定不会被磁铁吸住"),
    ]
    words = [
        TimedWord("很", 100, 180, begin_index=0, end_index=1),
        TimedWord("多", 180, 260, begin_index=1, end_index=2),
        TimedWord("人", 260, 340, begin_index=2, end_index=3),
        TimedWord("以", 340, 420, begin_index=3, end_index=4),
        TimedWord("为", 420, 500, begin_index=4, end_index=5),
        TimedWord("，", 500, 520, begin_index=5, end_index=6),
        TimedWord("不", 600, 680, begin_index=6, end_index=7),
        TimedWord("锈", 680, 760, begin_index=7, end_index=8),
        TimedWord("钢", 760, 840, begin_index=8, end_index=9),
    ]
    cues = build_phrase_breath_cues(phrases, words, segment_duration_sec=3.0)
    assert len(cues) == 2
    assert cues[0].duration_sec == 0.5
    assert cues[0].pause_after_ms == 100
    assert cues[1].pause_after_ms is None
