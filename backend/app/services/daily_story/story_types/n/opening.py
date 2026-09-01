"""N 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

N_OPENING_ANCHOR_RE = re.compile(
    r"如果|还是|先|喜欢谁|怎么办|你说|问|选"
)
N_OPENING_BAD_RE = re.compile(r"爱学习|你爱吗|灵魂|拷问|八百|吃商|偏心|让给")


def append_n_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "N":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if N_OPENING_BAD_RE.search(first):
        errors.append("N类开场：首句勿灵魂拷问/吃商/偏心信号")
    if not N_OPENING_ANCHOR_RE.search(blob):
        errors.append("N类开场：宜点设问/考验信号")


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """N 开场质量：设问锚定 + 可拍画面。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["N开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    setting = str(story.get("setting") or "")
    conflict_core = str(story.get("conflict_core") or "")
    pts = 0

    first = lines_o[0] if lines_o else ""
    if N_OPENING_BAD_RE.search(first):
        cons.append("N开场：首句勿拷问/吃商/偏心信号")
        pts -= 4

    blob = f"{setting}{conflict_core}{''.join(lines_o)}"
    if N_OPENING_ANCHOR_RE.search(blob):
        pts += 2
        pros.append("N开场锚定设问/考验")
    else:
        cons.append("N开场缺设问/考验信号")
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
