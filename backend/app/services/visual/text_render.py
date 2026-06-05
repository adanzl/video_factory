"""中文文字渲染工具：项目字体加载与自动换行。"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import ImageFont

from app.config import get_settings

_TRAILING_PUNCTUATION = frozenset("？。！，、；：\"'”）】》")


def _try_load_font(
    path: Path | str,
    size: int,
    *,
    index: int | None = None,
) -> ImageFont.FreeTypeFont | None:
    font_path = Path(path)
    if index is not None:
        try:
            return ImageFont.truetype(str(font_path), size, index=index)
        except OSError:
            return None
    if font_path.suffix.lower() == ".ttc":
        for face_index in range(4):
            try:
                return ImageFont.truetype(str(font_path), size, index=face_index)
            except OSError:
                continue
        return None
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        return None


def _font_candidate_paths() -> list[Path]:
    settings = get_settings()
    paths: list[Path] = [settings.font_path]
    font_dir = settings.res_dir / "font"
    if font_dir.is_dir():
        for pattern in ("*.otf", "*.ttf", "*.ttc"):
            for path in sorted(font_dir.glob(pattern)):
                if path not in paths:
                    paths.append(path)
    return paths


def load_cjk_font(size: int) -> ImageFont.FreeTypeFont:
    """加载 backend/res/font 下的项目字体。"""
    for path in _font_candidate_paths():
        font = _try_load_font(path, size)
        if font is not None:
            return font
    settings = get_settings()
    raise FileNotFoundError(
        f"无法加载中文字体，请将字体放入 {settings.res_dir / 'font'} "
        f"或设置 FONT_PATH（当前: {settings.font_path}）",
    )


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """按像素宽度自动换行（逐字测量，适配中英文混排）。"""
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if font.getlength(trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)

    if (
        len(lines) >= 2
        and len(lines[-1]) <= 2
        and all(c in _TRAILING_PUNCTUATION for c in lines[-1])
    ):
        lines[-2] += lines[-1]
        lines.pop()

    return lines or [text]


_SENTENCE_END = frozenset("。！？!?；;")


_SUBTITLE_SPLIT_PUNCT = re.compile(
    r'[。！？；：，、,.!?;:…—·「」『』【】（）()\[\]{}《》〈〉—－~～\'"]+'
)


def balance_title_lines(text: str, max_lines: int) -> list[str]:
    """将标题均分为最多 max_lines 行，避免末行只剩一两个字。"""
    normalized = text.strip()
    if not normalized or max_lines <= 1:
        return [normalized] if normalized else []
    if len(normalized) <= max_lines:
        return [normalized]
    n = len(normalized)
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


def split_phrase_chunks(text: str) -> list[tuple[str, str]]:
    """按标点分条，返回 (TTS 文本含标点, 字幕文本无标点)。"""
    text = text.strip()
    if not text:
        return []

    tokens = re.split(
        r'([。！？；：，、,.!?;:…—·「」『』【】（）()\[\]{}《》〈〉—－~～\'"]+)',
        text,
    )
    chunks: list[tuple[str, str]] = []
    buf = ""
    for token in tokens:
        if not token:
            continue
        if _SUBTITLE_SPLIT_PUNCT.fullmatch(token):
            buf += token
            display = _SUBTITLE_SPLIT_PUNCT.sub("", buf).strip()
            if display:
                chunks.append((buf.strip(), display))
            buf = ""
        else:
            buf += token
    if buf.strip():
        display = _SUBTITLE_SPLIT_PUNCT.sub("", buf).strip()
        if display:
            chunks.append((buf.strip(), display))
    return chunks


def split_subtitle_phrases(text: str) -> list[str]:
    """按标点分条，字幕展示用（不含标点）。"""
    return [display for _, display in split_phrase_chunks(text)]


def split_sentences(text: str) -> list[str]:
    """兼容旧逻辑：按句末标点断句（保留标点）。"""
    text = text.strip()
    if not text:
        return []
    sentences: list[str] = []
    buf = ""
    for char in text:
        buf += char
        if char in _SENTENCE_END:
            sentence = buf.strip()
            if sentence:
                sentences.append(sentence)
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())
    return sentences
