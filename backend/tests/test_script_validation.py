import pytest

from app.utils.media import (
    default_narration_target_words,
    narration_accept_max_chars,
    narration_accept_min_chars,
    narration_shrink_max_chars,
    segment_text_char_cap,
    segment_text_hard_cap,
    segment_text_shrink_max,
)
from worker.stages.standard.script import (
    MIN_ACCEPT_NARRATION_CHARS,
    ScriptValidationError,
    _accept_narration_chars,
    _classify_segment_overflow,
    _min_narration_chars,
    _narration_retry_min_chars,
    _narration_short_retryable,
    _repair_narration_overflow_via_shrink,
    _repair_segment_overflow_via_shrink,
    _validate_script,
)

_IMAGE_PROMPT = "x" * 300
_VISUAL_BRIEF = "测试画面描述用于分镜校验。"
_DEFAULT_TARGET = default_narration_target_words()
_DEFAULT_MIN = _min_narration_chars(_DEFAULT_TARGET)
_DEFAULT_ACCEPT = _accept_narration_chars(_DEFAULT_TARGET)


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


def test_validate_script_accepts_slightly_short_image_prompt(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        segments=[
            {
                "segment_index": 1,
                "text": "x" * _DEFAULT_TARGET,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": "x" * 120,
            }
        ],
    )
    warnings = _validate_script(script, min_narration_chars=_DEFAULT_MIN)
    assert any("image_prompt slightly short" in w for w in warnings)


