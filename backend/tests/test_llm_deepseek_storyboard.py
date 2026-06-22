"""DeepSeek 分镜后处理测试。"""

from __future__ import annotations

from app.services.llm.llm_deepseek import _assemble_storyboard_narration


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
