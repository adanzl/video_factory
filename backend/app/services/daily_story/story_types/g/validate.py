"""G 类正文硬卡（pivot + 暖收，非 C/F 收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

RE_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|管你|认真的|我怕|别叫我|老弟|我弟|重要|舍不得|在乎",
)
RE_STUNNED = re.compile(r"你说啥|你说什么|……|\.\.\.|愣|啥\？|什么\？")
RE_SOFT_CLOSE = re.compile(
    r"擦|药|说好了|行了|过来|撑腰|嗯|笑|好\s*吧|别.*欺负|识相|饶|原谅|算了",
)
RE_F_STALE = re.compile(
    r"不跟你玩|不跟你好了|不理你|回家.*不|谁也不|爱咋咋",
)


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


def append_g_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "G":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    tail3 = "".join(lines[-3:])
    if not RE_PIVOT.search(body):
        errors.append("G类：正文须有 pivot（护短/护姐/真心一句）")
    if not RE_STUNNED.search(body):
        errors.append("G类：pivot 后须有愣住 beat（你说啥/……等）")
    if not RE_SOFT_CLOSE.search(tail3):
        errors.append("G类：末段须暖收或半暖（擦药/撑腰/说好了等）")
    if RE_BOOMERANG_RULE.search(tail3):
        errors.append("G类：末段勿 C 式回旋镖戳穿")
    if RE_F_STALE.search(tail3):
        errors.append("G类：末段勿 F 式威胁僵持")
