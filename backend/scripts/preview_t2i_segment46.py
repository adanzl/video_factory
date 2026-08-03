"""预览 job 61 第 1 分镜文生图（默认带参考图）。

用法（在 backend 目录）:

  python -m scripts.preview_t2i_segment46                # 默认带 hosts.png 参考图
  python -m scripts.preview_t2i_segment46 --no-ref       # 纯 T2I 无参考图
  python -m scripts.preview_t2i_segment46 --ref ../data/tmp/hosts.png  # 指定参考图
  python -m scripts.preview_t2i_segment46 --no-verify    # 跳过质检

输出: tmp/t2i_seg1_<ts>.png

提示词与流水线共用 assemble_daily_t2i_prompt（规则拼装）。

job 61 seg1（妈妈心里换过鞋）: 验证发色硬锁前置（首句注入 + 角色块后）能否压住彩虹挑染。
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# ── path setup ──────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 项目根 tmp/ 目录
TMP_DIR = ROOT_DIR / "tmp"

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from app.config import get_settings
from app.services.llm.llm_agnes import agnes_api_keys
from app.services.script.image_prompt import assemble_daily_t2i_prompt
from app.services.segment.image.image_agnes import AgnesImageProvider
from app.services.segment.segment_mgr import _resolve_chat_ref_images
from app.utils.job_info import CONTENT_STYLE_DAILY_STORY

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  分镜数据（模拟 DB 中 job 61 seg1 的字段；改这里换分镜）
# ══════════════════════════════════════════════════════════════════════

SEG1 = {
    "segment_index": 1,
    "speakers": ["昭昭", "灿灿", "妈妈"],
    "shot_type": "特写",
    # visual_brief: job 61「妈妈心里换过鞋」seg1（对白：进门必须换拖鞋）
    "visual_brief": (
        "客厅门口，门垫歪斜，鞋柜敞开，柜面上整齐摆着一双室内拖鞋；"
        "画面从左到右是昭昭、妈妈、灿灿：昭昭站在左边，左手叉腰，右手指向妈妈脚下，"
        "瞪圆眼睛、嘴巴大张做出质问的夸张表情；"
        "妈妈站在中间，一只脚正迈入客厅地板，另一只脚还踩在门垫上，"
        "双手摊开耸着肩，眉毛高挑、撇嘴露出“这不重要”的神态；"
        "灿灿站在右边，两手背在身后，好奇地歪头看向妈妈脚下。"
        "地板上从门口延伸出几串带灰的大鞋印，鞋印清晰醒目，一直通到妈妈脚边。"
    ),
    "dialogue": [
        {"speaker": "昭昭", "text": "妈，不换拖鞋可以进客厅么？"},
        {"speaker": "妈妈", "text": "不行，进门必须换拖鞋，鞋子放鞋柜上。"},
    ],
}

# ── 默认 prompt: 与流水线同一套规则拼装 ──────────────────────────────
T2I_PROMPT = assemble_daily_t2i_prompt(SEG1)

# 同段 speakers 供质检用
EXPECTED_SPEAKERS = SEG1["speakers"]


def _size_from_env() -> str:
    # 测试用小尺寸 640*360（16:9 同比例），生成快很多；流水线仍走 1280*720
    return "640*360"


def _resolve_ref_images(
    ref_args: list[Path] | None,
    no_ref: bool,
) -> list[Path | str]:
    """解析参考图：--no-ref 为空，--ref 手动指定，默认走 chat 流水线 hosts.png。"""
    if no_ref:
        return []
    if ref_args:
        return list(ref_args)
    return _resolve_chat_ref_images()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="预览 job 46 第 1 分镜文生图（纯 T2I）"
    )
    parser.add_argument(
        "--prompt",
        default=T2I_PROMPT,
        help="文生图提示词（默认已内置 job 46 seg1 提示词）",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help="从文件读提示词（优先于 --prompt）",
    )
    parser.add_argument(
        "--size",
        default=None,
        help="尺寸，如 1280*720（默认走景观模式）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出路径（默认 tmp/t2i_seg1_<时间戳>.png）",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="跳过 VL 质检（只生图）",
    )
    parser.add_argument(
        "--ref",
        action="append",
        type=Path,
        default=None,
        help="参考图路径，可多次传入；默认用 chat 流水线 hosts.png",
    )
    parser.add_argument(
        "--no-ref",
        action="store_true",
        help="不传参考图（纯文生图）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打印 DEBUG 日志",
    )
    args = parser.parse_args()

    if args.prompt_file is not None:
        args.prompt = args.prompt_file.read_text(encoding="utf-8").strip()

    # ── 参考图 ────────────────────────────────────────────────────
    ref_images = _resolve_ref_images(args.ref, args.no_ref)
    missing = [
        str(p)
        for p in ref_images
        if isinstance(p, Path) and not p.exists()
    ]
    if missing:
        print(f"❌ 参考图不存在: {missing}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = get_settings()
    keys = agnes_api_keys()
    size = args.size or _size_from_env()
    ts = datetime.now().strftime("%m%d_%H%M%S")
    out = args.out or (TMP_DIR / f"t2i_seg1_{ts}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    # ── 打印参数 ────────────────────────────────────────────────
    print(f"provider:  agnes_t2i")
    print(f"base_url:  {settings.agnes_api_base_url}")
    print(f"model:     {settings.agnes_image_model}")
    print(f"size:      {size}")
    print(f"timeout:   {settings.agnes_image_timeout_sec}s")
    print(f"keys:      {[k.label for k in keys] or '(none)'}")
    print(f"refs:      {[str(p) for p in ref_images] or '(none / pure T2I)'}")
    print(f"verify:    {not args.no_verify}")
    print(f"out:       {out}")
    print(f"prompt ({len(args.prompt)} chars):")
    print(f"  {args.prompt}")
    print()

    if not keys:
        print("❌ 未配置 AGNES_API_KEY / AGNES_FREE_API_KEY", file=sys.stderr)
        return 1

    provider = AgnesImageProvider()
    t0 = time.time()
    try:
        if args.no_verify:
            result = provider._generate_with_key(
                keys[0],
                args.prompt,
                out,
                size=size,
                ref_images=ref_images or None,
            )
        else:
            result = provider.generate(
                args.prompt,
                out,
                size=size,
                ref_images=ref_images or None,
                expected_speakers=EXPECTED_SPEAKERS,
                content_style=CONTENT_STYLE_DAILY_STORY,
            )
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"❌ FAILED after {elapsed:.1f}s: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    n_bytes = result.stat().st_size if result.exists() else 0
    print(f"✅ OK in {elapsed:.1f}s -> {result} ({n_bytes} bytes)")
    print(f"\n图片路径: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
