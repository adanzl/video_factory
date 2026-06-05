from __future__ import annotations

import shutil

from app.core import pipeline
from app.core.job_service import mark_done, mark_failed, mark_running
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.cover import CoverStage
from worker.stages.ffmpeg import FFmpegStage
from worker.stages.image import ImageStage
from worker.stages.intro import IntroStage
from worker.stages.publish import PublishStage
from worker.stages.quality import QualityStage
from worker.stages.script import ScriptStage
from worker.stages.title import TitleStage
from worker.stages.tts import TTSStage

EXECUTORS = {
    "title": TitleStage(),
    "script": ScriptStage(),
    "image": ImageStage(),
    "cover": CoverStage(),
    "intro": IntroStage(),
    "tts": TTSStage(),
    "quality": QualityStage(),
    "ffmpeg": FFmpegStage(),
    "publish": PublishStage(),
}


def _reload_job(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.get_job(conn, job_id)


def run_job(job_id: int, *, from_stage: str | None = None) -> dict:
    job = _reload_job(job_id)
    mark_running(job_id)
    stage = from_stage or job["stage"]
    if stage == "done":
        return job

    while stage != "done":
        job = _reload_job(job_id)
        ctx = JobContext.from_job(job)
        executor = EXECUTORS.get(stage)
        if executor is None:
            raise ValueError(f"no executor for stage {stage}")

        with connection() as conn:
            job_log_repo.append_log(conn, job_id, stage, "stage started")

        try:
            executor.run(ctx)
        except Exception as exc:
            mark_failed(job_id, stage, str(exc))
            raise

        next_stage = pipeline.next_stage(stage)
        job = _reload_job(job_id)
        if next_stage == "publish" and job.get("skip_publish"):
            mark_done(job_id)
            return _reload_job(job_id)
        with connection() as conn:
            job_repo.update_job(conn, job_id, stage=next_stage, status="running")
        stage = next_stage
        if stage == "done":
            mark_done(job_id)
            break

    return _reload_job(job_id)


def drain_pending() -> int:
    count = 0
    while True:
        with connection() as conn:
            job = job_repo.claim_next_pending(conn)
        if job is None:
            break
        run_job(job["id"])
        count += 1
    return count
