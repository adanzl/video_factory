"""B 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# 开场禁止已露馅/已受罚
B_OPENING_CAUGHT_RE = re.compile(
    r"完蛋|死定了|站好|罚站|被抓|妈妈来了|露馅了|藏不住了|"
    r"写检讨|别想吃",
)
# 禁止像 C 公平争夺战开场
B_OPENING_C_FIGHT_RE = re.compile(
    r"不公平|凭什么你拿|谁先拿|你先选|我的没|归谁",
)
# 禁止像 A 管教开场
B_OPENING_A_RULE_RE = re.compile(
    r"你得听|听我的|我是姐姐你得|写作业|刷牙太快|不许磨蹭",
)
# 密谋/结盟片头正向信号
B_OPENING_ALLY_RE = re.compile(
    r"嘘|小声|别告诉|咱俩|我俩|一起|暗号|望风|放风|盯门|拆包|"
    r"别出声|瞒|悄悄",
)


def append_b_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "B":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if B_OPENING_CAUGHT_RE.search(line):
            errors.append(
                f"opening[{i}] B类禁止开场已露馅或已受罚"
                "（完蛋/站好/妈妈来了等），留给正文末段",
            )
            break
        if B_OPENING_C_FIGHT_RE.search(line):
            errors.append(
                f"opening[{i}] B类开场勿像C争公平（凭什么/不公平），"
                "应是密谋嘀咕或分工",
            )
            break
        if B_OPENING_A_RULE_RE.search(line):
            errors.append(
                f"opening[{i}] B类开场勿像A管教（听我的/写作业），"
                "应是联手瞒妈",
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
    """开场质量：约 -5～+5，叠在结构分上。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["B开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if B_OPENING_CAUGHT_RE.search(joined):
        cons.append("B开场已露馅不好看")
        pts -= 5
    elif B_OPENING_C_FIGHT_RE.search(joined):
        cons.append("B开场偏争公平")
        pts -= 4
    elif B_OPENING_A_RULE_RE.search(joined):
        cons.append("B开场偏管教")
        pts -= 4
    elif B_OPENING_ALLY_RE.search(joined):
        pts += 3
        pros.append("B开场密谋片头")

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
            cons.append("B开场与正文首句重复")
            pts -= 3

    if not B_OPENING_ALLY_RE.search(joined) and pts >= 0:
        cons.append("B开场缺密谋感")
        pts -= 2

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "密谋" not in issue:
        return None
    return (
        f"【开场·B】{issue}。"
        "须 2 句正片第一镜：地点+嘀咕/分工（厨房柜门缝、玄关书包）；"
        "嘘/别告诉/你望风；勿完蛋/勿不公平；勿单句干问。"
    )
