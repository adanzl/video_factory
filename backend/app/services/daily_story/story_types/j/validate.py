"""J 类正文硬卡（否决压住 + 怂退收场，无 A 反噬）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_PLEAD = re.compile(r"求|让我|去吧|放行|同意了吗|妈妈.*答应|写完作业")
RE_VETO = re.compile(r"不行|不同意|我说了算|否决|不准|没用|听我的|霸道")
RE_SURRENDER = re.compile(r"不去了|回房间|不理你|再也不求|放弃|呜呜")
RE_HOLD = re.compile(r"我说了算|反正|听我的|省得|这个家")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说|哪里不一样")
RE_H_MEDIATE = re.compile(r"别打|和好|道歉|原谅|都错|拉手|定责")


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


def append_j_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "J":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_PLEAD.search(body):
        errors.append("J类：正文须有求放行/试探（求/让我/同意了吗等）")
    if not RE_VETO.search(body):
        errors.append("J类：正文须有一票否决/权威压住（不行/我说了算等）")
    if not RE_SURRENDER.search(body):
        errors.append("J类：正文须写对方怂退/放弃（不去了/回房间/不理你等）")
    if not RE_HOLD.search(tail4):
        errors.append("J类：末段须镇住收场（我说了算/反正…等）")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("J类：末段勿 A 式反噬/破功链")
    if RE_H_MEDIATE.search(body) and "妈妈" in "".join(speakers):
        errors.append("J类：妈妈宜旁观，勿 H 式劝和定责")
