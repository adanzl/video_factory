"""O 类好笑维：死磕过程、资源溜走、点题认栽。"""

from __future__ import annotations

from app.services.daily_story.story_types.o.validate import (
    RE_GAME_RULE,
    RE_GOAL_PUNCH,
    RE_PRIZE_GONE,
    RE_PROCESS_FOCUS,
)


def collect_o_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    if not RE_GAME_RULE.search(body) and not RE_PROCESS_FOCUS.search(body):
        issues.append("O缺立赛规/死磕过程")
    if not RE_PRIZE_GONE.search(body):
        issues.append("O缺资源溜走")
    if not RE_GOAL_PUNCH.search(body) and not RE_GOAL_PUNCH.search(tail6):
        issues.append("O缺点题认栽")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """O 好笑维：死磕赢赛后发现目标没了。"""
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_GAME_RULE.search(body) and RE_PROCESS_FOCUS.search(body):
        pts += 3
        pros.append("立规死磕过程")
    elif RE_PROCESS_FOCUS.search(body):
        pts += 1
        pros.append("有死磕过程")

    if RE_PRIZE_GONE.search(body):
        pts += 4
        pros.append("资源溜走")

    if RE_GOAL_PUNCH.search(tail) or RE_GOAL_PUNCH.search(body):
        pts += 3
        pros.append("点题认栽")

    return min(pts, 10), pros
