"""E 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# 开场禁止妈妈已破功
E_OPENING_SPOILER_RE = re.compile(
    r"行行行|算你说得对|随便你|说不通|唉算了|"
    r"妈妈你也|你自己说",
)
# 勿像 A/B/C 开场
E_OPENING_A_RE = re.compile(
    r"那不一样|哪里不一样|检查不算|刷牙太快",
)
E_OPENING_B_RE = re.compile(
    r"嘘|别告诉|咱俩|完蛋|妈妈来了",
)
E_OPENING_C_RE = re.compile(
    r"不公平|谁先拿|你输了",
)
E_OPENING_ANCHOR_RE = re.compile(
    r"妈妈|妈|讲理|规矩|应该|不行|怎么又|我说|"
    r"挂钟|嘴角|勺子|屏幕|被窝|亮着",
)


def append_e_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "E":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if E_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] E类禁止开场妈妈已破功"
                "（行行行/算你对等），破功留给正文末句",
            )
            break
        if E_OPENING_B_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像B密谋（嘘/别告诉/完蛋），"
                "应是找妈妈讲理或挨训前场面",
            )
            break
        if E_OPENING_C_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像C争公平，应是妈妈/孩子要讲道理",
            )
            break
        if E_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像A姐弟末四拍（那不一样等）",
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
        return -5, pros, ["E开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if E_OPENING_SPOILER_RE.search(joined):
        cons.append("E开场妈妈已破功")
        pts -= 5
    elif E_OPENING_B_RE.search(joined):
        cons.append("E开场偏B密谋")
        pts -= 4
    elif E_OPENING_C_RE.search(joined):
        cons.append("E开场偏C争公平")
        pts -= 4
    elif E_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("E开场锚定讲理场面")

    dialogue = story.get("dialogue")
    if isinstance(dialogue, list) and dialogue and lines_o:
        first_body = ""
        for item in dialogue:
            if isinstance(item, dict):
                first_body = str(item.get("line") or "").strip()
                if first_body:
                    break
        if first_body and _opening_body_overlap(lines_o[0], first_body):
            cons.append("E开场与正文首句重复")
            pts -= 3

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "E开场" not in issue:
        return None
    return (
        f"【开场·E】{issue}。"
        "须 2 句正片第一镜：地点+现行（灶台嘴角、卧室挂钟/被窝亮光）；"
        "换人说，speaker 可为孩子或妈妈；先抓现行再立规；"
        "勿行行行/孩子预支规矩/嘘别告诉；勿单句干问。"
    )
