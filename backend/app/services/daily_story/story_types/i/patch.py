"""I 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.i.validate import (
    RE_SPEECHLESS,
    RE_WIN_STUBBORN,
)

_I_CLOSING_TAIL_ALLOW = 1
_RE_INDOOR_SETTING = re.compile(r"卧室|客厅|厨房|餐厅|书桌|餐桌|沙发")
_RE_I_SURRENDER = re.compile(r"服了|我这就去|这就去写|行了吧|听你的|真的呀.*写")
_ORAL_WIN_LINE = "看你还嘴硬！"


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def _find_i_close_index(lines: list[str]) -> int:
    speechless_seen = False
    for i, ln in enumerate(lines):
        if RE_SPEECHLESS.search(ln):
            speechless_seen = True
        if RE_WIN_STUBBORN.search(ln):
            return i
        if speechless_seen and _RE_I_SURRENDER.search(ln):
            return i
    return -1


def _ensure_oral_win_at_end(story: dict, winner: str) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return notes
    lines = _dialogue_lines(story)
    if RE_WIN_STUBBORN.search("".join(lines[-4:])):
        return notes
    sp = winner or "昭昭"
    last = dialogue[-1] if isinstance(dialogue[-1], dict) else None
    if last and str(last.get("speaker") or "").strip() == sp:
        last["line"] = _ORAL_WIN_LINE
        notes.append("I末句补口语制敌")
    else:
        dialogue.append({"speaker": sp, "line": _ORAL_WIN_LINE})
        notes.append("I补末句口语制敌")
    story["dialogue"] = dialogue
    return notes


def patch_i_trim_trailing_subplot(story: dict) -> list[str]:
    """语塞后首次服软/制敌即收束；其后第二轮一律裁掉。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes

    lines = _dialogue_lines(story)
    close_idx = _find_i_close_index(lines)
    if close_idx < 0:
        return notes

    trailing = len(lines) - close_idx - 1
    if trailing <= _I_CLOSING_TAIL_ALLOW and RE_WIN_STUBBORN.search(
        "".join(lines[-4:])
    ):
        return notes

    winner = ""
    for i, ln in enumerate(lines):
        if RE_WIN_STUBBORN.search(ln) and isinstance(dialogue[i], dict):
            winner = str(dialogue[i].get("speaker") or "").strip()
    if not winner:
        for i in range(close_idx, -1, -1):
            if not isinstance(dialogue[i], dict):
                continue
            sp = str(dialogue[i].get("speaker") or "").strip()
            ln = str(dialogue[i].get("line") or "")
            if sp in ("昭昭", "灿灿") and not _RE_I_SURRENDER.search(ln):
                winner = sp
                break

    min_keep = close_idx + 1 + _I_CLOSING_TAIL_ALLOW
    if len(dialogue) > min_keep:
        removed = len(dialogue) - min_keep
        story["dialogue"] = [x for x in dialogue[:min_keep] if isinstance(x, dict)]
        notes.append(f"I首次收束后裁拖尾 {removed}句")

    notes.extend(_ensure_oral_win_at_end(story, winner))
    return notes


def patch_i_strip_meta_type_labels(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "一招制敌" not in line and "问倒你" not in line:
            continue
        new = (
            line.replace("一招制敌，", "")
            .replace("一招制敌", "")
            .replace("问倒你", "看你还嘴硬")
        )
        new = re.sub(r"[，,]{2,}", "，", new).strip("，、 ")
        if not new or not RE_WIN_STUBBORN.search(new):
            new = _ORAL_WIN_LINE
        if new != line:
            item["line"] = new
            notes.append("I去类型标签自指")
    return notes


def patch_i_indoor_dialogue(story: dict) -> list[str]:
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
    notes.extend(patch_i_strip_meta_type_labels(story))
    notes.extend(patch_i_indoor_dialogue(story))
    return notes
