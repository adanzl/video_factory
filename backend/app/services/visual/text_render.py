"""中文文字渲染工具：项目字体加载与自动换行。"""

from __future__ import annotations

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


def split_sentences(text: str) -> list[str]:
    """按句末标点断句。"""
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

