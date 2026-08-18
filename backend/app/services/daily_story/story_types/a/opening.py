"""A 类发现开场校验。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    OPENING_PLACE_RE,
    score_opening_cinematic,
)

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
# 昭昭开场首句把灿灿当前失误说成事实（抽象语法，不锁说话人顺序）
A_OPENING_ZHAO_ACCUSE_RE = re.compile(
    r"^你.{0,20}(?:了|得|成|出|着)|"
    r"^你.{0,16}怎么.{0,12}(?:的|了|着)"
)
# A 类框架把一锤写成既成事实（自己示范失败 / 示范时已经翻车）
A_FRAMEWORK_PUNCH_LEAK_RE = re.compile(
    r"自己.{0,8}(?:示范|剪歪|写错|算错|弹错|刷错)|"
    r"示范时|示范也"
)


def append_a_framework_errors(
    framework: dict,
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "A" or not isinstance(framework, dict):
        return
    for field in ("setting", "conflict_core"):
        text = str(framework.get(field) or "").strip()
        if text and A_FRAMEWORK_PUNCH_LEAK_RE.search(text):
            errors.append(
                f"{field} A类只写「灿灿在教 + 昭昭留下的痕迹」，"
                "一锤留给正文中段（勿写自己示范失败/示范时已翻车）"
            )


def setting_place_tokens(setting: str) -> list[str]:
    """从 setting 抽出地点词；无地点则空，不做主题词穷举。"""
    return list(dict.fromkeys(OPENING_PLACE_RE.findall(setting or "")))


def append_a_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    setting: str = "",
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "A":
        return
    first = normalized[0] if normalized else None
    if (
        first
        and first.get("speaker") == "昭昭"
        and A_OPENING_ZHAO_ACCUSE_RE.search(str(first.get("line") or "").strip())
    ):
        errors.append(
            "opening[0] A类昭昭首句只问由头/抱怨规矩/求教，"
            "不得把灿灿当前失误说成事实（你…了/得/成/出/怎么…的）",
        )

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

    places = setting_place_tokens(setting)
    if places:
        joined = "".join(str(item.get("line") or "") for item in normalized)
        if not any(place in joined for place in places):
            errors.append(
                "opening A类须带出 setting 地点词"
                f"（本场有：{'/'.join(places)}），嵌进痕迹短语",
            )


def _opening_body_overlap(a: str, b: str) -> bool:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    n = min(len(left), len(right), 8)
    return n >= 4 and left[:n] == right[:n]


def _first_body_line_after_opening(story: dict) -> str:
    opening = story.get("discovery_opening")
    dialogue = story.get("dialogue")
    if not isinstance(opening, list) or not isinstance(dialogue, list):
        return ""
    o_lines = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    d_lines = [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict)
    ]
    k = 0
    while (
        k < len(o_lines)
        and k < len(d_lines)
        and _opening_body_overlap(o_lines[k], d_lines[k])
    ):
        k += 1
    return d_lines[k] if k < len(d_lines) else ""


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

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("A开场与正文首句重复")
        pts -= 3

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "A开场" not in issue:
        return None
    return (
        f"【开场·A】{issue}。"
        "第 1 句四件套：setting地点嵌进痕迹 + 你/昭昭 + 痕迹 + 标准；"
        "第 2 句昭昭把球踢回；"
        "昭昭先开口只问由头/抱怨规矩/求教，不把灿灿当前失误说成事实；"
        "一锤留给正文中段她自己示范时发生。"
    )
