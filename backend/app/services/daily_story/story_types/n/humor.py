"""N 类好笑维：设问、荒诞自洽、愣住。"""

from __future__ import annotations

from app.services.daily_story.story_types.n.validate import (
    RE_CHALLENGE,
    RE_SOLEMN_REASON,
    RE_STUN_CLOSE,
    RE_WHY,
)


def collect_n_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    if not RE_CHALLENGE.search(body):
        issues.append("N缺设问/考验")
    if not RE_WHY.search(body):
        issues.append("N缺追问")
    if not RE_SOLEMN_REASON.search(body):
        issues.append("N缺一本正经自洽")
    if not RE_STUN_CLOSE.search(body) and not RE_STUN_CLOSE.search(tail6):
        issues.append("N缺愣住收束")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """N 好笑维：离谱答被追问后一本正经自洽噎住。"""
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_CHALLENGE.search(body) and RE_WHY.search(body):
        pts += 3
        pros.append("设问追问链")
    elif RE_WHY.search(body):
        pts += 1
        pros.append("有追问")

    if RE_SOLEMN_REASON.search(body):
        pts += 4
        pros.append("一本正经自洽")

    if RE_STUN_CLOSE.search(tail) or RE_STUN_CLOSE.search(body):
        pts += 3
        pros.append("愣住收束")

    return min(pts, 10), pros
