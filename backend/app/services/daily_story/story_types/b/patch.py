"""B 类正文本地修稿（确定性结构修补）。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地，
  以及不含主题词的类型通用短句（如「完了完了！」）。
- 禁止绑定具体 theme 的规则（按主题关键词分支改写台词）。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

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

# 句尾/句内无意义语气垫字（对齐 E；B 额外含真的呀/好不好）——本地剥，不整段重试
_RE_FILLER_TAIL = re.compile(
    r"(?:[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}|"
    r"了呢[了呀]|了呀[呢]|嘛了[呀]|了呢呀|"
    r"了呢|了呀|嘛了|呢吧|呀呢|呢嘛|真的呀|好不好)$",
)
_RE_FILLER_INLINE = re.compile(
    r"呢了呀|了呢呀|嘛了呀|了呀呢|真的呀",
)


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


def patch_b_strip_filler(story: dict) -> list[str]:
    """一句一改：剥句尾/句内无意义语气垫字（了呢了呀/真的呀/好不好等），
    走本地修稿而非整段重试（整段重试失败率高且可能引入新伤）。"""
    notes: list[str] = []
    if not _is_b(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = _RE_FILLER_INLINE.sub("", line)
        new_line = _RE_FILLER_TAIL.sub("", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"B剥垫字[{i}]")
    return notes


def patch_b_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_b_split_consecutive(story))
    notes.extend(patch_b_orphan_ye(story))
    notes.extend(patch_b_ensure_pre_punish_blame(story))
    notes.extend(patch_b_merge_mom_lines(story))
    notes.extend(patch_b_shorten_freeze(story))
    notes.extend(patch_b_strip_filler(story))
    return notes
