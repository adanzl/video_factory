import pytest

from worker.stages.standard.script import (
    MIN_ACCEPT_NARRATION_CHARS,
    MIN_NARRATION_CHARS,
    NARRATION_RETRY_MIN_CHARS,
    ScriptValidationError,
    _narration_short_retryable,
    _validate_script,
)

_IMAGE_PROMPT = "x" * 300
_VISUAL_BRIEF = "测试画面描述用于分镜校验。"


def _valid_script(**overrides: object) -> dict:
    script = {
        "title": "短标题",
        "narration": "x" * MIN_NARRATION_CHARS,
        "visual_style": "测试画风定调",
        "segments": [
            {
                "segment_index": 1,
                "text": "x" * 120,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    }
    script.update(overrides)
    return script


def test_narration_short_retryable_threshold():
    assert _narration_short_retryable(NARRATION_RETRY_MIN_CHARS) is True
    assert _narration_short_retryable(NARRATION_RETRY_MIN_CHARS - 1) is False


def test_validate_script_rejects_segment_over_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 12, "max_title_length": 20})(),
    )
    script = _valid_script()
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
    assert "exceeds" in str(exc_info.value)


def test_validate_script_rejects_too_few_segments_for_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 12, "max_title_length": 20})(),
    )
    script = _valid_script(
        segments=[
            {
                "segment_index": i,
                "text": "x" * 100,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
            for i in range(1, 8)
        ]
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
    assert "too few segments" in str(exc_info.value)


def test_validate_script_narration_gap_too_large_accepts_with_warning(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        narration="x" * (NARRATION_RETRY_MIN_CHARS - 1),
        segments=[
            {
                "segment_index": 1,
                "text": "ok",
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    warnings = _validate_script(script)
    assert warnings
    assert str(MIN_NARRATION_CHARS) in warnings[0]


def test_validate_script_narration_below_minimum_still_fails(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        narration="x" * (MIN_ACCEPT_NARRATION_CHARS - 1),
        segments=[
            {
                "segment_index": 1,
                "text": "ok",
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError):
        _validate_script(script)


def test_validate_script_narration_slightly_short_is_retryable(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        narration="x" * (MIN_NARRATION_CHARS - 50),
        segments=[
            {
                "segment_index": 1,
                "text": "ok",
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
