"""片头画面生成：PIL 绘制标题静帧，再经 FFmpeg 转为短视频。

默认纯文字模板（HOST_ENABLED=false）；讲解人叠图后续在 generate_intro 内扩展。
产物：intro.png（中间帧）+ intro.mp4（3～5s 竖屏片头）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings
from app.services.media.ffmpeg_utils import image_to_video
from app.services.visual.text_render import load_cjk_font, wrap_text
from app.services.visual.title_render import (
    STROKE_WIDTH,
    fit_font_and_lines,
    render_title_block,
)

_BG_COLOR = (26, 39, 68)
_TITLE_BG_COLOR = (255, 214, 64, 255)
_TEXT_COLOR = (26, 26, 26, 255)
_BOX_WIDTH_RATIO = 0.95
_BOX_RADIUS = 56
_BOX_PADDING_X = 56
_BOX_PADDING_Y = 48
_BOX_TOP_RATIO = 0.30
_TITLE_FONT_SIZE = 104
_TITLE_FONT_MIN = 52
_DEFAULT_DURATION_SEC = 3.0


def _is_han(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
    )


def _normalize_intro_text(text: str) -> str:
    """去掉除问号外的标点；问号保留并跟在正文末尾。"""
    parts: list[str] = []
    for char in text:
        if char in "？?":
            parts.append("？")
        elif char.isspace():
            continue
        elif _is_han(char) or (char.isascii() and char.isalnum()):
            parts.append(char)
    return "".join(parts)


def _load_background(width: int, height: int, bg_path: Path) -> Image.Image:
    """等比放大并居中裁剪，铺满成片画幅。"""
    if not bg_path.exists():
        return Image.new("RGBA", (width, height), (*_BG_COLOR, 255))
    bg = Image.open(bg_path).convert("RGBA")
    src_w, src_h = bg.size
    scale = max(width / src_w, height / src_h)
    resized_w = int(src_w * scale)
    resized_h = int(src_h * scale)
    bg = bg.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
    left = (resized_w - width) // 2
    top = (resized_h - height) // 2
    return bg.crop((left, top, left + width, top + height))


def _draw_title_frame(title: str, frame_path: Path) -> None:
    """绘制片头静帧：背景 + 黄底圆角条 + 描边阴影标题。"""
    settings = get_settings()
    width, height = settings.video_width, settings.video_height

    box_width = int(width * _BOX_WIDTH_RATIO)
    box_left = (width - box_width) // 2
    inner_width = box_width - _BOX_PADDING_X * 2

    normalized = _normalize_intro_text(title) or title.strip()

    def _load(size: int):
        return load_cjk_font(size)

    font, lines, font_size = fit_font_and_lines(
        normalized,
        inner_width,
        _load,
        max_size=_TITLE_FONT_SIZE,
        min_size=_TITLE_FONT_MIN,
        wrap_fn=wrap_text,
    )
    line_gap = max(4, font_size // 24)

    text_block = render_title_block(
        lines,
        font,
        fill=_TEXT_COLOR,
        line_gap=line_gap,
        stroke_width=STROKE_WIDTH,
    )

    box_height = text_block.size[1] + _BOX_PADDING_Y * 2
    box_top = int(height * _BOX_TOP_RATIO)

    image = _load_background(width, height, settings.intro_bg_path)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [box_left, box_top, box_left + box_width, box_top + box_height],
        radius=_BOX_RADIUS,
        fill=_TITLE_BG_COLOR,
    )

    text_x = box_left + (box_width - text_block.size[0]) // 2
    text_y = box_top + _BOX_PADDING_Y
    image.alpha_composite(text_block, (text_x, text_y))

    frame_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(frame_path, compress_level=1)


def generate_intro(title: str, output_path: Path, *, duration: float = _DEFAULT_DURATION_SEC) -> Path:
    """生成片头 MP4：intro.png → image_to_video → intro.mp4。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path = output_path.with_suffix(".png")
    _draw_title_frame(title, frame_path)
    image_to_video(frame_path, output_path, duration=duration)
    return output_path
