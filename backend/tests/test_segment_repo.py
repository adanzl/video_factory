from __future__ import annotations

import sqlite3

from app.repositories import repo_job, repo_segment
from app.repositories.schema import apply_schema


def test_insert_segments_preserves_media_paths() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    job = repo_job.create_job(conn, "test preserve media")
    job_id = job["id"]
    repo_segment.insert_segments(
        conn,
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "image_prompt": "old prompt",
                "motion_prompt": "motion",
                "visual_mode": "static_motion",
            },
            {
                "segment_index": 2,
                "text": "b",
                "image_prompt": "old prompt 2",
                "motion_prompt": "motion 2",
                "visual_mode": "static_motion",
            },
        ],
    )
    rows = repo_segment.list_segments(conn, job_id)
    repo_segment.update_segment(
        conn,
        rows[0]["id"],
        image_path="/data/1.png",
        clip_path="/data/1.mp4",
        status="done",
        version=3,
    )
    repo_segment.update_segment(
        conn,
        rows[1]["id"],
        image_path="/data/2.png",
        status="done",
        version=5,
    )

    repo_segment.insert_segments(
        conn,
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "image_prompt": "new prompt",
                "motion_prompt": "new motion",
                "visual_mode": "static_motion",
            },
            {
                "segment_index": 2,
                "text": "b",
                "image_prompt": "old prompt 2",
                "motion_prompt": "motion 2",
                "visual_mode": "static_motion",
            },
        ],
    )

    updated = repo_segment.list_segments(conn, job_id)
    by_index = {row["segment_index"]: row for row in updated}
    assert by_index[1]["image_prompt"] == "new prompt"
    assert by_index[1]["image_path"] == "/data/1.png"
    assert by_index[1]["clip_path"] == "/data/1.mp4"
    assert by_index[1]["status"] == "done"
    assert by_index[1]["version"] == 3
    assert by_index[2]["image_path"] == "/data/2.png"
    assert by_index[2]["version"] == 5
