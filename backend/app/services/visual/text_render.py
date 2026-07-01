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


_EDGE_STRIP_PUNCT = re.compile(
    r'^[。！？；：，,.!?;:"]+|[。！？；：，,.!?;:"]+$'
)
# 分条断点：顿号、书名号《》〈〉、各类括号不分割，保留在句内
_SUBTITLE_SPLIT_PUNCT = re.compile(
    r'[。！？；：，,.!?;:"]+'
)


def balance_title_lines(text: str, max_lines: int) -> list[str]:
    """将过长标题均分为最多 max_lines 行（仅当自然折行仍超行数时使用）。"""
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


_OPEN_BRACKETS = frozenset('『「（([{《〈【“‘')
_CLOSE_BRACKETS = frozenset('』」）)]}》〉】”’')
_BRACKET_PAIRS = {'『': '』', '「': '」', '（': '）', '(': ')', '[': ']', '{': '}',
                  '《': '》', '〈': '〉', '【': '】', '“': '”', '‘': '’'}
_TOGGLE_QUOTES = frozenset('"\'')
_PHRASE_MERGE_SENTENCE_END = frozenset("。！？!?")
MIN_PHRASE_DISPLAY_LEN = 6


def phrase_display_text(tts_text: str) -> str:
    """字幕展示：仅去掉首尾句读标点，中间逗号/冒号等保留。"""
    text = tts_text.strip()
    return _EDGE_STRIP_PUNCT.sub("", text).strip()


def _merge_phrase_pair(
    left: tuple[str, str],
    right: tuple[str, str],
) -> tuple[str, str]:
    tts = left[0] + right[0]
    return (tts, phrase_display_text(tts))


def _phrase_merge_complete(tts: str, display: str) -> bool:
    """短句已到自然语气边界（如「哇，你知道吗？」）则不再向后合并。"""
    stripped = tts.rstrip()
    return (
        bool(stripped)
        and stripped[-1] in _PHRASE_MERGE_SENTENCE_END
        and len(display) >= 5
    )


def merge_short_phrase_chunks(
    chunks: list[tuple[str, str]],
    *,
    min_display_len: int = MIN_PHRASE_DISPLAY_LEN,
) -> list[tuple[str, str]]:
    """过短字幕条与相邻条合并，避免「哇」「你看」等单独成条。"""
    if len(chunks) <= 1:
        return chunks

    result = list(chunks)
    changed = True
    while changed:
        changed = False
        index = 0
        while index < len(result):
            tts, display = result[index]
            if len(display) >= min_display_len or _phrase_merge_complete(tts, display):
                index += 1
                continue
            if index + 1 < len(result):
                result[index] = _merge_phrase_pair(result[index], result[index + 1])
                del result[index + 1]
                changed = True
                continue
            if index > 0:
                result[index - 1] = _merge_phrase_pair(result[index - 1], result[index])
                del result[index]
                changed = True
                index -= 1
                continue
            index += 1
    return result


def split_phrase_chunks(text: str) -> list[tuple[str, str]]:
    """按标点分条，引号/括号内的内容不拆分。"""
    text = text.strip()
    if not text:
        return []

    tokens = re.split(
        r'([。！？；：，,.!?;:…—·—－~～\'"]+)',
        text,
    )
    chunks: list[tuple[str, str]] = []
    buf = ""
    bracket_depth = 0
    in_double_quote = False
    in_single_quote = False

    for token in tokens:
        if not token:
            continue
        for ch in token:
            if ch in _OPEN_BRACKETS:
                bracket_depth += 1
                matched_close = _BRACKET_PAIRS.get(ch)
            elif ch in _CLOSE_BRACKETS:
                bracket_depth = max(0, bracket_depth - 1)
            elif ch == '"':
                in_double_quote = not in_double_quote
            elif ch == "'":
                in_single_quote = not in_single_quote
            buf += ch

        has_punct = _SUBTITLE_SPLIT_PUNCT.fullmatch(token)
        if has_punct and bracket_depth == 0 and not in_double_quote and not in_single_quote:
            tts = buf.strip()
            display = phrase_display_text(tts)
            if display:
                chunks.append((tts, display))
            buf = ""

    if buf.strip():
        tts = buf.strip()
        display = phrase_display_text(tts)
        if display:
            chunks.append((tts, display))
        elif chunks:
            prev_text, _ = chunks[-1]
            merged_tts = prev_text + buf
            chunks[-1] = (merged_tts, phrase_display_text(merged_tts))
    return merge_short_phrase_chunks(chunks)


def split_subtitle_phrases(text: str) -> list[str]:
    """按标点分条，字幕展示用（仅去首尾句读标点，中间保留）。"""
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
