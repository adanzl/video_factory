"""金故事 H0c 逐字稿修复测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story import llm_steps
from app.services.daily_story.gold_story.transcript import format_dialogue_transcript


def test_format_dialogue_transcript():
    lines = [
        {"speaker": "妈妈", "text": "快睡吧"},
        {"speaker": "宝宝", "text": "不要"},
    ]
    assert format_dialogue_transcript(lines) == "妈妈：快睡吧\n宝宝：不要"


def test_repair_transcript_rejects_low_confidence(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "lines": [
                {"speaker": "妈妈", "text": "睡吧"},
                {"speaker": "宝宝", "text": "不睡"},
            ],
            "repair_confidence": 0.2,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    with pytest.raises(ValueError, match="H0c low repair_confidence"):
        llm_steps.repair_transcript(title="测试", transcript="睡吧 不睡")


def test_repair_transcript_ok(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "speakers": ["妈妈", "宝宝"],
            "lines": [
                {"speaker": "妈妈", "text": "十二点了还不睡？"},
                {"speaker": "宝宝", "text": "谁12点不到天亮"},
            ],
            "repair_confidence": 0.82,
            "repair_notes": "标题暗示母子对话",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(
        title="深夜对话",
        transcript="十二点岁 谁12点不到天亮",
        description="宝宝和妈妈",
    )
    assert out["repair_confidence"] == 0.82
    assert len(out["lines"]) == 2
    assert out["lines"][0]["speaker"] == "妈妈"
