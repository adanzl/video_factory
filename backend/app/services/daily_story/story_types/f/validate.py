"""F 类正文硬卡（互呛加码收束，非 B/G/C/A）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_THREAT = re.compile(
    r"再说|试试|你敢|你敢|别吵|讨厌|哼|吼什么|还.*呢",
)
RE_ESCALATION = re.compile(
    r"还.{0,4}呢|吼|啊{2,}|更|再来| louder",
)
RE_STALE_OR_YIELD = re.compile(
    r"不跟你|不理你|谁也不|爱咋|算了|怂|不敢|露怯",
)
RE_EXTERNAL_PIVOT = re.compile(
    r"拍|镜头|偷拍|闭嘴|尴尬|茄子|闹着玩|丢人",
)
RE_B_ALLIANCE_TAIL = re.compile(
    r"一伙|一致对外|甩锅|露馅|瞒妈|别告诉妈|分工|你望风",
)
RE_G_SOFT = re.compile(
    r"擦药|撑腰|说好了|心疼|护姐|护短|给你擦",
)
RE_C_BOOMERANG = re.compile(
    r"你刚才说|你刚说|你说的|凭什么你|你先选|归谁",
)
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|哪里不一样")


def _story_type_f(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "F"


def _lines_and_speakers(story: dict) -> tuple[list[str], list[str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], []
    lines: list[str] = []
    speakers: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if not ln:
            continue
        speakers.append(sp)
        lines.append(ln)
    return lines, speakers


def append_f_body_errors(story: dict, errors: list[str]) -> None:
    if not _story_type_f(story):
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    tail4 = "".join(lines[-4:])
    threat_hits = len(RE_THREAT.findall(mid))
    esc_hits = len(RE_ESCALATION.findall(mid))

    if threat_hits < 2:
        errors.append("F类：中段须至少两轮互呛/威胁（你再说/试试/还…呢等）")
    if esc_hits < 1:
        errors.append("F类：中段须有加码升级（吼/还…呢/啊啊等）")
    has_close = (
        RE_STALE_OR_YIELD.search(tail4)
        or RE_EXTERNAL_PIVOT.search(tail4)
    )
    if not has_close:
        errors.append(
            "F类：末段须僵持/露怯或外部打断收束（不跟你玩/偷拍/尴尬等）"
        )
    if RE_B_ALLIANCE_TAIL.search(tail4) and not RE_EXTERNAL_PIVOT.search(tail4):
        errors.append("F类：末段勿 B 式结盟甩锅/一伙表演（无外部打断时）")
    if RE_G_SOFT.search(tail4):
        errors.append("F类：末段勿 G 式暖收（擦药/撑腰等）")
    if RE_C_BOOMERANG.search(tail4):
        errors.append("F类：末段勿 C 式回旋镖戳穿")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("F类：末段勿 A 式反噬/破功链")


def append_f_fidelity_issues(
    rows: list[dict],
    issues: list[dict],
    *,
    mechanism: str = "",
) -> None:
    """gold_chat 保真：F 类抽象 invariant（非逐篇剧情）。"""
    lines = [
        str(row.get("line") or "").strip()
        for row in rows
        if str(row.get("line") or "").strip()
    ]
    if len(lines) < 8:
        return
    n = len(lines)
    mid = "".join(lines[: max(1, n * 2 // 3)])
    tail4 = "".join(lines[-4:])
    mech = str(mechanism or "").strip().upper()

    if len(RE_THREAT.findall(mid)) < 2:
        issues.append(
            {
                "lines": list(range(1, min(6, n) + 1)),
                "kind": "保真-F互呛",
                "desc": "中段互呛/威胁不足（须至少两轮）",
                "fix": "补你再说/试试/还…呢等互呛，再加码",
            }
        )
    if not RE_ESCALATION.search(mid):
        issues.append(
            {
                "lines": list(range(2, min(8, n) + 1)),
                "kind": "保真-F加码",
                "desc": "中段缺互呛加码升级",
                "fix": "补吼叫/镜像回怼/啊啊等等势抬升",
            }
        )
    if not (
        RE_STALE_OR_YIELD.search(tail4) or RE_EXTERNAL_PIVOT.search(tail4)
    ):
        issues.append(
            {
                "lines": list(range(max(1, n - 3), n + 1)),
                "kind": "保真-F收束",
                "desc": "末段缺僵持/露怯或外部打断收束",
                "fix": "末段补不跟你玩/尴尬微笑/偷拍闭嘴等",
            }
        )
    if RE_B_ALLIANCE_TAIL.search(tail4) and not RE_EXTERNAL_PIVOT.search(tail4):
        issues.append(
            {
                "lines": list(range(max(1, n - 4), n + 1)),
                "kind": "保真-F边界",
                "desc": "末段似 B 结盟一伙链（无外部打断）",
                "fix": "删一伙/一致对外堆砌，改僵持或镜头尴尬收",
            }
        )
    del mech
