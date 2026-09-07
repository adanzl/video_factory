"""P 类正文本地修稿（轻量：认怂后截第二轮 + 剥垫字）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.p.validate import (
    RE_INIT_OFFER,
    RE_OFFER,
    RE_PAD_TAIL,
    RE_SURRENDER,
)

_P_CLOSING_TAIL_ALLOW = 3
_RE_SECOND_ROUND = re.compile(
    r"再来一次|再试试|偏不信|你敢不敢|继续加|再开一局|"
    r"不行嘛了呀|不行好不好|真的不行好不好|我偏就|我可记住"
)
_RE_PAD_CLAUSE = re.compile(
    r"[，,。！!]+\s*(?:"
    r"马上给我挪开|我才不怕呢|不许再耍赖了?|我偏就不信|"
    r"好不好呀|了呢|着呢"
    r")[^。！!]*"
)


def _dialogue_rows(story: dict) -> list[dict]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        d
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def patch_p_trim_after_surrender(story: dict) -> list[str]:
    """认怂落位后删第二轮再开挑战拖尾。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    rows = _dialogue_rows(story)
    surrender = [
        i
        for i, d in enumerate(rows)
        if RE_SURRENDER.search(str(d.get("line") or ""))
    ]
    if not surrender:
        return notes
    close_idx = surrender[-1]
    after = rows[close_idx + 1 :]
    if len(after) <= _P_CLOSING_TAIL_ALLOW and not any(
        _RE_SECOND_ROUND.search(str(d.get("line") or "")) for d in after
    ):
        return notes
    kept = list(rows[: close_idx + 1])
    extra: list[dict] = []
    for item in after:
        line = str(item.get("line") or "")
        if _RE_SECOND_ROUND.search(line):
            continue
        if len(extra) < _P_CLOSING_TAIL_ALLOW:
            extra.append(item)
    kept.extend(extra)
    removed = len(rows) - len(kept)
    if removed <= 0:
        return notes
    # 截太狠会掉 gold_chat 句数硬卡（≥12）
    if len(kept) < 12:
        return notes
    story["dialogue"] = kept
    notes.append(f"P认怂后截第二轮{removed}句")
    return notes


def patch_p_strip_pad_tails(story: dict) -> list[str]:
    """剥垫字尾巴分句。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    n = 0
    for item in rows:
        line = str(item.get("line") or "")
        cleaned = _RE_PAD_CLAUSE.sub("", line).rstrip("，, ")
        if RE_PAD_TAIL.search(cleaned):
            cleaned = RE_PAD_TAIL.sub("", cleaned).rstrip("，, ")
        if cleaned and cleaned[-1] not in "。！!…？?":
            cleaned += "！"
        if cleaned != line and cleaned.strip():
            item["line"] = cleaned
            n += 1
    if n:
        notes.append(f"P剥垫字尾巴{n}句")
    return notes


def patch_p_fix_boomerang_label(story: dict) -> list[str]:
    """key/punchline 去掉回旋镖标签，改整蛊回敬表述。"""
    notes: list[str] = []
    key = str(story.get("key") or "")
    if "回旋镖" in key:
        story["key"] = key.replace("回旋镖", "回敬").strip() or "整蛊回敬"
        notes.append("P key 去回旋镖标签")
    punch = str(story.get("punchline_explain") or "")
    if "回旋镖" in punch:
        story["punchline_explain"] = punch.replace("回旋镖", "回敬")
        notes.append("P punchline 去回旋镖标签")
    return notes


def patch_p_fix_surrender_speaker(story: dict) -> list[str]:
    """认怂句说话人归位到首发下料方（挑战发起人）。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    offer = [
        i
        for i, d in enumerate(rows)
        if RE_INIT_OFFER.search(str(d.get("line") or ""))
    ]
    if not offer:
        offer = [
            i
            for i, d in enumerate(rows)
            if RE_OFFER.search(str(d.get("line") or ""))
        ]
    surrender = [
        i
        for i, d in enumerate(rows)
        if RE_SURRENDER.search(str(d.get("line") or ""))
    ]
    if not offer or not surrender:
        return notes
    init_sp = str(rows[offer[0]].get("speaker") or "").strip()
    if not init_sp:
        return notes
    fixed = 0
    for i in surrender:
        sp = str(rows[i].get("speaker") or "").strip()
        if sp and sp != init_sp:
            rows[i]["speaker"] = init_sp
            fixed += 1
    if fixed:
        notes.append(f"P认怂说话人归位→{init_sp}×{fixed}")
    return notes


def patch_p_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "P":
        return notes
    notes.extend(patch_p_fix_boomerang_label(story))
    notes.extend(patch_p_strip_pad_tails(story))
    notes.extend(patch_p_fix_surrender_speaker(story))
    notes.extend(patch_p_trim_after_surrender(story))
    return notes
