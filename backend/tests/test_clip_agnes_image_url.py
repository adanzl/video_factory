from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.media.clip.video_agnes import (
    _is_reverse_proxy_public_url,
    _mirror_image_public_url,
    _read_agnes_source_url,
    _resolve_i2v_image_url,
)


def test_read_agnes_source_url_sidecar(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    sidecar = image.with_name(image.name + ".agnes_source_url")
    sidecar.write_text("https://storage.googleapis.com/agnes-aigc/test.png", encoding="utf-8")
    assert _read_agnes_source_url(image) == "https://storage.googleapis.com/agnes-aigc/test.png"


def test_resolve_i2v_image_url_prefers_sidecar(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    sidecar = image.with_name(image.name + ".agnes_source_url")
    cdn = "https://storage.googleapis.com/agnes-aigc/aigc/images/test.png"
    sidecar.write_text(cdn, encoding="utf-8")
    with patch(
        "app.services.media.clip.video_agnes._to_public_media_url",
        return_value="https://natapp.example/v_factory/api/media/files/mnt/data/1.png",
    ):
        assert _resolve_i2v_image_url(image) == cdn


def test_mirror_image_public_url(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"png-bytes")
    with patch("app.services.media.clip.video_agnes._mirror_tmpfiles") as mock_tmp:
        mock_tmp.return_value = "https://tmpfiles.org/dl/12345/frame.png"
        url = _mirror_image_public_url(image)
    assert url == "https://tmpfiles.org/dl/12345/frame.png"


def test_is_reverse_proxy_public_url() -> None:
    assert _is_reverse_proxy_public_url("https://leo-zhao.natapp4.cc/foo")
    assert not _is_reverse_proxy_public_url("https://example.com/foo")


def test_resolve_i2v_image_url_mirrors_natapp(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    mirror_url = "https://litterbox.catbox.moe/abc/frame.png"
    with (
        patch(
            "app.services.media.clip.video_agnes._to_public_media_url",
            return_value="https://leo-zhao.natapp4.cc/v_factory/api/media/files/mnt/data/1.png",
        ),
        patch(
            "app.services.media.clip.video_agnes._mirror_image_public_url",
            return_value=mirror_url,
        ) as mock_mirror,
        patch("app.services.media.clip.video_agnes._url_reachable", return_value=True),
    ):
        assert _resolve_i2v_image_url(image) == mirror_url
    mock_mirror.assert_called_once_with(image)
