"""DeepSeek 分镜后处理测试。"""

from __future__ import annotations

from app.services.llm.llm_deepseek import (
    _apply_segments_from_narration,
    _assemble_storyboard_narration,
    _loads_llm_json,
)
from app.utils.media import segment_text_char_cap


def test_apply_segments_from_narration_respects_cap():
    narration = "第一句。" + "字" * 70 + "。第二句。"
    data = {"narration": narration, "visual_style": "写实", "title": "测试"}
    out = _apply_segments_from_narration(data, segment_target_sec=15.0)
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

