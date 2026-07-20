"""visual_brief 局部合并。"""

from __future__ import annotations

from app.services.llm.llm_deepseek import _merge_visual_briefs
from app.services.llm.llm_mock import MockLLMClient


def test_merge_visual_briefs_partial_keeps_others():
    script = {
        "segments": [
            {"segment_index": 1, "visual_brief": "旧1"},
            {"segment_index": 2, "visual_brief": "旧2"},
            {"segment_index": 3, "visual_brief": "旧3"},
        ]
    }
    _merge_visual_briefs(
        script,
        {
            "segments": [
                {
                    "segment_index": 2,
                    "visual_brief": "新2",
                    "visual_mode": "static_motion",
                }
            ]
        },
        required_indices=[2],
    )
    assert script["segments"][0]["visual_brief"] == "旧1"
    assert script["segments"][1]["visual_brief"] == "新2"
    assert script["segments"][2]["visual_brief"] == "旧3"


def test_mock_fill_visual_briefs_respects_segment_indices():
    script = {
        "title": "t",
        "segments": [
            {"segment_index": 1, "visual_brief": "a"},
            {"segment_index": 2, "visual_brief": "b"},
        ],
    }
    MockLLMClient().fill_visual_briefs(script, segment_indices=[2])
    assert script["segments"][0]["visual_brief"] == "a"
    assert "第2镜" in script["segments"][1]["visual_brief"]