def test_validate_script_accepts_fewer_segments_than_word_budget(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 28, "max_title_length": 20})(),
    )
    target = 1350
    cap = segment_text_char_cap(28)
    needed = max(1, (target + cap - 1) // cap)
    script = _valid_script(
        narration="x" * narration_accept_min_chars(target),
        segments=[
            {
                "segment_index": i,
                "text": "x" * 60,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
            for i in range(1, needed)
        ],
    )
    _validate_script(
        script,
        min_narration_chars=_min_narration_chars(target),
        accept_narration_chars=narration_accept_min_chars(target),
        narration_target_words=target,
        segment_target_sec=28,
    )


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
    required = 882
    soft = int(required * 0.89)
    script = _valid_script(
        narration="x" * (soft - 20),
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
        _validate_script(script, min_narration_chars=required)
    assert exc_info.value.retryable is True


def test_validate_script_narration_below_accept_retries(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    script = _valid_script(
        narration="x" * (_DEFAULT_ACCEPT - 50),
        segments=[
            {
                "segment_index": 1,
                "text": "x" * (_DEFAULT_ACCEPT - 50),
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(
            script,
            min_narration_chars=_DEFAULT_MIN,
            accept_narration_chars=_DEFAULT_ACCEPT,
            narration_target_words=_DEFAULT_TARGET,
        )
    assert exc_info.value.retryable is True
    assert str(_DEFAULT_ACCEPT) in str(exc_info.value)


def test_validate_script_narration_far_below_target_retries(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    target = 1318
    accept = narration_accept_min_chars(target)
    retry_min = _narration_retry_min_chars(target)
    chars = retry_min - 10
    assert chars >= MIN_ACCEPT_NARRATION_CHARS
    assert chars < accept
    script = _valid_script(
        narration="x" * chars,
        segments=[
            {
                "segment_index": 1,
                "text": "x" * chars,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(
            script,
            min_narration_chars=_min_narration_chars(target),
            accept_narration_chars=accept,
            narration_target_words=target,
        )
    assert exc_info.value.retryable is True
    assert str(chars) in str(exc_info.value)


def test_validate_script_narration_too_long_retries(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    target = 1646
    accept_max = narration_accept_max_chars(target)
    script = _valid_script(
        narration="x" * (accept_max + 200),
        segments=[
            {
                "segment_index": 1,
                "text": "x" * (accept_max + 200),
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        _validate_script(
            script,
            min_narration_chars=_min_narration_chars(target),
            accept_narration_chars=narration_accept_min_chars(target),
            narration_target_words=target,
        )
    assert exc_info.value.retryable is True
    assert "narration too long" in str(exc_info.value)
    assert str(accept_max) in str(exc_info.value)


def test_validate_script_narration_slightly_over_accepts_with_warning(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 0, "max_title_length": 20})(),
    )
    target = 1350
    accept_max = narration_accept_max_chars(target)
    over = accept_max + 34
    assert over <= narration_shrink_max_chars(target)
    script = _valid_script(
        narration="x" * over,
        segments=[
            {
                "segment_index": 1,
                "text": "x" * over,
                "visual_brief": _VISUAL_BRIEF,
                "image_prompt": _IMAGE_PROMPT,
            }
        ],
    )
    warnings = _validate_script(
        script,
        min_narration_chars=_min_narration_chars(target),
        accept_narration_chars=narration_accept_min_chars(target),
        narration_target_words=target,
    )
    assert any("slightly over target" in w for w in warnings)


def test_repair_narration_overflow_via_shrink_mock(monkeypatch):
    monkeypatch.setattr(
        "worker.stages.standard.script.get_settings",
        lambda: type("S", (), {"segment_target_sec": 15, "max_title_length": 20})(),
    )
    target = 1350
    accept_max = narration_accept_max_chars(target)
    over = accept_max + 34
    cap = segment_text_char_cap(15.0)
    long_text = "y" * (cap + 20)
    script = {
        "title": "短标题",
        "narration": "y" * over,
        "word_count": over,
        "visual_style": "测试画风",
        "segments": [
            {"segment_index": 1, "text": long_text, "visual_brief": _VISUAL_BRIEF},
            {"segment_index": 2, "text": "z" * 80, "visual_brief": _VISUAL_BRIEF},
        ],
    }

    def _fake_shrink(s, *, segment_indices, segment_target_sec, job=None):
        for seg in s["segments"]:
            if int(seg["segment_index"]) in segment_indices:
                seg["text"] = "a" * 60
        s["narration"] = "".join(str(seg["text"]) for seg in s["segments"])
        s["word_count"] = len(s["narration"])
        return s

    monkeypatch.setattr("worker.stages.standard.script.llm_mgr.shrink_segment_texts", _fake_shrink)
    monkeypatch.setattr("worker.stages.standard.script.repo_job_log.append_log", lambda *a, **k: None)
    assert _repair_narration_overflow_via_shrink(
        script,
        narration_target_words=target,
        segment_target_sec=15.0,
        job_id=1,
        stage_name="script",
        job=None,
    )
    assert len(script["narration"]) <= accept_max


def test_classify_segment_overflow_mild_vs_severe():
    cap = segment_text_char_cap(15.0)
    hard_cap = segment_text_hard_cap(15.0)
    shrink_max = segment_text_shrink_max(15.0)
    segments = [
        {"segment_index": 1, "text": "x" * (hard_cap + 5)},
        {"segment_index": 2, "text": "x" * (shrink_max + 1)},
        {"segment_index": 3, "text": "x" * cap},
    ]
    shrinkable, severe = _classify_segment_overflow(
        segments, 15.0, speech_chars_per_sec=4.1
    )
    assert shrinkable == [1]
    assert severe == [(2, shrink_max + 1)]


def test_repair_segment_overflow_via_shrink_mock(monkeypatch):
    monkeypatch.setattr("worker.stages.standard.script.get_settings", lambda: type("S", (), {"segment_target_sec": 15, "max_title_length": 20})())
    hard_cap = segment_text_hard_cap(15.0)
    long_text = "y" * (hard_cap + 8)
    script = {
        "title": "短标题",
        "narration": long_text,
        "word_count": len(long_text),
        "visual_style": "测试画风",
        "segments": [
            {
                "segment_index": 1,
                "text": long_text,
                "visual_brief": _VISUAL_BRIEF,
            }
        ],
    }

    def _fake_shrink(s, *, segment_indices, segment_target_sec, job=None):
        cap = segment_text_char_cap(segment_target_sec)
        for seg in s["segments"]:
            if int(seg["segment_index"]) in segment_indices:
                seg["text"] = "z" * cap
        s["narration"] = "z" * cap
        s["word_count"] = cap
        return s

    monkeypatch.setattr("worker.stages.standard.script.llm_mgr.shrink_segment_texts", _fake_shrink)
    assert _repair_segment_overflow_via_shrink(
        script,
        segment_target_sec=15.0,
        speech_chars_per_sec=4.1,
        job_id=1,
        stage_name="script",
        job=None,
    )
    warnings = _validate_script(
        script,
        segment_target_sec=15.0,
        min_narration_chars=1,
        accept_narration_chars=1,
        require_image_prompt=False,
    )
    assert warnings == []
