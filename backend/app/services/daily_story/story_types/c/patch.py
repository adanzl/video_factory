"""C 类正文本地修稿（仅确定性结构）。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地。
- 禁止绑定具体 theme 的规则（按主题关键词分支改写台词）。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code


def patch_c_body(story: dict) -> list[str]:
    """C 类：末句 speaker 勿为妈妈（改为与上一句交替的姐弟）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes

    last_sp = str(last.get("speaker") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    if last_sp != "妈妈":
        return notes

    if prev_sp in ("昭昭", "灿灿"):
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("C末句speaker妈妈→姐弟")
    return notes
