"""本地 debug：以分镜静图为底图合成投稿封面（16:9）。

用法（backend 目录）:
  python scripts/debug_cover.py --base /tmp/segment1.png
  python scripts/debug_cover.py --base /tmp/segment1.png --title "你的标题"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.intro.title_layout import render_feed_title
from app.services.intro.themes import get_intro_theme


def _fit_cover(base: Image.Image, width: int, height: int) -> Image.Image:
    """等比放大后居中裁剪到封面画幅。"""
    img = base.convert("RGB")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w = max(width, int(src_w * scale))
    new_h = max(height, int(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _bottom_scrim(canvas: Image.Image, *, height_ratio: float = 0.42) -> Image.Image:
    """底部渐变遮罩，便于叠标题。"""
    out = canvas.convert("RGBA")
    width, height = out.size
    grad_h = max(1, int(height * height_ratio))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top = height - grad_h
    for y in range(grad_h):
        alpha = int(210 * (y + 1) / grad_h)
        draw.line([(0, top + y), (width, top + y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(out, overlay)


def compose_cover_from_base(
    base_path: Path,
    output_path: Path,
    *,
    title: str,
    width: int,
    height: int,
    category: str = "百科",
) -> Path:
    theme = get_intro_theme(category)
    base = Image.open(base_path)
    frame = _fit_cover(base, width, height)
    canvas = _bottom_scrim(frame)

    title_block = render_feed_title(
        title.strip(),
        theme,
        int(width * 0.88),
        max_size=96,
        min_size=48,
        max_lines=3,
        max_height=int(height * 0.28),
    )
    x = (width - title_block.size[0]) // 2
    y = height - title_block.size[1] - int(height * 0.06)
    canvas.alpha_composite(title_block, (x, y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        canvas.convert("RGB").save(output_path, quality=92)
    else:
        canvas.save(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug：分镜底图合成投稿封面")
    parser.add_argument("--base", type=Path, required=True, help="分镜静图路径")
    parser.add_argument("--title", default="秦始皇陵未解之谜")
    parser.add_argument("--category", default="百科", choices=["百科", "历史悬案"])
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BACKEND_DIR.parent / "data" / "debug" / "cover",
    )
    args = parser.parse_args()

    if not args.base.is_file():
        raise SystemExit(f"底图不存在: {args.base}")

    settings = get_settings()
    width = settings.cover_width
    height = settings.cover_height
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cover_jpg = out_dir / "cover.jpg"
    cover_png = out_dir / "cover.png"
    compose_cover_from_base(
        args.base,
        cover_jpg,
        title=args.title,
        width=width,
        height=height,
        category=args.category,
    )
    compose_cover_from_base(
        args.base,
        cover_png,
        title=args.title,
        width=width,
        height=height,
        category=args.category,
    )

    print(f"base:  {args.base.resolve()}")
    print(f"title: {args.title}")
    print(f"size:  {width}x{height}")
    print(f"jpg:   {cover_jpg.resolve()} ({cover_jpg.stat().st_size:,} bytes)")
    print(f"png:   {cover_png.resolve()} ({cover_png.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
