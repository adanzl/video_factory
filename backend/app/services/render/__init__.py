"""排版与字幕样式：文字渲染、标题样式、字幕规格。"""

from app.services.render.subtitle_style import subtitle_style_for_canvas
from app.services.render.text_render import load_cjk_font, split_phrase_chunks, wrap_text
from app.services.render.title_render import STROKE_WIDTH, render_text_rgba

__all__ = [
    "STROKE_WIDTH",
    "load_cjk_font",
    "render_text_rgba",
    "split_phrase_chunks",
    "subtitle_style_for_canvas",
    "wrap_text",
]
