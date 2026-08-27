"""K 类正文硬卡（互骂升级 + 劝失败 + 僵持不和好）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_FIGHT = re.compile(r"打|骂|推|吵|互骂|别吵|讨厌|滚|吼")
RE_PARENT_FAIL = re.compile(
    r"躲|叹气|劝不了|管不了|别打了|你们别|看你们|我不管了|管不着",
)
RE_STALEMATE = re.compile(r"不和好|僵持|哼|不理|别理|谁怕谁|越劝越")
RE_H_RECONCILE = re.compile(r"拉手|(?<!不)和好|不打了|对不起|原谅|说好了|齐声")
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


def append_k_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "K":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    parent_n = sum(1 for sp in speakers if sp in ("妈妈", "爸爸"))
    if not RE_FIGHT.search(body):
        errors.append("K类：正文须有互骂/互打升级（打/骂/推/吵等）")
    if parent_n >= 1 and not RE_PARENT_FAIL.search(body):
        errors.append("K类：大人台词须像劝失败/旁观（躲/叹气/劝不了等）")
    if not RE_STALEMATE.search(tail4):
        errors.append("K类：末段须僵持不和好（哼/不理/僵持等）")
    if RE_H_RECONCILE.search(tail4):
        errors.append("K类：末段勿 H 式和好（拉手/不打了/对不起等）")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("K类：末段勿 A 式反噬/破功链")
