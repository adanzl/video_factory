"""N 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.n.validate import (
    RE_SOLEMN_REASON,
    RE_STUN_CLOSE,
    RE_WHY,
)

_N_CLOSING_TAIL_ALLOW = 2
_RE_SECOND_ROUND = re.compile(
    r"那我再问|再说一遍|你听清楚|不对不对|重新选|再选一次"
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


def patch_n_ensure_solemn_reason(story: dict) -> list[str]:
    """追问后已有回答但缺因果连接词时，只显式化原回答，不编新理由。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    body = "".join(_dialogue_lines(story))
    if RE_SOLEMN_REASON.search(body):
        return []

    for why_idx, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        why_line = str(item.get("line") or "").strip()
        if not RE_WHY.search(why_line):
            continue
        why_speaker = str(item.get("speaker") or "").strip()
        # 只看紧随追问的局部回答窗；遇到愣住收束即停止，避免改成「因为行吧」。
        for answer_idx in range(why_idx + 1, min(len(dialogue), why_idx + 4)):
            answer = dialogue[answer_idx]
            if not isinstance(answer, dict):
                continue
            line = str(answer.get("line") or "").strip()
            if not line:
                continue
            if RE_STUN_CLOSE.search(line):
                break
            speaker = str(answer.get("speaker") or "").strip()
            if why_speaker and speaker == why_speaker:
                continue
            if RE_WHY.search(line) or line.endswith(("？", "?")):
                continue
            answer["line"] = f"因为{line}"
            return [f"N追问后补自洽连接词第{answer_idx + 1}句"]
        break
    return []


def patch_n_trim_after_stun(story: dict) -> list[str]:
    """荒诞自洽/愣住落位后删第二轮抬杠拖尾。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    stun = [i for i, ln in enumerate(lines) if RE_STUN_CLOSE.search(ln)]
    reason = [i for i, ln in enumerate(lines) if RE_SOLEMN_REASON.search(ln)]
    if not stun and not reason:
        return notes
    close_idx = stun[-1] if stun else reason[-1]
    min_keep = close_idx + 1 + _N_CLOSING_TAIL_ALLOW
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
        notes.append(f"N愣住后剔除第二轮拖尾{removed}句")
    return notes


def patch_n_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "N":
        return notes
    notes.extend(patch_n_ensure_solemn_reason(story))
    notes.extend(patch_n_trim_after_stun(story))
    return notes
