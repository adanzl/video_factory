"""Q 类好笑维：耍赖、拆穿、反噬。"""

from __future__ import annotations

from app.services.daily_story.story_types.q.validate import (
    RE_BACKFIRE,
    RE_CHEAT,
    RE_EXPOSE,
)


def collect_q_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_CHEAT.search(body):
        issues.append("Q缺耍赖/借口加码")
    if not RE_EXPOSE.search(body):
        issues.append("Q缺拆穿")
    if not RE_BACKFIRE.search(tail4) and not RE_BACKFIRE.search(body):
        issues.append("Q缺反噬收束")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_CHEAT.search(body):
        pts += 2
        pros.append("有耍赖加码")
    if RE_EXPOSE.search(body):
        pts += 4
        pros.append("有拆穿")
    if RE_BACKFIRE.search(tail) or RE_BACKFIRE.search(body):
        pts += 3
        pros.append("反噬收场")

    return min(pts, 10), pros
