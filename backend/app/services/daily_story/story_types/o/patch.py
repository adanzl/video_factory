"""O 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.o.validate import RE_GOAL_PUNCH

_O_CLOSING_TAIL_ALLOW = 2
_RE_SECOND_ROUND = re.compile(
    r"那不算|重新猜|再比一次|你刚说|凭什么|归谁|公平"
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


def patch_o_trim_after_punch(story: dict) -> list[str]:
    """点题认栽后删双规则/再赛第二轮拖尾。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    punch = [i for i, ln in enumerate(lines) if RE_GOAL_PUNCH.search(ln)]
    if not punch:
        return notes
    close_idx = punch[-1]
    min_keep = close_idx + 1 + _O_CLOSING_TAIL_ALLOW
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
        notes.append(f"O点题后剔除第二轮拖尾{removed}句")
    return notes


def patch_o_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "O":
        return notes
    notes.extend(patch_o_trim_after_punch(story))
    return notes
