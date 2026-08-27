"""J 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

J_OPENING_PLEAD_RE = re.compile(r"求|让我|去吧|玩|同意了吗|妈妈")
J_OPENING_VETO_RE = re.compile(r"不行|不同意|我说了算|等等|否决|不准")
J_OPENING_MEDIATE_RE = re.compile(r"别打|和好|定责|都错|拉手")


def append_j_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "J":
        return
    if not normalized:
        return
    blob = f"{setting}{conflict_core}" + "".join(
        str(d.get("line") or "").strip()
        for d in normalized[:2]
        if isinstance(d, dict)
    )
    if J_OPENING_MEDIATE_RE.search(blob):
        errors.append("J类开场：首句勿 H 式劝和，求放行/否决留正文")
    if not J_OPENING_PLEAD_RE.search(blob) and not J_OPENING_VETO_RE.search(blob):
        errors.append("J类开场：首句宜点求放行或否决（求/去吧/不同意等）")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """J 开场质量：求/否锚定 + 可拍画面；M5+J 允许妈妈先同意。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["J开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    blob = f"{setting}{conflict_core}{''.join(lines_o)}"
    if J_OPENING_MEDIATE_RE.search("".join(lines_o)):
        cons.append("J开场：首句勿 H 式劝和")
        pts -= 4
    elif J_OPENING_PLEAD_RE.search(blob) or J_OPENING_VETO_RE.search(blob):
        pts += 2
        pros.append("J开场锚定求/否")
    else:
        cons.append("J开场缺求放行或否决信号")
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
