"""B 类正文硬卡（收束落槌、末句嘴硬）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_SOFT_LAST = re.compile(r"哼|才不是|才不是我的主意")
RE_BLAME_TAIL = re.compile(r"都怪你|是你先|你答应|赖我")


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


def append_b_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "B":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""
    if last_sp in ("昭昭", "灿灿") and not RE_SOFT_LAST.search(last):
        if not RE_BLAME_TAIL.search(last):
            errors.append(
                "B类：末句须破功方嘴硬收束（哼/才不是/才不是我的主意）",
            )
