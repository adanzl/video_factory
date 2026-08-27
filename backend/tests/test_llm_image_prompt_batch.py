"""image_prompt 分批与打回范围测试。"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.llm.llm_deepseek import (
    DeepSeekClient,
    _chunk_indices,
    _missing_image_prompt_indices,
)
from worker.stages.standard.script import ScriptValidationError, _validation_retry_scope


def test_chunk_indices():
    assert _chunk_indices([3, 1, 2, 4, 5, 6], 2) == [[1, 2], [3, 4], [5, 6]]
    assert _chunk_indices([1], 4) == [[1]]


def test_validation_retry_scope_image_prompt():
    exc = ScriptValidationError("segment 2 image_prompt too short: 10 chars (need >= 50)")
    assert _validation_retry_scope(exc) == "image_prompts"


def test_validation_retry_scope_storyboard():
    exc = ScriptValidationError("segment text exceeds 28.0s cap")
    assert _validation_retry_scope(exc) == "storyboard"


def _make_segments(n: int) -> list[dict]:
    return [{"segment_index": i} for i in range(1, n + 1)]


def test_missing_image_prompt_indices_motion_only():
    prompts = [
        {"segment_index": 1, "motion_prompt": "窗外树影轻晃"},
        {"segment_index": 2, "motion_prompt": ""},
        {"segment_index": 4, "motion_prompt": "窗帘微微飘动"},
    ]
    assert _missing_image_prompt_indices(prompts, [1, 2, 3, 4], motion_only=True) == [2, 3]


def test_missing_image_prompt_indices_image_prompt():
    prompts = [
        {"segment_index": 1, "image_prompt": "一个客厅"},
        {"segment_index": 2, "image_prompt": None},
    ]
    assert _missing_image_prompt_indices(prompts, [1, 2, 3], motion_only=False) == [2, 3]


def test_fill_image_prompts_retries_missing_segments(monkeypatch):
    """LLM 首轮漏段时，只对缺段局部重试补全，脚本正常完成。"""
    client = object.__new__(DeepSeekClient)
    script = {"title": "测试", "segments": _make_segments(4)}
    calls: list[list[int]] = []

    def fake_generate(script, **kwargs):
        calls.append(list(kwargs.get("segment_indices") or []))
        if len(calls) == 1:
            return {
                "image_prompts": [
                    {"segment_index": 1, "image_prompt": "a"},
                    {"segment_index": 2, "image_prompt": "b"},
                    {"segment_index": 4, "image_prompt": "d"},
                ]
            }
        return {"image_prompts": [{"segment_index": 3, "image_prompt": "c"}]}

    monkeypatch.setattr(get_settings(), "llm_image_prompt_batch_size", 4)
    monkeypatch.setattr(client, "_generate_image_prompts", fake_generate)

    client.fill_image_prompts(script)

    assert calls == [[1, 2, 3, 4], [3]]
    assert script["segments"][2]["image_prompt"] == "c"


def test_fill_image_prompts_retry_exhausted_still_raises(monkeypatch):
    """缺段重试耗尽后仍缺，则保留原 ValueError 硬失败行为。"""
    client = object.__new__(DeepSeekClient)
    script = {"title": "测试", "segments": _make_segments(3)}

    def fake_generate(script, **kwargs):
        return {"image_prompts": [{"segment_index": 1, "image_prompt": "a"}]}

    monkeypatch.setattr(get_settings(), "llm_image_prompt_batch_size", 4)
    monkeypatch.setattr(client, "_generate_image_prompts", fake_generate)

    with pytest.raises(ValueError, match="missing segments"):
        client.fill_image_prompts(script)

