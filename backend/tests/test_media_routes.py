from __future__ import annotations

from pathlib import Path

import pytest

from app.services.media.media_serve_mgr import media_serve_mgr
from app.utils.media_path import normalize_media_path


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("VIDEO_DATA_DIR", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(data_root / "data.db"))
    media_serve_mgr.allowed_roots = [root.resolve(), data_root.resolve()]
    return root


def test_normalize_media_path_relative(media_root):
    file_path = media_root / "clip.mp4"
    file_path.write_bytes(b"x")
    resolved = normalize_media_path("clip.mp4", allowed_roots=media_serve_mgr.allowed_roots)
    assert resolved == file_path.resolve()


def test_normalize_media_path_rejects_traversal(media_root):
    with pytest.raises(ValueError, match="traversal"):
        normalize_media_path("../secret.mp4", allowed_roots=media_serve_mgr.allowed_roots)


def test_get_duration(media_root, monkeypatch):
    file_path = media_root / "a.mp4"
    file_path.write_bytes(b"x")
    monkeypatch.setattr(
        "app.services.media.media_serve_mgr.probe_duration",
        lambda path: 3.25,
    )
    result = media_serve_mgr.get_duration(str(file_path))
    assert result["duration"] == 3.25


def test_prepare_serve_file(media_root):
    file_path = media_root / "final.mp4"
    file_path.write_bytes(b"video")
    result = media_serve_mgr.prepare_serve_file(str(file_path))
    assert result["path"] == str(file_path.resolve())
    assert result["mimetype"] == "video/mp4"
