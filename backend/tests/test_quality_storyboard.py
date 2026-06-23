from app.quality.checkers import check_storyboard


def _script_with_segments(count: int, *, chars_per_segment: int = 80) -> dict:
    text = "字" * chars_per_segment
    segments = [
        {"segment_index": i + 1, "text": text} for i in range(count)
    ]
    narration = "\n".join(text for _ in range(count))
    return {
        "title": "测试标题",
        "narration": narration,
        "segments": segments,
    }


def test_check_storyboard_uses_run_segment_target_not_settings_default():
    """28s 单镜下 12 段足够；若误用默认 16s 会误判段数不足。"""
    script = _script_with_segments(12, chars_per_segment=140)
    report = check_storyboard(script, segment_target_sec=28.0)
    assert report.level == "pass"


def test_check_storyboard_fails_when_segments_insufficient_for_target():
    script = _script_with_segments(15, chars_per_segment=110)
    report = check_storyboard(script, segment_target_sec=16.0)
    assert report.level == "major"
    assert report.details["reason"] == "too few segments"


def test_check_storyboard_reads_segment_target_from_script_json():
    script = _script_with_segments(12, chars_per_segment=140)
    script["segment_target_sec"] = 28.0
    report = check_storyboard(script)
    assert report.level == "pass"
