"""H3a scene_contract：可拍场景契约。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES

ALLOWED_SPEAKERS = frozenset(DAILY_STORY_SPEAKER_NAMES)
ILLEGAL_SPEAKER_HINTS = (
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


_TERMINAL_NO_REPLY_RE = re.compile(
    r"(?:不再|没再|不敢再)(?:接话|搭话|回话|顶嘴|回嘴|反驳|说话)|"
    r"(?:不|没)(?:接话|搭话|回话|说话)|"
    r"低头[^，。！？]{0,16}(?:不接话|不说话|没再说)|"
    r"沉默(?:收场|下来|不语)?$|无话可说$"
)


_TERMINAL_NO_REPLY_DIALOGUE_INTENT = re.compile(
    r"^(?:回答|作答|解释|反驳|嘴硬|接话|回嘴)[:：]"
)


def is_terminal_no_reply_intent(intent: str) -> bool:
    """是否是只能作为表演结果、不能再生成一条对白的末拍。"""
    text = str(intent or "").strip()
    if not text:
        return False
    if _TERMINAL_NO_REPLY_DIALOGUE_INTENT.match(text):
        return False
    if re.search(r"[？?]", text):
        return False
    return bool(_TERMINAL_NO_REPLY_RE.search(text))


def trim_terminal_no_reply_rows(rows: list[Any] | None) -> tuple[list[Any], list[str]]:
    """去掉末尾“沉默/不再接话”结果行；中段语塞/停顿仍可保留。"""
    out = list(rows or [])
    notes: list[str] = []
    while out:
        row = out[-1]
        if not isinstance(row, dict):
            break
        if isinstance(row, dict) and str(row.get("line") or "").strip():
            break
        intent = str(row.get("intent") or row.get("beat") or "").strip()
        if not is_terminal_no_reply_intent(intent):
            break
        notes.append(intent)
        out.pop()
    return out, notes


def normalize_scene_dialogue_beats(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """scene beat_chain 只保留可展开成对白的末拍，避免 punchline 后硬续“沉默”。"""
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    trimmed, removed = trim_terminal_no_reply_rows(chain)
    if not removed:
        return contract, []
    out = dict(contract)
    normalized: list[Any] = []
    for idx, row in enumerate(trimmed, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = idx
            normalized.append(item)
        else:
            normalized.append(row)
    out["beat_chain"] = normalized
    return out, [f"移除末尾纯静默结果拍:{text}" for text in reversed(removed)]


_RETROSPECTIVE_TOPIC_RE = re.compile(
    r"(?:旧事|往事|回忆|经历|小时候|童年|当年|曾经|以前|那次|事故|的事)$|"
    r"(?:旧事|往事|回忆|经历|小时候|童年|当年|曾经|以前|那次|事故)"
)
_RETROSPECTIVE_MATERIALIZE_NOTE_RE = re.compile(
    r"(?:替代|近似|换成|改成|搬到|搬进|端出|拿出|重演)"
)


def is_retrospective_topic_object(value: str) -> bool:
    """object 是过去事件/回忆话题，而不是当前场景要持有的实体物。"""
    text = str(value or "").strip()
    return bool(text and _RETROSPECTIVE_TOPIC_RE.search(text))


def normalize_retrospective_topic_contract(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """回忆型 object 不应被 remap_note 强行物化成当前道具。"""
    if not isinstance(contract, dict):
        return contract, []
    if not is_retrospective_topic_object(str(contract.get("object") or "")):
        return contract, []
    note = str(contract.get("remap_note") or "").strip()
    if not note:
        return contract, []
    parts = [p.strip(" 。") for p in re.split(r"[；;]", note) if p.strip(" 。")]
    kept = [p for p in parts if not _RETROSPECTIVE_MATERIALIZE_NOTE_RE.search(p)]
    if kept == parts:
        return contract, []
    out = dict(contract)
    out["remap_note"] = "；".join(kept)
    return out, ["移除回忆话题物化 remap_note"]


_RETROSPECTIVE_PARENT_EXPOSITION_RE = re.compile(
    r"重提|讲|回忆|旧事|定论|定性|命大|补充|说.*(?:命|运气)"
)
_RETROSPECTIVE_N_SUPPORT_RE = re.compile(
    r"帮腔|附和|赞同|同意|讲得对|说得对|就是命大|确实命大|命真大"
)
_RETROSPECTIVE_N_REBUTTAL_RE = re.compile(
    r"反驳|嘴硬|不是.{0,8}命|会挑地方|自己会|主动"
)


def normalize_retrospective_n_opening_parent_beats(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """N 型回忆稿避免开场连续两拍家长讲解，合并成一个前提拍。"""
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    if not is_retrospective_topic_object(str(contract.get("object") or "")):
        return contract, []
    chain = contract.get("beat_chain")
    # 至少 5 拍才合并，避免把合法 4 拍压到 scene_contract 最低拍数以下。
    if not isinstance(chain, list) or len(chain) < 5:
        return contract, []
    first, second = chain[0], chain[1]
    if not isinstance(first, dict) or not isinstance(second, dict):
        return contract, []
    speaker1 = str(first.get("speaker") or "").strip()
    speaker2 = str(second.get("speaker") or "").strip()
    if speaker1 not in {"妈妈", "爸爸"}:
        return contract, []
    intent1 = str(first.get("intent") or first.get("beat") or "").strip()
    intent2 = str(second.get("intent") or second.get("beat") or "").strip()

    third = chain[2] if len(chain) > 2 else None
    if (
        speaker2 != speaker1
        and _RETROSPECTIVE_N_SUPPORT_RE.search(intent2)
        and isinstance(third, dict)
        and _RETROSPECTIVE_N_REBUTTAL_RE.search(
            str(third.get("intent") or third.get("beat") or "")
        )
    ):
        new_chain = [first, *chain[2:]]
        normalized: list[Any] = []
        for idx, row in enumerate(new_chain, 1):
            if isinstance(row, dict):
                item = dict(row)
                if "beat" in item:
                    item["beat"] = idx
                normalized.append(item)
            else:
                normalized.append(row)
        out = dict(contract)
        out["beat_chain"] = normalized
        return out, [f"移除N回忆开场冗余附和拍:{speaker2}"]

    if speaker2 != speaker1:
        return contract, []
    if not _RETROSPECTIVE_PARENT_EXPOSITION_RE.search(intent2):
        return contract, []

    merged_first = dict(first)
    merged_first["intent"] = f"{intent1}；{intent2}".strip("；")
    new_chain: list[Any] = [merged_first, *chain[2:]]
    normalized: list[Any] = []
    for idx, row in enumerate(new_chain, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = idx
            normalized.append(item)
        else:
            normalized.append(row)
    out = dict(contract)
    out["beat_chain"] = normalized
    return out, [f"合并N回忆开场连续家长拍:{speaker1}"]


def normalize_dialogue_setting_for_contract(
    setting: str,
    contract: dict[str, Any] | None,
) -> tuple[str, bool]:
    """回忆/旧事类 object 只作为当前谈话主题，不把历史物件搬进 setting。"""
    sc = contract if isinstance(contract, dict) else {}
    if not is_retrospective_topic_object(str(sc.get("object") or "")):
        return str(setting or "").strip(), False
    location = str(sc.get("location") or "").strip()
    neutral = f"{location}，一家人聊起以前的事" if location else "一家人聊起以前的事"
    current = str(setting or "").strip()
    return neutral, neutral != current


_DIALOGUE_META_LABEL_RE = re.compile(
    r"一锤定音|镇住话题|嘴硬收场|旁观感叹|一招制敌|语塞收场|愣住收束"
)
_DIALOGUE_META_LABEL_SUFFIX_RE = re.compile(
    r"(?:[，,；;。！？!?]?\s*)"
    r"(?:一锤定音|镇住话题|嘴硬收场|旁观感叹|一招制敌|语塞收场|愣住收束)"
    r"[。！？!?]*$"
)


def has_dialogue_meta_label(line: str) -> bool:
    """结构/审稿标签不得由角色念出口。"""
    return bool(_DIALOGUE_META_LABEL_RE.search(str(line or "")))


def sanitize_dialogue_meta_label_suffix(line: str) -> str:
    """只剥句尾结构标签；整句都是标签时保留给 hard gate/LLM 修稿。"""
    text = str(line or "").strip()
    if not text:
        return text
    match = _DIALOGUE_META_LABEL_SUFFIX_RE.search(text)
    if not match:
        return text
    prefix = text[: match.start()].rstrip("，,；;。！？!? ")
    if not prefix:
        return text
    tail = text[-1] if text[-1] in "。！？!?" else "。"
    return f"{prefix}{tail}"


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


_PARENT_SPEAKERS = frozenset({"妈妈", "爸爸"})
_RE_ADULT_EXAM = re.compile(r"高考|中考|考研|成考")
_RE_SCORE_NUM = re.compile(r"(\d{2,3})分")


def _contract_age_check_blob(contract: dict[str, Any]) -> str:
    """迁龄检查只看可拍正文口径，不含 remap_note 说明句（避免「高考→小学」误伤）。"""
    parts: list[str] = []
    for key in ("object", "conflict", "mechanism", "closing_intent"):
        parts.append(str(contract.get(key) or ""))
    for row in contract.get("beat_chain") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or ""))
        else:
            parts.append(str(row))
    return "\n".join(parts)


def age_remap_contract_errors(
    story_raw: str,
    contract: dict[str, Any],
) -> list[str]:
    """站外成人考语境迁入 7–10 岁后，契约仍残留成人考/大总分则报错。

    抽象门槛：源稿含高考/中考等，且契约正文仍写成人考词，或原样带回 ≥300 的分值。
    """
    raw = str(story_raw or "")
    if not _RE_ADULT_EXAM.search(raw):
        return []
    blob = _contract_age_check_blob(contract) if contract else ""
    errors: list[str] = []
    if _RE_ADULT_EXAM.search(blob):
        errors.append("age_remap:contract_still_has_adult_exam")
    raw_big = {int(x) for x in _RE_SCORE_NUM.findall(raw) if int(x) >= 300}
    out_big = {int(x) for x in _RE_SCORE_NUM.findall(blob) if int(x) >= 300}
    if raw_big & out_big:
        errors.append("age_remap:adult_total_score_carried_over")
    return errors


def _elementary_score_map(raw: str, text: str) -> dict[int, int]:
    """把 ≥300 的成人总分映射为小学百分制高低对比（抽象，非单篇分值）。"""
    big = sorted(
        {
            int(x)
            for x in _RE_SCORE_NUM.findall(f"{raw}\n{text}")
            if int(x) >= 300
        }
    )
    if not big:
        return {}
    mapping: dict[int, int] = {}
    if len(big) == 1:
        mapping[big[0]] = 58 if big[0] < 550 else 98
        return mapping
    mapping[big[0]] = 58
    mapping[big[-1]] = 98
    for mid in big[1:-1]:
        mapping[mid] = 78
    return mapping


def _remap_adult_exam_text(text: str, *, score_map: dict[int, int]) -> str:
    out = _RE_ADULT_EXAM.sub("考试", str(text or ""))
    for old, new in sorted(score_map.items(), reverse=True):
        out = out.replace(f"{old}分", f"{new}分")
    return out


def remap_story_raw_scores_for_prompt(
    story_raw: str,
    *,
    contract: dict[str, Any] | None = None,
) -> str:
    """扩写/seed 提示用：把成人考大总分改成小学量级，避免原稿分数字面污染对白。"""
    text = str(story_raw or "")
    if not text:
        return text
    blob = ""
    if isinstance(contract, dict):
        blob = _contract_age_check_blob(contract)
    score_map = _elementary_score_map(text, blob or text)
    if not score_map and not _RE_ADULT_EXAM.search(text):
        return text
    return _remap_adult_exam_text(text, score_map=score_map)


def force_age_score_remap(
    contract: dict[str, Any],
    *,
    story_raw: str,
) -> tuple[dict[str, Any], bool]:
    """LLM 迁龄仍残留成人考/大总分时，本地改写契约文本字段。"""
    if not isinstance(contract, dict):
        return contract, False
    if not age_remap_contract_errors(story_raw, contract):
        return contract, False
    score_map = _elementary_score_map(
        story_raw,
        _contract_age_check_blob(contract),
    )
    out = dict(contract)
    changed = False
    for key in (
        "object",
        "conflict",
        "mechanism",
        "closing_intent",
        "remap_note",
    ):
        old = str(out.get(key) or "")
        if not old:
            continue
        new = _remap_adult_exam_text(old, score_map=score_map)
        if new != old:
            out[key] = new
            changed = True
    chain = out.get("beat_chain")
    if isinstance(chain, list):
        new_chain: list[Any] = []
        for row in chain:
            if not isinstance(row, dict):
                new_chain.append(row)
                continue
            item = dict(row)
            old = str(item.get("intent") or "")
            new = _remap_adult_exam_text(old, score_map=score_map)
            if new != old:
                item["intent"] = new
                changed = True
            new_chain.append(item)
        out["beat_chain"] = new_chain
    note = str(out.get("remap_note") or "").strip()
    marker = "成人考分已迁小学量级"
    if marker not in note:
        out["remap_note"] = f"{note}；{marker}".strip("；") if note else marker
        changed = True
    return out, changed


_RE_EXAM_SCORE = re.compile(r"(?<!\d)(\d{1,3})分")
_RE_SIBLING_LABEL = (
    (re.compile(r"妹妹"), "昭昭"),
    (re.compile(r"弟弟"), "昭昭"),
    (re.compile(r"姐姐"), "灿灿"),
    (re.compile(r"哥哥"), "灿灿"),
)


def remap_story_raw_sibling_roles(story_raw: str) -> str:
    """源稿把站内名反挂（姐姐昭昭/弟弟灿灿）时，按姐弟角色映回站内名。

    只处理「角色标 + 昭昭/灿灿」反挂；其他站外真名仍交 H3a remap。
    """
    text = str(story_raw or "")
    if not text.strip():
        return text
    swapped = bool(
        re.search(r"(?:姐姐|哥哥)\s*昭昭", text)
        or re.search(r"(?:弟弟|妹妹)\s*灿灿", text)
    )
    if not swapped:
        out = re.sub(r"(?:姐姐|哥哥)\s*灿灿", "灿灿", text)
        out = re.sub(r"(?:弟弟|妹妹)\s*昭昭", "昭昭", out)
        return out

    sis_ph, bro_ph = "<<SIS>>", "<<BRO>>"
    out = text
    out = re.sub(r"(?:姐姐|哥哥)\s*昭昭", sis_ph, out)
    out = re.sub(r"(?:弟弟|妹妹)\s*灿灿", bro_ph, out)
    out = out.replace("昭昭", sis_ph).replace("灿灿", bro_ph)
    out = re.sub(r"姐姐|哥哥", sis_ph, out)
    out = re.sub(r"弟弟|妹妹", bro_ph, out)
    out = out.replace(sis_ph, "灿灿").replace(bro_ph, "昭昭")
    out = re.sub(r"(灿灿){2,}", "灿灿", out)
    out = re.sub(r"(昭昭){2,}", "昭昭", out)
    return out


def scrub_h3_beat_list(
    beat: list[Any] | None,
    *,
    story_raw: str = "",
) -> list[Any]:
    """H3 beat 进 H3a 前：迁龄分数字面 + 站外姐弟称谓 → 站内名。"""
    if not isinstance(beat, list):
        return []
    score_map = _elementary_score_map(story_raw, story_raw) if story_raw else {}
    out: list[Any] = []
    for step in beat:
        text = str(step or "")
        if not text:
            out.append(step)
            continue
        if score_map or _RE_ADULT_EXAM.search(text):
            text = _remap_adult_exam_text(text, score_map=score_map)
        for pat, repl in _RE_SIBLING_LABEL:
            text = pat.sub(repl, text)
        out.append(text)
    return out


def canonical_exam_score_from_texts(*blobs: str) -> int | None:
    """从 seed/beat 文本抽小学百分制考分（1–100）；众数优先。"""
    from collections import Counter

    scores: list[int] = []
    for blob in blobs:
        for m in _RE_EXAM_SCORE.finditer(str(blob or "")):
            n = int(m.group(1))
            if 1 <= n <= 100:
                scores.append(n)
    if not scores:
        return None
    mode, _cnt = Counter(scores).most_common(1)[0]
    return mode


def sync_contract_exam_scores(
    contract: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
    conflict_core: str = "",
) -> tuple[dict[str, Any], str, bool]:
    """契约与 seed 考分口径对齐：以 seed/beat_chain 众数为准改写 conflict 等。"""
    if not isinstance(contract, dict):
        return contract, conflict_core, False
    seed_blob = "\n".join(
        str(r.get("intent") or "")
        for r in (dialogue_seed or [])
        if isinstance(r, dict)
    )
    chain_blob = "\n".join(
        str(r.get("intent") or "")
        for r in (contract.get("beat_chain") or [])
        if isinstance(r, dict)
    )
    canon = canonical_exam_score_from_texts(seed_blob, chain_blob)
    if canon is None:
        return contract, conflict_core, False

    def _rewrite(text: str) -> str:
        raw = str(text or "")
        if not raw:
            return raw

        def _sub(m: re.Match[str]) -> str:
            n = int(m.group(1))
            if 1 <= n <= 100 and n != canon:
                return f"{canon}分"
            return m.group(0)

        return _RE_EXAM_SCORE.sub(_sub, raw)

    out = dict(contract)
    changed = False
    for key in ("object", "conflict", "mechanism", "closing_intent", "remap_note"):
        old = str(out.get(key) or "")
        new = _rewrite(old)
        if new != old:
            out[key] = new
            changed = True
    chain = out.get("beat_chain")
    if isinstance(chain, list):
        new_chain: list[Any] = []
        for row in chain:
            if not isinstance(row, dict):
                new_chain.append(row)
                continue
            item = dict(row)
            old = str(item.get("intent") or "")
            new = _rewrite(old)
            if new != old:
                item["intent"] = new
                changed = True
            new_chain.append(item)
        out["beat_chain"] = new_chain
    core = _rewrite(conflict_core)
    if core != str(conflict_core or ""):
        changed = True
    return out, core, changed


def _parent_in_h3_beats(h3: dict[str, Any] | None) -> bool:
    """H3 beat 文案是否把家长写成戏内行动者。"""
    if not isinstance(h3, dict):
        return False
    for step in h3.get("beat") or []:
        text = str(step or "")
        if any(p in text for p in ("妈妈", "爸爸", "家长")):
            return True
    return False


def _parent_in_contract(contract: dict[str, Any]) -> bool:
    chars = {
        str(c).strip()
        for c in (contract.get("characters") or [])
        if str(c).strip()
    }
    if chars & _PARENT_SPEAKERS:
        return True
    for row in contract.get("beat_chain") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKERS:
            return True
    note = f"{contract.get('remap_note') or ''} {contract.get('mechanism') or ''}"
    return any(p in note for p in ("妈妈", "爸爸", "家长"))


_K_PARENT_INTERVENTION_RE = re.compile(
    r"止争|平息|调解|劝架|提议|建议|一人.{0,8}一个|各.{0,6}一个|别抢|别闹|分开"
)
_K_PARENT_FAIL_CLOSE_RE = re.compile(
    r"叹气|劝不动|劝不了|管不了|拦不住|制止失败|僵持|不和好"
)


def normalize_k_parent_intervention_budget(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """K-A 两句家长预算下合并同轮干预，保住开场因果与最终劝失败。

    仅处理窄形状：K、mom_lines_max=2、恰有 3 个同一家长 beat，
    首拍与中拍都是干预/止争，末拍明确是劝失败/僵持。其它形状不猜。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "K":
        return contract, []
    try:
        mom_max = max(0, int(contract.get("mom_lines_max") or 0))
    except (TypeError, ValueError):
        return contract, []
    if mom_max != 2:
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 5:
        return contract, []

    parent_rows: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(chain):
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKERS:
            parent_rows.append((idx, row))
    if len(parent_rows) != 3:
        return contract, []

    (first_idx, first), (middle_idx, middle), (last_idx, last) = parent_rows
    parent = str(first.get("speaker") or "").strip()
    if any(str(row.get("speaker") or "").strip() != parent for _, row in parent_rows):
        return contract, []
    first_intent = str(first.get("intent") or first.get("beat") or "").strip()
    middle_intent = str(middle.get("intent") or middle.get("beat") or "").strip()
    last_intent = str(last.get("intent") or last.get("beat") or "").strip()
    if not (
        _K_PARENT_INTERVENTION_RE.search(first_intent)
        and _K_PARENT_INTERVENTION_RE.search(middle_intent)
        and _K_PARENT_FAIL_CLOSE_RE.search(last_intent)
        and first_idx < middle_idx < last_idx
    ):
        return contract, []

    merged_first = dict(first)
    merged_first["intent"] = f"{first_intent}；同轮继续干预：{middle_intent}".strip("；")
    new_chain: list[Any] = []
    for idx, row in enumerate(chain):
        if idx == middle_idx:
            continue
        new_chain.append(merged_first if idx == first_idx else row)

    normalized: list[Any] = []
    for beat_no, row in enumerate(new_chain, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = beat_no
            normalized.append(item)
        else:
            normalized.append(row)
    out = dict(contract)
    out["beat_chain"] = normalized
    return out, [f"K家长预算2合并同轮干预:{parent}"]


def apply_parent_role_budget(
    contract: dict[str, Any],
    *,
    h3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """源稿/beat 有家长戏核时，勿把 mom_lines_max 压成 0、勿抹掉家长。

    不发明家长戏；只抬预算、补角色位。beat_chain 谁说哪句由 H3a 提示词约束。
    """
    if not isinstance(contract, dict):
        return contract
    st = str(
        contract.get("story_type")
        or (h3 or {}).get("structure_type")
        or "C"
    ).upper().strip()
    need_parent = _parent_in_h3_beats(h3) or _parent_in_contract(contract)

    raw_max = contract.get("mom_lines_max")
    if raw_max is None:
        if st == "H":
            contract["mom_lines_max"] = 3
        elif st == "K":
            contract["mom_lines_max"] = 2
        else:
            contract["mom_lines_max"] = 2 if need_parent else 0
    else:
        try:
            mom_max = max(0, int(raw_max))
        except (TypeError, ValueError):
            mom_max = 0
        contract["mom_lines_max"] = mom_max

    if need_parent:
        floor = 3 if st == "H" else 2
        if int(contract.get("mom_lines_max") or 0) < floor:
            contract["mom_lines_max"] = floor
        chars = [
            str(c).strip()
            for c in (contract.get("characters") or [])
            if str(c).strip()
        ]
        if not (set(chars) & _PARENT_SPEAKERS):
            chars.append("妈妈")
            contract["characters"] = chars
        note = str(contract.get("remap_note") or "").strip()
        marker = "戏核家长须保留出场"
        if marker not in note:
            contract["remap_note"] = (
                f"{note}；{marker}".strip("；") if note else marker
            )
    return contract


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
        errors.append(
            f"beat_chain_too_short:"
            f"{len(chain) if isinstance(chain, list) else 0}"
        )
    else:
        for i, row in enumerate(chain):
            if not isinstance(row, dict):
                errors.append(f"beat_chain[{i}]_invalid")
                continue
            sp = str(row.get("speaker") or "").strip()
            if sp not in ALLOWED_SPEAKERS:
                errors.append(f"beat_chain[{i}]_speaker_illegal:{sp!r}")
        last = chain[-1] if chain else None
        if isinstance(last, dict):
            last_intent = str(last.get("intent") or last.get("beat") or "").strip()
            if is_terminal_no_reply_intent(last_intent):
                errors.append("beat_chain_terminal_no_reply_not_dialogue")
    source_type = str(contract.get("source_type") or "").strip().lower()
    if source_type == "tutorial":
        check_blob = (
            f"{contract.get('conflict')} "
            f"{contract.get('mechanism')} "
            f"{contract.get('remap_note')}"
        )
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
    r"(?:哼，)?(?:缩到|嘟囔|趴下|扭头走开)|"
    # 咀嚼/塞食动作说明（非口语；须带宾语/结果，避免误伤「看我一口吞」）
    r"一口(?:吞下|塞进|吞了)[^。！？?]{0,20}|"
    r"(?:^|[，,])奶油都?(?:挤|溢)(?:出来|出)?|"
    # 舞台指示：动作链 / 问：台词 / 纯动作收场（抽象，不绑单篇）
    r"(?:站直了|叉着?腰站|叉腰问)|"
    r"手指戳|"
    r"(?:^|[，,])戳(?:着)?(?:你的?)?(?:腰侧|腰眼)|"
    r"抽抽搭搭|"
    r"摇摇头|"
    r"转身回|"
    r"探(?:出)?头|"
    r"俯视|"
    r"问[:：]|"
    r"开口[:：]|"
    r"(?:不|没)说话|"
    r"没再管|"
    r"(?:把|将)(?:笔|东西)?举高|"
    r"(?:按倒在|追着)(?:灿灿|昭昭|沙发)|"
    r"(?:灿灿|昭昭)腰侧|"
    r"笑出眼泪后|"
    r"哇地一声|"
    r"嘴抿紧|"
    r"缩回[^，。]{0,6}|"
    r"拼命扭|"
    r"开始挠痒|"
    r"松手叉腰|"
    r"瞪(?:灿灿|昭昭|她|他)一眼|"
    # 当场动作指令入对白（抽象：按/继续+肢体，非「你抓我干嘛」控诉）
    r"按在沙发上|按沙发上|"
    r"(?:^|[，,])继续挠|"
    r"(?:看我)?吐舌头|"
    r"瞪你一眼|"
    # 动作/神态说明混入对白（抽象，不绑场景名词）
    r"拎起|"
    r"塞进(?:袋子|包)|"
    r"拉链一拉|"
    r"鞋跟一踩|"
    r"换好鞋|"
    r"(?:^|[，,])对视一眼|"
    r"(?:^|[，,])笑出声|"
    r"沉默几秒|沉默一会儿|"
    r"我俩都愣住|都愣住|"
    r"气全消了|"
    r"撞见(?:她|他)|"
    # 姿态分镜词（宜改口语「一起走/一起吃」，勿当 line 开头旁白）
    r"勾肩搭背|肩并肩|手挽手|挽着手臂"
)
_RE_ACTION_CHUNK = re.compile(
    r"又?补[一二两三四五两1-5]?下|按在地上|"
    r"(?:一把|挣扎着|护着手)[^。！？]{0,24}(?:揪|按|拍|打|推|抓)|"
    r"(?:揪住|按住|推向)(?:昭昭|灿灿|她|他)|"
    r"被(?:灿灿|昭昭|妈妈)[^。！？]{0,16}|"
    r"缩到角落|嘟囔着|"
    r"^(?:叹气|愣住)$|"
    r"(?:站直了|叉着?腰站|叉腰问)[^，。！？]{0,12}|"
    r"手指戳[^，。！？]{0,12}|"
    r"(?:^|[，,])戳(?:着)?(?:你的?)?(?:腰侧|腰眼)[^，。！？]{0,8}|"
    r"抽抽搭搭[^，。！？]{0,12}|"
    r"摇摇头[^，。！？]{0,16}|"
    r"转身回[^，。！？]{0,12}|"
    r"探(?:出)?头[^，。！？]{0,16}|"
    r"俯视[^，。！？]{0,8}|"
    r"(?:不|没)说话|"
    r"没再管|"
    r"瞪(?:灿灿|昭昭|她|他)一眼|"
    r"(?:把|将)(?:笔|东西)?举高[^，。！？]{0,12}|"
    r"(?:按倒在|追着)(?:灿灿|昭昭|沙发)[^，。！？]{0,12}|"
    r"笑出眼泪后[^，。！？]{0,12}|"
    r"哇地一声[^，。！？]{0,8}|"
    r"嘴抿紧[^，。！？]{0,12}|"
    r"缩回[^，。！？]{0,8}|"
    r"拼命扭|"
    r"开始挠痒[^，。！？]{0,8}|"
    r"松手叉腰[^，。！？]{0,12}|"
    r"按在沙发上|"
    r"(?:^|[，,])继续挠[^，。！？]{0,6}|"
    r"(?:^|[，,])吐舌头"
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
    # 咀嚼/塞食动作 → 可说的逞强短句（抽象，不绑具体食物）
    if re.search(r"一口(?:吞下|塞进|吞了)|奶油都?(?:挤|溢)", raw):
        return "看我一口吞！"
    m_pose = re.match(
        r"^(?:勾肩搭背|肩并肩|手挽手|挽着手臂)[，,]\s*(.+)$",
        raw,
    )
    if m_pose:
        tail = m_pose.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
        return "咱俩一起走！" if sp in {"昭昭", "灿灿"} else "一起走！"
    if re.search(r"^(?:勾肩搭背|肩并肩|手挽手)", raw):
        return "咱俩一起走！" if sp in {"昭昭", "灿灿"} else "一起走！"
    # 「…问：台词」/「…开口：台词」只留冒号后口语
    m_ask = re.search(r"(?:问|开口)[:：]\s*(.+)$", raw)
    if m_ask:
        tail = m_ask.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「笑出声，口语尾巴」只留可说部分
    m_laugh = re.match(r"笑出声[，,]\s*(.+)$", raw)
    if m_laugh:
        tail = m_laugh.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「对视一眼，…」剥掉神态块，留口语尾巴
    m_gaze = re.match(r"对视一眼[，,]\s*(.+)$", raw)
    if m_gaze:
        tail = m_gaze.group(1).strip()
        tail = re.sub(r"^气全消了[，,]?\s*", "", tail).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 家长旁观笑声 → 可说的旁观句（勿劝架）
    if sp in {"妈妈", "爸爸"} and re.search(r"笑", raw):
        return "你们闹吧，我看着！"
    # 僵持/不说话收场 → 短哼
    if re.search(r"(?:不|没)说话|不敢再闹|缩回|瞪.{0,4}一眼", raw):
        if sp not in {"妈妈", "爸爸"}:
            return "哼！"
    fallback = (
        "唉，我管不了你们了" if sp in {"妈妈", "爸爸"} else "你别过来！"
    )
    parts = [p.strip() for p in re.split(r"[，,]", raw) if p.strip()]
    spoken: list[str] = []
    for part in parts:
        # 纯动作块即使带「我」也剥掉（如「我补两下」）
        if _RE_ACTION_CHUNK.search(part) and not re.search(
            r"[？！]|疼|怕|不服|活该|警告|别逼|松手|嘴硬|还不哭",
            part,
        ):
            cleaned = _RE_ACTION_CHUNK.sub("", part).strip("，。！？ ")
            cleaned = re.sub(r"^我$", "", cleaned).strip()
            if cleaned and re.search(r"[我你]|疼|怕|警告|别|嘴硬|哭", cleaned):
                spoken.append(cleaned)
            continue
        if looks_like_narration_line(part) and not re.search(
            r"[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了|嘴硬|还不哭",
            part,
        ):
            continue
        if re.search(
            r"[我你]|[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了|劝不|嘴硬|还不哭",
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
    """beat_chain → dialogue_seed 兜底；末尾纯静默结果不生成假对白。"""
    rows, _ = trim_terminal_no_reply_rows(chain)
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        intent = str(row.get("intent") or row.get("beat") or "").strip()
        if sp in ALLOWED_SPEAKERS and intent:
            out.append({"speaker": sp, "intent": intent})
    return out
