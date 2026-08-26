"""L 类好笑维：催让、拒收、点破偏心。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.l.validate import (
    RE_BIAS_EXPOSE,
    RE_REFUSE,
    RE_URGE_GIVE,
)

RE_FAIR_WORD = re.compile(r"公平|偏心|让给|给他|给她")


def collect_l_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 6:
        return issues
    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    if not RE_URGE_GIVE.search(body):
        issues.append("L缺成人催让渡")
    if not RE_REFUSE.search(body):
        issues.append("L缺拒收退让")
    if not RE_BIAS_EXPOSE.search(body) and not RE_BIAS_EXPOSE.search(tail6):
        issues.append("L缺点破偏心")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """L 好笑维：表演公平反差、拒领、点破。"""
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    if RE_URGE_GIVE.search(body) and RE_REFUSE.search(body):
        pts += 4
        pros.append("催让被拒收")
    elif RE_REFUSE.search(body):
        pts += 2
        pros.append("有拒收退让")

    if RE_BIAS_EXPOSE.search(body):
        pts += 3
        pros.append("点破偏心")

    if RE_FAIR_WORD.search(tail) and RE_REFUSE.search(body):
        pts += 2
        pros.append("公平反差收束")

    return min(pts, 10), pros
