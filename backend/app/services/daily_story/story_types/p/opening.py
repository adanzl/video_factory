"""P 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

P_OPENING_ANCHOR_RE = re.compile(
    r"尝尝|试试|挑战|给你|递|卷|饼|加料|桌上"
)
P_OPENING_BAD_RE = re.compile(
    r"爱学习|你爱吗|灵魂|拷问|你刚说|那不一样|擦药|偏心|归谁"
)


def append_p_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "P":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if P_OPENING_BAD_RE.search(first):
        errors.append("P类开场：首句勿拷问/回旋镖/暖收/争归属信号")
    if not P_OPENING_ANCHOR_RE.search(blob):
        errors.append("P类开场：宜点挑战/递物信号")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """P 开场质量：挑战/递物锚定 + 可拍画面。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["P开场缺失"]

    lines_p = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    first = lines_p[0] if lines_p else ""
    if P_OPENING_BAD_RE.search(first):
        cons.append("P开场：首句勿拷问/回旋镖信号")
        pts -= 4

    blob = f"{setting}{conflict_core}{''.join(lines_p)}"
    if P_OPENING_ANCHOR_RE.search(blob):
        pts += 2
        pros.append("P开场锚定挑战/递物")
    else:
        cons.append("P开场缺挑战/递物信号")
        pts -= 2

    cinematic_pts, cinematic_pros, cinematic_cons = score_opening_cinematic(
        lines_p
    )
    if setting and OPENING_PLACE_RE.search(setting):
        if not OPENING_PLACE_RE.search("".join(lines_p)):
            cinematic_pts += 1
            cinematic_pros = list(cinematic_pros)
            cinematic_cons = [
                c for c in cinematic_cons if c != "开场缺背景地点"
            ]
            if not any("背景地点" in p for p in cinematic_pros):
                cinematic_pros.append("开场有背景地点")
    pts += cinematic_pts
    pros.extend(cinematic_pros)
    cons.extend(cinematic_cons)

    return max(-8, min(8, pts)), pros, cons
