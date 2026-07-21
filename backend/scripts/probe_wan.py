"""探测万相：出图（image）或图生视频（i2v）。

用法（backend 目录）:
  python -m scripts.probe_wan image
  python -m scripts.probe_wan i2v
  python -m scripts.probe_wan i2v --image /path/to.png --duration 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
TEST_OUTPUT_DIR = ROOT_DIR / "data/media/test"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.media.ffmpeg_utils import probe_duration
from app.services.segment.clip.video_wan import WanClipProvider
from app.services.segment.image.image_wan import WanImageProvider

TEST_PROMPTS = [
    "电影级写实科普画面，显微视角下的人体细胞分裂过程，"
    "中心是一个正在分裂的细胞，染色体清晰可见，周围有流动的细胞质，"
    "柔和的生物荧光蓝紫色调，景深效果突出主体，细节真实可辨。",
    "电影级写实科普画面，俯视地球板块俯冲带，"
    "两块大陆板块碰撞挤压，一侧板块俯冲入地幔，熔岩从缝隙中涌出，"
    "远处有海洋和云层，暖色调熔岩与冷色海洋形成对比，大气透视感强。",
    "电影级写实科普画面，左右并排展示两块条形磁铁，"
    "左侧同极相对（N-N），用红色叉号和排斥箭头表示相斥，"
    "右侧异极相对（N-S），用绿色对勾和吸引箭头表示相吸，"
    "磁铁表面金属质感真实，背景干净柔和的浅灰色，光线均匀明亮。",
]

DEFAULT_I2V_IMAGE = ROOT_DIR / "data/media/2/images/1.png"
DEFAULT_I2V_PROMPT = (
    "轻微镜头推进，磁铁与不锈钢板接触点细节清晰，"
    "背景问号微微发光，画面自然流畅，科普讲解风格"
)


def cmd_image(_: argparse.Namespace) -> int:
    settings = get_settings()
    print(f"Model: {settings.wan_model}")
    print(f"Size: {settings.wan_image_size}")
    print(f"Prompt extend: {settings.wan_prompt_extend}")
    print(f"API key set: {bool(settings.dashscope_api_key)}\n")

    provider = WanImageProvider()
    out_dir = TEST_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        out_path = out_dir / f"test_{i}.png"
        print(f"[{i}/3] Generating: {prompt[:60]}...")
        try:
            result = provider.generate(prompt, out_path)
            print(f"  -> Saved: {result}")
        except Exception as exc:
            print(f"  -> Failed: {exc}")
    return 0


def cmd_i2v(args: argparse.Namespace) -> int:
    settings = get_settings()
    print(f"Model: {settings.wan_i2v_model}")
    print(f"Resolution: {settings.wan_i2v_resolution}")
    print(f"API key set: {bool(settings.dashscope_api_key)}")
    print(f"Image: {args.image}")
    print(f"Prompt: {args.prompt[:80]}...")
    print(f"Duration: {args.duration}s\n")

    if not args.image.exists():
        print(f"图片不存在: {args.image}", file=sys.stderr)
        return 1

    provider = WanClipProvider()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print("提交万相图生视频任务，预计 1-5 分钟...")
    provider._generate_raw(
        args.image,
        args.prompt,
        args.out,
        duration=args.duration,
    )
    dur = probe_duration(args.out)
    print(f"\n完成 -> {args.out.resolve()}")
    print(f"时长: {dur:.2f}s, 大小: {args.out.stat().st_size / 1024:.1f} KB")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探测万相出图 / 图生视频")
    sub = parser.add_subparsers(dest="command", required=True)

    p_image = sub.add_parser("image", help="探测 wan 文生图")
    p_image.set_defaults(func=cmd_image)

    p_i2v = sub.add_parser("i2v", help="探测 wan 图生视频")
    p_i2v.add_argument("--image", type=Path, default=DEFAULT_I2V_IMAGE)
    p_i2v.add_argument("--prompt", default=DEFAULT_I2V_PROMPT)
    p_i2v.add_argument("--duration", type=int, default=5, choices=[3, 4, 5])
    p_i2v.add_argument(
        "--out",
        type=Path,
        default=TEST_OUTPUT_DIR / "wan_i2v_test.mp4",
    )
    p_i2v.set_defaults(func=cmd_i2v)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
