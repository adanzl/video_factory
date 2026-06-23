"""image_prompt 分批与打回范围测试。"""

from __future__ import annotations

from app.services.llm.llm_deepseek import _chunk_indices
from worker.stages.standard.script import ScriptValidationError, _validation_retry_scope


def test_chunk_indices():
    assert _chunk_indices([3, 1, 2, 4, 5, 6], 2) == [[1, 2], [3, 4], [5, 6]]
    assert _chunk_indices([1], 4) == [[1]]


def test_validation_retry_scope_image_prompt():
    exc = ScriptValidationError("segment 2 image_prompt too short: 274 chars (need >= 200)")
    assert _validation_retry_scope(exc) == "image_prompts"


def test_validation_retry_scope_storyboard():
    exc = ScriptValidationError("segment text exceeds 28.0s cap")
    assert _validation_retry_scope(exc) == "storyboard"
