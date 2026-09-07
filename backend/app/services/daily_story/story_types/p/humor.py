"""P 类好笑维：下料、回敬、认怂。"""

from __future__ import annotations

from app.services.daily_story.story_types.p.validate import (
    RE_BRACE_OR_HIT,
    RE_OFFER,
    RE_RETALIATE,
    RE_SURRENDER,
)


def collect_p_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_OFFER.search(body):
        issues.append("P缺下料/挑战")
    if not RE_RETALIATE.search(body) and not RE_BRACE_OR_HIT.search(body):
        issues.append("P缺硬撑或回敬")
    if not RE_SURRENDER.search(tail4) and not RE_SURRENDER.search(body):
        issues.append("P缺认怂收束")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """P 好笑维：回敬加码后认怂。"""
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_OFFER.search(body):
        pts += 2
        pros.append("有下料挑战")
    if RE_RETALIATE.search(body):
        pts += 4
        pros.append("回敬加码")
    elif RE_BRACE_OR_HIT.search(body):
        pts += 2
        pros.append("有硬撑/中招")
    if RE_SURRENDER.search(tail) or RE_SURRENDER.search(body):
        pts += 3
        pros.append("认怂散场")

    return min(pts, 10), pros
