"""I 类好笑维：灵魂拷问、语塞、一招制敌。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.i.validate import (
    RE_SOUL_QUESTION,
    RE_SPEECHLESS,
    RE_WIN_STUBBORN,
)

RE_BANTER = re.compile(r"少来|哼|凭啥|转移|更爱你|哭哭啼啼|咋不")
RE_DOUBLE_STANDARD = re.compile(r"学习.*玩|玩.*学习|写作业|催")


def collect_i_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    if not RE_SOUL_QUESTION.search(body):
        issues.append("I缺灵魂拷问/价值高地")
    if not RE_SPEECHLESS.search(body):
        issues.append("I缺对方语塞")
    has_win = bool(RE_WIN_STUBBORN.search(tail6))
    has_surrender = bool(re.search(r"服了|行了吧|听你的", tail6))
    if not has_win and not (RE_SPEECHLESS.search(tail6) and has_surrender):
        issues.append("I末段缺赢家一招制敌")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """I 好笑维：拷问反差、双标回击、语塞败北。"""
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_SOUL_QUESTION.search(body):
        pts += 3
        pros.append("灵魂拷问有梗")
    if RE_DOUBLE_STANDARD.search(body):
        pts += 3
        pros.append("双标回击")
    if RE_SPEECHLESS.search(body):
        pts += 2
        pros.append("语塞反差")

    banter_hits = len(RE_BANTER.findall(body))
    if banter_hits >= 2:
        pts += 2
        pros.append("互怼有梗")
    elif banter_hits >= 1:
        pts += 1
        pros.append("有互怼")

    if RE_WIN_STUBBORN.search(tail):
        pts += 2
        pros.append("一招制敌收束")

    return min(pts, 10), pros
