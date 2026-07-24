import pytest

from app.services.tts.audio_timeline import (
    align_segment_durations_to_narration,
    extend_phrase_cues_to_duration,
    segment_timeline_durations_from_db,
)


def test_extend_phrase_cues_to_duration_pads_tail():
    cues = [("第一句", 2.0), ("第二句", 3.0)]
    extended = extend_phrase_cues_to_duration(cues, 5.4)
    assert extended[-1][0] == "第二句"
    assert extended[-1][1] == pytest.approx(3.4)
    assert extend_phrase_cues_to_duration(cues, 5.0) == cues


def test_segment_timeline_durations_from_db_reads_segments():
    segments = [
        {"segment_index": 2, "duration_sec": 4.0},
        {"segment_index": 1, "duration_sec": 6.0},
    ]
    assert segment_timeline_durations_from_db(segments) == [6.0, 4.0]


def test_align_segment_durations_to_narration(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(
        "app.services.tts.audio_timeline.probe_duration",
        lambda _path: 10.0,
    )
    assert align_segment_durations_to_narration([3.0, 3.0], Path("narration.mp3")) == [
        5.0,
        5.0,
    ]
