"""D 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# 开场禁止已回旋镖/叮嘱方已破规
D_OPENING_SPOILER_RE = re.compile(
    r"你自己说|你刚才说|你也破了|你也碰了|回旋镖|"
    r"我说不许你|你不也|算你狠",
)
# 勿像 A 管教末四拍、C 争公平
D_OPENING_A_RE = re.compile(
    r"那不一样|哪里不一样|听我的|我是姐姐你得|检查不算",
)
D_OPENING_C_RE = re.compile(
    r"不公平|谁先拿|一人一半|凭什么你拿",
)
# 正向：叮嘱/待执行场面
D_OPENING_ANCHOR_RE = re.compile(
    r"别碰|不许|轻点|慢点|按|照|叠|鞋带|收拾|弄|叮嘱|规矩",
)


def append_d_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "D":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if D_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] D类禁止开场已回旋镖或叮嘱方已破规"
                "（你自己说/你也碰了等），留给正文末段",
            )
            break
        if D_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] D类开场勿像A末四拍管教"
                "（那不一样/听我的等），应是叮嘱将执行现场",
            )
            break
        if D_OPENING_C_RE.search(line):
            errors.append(
                f"opening[{i}] D类开场勿像C争公平（不公平/谁先拿），"
                "应是「别这样弄/按我说的」类叮嘱前场面",
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
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["D开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if D_OPENING_SPOILER_RE.search(joined):
        cons.append("D开场已像末段回旋镖")
        pts -= 5
    elif D_OPENING_A_RE.search(joined):
        cons.append("D开场偏A管教")
        pts -= 4
    elif D_OPENING_C_RE.search(joined):
        cons.append("D开场偏C争公平")
        pts -= 4
    elif D_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("D开场锚定叮嘱物")

    dialogue = story.get("dialogue")
    if isinstance(dialogue, list) and dialogue and lines_o:
        first_body = ""
        for item in dialogue:
            if isinstance(item, dict):
                first_body = str(item.get("line") or "").strip()
                if first_body:
                    break
        if first_body and _opening_body_overlap(lines_o[0], first_body):
            cons.append("D开场与正文首句重复")
            pts -= 3

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "D开场" not in issue:
        return None
    return (
        f"【开场·D】{issue}。"
        "须 2 句正片第一镜：地点+叮嘱将执行场面（床边歪摞、玄关鞋带松了）；"
        "先报场面再立叮嘱；勿回旋镖/不公平/那不一样；勿单句干问。"
    )
