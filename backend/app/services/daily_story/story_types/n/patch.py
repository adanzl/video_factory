"""N 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.n.validate import (
    RE_CHALLENGE,
    RE_SOLEMN_REASON,
    RE_STUN_CLOSE,
    RE_WHY,
)

_N_CLOSING_TAIL_ALLOW = 2
_RE_SECOND_ROUND = re.compile(
    r"那我再问|再说一遍|你听清楚|不对不对|重新选|再选一次"
)


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def patch_n_promote_existing_question_to_challenge(story: dict) -> list[str]:
    """已有普通问句但缺设问槽时，仅加「你说」框架，不新增剧情事实。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    body = "".join(_dialogue_lines(story))
    if RE_CHALLENGE.search(body):
        return []

    # 优先用追问前问句；若 LLM 把原 challenge 漂到后段，仍只显式化现成问句，
    # 不搬句、不新增剧情。gold_chat 类型硬卡只要求槽位存在，避免机械重排引出连说/seed 副作用。
    why_idx = next(
        (
            i
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and RE_WHY.search(str(item.get("line") or ""))
        ),
        len(dialogue),
    )
    candidate_idxs = list(range(why_idx)) + list(range(why_idx + 1, len(dialogue)))
    for idx in candidate_idxs:
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line or RE_WHY.search(line):
            continue
        is_question = line.endswith(("？", "?")) or bool(
            re.search(r"吗[？?]?$|呢[？?]?$|是不是|要不要|能不能|该不该", line)
        )
        if not is_question:
            continue
        promoted = f"你说，{line}"
        # 只做不触碰单句硬上限的安全原位改写。
        if len(promoted) > DAILY_STORY_LINE_CHARS_MAX:
            continue
        item["line"] = promoted
        return [f"N已有问句补设问框架第{idx + 1}句"]
    return []


def patch_n_ensure_solemn_reason(story: dict) -> list[str]:
    """追问后已有回答但缺因果连接词时，只显式化原回答，不编新理由。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    body = "".join(_dialogue_lines(story))
    if RE_SOLEMN_REASON.search(body):
        return []

    for why_idx, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        why_line = str(item.get("line") or "").strip()
        if not RE_WHY.search(why_line):
            continue
        why_speaker = str(item.get("speaker") or "").strip()
        # 只看紧随追问的局部回答窗；遇到愣住收束即停止，避免改成「因为行吧」。
        for answer_idx in range(why_idx + 1, min(len(dialogue), why_idx + 4)):
            answer = dialogue[answer_idx]
            if not isinstance(answer, dict):
                continue
            line = str(answer.get("line") or "").strip()
            if not line:
                continue
            if RE_STUN_CLOSE.search(line):
                break
            speaker = str(answer.get("speaker") or "").strip()
            if why_speaker and speaker == why_speaker:
                continue
            if RE_WHY.search(line) or line.endswith(("？", "?")):
                continue
            answer["line"] = f"因为{line}"
            return [f"N追问后补自洽连接词第{answer_idx + 1}句"]
        break
    return []


def patch_n_promote_existing_reaction_to_stun(story: dict) -> list[str]:
    """荒诞自洽后已有对方反应但缺愣住槽时，只显式化反应，不新增剧情。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    body = "".join(_dialogue_lines(story))
    if RE_STUN_CLOSE.search(body):
        return []

    reason_idxs = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and RE_SOLEMN_REASON.search(str(item.get("line") or ""))
    ]
    # 从最后一个已成立的自洽理由向后找局部反应，并优先取窗口内最后一个安全反应，
    # 让「行吧」尽量靠近收束，避免把中段普通接话过早标成愣住。
    for reason_idx in reversed(reason_idxs):
        reason_item = dialogue[reason_idx]
        reason_speaker = str(reason_item.get("speaker") or "").strip()
        candidates: list[tuple[int, str]] = []
        for idx in range(reason_idx + 1, min(len(dialogue), reason_idx + 5)):
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            speaker = str(item.get("speaker") or "").strip()
            if not line or (reason_speaker and speaker == reason_speaker):
                continue
            if RE_WHY.search(line) or RE_SOLEMN_REASON.search(line):
                continue
            if line.endswith(("？", "?")) or _RE_SECOND_ROUND.search(line):
                continue
            if line.startswith("好吧"):
                promoted = f"行吧{line[2:]}"
            else:
                promoted = f"行吧，{line}"
            if len(promoted) <= DAILY_STORY_LINE_CHARS_MAX:
                candidates.append((idx, promoted))
        if candidates:
            idx, promoted = candidates[-1]
            dialogue[idx]["line"] = promoted
            return [f"N自洽后显式化愣住反应第{idx + 1}句"]
    return []


def patch_n_trim_after_stun(story: dict) -> list[str]:
    """荒诞自洽/愣住落位后删第二轮抬杠拖尾。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    lines = _dialogue_lines(story)
    stun = [i for i, ln in enumerate(lines) if RE_STUN_CLOSE.search(ln)]
    reason = [i for i, ln in enumerate(lines) if RE_SOLEMN_REASON.search(ln)]
    if not stun and not reason:
        return notes
    close_idx = stun[-1] if stun else reason[-1]
    min_keep = close_idx + 1 + _N_CLOSING_TAIL_ALLOW
    removed = 0
    while len(dialogue) > min_keep:
        tail_line = (
            str(dialogue[-1].get("line") or "")
            if isinstance(dialogue[-1], dict)
            else ""
        )
        if not _RE_SECOND_ROUND.search(tail_line):
            break
        dialogue.pop()
        removed += 1
    if removed:
        story["dialogue"] = dialogue
        notes.append(f"N愣住后剔除第二轮拖尾{removed}句")
    return notes


def patch_n_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "N":
        return notes
    notes.extend(patch_n_promote_existing_question_to_challenge(story))
    notes.extend(patch_n_ensure_solemn_reason(story))
    notes.extend(patch_n_promote_existing_reaction_to_stun(story))
    notes.extend(patch_n_trim_after_stun(story))
    return notes
