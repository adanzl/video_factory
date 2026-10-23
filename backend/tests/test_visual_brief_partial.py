"""visual_brief 局部合并。"""

from __future__ import annotations

from app.services.llm.llm_deepseek import _merge_visual_briefs
from app.services.llm.llm_mock import MockLLMClient
import copy
import pytest
from app.exceptions import JobStageFailureError
from app.services.llm.llm_deepseek import DeepSeekClient


def test_visual_briefs_fill_missing_without_overwriting_completed(monkeypatch):
    client = object.__new__(DeepSeekClient)
    script = {"segments": [{"segment_index": i, "text": "对白"} for i in range(1, 10)]}
    calls = []

    def chat(system, user, **kwargs):
        calls.append(user)
        indices = [1] if len(calls) == 1 else list(range(2, 10))
        return {"segments": [{"segment_index": i, "visual_brief": f"第{i}段画面"} for i in indices]}, "stop"

    monkeypatch.setattr(client, "_chat_json", chat)
    client.fill_visual_briefs(script)
    assert len(calls) == 2
    assert "【仅上下文】segment 1" in calls[1]
    assert "【需生成】segment 2" in calls[1]
    assert [s["visual_brief"] for s in script["segments"]] == [f"第{i}段画面" for i in range(1, 10)]


@pytest.mark.parametrize("bad_rows", [
    [{"segment_index": 2, "visual_brief": ""}],
    [{"segment_index": 2, "visual_brief": "a"}, {"segment_index": 2, "visual_brief": "b"}],
    [{"segment_index": 2, "visual_subjects": [{"name": "昭昭"}]}],
    [{"segment_index": "wrong", "visual_brief": "a"}, None],
])
def test_visual_briefs_exhaustion_is_atomic_and_friendly(monkeypatch, bad_rows):
    client = object.__new__(DeepSeekClient)
    script = {"segments": [{"segment_index": 1, "text": "一"}, {"segment_index": 2, "text": "二"}]}
    before = copy.deepcopy(script)
    calls = []

    def chat(*args, **kwargs):
        calls.append(1)
        return {"segments": [{"segment_index": 1, "visual_brief": "完成"}, *bad_rows]}, "stop"

    monkeypatch.setattr(client, "_chat_json", chat)
    with pytest.raises(JobStageFailureError, match="分镜 2"):
        client.fill_visual_briefs(script)
    assert len(calls) == 3
    assert script == before


def test_visual_briefs_partial_generation_preserves_other_segments(monkeypatch):
    client = object.__new__(DeepSeekClient)
    script = {"segments": [{"segment_index": 1, "visual_brief": "已验收"}, {"segment_index": 2}]}
    calls = []

    def chat(*args, **kwargs):
        calls.append(1)
        return {"segments": [{"segment_index": 1, "visual_brief": "不应覆盖"},
                             {"segment_index": 2, "visual_brief": "新画面"}]}, "stop"

    monkeypatch.setattr(client, "_chat_json", chat)
    client.fill_visual_briefs(script, segment_indices=[2])
    assert len(calls) == 1
    assert script["segments"][0]["visual_brief"] == "已验收"


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
