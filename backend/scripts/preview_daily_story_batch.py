"""本地批量预览日常故事生成（含发现开场拼接），便于调提示词。

用法:

  conda run -n flask_env python \\
    backend/scripts/preview_daily_story_batch.py

  conda run -n flask_env python \\
    backend/scripts/preview_daily_story_batch.py \\
    --story-type A \\
    --themes 姐姐教弟弟写作业自己写错 灿灿不许昭昭磨蹭玩手机 \\
    --out tmp/daily_a_smoke.json

默认主题见 DEFAULT_THEMES；结果默认写到
tmp/daily_story_batch_<时间戳>.json（项目根 tmp/，已在
.gitignore）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.services.daily_story.prompts import (  # noqa: E402
    dialogue_total_chars,
    validate_daily_story_json,
)
from app.services.daily_story.story_type_lines import story_type_tag  # noqa: E402
from app.services.llm.llm_mgr import llm_mgr  # noqa: E402

DEFAULT_THEMES = [
    "沙发上的抱枕大战",
    "争最后一瓶酸奶",
    "谁先洗澡",
    "抢用新橡皮",
    "把饼干碎撒一地",
]

DEFAULT_OUT_DIR = ROOT / "tmp"


def _speakers(story: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in story.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip() or "?"
        counts[sp] = counts.get(sp, 0) + 1
    return counts


def _lines(story: dict, *, speaker: str | None = None) -> list[str]:
    out: list[str] = []
    for item in story.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("line") or "").strip()
        if not text:
            continue
        if speaker is not None and sp != speaker:
            continue
        out.append(f"{sp}：{text}")
    return out


def _summarize(theme: str, story: dict, elapsed: float) -> dict:
    dialogue = story.get("dialogue") or []
    opening = story.get("discovery_opening") or []
    quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
    return {
        "theme": theme,
        "ok": True,
        "elapsed_sec": round(elapsed, 1),
        "chars": dialogue_total_chars(story),
        "lines": len(dialogue),
        "opening_lines": len(opening) if isinstance(opening, list) else 0,
        "speakers": _speakers(story),
        "scene_title": story.get("scene_title"),
        "setting": story.get("setting"),
        "conflict_core": story.get("conflict_core"),
        "punchline_explain": story.get("punchline_explain"),
        "quality_grade": quality.get("grade"),
        "quality_score": quality.get("score"),
        "quality_summary": quality.get("summary"),
        "opening": opening,
        "head": _lines(story)[:4],
        "tail": _lines(story)[-4:],
        "mom_lines": _lines(story, speaker="妈妈"),
        "story": story,
    }


def run_batch(
    themes: list[str],
    *,
    story_type: str | None = None,
) -> list[dict]:
    locked = story_type_tag(story_type) if story_type else None
    if locked:
        print(f"[batch] locked story_type={locked}", flush=True)
    results: list[dict] = []
    for i, theme in enumerate(themes, 1):
        print(f"\n===== [{i}/{len(themes)}] {theme} =====", flush=True)
        started = time.perf_counter()
        try:
            story = llm_mgr.generate_daily_story(
                theme,
                story_type=locked,
            )
            validate_daily_story_json(story, phase="full")
            item = _summarize(theme, story, time.perf_counter() - started)
            print(
                f"ok chars={item['chars']} lines={item['lines']} "
                f"opening={item['opening_lines']} speakers={item['speakers']} "
                f"elapsed={item['elapsed_sec']}s "
                f"grade={item.get('quality_grade')}({item.get('quality_score')})",
                flush=True,
            )
            print(f"core={item['conflict_core']}", flush=True)
            print(f"setting={item['setting']}", flush=True)
            if item.get("quality_summary"):
                print(f"quality={item['quality_summary']}", flush=True)
            if item["opening"]:
                print("opening:", flush=True)
                for row in item["opening"]:
                    print(
                        f"  {row.get('speaker')}：{row.get('line')}",
                        flush=True,
                    )
            print("head:", flush=True)
            for line in item["head"]:
                print(f"  {line}", flush=True)
            print("tail:", flush=True)
            for line in item["tail"]:
                print(f"  {line}", flush=True)
            if item["mom_lines"]:
                print("mom:", flush=True)
                for line in item["mom_lines"]:
                    print(f"  {line}", flush=True)
            print(f"punchline={item['punchline_explain']}", flush=True)
        except Exception as exc:
            item = {
                "theme": theme,
                "ok": False,
                "elapsed_sec": round(time.perf_counter() - started, 1),
                "error": str(exc),
            }
            print(f"FAIL elapsed={item['elapsed_sec']}s: {exc}", flush=True)
        results.append(item)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="批量预览日常故事生成")
    parser.add_argument(
        "--themes",
        nargs="+",
        default=DEFAULT_THEMES,
        help="主题列表（默认内置 5 个）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="结果 JSON 路径（默认 tmp/daily_story_batch_*.json）",
    )
    parser.add_argument(
        "--story-type",
        choices=["A", "B", "C", "D", "E"],
        default=None,
        help="锁定矛盾类型（A–E），不指定则按主题关键词自动选",
    )
    args = parser.parse_args()

    results = run_batch(list(args.themes), story_type=args.story_type)
    out = args.out
    if out is None:
        DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = DEFAULT_OUT_DIR / f"daily_story_batch_{stamp}.json"
    else:
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)

    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"\n[local] wrote {out}", flush=True)
    print(f"[local] done {ok_n}/{len(results)} ok", flush=True)


if __name__ == "__main__":
    main()
