"""J 类好笑维：否决权、哀求无效、镇住收场。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.j.validate import (
    RE_HOLD,
    RE_PLEAD,
    RE_SURRENDER,
    RE_VETO,
)

RE_MOM_USELESS = re.compile(r"妈妈.*没用|答应没用|妈妈都答应")
RE_REPEAT_VETO = re.compile(r"我说了算|不行就不行|我说不行")


def collect_j_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 8:
        return issues
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_PLEAD.search(body):
        issues.append("J缺求放行/试探")
    if not RE_VETO.search(body):
        issues.append("J缺否决压住")
    if not RE_SURRENDER.search(body):
        issues.append("J缺对方怂退")
    if not RE_HOLD.search(tail4):
        issues.append("J末段缺镇住收场")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """J 好笑维：妈妈同意无效、反复否决、哀求加码。"""
    del speakers
    if len(lines) < 8:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_MOM_USELESS.search(body):
        pts += 4
        pros.append("妈妈同意无效反差")
    plead_hits = len(RE_PLEAD.findall(body))
    if plead_hits >= 2:
        pts += 2
        pros.append("哀求加码")
    veto_hits = len(RE_REPEAT_VETO.findall(body))
    if veto_hits >= 2:
        pts += 2
        pros.append("反复否决")
    if RE_SURRENDER.search(body) and RE_HOLD.search(tail):
        pts += 2
        pros.append("镇住收场")

    return min(pts, 10), pros
