"""N 类正文硬卡（设问 + 荒诞自洽 + 愣住）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象不变量：追问链 + 因果自洽 + 愣住；禁单篇香蕉/苹果词表
RE_CHALLENGE = re.compile(r"如果|还是|先吃|先|喜欢谁|怎么办|你说")
RE_WHY = re.compile(r"为什么|为啥|怎么想|怎么会|哪有")
RE_SOLEMN_REASON = re.compile(r"因为|所以|这样就能|等到|长成|就能|有籽")
RE_STUN_CLOSE = re.compile(
    r"那……|那\.\.\.|行吧|服了|说不出|无语|愣住|哭笑|"
    r"接不住|被噎|算了|放弃"
)
RE_C_BOOMERANG_CLOSE = re.compile(r"你刚说|你说的|八百|吃商|心眼子")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")
RE_I_SOUL = re.compile(r"爱学习|你爱吗|灵魂|拷问")
RE_E_THESIS_FLIP = re.compile(r"我改口|我说错了|不算了.*改|重新立")


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


def append_n_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "N":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 6:
        return

    body = "".join(lines)
    tail5 = "".join(lines[-5:])
    if not RE_CHALLENGE.search(body):
        errors.append("N类：正文须有设问/考验（如果/还是/喜欢谁等）")
    if not RE_WHY.search(body):
        errors.append("N类：正文须有追问（为什么/为啥等）")
    if not RE_SOLEMN_REASON.search(body):
        errors.append("N类：须有一本正经自洽（因为/所以/就能等）")
    if not RE_STUN_CLOSE.search(body) and not RE_STUN_CLOSE.search(tail5):
        errors.append("N类：收束须愣住/接不住（行吧/服了/那……等）")
    if RE_A_BACKFIRE.search(tail5):
        errors.append("N类：末段勿 A 式反噬/破功链")
    if RE_C_BOOMERANG_CLOSE.search(tail5) and not RE_STUN_CLOSE.search(tail5):
        errors.append("N类：末段勿套 C 回旋镖收束，须落愣住/接不住")
    if RE_I_SOUL.search(body):
        errors.append("N类：勿写成 I 灵魂拷问（爱学习/你爱吗）")
    if RE_E_THESIS_FLIP.search(body):
        errors.append("N类：勿写成 E 立论改口链")
