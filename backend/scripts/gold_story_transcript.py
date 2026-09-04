"""金故事 H0b 逐字稿 CLI。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_transcript doctor
  conda run -n flask_env python -m scripts.gold_story_transcript batch \\
    --file ../data/gold_story/_candidates_bv.txt
  conda run -n flask_env python -m scripts.gold_story_transcript one BV1xxxxx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import create_app
from app.services.gold_story import transcript as gs_transcript


def _cmd_doctor(_: argparse.Namespace) -> int:
    report = gs_transcript.doctor()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = bool(report.get("ffmpeg") and report.get("yt_dlp") and report.get("faster_whisper"))
    ok = ok and bool(report.get("whisper_model_exists"))
    if report.get("gold_story_ocr_enabled"):
        ok = ok and bool(report.get("rapidocr") and report.get("ocr_models_ready"))
    return 0 if ok else 1


def _cmd_batch(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    sources = gs_transcript.read_source_list(path)
    results = gs_transcript.batch_bilibili(
        sources,
        skip_existing=not args.force,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = sum(1 for row in results if row.get("action") == "error")
    return 1 if failed else 0


def _cmd_one(args: argparse.Namespace) -> int:
    result = gs_transcript.transcribe_bilibili(
        args.source,
        skip_existing=not args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("action") in {"ok", "skip"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事 H0b 逐字稿（yt-dlp + faster-whisper）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="检查 ffmpeg / yt-dlp / 模型目录")
    p_doctor.set_defaults(func=_cmd_doctor)

    p_batch = sub.add_parser("batch", help="批量转写 BV 列表文件")
    p_batch.add_argument(
        "--file",
        "-f",
        required=True,
        help="BV 列表（每行一个 BV 或 URL，# 开头为注释）",
    )
    p_batch.add_argument(
        "--force",
        action="store_true",
        help="已有逐字稿也重跑",
    )
    p_batch.set_defaults(func=_cmd_batch)

    p_one = sub.add_parser("one", help="转写单个 BV")
    p_one.add_argument("source", help="BV 号或 B 站 URL")
    p_one.add_argument(
        "--force",
        action="store_true",
        help="已有逐字稿也重跑",
    )
    p_one.set_defaults(func=_cmd_one)

    args = parser.parse_args(argv)
    create_app()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
