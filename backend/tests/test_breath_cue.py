"""气口解析与 SSML 构建测试。"""

from __future__ import annotations

from app.services.tts.breath_cue import (
    PAUSE_MARK,
    BreathCueParsed,
    is_usable,
    post_process,
    scale_pause_ms_to_fit_slot,
    _sanitize_mark_adjacent_punct,
)
from app.services.tts.ssml_build import build_ssml_from_breath_cue


def test_sanitize_drops_punct_beside_mark():
    segmented, pauses = _sanitize_mark_adjacent_punct("都没空调·，夏天", [88])
    assert segmented == "都没空调·夏天"
    assert pauses == [88]


def test_sanitize_drops_mark_beside_question():
    segmented, pauses = _sanitize_mark_adjacent_punct("你知道吗？·欧洲", [90])
    assert segmented == "你知道吗？欧洲"
    assert pauses == []


def test_sanitize_drops_mark_after_question():
    segmented, pauses = _sanitize_mark_adjacent_punct("你知道吗？·欧洲", [90])
    assert "·" not in segmented
    assert pauses == []


def test_post_process_llm_punct_adjacent_marks():
    original = "欧洲好多房子都没空调，夏天热得像烤炉！"
    raw = (
        '{"text":"欧洲好多房子都没空调·，夏天热得像烤炉！",'
        '"pause_ms":[88]}'
    )
    parsed = post_process(original, raw)
    assert parsed is not None
    assert is_usable(parsed)
    assert parsed.segmented.replace(PAUSE_MARK, "") == original


def test_build_ssml_strips_comma_before_break():
    parsed = BreathCueParsed(
        segmented="阳光直射着窄窄的街道，·街边石头",
        pause_ms=[74],
    )
    ssml = build_ssml_from_breath_cue(parsed)
    assert ssml is not None
    assert "街道，<break" not in ssml
    assert "街道<break" in ssml


def test_build_ssml_skips_break_after_question():
    parsed = BreathCueParsed(
        segmented="你知道吗？·欧洲好多房子都没空调，",
        pause_ms=[80],
    )
    ssml = build_ssml_from_breath_cue(parsed)
    assert ssml is not None
    assert "你知道吗？欧洲" in ssml
    assert "你知道吗？<break" not in ssml


def test_scale_pause_ms_to_fit_slot():
    scaled = scale_pause_ms_to_fit_slot(10.0, 10.0, [200, 200])
    assert scaled == [0, 0]
    ok = scale_pause_ms_to_fit_slot(10.0, 9.0, [1000, 1000])
    assert sum(ok) == 1000
