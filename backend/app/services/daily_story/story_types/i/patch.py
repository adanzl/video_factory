"""I 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.i.validate import RE_WIN_STUBBORN

_I_CLOSING_TAIL_ALLOW = 2
_RE_SUBPLOT_TAIL = re.compile(r"写作业|监督|偷懒|才公平|公平吧|光嘴上说")
_RE_INDOOR_SETTING = re.compile(r"卧室|客厅|厨房|餐厅|书桌|餐桌|沙发")


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def patch_i_trim_trailing_subplot(story: dict) -> list[str]:
    """pass2 补刀：一招制敌/语塞收束后裁掉作业监督等拖尾 subplot。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    win_indices = [i for i, ln in enumerate(lines) if RE_WIN_STUBBORN.search(ln)]
    if not win_indices:
        return notes
    win_idx = win_indices[-1]
    max_keep = win_idx + 1 + _I_CLOSING_TAIL_ALLOW
    if len(dialogue) <= max_keep:
        return notes

    tail_lines = lines[max_keep:]
    if not any(_RE_SUBPLOT_TAIL.search(ln) for ln in tail_lines):
        return notes

    story["dialogue"] = dialogue[:max_keep]
    notes.append(f"I收束拖尾已裁至{max_keep}句")
    return notes


def patch_i_indoor_dialogue(story: dict) -> list[str]:
    """室内 setting 时「看窗外」改为可拍反应。"""
    notes: list[str] = []
    setting = str(story.get("setting") or "")
    if not _RE_INDOOR_SETTING.search(setting):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "看窗外" not in line:
            continue
        item["line"] = (
            line.replace("看窗外还不行", "别说了还不行")
            .replace("看窗外", "别说了")
        )
        notes.append("I室内场景：看窗外→别说了")
    return notes


def patch_i_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "I":
        return notes
    notes.extend(patch_i_trim_trailing_subplot(story))
    notes.extend(patch_i_indoor_dialogue(story))
    return notes
