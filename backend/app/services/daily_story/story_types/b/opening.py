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
# 分工钉死（谁望风/谁动手）——密谋加分的强档
B_OPENING_WATCH_RE = re.compile(
    r"望风|放风|盯门|看门|门缝|负责|你来|我去|你盯|我盯|你望|我望",
)
# 开场首句＝发现/现状/来路/欲望/提议拍（正向）
B_OPENING_PREMISE_RE = re.compile(
    r"发现|怎么|捡|碰|摔|打翻|打碎|打裂|撞|掉|少|不见|"
    r"好香|好想|想喝|想吃|要不要|吧|"
    r"妈.*(回来|看见|发现|要骂|会骂|来了)|"
    r"地上|门口|茶几|冰箱|沙发上|桌上|柜子|书包|床底|"
    r"一包|一块|一堆|咱俩|我俩|咱们",
)
# 首句禁止直接进补救中段（快把/盖好等是正文段2/3的台词）
B_OPENING_FIXUP_LEAD_RE = re.compile(
    r"快把|快去|快给|快拿|快点|快藏|快关|快跑|快塞|"
    r"扶住|按住|压住|稳住|接住|盖好|塞进|塞到|塞回|"
    r"转过去|转过来|别动|松手|拿纸|拿抹布|擦掉|捡起|放回去",
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
    if normalized and B_OPENING_FIXUP_LEAD_RE.search(normalized[0]["line"]):
        errors.append(
            f"opening[0] B类开场首句是补救中段指令"
            f"（快把/盖好/扶住等）：{normalized[0]['line']!r}；"
            "首句须先给发现/现状/来路拍（怎么坏的/发现了什么/想干什么），"
            "补救动作留给正文连锁"
        )
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

    first = lines_o[0] if lines_o else ""
    if B_OPENING_FIXUP_LEAD_RE.search(first):
        cons.append("B开场补救中段开场（首句快把/盖好等）")
        pts -= 4
    elif B_OPENING_PREMISE_RE.search(first):
        pts += 2
        pros.append("B开场发现拍")
    if B_OPENING_CAUGHT_RE.search(joined):
        cons.append("B开场已露馅不好看")
        pts -= 5
    elif B_OPENING_C_FIGHT_RE.search(joined):
        cons.append("B开场偏争公平")
        pts -= 4
    elif B_OPENING_A_RULE_RE.search(joined):
        cons.append("B开场偏管教")
        pts -= 4
    else:
        if B_OPENING_WATCH_RE.search(joined):
            pts += 3
            pros.append("B开场分工钉死")
        elif B_OPENING_ALLY_RE.search(joined):
            pts += 2
            pros.append("B开场密谋片头")
        else:
            cons.append("B开场缺密谋感")
            pts -= 2

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("B开场与正文首句重复")
        pts -= 3

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "密谋" not in issue:
        return None
    return (
        f"【开场·B】{issue}。"
        "须 2 句正片第一镜：首句=发现/现状/来路/欲望拍"
        "（姐，我把相框碰裂了！/我发现茶几下有包饼干），"
        "禁首句补救祈使（快把/盖好/快去）；"
        "开场只写起因+分工，不写无关内容（受伤/收拾/讲道理等）；"
        "次句=密谋+分工（嘘，你望风我下手/你找胶水粘我盯门口）；"
        "勿完蛋/勿不公平；勿单句干问。"
    )
