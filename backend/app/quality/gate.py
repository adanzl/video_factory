"""质检结果写入 job，并在 major 时阻断流水线。"""

from __future__ import annotations

from app.exceptions import JobStageFailureError
from app.quality.models import QualityReport, QualityStep
from app.repositories import job_log_repo, job_repo


def _normalize_existing(existing: dict | None) -> dict:
    if not existing:
        return {}
    if "level" in existing and "step" not in existing:
        return {"legacy": existing}
    return dict(existing)


def merge_quality_report(existing: dict | None, step: QualityStep, report: QualityReport) -> dict:
    merged = _normalize_existing(existing)
    merged[step] = report.to_dict()
    return merged


def apply_quality_checks(
    conn,
    job_id: int,
    log_stage: str,
    checks: dict[QualityStep, QualityReport],
    *,
    existing_report: dict | None = None,
) -> dict:
    merged = _normalize_existing(existing_report)
    for step, report in checks.items():
        merged = merge_quality_report(merged, step, report)
        job_log_repo.append_log(
            conn,
            job_id,
            log_stage,
            f"quality[{step}]={report.level}",
            level="warning" if report.level == "minor" else "info",
        )
        if report.level == "major" and report.fail_stage:
            job_repo.update_job(conn, job_id, quality_report=merged, fail_stage=report.fail_stage)
            raise JobStageFailureError(
                f"quality[{step}] major, rollback to {report.fail_stage}"
            )
    job_repo.update_job(conn, job_id, quality_report=merged)
    return merged
