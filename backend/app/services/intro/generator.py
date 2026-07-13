"""片头视频：品牌喊声 + 本期标题 + 双人 IP，按分类色系程序化合成。"""

from __future__ import annotations

import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from app.config import get_settings
from app.services.intro.title_layout import render_feed_title
from app.services.intro.themes import get_intro_theme
from app.services.media.ffmpeg_utils import (
    OUTPUT_AUDIO_SAMPLE_RATE,
    mux_video_audio,
    probe_duration,
    sequence_to_video,
)
from app.services.render.text_render import load_cjk_font
from app.services.render.title_render import STROKE_WIDTH, render_text_rgba

_FPS = 25
_ENTER_SEC = 0.32
_HOLD_TAIL_SEC = 0.15


@dataclass(frozen=True)
class _IntroLayout:
    """竖屏 / 横屏片头布局参数。"""

    landscape: bool
    brand_top_ratio: float
    badge_margin_x_ratio: float  # 竖屏：相对画布左缘；横屏：相对 4:3 安全区左缘
    title_circle_width_ratio: float
    title_moon_scale: float
    title_center_x_ratio: float
    title_center_y_ratio: float
    title_text_width_ratio: float
    title_circle_height_cap_ratio: float | None
    host_height_ratio: float
    host_width_ratio: float
    host_right_ratio: float | None
    host_bottom_ratio: float
    host_visible_fraction: float
    episode_font_max: int
    episode_font_min: int
    episode_max_lines: int
    accent_width_ratio: float
    title_text_moon_width_ratio: float


_PORTRAIT_LAYOUT = _IntroLayout(
    landscape=False,
    brand_top_ratio=0.06,
    badge_margin_x_ratio=0.04,
    title_circle_width_ratio=0.60,
    title_moon_scale=1.5,
    title_center_x_ratio=0.5,
    title_center_y_ratio=0.36,
    title_text_width_ratio=0.90,
    title_circle_height_cap_ratio=None,
    host_height_ratio=0.42,
    host_width_ratio=0.94,
    host_right_ratio=None,
    host_bottom_ratio=0.02,
    host_visible_fraction=1.0,
    episode_font_max=120,
    episode_font_min=96,
    episode_max_lines=3,
    accent_width_ratio=0.55,
    title_text_moon_width_ratio=0.88,
)

_LANDSCAPE_LAYOUT = _IntroLayout(
    landscape=True,
    brand_top_ratio=0.05,
    badge_margin_x_ratio=0.04,
    title_circle_width_ratio=0.52,
    title_moon_scale=1.12,
    title_center_x_ratio=0.5,
    title_center_y_ratio=0.36,
    title_text_width_ratio=0.88,
    title_circle_height_cap_ratio=0.88,
    host_height_ratio=0.88,
    host_width_ratio=0.72,
    host_right_ratio=None,
    host_bottom_ratio=0.0,
    host_visible_fraction=0.58,
    episode_font_max=184,
    episode_font_min=100,
    episode_max_lines=2,
    accent_width_ratio=0.0,
    title_text_moon_width_ratio=1.28,
)


def _layout_for(width: int, height: int) -> _IntroLayout:
    return _LANDSCAPE_LAYOUT if width > height else _PORTRAIT_LAYOUT


def _moon_diameter(layout: _IntroLayout, width: int, height: int) -> int:
    from_width = int(width * layout.title_circle_width_ratio * layout.title_moon_scale)
    if layout.title_circle_height_cap_ratio is None:
        return from_width
    from_height = int(height * layout.title_circle_height_cap_ratio)
    return min(from_width, from_height)


_BRAND_FONT_SIZE = 72

# 常见冒号变体（Word / 竖排标点等）统一为全角冒号
_COLON_CHARS = frozenset(":\uFF1A\uFE55\uFE30\uFE13\u0589\uA789")
_HALF_TO_FULL = str.maketrans(
    {
        ":": "：",
        "?": "？",
        "!": "！",
        ",": "，",
        ";": "；",
    }
)


def _normalize_title(text: str) -> str:
    """片头标题：去空白，半角/变体标点归一，其余字符保留。"""
    parts: list[str] = []
    for char in text:
        if char.isspace():
            continue
        if char in _COLON_CHARS:
            parts.append("：")
        else:
            parts.append(char)
    return "".join(parts).translate(_HALF_TO_FULL)


def _ease_out_back(t: float, s: float = 1.4) -> float:
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return t * t * ((s + 1.0) * t + s) + 1.0


