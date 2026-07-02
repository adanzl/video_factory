"""成片质检：素材线短时长。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.quality.quality_mgr import check_merged_video


def test_check_merged_video_accepts_short_material_with_custom_min(tmp_path: Path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"x")
    loudness = MagicMock(integrated_lufs=-16.0, true_peak_dbtp=-1.0)

    with patch("app.quality.final_video.probe_duration", return_value=29.5):
        report = check_merged_video(final_path, loudness=loudness, min_duration_sec=25.5)

    assert report.level == "pass"
    assert report.details.get("duration_sec") == 29.5


def test_check_merged_video_rejects_short_material_with_standard_min(tmp_path: Path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"x")

    with patch("app.quality.final_video.probe_duration", return_value=29.5):
        report = check_merged_video(final_path, min_duration_sec=55.0)

    assert report.level == "major"
    assert report.details.get("reason") == "final too short"
    assert report.details.get("min_duration_sec") == 55.0
