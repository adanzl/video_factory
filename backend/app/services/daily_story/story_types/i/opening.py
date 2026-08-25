"""I 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

I_OPENING_QUESTION_RE = re.compile(r"爱学习|你爱|灵魂|拷问|讲道理|凭啥")
I_OPENING_MOM_RE = re.compile(r"^妈妈|别打|和好|调解")


def append_i_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "I":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if I_OPENING_MOM_RE.search(first):
        errors.append("I类开场：首句勿妈妈调解，灵魂拷问留正文")
    if not I_OPENING_QUESTION_RE.search(blob):
        errors.append("I类开场：首句宜点争锋或灵魂拷问（你爱吗/爱学习等）")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """I 开场质量：拷问/争锋锚定 + 可拍画面；setting 可补背景地点。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["I开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    first = lines_o[0] if lines_o else ""
    if I_OPENING_MOM_RE.search(first):
        cons.append("I开场：首句勿妈妈调解")
        pts -= 4

    blob = f"{setting}{conflict_core}{''.join(lines_o)}"
    if I_OPENING_QUESTION_RE.search(blob):
        pts += 2
        pros.append("I开场锚定拷问/争锋")
    else:
        cons.append("I开场缺灵魂拷问信号")
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
