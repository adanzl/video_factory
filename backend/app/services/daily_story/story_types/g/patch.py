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


_G_RETORT_POOL = (
    "你别抢！",
    "我就不给！",
    "那是我先拿到的！",
    "你快松手！",
    "你放手！",
    "还给我！",
    "别抢了！",
    "这是我先拿的！",
)


def _patch_g_break_consecutive(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    used = {_compact(item.get("line")) for item in dialogue if isinstance(item, dict)}
    for _ in range(6):
        hit = -1
        for i in range(1, len(dialogue)):
            a, b = dialogue[i - 1], dialogue[i]
            if not isinstance(a, dict) or not isinstance(b, dict):
                continue
            sa = str(a.get("speaker") or "").strip()
            sb = str(b.get("speaker") or "").strip()
            if sa in {"昭昭", "灿灿"} and sa == sb:
                hit = i
                break
        if hit < 0:
            break
        other = "灿灿" if str(dialogue[hit - 1].get("speaker") or "").strip() == "昭昭" else "昭昭"
        picked = ""
        for retort in _G_RETORT_POOL:
            core = _compact(retort)
            if core not in used:
                picked = retort
                used.add(core)
                break
        if not picked:
            break
        dialogue.insert(hit, {"speaker": other, "line": picked})
        notes.append(f"G插接话断连说[{hit + 1}]")
    return notes


def patch_g_body(story: dict) -> list[str]:
    """G 缺 pivot/愣住/暖收时补行动跟随；连说与 near-miss 每次都收口。"""
    notes: list[str] = []
    if str(story.get("story_type") or "").strip().upper() != "G":
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes

    from app.services.gold_story.scene import (
        patch_dialogue_narration_to_speech,
    )

    notes.extend(patch_dialogue_narration_to_speech(story))
    # 先断同人连说、补 near-miss；再做 pivot/stun/soft 判定。
    notes.extend(_patch_g_break_consecutive(story))
    notes.extend(_patch_g_min_chars(story))

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

    parts: list[str] = []
    if not has_stun:
        parts.append("你干嘛呀？")
    if not has_pivot:
        parts.append("还没玩完呢，")
    if not has_soft or not has_pivot:
        parts.append("那我也一起玩！")
    line = "".join(parts).strip()
    if not line:
        return notes

    used = {_compact(item.get("line")) for item in dialogue if isinstance(item, dict)}
    core = _compact(line)
    if core not in used:
        last_sp = str(dialogue[-1].get("speaker") or "").strip()
        other = "灿灿" if last_sp == "昭昭" else "昭昭"
        dialogue.append({"speaker": other, "line": line})
        notes.append("G补行动跟随句")
    notes.extend(_patch_g_break_consecutive(story))
    notes.extend(_patch_g_min_chars(story))
    return notes
