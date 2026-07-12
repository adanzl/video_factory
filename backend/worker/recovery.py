"""自动恢复：服务重启后恢复卡住的视频生成任务。

当服务（video-factory）意外重启时，正在执行的任务在数据库中仍标记为
status='running'，但后台工作线程已丢失，这些任务会永久卡住。

恢复策略：
1. 启动时扫描所有 status='running' 的任务
2. 仅恢复属于视频生成阶段（segment）的任务
3. 将其重置为 status='pending'
4. 在后台线程中重新从当前 stage 执行
"""

from __future__ import annotations

import logging

from app.repositories import repo_job, repo_job_log
from app.repositories.connection import connection
from app.utils.async_util import run_in_background

logger = logging.getLogger(__name__)

# 视频生成相关 stage（先仅开放 segment，后续可按需扩展）
# segment 阶段包含：图生成（images）和图生视频（clips）
VIDEO_GENERATION_STAGES: frozenset[str] = frozenset({"segment"})


def recover_stuck_jobs() -> int:
    """恢复卡在 running 状态的视频生成任务并重新执行。

    Returns:
        已恢复的任务数量
    """
    recovered_jobs: list[int] = []

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
            if stage not in VIDEO_GENERATION_STAGES:
                logger.info(
                    "job %s stage=%s skipped (not in video generation stages)",
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
            recovered_jobs.append(job_id)

    # 在后台重新执行恢复的任务
    if recovered_jobs:
        logger.warning(
            "recovered %d stuck video-generation job(s), re-running in background",
            len(recovered_jobs),
        )
        for job_id in recovered_jobs:
            # 延迟导入避免循环依赖
            from worker.loop import run_job

            run_in_background(lambda jid=job_id: run_job(jid))
    else:
        logger.info("no stuck jobs to recover")

    return len(recovered_jobs)
