"""投稿封面：4:3 安全区、标题折行与品牌/讲解人/标题合成。

横屏 1280×720 时 4:3 安全区为 x=160~1120；标题黄字居中偏上（安全区高度 36%），
字号横屏 135→112 自适应。与 intro 片头共用 central_43_bounds。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.services.intro.generator import central_43_bounds
from app.services.render.text_render import balance_title_lines, load_cjk_font
from app.services.render.title_render import (
    STROKE_WIDTH,
    compose_vstack,
    render_text_rgba,
    text_bbox,
)

# 与 MAX_TITLE_LENGTH 一致；封面渲染时超长会截断到此长度
COVER_TITLE_MAX_CHARS = 18
_COVER_TITLE_FILL = (255, 210, 50, 255)
_COVER_TITLE_STROKE = (60, 30, 15, 255)
# 无空格时单行上限；超过则 balance_title_lines 均分两行
_COVER_SINGLE_LINE_MAX = 8


def cover_canvas_size(width: int, height: int) -> tuple[int, int, bool]:
    """封面合成画幅 (cw, ch, is_landscape)。"""
    if width > height:
        return 1280, 720, True
    return 720, 1280, False


_COVER_MAP_KEYWORDS = ("世界地图", "地球仪")


def _resolve_cover_subject(subject: str) -> str:
    """若 subject 含地图关键词（如"世界地图"）则通过 LLM 改写，
    避免在"不得出现世界地图"的同时出现"世界地图背景上"的矛盾。"""
    if not any(kw in subject for kw in _COVER_MAP_KEYWORDS):
        return subject

    import logging

    from app.config import get_settings
    from app.services.llm.llm_deepseek import DeepSeekClient

    logger = logging.getLogger(__name__)
    settings = get_settings()
    if not settings.deepseek_api_key:
        logger.warning("cover subject contains '%s' but no LLM key, using as-is", subject[:60])
        return subject

    system = (
        "你是一个封面提示词优化器。将输入中的'世界地图'或'地球仪'替换为视觉上等效但不出现完整地图的描述："
        "使用'深色地理示意图背景'、'区域插画背景'、'抽象地标背景'等替代方案，"
        "同时保留原句的地理位置、颜色、风格等所有其他细节。"
        "仅输出改写后的文本，不要额外解释。"
    )
    try:
        client = DeepSeekClient()
        rewritten, _ = client._chat(system, subject, max_tokens=600)
        result = rewritten.strip()
        if result and len(result) >= len(subject) * 0.3:
            logger.info("cover subject rewritten: '%s' -> '%s'", subject[:80], result[:80])
            return result
    except Exception as exc:
        logger.warning("cover subject rewrite failed: %s", exc)
    return subject


def build_cover_image_prompt(*, cw: int, ch: int, subject: str) -> str:
    """Agnes 文生图 prompt：主体居中 4:3，上方留白供后期叠标题。

    注意：若有地图内容，不得出现藏南地区、阿克赛钦地区的边界线或标注，
    以规避平台审核风险。
    """
    resolved = _resolve_cover_subject(subject)
    return (
        f"视频封面，{cw}x{ch}，画面主体居中于4:3安全区，"
        f"中间无文字无水印，4:3区域上方留白给标题。"
        f"不得出现世界地图。若涉及地图，不得出现藏南地区、阿克赛钦地区的边界线或标识。"
        f"画面内容与视频一致：{resolved}"
    )


def split_cover_title_lines(title: str, *, max_lines: int = 2) -> list[str]:
    """封面标题折行：16 字以内；冒号变空格后优先按空格分两行，否则超过 8 字均分两行。"""
    # 冒号在封面上不单独占行，转为空格以便「烛影斧声：赵匡胤…」→ 两行
    display = title.replace("：", " ").replace(":", " ").strip()
    if not display:
        return [""]
    compact = display.replace(" ", "")
    if len(compact) > COVER_TITLE_MAX_CHARS:
        compact = compact[:COVER_TITLE_MAX_CHARS]
    if " " in display:
        parts = display.split(" ", 1)
        line1 = parts[0].strip()[:COVER_TITLE_MAX_CHARS]
        line2 = (
            parts[1].strip()[: COVER_TITLE_MAX_CHARS - len(line1)]
            if len(parts) > 1
            else ""
        )
        if line2:
            return [line1, line2]
        return [line1] if line1 else [compact]
    if len(compact) <= _COVER_SINGLE_LINE_MAX:
        return [compact]
    return balance_title_lines(compact, max_lines)


def render_cover_title_block(
    title: str,
    *,
    safe_left: int,
    safe_top: int,
    safe_right: int,
    safe_bottom: int,
    is_landscape: bool,
) -> tuple[Image.Image, int, int]:
    """渲染封面黄字标题块，返回 (RGBA 图块, x, y)，整体落在 4:3 安全区内、居中偏上。"""
    safe_w = safe_right - safe_left
    safe_h = safe_bottom - safe_top
    lines = [ln for ln in split_cover_title_lines(title) if ln]
    if not lines:
        lines = [""]

    title_max_w = int(safe_w * 0.92)
    title_max_h = int(safe_h * 0.34) if is_landscape else int(safe_h * 0.24)
    # 横屏投稿封面实测：最大 135px，放不下时逐步缩小至 100px
    title_max_size = 135 if is_landscape else 120
    title_min_size = 100 if is_landscape else 96
    line_gap = 10
    font = load_cjk_font(title_min_size)
    font_size = title_min_size

    for size in range(title_max_size, title_min_size - 1, -2):
        candidate = load_cjk_font(size)
        if not all(text_bbox(line, candidate)[0] <= title_max_w for line in lines):
            continue
        total_h = sum(text_bbox(line, candidate)[1] for line in lines)
        total_h += line_gap * max(len(lines) - 1, 0)
        if total_h <= title_max_h:
            font = candidate
            font_size = size
            break

    line_gap = max(8, font_size // 12)
    rendered = [
        render_text_rgba(
            line,
            font,
            fill=_COVER_TITLE_FILL,
            stroke_width=STROKE_WIDTH + 2,
            stroke_fill=_COVER_TITLE_STROKE,
            with_shadow=True,
            shadow_blur=10,
        )
        for line in lines
    ]
    text_block = compose_vstack(rendered, gap=line_gap, align="center")

    margin = max(6, int(min(safe_w, safe_h) * 0.03))
    tx = safe_left + (safe_w - text_block.size[0]) // 2
    # 垂直锚点：4:3 安全区从上往下 36% 处居中（偏上，避开品牌与讲解人）
    center_y = safe_top + int(safe_h * 0.36)
    ty = center_y - text_block.size[1] // 2
    tx = max(safe_left + margin, min(tx, safe_right - margin - text_block.size[0]))
    ty = max(safe_top + margin, min(ty, safe_bottom - margin - text_block.size[1]))
    return text_block, tx, ty


def compose_cover_image(
    img: Image.Image,
    title: str,
    *,
    brand_name: str,
    host_intro_path: Path,
) -> Image.Image:
    """在封面底图上叠加讲解人、品牌与标题（流水线与 debug 共用）。"""
    canvas = img.convert("RGBA")
    cw, ch = canvas.size
    is_landscape = cw > ch
    # 横屏只露出讲解人上半身，竖屏全身；与片头 host_visible_fraction 一致
    host_visible = 0.58 if is_landscape else 1.0
    safe_left, safe_top, safe_right, safe_bottom = central_43_bounds(cw, ch)
    safe_w = safe_right - safe_left

    host = Image.open(host_intro_path).convert("RGBA")
    max_w = int(cw * (0.72 if is_landscape else 0.94))
    max_h = int(ch * (0.88 if is_landscape else 0.42))
    shrink = min(1.0, max_w / host.size[0], max_h / host.size[1])
    host = host.resize(
        (int(host.size[0] * shrink), int(host.size[1] * shrink)),
        Image.Resampling.LANCZOS,
    )
    hx = (cw - host.size[0]) // 2
    hy = ch - int(host.size[1] * host_visible) if host_visible < 1.0 else ch - host.size[1]
    canvas.paste(host, (hx, hy), host)

    brand_font = load_cjk_font(max(24, int(72 * ch / 1080)))
    brand = render_text_rgba(
        brand_name,
        brand_font,
        fill=(255, 255, 255, 255),
        stroke_width=3,
        stroke_fill=(60, 30, 15, 255),
    )
    brand_x = safe_left + (safe_w - brand.size[0]) // 2
    # 品牌名对齐 4:3 顶边，而非全画布顶边
    canvas.paste(brand, (brand_x, int(ch * 0.04)), brand)

    text_block, tx, ty = render_cover_title_block(
        title,
        safe_left=safe_left,
        safe_top=safe_top,
        safe_right=safe_right,
        safe_bottom=safe_bottom,
        is_landscape=is_landscape,
    )
    canvas.paste(text_block, (tx, ty), text_block)
    return canvas
