"""I 类正文硬卡（灵魂拷问 + 语塞 + 一招制敌）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_SOUL_QUESTION = re.compile(r"爱学习|你爱吗|灵魂|拷问|凭啥|相同|为啥")
RE_SPEECHLESS = re.compile(r"说不过|语塞|哑口|不说了|看窗外|憋不出|张了张嘴")
RE_WIN_STUBBORN = re.compile(
    r"一招制敌|制敌|服不服|别跟我吵|不爱学习还|不爱学习就别|看你还说|还说啥|嘴硬"
)
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")


def _lines_and_speakers(story: dict) -> tuple[list[str], list[str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], []
    lines: list[str] = []
    speakers: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if not ln:
            continue
        speakers.append(sp)
        lines.append(ln)
    return lines, speakers


def append_i_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "I":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_SOUL_QUESTION.search(body):
        errors.append("I类：正文须有灵魂拷问/价值高地（你爱吗/爱学习等）")
    if not RE_SPEECHLESS.search(body):
        errors.append("I类：正文须写对方语塞/败北（说不过/看窗外等）")
    if not RE_WIN_STUBBORN.search(tail4):
        errors.append("I类：末段须赢家一招制敌（制敌/服不服等）")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("I类：末段勿 A 式反噬/破功链")
