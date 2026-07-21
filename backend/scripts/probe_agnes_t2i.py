"""探测 Agnes 文生图（/v1/images/generations）。

用法（在 backend 目录）:

  python -m scripts.probe_agnes_t2i
  python -m scripts.probe_agnes_t2i --prompt "客厅里两个小孩在抢橡皮"
  python -m scripts.probe_agnes_t2i --ref /path/to/hosts.png --size 1280*720
  python -m scripts.probe_agnes_t2i --verify
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
TEST_OUTPUT_DIR = ROOT_DIR / "data/media/test"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.llm.llm_agnes import agnes_api_keys
from app.services.segment.image.image_agnes import AgnesImageProvider
from app.utils.job_info import CONTENT_STYLE_DAILY_STORY

DEFAULT_PROMPT = (
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触。客厅地板上，"
    "7岁男孩昭昭（黑色超短发、蓝色短袖）伸手指向10岁女孩灿灿"
    "（马尾辫、粉色卫衣）；灿灿右手握白色橡皮，两人互瞪。"
    "中景，窗光从左侧斜照。"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Agnes text-to-image")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="文生图提示词")
    parser.add_argument(
        "--size",
        default=None,
        help="尺寸，如 1280*720（默认读 AGNES_IMAGE_SIZE）",
    )
    parser.add_argument(
        "--ref",
        action="append",
        type=Path,
        default=[],
        help="参考图路径，可多次传入",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出路径（默认 data/media/test/agnes_t2i.png）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="生图后跑 VL 校验（默认只打一次文生图请求）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打印 DEBUG 日志",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = get_settings()
    keys = agnes_api_keys()
    out = args.out or (TEST_OUTPUT_DIR / "agnes_t2i.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    size = args.size or settings.agnes_image_size
    refs = [p for p in args.ref if p]
    missing = [str(p) for p in refs if not p.exists()]
    if missing:
        print(f"参考图不存在: {missing}", file=sys.stderr)
        return 1

    print(f"base_url: {settings.agnes_api_base_url}")
    print(f"model:    {settings.agnes_image_model}")
    print(f"size:     {size}")
    print(f"timeout:  {settings.agnes_image_timeout_sec}s")
    print(f"retries:  {settings.agnes_http_max_retries}")
    print(f"keys:     {[k.label for k in keys] or '(none)'}")
    print(f"refs:     {[str(p) for p in refs] or '(none)'}")
    print(f"verify:   {args.verify}")
    print(f"out:      {out}")
    print(f"prompt:   {args.prompt[:120]}{'…' if len(args.prompt) > 120 else ''}")
    print()

    if not keys:
        print("未配置 AGNES_API_KEY / AGNES_FREE_API_KEY", file=sys.stderr)
        return 1

    provider = AgnesImageProvider()
    t0 = time.time()
    try:
        if args.verify:
            result = provider.generate(
                args.prompt,
                out,
                size=size,
                ref_images=refs or None,
                expected_speakers=["昭昭", "灿灿"],
                content_style=CONTENT_STYLE_DAILY_STORY,
            )
        else:
            # 默认只测文生图 HTTP，跳过 VL 校验与 regenerate
            result = provider._generate_with_key(
                keys[0],
                args.prompt,
                out,
                size=size,
                ref_images=refs or None,
            )
    except Exception as exc:
        print(f"FAILED after {time.time() - t0:.1f}s: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    n_bytes = result.stat().st_size if result.exists() else 0
    print(f"OK in {elapsed:.1f}s -> {result} ({n_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
