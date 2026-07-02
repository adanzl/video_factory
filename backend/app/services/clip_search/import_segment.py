"""将素材库视频导入任务分镜。"""

from __future__ import annotations

from app.config import get_settings
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.clip_search.download import download_stock_clip_to_segment
from app.services.job.job_mgr import JobBusyError, job_mgr


def import_clip_to_segment(job_id: int, segment_index: int, video_url: str) -> dict:
    with job_mgr._job_lock(job_id):
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            if job["status"] == "running":
                raise JobBusyError("任务运行中，请稍后再试")

            segments = repo_segment.list_segments(conn, job_id)
            segment = next(
                (row for row in segments if int(row["segment_index"]) == segment_index),
                None,
            )
            if segment is None:
                raise KeyError(f"segment {segment_index} not found")

            settings = get_settings()
            media_dir = settings.video_data_dir / str(job_id)
            clip_path = download_stock_clip_to_segment(
                job=job,
                media_dir=media_dir,
                segment=segment,
                video_url=video_url,
            )
            repo_segment.update_segment(
                conn,
                int(segment["id"]),
                clip_path=str(clip_path),
                status="done",
            )
            repo_job_log.append_log(
                conn,
                job_id,
                "segment",
                f"imported stock clip for segment #{segment_index}",
            )
            return next(
                row
                for row in repo_segment.list_segments(conn, job_id)
                if int(row["segment_index"]) == segment_index
            )
