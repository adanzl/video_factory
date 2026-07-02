from app.services.tts.tts_mgr import SubtitleCue, tts_mgr


def test_segment_durations_from_cues() -> None:
    cues = [
        SubtitleCue(segment_index=2, text="a", duration_sec=3.733),
        SubtitleCue(segment_index=2, text="b", duration_sec=2.512),
        SubtitleCue(segment_index=3, text="c", duration_sec=5.0),
    ]
    assert tts_mgr.segment_durations_from_cues(cues) == {2: 6.245, 3: 5.0}
