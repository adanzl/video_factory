"""O 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.o.validate import (
    RE_GOAL_PUNCH,
    RE_O_GLOAT_CHARITY,
    RE_O_GLOAT_CONTINUE,
    RE_O_LAUGH_CLOSE,
    RE_O_OTHER_SPOILER,
    RE_O_POST_GLOAT_QUARREL,
    RE_O_POST_PUNCH_CONTINUE,
    RE_O_PUNCH_SOFT_CHALLENGE,
    RE_O_PUNCH_TAIL_JUNK,
    RE_O_RESULT_GLOAT,
    RE_O_WIN_CLAIM,
)

_O_CLOSING_TAIL_ALLOW = 2
# 得意收束句中剥离续赛分句（抽象）
_RE_O_CONTINUE_CLAUSE = re.compile(
    r"[，,。！!]+\s*(?:你)?(?:"
    r"慢慢来|慢慢赢|再来(?:一局|一把)?(?:吧)?|再比|继续比|不许再耍赖|"
    r"马上给我挪开|这块给你|给你吧|留给你|剩的给你"
    r")[^。！!]*"
)
# 点题句剥离不服/不公平申诉尾巴（保留呜呜等情绪音）
_RE_O_PUNCH_SOFT_TAIL = re.compile(
    r"[，,]\s*(?:不公平|太不公|不服气?|我不服)[^。！!]*[。！!]?"
)
# 点题句尾垫字碎片
_RE_O_PUNCH_JUNK_TAIL = re.compile(
    r"[，,。！!…]*\s*(?:了呢|真的了呢|嘛了呀|了呀)[。！!…]*$"
)


def _dialogue_rows(story: dict) -> list[dict]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [d for d in dialogue if isinstance(d, dict) and str(d.get("line") or "").strip()]


def _is_o_closing_laugh(item: dict) -> bool:
    line = str(item.get("line") or "")
    speaker = str(item.get("speaker") or "").strip()
    if RE_O_POST_PUNCH_CONTINUE.search(line):
        return False
    if RE_O_POST_GLOAT_QUARREL.search(line):
        return False
    # 点题后对手再喊「我赢」不算笑场
    if speaker != "妈妈" and re.search(r"我赢|赢啦|赢了呀", line):
        return False
    if RE_O_LAUGH_CLOSE.search(line):
        return True
    # 妈妈旁观笑场：短感叹即可
    if speaker == "妈妈" and re.search(r"哈哈|真逗|你们|笑", line):
        return True
    return False


def patch_o_clean_punch_soft_tail(story: dict) -> list[str]:
    """点题认栽句去掉不公平/不服申诉尾巴与垫字碎片。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    item = rows[punch[-1]]
    line = str(item.get("line") or "")
    cleaned = line
    if RE_O_PUNCH_SOFT_CHALLENGE.search(cleaned):
        cleaned = _RE_O_PUNCH_SOFT_TAIL.sub("", cleaned).rstrip("，, ")
    if RE_O_PUNCH_TAIL_JUNK.search(cleaned) or _RE_O_PUNCH_JUNK_TAIL.search(cleaned):
        cleaned = _RE_O_PUNCH_JUNK_TAIL.sub("", cleaned).rstrip("，, ….")
        # 保留呜呜情绪音时补顿号收口
        if cleaned.endswith("呜呜") or cleaned.endswith("呜呜…"):
            cleaned = cleaned.rstrip("…") + "！"
    if cleaned and cleaned[-1] not in "。！!…":
        cleaned += "！"
    if cleaned == line or not cleaned.strip():
        return notes
    item["line"] = cleaned
    notes.append("O点题句去申诉/垫字尾巴")
    return notes


def patch_o_trim_after_gloat(story: dict) -> list[str]:
    """资源溜走得意后删掉偷吃互怼句，保留其余桥接到点题。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    close_idx = punch[-1]
    gloat = [
        i
        for i, d in enumerate(rows[:close_idx])
        if RE_O_RESULT_GLOAT.search(str(d.get("line") or ""))
    ]
    if not gloat:
        return notes
    g0 = gloat[0]
    kept: list[dict] = list(rows[: g0 + 1])
    dropped = 0
    for item in rows[g0 + 1 : close_idx]:
        line = str(item.get("line") or "")
        if RE_O_POST_GLOAT_QUARREL.search(line):
            dropped += 1
            continue
        kept.append(item)
    kept.extend(rows[close_idx:])
    if dropped <= 0:
        return notes
    story["dialogue"] = kept
    notes.append(f"O得意后删互怼{dropped}句")
    return notes


def patch_o_strip_pre_punch_continue(story: dict) -> list[str]:
    """点题前得意收束句去掉续赛分句与施舍尾巴。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    close_idx = punch[-1]
    n = 0
    for item in rows[:close_idx]:
        line = str(item.get("line") or "")
        if not (
            RE_O_RESULT_GLOAT.search(line) or RE_O_LAUGH_CLOSE.search(line)
        ):
            continue
        if not (
            RE_O_POST_PUNCH_CONTINUE.search(line)
            or RE_O_GLOAT_CONTINUE.search(line)
            or RE_O_GLOAT_CHARITY.search(line)
            or "马上给我挪开" in line
        ):
            continue
        cleaned = _RE_O_CONTINUE_CLAUSE.sub("", line).rstrip("，, ")
        if cleaned and cleaned[-1] not in "。！!…":
            cleaned += "！"
        if cleaned != line and cleaned.strip():
            item["line"] = cleaned
            n += 1
    if n:
        notes.append(f"O得意收束去续赛/施舍{n}句")
    return notes


