"""O 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

O_OPENING_ANCHOR_RE = re.compile(
    r"剪刀石头布|猜拳|赢|吃|规则|抢|赛|吹蜡烛|菜"
)
O_OPENING_BAD_RE = re.compile(
    r"爱学习|你爱吗|灵魂|拷问|八百|吃商|偏心|让给|你刚说"
)


def append_o_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "O":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if O_OPENING_BAD_RE.search(first):
        errors.append("O类开场：首句勿灵魂拷问/吃商/回旋镖信号")
    if not O_OPENING_ANCHOR_RE.search(blob):
        errors.append("O类开场：宜点立赛规/争资源信号")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """O 开场质量：立赛规锚定 + 可拍画面。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["O开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    first = lines_o[0] if lines_o else ""
    if O_OPENING_BAD_RE.search(first):
        cons.append("O开场：首句勿拷问/吃商/回旋镖信号")
        pts -= 4

    blob = f"{setting}{conflict_core}{''.join(lines_o)}"
    if O_OPENING_ANCHOR_RE.search(blob):
        pts += 2
        pros.append("O开场锚定立赛规/争资源")
    else:
        cons.append("O开场缺立赛规/争资源信号")
        pts -= 2

    cinematic_pts, cinematic_pros, cinematic_cons = score_opening_cinematic(lines_o)
    if setting and OPENING_PLACE_RE.search(setting):
        if not OPENING_PLACE_RE.search("".join(lines_o)):
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
