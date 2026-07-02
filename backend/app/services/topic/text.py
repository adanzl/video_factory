"""选题标题文本规范化。"""

from __future__ import annotations

import re


def normalize_title(title: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_len + 2:
        return cleaned
    truncated = cleaned[:max_len]
    for punct in ("。", "！", "？", "，", "——"):
        idx = truncated.rfind(punct)
        if idx >= max_len // 2:
            return truncated[:idx]
    return cleaned[:max_len]
