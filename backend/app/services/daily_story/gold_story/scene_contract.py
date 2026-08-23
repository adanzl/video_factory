"""H3a scene_contract：可拍场景契约 + 成品对白 hard 校验。"""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES

ALLOWED_SPEAKERS = frozenset(DAILY_STORY_SPEAKER_NAMES)
ILLEGAL_SPEAKER_HINTS = (
    "爸爸",
    "父亲",
    "小男孩",
    "小女孩",
    "陌生",
    "对方",
    "老师",
    "博主",
    "哥哥",
    "妹妹",
)
TUTORIAL_RESIDUE = (
    "第一招",
    "第二招",
    "第三招",
    "第四招",
    "四招",
    "方法",
    "经验分享",
    "应该",
    "告诉",
    "教会",
)
MOM_BANNED_IN_LINE = ("应该", "告诉", "记住", "教")
_PAREN_IN_LINE = re.compile(r"（[^）]*）|\([^)]*\)")
_RELAY_SPEECH = re.compile(
    r"(?:妈妈|爸爸)(?:说了|说，|教过|告诉我|说过)|"
    r"你上次说的呀|一位(?:妈妈|爸爸)|经验分享|第[一二三四1-4]招"
)

CHAT_LINE_COUNT_MIN = 12
CHAT_LINE_COUNT_MAX = 24
CHAT_MAX_LINE_CHARS = 30
CHAT_AVG_LINE_CHARS_MAX = 22
SEED_MIN = 4
BEAT_CHAIN_MIN = 4


def format_beat_chain(chain: list[Any]) -> str:
    lines: list[str] = []
    for i, item in enumerate(chain or [], start=1):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or item.get("beat") or "").strip()
        if sp and intent:
            lines.append(f"{i}. {sp}：{intent}")
    return "\n".join(lines)


def format_scene_contract_block(contract: dict[str, Any]) -> str:
    """注入块 / gold_chat 用的 scene_contract 文本。"""
    if not isinstance(contract, dict):
        return "（无 scene_contract）"
    parts = [
        "【可拍场景契约 scene_contract】",
        f"source_type: {contract.get('source_type') or 'field'}",
        f"location: {contract.get('location') or ''}",
        f"object: {contract.get('object') or ''}",
        f"characters: {', '.join(contract.get('characters') or [])}",
        f"conflict: {contract.get('conflict') or ''}",
        f"mechanism: {contract.get('mechanism') or ''}",
        f"mom_lines_max: {contract.get('mom_lines_max', 0)}",
        f"remap_note: {contract.get('remap_note') or ''}",
        "beat_chain:",
        format_beat_chain(contract.get("beat_chain") or []) or "（无）",
    ]
    closing = str(contract.get("closing_intent") or "").strip()
    if closing:
        parts.append(f"closing_intent: {closing}")
    banned = contract.get("banned_literals") or []
    if banned:
        parts.append(
            "banned_literals: "
            + "、".join(str(x) for x in banned if str(x).strip())
        )
    return "\n".join(parts)


def _line_lens(dialogue: list[Any]) -> list[int]:
    return [
        len(str(item.get("line") or ""))
        for item in dialogue
        if isinstance(item, dict) and str(item.get("line") or "").strip()
    ]


def validate_scene_contract(contract: dict[str, Any] | None) -> list[str]:
    """H3a / H4a 规则：scene_contract 硬卡。"""
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["scene_contract_missing"]
    chars = contract.get("characters") or []
    if not isinstance(chars, list) or not chars:
        errors.append("scene_contract_characters_empty")
    else:
        for name in chars:
            n = str(name or "").strip()
            if n and n not in ALLOWED_SPEAKERS:
                errors.append(f"scene_contract_illegal_character:{n}")
    chain = contract.get("beat_chain") or []
    if not isinstance(chain, list) or len(chain) < BEAT_CHAIN_MIN:
        errors.append(f"beat_chain_too_short:{len(chain) if isinstance(chain, list) else 0}")
    else:
        for i, row in enumerate(chain):
            if not isinstance(row, dict):
                errors.append(f"beat_chain[{i}]_invalid")
                continue
            sp = str(row.get("speaker") or "").strip()
            if sp not in ALLOWED_SPEAKERS:
                errors.append(f"beat_chain[{i}]_speaker_illegal:{sp!r}")
    source_type = str(contract.get("source_type") or "").strip().lower()
    if source_type == "tutorial":
        check_blob = f"{contract.get('conflict')} {contract.get('mechanism')} {contract.get('remap_note')}"
        for word in TUTORIAL_RESIDUE:
            if word in check_blob:
                errors.append(f"tutorial_residue_in_contract:{word}")
    return errors


