from __future__ import annotations

from app.repositories import repo_job, repo_segment


def test_insert_segments_preserves_media_paths(app_ctx) -> None:
    job = repo_job.create_job("test preserve media")
    job_id = job["id"]
    repo_segment.insert_segments(
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
    rows = repo_segment.list_segments(job_id)
    repo_segment.update_segment(
        rows[0]["id"],
        image_path="/data/1.png",
        clip_path="/data/1.mp4",
        status="done",
        version=3,
    )
    repo_segment.update_segment(
        rows[1]["id"],
        image_path="/data/2.png",
        status="done",
        version=5,
    )

    repo_segment.insert_segments(
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

    updated = repo_segment.list_segments(job_id)
    by_index = {row["segment_index"]: row for row in updated}
    assert by_index[1]["image_prompt"] == "new prompt"
    assert by_index[1]["image_path"] == "/data/1.png"
    assert by_index[1]["clip_path"] == "/data/1.mp4"
    assert by_index[1]["status"] == "done"
    assert by_index[1]["version"] == 3
    assert by_index[2]["image_path"] == "/data/2.png"
    assert by_index[2]["version"] == 5


def test_insert_segments_stores_info_json(app_ctx) -> None:
    job = repo_job.create_job("test segment info")
    job_id = job["id"]
    repo_segment.insert_segments(
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "visual_mode": "static_motion",
                "info": {"video_provider": "agnes_i2v"},
            },
            {
                "segment_index": 2,
                "text": "b",
                "visual_mode": "static_motion",
            },
        ],
    )
    rows = {row["segment_index"]: row for row in repo_segment.list_segments(job_id)}
    assert rows[1]["info"]["video_provider"] == "agnes_i2v"
    assert "info" not in rows[2]

    repo_segment.update_segment(rows[1]["id"], info={"video_provider": "ffmpeg"})
    updated = {row["segment_index"]: row for row in repo_segment.list_segments(job_id)}
    assert updated[1]["info"]["video_provider"] == "ffmpeg"

    repo_segment.insert_segments(
        job_id,
        [
            {"segment_index": 1, "text": "a2", "visual_mode": "static_motion"},
            {"segment_index": 2, "text": "b2", "visual_mode": "static_motion"},
        ],
    )
    rebuilt = {row["segment_index"]: row for row in repo_segment.list_segments(job_id)}
    assert rebuilt[1]["info"]["video_provider"] == "ffmpeg"
    assert rebuilt[1]["text"] == "a2"


def test_insert_segments_preserves_tts_duration_sec(app_ctx) -> None:
    job = repo_job.create_job("test preserve duration")
    job_id = job["id"]
    repo_segment.insert_segments(
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "visual_mode": "static_motion",
                "duration_sec": 8.78,
            },
        ],
    )
    rows = repo_segment.list_segments(job_id)
    repo_segment.update_segment(rows[0]["id"], duration_sec=9.795)

    repo_segment.insert_segments(
        job_id,
        [
            {
                "segment_index": 1,
                "text": "a",
                "visual_mode": "static_motion",
                "duration_sec": 8.78,
                "image_prompt": "new prompt",
            },
        ],
    )

    updated = repo_segment.list_segments(job_id)[0]
    assert updated["duration_sec"] == 9.795
    assert updated["image_prompt"] == "new prompt"
