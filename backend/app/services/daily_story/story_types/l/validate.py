"""L 类正文硬卡（催让渡 + 拒收退让 + 点破偏心）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象不变量：成人催让 / 拒收退让 / 点破偏心；禁单篇牛奶词表
RE_URGE_GIVE = re.compile(r"给他|给她|让给|给灿灿|给昭昭|要公平")
RE_REFUSE = re.compile(r"不想.*了|我不[喝吃拿要]|你们.*吧|不要了|不接")
RE_BIAS_EXPOSE = re.compile(
    r"偏心|哪门子公平|什么公平|假公平|向着|套路|公平压|表演"
)
RE_C_BOOMERANG_CLOSE = re.compile(r"你刚说|你说的|八百|吃商|心眼子")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")


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


def append_l_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "L":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    body = "".join(lines)
    tail5 = "".join(lines[-5:])
    if not RE_URGE_GIVE.search(body):
        errors.append("L类：正文须有成人催让渡（给他/给她/要公平）")
    if not RE_REFUSE.search(body):
        errors.append("L类：正文须有拒收退让（不想要了/你们喝吧等）")
    if not RE_BIAS_EXPOSE.search(body) and not RE_BIAS_EXPOSE.search(tail5):
        errors.append("L类：须点破偏心/假公平（偏心/哪门子公平等）")
    mom_n = sum(1 for sp in speakers if sp == "妈妈")
    if mom_n > 1:
        errors.append(f"L类：妈妈台词须≤1句，当前{mom_n}")
    if RE_A_BACKFIRE.search(tail5):
        errors.append("L类：末段勿 A 式反噬/破功链")
    if RE_C_BOOMERANG_CLOSE.search(tail5) and not RE_BIAS_EXPOSE.search(tail5):
        errors.append("L类：末段勿套 C 回旋镖/吃商收束，须落点破偏心")
