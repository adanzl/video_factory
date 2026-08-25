"""I 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.i.validate import RE_WIN_STUBBORN

_I_CLOSING_TAIL_ALLOW = 2
_RE_SUBPLOT_TAIL = re.compile(r"写作业|监督|偷懒|才公平|公平吧|你也得写")
_RE_INDOOR_SETTING = re.compile(r"卧室|客厅|厨房|餐厅|书桌|餐桌|沙发")
_RE_UNNATURAL_WIN = re.compile(r"一招制敌|服不服|制敌")


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
    """pass2：仅从末段剔除作业监督等 subplot，保留收束句与篇幅。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    win_indices = [i for i, ln in enumerate(lines) if RE_WIN_STUBBORN.search(ln)]
    if not win_indices:
        return notes
    win_idx = win_indices[-1]
    min_keep = win_idx + 1 + _I_CLOSING_TAIL_ALLOW
    removed = 0
    while len(dialogue) > min_keep:
        tail_line = str(dialogue[-1].get("line") or "") if isinstance(dialogue[-1], dict) else ""
        if not _RE_SUBPLOT_TAIL.search(tail_line):
            break
        dialogue.pop()
        removed += 1
    if removed:
        story["dialogue"] = dialogue
        notes.append(f"I收束拖尾剔除subplot {removed}句")
    return notes


def _naturalize_win_line(line: str, *, body: str = "") -> str:
    """金稿 seed/标题常带 narration 词，改写成姐弟现场嘴硬得意。"""
    if not _RE_UNNATURAL_WIN.search(line):
        return line
    ctx = body or line
    if re.search(r"爱学习|你爱吗|灵魂|拷问", ctx):
        return "好了，不爱学习还跟我吵啥！"
    if re.search(r"还说|相同|一样|凭啥", ctx):
        return "哼，看你还说啥！"
    return "哼，看你还嘴硬！"


def patch_i_naturalize_win_line(story: dict) -> list[str]:
    """pass2：赢家收束去 narration/meta，改姐弟口语；punchline_explain 不动。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return notes
    lines = _dialogue_lines(story)
    win_indices = [i for i, ln in enumerate(lines) if RE_WIN_STUBBORN.search(ln)]
    if not win_indices:
        win_indices = [
            i
            for i, ln in enumerate(lines)
            if _RE_UNNATURAL_WIN.search(ln)
        ]
    if not win_indices:
        return notes
    win_idx = win_indices[-1]
    item = dialogue[win_idx]
    if not isinstance(item, dict):
        return notes
    old = str(item.get("line") or "").strip()
    body = "".join(lines[: win_idx + 1])
    new = _naturalize_win_line(old, body=body)
    if new != old:
        item["line"] = new
        notes.append("I收束句改口语")
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
    notes.extend(patch_i_naturalize_win_line(story))
    notes.extend(patch_i_indoor_dialogue(story))
    return notes
