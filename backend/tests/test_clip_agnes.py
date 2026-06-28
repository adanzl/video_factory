from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.media.clip.video_agnes import AgnesClipProvider, _backoff_seconds, _pick_num_frames
from app.utils.job_info import normalize_video_provider, resolve_video_provider
from app.utils.media_path import resolve_media_public_base_url


def test_backoff_seconds_429() -> None:
    assert _backoff_seconds(0, status_code=429) >= 30.0
    assert _backoff_seconds(2, status_code=429) >= 70.0


def test_backoff_seconds_submit_timeout() -> None:
    assert _backoff_seconds(0, label="submit", is_timeout=True) >= 45.0


def test_pick_num_frames() -> None:
    assert _pick_num_frames(2.5, 24) == 81
    assert _pick_num_frames(5.0, 24) == 121
    assert _pick_num_frames(20.0, 24) == 441


def test_normalize_video_provider_agnes() -> None:
    assert normalize_video_provider("agnes_i2v") == "agnes_i2v"


def test_resolve_video_provider_agnes_override() -> None:
    settings = SimpleNamespace(clip_provider="ffmpeg")
    job = {"info": {"video_provider": "agnes_i2v"}}
    assert resolve_video_provider(job, visual_mode="static_motion", settings=settings) == "agnes_i2v"


def test_resolve_media_public_base_url_from_cors() -> None:
    settings = SimpleNamespace(
        media_public_base_url=None,
        get_cors_origins=lambda: ["http://localhost:5173", "https://example.com"],
    )
    assert resolve_media_public_base_url(settings) == "https://example.com"


def test_agnes_clip_provider_submits_image_url(tmp_path: Path) -> None:
    provider = AgnesClipProvider()
    provider._api_key = "test-key"  # noqa: SLF001
    image_path = tmp_path / "1.png"
    image_path.write_bytes(b"png")
    output_path = tmp_path / "clip.mp4"

    create_resp = MagicMock()
    create_resp.json.return_value = {
        "video_id": "video_test",
        "task_id": "task_test",
        "status": "queued",
    }
    create_resp.raise_for_status = MagicMock()

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "status": "completed",
        "remixed_from_video_id": "https://example.com/out.mp4",
    }
    poll_resp.raise_for_status = MagicMock()

    video_resp = MagicMock()
    video_resp.content = b"mp4-bytes"
    video_resp.raise_for_status = MagicMock()

    with (
        patch(
            "app.services.media.clip.video_agnes.resolve_media_public_base_url",
            return_value="https://example.com",
        ),
        patch("app.services.media.clip.video_agnes._url_reachable", return_value=True),
        patch.object(provider, "_request", side_effect=[create_resp, poll_resp]) as mock_request,
        patch("app.services.media.clip.video_agnes.requests.get", return_value=video_resp),
        patch("app.services.media.clip.video_agnes.probe_duration", return_value=5.0),
        patch("app.services.media.clip.video_agnes.fit_video_duration") as mock_fit,
        patch("app.services.media.clip.video_agnes.video_to_clip_timed_overlays"),
        patch("app.services.media.clip.video_agnes.clip_mgr.prepare_subtitle_overlays") as mock_overlays,
        patch("app.services.media.clip.video_agnes.clip_mgr.cleanup_overlay_paths"),
    ):
        mock_overlays.return_value = (5.0, [], [])
        mock_fit.side_effect = lambda src, dst, *_args, **_kwargs: dst.write_bytes(b"fit")
        provider.build_segment_clip(
            image_path=image_path,
            subtitle_cues=[("hello", 5.0)],
            output_path=output_path,
            motion_preset="ken_burns_slow",
            work_dir=tmp_path / "work",
            segment_index=1,
            motion_prompt="slow zoom",
            width=720,
            height=1280,
        )

    create_call = mock_request.call_args_list[0]
    payload = create_call.kwargs["json"]
    assert payload["model"] == provider._model  # noqa: SLF001
    assert payload["mode"] == "ti2vid"
    assert payload["image"].startswith("https://example.com/v_factory/api/media/files/")
    assert "width" not in payload
    assert "height" not in payload
    assert payload["num_frames"] == 121
