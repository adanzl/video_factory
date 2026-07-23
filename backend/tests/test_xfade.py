import pytest

from app.services.media.ffmpeg_utils import (
    build_segment_video_filter_complex,
    normalize_xfade_transition,
    resolve_effective_xfade,
)
from app.utils.job_info import normalize_xfade_payload, xfade_params_from_info


def test_normalize_xfade_transition_none():
    assert normalize_xfade_transition(None) == "none"
    assert normalize_xfade_transition("") == "none"
    assert normalize_xfade_transition("none") == "none"
    assert normalize_xfade_transition("fade") == "fade"


def test_normalize_xfade_transition_invalid():
    with pytest.raises(ValueError, match="unsupported"):
        normalize_xfade_transition("not_a_transition")


def test_resolve_effective_xfade_clamps_to_short_segment():
    transition, fade = resolve_effective_xfade(
        transition="fade",
        duration_sec=0.8,
        scaled_durations=[1.0, 1.2, 1.0],
    )
    assert transition == "fade"
    assert fade == pytest.approx(0.45)


def test_build_segment_video_filter_concat_when_none():
    fc, label = build_segment_video_filter_complex(
        3,
        factors=[1.0, 1.0, 1.0],
        scaled_durations=[10.0, 12.0, 11.0],
        fade_sec=0.4,
        transition="none",
    )
    assert "concat=n=3" in fc
    assert "xfade" not in fc
    assert label == "vout"


def test_build_segment_video_filter_xfade_chain():
    fc, label = build_segment_video_filter_complex(
        3,
        factors=[1.0, 1.02, 0.98],
        scaled_durations=[10.0, 12.0, 11.0],
        fade_sec=0.4,
        transition="fade",
    )
    assert "[v0][v1]xfade=transition=fade:duration=0.400:offset=9.600" in fc
    assert "[vx1][v2]xfade=transition=fade:duration=0.400:offset=21.200" in fc
    assert "fps=25" in fc
    assert "format=yuv420p" in fc
    assert label == "vout"


def test_xfade_params_from_info_job_override():
    params = xfade_params_from_info(
        {"xfade": {"transition": "wipeleft", "duration_sec": 0.5}}
    )
    assert params["enabled"] is True
    assert params["transition"] == "wipeleft"
    assert params["duration_sec"] == 0.5


def test_normalize_xfade_payload():
    payload = normalize_xfade_payload({"transition": "fade", "duration_sec": 0.3})
    assert payload == {"transition": "fade", "duration_sec": 0.3}
