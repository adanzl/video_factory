"""F 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

_RE_FILLER_TAIL = re.compile(
    r"(好不好呀?|真的呀|着呢呀?|你听着呀|吧呀|呢呀)+$",
)
_RE_FILLER_INLINE = re.compile(r"(好不好呀|真的呀|着呢)")
_RE_BROKEN_EXCLAIM = re.compile(r"啊{2,}了啊")
_RE_BROKEN_AH = re.compile(r"啊什么了啊")


def _is_f(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "F"


def patch_f_strip_filler(story: dict) -> list[str]:
    """剥句尾语气垫字（与 B 垫字补 min 共用场景）。"""
    notes: list[str] = []
    if not _is_f(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = line
        if _RE_BROKEN_EXCLAIM.search(new_line):
            new_line = _RE_BROKEN_EXCLAIM.sub("啊啊啊", new_line)
        if _RE_BROKEN_AH.search(new_line):
            new_line = _RE_BROKEN_AH.sub("啊什么啊", new_line)
        new_line = _RE_FILLER_INLINE.sub("", new_line)
        new_line = _RE_FILLER_TAIL.sub("", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"F剥垫字[{i}]")
    return notes


def patch_f_punchline_prefix(story: dict) -> list[str]:
    """gold_chat：punchline_explain 补 F类 前缀（机读结构分）。"""
    if not _is_f(story):
        return []
    explain = str(story.get("punchline_explain") or "").strip()
    if not explain or explain.startswith("F类"):
        return []
    story["punchline_explain"] = f"F类：{explain}"
    return ["F punchline→F类"]


def patch_f_body(story: dict) -> list[str]:
    notes = patch_f_strip_filler(story)
    notes.extend(patch_f_punchline_prefix(story))
    return notes
