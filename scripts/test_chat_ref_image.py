"""测试 chat 流水线参考图出图：取 job 33 剧本的第一镜生成一张图。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.segment.image.image_agnes import AgnesImageProvider

# --- job 33 的 script_json（第一镜）---
SCRIPT_JSON = {
    "title":
    "偷零食",
    "segments": [{
        "segment_index":
        1,
        "text":
        "姐姐，你看！柜子没锁！妈妈藏的饼干在里面！嘘！小声点！妈妈说过不能偷吃。为什么不能？妈妈偷藏才不对吧？",
        "image_prompt": ("儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，主观夸张变形，高饱和色彩，涂色出界，横格笔记本纸背景，橡皮擦拭痕迹，手工感，孩子气的构图。"
                         "客厅场景，左侧木柜半开，"
                         "昭昭（7岁男孩，黑色短发，圆脸，穿蓝色短袖T恤，比姐姐矮）站在柜前手指着柜子，"
                         "灿灿（9岁女孩，扎马尾辫，穿粉色卫衣）站在他身后，"
                         "背景有沙发和窗户，全景"),
    }],
}


def main() -> None:
    settings = get_settings()
    provider = AgnesImageProvider()

    # chat 流水线角色参考图
    ref_images = [
        settings.res_dir / "host" / "crayon" / "zhao.png",
        settings.res_dir / "host" / "crayon" / "can.png",
    ]

    # 检查参考图是否存在
    for p in ref_images:
        if not p.exists():
            print(f"WARNING: 参考图不存在: {p}")

    seg = SCRIPT_JSON["segments"][0]
    prompt = seg["image_prompt"]

    # 输出到 data/debug 目录
    out_dir = BACKEND_DIR.parent / "data" / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_chat_ref_seg1.png"

    # job 33 是 landscape，Agnes API 仅支持预设尺寸，用 1280*720
    size = "1280*720"  # landscape 预设尺寸（Agnes 不支持 960*1706 等自定义尺寸）

    print(f"prompt ({len(prompt)} chars): {prompt[:120]}...")
    print(f"ref_images: {[p.name for p in ref_images]}")
    print(f"size: {size} (job orientation=landscape)")
    print(f"model: {settings.agnes_image_model}")
    print(f"output: {out_path}")
    print("--- generating ---")

    result = provider.generate(
        prompt,
        out_path,
        size=size,
        ref_images=ref_images,
    )
    print(f"done: {result} ({result.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