def _draw_vertical_gradient_rgba(
    width: int,
    height: int,
    top: tuple[int, int, int, int],
    bottom: tuple[int, int, int, int],
) -> Image.Image:
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def _key_black_to_alpha(img: Image.Image, *, threshold: int = 35) -> Image.Image:
    rgba = img.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0 or (r <= threshold and g <= threshold and b <= threshold):
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _tint_image(
    img: Image.Image,
    color: tuple[int, int, int],
    *,
    strength: float = 0.5,
) -> Image.Image:
    tinted = img.copy()
    pixels = tinted.load()
    w, h = tinted.size
    tr, tg, tb = color
    mix = max(0.0, min(1.0, strength))
    keep = 1.0 - mix
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            pixels[x, y] = (
                int(r * keep + tr * mix),
                int(g * keep + tg * mix),
                int(b * keep + tb * mix),
                a,
            )
    return tinted


def _load_moon_backdrop(
    path: Path,
    diameter: int,
    theme,
    *,
    tint_yellow: bool = False,
) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"片头月亮素材不存在: {path}")
    moon = Image.open(path).convert("RGBA")
    moon = moon.resize((diameter, diameter), Image.Resampling.LANCZOS)
    moon = _key_black_to_alpha(moon)
    if tint_yellow:
        moon = _tint_image(moon, theme.title_fill[:3], strength=0.58)
    fade = _draw_vertical_gradient_rgba(
        diameter,
        diameter,
        (255, 255, 255, theme.title_circle_top[3]),
        (255, 255, 255, theme.title_circle_bottom[3]),
    )
    moon.putalpha(ImageChops.multiply(moon.split()[3], fade.split()[3]))
    return moon


def _draw_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
            255,
        )
        draw.line([(0, y), (width, y)], fill=color)
    return image


def _draw_particles(width: int, height: int, color: tuple[int, int, int, int]) -> Image.Image:
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    spacing = 56
    for x in range(0, width + spacing, spacing):
        for y in range(0, height + spacing, spacing):
            alpha = color[3] + int(12 * math.sin(x * 0.03 + y * 0.02))
            r = 2 + int(abs(math.sin(x * 0.01)) * 2)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(color[0], color[1], color[2], min(alpha, 90)))
    return layer


def _load_host_sprite(host_path: Path, *, width: int, height: int, layout: _IntroLayout) -> Image.Image:
    """加载片头双人图 intro.png，仅等比缩放，不裁剪。"""
    path = host_path
    if not path.exists():
        raise FileNotFoundError(f"片头讲解人素材不存在: {path}")
    img = Image.open(path).convert("RGBA")
    max_w = int(width * layout.host_width_ratio)
    max_h = int(height * layout.host_height_ratio)
    shrink = min(1.0, max_w / img.size[0], max_h / img.size[1])
    if shrink >= 1.0:
        return img
    return img.resize(
        (int(img.size[0] * shrink), int(img.size[1] * shrink)),
        Image.Resampling.LANCZOS,
    )


def central_43_bounds(width: int, height: int) -> tuple[int, int, int, int]:
    """画布内居中 4:3 安全区 (left, top, right, bottom)。

    横屏 16:9 裁左右（1280×720 → x=160~1120）；竖屏 9:16 裁上下。
    片头与投稿封面共用此区域约束品牌/标题位置。
    """
    if width >= height:
        crop_w = height * 4 / 3
        left = int(round((width - crop_w) / 2))
        return left, 0, left + int(crop_w), height
    crop_h = width * 3 / 4
    top = int(round((height - crop_h) / 2))
    return 0, top, width, top + int(crop_h)


def _central_43_left_x(width: int, height: int) -> int:
    """16:9 画布内居中 4:3 区域的左边界 x。"""
    return central_43_bounds(width, height)[0]


def _brand_header_x(width: int, height: int, layout: _IntroLayout, header_w: int) -> int:
    if layout.landscape:
        left = _central_43_left_x(width, height)
        crop_w = height * 4 / 3
        center_x = left + crop_w / 2
        return int(round(center_x - header_w / 2))
    return (width - header_w) // 2


def _render_brand_mark(theme, brand: str) -> Image.Image:
    """昭墨百科：红字 + 白色描边，无背景。"""
    font = load_cjk_font(_BRAND_FONT_SIZE)
    return render_text_rgba(
        brand,
        font,
        fill=theme.brand_fill,
        stroke_width=STROKE_WIDTH + 4,
        stroke_fill=theme.brand_stroke,
        with_shadow=True,
        shadow_blur=6,
    )


