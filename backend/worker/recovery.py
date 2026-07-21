"""自动恢复：服务重启后恢复卡住的任务。

当服务意外重启时，正在执行的任务在数据库中仍标记为
status='running'，但后台工作线程已丢失。

恢复策略：
1. 启动时扫描所有 status='running' 的任务
2. 重置为 status='pending'
3. 经 job_mgr.continue_job（持锁、后台）从当前 stage 续跑
"""

from __future__ import annotations

import logging

from app.repositories import repo_job, repo_job_log
from app.repositories.connection import connection

logger = logging.getLogger(__name__)

# 终态不恢复；其余 running 一律重置并续跑
_TERMINAL_STAGES: frozenset[str] = frozenset({"done"})


def recover_stuck_jobs() -> int:
    """恢复卡在 running 状态的任务并经 job_mgr 重新执行。

    Returns:
        已恢复的任务数量
    """
    recovered: list[tuple[int, str]] = []

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, stage, pipeline, title
            FROM video_job
            WHERE status = 'running'
            ORDER BY id
            """,
        ).fetchall()

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

            repo_job.update_job(conn, job_id, status="pending", error_message=None)
            repo_job_log.append_log(
                conn,
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
