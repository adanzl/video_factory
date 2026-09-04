"""H3a scene_contract：可拍场景契约。"""

from __future__ import annotations

import re
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
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
_REMAP_SIBLING_TERMS = re.compile(r"哥哥|弟弟")

CHAT_LINE_COUNT_MIN = 12
CHAT_LINE_COUNT_MAX = 24
CHAT_MAX_LINE_CHARS = DAILY_STORY_LINE_CHARS_MAX
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


def format_scene_block(contract: dict[str, Any]) -> str:
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


def validate_scene(contract: dict[str, Any] | None) -> list[str]:
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


_NARRATION_LINE_RE = re.compile(
    r"(?:^|[，,])"
    r"(?:松手|转身离开|愣住|留下面面相觑|推向(?:灿灿|昭昭)|"
    r"放下牛奶|心里不是滋味，但坚持)|"
    # 第三人称分镜/动作说明（抽象形态，非单篇词表）
    r"被(?:灿灿|昭昭|妈妈)[^。！？]{0,20}|"
    r"^(?:叹气|愣住)[，,]|"
    r"(?:一把|挣扎着|护着手)[^。！？]{0,24}"
    r"(?:揪|按|拍|打|推|抓)|"
    r"(?:揪住|按住|推向)(?:昭昭|灿灿|她|他)|"
    r"按在地上|"
    r"又?补[一二两三四五两1-5]?下|"
    r"缩到角落|嘟囔着|一边[^，。]{0,10}一边|"
    r"(?:哼，)?(?:缩到|嘟囔|趴下|扭头走开)"
)
_RE_ACTION_CHUNK = re.compile(
    r"又?补[一二两三四五两1-5]?下|按在地上|"
    r"(?:一把|挣扎着|护着手)[^。！？]{0,24}(?:揪|按|拍|打|推|抓)|"
    r"(?:揪住|按住|推向)(?:昭昭|灿灿|她|他)|"
    r"被(?:灿灿|昭昭|妈妈)[^。！？]{0,16}|"
    r"缩到角落|嘟囔着|"
    r"^(?:叹气|愣住)$"
)


def looks_like_narration_line(text: str) -> bool:
    """对白/seed 是否像分镜动作说明而非可说出口的话。"""
    line = str(text or "").strip()
    return bool(line and _NARRATION_LINE_RE.search(line))


def rewrite_narration_to_speech(text: str, *, speaker: str = "") -> str:
    """把动作说明压成可说出口的短句；无口语尾巴则给抽象兜底。"""
    raw = str(text or "").strip()
    if not raw or not looks_like_narration_line(raw):
        return raw
    sp = str(speaker or "").strip()
    fallback = (
        "唉，我管不了你们了" if sp in {"妈妈", "爸爸"} else "你别过来！"
    )
    parts = [p.strip() for p in re.split(r"[，,]", raw) if p.strip()]
    spoken: list[str] = []
    for part in parts:
        # 纯动作块即使带「我」也剥掉（如「我补两下」）
        if _RE_ACTION_CHUNK.search(part) and not re.search(
            r"[？！]|疼|怕|不服|活该|警告|别逼|松手",
            part,
        ):
            cleaned = _RE_ACTION_CHUNK.sub("", part).strip("，。！？ ")
            cleaned = re.sub(r"^我$", "", cleaned).strip()
            if cleaned and re.search(r"[我你]|疼|怕|警告|别", cleaned):
                spoken.append(cleaned)
            continue
        if looks_like_narration_line(part) and not re.search(
            r"[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了",
            part,
        ):
            continue
        if re.search(
            r"[我你]|[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了|劝不",
            part,
        ):
            spoken.append(part)
    if spoken:
        out = spoken[0]
        for part in spoken[1:]:
            if out and out[-1] in "？！。!?":
                out = f"{out}{part}"
            else:
                out = f"{out}，{part}"
        out = _RE_ACTION_CHUNK.sub("", out)
        out = re.sub(r"[？！。!?][，,]+", lambda m: m.group(0)[0], out)
        out = re.sub(r"[，,]{2,}", "，", out)
        out = re.sub(r"(?:^|[，,])我(?=[，,]|$)", "", out)
        out = out.strip("，。 ")
        if not out:
            return fallback
        if looks_like_narration_line(out):
            return fallback
        if out[-1] not in "？！。!?":
            out = f"{out}！"
        return out
    return fallback


