from __future__ import annotations

import json

from app.services.llm.llm_script_timeline import (
    hard_max_chars,
    parse_video_timeline,
    validate_timeline_script,
)


def test_parse_video_timeline_balls():
    raw = json.dumps(
        {
            "duration_sec": 14.0,
            "balls": [
                {
                    "index": 1,
                    "year": 1930,
                    "country": "乌拉圭",
                    "ball_name": "T-model",
                    "start_sec": 0,
                    "end_sec": 8,
                    "duration_sec": 8,
                },
                {
                    "index": 2,
                    "year": 1934,
                    "country": "意大利",
                    "ball_name": "Federale 102",
                    "start_sec": 8,
                    "end_sec": 14,
                    "duration_sec": 6,
                },
            ],
        },
        ensure_ascii=False,
    )
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    assert len(timeline.slots) == 2
    assert timeline.slots[0].scene == "1930年 乌拉圭 T-model"
    assert timeline.slots[0].max_chars == 44
    assert timeline.slots[1].max_chars == 33


def test_validate_timeline_script_rejects_wrong_count():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    err, warnings = validate_timeline_script({"segments": []}, timeline)
    assert err is not None
    assert "1" in err
    assert warnings == []


def test_validate_timeline_script_slight_over_target_passes_with_warning():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    target = timeline.slots[0].max_chars
    text = "字" * (target + 2)
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, warnings = validate_timeline_script(script, timeline, length_mode="strict")
    assert err is None
    assert warnings


def test_validate_timeline_script_hard_limit_still_retries():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    target = timeline.slots[0].max_chars
    hard = hard_max_chars(target)
    text = "字" * (hard + 5)
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, _ = validate_timeline_script(script, timeline, length_mode="strict")
    assert err is not None
    assert "过长" in err


def test_validate_timeline_script_warn_only_accepts():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    text = "这是一段明显超过二十五字上限的口播内容，用来测试校验逻辑是否生效。"
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, warnings = validate_timeline_script(script, timeline, length_mode="warn_only")
    assert err is None
    assert warnings
