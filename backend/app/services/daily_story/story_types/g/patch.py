"""G 类正文本地修稿（M4 行动跟随兜底）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.g import humor as g_humor

_G_PAIRS = (
    (
        ("拼图", "回看", "抢拼"),
        (
            ("昭昭", "姐，那块拼图还你，那我也一起拼。"),
            ("灿灿", "行，算你识相，别哭了。"),
        ),
    ),
    (
        ("娃娃", "自砸", "自伤", "抢玩具"),
        (
            ("昭昭", "你干嘛砸自己？还没玩完呢，我就不给！"),
            ("灿灿", "那我也一起收，给你给你吧！"),
        ),
    ),
)
_G_GENERIC_PAIR = (
    ("昭昭", "姐，那我也来帮你。"),
    ("灿灿", "行，算你识相。"),
)


def _compact(text: str) -> str:
    return re.sub(r"[，,。！!？?\s]+", "", str(text or ""))


def _patch_g_min_chars(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) >= 24:
        return notes
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    if dialogue_total_chars(story) >= DAILY_STORY_BODY_CHARS_MIN:
        return notes
    pool = ["那我也一起玩！", "你干嘛呀？", "一起收拾吧！"]
    used = {_compact(item.get("line")) for item in dialogue if isinstance(item, dict)}
    for line in pool:
        if dialogue_total_chars(story) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        core = _compact(line)
        if core in used:
            continue
        last_sp = str(dialogue[-1].get("speaker") or "").strip()
        other = "灿灿" if last_sp == "昭昭" else "昭昭"
        dialogue.append({"speaker": other, "line": line})
        used.add(core)
        notes.append("G补字数行动句")
    return notes


def patch_g_body(story: dict) -> list[str]:
    """G 缺 pivot/愣住/暖收时，补一对行动跟随短句兜底。"""
    notes: list[str] = []
    if str(story.get("story_type") or "").strip().upper() != "G":
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    lines = [
        str(item.get("line") or "")
        for item in dialogue
        if isinstance(item, dict)
    ]
    body = "".join(lines)
    tail = "".join(lines[-3:])
    has_pivot = bool(
        g_humor.RE_PIVOT.search(body)
        or g_humor.RE_BEHAVIOR_SOFTEN.search(body)
    )
    has_stun = bool(g_humor.RE_STUNNED.search(body))
    has_soft = bool(
        g_humor.RE_SOFT.search(tail)
        or g_humor.RE_BEHAVIOR_SOFTEN.search(tail)
        or g_humor.RE_PIVOT.search(tail)
    )
    if has_pivot and has_stun and has_soft:
        return notes

    conflict = f"{story.get('conflict_core') or ''}{story.get('setting') or ''}"
    pair = _G_GENERIC_PAIR
    for keys, candidate in _G_PAIRS:
        if any(key in conflict for key in keys):
            pair = candidate
            break

    used = {_compact(item.get("line")) for item in dialogue if isinstance(item, dict)}
    for speaker, line in pair:
        core = _compact(line)
        if core in used:
            continue
        dialogue.append({"speaker": speaker, "line": line})
        used.add(core)
        notes.append(f"G补行动跟随[{speaker}]")
    if len(dialogue) > 24:
        dialogue[:] = dialogue[:24]
    notes.extend(_patch_g_min_chars(story))
    return notes
