"""A 类发现开场校验。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# A 开场禁止先揭穿一锤（灿灿已翻车/双标）
A_OPENING_SPOILER_RE = re.compile(
    r"自己才|自己刷了|自己算错|自己写错|自己弹错|"
    r"草稿.{0,6}错|计时器上自己|你也错了|"
    r"刚玩过|你上次|双标|才刷了半|一分半",
)
# A 开场禁止「互怼中途读数/宣判」——须先看见场面
A_OPENING_MID_FIGHT_RE = re.compile(
    r"计时器才走|才走了\s*\d+\s*秒|才走了\s*[一二三四五六七八九十两半]+\s*秒|"
    r"至少两分钟|牙医说的|重刷|时间到了|到点了",
)


def append_a_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "A":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if A_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] A类禁止开场先揭穿灿灿翻车/双标"
                "（自己才刷/算错/刚玩过等），一锤留给正文中段",
            )
            break
        if A_OPENING_MID_FIGHT_RE.search(line):
            errors.append(
                f"opening[{i}] A类开场须像发现现场（物/动作），"
                "禁止读秒宣判或直接立规（如「计时器才走了30秒」）",
            )
            break


def _opening_body_overlap(a: str, b: str) -> bool:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    n = min(len(left), len(right), 8)
    return n >= 4 and left[:n] == right[:n]


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """A 类开场质量：约 -8～+8。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["A开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if A_OPENING_SPOILER_RE.search(joined):
        cons.append("A开场先揭穿一锤")
        pts -= 5
    elif A_OPENING_MID_FIGHT_RE.search(joined):
        cons.append("A开场像读秒宣判")
        pts -= 4
    else:
        pts += 2
        pros.append("A开场发现现场")

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    dialogue = story.get("dialogue")
    if isinstance(dialogue, list) and dialogue and lines_o:
        first_body = ""
        for item in dialogue:
            if isinstance(item, dict):
                first_body = str(item.get("line") or "").strip()
                if first_body:
                    break
        if first_body and _opening_body_overlap(lines_o[0], first_body):
            cons.append("A开场与正文首句重复")
            pts -= 3

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "A开场" not in issue:
        return None
    return (
        f"【开场·A】{issue}。"
        "须 2 句正片第一镜：地点+物/动作（洗手台牙膏沫、餐桌水果盘）；"
        "勿自己才刷/算错/到点了；勿单句干问。"
    )
