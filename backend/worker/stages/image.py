from __future__ import annotations

from app.config import get_settings
from app.repositories import job_log_repo, segment_repo
from app.repositories.connection import connection
from app.services.visual.visual_mgr import generate_segment_images
from worker.context import JobContext
from worker.stages.base import StageExecutor


class ImageStage(StageExecutor):
    name = "image"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            segments = segment_repo.list_segments(conn, ctx.job["id"])

        results = generate_segment_images(segments, ctx.media_dir / "images")
        with connection() as conn:
            for seg_id, path in results:
                segment_repo.update_segment(
                    conn,
                    seg_id,
                    image_path=str(path),
                    status="done",
                )
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"generated {len(segments)} images "
                f"(provider={get_settings().image_provider}, mock={get_settings().mock_mode})",
            )
