from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.media.ffmpeg_utils import prepend_intro

_COMPAT_VIDEO = {
    "codec": "h264",
    "codec_tag": "avc1",
    "width": 1920,
    "height": 1080,
    "pix_fmt": "yuv420p",
    "fps": 25.0,
    "profile": "High",
    "level": 40,
    "sar_square": True,
}
_COMPAT_AUDIO = {"codec": "aac", "sample_rate": 44100, "channels": 1}


def test_prepend_intro_uses_concat_when_streams_compatible(tmp_path: Path) -> None:
    intro = tmp_path / "intro.mp4"
    body = tmp_path / "body.mp4"
    out = tmp_path / "final.mp4"
    intro.write_bytes(b"i")
    body.write_bytes(b"b")

    with (
        patch("app.services.media.ffmpeg_utils._probe_video_stream", return_value=_COMPAT_VIDEO),
        patch("app.services.media.ffmpeg_utils._probe_audio_stream", return_value=_COMPAT_AUDIO),
        patch("app.services.media.ffmpeg_utils.concat_clips", return_value=out) as mock_concat,
        patch("app.services.media.ffmpeg_utils._run_cmd") as mock_run,
    ):
        result = prepend_intro(intro, body, out)

    mock_concat.assert_called_once_with([intro, body], out)
    mock_run.assert_not_called()
    assert result == out


def test_prepend_intro_aligns_intro_then_concat(tmp_path: Path) -> None:
    intro = tmp_path / "intro.mp4"
    body = tmp_path / "body.mp4"
    out = tmp_path / "final.mp4"
    intro.write_bytes(b"i")
    body.write_bytes(b"b")

    with (
        patch(
            "app.services.media.ffmpeg_utils._can_concat_demuxer_copy",
            side_effect=[False, True],
        ),
        patch("app.services.media.ffmpeg_utils._probe_video_stream", return_value=_COMPAT_VIDEO),
        patch("app.services.media.ffmpeg_utils._prepend_stream_mismatch", return_value={"v.fps": {"intro": 25.0, "body": 30.0}}),
        patch("app.services.media.ffmpeg_utils._align_intro_to_body", return_value=intro) as mock_align,
        patch("app.services.media.ffmpeg_utils.concat_clips", return_value=out) as mock_concat,
        patch("app.services.media.ffmpeg_utils._run_cmd") as mock_run,
    ):
        result = prepend_intro(intro, body, out)

    mock_align.assert_called_once()
    aligned = tmp_path / "prepend_work" / "intro_aligned.mp4"
    mock_concat.assert_called_once_with([aligned, body], out)
    mock_run.assert_not_called()
    assert result == out


def test_prepend_intro_reencodes_when_align_insufficient(tmp_path: Path) -> None:
    intro = tmp_path / "intro.mp4"
    body = tmp_path / "body.mp4"
    out = tmp_path / "final.mp4"
    intro.write_bytes(b"i")
    body.write_bytes(b"b")
    body_video = dict(_COMPAT_VIDEO)
    body_video["profile"] = "Main"

    with (
        patch("app.services.media.ffmpeg_utils._can_concat_demuxer_copy", return_value=False),
        patch("app.services.media.ffmpeg_utils._align_intro_to_body", return_value=intro),
        patch("app.services.media.ffmpeg_utils._prepend_stream_mismatch", return_value={"v.profile": {"intro": "High", "body": "Main"}}),
        patch("app.services.media.ffmpeg_utils._probe_video_stream", return_value=body_video),
        patch("app.services.media.ffmpeg_utils._probe_audio_sample_rate", return_value=44100),
        patch("app.services.media.ffmpeg_utils.probe_duration", return_value=2.0),
        patch("app.services.media.ffmpeg_utils.concat_clips") as mock_concat,
        patch("app.services.media.ffmpeg_utils._run_cmd") as mock_run,
        patch("app.services.media.ffmpeg_utils.run_ffmpeg") as mock_ffmpeg,
    ):
        prepend_intro(intro, body, out)

    mock_concat.assert_not_called()
    mock_ffmpeg.assert_called_once()
