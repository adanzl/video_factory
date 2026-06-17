"""快速测试万相图生视频（wanx2.1-i2v）。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
TEST_OUTPUT_DIR = ROOT_DIR / "data/media/test"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.media.clip.wan import WanClipProvider
from app.services.media.ffmpeg_utils import probe_duration

DEFAULT_IMAGE = Path(__file__).resolve().parents[2] / "data/media/2/images/1.png"
DEFAULT_PROMPT = (
    "轻微镜头推进，磁铁与不锈钢板接触点细节清晰，"
    "背景问号微微发光，画面自然流畅，科普讲解风格"
)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="测试万相图生视频")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="首帧图片路径")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="动效描述")
    parser.add_argument("--duration", type=int, default=5, choices=[3, 4, 5], help="API 出视频秒数")
    parser.add_argument(
        "--out",
        type=Path,
        default=TEST_OUTPUT_DIR / "wan_i2v_test.mp4",
        help="输出 MP4 路径",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Model: {settings.wan_i2v_model}")
    print(f"Resolution: {settings.wan_i2v_resolution}")
    print(f"API key set: {bool(settings.dashscope_api_key)}")
    print(f"Image: {args.image}")
    print(f"Prompt: {args.prompt[:80]}...")
    print(f"Duration: {args.duration}s\n")

    if not args.image.exists():
        raise SystemExit(f"图片不存在: {args.image}")

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


if __name__ == "__main__":
    main()
