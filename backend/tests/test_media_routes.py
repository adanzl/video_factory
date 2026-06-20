from __future__ import annotations

import os

import pytest

from app.services.media.media_serve_mgr import media_serve_mgr
from app.utils.media_path import (
    normalize_media_path,
    resolve_media_serve_path,
    to_media_url_path,
)


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("VIDEO_DATA_DIR", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(data_root / "data.db"))
    monkeypatch.setenv("ALLOWED_DIR", "")
    media_serve_mgr.allowed_roots = [str(root.resolve()), str(data_root.resolve())]
    return root


def test_to_media_url_path_strips_leading_slash():
    assert to_media_url_path("/mnt/data/clip.mp4") == "mnt/data/clip.mp4"


def test_normalize_media_path_rejects_relative(media_root):
    with pytest.raises(ValueError, match="absolute"):
        normalize_media_path("clip.mp4", allowed_roots=media_serve_mgr.allowed_roots)


def test_normalize_media_path_rejects_traversal(media_root):
    with pytest.raises(ValueError, match="traversal"):
        normalize_media_path("../secret.mp4", allowed_roots=media_serve_mgr.allowed_roots)


def test_normalize_media_path_absolute(media_root):
    file_path = media_root / "clip.mp4"
    file_path.write_bytes(b"x")
    resolved = normalize_media_path(
        str(file_path.resolve()),
        allowed_roots=media_serve_mgr.allowed_roots,
    )
    assert resolved == str(file_path.resolve())


def test_resolve_media_serve_path_absolute_without_leading_slash(media_root):
    file_path = media_root / "intro.mp4"
    file_path.write_bytes(b"video")
    abs_path = str(file_path.resolve())
    url_path = to_media_url_path(abs_path)
    resolved = resolve_media_serve_path(url_path, allowed_roots=media_serve_mgr.allowed_roots)
    assert os.path.normpath(resolved) == os.path.normpath(str(file_path.resolve()))


def test_resolve_media_serve_path_nested_audio(media_root):
    file_path = media_root / "13" / "audio" / "narration.mp3"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"audio")
    url_path = to_media_url_path(str(file_path.resolve()))
    resolved = resolve_media_serve_path(
        url_path,
        allowed_roots=media_serve_mgr.allowed_roots,
    )
    assert os.path.normpath(resolved) == os.path.normpath(str(file_path.resolve()))


def test_resolve_media_serve_path_rejects_relative(media_root):
    with pytest.raises(FileNotFoundError, match="absolute"):
        resolve_media_serve_path(
            "13/audio/narration.mp3",
            allowed_roots=media_serve_mgr.allowed_roots,
        )


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
    url_path = to_media_url_path(str(file_path.resolve()))
    result = media_serve_mgr.prepare_serve_file(url_path)
    assert os.path.normpath(result["path"]) == os.path.normpath(str(file_path.resolve()))
    assert result["mimetype"] == "video/mp4"
