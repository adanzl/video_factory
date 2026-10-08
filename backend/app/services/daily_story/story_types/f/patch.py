"""F 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

_RE_FILLER_TAIL = re.compile(
    r"(?:[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}|"
    r"了呢[了呀]|了呀[呢]|嘛了[呀]|了呢呀|"
    r"了呢|了呀|嘛了|呢吧|呀呢|呢嘛|真的呀|好不好呀|好不好|着呢|"
    r"你听着呀|了呢了呀|好不好了呀)$",
)
_RE_FILLER_INLINE = re.compile(
    r"呢了呀|了呢呀|嘛了呀|了呀呢|真的呀|你听着呀|你听着了呀|着呢了呀|好不好了呀|了呢了呀",
)
_RE_BROKEN_EXCLAIM = re.compile(r"啊{2,}了啊")
_RE_BROKEN_AH = re.compile(r"啊什么了啊")


def _is_f(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "F"


def _strip_filler_line(line: str) -> str:
    trail = ""
    core = line
    if core and core[-1] in "。！？…":
        trail = core[-1]
        core = core[:-1]
    new_core = _RE_FILLER_INLINE.sub("", core)
    new_core = _RE_FILLER_TAIL.sub("", new_core)
    return f"{new_core}{trail}"


def patch_f_strip_filler(story: dict) -> list[str]:
    """剥句尾语气垫字（与 B 垫字补 min 共用场景）。"""
    notes: list[str] = []
    if not _is_f(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = line
        if _RE_BROKEN_EXCLAIM.search(new_line):
            new_line = _RE_BROKEN_EXCLAIM.sub("啊啊啊", new_line)
        if _RE_BROKEN_AH.search(new_line):
            new_line = _RE_BROKEN_AH.sub("啊什么啊", new_line)
        new_line = _strip_filler_line(new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"F剥垫字[{i}]")
    return notes


def patch_f_punchline_prefix(story: dict) -> list[str]:
    """gold_chat：punchline_explain 补 F类 前缀（机读结构分）。"""
    if not _is_f(story):
        return []
    explain = str(story.get("punchline_explain") or "").strip()
    if not explain or explain.startswith("F类"):
        return []
    story["punchline_explain"] = f"F类：{explain}"
    return ["F punchline→F类"]


_F_RETORT_POOL = (
    "你再说一遍！",
    "谁怕谁啊！",
    "我才不信！",
    "哼，少来！",
)


def patch_f_break_consecutive(story: dict) -> list[str]:
    """F 同人连说时插入对方短接话，恢复互呛交替。"""
    notes: list[str] = []
    if not _is_f(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    used = {
        re.sub(r"[，,。！!？?\s]+", "", str(item.get("line") or ""))
        for item in dialogue
        if isinstance(item, dict)
    }
    inserted = 0
    i = 1
    while i < len(dialogue) and inserted < 2:
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in {"昭昭", "灿灿"} or sa != sb:
            i += 1
            continue
        other = "灿灿" if sa == "昭昭" else "昭昭"
        for retort in _F_RETORT_POOL:
            core = re.sub(r"[，,。！!？?\s]+", "", retort)
            if core in used:
                continue
            dialogue.insert(i, {"speaker": other, "line": retort})
            used.add(core)
            notes.append(f"F插接话断连说[{i + 1}]")
            inserted += 1
            i += 1
            break
        else:
            i += 1
        i += 1
    return notes


def patch_f_append_stale_close(story: dict) -> list[str]:
    """末段缺僵持/露怯/外部打断时，补一句对方短收束。"""
    notes: list[str] = []
    if not _is_f(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    from app.services.daily_story.story_types.f.validate import (
        RE_EXTERNAL_PIVOT,
        RE_STALE_OR_YIELD,
    )

    tail = "".join(str(item.get("line") or "") for item in dialogue[-3:])
    if RE_STALE_OR_YIELD.search(tail) or RE_EXTERNAL_PIVOT.search(tail):
        return notes
    last_sp = str(dialogue[-1].get("speaker") or "").strip()
    other = "灿灿" if last_sp == "昭昭" else "昭昭"
    close = "不跟你玩了！"
    if len(dialogue) < 24:
        dialogue.append({"speaker": other, "line": close})
        notes.append("F补僵持收束")
        return notes
    last = dialogue[-1]
    if isinstance(last, dict):
        last["speaker"] = other
        last["line"] = close
        notes.append("F末句改僵持收束")
    return notes


def patch_f_narration_to_speech(story: dict) -> list[str]:
    """F 类正文里的分镜/旁白句改成可说出口的话。"""
    if not _is_f(story):
        return []
    from app.services.gold_story.scene import (
        patch_dialogue_narration_to_speech,
    )

    return patch_dialogue_narration_to_speech(story)


def patch_f_body(story: dict) -> list[str]:
    notes = patch_f_strip_filler(story)
    notes.extend(patch_f_punchline_prefix(story))
    notes.extend(patch_f_narration_to_speech(story))
    notes.extend(patch_f_break_consecutive(story))
    notes.extend(patch_f_append_stale_close(story))
    return notes
