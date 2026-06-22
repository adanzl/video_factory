import pytest

from app.utils.media import default_narration_target_words, segment_text_char_cap
from worker.stages.standard.script import (
    MIN_ACCEPT_NARRATION_CHARS,
    ScriptValidationError,
    _min_narration_chars,
    _narration_retry_min_chars,
    _narration_short_retryable,
    _validate_script,
)

_IMAGE_PROMPT = "x" * 300
_VISUAL_BRIEF = "测试画面描述用于分镜校验。"
_DEFAULT_TARGET = default_narration_target_words()
_DEFAULT_MIN = _min_narration_chars(_DEFAULT_TARGET)


def _valid_script(**overrides: object) -> dict:
    script = {
        "title": "短标题",
        "narration": "x" * _DEFAULT_TARGET,
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
    retry_min = _narration_retry_min_chars(_DEFAULT_TARGET)
    assert _narration_short_retryable(retry_min, narration_target_words=_DEFAULT_TARGET) is True
    assert (
        _narration_short_retryable(retry_min - 1, narration_target_words=_DEFAULT_TARGET)
        is False
    )


def test_validate_script_rejects_segment_over_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 16, "max_title_length": 20})(),
    )
    cap = segment_text_char_cap(16)
    script = _valid_script(
        segments=[
            {
                "segment_index": 1,
                "text": "x" * (cap + 20),
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script, min_narration_chars=_DEFAULT_MIN)
    assert exc_info.value.retryable is True
    assert "exceeds" in str(exc_info.value)


def test_validate_script_rejects_too_few_segments_for_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 16, "max_title_length": 20})(),
    )
    cap = segment_text_char_cap(16)
    needed = max(1, (_DEFAULT_TARGET + cap - 1) // cap)
    script = _valid_script(
        segments=[
            {
                "segment_index": i,
                "text": "x" * 70,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
            for i in range(1, needed)
        ]
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script, min_narration_chars=_DEFAULT_MIN)
    assert exc_info.value.retryable is True
    assert "too few segments" in str(exc_info.value)


def test_validate_script_narration_gap_too_large_accepts_with_warning(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    retry_min = _narration_retry_min_chars(_DEFAULT_TARGET)
    script = _valid_script(
        narration="x" * (retry_min - 1),
        segments=[
            {
                "segment_index": 1,
                "text": "ok",
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    warnings = _validate_script(script, min_narration_chars=_DEFAULT_MIN)
    assert warnings
    assert str(_DEFAULT_MIN) in warnings[0]


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
        _validate_script(script, min_narration_chars=_DEFAULT_MIN)


def test_validate_script_narration_slightly_short_is_retryable(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        narration="x" * (_DEFAULT_MIN - 10),
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
        _validate_script(script, min_narration_chars=_DEFAULT_MIN)
    assert exc_info.value.retryable is True
