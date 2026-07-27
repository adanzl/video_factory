"""E 类正文本地修稿（确定性结构）。"""

from __future__ import annotations

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types import parse_story_type_code


def patch_e_body(story: dict) -> list[str]:
    """末句应为妈妈破功：若末句是姐弟且上一句已闭环，改 speaker 为妈妈并补短破功。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "E":
        return notes

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes

    last = dialogue[-1]
    if not isinstance(last, dict):
        return notes
    last_sp = str(last.get("speaker") or "").strip()
    if last_sp == "妈妈":
        return notes

    prev_ln = ""
    if isinstance(dialogue[-2], dict):
        prev_ln = str(dialogue[-2].get("line") or "")
    if "你自己说" not in prev_ln and "你刚才" not in prev_ln and "那你也是" not in prev_ln:
        return notes

    soft = "……行行行，算你说得对"
    if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
        last["speaker"] = "妈妈"
        last["line"] = soft
        notes.append("E末句改妈妈破功")
    return notes
