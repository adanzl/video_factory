from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.visual.image_agnes import AgnesImageProvider, _to_agnes_size


def test_to_agnes_size() -> None:
    assert _to_agnes_size("720*1280") == "720x1280"
    assert _to_agnes_size("1920x1080") == "1920x1080"


def test_generate_downloads_url(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    provider._api_key = "test-key"  # noqa: SLF001
    output = tmp_path / "1.png"

    mock_post = MagicMock()
    mock_post.json.return_value = {"data": [{"url": "https://example.com/out.png"}]}
    mock_post.raise_for_status = MagicMock()

    mock_img = MagicMock()
    mock_img.content = b"png-bytes"
    mock_img.raise_for_status = MagicMock()

    with (
        patch.object(provider, "_request", return_value=mock_post) as mock_request,
        patch("app.services.visual.image_agnes.requests.get", return_value=mock_img),
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    mock_request.assert_called_once()
    payload = mock_request.call_args.kwargs["json"]
    assert payload["model"] == provider._model  # noqa: SLF001
    assert payload["size"] == "720x1280"
    assert payload["extra_body"] == {"response_format": "url"}
    assert output.read_bytes() == b"png-bytes"
