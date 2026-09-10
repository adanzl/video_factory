"""Q 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

Q_OPENING_ANCHOR_RE = re.compile(
    r"约定|规则|玩法|轮到|说好|抽签|猜拳|轮流|"
    r"(?:\d+|[一二三四五六七八九十两]+|几)(?:口|下|次)|"
    r"玩|吃"
)
Q_OPENING_BAD_RE = re.compile(
    r"爱学习|你爱吗|灵魂|拷问|你刚说|那不一样|擦药|尝尝|再试试"
)


def append_q_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "Q":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if Q_OPENING_BAD_RE.search(first):
        errors.append("Q类开场：首句勿拷问/回旋镖/互整信号")
    if not Q_OPENING_ANCHOR_RE.search(blob):
        errors.append("Q类开场：宜点玩法/约定信号")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["Q开场缺失"]

    lines_q = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    first = lines_q[0] if lines_q else ""
    if Q_OPENING_BAD_RE.search(first):
        cons.append("Q开场：首句勿拷问/互整信号")
        pts -= 4

    blob = f"{setting}{conflict_core}{''.join(lines_q)}"
    if Q_OPENING_ANCHOR_RE.search(blob):
        pts += 2
        pros.append("Q开场锚定玩法/约定")
    else:
        cons.append("Q开场缺玩法/约定信号")
        pts -= 2

    cinematic_pts, cinematic_pros, cinematic_cons = score_opening_cinematic(
        lines_q
    )
    if setting and OPENING_PLACE_RE.search(setting):
        if not OPENING_PLACE_RE.search("".join(lines_q)):
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
