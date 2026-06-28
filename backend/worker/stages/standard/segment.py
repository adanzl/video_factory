from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.utils.job_info import resolve_image_provider, resolve_video_provider
from app.quality.checkers import check_segment_clips, check_visual
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.segment.segment_mgr import segment_mgr
from worker.context import JobContext
from worker.stages.base import StageExecutor


class SegmentStage(StageExecutor):
    name = "segment"

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])

        image_provider = resolve_image_provider(job)
        video_provider = resolve_video_provider(job)

        audio_path = Path(job["audio_path"]) if job.get("audio_path") else None
        produce_scope = ctx.segment_scope or "all"

        def persist_segment_image(seg_id: int, path: Path) -> None:
            with connection() as conn:
                segment_repo.update_segment(
                    conn,
                    seg_id,
                    image_path=str(path),
                    status="done",
                )

        def persist_segment_clip(seg_id: int, path: Path) -> None:
            with connection() as conn:
                segment_repo.update_segment(
                    conn,
                    seg_id,
                    clip_path=str(path),
                )

        on_image_done = persist_segment_image if produce_scope in {"all", "images"} else None
        on_clip_done = persist_segment_clip if produce_scope in {"all", "clips"} else None
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=ctx.media_dir,
            audio_path=audio_path,
            only_segment_indices=ctx.segment_indices_set(),
            scope=produce_scope,
            job=job,
            on_image_done=on_image_done,
            on_clip_done=on_clip_done,
        )

        image_by_id = dict(result.image_paths)
        clip_by_id = dict(result.clips.segment_clip_paths)
        segments_for_qc = []
        for seg in segments:
            image_path = image_by_id.get(seg["id"]) or seg.get("image_path")
            clip_path = clip_by_id.get(seg["id"]) or seg.get("clip_path")
            segments_for_qc.append(
                {
                    **seg,
                    "image_path": str(image_path) if image_path else None,
                    "clip_path": str(clip_path) if clip_path else None,
                }
            )

        with connection() as conn:
            log_scope = (
                f"segments={list(ctx.rerun_segment_indices)}"
                if ctx.rerun_segment_indices
                else "all"
            )
            clip_note = (
                f"clips={len(result.clips.segment_clip_paths)} "
                f"(provider={video_provider})"
                if result.clips.segment_clip_paths
                else "clips=0"
            )
            model = (
                settings.z_image_model
                if image_provider == "z_image_t2i"
                else settings.wan_model
                if image_provider == "wan_t2i"
                else settings.agnes_image_model
                if image_provider == "agnes_t2i"
                else f"sd15/{settings.sd_business or 'auto'}"
                if image_provider == "sd15_t2i"
                else image_provider
            )
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"scope={log_scope}, "
                    f"images={len(result.image_paths)} "
                    f"(provider={image_provider}, model={model}), "
                    f"{clip_note}"
                ),
            )
            qc_checks: dict = {}
            rerun_indices = ctx.segment_indices_set()
            if produce_scope in {"all", "images"}:
                visual_qc = segments_for_qc
                if rerun_indices is not None and produce_scope == "images":
                    visual_qc = [
                        seg for seg in segments_for_qc if seg["segment_index"] in rerun_indices
                    ]
                qc_checks["visual"] = check_visual(visual_qc)
            if produce_scope in {"all", "clips"} and (
                produce_scope == "clips" or audio_path is not None
            ):
                clip_qc = segments_for_qc
                if rerun_indices is not None:
                    clip_qc = [
                        seg for seg in segments_for_qc if seg["segment_index"] in rerun_indices
                    ]
                qc_checks["clip"] = check_segment_clips(clip_qc)
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                qc_checks,
                existing_report=job.get("quality_report"),
            )
