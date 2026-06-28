"""标题文本：标点保留与等价比较。"""

from __future__ import annotations

import re

_TITLE_PUNCT_RE = re.compile(
    r'[\s:：?？!！,，;；·《》「」【】()（）\-"\'""]+'
)


def title_core(text: str) -> str:
    """去掉空白与常见标点后比较标题主干。"""
    return _TITLE_PUNCT_RE.sub("", text.strip())


def collapse_title_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def prefer_source_punctuation(source: str, optimized: str) -> str:
    """优化若仅改标点/空白，保留来源标题（含冒号等）。"""
    src = collapse_title_whitespace(source)
    opt = collapse_title_whitespace(optimized)
    if not src:
        return opt
    if not opt:
        return src
    if title_core(src) != title_core(opt):
        return opt
    return src if len(src) >= len(opt) else opt
