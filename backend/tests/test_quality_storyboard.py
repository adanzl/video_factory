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


def test_check_storyboard_matches_validation_when_narration_exceeds_target():
    """口播实际字数高于 narration_target_words 时，质检与 validate 段数一致。"""
    text = "字" * 550
    script = {
        "title": "测试标题",
        "narration": text,
        "narration_target_words": 404,
        "segment_target_sec": 28.0,
        "segments": [
            {"segment_index": i + 1, "text": "字" * 138} for i in range(4)
        ],
    }
    report = check_storyboard(script, segment_target_sec=28.0)
    assert report.level == "pass"
    script["segments"] = script["segments"][:3]
    report = check_storyboard(script, segment_target_sec=28.0)
    assert report.level == "major"
    assert report.details["reason"] == "too few segments"
