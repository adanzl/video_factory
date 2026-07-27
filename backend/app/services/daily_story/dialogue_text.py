"""日常故事对白字数与截断（供 prompts 与 story_types 共用）。"""

from __future__ import annotations

DAILY_STORY_LINE_CHARS_MAX = 22


def dialogue_char_count(line: str) -> int:
    """与成片时长估算一致：按台词字符串长度计。"""
    return len(line or "")


def truncate_overlong_line(
    line: str,
    *,
    max_chars: int = DAILY_STORY_LINE_CHARS_MAX,
) -> str:
    limit = max_chars
    cut = -1
    for i, ch in enumerate(line):
        if i >= limit:
            break
        if ch in "，、；; ":
            cut = i
    if cut >= 6:
        return line[:cut].rstrip("，、；; ")
    return line[:limit]
