from __future__ import annotations

import json

from app.utils.final_asset import build_final_asset, parse_final_asset, resolve_final_path_file


def test_parse_legacy_string():
    assert parse_final_asset("/data/media/1/final.mp4") == {
        "path": "/data/media/1/final.mp4",
        "duration": None,
        "size": None,
        "cost_time": None,
    }


def test_parse_json():
    raw = json.dumps(
        {"path": "/a/final.mp4", "duration": 123.456, "size": 2048, "cost_time": 9.8}
    )
    assert parse_final_asset(raw) == {
        "path": "/a/final.mp4",
        "duration": 123.456,
        "size": 2048,
        "cost_time": 9.8,
    }


def test_build_final_asset(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"0123456789")
    asset = build_final_asset(video, duration=12.3456, cost_time=3.456)
    assert asset["path"] == str(video)
    assert asset["duration"] == 12.346
    assert asset["size"] == 10
    assert asset["cost_time"] == 3.5


def test_resolve_final_path_file():
    assert resolve_final_path_file({"path": "/x.mp4"}) == "/x.mp4"
    assert resolve_final_path_file("/legacy.mp4") == "/legacy.mp4"
