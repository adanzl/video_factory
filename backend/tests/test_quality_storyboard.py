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


def test_check_storyboard_passes_with_fewer_segments_than_word_budget():
    """段数少于字数÷单镜上限估算值时仍可通过（不再强制最少分镜数）。"""
    cap = 80  # 16s × 5字/秒
    script = _script_with_segments(8, chars_per_segment=cap)
    report = check_storyboard(script, segment_target_sec=16.0)
    assert report.level == "pass"


def test_check_storyboard_reads_segment_target_from_script_json():
    script = _script_with_segments(12, chars_per_segment=140)
    script["segment_target_sec"] = 28.0
    report = check_storyboard(script)
    assert report.level == "pass"


def test_check_storyboard_passes_when_narration_exceeds_target_with_few_segments():
    """口播实际字数高于 narration_target_words 时，段数少也不判失败。"""
    text = "字" * 550
    script = {
        "title": "测试标题",
        "narration": text,
        "narration_target_words": 404,
        "segment_target_sec": 28.0,
        "segments": [
            {"segment_index": i + 1, "text": "字" * 138} for i in range(3)
        ],
    }
    report = check_storyboard(script, segment_target_sec=28.0)
    assert report.level == "pass"
