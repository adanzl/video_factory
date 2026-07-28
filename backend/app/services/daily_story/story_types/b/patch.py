"""B 类正文本地修稿（确定性结构修补）。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.b.humor import (
    RE_BLAME_MID,
    RE_PLAN_FAIL,
    _anaphora_scan_bounds,
    _chain_anaphora_tag,
    _find_last_mom_punish,
    analyze_pre_punish_self_preservation,
)

_MAX_CONSECUTIVE_FIXES = 4


def _is_b(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    return parse_story_type_code(punchline=punch) == "B"


def _pick_bridge_line(prev_sp: str, next_line: str) -> tuple[str, str]:
    """连说处插入短接话：(speaker, line)。"""
    alt = "昭昭" if prev_sp == "灿灿" else "灿灿"
    if RE_BLAME_MID.search(next_line):
        return (
            "昭昭",
            "完了完了！",
        ) if alt == "昭昭" else ("灿灿", "别慌！")
    if RE_PLAN_FAIL.search(next_line) or next_line.startswith("哎呀"):
        if alt == "昭昭":
            return "昭昭", "我这就来！"
        return "灿灿", "别慌！"
    if any(k in next_line for k in ("拿桶", "扫", "分工", "你拆", "我盯")):
        if alt == "昭昭":
            return "昭昭", "我这就去！"
        return "灿灿", "快点！"
    if alt == "昭昭":
        return "昭昭", "怎么办！"
    return "灿灿", "小声点！"


def patch_b_split_consecutive(story: dict) -> list[str]:
    """同人连说：插入另一方短接话，勿只改 speaker。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes

    fixes = 0
    i = 1
    while i < len(dialogue) and fixes < _MAX_CONSECUTIVE_FIXES:
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in ("昭昭", "灿灿") or sa != sb:
            i += 1
            continue
        next_line = str(b.get("line") or "")
        bridge_sp, bridge_ln = _pick_bridge_line(sa, next_line)
        if dialogue_char_count(bridge_ln) > DAILY_STORY_LINE_CHARS_MAX:
            i += 1
            continue
        dialogue.insert(i, {"speaker": bridge_sp, "line": bridge_ln})
        notes.append(f"B插接话[{i}]")
        fixes += 1
        i += 2
    return notes


def patch_b_orphan_ye(story: dict) -> list[str]:
    """「我也…」无前句动作时去掉「也」（结盟段与连锁段均扫）。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = [str(d.get("line") or "") for d in dialogue if isinstance(d, dict)]
    speakers = [str(d.get("speaker") or "") for d in dialogue if isinstance(d, dict)]
    start, end = _anaphora_scan_bounds(lines, speakers)
    if end - start < 1:
        return notes

    for i in range(start, end):
        if not isinstance(dialogue[i], dict):
            continue
        line = str(dialogue[i].get("line") or "")
        if "我也" not in line:
            continue
        prev2 = "".join(lines[max(0, i - 2) : i])
        if _chain_anaphora_tag(line, prev2) != "我也缺前句动作":
            continue
        new_line = line.replace("我也", "我", 1)
        if new_line == line:
            continue
        dialogue[i]["line"] = new_line
        lines[i] = new_line
        notes.append(f"B去也[{i}]")
    return notes


def patch_b_ensure_pre_punish_blame(story: dict) -> list[str]:
    """惩罚令前缺互甩时插 1–2 句扣分工的甩锅。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes

    lines = [str(d.get("line") or "") for d in dialogue if isinstance(d, dict)]
    speakers = [str(d.get("speaker") or "") for d in dialogue if isinstance(d, dict)]
    weak, _ = analyze_pre_punish_self_preservation(lines, speakers)
    if not weak:
        return notes

    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None or punish_i < 2:
        return notes

    prev_sp = speakers[punish_i - 1]
    if prev_sp == "灿灿":
        pair = [
            ("昭昭", "都怪你没看好！"),
            ("灿灿", "是你自己搞砸的！"),
        ]
    elif prev_sp == "昭昭":
        pair = [
            ("灿灿", "都怪你乱动！"),
            ("昭昭", "你还说我，你倒是扫啊！"),
        ]
    else:
        pair = [
            ("灿灿", "都怪你！"),
            ("昭昭", "是你先的！"),
        ]

    insert_at = punish_i
    for sp, ln in reversed(pair):
        if dialogue_char_count(ln) > DAILY_STORY_LINE_CHARS_MAX:
            continue
        dialogue.insert(insert_at, {"speaker": sp, "line": ln})
    notes.append(f"B补甩锅[{insert_at}]")
    return notes


def patch_b_merge_mom_lines(story: dict) -> list[str]:
    """妈妈连续两句时合并为一句（物证+短令）。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes

    i = 1
    while i < len(dialogue):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        if str(a.get("speaker") or "").strip() != "妈妈":
            i += 1
            continue
        if str(b.get("speaker") or "").strip() != "妈妈":
            i += 1
            continue
        left = str(a.get("line") or "").rstrip("。！？…")
        right = str(b.get("line") or "").strip()
        sep = "，" if not left.endswith(("！", "!", "？")) else ""
        merged = f"{left}{sep}{right}"
        if dialogue_char_count(merged) > DAILY_STORY_LINE_CHARS_MAX:
            i += 1
            continue
        a["line"] = merged
        dialogue.pop(i)
        notes.append(f"B并妈妈句[{i - 1}]")
    return notes


def patch_b_shorten_freeze(story: dict) -> list[str]:
    """定格句过长时压成短反应。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    from app.services.daily_story.story_types.b.humor import (
        _freeze_line_verbose,
        _punish_freeze_react,
    )

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    lines = [str(d.get("line") or "") for d in dialogue if isinstance(d, dict)]
    speakers = [str(d.get("speaker") or "") for d in dialogue if isinstance(d, dict)]
    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None:
        return notes

    for i in range(punish_i + 1, min(len(dialogue), punish_i + 4)):
        if not isinstance(dialogue[i], dict):
            continue
        sp = str(dialogue[i].get("speaker") or "").strip()
        if sp not in ("昭昭", "灿灿"):
            continue
        line = str(dialogue[i].get("line") or "")
        if not _punish_freeze_react(line) or not _freeze_line_verbose(line):
            continue
        if "死定了" in line or "完蛋" in line:
            new_line = "这下死定了……"
        else:
            new_line = "被发现了！"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            dialogue[i]["line"] = new_line
            notes.append(f"B压定格[{i}]")
    return notes


def patch_b_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_b_split_consecutive(story))
    notes.extend(patch_b_orphan_ye(story))
    notes.extend(patch_b_ensure_pre_punish_blame(story))
    notes.extend(patch_b_merge_mom_lines(story))
    notes.extend(patch_b_shorten_freeze(story))
    return notes