def _render_brand_header(theme, brand: str) -> Image.Image:
    """顶栏品牌字标（昭墨百科）。"""
    return _render_brand_mark(theme, brand)


def _build_title_layers(
    title: str,
    theme,
    width: int,
    height: int,
    layout: _IntroLayout,
    *,
    moon_path: Path,
    moon_tint_yellow: bool = False,
) -> tuple[Image.Image, Image.Image]:
    """分别生成月亮层与标题文字层（全画布透明底）。"""
    diameter = _moon_diameter(layout, width, height)
    center_x = int(width * layout.title_center_x_ratio)
    center_y = int(height * layout.title_center_y_ratio)
    if layout.landscape:
        text_max_w = int(diameter * layout.title_text_moon_width_ratio)
    else:
        text_max_w = int(width * layout.title_text_width_ratio)
        text_max_w = min(text_max_w, int(diameter * layout.title_text_moon_width_ratio))
    text_max_h = int(diameter * 0.68)

    text_block = render_feed_title(
        title,
        theme,
        text_max_w,
        max_size=layout.episode_font_max,
        min_size=layout.episode_font_min,
        max_lines=layout.episode_max_lines,
        max_height=text_max_h,
    )

    left = center_x - diameter // 2
    top = center_y - diameter // 2
    moon = _load_moon_backdrop(
        moon_path,
        diameter,
        theme,
        tint_yellow=moon_tint_yellow,
    )

    moon_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    moon_layer.alpha_composite(moon, (left, top))

    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_layer.alpha_composite(
        text_block,
        (center_x - text_block.size[0] // 2, center_y - text_block.size[1] // 2),
    )
    return moon_layer, text_layer


def _build_layers(
    title: str,
    brand: str,
    theme,
    width: int,
    height: int,
    host: Image.Image,
    layout: _IntroLayout,
    *,
    moon_path: Path,
    moon_tint_yellow: bool = False,
    bg_image_path: Path | None = None,
) -> dict:
    normalized = _normalize_title(title) or title.strip()
    moon_layer, text_layer = _build_title_layers(
        normalized,
        theme,
        width,
        height,
        layout,
        moon_path=moon_path,
        moon_tint_yellow=moon_tint_yellow,
    )

    brand_header = _render_brand_header(theme, brand)

    if bg_image_path and bg_image_path.exists():
        bg_img = Image.open(bg_image_path).convert("RGBA")
        bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)
        bg = bg_img
    else:
        bg = _draw_gradient(width, height, theme.bg_top, theme.bg_bottom)
        bg.alpha_composite(_draw_particles(width, height, theme.particle))

    host_scaled = host

    return {
        "bg": bg,
        "moon_layer": moon_layer,
        "text_layer": text_layer,
        "brand_header": brand_header,
        "host": host_scaled,
        "layout": layout,
        "theme": theme,
        "width": width,
        "height": height,
    }


def _host_position(layers: dict, host_w: int, host_h: int, *, enter: float) -> tuple[int, int]:
    width = layers["width"]
    height = layers["height"]
    layout: _IntroLayout = layers["layout"]
    if layout.host_right_ratio is not None:
        host_x = width - host_w - int(width * layout.host_right_ratio)
    else:
        host_x = (width - host_w) // 2
    visible = max(0.0, min(1.0, layout.host_visible_fraction))
    if visible < 1.0:
        # 仅露出上方 visible 比例，其余在屏幕外（横屏：下半身在画面下缘之外）
        host_y = height - int(host_h * visible)
    else:
        host_y = height - host_h - int(height * layout.host_bottom_ratio)
    host_y += int((1.0 - enter) * (60 if layout.landscape else 80))
    return host_x, host_y


