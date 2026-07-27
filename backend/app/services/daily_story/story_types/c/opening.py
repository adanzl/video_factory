"""C 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

# 开场禁止已分胜负/已回旋镖收束
C_OPENING_RESOLVED_RE = re.compile(
    r"你输了|我赢了|算你狠|回旋镖|谁弄乱谁收拾.*你收",
)
# 勿像 A 管教、B 密谋
C_OPENING_A_RE = re.compile(
    r"那不一样|听我的|写作业|刷牙太快|检查不算",
)
C_OPENING_B_RE = re.compile(
    r"嘘|别告诉|咱俩|暗号|望风|完蛋|妈妈来了",
)
# 正向：发现争点实物/场面
C_OPENING_ANCHOR_RE = re.compile(
    r"怎么|谁|凭什么|不公平|规矩|抢|弄乱|翻|叠|洒|倒|多拿|先",
)


def append_c_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "C":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if C_OPENING_RESOLVED_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场禁止已分胜负或已收束"
                "（你赢了/算你狠等），留给正文末四拍",
            )
            break
        if C_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场勿像A管教末四拍"
                "（那不一样/听我的等），应是发现争点",
            )
            break
        if C_OPENING_B_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场勿像B密谋露馅"
                "（嘘/别告诉/完蛋等），应是争资源现场",
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


def _conflict_anchor_tokens(blob: str) -> list[str]:
    cleaned = re.sub(
        r"灿灿|昭昭|[，。！？\s]|vs|VS|争谁|谁该|重新",
        "",
        blob,
    )
    return [
        t for t in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned)
        if len(t) >= 2
    ][:8]


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """开场质量：约 -6～+6，叠在结构分上。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["C开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if C_OPENING_RESOLVED_RE.search(joined):
        cons.append("C开场已像末段收束")
        pts -= 5
    elif C_OPENING_A_RE.search(joined):
        cons.append("C开场偏A管教")
        pts -= 4
    elif C_OPENING_B_RE.search(joined):
        cons.append("C开场偏B密谋")
        pts -= 4
    elif C_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("C开场锚定争点")

    core = str(story.get("conflict_core") or "")
    setting = str(story.get("setting") or "")
    anchor_blob = core + setting
    if pts >= 0 and anchor_blob.strip():
        tokens = _conflict_anchor_tokens(anchor_blob)
        anchored = bool(tokens) and any(t in joined for t in tokens)
        if not anchored and anchor_blob.strip():
            if re.search(r"衣服|叠好|零食|酸奶|马桶|洗澡", anchor_blob) and re.search(
                r"衣服|叠|零食|酸奶|马桶|洗澡", joined,
            ):
                anchored = True
        if tokens and not anchored:
            cons.append("C开场未扣 conflict_core")
            pts -= 2

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("C开场与正文首句重复")
        pts -= 3

    if len(opening) == 2 and pts >= 0:
        pts += 1
        pros.append("C开场双句定格")

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "C开场" not in issue:
        return None
    return (
        f"【开场·C】{issue}。"
        "1–2 句发现争点（谁弄乱/怎么抢/凭什么），点名主题物；"
        "勿照抄正文首句（开场可定格远景，正文再顶嘴）；"
        "勿你赢了/算你狠/嘘别告诉/那不一样。"
    )
