from __future__ import annotations

import re

from app.services.media.clip.render import _motion_vf, _prep_filter, _resolve_clip_canvas


def test_prep_filter_scale_dimensions_are_even() -> None:
    vf = _prep_filter(headroom=1.14, width=1920, height=1080)
    match = re.search(r"scale=(\d+):(\d+)", vf)
    assert match is not None
    width, height = int(match.group(1)), int(match.group(2))
    assert width % 2 == 0
    assert height % 2 == 0
    assert height == 1232  # 1080 * 1.14 = 1231 → 1232


def test_motion_vf_segment6_landscape_uses_even_prep_scale() -> None:
    vf = _motion_vf(
        12.0,
        preset="ken_burns_slow",
        segment_index=6,
        width=1920,
        height=1080,
    )
    match = re.search(r"scale=(\d+):(\d+)", vf)
    assert match is not None
    assert int(match.group(2)) % 2 == 0
    assert "s=1920x1080" in vf
    assert "floor(" in vf


def test_motion_vf_uses_reduced_ken_burns_zoom() -> None:
    vf = _motion_vf(10.0, preset="ken_burns_slow", segment_index=1, width=1080, height=1920)
    assert "1.0800" in vf or "1+0.0800" in vf


def test_resolve_clip_canvas_snaps_to_even() -> None:
    assert _resolve_clip_canvas(1921, 1081) == (1922, 1082)