def sanitize_dialogue_seed_speech(seed: list[Any] | None) -> list[Any]:
    """seed intent/line 若是分镜说明，压成可说出口的话（全类型通用）。"""
    if not isinstance(seed, list):
        return []
    out: list[Any] = []
    for item in seed:
        if not isinstance(item, dict):
            out.append(item)
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        key = "intent" if str(row.get("intent") or "").strip() else "line"
        text = str(row.get(key) or "").strip()
        if text and looks_like_narration_line(text):
            row[key] = rewrite_narration_to_speech(text, speaker=sp)
        out.append(row)
    return out


def patch_dialogue_narration_to_speech(story: dict[str, Any]) -> list[str]:
    """正文对白里的分镜说明压成口语。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not looks_like_narration_line(line):
            continue
        new_line = rewrite_narration_to_speech(line, speaker=sp)
        if looks_like_narration_line(new_line):
            new_line = (
                "唉，我管不了你们了"
                if sp in {"妈妈", "爸爸"}
                else "你别过来！"
            )
        if new_line != line:
            item["line"] = new_line
            notes.append(f"旁白→口语[{i + 1}]")
    return notes


def collect_narration_dialogue_errors(dialogue: list[Any]) -> list[str]:
    """分镜/动作句误当对白。"""
    errors: list[str] = []
    for i, item in enumerate(dialogue or []):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if looks_like_narration_line(line):
            errors.append(f"dialogue[{i}] narration_not_speech")
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
        elif _REMAP_SIBLING_TERMS.search(line):
            errors.append(
                f"dialogue[{i}] 含站外称谓哥哥/弟弟，须改姐姐/昭昭/灿灿"
            )
    return errors


# banned_literals 仅保留站外真名 / 须 remap 的 speaker 称谓（H3 prompt 对齐）
SPEAKER_REMAP_BANNED: frozenset[str] = frozenset(
    {
        "哥哥",
        "妹妹",
        "弟弟",
        "姐姐",
        "小男孩",
        "小女孩",
        "爸爸",
        "父亲",
        "母亲",
        "宝爸",
        "宝妈",
        "老爸",
        "对方",
        "陌生小孩",
        "对方家长",
        "对方妈妈",
        "对方爸爸",
        "小朋友",
        "对方孩子",
    },
)

# 常见 scene / 笑点词，禁止 LLM 误写入 banned_literals
_BANNED_LITERAL_NEVER: frozenset[str] = frozenset(
    {
        "画画",
        "碘伏",
        "朋友圈",
        "涂药",
        "扭打",
        "相声",
    },
)

_SURNAME_HINT = re.compile(r"[贾赵李王张刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁]")


def _scene_core_blob(
    scene_contract: dict[str, Any] | None,
    beat: list[Any] | None,
) -> str:
    sc = scene_contract or {}
    parts: list[str] = [
        str(sc.get("object") or ""),
        str(sc.get("conflict") or ""),
        str(sc.get("mechanism") or ""),
        str(sc.get("closing_intent") or ""),
        str(sc.get("location") or ""),
    ]
    for row in sc.get("beat_chain") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or row.get("beat") or ""))
    for item in beat or []:
        parts.append(str(item or ""))
    return "".join(parts)


def _is_source_proper_name(word: str) -> bool:
    w = str(word or "").strip()
    if len(w) < 3 or len(w) > 8:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]+", w):
        return False
    if w in _BANNED_LITERAL_NEVER:
        return False
    return bool(_SURNAME_HINT.search(w))


def sanitize_banned_literals(
    banned: list[Any] | None,
    *,
    scene_contract: dict[str, Any] | None = None,
    beat: list[Any] | None = None,
) -> list[str]:
    """过滤 H3 误伤的 scene/笑点词，只留 remap 称谓与站外真名。"""
    core = _scene_core_blob(scene_contract, beat)
    out: list[str] = []
    seen: set[str] = set()
    for raw in banned or []:
        w = str(raw or "").strip()
        if not w or w in seen:
            continue
        if w in _BANNED_LITERAL_NEVER:
            continue
        if w in core:
            continue
        if w in SPEAKER_REMAP_BANNED or _is_source_proper_name(w):
            seen.add(w)
            out.append(w)
    return out


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
