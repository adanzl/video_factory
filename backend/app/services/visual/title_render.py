"""标题文字渲染（参考 scene_cut/post_process.py）：描边 + 阴影 + 自适应字号。"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# 描边 / 阴影
STROKE_WIDTH = 1
SHADOW_BLUR = 4
SHADOW_OFFSET_X = 2
SHADOW_OFFSET_Y = 2
STROKE_FILL = (0, 0, 0, 230)
SHADOW_FILL = (0, 0, 0, 210)


def text_bbox(
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    stroke_width: int = STROKE_WIDTH,
) -> tuple[int, int]:
    if not text:
        return 0, 0
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=stroke_width,
    )
    return right - left, bottom - top


def _draw_styled_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    *,
    stroke_width: int = STROKE_WIDTH,
    stroke_fill: tuple[int, int, int, int] = STROKE_FILL,
) -> None:
    draw.text(
        pos,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def render_text_rgba(
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    stroke_width: int = STROKE_WIDTH,
    with_shadow: bool = True,
    shadow_blur: int | None = None,
    shadow_offset_x: int = SHADOW_OFFSET_X,
    shadow_offset_y: int = SHADOW_OFFSET_Y,
    with_glow: bool = False,
    glow_blur: int = 10,
    glow_spread: int = 3,
) -> Image.Image:
    """单行文字：可选阴影/黑色发光 + 描边正文，输出 RGBA。"""
    blur = SHADOW_BLUR if shadow_blur is None else shadow_blur
    extra_pad = glow_blur * 2 if with_glow else (blur if with_shadow else 0)
    width, height = text_bbox(text, font, stroke_width=stroke_width)
    pad = max(
        4,
        extra_pad + stroke_width + abs(shadow_offset_x) + abs(shadow_offset_y),
    )
    canvas = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _draw_styled_text(draw, (pad, pad), text, font, fill, stroke_width=stroke_width)

    if with_glow:
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_stroke = stroke_width + glow_spread
        _draw_styled_text(
            glow_draw,
            (pad, pad),
            text,
            font,
            (0, 0, 0, 220),
            stroke_width=glow_stroke,
            stroke_fill=(0, 0, 0, 220),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_blur))
        merged = Image.alpha_composite(glow, layer)
    elif with_shadow:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        _draw_styled_text(
            shadow_draw,
            (pad + shadow_offset_x, pad + shadow_offset_y),
            text,
            font,
            SHADOW_FILL,
            stroke_width=stroke_width,
            stroke_fill=SHADOW_FILL,
        )
        if blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
        merged = Image.alpha_composite(shadow, layer)
    else:
        merged = layer

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


def compose_vstack(
    images: list[Image.Image],
    *,
    gap: int = 0,
    align: str = "center",
) -> Image.Image:
    valid = [img for img in images if img.size[0] > 0 and img.size[1] > 0]
    if not valid:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    max_w = max(img.size[0] for img in valid)
    total_h = sum(img.size[1] for img in valid) + gap * (len(valid) - 1)
    canvas = Image.new("RGBA", (max_w, total_h), (0, 0, 0, 0))
    y = 0
    for img in valid:
        if align == "right":
            x = max_w - img.size[0]
        elif align == "center":
            x = (max_w - img.size[0]) // 2
        else:
            x = 0
        canvas.alpha_composite(img, (x, y))
        y += img.size[1] + gap
    return canvas


def fit_font_and_lines(
    text: str,
    max_width: int,
    load_font,
    *,
    max_size: int,
    min_size: int,
    wrap_fn,
    max_lines: int | None = None,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """从大字号尝试，直到折行后每行都不超宽（可选限制最大行数）。"""
    normalized = text.strip()
    if not normalized:
        font = load_font(max_size)
        return font, [text], max_size

    for size in range(max_size, min_size - 1, -2):
        font = load_font(size)
        lines = wrap_fn(normalized, font, max_width)
        if max_lines is not None and len(lines) > max_lines:
            continue
        if all(text_bbox(line, font)[0] <= max_width for line in lines):
            return font, lines, size
    font = load_font(min_size)
    lines = wrap_fn(normalized, font, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    return font, lines, min_size


def render_title_block(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    line_gap: int,
    stroke_width: int = STROKE_WIDTH,
    with_shadow: bool = True,
    shadow_blur: int | None = None,
    shadow_offset_x: int = SHADOW_OFFSET_X,
    shadow_offset_y: int = SHADOW_OFFSET_Y,
    with_glow: bool = False,
    glow_blur: int = 10,
    glow_spread: int = 3,
) -> Image.Image:
    rendered = [
        render_text_rgba(
            line,
            font,
            fill=fill,
            stroke_width=stroke_width,
            with_shadow=with_shadow,
            shadow_blur=shadow_blur,
            shadow_offset_x=shadow_offset_x,
            shadow_offset_y=shadow_offset_y,
            with_glow=with_glow,
            glow_blur=glow_blur,
            glow_spread=glow_spread,
        )
        for line in lines
    ]
    return compose_vstack(rendered, gap=line_gap, align="center")
