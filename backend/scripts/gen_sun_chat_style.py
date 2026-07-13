"""用 chat 流水线涂鸦画风生成一张太阳。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.segment.image.image_agnes import AgnesImageProvider

# chat 流水线画风前缀
CHAT_STYLE = (
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
    "主观夸张变形，高饱和色彩，涂色出界，横格笔记本纸背景，"
    "橡皮擦拭痕迹，手工感，孩子气的构图。"
)

PROMPT = (
    CHAT_STYLE
    + "画面中央是一个巨大的太阳，圆圆的脸庞，金黄色的光芒向四周发散，"
    "太阳脸上带着开心的笑容，眼睛弯弯的，"
    "背景是浅蓝色的天空，几朵松软的白云飘在旁边，"
    "画面底部有绿色的草地和几朵彩色小花，"
    "整体温暖明亮，充满童趣。"
)


def main() -> None:
    settings = get_settings()
    provider = AgnesImageProvider()

    out_dir = BACKEND_DIR.parent / "data" / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sun_chat_style.png"

    size = "1280*720"  # 横版

    print(f"model: {settings.agnes_image_model}")
    print(f"size: {size}")
    print(f"prompt ({len(PROMPT)} chars):")
    print(f"  {PROMPT}")
    print(f"output: {out_path}")
    print("--- generating ---")

    result = provider.generate(PROMPT, out_path, size=size)
    print(f"done: {result} ({result.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