def patch_o_trim_after_punch(story: dict) -> list[str]:
    """点题认栽后只保留连续笑场/旁观；跳过中间抬杠句仍可接妈妈笑场。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    close_idx = punch[-1]
    kept = list(rows[: close_idx + 1])
    extra: list[dict] = []
    for item in rows[close_idx + 1 :]:
        if _is_o_closing_laugh(item) and len(extra) < _O_CLOSING_TAIL_ALLOW:
            extra.append(item)
            continue
    kept.extend(extra)
    removed = len(rows) - len(kept)
    if removed <= 0:
        return notes
    story["dialogue"] = kept
    notes.append(f"O点题后截断第二轮{removed}句")
    return notes


def patch_o_strip_line_junk(story: dict) -> list[str]:
    """剥全篇垫字碎片（了呢/好不好呀/再闹我恼等）。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    n = 0
    junk = re.compile(
        r"[，,]?\s*(?:再闹我恼了呢?|好不好呀|了呢|马上给我挪开(?:嘛)?|"
        r"你试试看了呢|不许再耍赖了呢)[。！!]?"
    )
    for item in rows:
        line = str(item.get("line") or "")
        cleaned = junk.sub("", line).rstrip("，, ")
        if cleaned and cleaned[-1] not in "。！!…？?":
            cleaned += "！"
        if cleaned != line and cleaned.strip():
            item["line"] = cleaned
            n += 1
    if n:
        notes.append(f"O剥垫字碎片{n}句")
    return notes


def patch_o_drop_other_spoiler(story: dict) -> list[str]:
    """点题前删掉对手「你光顾着赢」代点题句。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    close_idx = punch[-1]
    kept: list[dict] = []
    dropped = 0
    for i, item in enumerate(rows):
        if i < close_idx and RE_O_OTHER_SPOILER.search(str(item.get("line") or "")):
            dropped += 1
            continue
        kept.append(item)
    if dropped <= 0:
        return notes
    story["dialogue"] = kept
    notes.append(f"O删对手代点题{dropped}句")
    return notes


def patch_o_fix_punch_speaker(story: dict) -> list[str]:
    """点题句若落在对手嘴上，改回死磕赢赛方。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    p_i = punch[-1]
    punch_sp = str(rows[p_i].get("speaker") or "").strip()
    prior_winners = [
        str(rows[i].get("speaker") or "").strip()
        for i, d in enumerate(rows[:p_i])
        if RE_O_WIN_CLAIM.search(str(d.get("line") or ""))
    ]
    winners = [w for w in prior_winners if w]
    if not winners:
        return notes
    if punch_sp in winners:
        return notes
    # 优先昭昭（姐弟稿常见死磕方），否则取首次赢赛方
    target = "昭昭" if "昭昭" in winners else winners[0]
    if punch_sp == target:
        return notes
    rows[p_i]["speaker"] = target
    notes.append(f"O点题说话人归位→{target}")
    return notes


def patch_o_cap_win_rounds(story: dict) -> list[str]:
    """死磕赢赛超过约两轮时，删掉多余赢赛句（保留前两轮）。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    close_idx = punch[-1]
    win_idxs = [
        i
        for i, d in enumerate(rows[:close_idx])
        if RE_O_WIN_CLAIM.search(str(d.get("line") or ""))
    ]
    if len(win_idxs) < 3:
        return notes
    drop = set(win_idxs[2:])
    kept = [d for i, d in enumerate(rows) if i not in drop]
    removed = len(rows) - len(kept)
    if removed <= 0:
        return notes
    story["dialogue"] = kept
    notes.append(f"O压缩赢赛轮次删{removed}句")
    return notes


def patch_o_ensure_punch_first_person(story: dict) -> list[str]:
    """点题含光顾着赢时补上「我」。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    punch = [
        i
        for i, d in enumerate(rows)
        if RE_GOAL_PUNCH.search(str(d.get("line") or ""))
    ]
    if not punch:
        return notes
    item = rows[punch[-1]]
    line = str(item.get("line") or "")
    if "光顾着赢" in line and "我光顾着赢" not in line:
        item["line"] = line.replace("光顾着赢", "我光顾着赢", 1)
        notes.append("O点题补我光顾着赢")
    return notes


def patch_o_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "O":
        return notes
    notes.extend(patch_o_drop_other_spoiler(story))
    notes.extend(patch_o_cap_win_rounds(story))
    notes.extend(patch_o_trim_after_gloat(story))
    notes.extend(patch_o_strip_pre_punch_continue(story))
    notes.extend(patch_o_ensure_punch_first_person(story))
    notes.extend(patch_o_clean_punch_soft_tail(story))
    notes.extend(patch_o_fix_punch_speaker(story))
    notes.extend(patch_o_trim_after_punch(story))
    notes.extend(patch_o_strip_line_junk(story))
    return notes
