"""C 类正文本地修稿（仅确定性结构）。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地。
- 禁止绑定具体 theme 的规则（按主题关键词分支改写台词）。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 末句嘴硬软收词（可在句首，可带 …… 前缀）
_RE_C_SOFT_HEAD = re.compile(
    r"^[……。！？\s]*(哼|行吧|随便|算了|好吧|认栽|服了|算了算)[，,。！？…]?",
)


def patch_c_trim_soft_last(story: dict) -> list[str]:
    """一句一改：末句若「哼/行吧/算了 + 长解释/文字游戏」，截到软收词即止。

    C 末句只许「……哼/行吧/随便/算了」；模型常写成「哼，你那是碰，
    我这是拿，不一样！」这类草率续句——本地截断比整段重试稳。
    软收词后尾巴 ≤8 字（如「……哼，给你吧」）视为合理嘴硬，保留。
    """
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return notes
    last = dialogue[-1]
    if not isinstance(last, dict):
        return notes
    line = str(last.get("line") or "").strip()
    m = _RE_C_SOFT_HEAD.match(line)
    if not m:
        return notes
    soft = m.group(1)
    tail = line[m.end():].strip("，,。！？… \t")
    if not tail or len(tail) < 8:
        return notes
    new_line = f"{soft}。"
    total = sum(len(str(d.get("line") or "")) for d in dialogue)
    if total - (len(line) - len(new_line)) < 280:  # 别把正文削到 280 硬卡以下
        return notes
    last["line"] = new_line
    notes.append("C末句软收截断")
    return notes


def patch_c_body(story: dict) -> list[str]:
    """C 类：末句 speaker 勿为妈妈 + 末句软收截断（一句一改）。"""
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
        notes.extend(patch_c_trim_soft_last(story))
        return notes

    if prev_sp in ("昭昭", "灿灿"):
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("C末句speaker妈妈→姐弟")
    notes.extend(patch_c_trim_soft_last(story))
    return notes
