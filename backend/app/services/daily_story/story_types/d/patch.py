"""D 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.d.humor import (
    RE_BOOM_CLOSE,
    RE_FIX,
    RE_LITERAL,
    RE_MESS,
)
from app.services.daily_story.story_types.quality import RE_SOFT_LAST

_A_TAIL = re.compile(r"哪里不一样|都是听|那不一样")


def _is_d(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    return parse_story_type_code(punchline=punch) == "D"


def patch_d_strip_a_close(story: dict) -> list[str]:
    """剥 A 式末四拍词，改回旋镖收束。"""
    notes: list[str] = []
    if not _is_d(story):
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
        sp = str(d.get("speaker") or "")
        if i == len(dialogue) - 1:
            new_line = "……哼，算了"
            if sp not in ("灿灿", "妈妈"):
                d["speaker"] = "灿灿"
        elif i == len(dialogue) - 2:
            new_line = "那你刚才说别碰，你现在也碰了"
            d["speaker"] = "昭昭"
        elif "那不一样" in line:
            new_line = "你自己说别碰的"
            d["speaker"] = "昭昭"
        else:
            new_line = "现在不碰谁收拾啊"
            if sp == "昭昭":
                d["speaker"] = "灿灿"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"D去A收束[{i}]")
    return notes


def patch_d_ensure_literal(story: dict) -> list[str]:
    """中段缺字面执行时，改一句昭昭为「按你说的」。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-4]
    text = "".join(str(d.get("line") or "") for d in mid if isinstance(d, dict))
    if RE_LITERAL.search(text):
        return notes
    for d in mid:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "昭昭":
            continue
        new_line = "那我按你说的，照做就是了"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("D补字面执行")
            break
    return notes


def patch_d_ensure_mess(story: dict) -> list[str]:
    """缺可见后果时，在破规前补一句搞砸。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    if RE_MESS.search("".join(lines)):
        return notes
    end = len(dialogue) - 4
    i = max(3, end - 3)
    if not isinstance(dialogue[i], dict):
        return notes
    dialogue[i]["speaker"] = "昭昭"
    dialogue[i]["line"] = "倒了……全掉地上了"
    notes.append(f"D补后果[{i}]")
    return notes


def patch_d_ensure_fix(story: dict) -> list[str]:
    """回旋镖前须有叮嘱方破规补救。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    fix_i = next((i for i, ln in enumerate(lines) if RE_FIX.search(ln)), None)
    boom_i = next(
        (i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)),
        None,
    )
    if fix_i is not None and (boom_i is None or fix_i < boom_i):
        return notes
    # 找末四拍前灿灿句改写
    end = len(dialogue) - 4
    for j in range(end - 1, 2, -1):
        if not isinstance(dialogue[j], dict):
            continue
        if str(dialogue[j].get("speaker") or "") not in ("灿灿", "妈妈"):
            continue
        new_line = "我来扶，你别乱动"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            dialogue[j]["line"] = new_line
            notes.append(f"D补破规[{j}]")
            break
    return notes


def patch_d_ensure_boomerang(story: dict) -> list[str]:
    """末段缺回旋镖时补「你自己说…你现在也…」。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    full = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    # 前文已有收束回旋镖则勿在尾巴硬塞第二发
    if RE_BOOM_CLOSE.search(full):
        last = dialogue[-1]
        if isinstance(last, dict) and not RE_SOFT_LAST.search(
            str(last.get("line") or ""),
        ):
            # 末句不是软收且无回旋镖词：若倒数第二已是回旋镖则只修末句
            prev = dialogue[-2]
            if isinstance(prev, dict) and RE_BOOM_CLOSE.search(
                str(prev.get("line") or ""),
            ):
                last["speaker"] = "灿灿"
                last["line"] = "……哼，算了"
                notes.append("D补末句嘴硬")
        return notes
    d = dialogue[-2]
    if not isinstance(d, dict):
        return notes
    d["speaker"] = "昭昭"
    d["line"] = "你自己说别碰，你现在也碰了"
    notes.append("D补回旋镖")
    last = dialogue[-1]
    if isinstance(last, dict) and not RE_SOFT_LAST.search(str(last.get("line") or "")):
        last["speaker"] = "灿灿"
        last["line"] = "……哼，算了"
        notes.append("D补末句嘴硬")
    return notes


def patch_d_closing_speaker(story: dict) -> list[str]:
    """末句若为妈妈但无破功语气，且上一句已是回旋镖，改末句 speaker 为灿灿。"""
    notes: list[str] = []
    if not _is_d(story):
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


def patch_d_strip_nitpick(story: dict) -> list[str]:
    """中段抠「你又没说/也包括」车轱辘，改回动作抬杠。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-4]
    nit_re = re.compile(r"你又没说|只说了|也包括|没说别的|当然包括")
    seen = 0
    for i, d in enumerate(mid):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not nit_re.search(line):
            continue
        seen += 1
        if seen <= 1:
            continue
        sp = str(d.get("speaker") or "")
        new_line = (
            "我一直在轻轻叠啊"
            if sp == "昭昭"
            else "你叠歪了，快停手"
        )
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"D去空辩[{i + 2}]")
    return notes


def patch_d_trim_second_boom(story: dict) -> list[str]:
    """哼/算了后若再开回旋镖，砍到第一次软收（可留一句无回旋镖的尾巴）。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    soft_i = next(
        (
            i
            for i, d in enumerate(dialogue)
            if isinstance(d, dict)
            and re.search(r"哼|算了", str(d.get("line") or ""))
        ),
        None,
    )
    if soft_i is None or soft_i >= len(dialogue) - 2:
        return notes
    later_boom = any(
        isinstance(dialogue[i], dict)
        and RE_BOOM_CLOSE.search(str(dialogue[i].get("line") or ""))
        for i in range(soft_i + 1, len(dialogue))
    )
    if not later_boom:
        return notes
    # 保留软收 + 最多 2 句无回旋镖尾巴
    keep = soft_i + 1
    for i in range(soft_i + 1, min(len(dialogue), soft_i + 3)):
        ln = str(dialogue[i].get("line") or "") if isinstance(dialogue[i], dict) else ""
        if RE_BOOM_CLOSE.search(ln):
            break
        keep = i + 1
    if keep < len(dialogue):
        del dialogue[keep:]
        notes.append(f"D砍二次回旋镖→{keep}句")
    return notes


def patch_d_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_d_strip_a_close(story))
    notes.extend(patch_d_strip_nitpick(story))
    notes.extend(patch_d_ensure_literal(story))
    notes.extend(patch_d_ensure_mess(story))
    notes.extend(patch_d_ensure_fix(story))
    notes.extend(patch_d_ensure_boomerang(story))
    notes.extend(patch_d_closing_speaker(story))
    notes.extend(patch_d_trim_second_boom(story))
    notes.extend(patch_d_strip_a_close(story))
    notes.extend(patch_d_strip_nitpick(story))
    notes.extend(patch_d_ensure_fix(story))
    notes.extend(patch_d_ensure_boomerang(story))
    notes.extend(patch_d_trim_second_boom(story))
    return notes
