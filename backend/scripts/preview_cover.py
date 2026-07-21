"""预览投稿封面（以分镜静图为底，与 intro 同款 compose_cover_image）。

用法（backend 目录）:
  python scripts/preview_cover.py --base /tmp/segment1.png
  python scripts/preview_cover.py --base /tmp/segment1.png --title "你的标题"
  python scripts/preview_cover.py --base /tmp/segment1.png --guides  # 4:3 红线预览
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
from app.services.intro.cover_layout import compose_cover_image, split_cover_title_lines
from app.services.intro.generator import central_43_bounds


def _fit_cover(base: Image.Image, width: int, height: int) -> Image.Image:
    """等比放大后居中裁剪到封面画幅。"""
    img = base.convert("RGBA")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w = max(width, int(src_w * scale))
    new_h = max(height, int(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _draw_43_guides(canvas: Image.Image, *, color: tuple[int, int, int, int] = (255, 40, 40, 230)) -> Image.Image:
    """在画布上标注居中 4:3 安全区边界（横屏竖线 / 竖屏横线）。"""
    width, height = canvas.size
    left, top, right, bottom = central_43_bounds(width, height)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    line_w = max(2, round(width / 640))
    if width >= height:
        for x in (left, right):
            draw.line([(x, 0), (x, height)], fill=color, width=line_w)
    else:
        for y in (top, bottom):
            draw.line([(0, y), (width, y)], fill=color, width=line_w)
    base = canvas.convert("RGBA")
    return Image.alpha_composite(base, overlay)


def compose_cover_from_base(
    base_path: Path,
    output_path: Path,
    *,
    title: str,
    width: int,
    height: int,
) -> Path:
    settings = get_settings()
    img = _fit_cover(Image.open(base_path), width, height)
    composed = compose_cover_image(
        img,
        title,
        brand_name=settings.brand_name,
        host_intro_path=settings.host_intro_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        composed.convert("RGB").save(output_path, quality=92)
    else:
        composed.save(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug：分镜底图合成投稿封面")
    parser.add_argument("--base", type=Path, required=True, help="分镜静图路径")
    parser.add_argument("--title", default="秦始皇陵未解之谜")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JPG 路径（指定则只生成一张并覆盖该文件）",
    )
    parser.add_argument(
        "--samples",
        action="store_true",
        help="在底图同目录生成 cover_title_16.jpg / cover_title_5.jpg（覆盖）",
    )
    parser.add_argument(
        "--guides",
        action="store_true",
        help="输出带 4:3 安全区红线的预览图",
    )
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

    if args.samples:
        out_dir = args.base.parent
        title_16 = "大雪封存十三载桩基之下惊现战编钟"
        title_5 = "秦陵编钟谜"
        out16 = out_dir / "cover_title_16.jpg"
        out5 = out_dir / "cover_title_5.jpg"
        compose_cover_from_base(args.base, out16, title=title_16, width=width, height=height)
        compose_cover_from_base(args.base, out5, title=title_5, width=width, height=height)
        print(f"base:   {args.base.resolve()}")
        print(f"16字:   {title_16} -> {out16.resolve()}")
        print(f"5字:    {title_5} -> {out5.resolve()}")
        print(f"lines16: {split_cover_title_lines(title_16)}")
        return

    if args.output is not None:
        compose_cover_from_base(
            args.base,
            args.output,
            title=args.title,
            width=width,
            height=height,
        )
        print(f"base:  {args.base.resolve()}")
        print(f"title: {args.title}")
        print(f"lines: {split_cover_title_lines(args.title)}")
        print(f"saved: {args.output.resolve()}")
        return

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
    )
    compose_cover_from_base(
        args.base,
        cover_png,
        title=args.title,
        width=width,
        height=height,
    )
    if args.guides:
        guides_png = args.base.with_name(f"{args.base.stem}_43_guides.png")
        base = Image.open(args.base)
        frame = _fit_cover(base, width, height)
        guided = _draw_43_guides(frame)
        guided.convert("RGB").save(guides_png, quality=95)
        left, top, right, bottom = central_43_bounds(width, height)
        print(f"4:3 bounds: left={left} right={right} top={top} bottom={bottom}")
        print(f"guides: {guides_png.resolve()}")

    print(f"base:  {args.base.resolve()}")
    print(f"title: {args.title}")
    print(f"lines: {split_cover_title_lines(args.title)}")
    print(f"size:  {width}x{height}")
    print(f"jpg:   {cover_jpg.resolve()} ({cover_jpg.stat().st_size:,} bytes)")
    print(f"png:   {cover_png.resolve()} ({cover_png.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
