from __future__ import annotations

from app.services.media.ffmpeg_utils import _ffmpeg_error_message


def test_ffmpeg_error_message_keeps_key_lines_only() -> None:
    detail = "\n".join(
        [
            "Input #0, mov,mp4, from 'intro.mp4':",
            "  Metadata:",
            "    major_brand     : isom",
            "  Stream #0:0: Video: h264",
            "[vf#0:0] Simple filtergraph was expected to have exactly 1 input",
            "Error opening output file out.mp4: Invalid argument",
        ]
    )
    msg = _ffmpeg_error_message(detail)
    assert "major_brand" not in msg
    assert "Invalid argument" in msg
    assert "filtergraph" in msg
