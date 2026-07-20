from __future__ import annotations

import re

from app.services.segment.clip.clip_render import (
    _MOTION_MODES,
    _motion_vf,
    _pick_motion_mode,
    _prep_filter,
    _resolve_clip_canvas,
)


def test_prep_filter_scale_dimensions_are_even() -> None:
    vf = _prep_filter(headroom=1.14, width=1920, height=1080)
    match = re.search(r"scale=(\d+):(\d+)", vf)
    assert match is not None
    width, height = int(match.group(1)), int(match.group(2))
    assert width % 2 == 0
    assert height % 2 == 0
    assert height == 1232  # 1080 * 1.14 = 1231 → 1232


def test_pick_motion_mode_rotates_without_adjacent_dupes() -> None:
    modes = [_pick_motion_mode(i) for i in range(1, 17)]
    assert modes[:8] == list(_MOTION_MODES)
    assert modes[8:16] == list(_MOTION_MODES)
    for left, right in zip(modes, modes[1:]):
        assert left != right


def test_motion_vf_segment1_zoom_in_uses_center_floor() -> None:
    vf = _motion_vf(10.0, preset="ken_burns_slow", segment_index=1, width=1920, height=1080)
    assert _pick_motion_mode(1) == "zoom_in"
    assert "eval=frame" in vf
    assert "floor((iw-1920)/2)" in vf
    assert "zoompan" not in vf
    assert "fps=25" in vf


def test_motion_vf_segment2_pan_right_uses_scale_crop() -> None:
    vf = _motion_vf(
        12.0,
        preset="ken_burns_slow",
        segment_index=2,
        width=1920,
        height=1080,
    )
    assert _pick_motion_mode(2) == "pan_right"
    match = re.search(r"scale=(\d+):(\d+)", vf)
    assert match is not None
    assert int(match.group(2)) % 2 == 0
    assert "crop=1920:1080" in vf
    assert "zoompan" not in vf
    assert "floor((" in vf


def test_motion_vf_uses_livelier_ken_burns_zoom() -> None:
    vf = _motion_vf(10.0, preset="ken_burns_slow", segment_index=1, width=1080, height=1920)
    assert "1.1000" in vf or "1+0.1000" in vf


def test_resolve_clip_canvas_snaps_to_even() -> None:
    assert _resolve_clip_canvas(1921, 1081) == (1922, 1082)
