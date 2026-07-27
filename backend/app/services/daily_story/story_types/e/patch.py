"""E 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.e.humor import (
    RE_KID_ASK,
    RE_LOOP,
    RE_MOM_RULE,
    RE_MOM_SOFT,
    RE_MOM_WAFFLE,
)

_A_TAIL = re.compile(r"哪里不一样|都是听|那不一样")


def _is_e(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    return parse_story_type_code(punchline=punch) == "E"


def _lines(dialogue: list) -> list[str]:
    return [
        str(d.get("line") or "") if isinstance(d, dict) else ""
        for d in dialogue
    ]


def _speakers(dialogue: list) -> list[str]:
    return [
        str(d.get("speaker") or "") if isinstance(d, dict) else ""
        for d in dialogue
    ]


def patch_e_strip_a_close(story: dict) -> list[str]:
    """剥 A 式末四拍，改孩子闭环 + 妈妈破功。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    for i in range(len(dialogue) - 4, len(dialogue)):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not _A_TAIL.search(line):
            continue
        if i == len(dialogue) - 1:
            d["speaker"] = "妈妈"
            new_line = "……行行行，算你说得对"
        elif i == len(dialogue) - 2:
            d["speaker"] = "昭昭"
            new_line = "你自己说的，你现在也这样"
        elif "那不一样" in line:
            d["speaker"] = "妈妈"
            new_line = "那是工作需要，不算数"
        else:
            d["speaker"] = "昭昭"
            new_line = "那你刚才也破规矩了"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"E去A收束[{i}]")
    return notes


def patch_e_ensure_mom_rule(story: dict) -> list[str]:
    """前段缺妈妈立论时，改一句妈妈为短规矩。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    head = dialogue[: max(2, len(dialogue) // 2)]
    text = "".join(_lines(head))
    if RE_MOM_RULE.search(text):
        return notes
    for d in head:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "妈妈":
            continue
        new_line = "我说了，饭前不能吃零食"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("E补妈妈立论")
            break
    else:
        # 无妈妈句：插在第 2 句位置改写成妈妈
        if isinstance(dialogue[1], dict):
            dialogue[1]["speaker"] = "妈妈"
            dialogue[1]["line"] = "我说了，饭前不能吃零食"
            notes.append("E补妈妈立论[1]")
    return notes


def patch_e_ensure_kid_ask(story: dict) -> list[str]:
    """中段缺孩子追问时，改一句昭昭。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-3]
    text = "".join(_lines(mid))
    if RE_KID_ASK.search(text):
        return notes
    for d in mid:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") not in ("昭昭", "灿灿"):
            continue
        new_line = "那你刚才那一口算不算啊"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("E补孩子追问")
            break
    return notes


def patch_e_ensure_waffle(story: dict) -> list[str]:
    """缺妈妈改口时，在闭环前改一句妈妈。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = _lines(dialogue)
    if RE_MOM_WAFFLE.search("".join(lines)):
        return notes
    # 找闭环前最近的妈妈句
    loop_i = next(
        (i for i, ln in enumerate(lines) if RE_LOOP.search(ln)),
        len(dialogue) - 2,
    )
    for i in range(min(loop_i, len(dialogue) - 1) - 1, 1, -1):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "妈妈":
            continue
        new_line = "那是尝咸淡，不算吃零食"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"E补妈妈改口[{i}]")
            return notes
    # 强制改倒数第 3 句
    i = len(dialogue) - 3
    if isinstance(dialogue[i], dict):
        dialogue[i]["speaker"] = "妈妈"
        dialogue[i]["line"] = "那是尝咸淡，不算吃零食"
        notes.append(f"E补妈妈改口[{i}]")
    return notes


def patch_e_ensure_loop(story: dict) -> list[str]:
    """末段缺闭环时，改倒数第 2 句为孩子闭环。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    tail = "".join(_lines(dialogue[-4:]))
    if RE_LOOP.search(tail):
        return notes
    d = dialogue[-2]
    if not isinstance(d, dict):
        return notes
    d["speaker"] = "昭昭"
    d["line"] = "你自己说不能吃，你现在也吃了"
    notes.append("E补追问闭环")
    return notes


def patch_e_closing_mom_soft(story: dict) -> list[str]:
    """末句须妈妈破功。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    last = dialogue[-1]
    if not isinstance(last, dict):
        return notes
    last_sp = str(last.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "")
    if last_sp == "妈妈" and RE_MOM_SOFT.search(last_ln):
        return notes
    # 上一句已闭环才改
    prev_ln = ""
    if isinstance(dialogue[-2], dict):
        prev_ln = str(dialogue[-2].get("line") or "")
    if not RE_LOOP.search(prev_ln) and last_sp == "妈妈":
        # 仅补软词
        soft = "……行行行，算你说得对"
        if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
            last["line"] = soft
            notes.append("E末句补妈妈破功词")
        return notes
    if not RE_LOOP.search(prev_ln):
        return notes
    soft = "……行行行，算你说得对"
    if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
        last["speaker"] = "妈妈"
        last["line"] = soft
        notes.append("E末句改妈妈破功")
    return notes


def patch_e_trim_mom_lecture(story: dict) -> list[str]:
    """妈妈台词过多时，合并中段空说教句为短句。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    speakers = _speakers(dialogue)
    mom_idx = [i for i, sp in enumerate(speakers) if sp == "妈妈"]
    if len(mom_idx) <= 5:
        return notes
    # 砍中间多余妈妈句（保留首立论、改口、末破功）
    keep_first = mom_idx[0]
    keep_last = mom_idx[-1]
    # 找改口句
    lines = _lines(dialogue)
    waffle_i = next(
        (i for i in mom_idx if RE_MOM_WAFFLE.search(lines[i])),
        mom_idx[min(2, len(mom_idx) - 1)],
    )
    drop = [
        i
        for i in mom_idx
        if i not in (keep_first, waffle_i, keep_last)
        and 1 < i < len(dialogue) - 2
    ]
    # 从后往前删，最多删到剩 5 句妈妈
    dropped = 0
    for i in reversed(drop):
        if len(mom_idx) - dropped <= 5:
            break
        # 改成昭昭短追问，避免句数塌
        if isinstance(dialogue[i], dict):
            dialogue[i]["speaker"] = "昭昭"
            dialogue[i]["line"] = "那你刚才呢"
            dropped += 1
            notes.append(f"E削妈妈说教[{i}]")
    return notes


def patch_e_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_e_strip_a_close(story))
    notes.extend(patch_e_ensure_mom_rule(story))
    notes.extend(patch_e_ensure_kid_ask(story))
    notes.extend(patch_e_ensure_waffle(story))
    notes.extend(patch_e_ensure_loop(story))
    notes.extend(patch_e_closing_mom_soft(story))
    notes.extend(patch_e_trim_mom_lecture(story))
    notes.extend(patch_e_strip_a_close(story))
    notes.extend(patch_e_ensure_loop(story))
    notes.extend(patch_e_closing_mom_soft(story))
    return notes
