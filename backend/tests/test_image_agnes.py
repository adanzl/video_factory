from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.llm.llm_agnes import AgnesApiKey
from app.services.segment.image.image_agnes import AgnesImageProvider, _to_agnes_size


def test_to_agnes_size() -> None:
    assert _to_agnes_size("720*1280") == "720x1280"
    assert _to_agnes_size("1920x1080") == "1920x1080"


def test_generate_downloads_url(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"

    mock_post = MagicMock()
    mock_post.json.return_value = {"data": [{"url": "https://example.com/out.png"}]}
    mock_post.raise_for_status = MagicMock()

    mock_img = MagicMock()
    mock_img.content = b"png-bytes"
    mock_img.raise_for_status = MagicMock()

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "test-key")],
        ),
        patch.object(provider, "_request", return_value=mock_post) as mock_request,
        patch("app.services.segment.image.image_agnes.requests.get", return_value=mock_img),
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    mock_request.assert_called_once()
    assert mock_request.call_args.kwargs["api_key"] == "test-key"
    payload = mock_request.call_args.kwargs["json"]
    assert payload["model"] == provider._model  # noqa: SLF001
    assert payload["size"] == "720x1280"
    assert payload["extra_body"] == {"response_format": "url"}
    assert output.read_bytes() == b"png-bytes"


def test_generate_switches_to_backup_key_on_quota(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"

    mock_post = MagicMock()
    mock_post.json.return_value = {"data": [{"url": "https://example.com/out.png"}]}
    mock_post.raise_for_status = MagicMock()

    mock_img = MagicMock()
    mock_img.content = b"png-bytes"
    mock_img.raise_for_status = MagicMock()

    from app.services.llm.llm_agnes import AgnesQuotaExceeded

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[
                AgnesApiKey("free", "free-key"),
                AgnesApiKey("primary", "main-key"),
            ],
        ),
        patch.object(
            provider,
            "_generate_with_key",
            side_effect=[AgnesQuotaExceeded("429"), output],
        ) as mock_generate,
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    assert mock_generate.call_count == 2
    assert mock_generate.call_args_list[0].args[0].value == "free-key"
    assert mock_generate.call_args_list[1].args[0].value == "main-key"


def test_concurrent_submit_staggered() -> None:
    import time

    import gevent

    from app.config import get_settings

    settings = get_settings()
    workers = max(2, settings.image_max_workers)
    stagger = max(0.5, settings.image_submit_interval_sec)

    AgnesImageProvider._inflight = None  # noqa: SLF001
    with (
        patch.object(get_settings(), "image_max_workers", workers),
        patch.object(get_settings(), "image_submit_interval_sec", stagger),
    ):
        provider = AgnesImageProvider()
        starts: list[float] = []

        def worker() -> None:
            provider._acquire_submit_slot()  # noqa: SLF001
            starts.append(time.monotonic())
            gevent.sleep(0.05)
            provider._release_submit_slot()  # noqa: SLF001

        green_lets = [gevent.spawn(worker) for _ in range(workers)]
        gevent.joinall(green_lets)

    assert len(starts) == workers
    starts.sort()
    for i in range(1, workers):
        gap = starts[i] - starts[i - 1]
        assert gap >= stagger * 0.8, f"expected stagger ~{stagger}s, got {gap:.2f}s"
