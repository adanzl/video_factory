"""封面合成（独立脚本）：底图 + 讲解人 + 标题 → cover.png

用法:
  python covers/compose_cover.py
  python covers/compose_cover.py --make-english-base
  python covers/compose_cover.py --base covers/base_english.jpeg --title "昭墨英语 （一）" --output covers/cover_english.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COVERS_DIR = Path(__file__).resolve().parent
ROOT_DIR = COVERS_DIR.parent
RES_DIR = ROOT_DIR / "backend" / "res"

DEFAULT_BASE = COVERS_DIR / "base_math.jpeg"
DEFAULT_BG = COVERS_DIR / "base.jpeg"
DEFAULT_BOOK = COVERS_DIR / "book1.png"
DEFAULT_OUTPUT = COVERS_DIR / "cover.png"
DEFAULT_ENGLISH_BASE = COVERS_DIR / "base_english.jpeg"
DEFAULT_HOST = RES_DIR / "host" / "intro.png"
DEFAULT_FONT = RES_DIR / "font" / "SourceHanSansCN-Medium.otf"

COVER_WIDTH = 1280
COVER_HEIGHT = 720
DEFAULT_HOST_SCALE = 0.75
DEFAULT_TITLE = "昭墨学数学 （一）"
DEFAULT_BRAND = "昭墨百科"

TITLE_MAX_CHARS = 18
TITLE_SINGLE_LINE_MAX = 8
TITLE_FILL = (255, 210, 50, 255)
TITLE_STROKE = (60, 30, 15, 255)
STROKE_WIDTH = 1


def _central_43_bounds(width: int, height: int) -> tuple[int, int, int, int]:
    """画布内居中 4:3 安全区 (left, top, right, bottom)。"""
    if width >= height:
        crop_w = height * 4 / 3
        left = int(round((width - crop_w) / 2))
        return left, 0, left + int(crop_w), height
    crop_h = width * 3 / 4
    top = int(round((height - crop_h) / 2))
    return 0, top, width, top + int(crop_h)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(DEFAULT_FONT), size=size)


def _text_bbox(text: str, font: ImageFont.FreeTypeFont, *, stroke_width: int = STROKE_WIDTH) -> tuple[int, int]:
    if not text:
        return 0, 0
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return right - left, bottom - top


def _balance_title_lines(text: str, max_lines: int) -> list[str]:
    normalized = text.strip()
    if not normalized or max_lines <= 1:
        return [normalized] if normalized else []
    n = len(normalized)
    if n <= max_lines:
        return [normalized]
    base, extra = divmod(n, max_lines)
    lines: list[str] = []
    idx = 0
    for i in range(max_lines):
        length = base + (1 if i < extra else 0)
        if length <= 0:
            break
        lines.append(normalized[idx : idx + length])
        idx += length
    return lines


def _split_title_lines(title: str) -> list[str]:
    display = title.replace("：", " ").replace(":", " ").strip()
    if not display:
        return [""]
    compact = display.replace(" ", "")
    if len(compact) > TITLE_MAX_CHARS:
        compact = compact[:TITLE_MAX_CHARS]
    if " " in display:
        parts = display.split(" ", 1)
        line1 = parts[0].strip()[:TITLE_MAX_CHARS]
        line2 = parts[1].strip()[: TITLE_MAX_CHARS - len(line1)] if len(parts) > 1 else ""
        if line2:
            return [line1, line2]
        return [line1] if line1 else [compact]
    if len(compact) <= TITLE_SINGLE_LINE_MAX:
        return [compact]
    return _balance_title_lines(compact, 2)


def _render_text_rgba(
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
) -> Image.Image:
    shadow_blur = 10
    shadow_offset_x = 2
    shadow_offset_y = 2
    width, height = _text_bbox(text, font, stroke_width=stroke_width)
    pad = max(4, shadow_blur + stroke_width + abs(shadow_offset_x) + abs(shadow_offset_y))
    canvas = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.text(
        (pad, pad),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text(
        (pad + shadow_offset_x, pad + shadow_offset_y),
        text,
        font=font,
        fill=(0, 0, 0, 210),
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    merged = Image.alpha_composite(shadow, layer)

    bbox = merged.getbbox()
    if bbox is None:
        return merged
    margin = stroke_width
    return merged.crop(
        (
            max(0, bbox[0] - margin),
            max(0, bbox[1] - margin),
            min(merged.size[0], bbox[2] + margin),
            min(merged.size[1], bbox[3] + margin),
        )
    )


def _compose_vstack(images: list[Image.Image], *, gap: int) -> Image.Image:
    if not images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    width = max(img.size[0] for img in images)
    height = sum(img.size[1] for img in images) + gap * max(len(images) - 1, 0)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    for img in images:
        x = (width - img.size[0]) // 2
        canvas.paste(img, (x, y), img)
        y += img.size[1] + gap
    return canvas


def _fit_cover(base: Image.Image, width: int, height: int) -> Image.Image:
    img = base.convert("RGBA")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w = max(width, int(src_w * scale))
    new_h = max(height, int(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _paste_book(
    canvas: Image.Image,
    book_path: Path,
    *,
    max_width_ratio: float = 0.52,
    max_height_ratio: float = 0.88,
    center_x_ratio: float = 0.5,
    center_y_ratio: float = 0.48,
) -> Image.Image:
    canvas = canvas.convert("RGBA")
    cw, ch = canvas.size
    book = Image.open(book_path).convert("RGBA")
    max_w = int(cw * max_width_ratio)
    max_h = int(ch * max_height_ratio)
    shrink = min(1.0, max_w / book.size[0], max_h / book.size[1])
    book = book.resize(
        (int(book.size[0] * shrink), int(book.size[1] * shrink)),
        Image.Resampling.LANCZOS,
    )
    bx = int(cw * center_x_ratio) - book.size[0] // 2
    by = int(ch * center_y_ratio) - book.size[1] // 2
    canvas.paste(book, (bx, by), book)
    return canvas


def _paste_host(canvas: Image.Image, host_path: Path, *, host_scale: float) -> Image.Image:
    canvas = canvas.convert("RGBA")
    cw, ch = canvas.size
    is_landscape = cw > ch
    host_visible = 0.58 if is_landscape else 1.0

    host = Image.open(host_path).convert("RGBA")
    width_ratio = (0.72 if is_landscape else 0.94) * host_scale
    height_ratio = (0.88 if is_landscape else 0.42) * host_scale
    max_w = int(cw * width_ratio)
    max_h = int(ch * height_ratio)
    shrink = min(1.0, max_w / host.size[0], max_h / host.size[1])
    host = host.resize(
        (int(host.size[0] * shrink), int(host.size[1] * shrink)),
        Image.Resampling.LANCZOS,
    )
    hx = (cw - host.size[0]) // 2
    hy = ch - int(host.size[1] * host_visible) if host_visible < 1.0 else ch - host.size[1]
    canvas.paste(host, (hx, hy), host)
    return canvas


def _render_title_block(
    title: str,
    *,
    safe_left: int,
    safe_top: int,
    safe_right: int,
    safe_bottom: int,
    is_landscape: bool,
) -> tuple[Image.Image, int, int]:
    safe_w = safe_right - safe_left
    safe_h = safe_bottom - safe_top
    lines = [ln for ln in _split_title_lines(title) if ln] or [""]

    title_max_w = int(safe_w * 0.92)
    title_max_h = int(safe_h * 0.34) if is_landscape else int(safe_h * 0.24)
    title_max_size = 135 if is_landscape else 120
    title_min_size = 100 if is_landscape else 96
    line_gap = 10
    font = _load_font(title_min_size)
    font_size = title_min_size

    for size in range(title_max_size, title_min_size - 1, -2):
        candidate = _load_font(size)
        if not all(_text_bbox(line, candidate)[0] <= title_max_w for line in lines):
            continue
        total_h = sum(_text_bbox(line, candidate)[1] for line in lines)
        total_h += line_gap * max(len(lines) - 1, 0)
        if total_h <= title_max_h:
            font = candidate
            font_size = size
            break

    line_gap = max(8, font_size // 12)
    rendered = [
        _render_text_rgba(
            line,
            font,
            fill=TITLE_FILL,
            stroke_width=STROKE_WIDTH + 2,
            stroke_fill=TITLE_STROKE,
        )
        for line in lines
    ]
    text_block = _compose_vstack(rendered, gap=line_gap)

    margin = max(6, int(min(safe_w, safe_h) * 0.03))
    tx = safe_left + (safe_w - text_block.size[0]) // 2
    center_y = safe_top + int(safe_h * 0.36)
    ty = center_y - text_block.size[1] // 2
    tx = max(safe_left + margin, min(tx, safe_right - margin - text_block.size[0]))
    ty = max(safe_top + margin, min(ty, safe_bottom - margin - text_block.size[1]))
    return text_block, tx, ty


def _compose_cover(
    canvas: Image.Image,
    *,
    title: str,
    host_path: Path,
    host_scale: float,
    brand_name: str | None,
) -> Image.Image:
    canvas = _paste_host(canvas, host_path, host_scale=host_scale)
    cw, ch = canvas.size
    is_landscape = cw > ch
    safe_left, safe_top, safe_right, safe_bottom = _central_43_bounds(cw, ch)
    safe_w = safe_right - safe_left

    if brand_name:
        brand_font = _load_font(max(24, int(72 * ch / 1080)))
        brand = _render_text_rgba(
            brand_name,
            brand_font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(60, 30, 15, 255),
        )
        brand_x = safe_left + (safe_w - brand.size[0]) // 2
        canvas.paste(brand, (brand_x, int(ch * 0.04)), brand)

    text_block, tx, ty = _render_title_block(
        title,
        safe_left=safe_left,
        safe_top=safe_top,
        safe_right=safe_right,
        safe_bottom=safe_bottom,
        is_landscape=is_landscape,
    )
    canvas.paste(text_block, (tx, ty), text_block)
    return canvas


def _save_image(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        img.convert("RGB").save(path, quality=92)
    else:
        img.save(path)


def compose(
    *,
    base_path: Path,
    host_path: Path,
    title: str,
    host_scale: float,
    cover_width: int,
    cover_height: int,
    no_fit: bool,
    no_cover: bool,
    book_only: bool,
    brand_name: str | None,
    book_path: Path | None = None,
) -> Image.Image:
    base = Image.open(base_path)
    canvas = base.convert("RGBA") if no_fit else _fit_cover(base, cover_width, cover_height)

    if book_path is not None:
        canvas = _paste_book(canvas, book_path)

    if book_only:
        return canvas
    if no_cover:
        return _paste_host(canvas, host_path, host_scale=host_scale)

    return _compose_cover(
        canvas,
        title=title,
        host_path=host_path,
        host_scale=host_scale,
        brand_name=brand_name,
    )


def _resolve_covers_path(path: Path) -> Path:
    if path.is_file() or path.is_absolute():
        return path
    candidate = COVERS_DIR / path
    return candidate if candidate.is_file() else path


def main() -> None:
    parser = argparse.ArgumentParser(description="封面合成（独立脚本）")
    parser.add_argument(
        "--make-english-base",
        action="store_true",
        help="book1 叠加到 base.jpeg，输出 base_english.jpeg",
    )
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE, help="底图路径")
    parser.add_argument("--book", type=Path, default=None, help="叠加书籍 PNG")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出路径")
    parser.add_argument("--host", type=Path, default=DEFAULT_HOST, help="讲解人 PNG")
    parser.add_argument("--no-fit", action="store_true", help="不裁剪到封面画幅")
    parser.add_argument("--no-cover", action="store_true", help="仅叠加讲解人，不渲染标题")
    parser.add_argument("--book-only", action="store_true", help="仅底图 + 书籍")
    parser.add_argument("--brand", action="store_true", help="叠加品牌名")
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--host-scale", type=float, default=DEFAULT_HOST_SCALE)
    args = parser.parse_args()

    if args.make_english_base:
        args.base = DEFAULT_BG
        args.book = DEFAULT_BOOK
        args.output = DEFAULT_ENGLISH_BASE
        args.book_only = True
        args.no_fit = True

    args.base = _resolve_covers_path(args.base)
    if args.book is not None:
        args.book = _resolve_covers_path(args.book)
    args.host = _resolve_covers_path(args.host)

    if not args.base.is_file():
        raise SystemExit(f"底图不存在: {args.base}")
    if not args.host.is_file():
        raise SystemExit(f"讲解人素材不存在: {args.host}")

    composed = compose(
        base_path=args.base,
        host_path=args.host,
        title=args.title,
        host_scale=args.host_scale,
        cover_width=COVER_WIDTH,
        cover_height=COVER_HEIGHT,
        no_fit=args.no_fit,
        no_cover=args.no_cover,
        book_only=args.book_only,
        brand_name=DEFAULT_BRAND if args.brand else None,
        book_path=args.book,
    )
    _save_image(composed, args.output)

    print(f"base:   {args.base.resolve()}")
    if args.book:
        print(f"book:   {args.book.resolve()}")
    print(f"host:   {args.host.resolve()}")
    print(f"size:   {composed.size[0]}x{composed.size[1]}")
    if args.book_only:
        mode = "book"
    elif args.no_cover:
        mode = "host"
    else:
        mode = "cover"
    print(f"mode:   {mode}")
    if not args.no_cover and not args.book_only:
        print(f"title:  {args.title}")
        if args.brand:
            print(f"brand:  {DEFAULT_BRAND}")
    elif not args.book_only:
        print(f"scale:  {args.host_scale}")
    print(f"saved:  {args.output.resolve()}")


if __name__ == "__main__":
    main()
