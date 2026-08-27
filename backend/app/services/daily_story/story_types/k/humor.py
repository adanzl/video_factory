"""K 类好笑维：越劝越凶、大人看戏、僵持不和好。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.k.validate import (
    RE_FIGHT,
    RE_PARENT_FAIL,
    RE_STALEMATE,
)

RE_BANTER = re.compile(r"哼|滚|讨厌|谁怕|别理|越劝越|看戏|管不着")


def collect_k_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 8:
        return issues
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_FIGHT.search(body):
        issues.append("K缺互骂升级")
    if not RE_PARENT_FAIL.search(body):
        issues.append("K缺大人劝失败")
    if not RE_STALEMATE.search(tail4):
        issues.append("K末段缺僵持不和好")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """K 好笑维：大人劝不动、越劝越凶、僵持收场。"""
    del speakers
    if len(lines) < 8:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_PARENT_FAIL.search(body) and RE_FIGHT.search(body):
        pts += 4
        pros.append("大人劝失败反差")
    if "越劝越" in body:
        pts += 2
        pros.append("越劝越凶")
    if RE_STALEMATE.search(tail):
        pts += 2
        pros.append("僵持收场")

    banter_hits = len(RE_BANTER.findall(body))
    if banter_hits >= 2:
        pts += 2
        pros.append("互骂有梗")

    return min(pts, 10), pros
