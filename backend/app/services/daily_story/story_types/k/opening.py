"""K 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

K_OPENING_FIGHT_RE = re.compile(r"打|骂|推|吵|别吵|讨厌|滚|哼")
K_OPENING_MEDIATE_RE = re.compile(r"和好|拉手|别打|定责|都错")


def append_k_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "K":
        return
    if not normalized:
        return
    blob = f"{setting}{conflict_core}" + "".join(
        str(d.get("line") or "").strip()
        for d in normalized[:2]
        if isinstance(d, dict)
    )
    if K_OPENING_MEDIATE_RE.search(blob):
        errors.append("K类开场：首句勿 H 式劝和，互骂升级留正文")
    if not K_OPENING_FIGHT_RE.search(blob):
        errors.append("K类开场：首句宜点互骂/冲突（打/骂/吵等）")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """K 开场质量：互骂锚定 + 可拍画面。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["K开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    blob = f"{setting}{conflict_core}{''.join(lines_o)}"
    if K_OPENING_MEDIATE_RE.search("".join(lines_o)):
        cons.append("K开场：首句勿 H 式劝和")
        pts -= 4
    elif K_OPENING_FIGHT_RE.search(blob):
        pts += 2
        pros.append("K开场锚定互骂")
    else:
        cons.append("K开场缺互骂/冲突信号")
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
