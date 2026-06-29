from __future__ import annotations

import sqlite3

from app.repositories import job_repo, segment_repo
from app.repositories.schema import apply_schema


def test_insert_segments_preserves_media_paths() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    job = job_repo.create_job(conn, "test preserve media")
    job_id = job["id"]
    segment_repo.insert_segments(
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
    rows = segment_repo.list_segments(conn, job_id)
    segment_repo.update_segment(
        conn,
        rows[0]["id"],
        image_path="/data/1.png",
        clip_path="/data/1.mp4",
        status="done",
    )
    segment_repo.update_segment(
        conn,
        rows[1]["id"],
        image_path="/data/2.png",
        status="done",
    )

    segment_repo.insert_segments(
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

    updated = segment_repo.list_segments(conn, job_id)
    by_index = {row["segment_index"]: row for row in updated}
    assert by_index[1]["image_prompt"] == "new prompt"
    assert by_index[1]["image_path"] == "/data/1.png"
    assert by_index[1]["clip_path"] == "/data/1.mp4"
    assert by_index[1]["status"] == "done"
    assert by_index[2]["image_path"] == "/data/2.png"
