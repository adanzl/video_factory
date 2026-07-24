"""自动恢复：服务重启后恢复卡住的任务。"""

from __future__ import annotations

import logging

from app.repositories import repo_job, repo_job_log
from app.repositories import sql_exec as sql
from app.repositories.sql_exec import atomic

logger = logging.getLogger(__name__)

_TERMINAL_STAGES: frozenset[str] = frozenset({"done"})


def recover_stuck_jobs() -> int:
    recovered: list[tuple[int, str]] = []

    with atomic():
        rows = sql.fetchall(
            """
            SELECT id, stage, pipeline, title
            FROM video_job
            WHERE status = 'running'
            ORDER BY id
            """,
        )

        for row in rows:
            stage: str = row["stage"] or ""
            if stage in _TERMINAL_STAGES:
                logger.info(
                    "job %s stage=%s skipped (terminal)",
                    row["id"],
                    stage,
                )
                continue

            job_id = int(row["id"])
            title_preview = (row["title"] or "")[:40]
            logger.warning(
                "recovering stuck job %s (stage=%s, pipeline=%s, title=%s...)",
                job_id,
                stage,
                row["pipeline"],
                title_preview,
            )

            repo_job.update_job(job_id, status="pending", error_message=None)
            repo_job_log.append_log(
                job_id,
                stage,
                "auto-recovered after service restart, reset to pending",
                level="warning",
            )
            recovered.append((job_id, stage))

    if recovered:
        logger.warning(
            "recovered %d stuck job(s), re-running via job_mgr",
            len(recovered),
        )
        from app.services.job.job_mgr import JobBusyError, job_mgr

        for job_id, _stage in recovered:
            try:
                job_mgr.continue_job(job_id, sync=False, allow_running=False)
            except JobBusyError:
                logger.warning(
                    "recovery skipped job %s: already locked",
                    job_id,
                )
    else:
        logger.info("no stuck jobs to recover")

    return len(recovered)


def recover_stuck_daily_stories() -> int:
    from app.services.daily_story.daily_story_mgr import daily_story_mgr

    return daily_story_mgr.recover_processing_stories()
