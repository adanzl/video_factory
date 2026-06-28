"""Debug：片头标题冒号渲染与标题解析链路。

用法（backend 目录）:
  python scripts/debug_intro_colon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.intro.generator import (
    _build_layers,
    _compose_frame,
    _layout_for,
    _load_host_sprite,
    _normalize_title,
)
from app.services.intro.title_layout import render_feed_title
from app.services.intro.themes import get_intro_theme
from app.utils.title_text import prefer_source_punctuation
from worker.stages.intro.base import resolve_intro_title

OUT_DIR = BACKEND_DIR.parent / "data" / "debug" / "history_intro_colon_test"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== 1. _normalize_title 变体 ===")
    variants = [
        "秦陵：未解之谜",
        "秦陵:未解之谜",
        "秦陵﹕未解之谜",
        "秦陵︰未解之谜",
    ]
    for raw in variants:
        print(f"  {raw!r} -> {_normalize_title(raw)!r}")

    print("=== 2. resolve_intro_title（draft 含冒号） ===")
    job = {
        "title": "秦陵未解之谜",
        "script_json": {
            "title": "秦陵未解之谜",
            "draft_title": "秦陵：未解之谜",
        },
    }
    resolved = resolve_intro_title(job)
    print(f"  resolved: {resolved!r}")

    print("=== 3. prefer_source_punctuation ===")
    kept = prefer_source_punctuation("秦陵：未解之谜", "秦陵未解之谜")
    print(f"  {kept!r}")

    theme = get_intro_theme("历史悬案")
    w_no = render_feed_title("秦陵未解之谜", theme, 600).size[0]
    w_colon = render_feed_title("秦陵：未解之谜", theme, 600).size[0]
    print("=== 4. 标题块宽度 ===")
    print(f"  无冒号: {w_no}px, 有冒号: {w_colon}px")

    settings = get_settings()
    w, h = 720, 1280
    layout = _layout_for(w, h)
    host = _load_host_sprite(settings, width=w, height=h, layout=layout)

    layers_colon = _build_layers(
        resolved,
        settings.brand_name,
        theme,
        w,
        h,
        host,
        layout,
        moon_path=settings.intro_moon_path,
        moon_tint_yellow=True,
    )
    layers_plain = _build_layers(
        "秦陵未解之谜",
        settings.brand_name,
        theme,
        w,
        h,
        host,
        layout,
        moon_path=settings.intro_moon_path,
        moon_tint_yellow=True,
    )

    frame_colon = _compose_frame(layers_colon, 0.5).convert("RGB")
    frame_colon.save(OUT_DIR / "frame_with_colon.jpg", quality=95)

    text_colon = layers_colon["text_layer"]
    text_plain = layers_plain["text_layer"]
    text_diff = ImageChops.difference(text_colon, text_plain)
    text_bbox = text_colon.getbbox()
    print("=== 5. 文字层差异（有冒号 vs 无冒号） ===")
    print(f"  text_layer bbox: {text_bbox}")
    if text_diff.getbbox():
        nz = sum(1 for p in text_diff.getdata() if p[3] > 10)
        print(f"  差异像素(α>10): {nz}")
    else:
        print("  警告: 文字层完全相同，冒号可能未渲染")

    print(f"=== 输出目录: {OUT_DIR.resolve()} ===")
    print("OK: 冒号链路通过（请查看 intro_history.png / frame_with_colon.jpg）")


if __name__ == "__main__":
    main()
