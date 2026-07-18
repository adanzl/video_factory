"""Agnes 图生图脚本：生成昭昭和灿灿的绘本风格形象。"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import requests

from app.config import get_settings

# 风格提示词
STYLE_PROMPT = "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，主观夸张变形，高饱和色彩，涂色出界，横格笔记本纸背景，橡皮擦拭痕迹，手工感，孩子气的构图。"

# 角色固定描述
CHARACTERS = {
    "昭昭": "7岁男孩，男孩气黑色超短发（发长在耳垂以上，清晰露出双耳及整个后颈，齐耳学生头），圆脸，穿蓝色短袖T恤，比姐姐矮一点",
    "灿灿": "9岁女孩，扎马尾辫，穿粉色卫衣",
}


def generate_image(
    prompt: str,
    output_path: Path,
    *,
    api_key: str,
    base_url: str,
    model: str = "agnes-image-2.1-flash",
    size: str = "720x1280",
) -> Path:
    """调用 Agnes images/generations 进行文生图。"""
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "extra_body": {"response_format": "url"},
    }

    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"  [生图] Model: {model}, Size: {size}")
    print(f"  [生图] Prompt: {prompt}")

    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    body = resp.json()

    if not resp.ok:
        err = body.get("error", {})
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"API error {resp.status_code}: {msg}")

    data = body.get("data") or []
    if not data:
        raise RuntimeError("API 返回无 data 字段")

    image_url = data[0].get("url")
    if not image_url:
        b64_json = data[0].get("b64_json")
        if b64_json:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(base64.b64decode(b64_json))
            print(f"  [生图] Done (b64_json): {output_path}")
            return output_path
        raise RuntimeError(f"API 返回无 url/b64_json: {body}")

    print(f"  [生图] Downloading: {image_url[:80]}...")
    img_resp = requests.get(image_url, timeout=120)
    img_resp.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_resp.content)
    print(f"  [生图] Done: {output_path}")
    return output_path


def main() -> None:
    settings = get_settings()
    api_key = settings.agnes_api_key or settings.agnes_free_api_key
    if not api_key:
        print("错误：未配置 AGNES_API_KEY 或 AGNES_FREE_API_KEY")
        sys.exit(1)

    out_dir = ROOT / "data" / "debug"

    # 顺序生成两个角色
    tasks = [
        {"label": "昭昭", "out": out_dir / "zhao_cartoon.png"},
        {"label": "灿灿", "out": out_dir / "can_cartoon.png"},
    ]

    for task in tasks:
        label = task["label"]
        desc = CHARACTERS[label]
        print(f"\n{'='*50}")
        print(f"[{label}] 角色描述: {desc}")

        prompt = f"{STYLE_PROMPT}，{desc}，白色背景，高清，杰作，最佳质量"

        generate_image(
            prompt,
            task["out"],
            api_key=api_key,
            base_url=settings.agnes_api_base_url,
            model=settings.agnes_image_model,
            size="720x1280",
        )

    print(f"\n全部完成，输出目录: {out_dir}")


if __name__ == "__main__":
    main()
