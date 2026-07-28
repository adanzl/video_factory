"""D 类正文硬卡（字面执行 + 回旋镖收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_SOFT_LAST,
)

RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩|大人要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
RE_LITERAL_MID = re.compile(
    r"照做|按你说的|你不是说|字面|按规矩|你说要|你让我|照你说的",
)
RE_MESS = re.compile(
    r"掉了|滑|洒|乱|坏|打不开|饿着|够不着|弄翻|摔|倒了|全掉|洒一地|堆塌|"
    r"解不开|勒|死结|死疙瘩|大马趴",
)
_D_MAX_DIALOGUE_LINES = 18
_RE_RULE = re.compile(r"不许|别碰|别晃|轻点|慢点|系紧|规矩|叮嘱|不准|不能")


def _dialogue_lines(story: dict) -> tuple[list[str], list[str]]:
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


def append_d_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "D":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("D类正文过短，不足以完成字面执行收束（至少约 8 句对白）")
        return

    if n > _D_MAX_DIALOGUE_LINES:
        errors.append(
            f"D类正文过长（须≤{_D_MAX_DIALOGUE_LINES}句对白），当前{n}句",
        )
        return

    mom_n = sum(1 for sp in speakers if sp == "妈妈")
    if mom_n > 0:
        errors.append("D类主戏姐弟，禁止妈妈插话（留给E类）")

    head6 = "".join(lines[:6])
    rule_hits = len(_RE_RULE.findall(head6))
    if rule_hits >= 3:
        errors.append("D类前段勿重复唠叨同一条规矩（立规≤2次）")

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    late8 = "".join(lines[max(0, n - 8) :])
    body = "".join(lines[: max(0, n - 4)])

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "D类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
            "应走叮嘱方破规+字面回旋镖",
        )
        return

    if not RE_LITERAL_MID.search(body):
        errors.append(
            "D类中段须有「按叮嘱/字面执行」对白（照做、按你说的、你不是说等）",
        )
        return

    # 允许哼后留 1–2 句尾巴；回旋镖看近 8 句即可
    if not RE_BOOMERANG_RULE.search(late8):
        errors.append(
            "D类末段须用叮嘱方原话回旋镖（你自己说/你刚才说/你现在也…）",
        )
        return

    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""
    if last_sp == "妈妈" and not RE_SOFT_LAST.search(last):
        if not re.search(r"哼|才不是|没办法|算了|行吧", last):
            errors.append(
                "D类末句叮嘱方（若由妈妈收束）须嘴硬或软破功（哼/行吧/算了等）",
            )
            return

    if RE_MESS.search(tail4) and not RE_MESS.search(body):
        errors.append(
            "D类后果跑偏宜在中段已可见（洒/掉/乱等），勿只在末句突然出现",
        )
