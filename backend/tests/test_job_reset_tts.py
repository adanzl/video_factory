"""TTS 重跑清理：应清空分镜 clip_path。"""

from __future__ import annotations

from pathlib import Path

from app.repositories import repo_job, repo_segment
from app.services.job import job_reset


def test_clear_tts_artifacts_clears_clip_path(app_ctx, tmp_path: Path) -> None:
    job = repo_job.create_job("tts clear clips")
    job_id = int(job["id"])
    repo_segment.insert_segments(
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "image_prompt": "p1",
                "motion_prompt": "m1",
                "visual_mode": "static_motion",
            },
            {
                "segment_index": 2,
                "text": "b",
                "image_prompt": "p2",
                "motion_prompt": "m2",
                "visual_mode": "static_motion",
            },
        ],
    )
    rows = repo_segment.list_segments(job_id)
    repo_segment.update_segment(
        rows[0]["id"], clip_path="/data/1.mp4", duration_sec=3.0
    )
    repo_segment.update_segment(
        rows[1]["id"], clip_path="/data/2.mp4", duration_sec=4.0
    )

    media_dir = tmp_path / str(job_id)
    media_dir.mkdir()
    job_reset._db_clear_tts(job_id)
    job_reset._fs_clear_tts(media_dir)

    updated = repo_segment.list_segments(job_id)
    assert all(row["clip_path"] is None for row in updated)
    assert all(row["duration_sec"] is None for row in updated)