def validate_dialogue_seed_speakers(seed: list[Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(seed, list) or len(seed) < SEED_MIN:
        errors.append(f"dialogue_seed_too_short:{len(seed) if isinstance(seed, list) else 0}")
        return errors
    for i, row in enumerate(seed):
        if not isinstance(row, dict):
            errors.append(f"dialogue_seed[{i}]_invalid")
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp not in ALLOWED_SPEAKERS:
            errors.append(f"dialogue_seed[{i}]_speaker_illegal:{sp!r}")
    return errors


def collect_voice_errors(dialogue: list[Any]) -> list[str]:
    errors: list[str] = []
    for i, item in enumerate(dialogue or []):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        if _PAREN_IN_LINE.search(line):
            errors.append(f"dialogue[{i}] 含括号说明，须改为当场对白")
        elif _RELAY_SPEECH.search(line):
            errors.append(f"dialogue[{i}] 像转述/论述，须改为第一人称现场对白")
    return errors


def validate_chat_hard(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "",
    mom_lines_max: int | None = None,
) -> list[str]:
    """gold_chat / 成品对白 hard 校验。"""
    errors: list[str] = []
    dialogue = story.get("dialogue") or []
    if not isinstance(dialogue, list):
        return ["dialogue 不是列表"]

    allowed = set(ALLOWED_SPEAKERS)
    mom_max = 1 if mom_lines_max is None else max(0, int(mom_lines_max))
    mom_count = 0

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            errors.append(f"dialogue[{i}] 不是字典")
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in allowed:
            errors.append(f"dialogue[{i}] speaker 非法: {sp!r}")
        if not line:
            errors.append(f"dialogue[{i}] line 为空")
        if sp == "妈妈":
            mom_count += 1
            if any(w in line for w in MOM_BANNED_IN_LINE):
                errors.append(f"dialogue[{i}] 妈妈台词像说教")

    if mom_count > mom_max:
        errors.append(f"妈妈台词须≤{mom_max}句，当前{mom_count}")

    line_count = len([x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()])
    if line_count < CHAT_LINE_COUNT_MIN:
        errors.append(f"对白句数须≥{CHAT_LINE_COUNT_MIN}，当前{line_count}")
    if line_count > CHAT_LINE_COUNT_MAX:
        errors.append(f"对白句数须≤{CHAT_LINE_COUNT_MAX}，当前{line_count}")

    lenses = _line_lens(dialogue if isinstance(dialogue, list) else [])
    if lenses:
        if max(lenses) > CHAT_MAX_LINE_CHARS:
            errors.append(f"单句过长(max={max(lenses)}>{CHAT_MAX_LINE_CHARS})")
        avg = mean(lenses)
        if avg > CHAT_AVG_LINE_CHARS_MAX:
            errors.append(f"均句过长({avg:.1f}>{CHAT_AVG_LINE_CHARS_MAX})")

    total = dialogue_total_chars(story)
    if total < DAILY_STORY_BODY_CHARS_MIN:
        errors.append(f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前{total}")
    if total > DAILY_STORY_BODY_CHARS_MAX:
        errors.append(f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}")

    if line_count > 0:
        last_sp = str(dialogue[-1].get("speaker") or "").strip() if isinstance(dialogue[-1], dict) else ""
        if last_sp == "妈妈":
            errors.append("末句不能是妈妈")

    banned = [str(x).strip() for x in (banned_literals or []) if str(x).strip()]
    if banned:
        body = "\n".join(
            str(item.get("line") or "")
            for item in dialogue
            if isinstance(item, dict)
        )
        hits = [w for w in banned if w and w in body]
        if hits:
            errors.append(f"对白含禁词: {'、'.join(hits[:5])}")

    st = str(source_type or "").strip().lower()
    if st == "tutorial":
        body = "\n".join(str(item.get("line") or "") for item in dialogue if isinstance(item, dict))
        for word in TUTORIAL_RESIDUE:
            if word in body:
                errors.append(f"tutorial_residue_in_dialogue:{word}")

    errors.extend(collect_voice_errors(dialogue))
    return errors


def seed_from_beat_chain(chain: list[Any]) -> list[dict[str, str]]:
    """beat_chain → dialogue_seed 兜底。"""
    out: list[dict[str, str]] = []
    for row in chain or []:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        intent = str(row.get("intent") or row.get("beat") or "").strip()
        if sp in ALLOWED_SPEAKERS and intent:
            out.append({"speaker": sp, "intent": intent})
    return out
