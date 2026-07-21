from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.core.log_config import attach_job_log, setup_logging

WORKER_LOG = setup_logging(
    log_dir=get_settings().log_dir,
    retention_days=get_settings().log_retention_days,
)

from app.core import pipeline
from app.services.job import job_mgr
from app.repositories import repo_job
from app.repositories.connection import connection
from worker.loop import drain_pending, run_job

_STAGE_CHOICES = [s for s in pipeline.STAGES if s != "done"]


def _parse_segment_indices(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    indices = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not indices:
        raise ValueError("--segments 不能为空")
    return indices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worker", description="video_factory worker")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a single job synchronously")
    run_p.add_argument("--title", help="create and run job from title")
    run_p.add_argument("--job-id", type=int, help="run existing job")
    run_p.add_argument(
        "--from-stage",
        choices=_STAGE_CHOICES,
        help="从该 stage 起连续跑到结束",
    )
    run_p.add_argument(
        "--only-stage",
        choices=_STAGE_CHOICES,
        help="只重跑该 stage 一步（清空该 stage 及下游产物）",
    )
    run_p.add_argument(
        "--segments",
        help="与 segment 联用：逗号分隔 segment_index，如 1,3",
    )
    run_p.add_argument(
        "--skip-publish",
        action="store_true",
        default=None,
        help="stop before publish (default from env)",
    )
    run_p.add_argument("--publish", action="store_true", help="enable publish stage")

    sub.add_parser("drain", help="consume all pending jobs")
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    skip_publish = settings.skip_publish_default
    if args.publish:
        skip_publish = False
    if args.skip_publish:
        skip_publish = True

    if args.from_stage and args.only_stage:
        print("--from-stage 与 --only-stage 不能同时使用", file=sys.stderr)
        return 2

    try:
        segment_indices = _parse_segment_indices(args.segments)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    rerun_stage = args.from_stage or args.only_stage
    rerun_mode = "only" if args.only_stage else "from"

    if args.title:
        job = job_mgr.create_from_title(args.title, skip_publish=skip_publish)
        job_id = job["id"]
        if rerun_stage:
            job_mgr.prepare_rerun(
                job_id,
                rerun_stage,
                segment_indices=segment_indices,
                mode=rerun_mode,
            )
    elif args.job_id:
        job_id = args.job_id
        if rerun_stage:
            job_mgr.prepare_rerun(
                job_id,
                rerun_stage,
                segment_indices=segment_indices,
                mode=rerun_mode,
            )
        elif args.publish or args.skip_publish is not None:
            with connection() as conn:
                repo_job.update_job(conn, job_id, skip_publish=skip_publish)
    else:
        print("either --title or --job-id is required", file=sys.stderr)
        return 2

    mode = "mock" if settings.mock_mode else "live"
    job_log = attach_job_log(settings.video_data_dir, job_id)
    print(f"Running job {job_id} (mode={mode}, skip_publish={skip_publish})")
    print(f"Log: {WORKER_LOG}")
    print(f"Job log: {job_log}")
    if rerun_stage:
        print(f"Rerun [{rerun_mode}]: {rerun_stage}")
    if segment_indices:
        print(f"Partial segments: {segment_indices}")

    job = run_job(
        job_id,
        from_stage=args.from_stage,
        only_stage=args.only_stage,
        segment_indices=segment_indices,
    )
    print(f"Done: stage={job['stage']} status={job['status']}")
    if job.get("final_path"):
        from app.utils.final_asset import resolve_final_path_file

        print(f"Final: {resolve_final_path_file(job['final_path'])}")
    if job["status"] == "done":
        return 0
    if job["status"] == "pending":
        return 0
    return 1


def cmd_drain(_: argparse.Namespace) -> int:
    count = drain_pending()
    print(f"Processed {count} job(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "drain":
        return cmd_drain(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
