"""job_reset 清理：TTS clip、segment/all 静图路径等。"""

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


def test_segment_all_with_indices_clears_image_and_clip(
    app_ctx, tmp_path: Path
) -> None:
    """segment/all 带分镜序号时须清 image_path（旧逻辑只清 clip）。"""
    job = repo_job.create_job("segment all clear", stage="segment", status="done")
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
        rows[0]["id"],
        image_path="/data/1.png",
        clip_path="/data/1.mp4",
    )
    repo_segment.update_segment(
        rows[1]["id"],
        image_path="/data/2.png",
        clip_path="/data/2.mp4",
    )

    media_dir = tmp_path / str(job_id)
    (media_dir / "images").mkdir(parents=True)
    (media_dir / "segments").mkdir(parents=True)
    img1 = media_dir / "images" / "1.png"
    img2 = media_dir / "images" / "2.png"
    clip1 = media_dir / "segments" / "1.mp4"
    clip2 = media_dir / "segments" / "2.mp4"
    for p in (img1, img2, clip1, clip2):
        p.write_bytes(b"x")

    job_reset._db_clear_stage_self(
        job_id, "segment", job, segment_indices=[1], segment_scope=None
    )
    job_reset._fs_clear_stage_self(
        "segment", media_dir, job, segment_indices=[1], segment_scope=None
    )

    updated = {row["segment_index"]: row for row in repo_segment.list_segments(job_id)}
    assert updated[1]["image_path"] is None
    assert updated[1]["clip_path"] is None
    assert updated[2]["image_path"] == "/data/2.png"
    assert updated[2]["clip_path"] == "/data/2.mp4"
    assert not img1.exists()
    assert not clip1.exists()
    assert img2.exists()
    assert clip2.exists()


def test_segment_clips_with_indices_keeps_image_path(app_ctx) -> None:
    """segment/clips 只清 clip，保留 image_path。"""
    job = repo_job.create_job(
        "segment clips keep image", stage="segment", status="done"
    )
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
        ],
    )
    rows = repo_segment.list_segments(job_id)
    repo_segment.update_segment(
        rows[0]["id"],
        image_path="/data/1.png",
        clip_path="/data/1.mp4",
    )

    job_reset._db_clear_stage_self(
        job_id, "segment", job, segment_indices=[1], segment_scope="clips"
    )

    updated = repo_segment.list_segments(job_id)[0]
    assert updated["image_path"] == "/data/1.png"
    assert updated["clip_path"] is None


def test_prepare_intro_video_keeps_cover_and_end(
    app_ctx, tmp_path: Path, monkeypatch
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "video_data_dir", tmp_path)
    job = repo_job.create_job("intro video only", stage="intro", status="done")
    job_id = int(job["id"])
    media_dir = tmp_path / str(job_id)
    media_dir.mkdir()
    intro = media_dir / "intro.mp4"
    intro_png = media_dir / "intro.png"
    cover = media_dir / "cover.jpg"
    end = media_dir / "end.mp4"
    for path in (intro, intro_png, cover, end):
        path.write_bytes(b"x")
    repo_job.update_job(
        job_id,
        intro_path=str(intro),
        cover_path=str(cover),
        end_path=str(end),
    )

    job_reset.prepare_rerun(job_id, "intro_video")

    updated = repo_job.get_job(job_id)
    assert updated["intro_path"] is None
    assert updated["cover_path"] == str(cover)
    assert updated["end_path"] == str(end)
    assert not intro.exists()
    assert not intro_png.exists()
    assert cover.exists()
    assert end.exists()

