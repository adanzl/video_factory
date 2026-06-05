from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.core.job_service import create_job_from_title, reset_job_from_stage
from app.repositories import job_repo
from app.repositories.connection import connection
from worker.loop import drain_pending, run_job
from worker.subtitle_test import rebuild_segment_subtitles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worker", description="video_factory worker")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a single job synchronously")
    run_p.add_argument("--title", help="create and run job from title")
    run_p.add_argument("--job-id", type=int, help="run existing job")
    run_p.add_argument("--from-stage", help="restart from stage")
    run_p.add_argument(
        "--skip-publish",
        action="store_true",
        default=None,
        help="stop before publish (default from env)",
    )
    run_p.add_argument("--publish", action="store_true", help="enable publish stage")

    sub.add_parser("drain", help="consume all pending jobs")

    sub_p = sub.add_parser("subtitle-test", help="rebuild one segment clip for subtitle preview")
    sub_p.add_argument("--job-id", type=int, required=True)
    sub_p.add_argument("--segment", type=int, required=True, help="segment_index, e.g. 1")
    sub_p.add_argument(
        "--sentence",
        type=int,
        help="only burn one sentence → segments/{N}_test.mp4 (faster)",
    )
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    skip_publish = settings.skip_publish_default
    if args.publish:
        skip_publish = False
    if args.skip_publish:
        skip_publish = True

    if args.title:
        job = create_job_from_title(args.title, skip_publish=skip_publish)
        job_id = job["id"]
        if args.from_stage:
            reset_job_from_stage(job_id, args.from_stage)
    elif args.job_id:
        job_id = args.job_id
        if args.from_stage:
            reset_job_from_stage(job_id, args.from_stage)
        elif args.publish or args.skip_publish is not None:
            with connection() as conn:
                job_repo.update_job(conn, job_id, skip_publish=skip_publish)
    else:
        print("either --title or --job-id is required", file=sys.stderr)
        return 2

    mode = "mock" if settings.mock_mode else "live"
    print(f"Running job {job_id} (mode={mode}, skip_publish={skip_publish})")
    job = run_job(job_id, from_stage=args.from_stage)
    print(f"Done: stage={job['stage']} status={job['status']}")
    if job.get("final_path"):
        print(f"Final: {job['final_path']}")
    return 0 if job["status"] == "done" else 1


def cmd_drain(_: argparse.Namespace) -> int:
    count = drain_pending()
    print(f"Processed {count} job(s)")
    return 0


def cmd_subtitle_test(args: argparse.Namespace) -> int:
    try:
        out = rebuild_segment_subtitles(
            args.job_id,
            args.segment,
            sentence=args.sentence,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Segment clip: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "drain":
        return cmd_drain(args)
    if args.command == "subtitle-test":
        return cmd_subtitle_test(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
