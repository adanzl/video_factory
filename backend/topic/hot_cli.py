"""热搜采集 → 规则筛选 →（可选）生成选题 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.core.log_config import setup_logging

setup_logging(
    log_dir=get_settings().log_dir,
    retention_days=get_settings().log_retention_days,
)

import logging

from app.services.topic.hot_pipeline import HotPipelineOptions, run_hot_pipeline
from app.services.topic.topic_mgr import topic_mgr

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="topic-hot",
        description="B 站热搜采集 → 规则筛选 →（可选）转 theme 并生成选题",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="热搜广场拉取条数（1-50，默认 50）",
    )
    parser.add_argument(
        "--l1-rules",
        action="store_true",
        help="L1 仅用规则（硬性丢弃 + direct），不做 LLM 相关性扩展判定",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整流程：筛选 → 转 theme → 生成标题 → 打分",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="完整流程后将 queued 标题写入选题库（source=热搜）",
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help="L1 筛选后转 theme（不生成标题）",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="theme 转化使用启发式，不调用 DeepSeek",
    )
    parser.add_argument(
        "--count-per-theme",
        type=int,
        default=3,
        help="每个 theme 生成标题数（默认 3，最大 20）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON",
    )
    return parser


def _print_human_report(payload: dict, *, show_convert_hint: bool = False) -> None:
    summary = payload["summary"]
    print(
        f"采集 {summary['fetched']} 条 → "
        f"保留 {summary['kept']} 条 → "
        f"丢弃 {summary['rejected']} 条"
        + (f"（L1={'规则' if summary.get('l1_rules') else 'LLM'}）" if "l1_rules" in summary else "")
    )

    if payload.get("themes"):
        print(f"\n=== 转化 theme（{len(payload['themes'])}）===")
        for item in payload["themes"]:
            print(f"· [{item['track']}] {item['theme']}")
            print(f"  来源热搜：{item['keyword']}（{item['reason']}）")
    elif show_convert_hint and payload.get("kept"):
        if "themes" in payload:
            print(f"\n=== L1 保留 {len(payload['kept'])} 条，但未能转化为 theme ===")
        else:
            print(f"\n=== L1 保留（{len(payload['kept'])}）===")
        for item in payload["kept"]:
            mode = item.get("mode") or "-"
            print(f"· [{mode}] {item['show_name']}（{item['reason']}）")

    if payload.get("topics"):
        print(f"\n=== 生成并打分（{len(payload['topics'])}）===")
        for item in payload["topics"]:
            mark = "✓" if item["status"] == "queued" else "✗"
            print(
                f"{mark} [{item['total']}分/{item['status']}] {item['title']}"
            )
            if item.get("rejected_reason"):
                print(f"   原因：{item['rejected_reason']}")
            print(f"   theme：{item['theme']}")

    if payload.get("added") is not None:
        print(f"\n=== 入库（source=热搜）{payload.get('count', 0)} 条，跳过 {payload.get('skipped', 0)} 条 ===")


def _pipeline_options(args: argparse.Namespace) -> HotPipelineOptions:
    convert_themes = args.convert or args.full or args.save
    generate_titles = args.full or args.save
    return HotPipelineOptions(
        limit=max(1, min(args.limit, 50)),
        l1_rules=args.l1_rules,
        count_per_theme=max(1, min(args.count_per_theme, 20)),
        use_theme_llm=not args.no_llm,
        convert_themes=convert_themes,
        generate_titles=generate_titles,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger.info(
        "[HOT] cli start limit=%d full=%s save=%s convert=%s l1_rules=%s no_llm=%s",
        args.limit,
        args.full,
        args.save,
        args.convert,
        args.l1_rules,
        args.no_llm,
    )
    try:
        if args.save:
            opts = _pipeline_options(args)
            payload = topic_mgr.import_from_hot_search(
                limit=opts.limit,
                l1_rules=opts.l1_rules,
                count_per_theme=opts.count_per_theme,
                use_theme_llm=opts.use_theme_llm,
                min_score=70,
            )
        else:
            payload = run_hot_pipeline(_pipeline_options(args))
    except Exception as exc:
        logger.exception("[HOT] cli failed")
        print(f"热搜流水线失败: {exc}", file=sys.stderr)
        return 1

    show_convert = args.convert or args.full or args.save
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human_report(payload, show_convert_hint=show_convert)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
