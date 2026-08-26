"""L 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.l.validate import RE_BIAS_EXPOSE, RE_REFUSE

_L_CLOSING_TAIL_ALLOW = 2
_RE_SECOND_ROUND = re.compile(
    r"那我现在想|一会儿要|一会儿不要|你给不给|我就要喝|我就要吃"
)


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def patch_l_trim_after_expose(story: dict) -> list[str]:
    """点破/拒收落位后删第二轮要/不要拖尾。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    close_indices = [
        i
        for i, ln in enumerate(lines)
        if RE_BIAS_EXPOSE.search(ln) or RE_REFUSE.search(ln)
    ]
    if not close_indices:
        return notes
    # 取首次「拒收后点破」一带：优先最后一次点破
    expose = [i for i, ln in enumerate(lines) if RE_BIAS_EXPOSE.search(ln)]
    close_idx = expose[-1] if expose else close_indices[-1]
    min_keep = close_idx + 1 + _L_CLOSING_TAIL_ALLOW
    removed = 0
    while len(dialogue) > min_keep:
        tail_line = (
            str(dialogue[-1].get("line") or "")
            if isinstance(dialogue[-1], dict)
            else ""
        )
        if not _RE_SECOND_ROUND.search(tail_line):
            break
        dialogue.pop()
        removed += 1
    if removed:
        story["dialogue"] = dialogue
        notes.append(f"L点破后剔除第二轮拖尾{removed}句")
    return notes


def patch_l_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "L":
        return notes
    notes.extend(patch_l_trim_after_expose(story))
    return notes
