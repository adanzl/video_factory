"""DeepSeek 分镜后处理测试。"""

from __future__ import annotations

import pytest

from app.services.llm.llm_deepseek import (
    DeepSeekClient,
    _assemble_storyboard_narration,
    _loads_llm_json,
)
from app.services.script.segment_split import apply_segments_from_voiceover
from app.utils.media import segment_text_char_cap


def _bare_client() -> DeepSeekClient:
    return object.__new__(DeepSeekClient)


def test_apply_segments_from_voiceover_respects_cap():
    narration = "第一句。" + "字" * 70 + "。第二句。"
    data = {"narration": narration, "visual_style": "写实", "title": "测试"}
    out = apply_segments_from_voiceover(data, segment_target_sec=15.0)
    cap = segment_text_char_cap(15.0)
    assert all(len(seg["text"].replace(" ", "")) <= cap for seg in out["segments"])
    assert out["narration"] == narration


def test_assemble_storyboard_narration_from_segments():
    data = {
        "title": "测试",
        "visual_style": "写实",
        "segments": [
            {"segment_index": 2, "text": "第二段"},
            {"segment_index": 1, "text": "第一段"},
        ],
    }
    out = _assemble_storyboard_narration(data)
    assert out["narration"] == "第一段第二段"
    assert out["word_count"] == 6


def test_loads_llm_json_escapes_unescaped_newlines_in_strings():
    raw = (
        '{\n'
        '  "title": "测试",\n'
        '  "visual_style": "写实",\n'
        '  "segments": [\n'
        '    {"segment_index": 1, "text": "第一行\n第二行", "visual_brief": "说明"}\n'
        "  ]\n"
        "}"
    )
    parsed = _loads_llm_json(raw)
    assert parsed["segments"][0]["text"] == "第一行\n第二行"


def test_loads_llm_json_strips_markdown_fence():
    raw = '```json\n{"title": "测试", "visual_style": "写实", "segments": []}\n```'
    parsed = _loads_llm_json(raw)
    assert parsed["title"] == "测试"


def test_loads_llm_json_repairs_speaker_line_colon_typo():
    raw = (
        '{"opening":[{"speaker":"灿灿","line":"蓝色抱枕怎么在你手里"},'
        '{"speaker":"昭昭":"我拽着一角你没看见吗"}]}'
    )
    parsed = _loads_llm_json(raw)
    assert parsed["opening"][1] == {
        "speaker": "昭昭",
        "line": "我拽着一角你没看见吗",
    }


def test_chat_json_retries_once_on_invalid_json(monkeypatch):
    """LLM 偶发坏 JSON 时，_chat_json 带格式提示重试一次并成功。"""
    client = _bare_client()
    calls: list[tuple[str, str]] = []

    def fake_chat(system, user, **kwargs):
        calls.append((system, user))
        if len(calls) == 1:
            return '{"segments": [{"segment_index": 1', "stop"
        return '{"segments": [{"segment_index": 1, "text": "ok"}]}', "stop"

    monkeypatch.setattr(client, "_chat", fake_chat)

    parsed, finish = client._chat_json("sys", "user")
    assert parsed == {"segments": [{"segment_index": 1, "text": "ok"}]}
    assert finish == "stop"
    assert len(calls) == 2
    assert "合法 JSON" in calls[1][1]


def test_chat_json_invalid_json_raises_after_retry(monkeypatch):
    """重试后仍坏 JSON 则保留原 ValueError 硬失败行为。"""
    client = _bare_client()

    def fake_chat(system, user, **kwargs):
        return '{"broken": ', "stop"

    monkeypatch.setattr(client, "_chat", fake_chat)

    with pytest.raises(ValueError, match="invalid JSON"):
        client._chat_json("sys", "user")