def _compose_frame(layers: dict, t: float) -> Image.Image:
    width = layers["width"]
    height = layers["height"]
    layout: _IntroLayout = layers["layout"]
    frame = layers["bg"].copy()

    enter = _ease_out_back(min(t / _ENTER_SEC, 1.0))
    opacity = min(1.0, t / 0.12) if t < _ENTER_SEC else 1.0
    breathe = 1.0 + 0.012 * math.sin(max(0.0, t - _ENTER_SEC) * 5.5)

    host: Image.Image = layers["host"]
    host_w = int(host.size[0] * (0.88 + 0.12 * enter) * breathe)
    host_h = int(host.size[1] * (0.88 + 0.12 * enter) * breathe)
    host_frame = host.resize((host_w, host_h), Image.Resampling.LANCZOS)
    host_x, host_y = _host_position(layers, host_w, host_h, enter=enter)

    moon: Image.Image = layers["moon_layer"]
    frame.alpha_composite(_with_opacity(moon, opacity), (0, 0))

    frame.alpha_composite(host_frame, (host_x, host_y))

    header: Image.Image = layers["brand_header"]
    header_x = _brand_header_x(width, height, layout, header.size[0])
    header_y = int(height * layout.brand_top_ratio)
    frame.alpha_composite(_with_opacity(header, opacity), (header_x, header_y))

    text: Image.Image = layers["text_layer"]
    frame.alpha_composite(_with_opacity(text, opacity), (0, 0))

    if layout.accent_width_ratio > 0:
        accent_w = int(width * layout.accent_width_ratio)
        accent_x = (width - accent_w) // 2
        accent_y = height - 24
        accent = layers["theme"].accent
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle(
            [accent_x, accent_y, accent_x + accent_w, accent_y + 6],
            radius=3,
            fill=(accent[0], accent[1], accent[2], int(accent[3] * opacity * 220 / 255)),
        )

    return frame


def _with_opacity(img: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return img
    out = img.copy()
    alpha = out.split()[3].point(lambda a: int(a * opacity))
    out.putalpha(alpha)
    return out


def _render_frames(
    layers: dict,
    frames_dir: Path,
    *,
    duration: float,
    fps: int = _FPS,
) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = max(int(duration * fps), 1)
    for i in range(total):
        t = i / fps
        frame = _compose_frame(layers, t)
        frame.convert("RGB").save(frames_dir / f"frame_{i:04d}.png", compress_level=1)
        # 让出 GIL，避免片头逐帧渲染时卡死 gevent 主线程接口
        time.sleep(0.001)
    return total


def _brand_audio_path(work_dir: Path, pipeline: str | None = None) -> Path:
    """优先使用 res 预置喊声；缺失时抛出明确错误。"""
    settings = get_settings()
    src = settings.get_intro_shout_path(pipeline)
    if not src.exists():
        raise FileNotFoundError(
            f"片头喊声音频不存在: {src}，请运行 scripts/prepare_intro_audio.py 生成"
        )
    dest = work_dir / "intro_shout.mp3"
    shutil.copy2(src, dest)
    return dest


def generate_intro(
    title: str,
    output_path: Path,
    *,
    category: str | None = None,
    work_dir: Path | None = None,
    hold_tail_sec: float | None = None,
    width: int | None = None,
    height: int | None = None,
    pipeline: str | None = None,
) -> Path:
    """生成带品牌喊声的片头 MP4。width/height 缺省时使用全局 VIDEO 配置。"""
    settings = get_settings()
    theme = get_intro_theme(category)
    video_w = width if width is not None else settings.video_width
    video_h = height if height is not None else settings.video_height
    layout = _layout_for(video_w, video_h)
    host_path = settings.get_host_intro_path(pipeline)
    host = _load_host_sprite(host_path, width=video_w, height=video_h, layout=layout)

    work = work_dir or output_path.parent / "intro_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    audio_path = _brand_audio_path(work, pipeline)
    audio_dur = probe_duration(audio_path)
    tail = _HOLD_TAIL_SEC if hold_tail_sec is None else max(0.0, hold_tail_sec)
    duration = audio_dur + tail

    moon_tint_yellow = settings.intro_moon_tint in {"yellow", "tint", "gold", "1", "true"}
    if category == "历史悬案":
        moon_tint_yellow = True
    layers = _build_layers(
        title,
        settings.brand_name,
        theme,
        video_w,
        video_h,
        host,
        layout,
        moon_path=settings.get_moon_path(pipeline),
        moon_tint_yellow=moon_tint_yellow,
        bg_image_path=settings.get_intro_bg_path(pipeline),
    )
    frames_dir = work / "frames"
    frame_count = _render_frames(layers, frames_dir, duration=duration, fps=_FPS)

    silent_video = work / "video.mp4"
    sequence_to_video(
        frames_dir,
        silent_video,
        fps=_FPS,
        frame_count=frame_count,
        subtitle=True,
        force_cpu=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mux_video_audio(
        silent_video,
        audio_path,
        output_path,
        sample_rate=OUTPUT_AUDIO_SAMPLE_RATE,
        channels=1,
    )

    preview = output_path.with_suffix(".png")
    _compose_frame(layers, duration * 0.45).convert("RGB").save(preview, compress_level=1)

    shutil.rmtree(work, ignore_errors=True)
    return output_path
