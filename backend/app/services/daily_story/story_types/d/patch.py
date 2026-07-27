"""D 类正文本地修稿（确定性结构）。"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import RE_SOFT_LAST


def patch_d_body(story: dict) -> list[str]:
    """末句若为妈妈但无破功语气，且上一句已是回旋镖，改末句 speaker 为灿灿。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "D":
        return notes

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 3:
        return notes

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes

    last_sp = str(last.get("speaker") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "")

    if last_sp == "妈妈" and prev_sp in ("昭昭", "灿灿"):
        if RE_SOFT_LAST.search(last_ln) or "行吧" in last_ln or "算了" in last_ln:
            return notes
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("D末句speaker妈妈→姐弟嘴硬")
    return notes
