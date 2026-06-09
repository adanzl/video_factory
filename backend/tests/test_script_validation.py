import pytest

from worker.stages.script import (
    MIN_ACCEPT_NARRATION_CHARS,
    MIN_NARRATION_CHARS,
    NARRATION_RETRY_MIN_CHARS,
    ScriptValidationError,
    _narration_short_retryable,
    _validate_script,
)


def test_narration_short_retryable_threshold():
    assert _narration_short_retryable(NARRATION_RETRY_MIN_CHARS) is True
    assert _narration_short_retryable(NARRATION_RETRY_MIN_CHARS - 1) is False


def test_validate_script_rejects_segment_over_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 12, "max_title_length": 20})(),
    )
    script = {
        "title": "短标题",
        "narration": "x" * MIN_NARRATION_CHARS,
        "segments": [{"segment_index": 1, "text": "x" * 120}],
    }
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
    assert "exceeds" in str(exc_info.value)


def test_validate_script_rejects_too_few_segments_for_cap(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 12, "max_title_length": 20})(),
    )
    script = {
        "title": "短标题",
        "narration": "x" * MIN_NARRATION_CHARS,
        "segments": [{"segment_index": 1, "text": "x" * MIN_NARRATION_CHARS}],
    }
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
    assert "too few segments" in str(exc_info.value)


def test_validate_script_narration_gap_too_large_accepts_with_warning(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = {
        "title": "短标题",
        "narration": "x" * (NARRATION_RETRY_MIN_CHARS - 1),
        "segments": [{"segment_index": 1, "text": "ok"}],
    }
    warnings = _validate_script(script)
    assert warnings
    assert str(MIN_NARRATION_CHARS) in warnings[0]


def test_validate_script_narration_below_minimum_still_fails(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = {
        "title": "短标题",
        "narration": "x" * (MIN_ACCEPT_NARRATION_CHARS - 1),
        "segments": [{"segment_index": 1, "text": "ok"}],
    }
    with pytest.raises(ScriptValidationError):
        _validate_script(script)


def test_validate_script_narration_slightly_short_is_retryable(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = {
        "title": "短标题",
        "narration": "x" * (MIN_NARRATION_CHARS - 50),
        "segments": [{"segment_index": 1, "text": "ok"}],
    }
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(script)
    assert exc_info.value.retryable is True
