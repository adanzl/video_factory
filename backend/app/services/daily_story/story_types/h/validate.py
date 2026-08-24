"""H 类正文硬卡（第三方调解 + 仪式性和好）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_ESCALATE = re.compile(r"打|推|抢|弄坏|不原谅|生气|互毁|走开")
RE_MOM_MEDIATE = re.compile(r"别打|和好|道歉|原谅|都错|不能打|拉手")
RE_RECONCILE = re.compile(r"拉手|和好|不打了|对不起|没关系|说好了")
RE_G_PIVOT = re.compile(r"护|撑腰|拼命|动你|心疼|认真的")


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


def append_h_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "H":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    mom_count = sum(1 for sp in speakers if sp == "妈妈")
    if mom_count < 1:
        errors.append("H类：须有妈妈调解台词")
    if mom_count > 3:
        errors.append(f"H类：妈妈台词宜≤3句，当前{mom_count}")

    if not RE_ESCALATE.search(body):
        errors.append("H类：正文须有冲突升级/僵持（打/抢/不原谅等）")
    if mom_count >= 1 and not RE_MOM_MEDIATE.search(body):
        errors.append("H类：妈妈台词须像定责劝和（和好/道歉/别打等）")
    tail4 = "".join(lines[-4:])
    if not RE_RECONCILE.search(tail4):
        errors.append("H类：末段须仪式性和好（拉手/不打了/对不起等）")
    if RE_G_PIVOT.search(body) and not RE_MOM_MEDIATE.search(body):
        errors.append("H类：勿纯 G 式 pivot 而无第三方调解")
