"""gold_chat 本地补丁（M5/H、M2/C 结构）。"""

from __future__ import annotations

import re
from typing import Any

from app.services.gold_story.gold_chat.validate import (
    RE_AUTH_RULE_SLOT,
    RE_AUTH_VICTIM_DISTRESS,
    RE_AUTH_HIDER_DENY,
    RE_AUTH_HIDER_ACT,
    RE_FIGHT_QUESTION,
    RE_INJURY,
    RE_IODINE_CLOSE,
    RE_IODINE_INVENT,
    RE_M5_APOLOGY,
    RE_M5_AUTHORITY,
    RE_M5_ESCALATE,
    RE_M5_RULE,
    RE_M5_STUBBORN,
    RE_MOM_ASK,
    RE_MOM_BALANCE,
    RE_MOM_SOFT,
    RE_ONE_SIDED,
    _dialogue_rows,
    _iodine_close_line_index,
    _m5_phrase_hits,
    _parse_conflict_victim,
    _parse_fight_question_asker,
    _sibling_partner,
)


def _last_kid_idx_before_mom(
    rows: list[dict[str, Any]],
    first_mom: int,
) -> int:
    for j in range(first_mom - 2, -1, -1):
        if str(rows[j].get("speaker") or "") in {"昭昭", "灿灿"}:
            return j
    return -1


def _pick_m5_bridge_line(
    speaker: str,
    prev_line: str,
    next_line: str,
) -> tuple[str, str]:
    """连说打断只插中性短接话，不按「画/撕」编剧情。"""
    del prev_line, next_line
    alt = "昭昭" if speaker == "灿灿" else "灿灿"
    return alt, "嗯。"


_MAX_M5_CONSECUTIVE_FIXES = 8


def patch_m5_break_sibling_consecutive(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """M5+H：姐弟同人连说处插短接话，满足观感交替节奏。"""
    import copy

    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
    )

    rows = _dialogue_rows(story)
    if len(rows) < 2:
        return story, False
    out = copy.deepcopy(story)
    dlg = out.get("dialogue")
    if not isinstance(dlg, list):
        return story, False
    changed = False
    fixes = 0
    i = 1
    while i < len(dlg) and fixes < _MAX_M5_CONSECUTIVE_FIXES:
        a, b = dlg[i - 1], dlg[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in ("昭昭", "灿灿") or sa != sb:
            i += 1
            continue
        prev_line = str(a.get("line") or "")
        next_line = str(b.get("line") or "")
        bridge_sp, bridge_ln = _pick_m5_bridge_line(sa, prev_line, next_line)
        if dialogue_char_count(bridge_ln) > DAILY_STORY_LINE_CHARS_MAX:
            i += 1
            continue
        dlg.insert(i, {"speaker": bridge_sp, "line": bridge_ln})
        changed = True
        fixes += 1
        i += 2
    return (out, True) if changed else (story, False)


_M5_RULE_AUTHORITY_PREFIX = "家规就是"
_RE_MOM_RULE_REF = re.compile(r"妈妈(?:说过|说|讲|告诉)")


def patch_m5_retaliation_action(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """互毁缺当场动作：不在本地写死道具/台词，交精修或扩写反馈闭环。"""
    del conflict_text
    return story, False


def patch_m5_soften_premature_push_blame(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """伤情句前昭昭「你推我」暗示受害方先推人；改为抱怨勿提前写推搡。"""
    import copy
    import re as _re

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 6:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    victim_pushed_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == victim and "推我" in line and RE_INJURY.search(line)
        ),
        next(
            (
                i
                for i, (sp, line) in enumerate(zip(speakers, lines))
                if sp == victim and _re.search(r"哎哟.*推|推.*疼|推.*破", line)
            ),
            -1,
        ),
    )
    if victim_pushed_i <= 0:
        return story, False

    out = copy.deepcopy(story)
    changed = False
    for i in range(victim_pushed_i):
        if speakers[i] != "昭昭":
            continue
        line = lines[i]
        if not _re.search(r"推我|你推", line):
            continue
        new_line = _re.sub(r"你推我干嘛[！!？?]*", "你干嘛凶我！", line)
        new_line = _re.sub(r"你推我[！!？?]*", "你干嘛凶我！", new_line)
        if new_line == line:
            new_line = "我就碰了一下，你干嘛凶我！"
        out["dialogue"][i]["line"] = new_line
        changed = True
    if not changed:
        return story, False
    return out, True


def patch_m5_denial_speaker_swap(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """服软方说了拒和/加码时，改由另一方 speaker（精修本地）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False
    pre_mom_end = mom_indices[0]
    apology_speakers: set[str] = set()
    for i in range(1, pre_mom_end):
        sp = speakers[i - 1]
        if sp in {"昭昭", "灿灿"} and RE_M5_APOLOGY.search(lines[i - 1]):
            apology_speakers.add(sp)
    if not apology_speakers:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for i in range(1, pre_mom_end):
        sp = speakers[i - 1]
        line = lines[i - 1]
        if sp not in apology_speakers:
            continue
        if not (RE_M5_STUBBORN.search(line) or RE_M5_ESCALATE.search(line)):
            continue
        dlg[i - 1]["speaker"] = _sibling_partner(sp)
        changed = True
    return out, changed


def patch_m5_rule_authority(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """M5 立规句：仅把「妈妈说过」换成「家规就是」前缀；不整句换成 canonical。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for item in dlg:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        if _RE_MOM_RULE_REF.search(line) and RE_M5_RULE.search(line):
            new_line = _RE_MOM_RULE_REF.sub(_M5_RULE_AUTHORITY_PREFIX, line)
            if new_line != line and len(new_line) <= max_line_chars:
                item["line"] = new_line
                changed = True
            continue
        if not RE_M5_RULE.search(line):
            continue
        if RE_M5_AUTHORITY.search(line):
            continue
        if line.startswith(_M5_RULE_AUTHORITY_PREFIX):
            continue
        candidate = f"{_M5_RULE_AUTHORITY_PREFIX}{line}"
        if len(candidate) <= max_line_chars:
            item["line"] = candidate
            changed = True
    return out, changed


def patch_m5_insert_authority_before_mom(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """缺家规不本地补 canonical 台词，交精修/扩写反馈。"""
    del max_line_chars
    return story, False


def patch_ensure_injury_after_push(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """缺伤情不本地补固定喊疼句，交精修/扩写反馈。"""
    return story, False


def patch_m5_fix_pre_mom_sequence(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈问谁先动手须晚于服软+立规+拒和+加码（精修本地重排）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False

    def _snapshot() -> tuple[list[str], list[str]]:
        ls = [str(r.get("line") or "").strip() for r in dlg]
        sps = [str(r.get("speaker") or "").strip() for r in dlg]
        return ls, sps

    lines, speakers = _snapshot()
    rule_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and RE_M5_AUTHORITY.search(line)
            and RE_M5_RULE.search(line)
        ),
        -1,
    )
    apology_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"} and RE_M5_APOLOGY.search(line)
        ),
        -1,
    )
    if rule_i >= 0 and apology_i > rule_i:
        dlg.insert(rule_i, dlg.pop(apology_i))
        changed = True
        lines, speakers = _snapshot()

    mom_ask_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == "妈妈" and RE_MOM_ASK.search(line)
        ),
        -1,
    )
    if mom_ask_i < 0:
        return (out, changed) if changed else (story, False)
    after_mom = [
        i
        for i in range(mom_ask_i + 1, len(lines))
        if speakers[i] in {"昭昭", "灿灿"}
        and (
            RE_M5_STUBBORN.search(lines[i])
            or RE_M5_ESCALATE.search(lines[i])
        )
    ]
    if not after_mom:
        return (out, changed) if changed else (story, False)

    last_i = after_mom[-1]
    mom_row = dlg.pop(mom_ask_i)
    dlg.insert(last_i + 1, mom_row)
    return out, True


def patch_sanitize_iodine_line(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏收场句删 story_raw 未提 invent（录视频/发朋友圈）。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "").strip()
        if not RE_IODINE_CLOSE.search(line):
            continue
        if not RE_IODINE_INVENT.search(line):
            continue
        trimmed = re.sub(r"[，,]?我?(?:录|发).*$", "", line).strip("，, ")
        item["line"] = trimmed or "来，额头涂点碘伏消消毒。"
        changed = True
    return out, changed


def patch_trim_post_iodine_tail(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏/涂药妈妈句后删拖句 invent（精修本地，不手改 export）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    iodine_idx = _iodine_close_line_index(lines)
    if iodine_idx <= 0 or iodine_idx >= len(rows):
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = list(rows[:iodine_idx])
    return out, True


def _trim_m5_merged_line(line: str) -> str:
    """一句内 M5 立规/拒和/加码合并 → 只保留立规段。"""
    raw = str(line or "").strip()
    if _m5_phrase_hits(raw) < 2:
        return raw
    m = re.search(
        r"((?:家规|规矩|规定).{0,24}?(?:谁先动手|先动手).{0,16}?[！!])",
        raw,
    )
    if m:
        return m.group(1)
    if RE_M5_STUBBORN.search(raw) and not RE_M5_ESCALATE.search(raw):
        m2 = re.search(r"[^！!]*不原谅[^！!]*[！!]?", raw)
        if m2:
            return m2.group(0).strip()
    if RE_M5_ESCALATE.search(raw) and not RE_M5_STUBBORN.search(raw):
        m3 = re.search(r"[^！!]*(?:道歉也没用|弄了好久|变不回来)[^！!]*[！!]?", raw)
        if m3:
            return m3.group(0).strip()
    return raw


def patch_split_m5_merged_line(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """精修：M5 立规/拒和/加码同句合并时只保留立规（其余靠邻句/本地补拍）。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in {"昭昭", "灿灿"}:
            continue
        line = str(item.get("line") or "").strip()
        if _m5_phrase_hits(line) < 2:
            continue
        trimmed = _trim_m5_merged_line(line)
        if trimmed and trimmed != line and len(trimmed) <= max_line_chars:
            item["line"] = trimmed
            changed = True
    return out, changed


def patch_fight_question_speaker(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """精修：「还打不打架」speaker 对齐 closing_intent（允许改 speaker）。"""
    import copy

    asker = _parse_fight_question_asker(closing_intent)
    if not asker:
        return story, False
    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not RE_FIGHT_QUESTION.search(line):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp != asker:
            item["speaker"] = asker
            changed = True
    return out, changed


# 站内人物关系只有姐弟一种（灿灿 = 10 岁姐姐、昭昭 = 7 岁弟弟）。源视频标题里的
# 关系标签按站内口径改写：**只换关系标签，内容词（抢娃娃/自砸头）原样保留**。
# 双胞胎/龙凤胎/兄妹/兄弟/姐妹 都不是站内关系 → 一律落回「姐弟」（不删除：删掉会丢
# 两人同框的关系锚点）。专家 2026-10-14 评审口径。
_METADATA_KINSHIP_REMAP: tuple[tuple[str, str], ...] = (
    ("双胞胎", "姐弟"),
    ("龙凤胎", "姐弟"),
    ("兄妹", "姐弟"),
    ("兄弟", "姐弟"),
    ("姐妹", "姐弟"),
    ("哥哥", "姐姐"),
    ("妹妹", "弟弟"),
)

# 其后紧跟的源稿标签不算主角色漏标（如「隔壁妹妹」「同学哥哥」）。
_THIRD_PARTY_PREFIXES = ("隔壁", "邻居", "同学", "朋友", "别人", "人家", "同事", "路人")

# 需要跟 theme 一起 remap 的元数据字段（不含对白正文：正文已由称谓 patch 处理）。
_KINSHIP_TEXT_FIELDS = ("scene_title", "key", "conflict_core", "punchline_explain")

# 单遍匹配用（长词优先，避免「兄妹」被拆）
_KINSHIP_REMAP_RE = re.compile(
    "|".join(
        re.escape(source)
        for source, _ in sorted(_METADATA_KINSHIP_REMAP, key=lambda item: -len(item[0]))
    )
)


def _after_third_party_prefix(text: str, index: int) -> bool:
    for size in (2, 1):
        if index >= size and text[index - size : index] in _THIRD_PARTY_PREFIXES:
            return True
    return False


def remap_source_kinship(text: str) -> str:
    """源稿关系标签 → 站内姐弟口径：双胞胎/兄妹/姐妹/兄弟 → 姐弟，哥哥 → 姐姐，妹妹 → 弟弟。

    只动关系标签，不动内容词；带第三方前缀（隔壁/同学…）的不动。
    单遍替换（替出的「姐弟/姐姐/弟弟」不再参与后续匹配，「龙凤胎兄妹」不会变成「姐弟姐弟」）。
    """
    out = str(text or "")
    if not out:
        return out
    mapping = dict(_METADATA_KINSHIP_REMAP)

    def _replace(match: re.Match[str]) -> str:
        if _after_third_party_prefix(out, match.start()):
            return match.group(0)
        return mapping[match.group(0)]

    remapped = _KINSHIP_REMAP_RE.sub(_replace, out)
    # 相邻两个标签（「龙凤胎兄妹」）会各替一次 → 收敛成一个「姐弟」
    while "姐弟姐弟" in remapped:
        remapped = remapped.replace("姐弟姐弟", "姐弟")
    return remapped


def remap_chat_kinship_metadata(
    story: dict[str, Any],
    *,
    theme: str,
) -> tuple[dict[str, Any], str, list[str]]:
    """落库前统一 remap：theme + 元数据字段的源稿关系标签 → 站内姐弟口径。

    返回 ``(story, theme, notes)``；notes 非空表示确实改写过（调用方记日志）。
    对白正文不在这里改（已有称谓 patch 按 banned_literals 处理），避免误伤第三方。
    """
    import copy

    out = copy.deepcopy(story)
    notes: list[str] = []
    new_theme = remap_source_kinship(theme)
    if new_theme != theme:
        notes.append(f"theme: {theme!r} -> {new_theme!r}")
    for field in _KINSHIP_TEXT_FIELDS:
        value = out.get(field)
        if not isinstance(value, str) or not value:
            continue
        cleaned = remap_source_kinship(value)
        if cleaned != value:
            out[field] = cleaned
            notes.append(f"{field}: {value!r} -> {cleaned!r}")
    return out, new_theme, notes


def patch_remap_sibling_terms(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line:
            continue
        new_line = (
            line.replace("哥哥", "姐姐")
            .replace("弟弟", "昭昭")
        )
        if new_line != line:
            item["line"] = new_line
            changed = True
    return out, changed


def patch_ensure_chorus_bukeda(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """缺齐声「不打了」不本地插入固定句，交精修/扩写反馈。"""
    del closing_intent
    return story, False


def patch_fix_mom_ask_admission(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """缺承认句不本地写「弄花」固定台词，交精修/扩写反馈。"""
    return story, False


_KEEP_NE_CLOSE_MARKERS = ("八百个心眼子", "一招制敌", "灵魂拷问")


def _strip_trailing_ne(line: str) -> str:
    for punct in ("！", "!", "。", "?", "？"):
        if line.endswith(f"呢{punct}"):
            return line[:-2] + punct
    if line.endswith("呢"):
        return line[:-1]
    return line


def patch_trim_redundant_ne_suffix(
    story: dict[str, Any],
    *,
    max_ne_suffix: int = 6,
) -> tuple[dict[str, Any], list[str]]:
    """句尾「呢」过密时优先删昭昭侧冗余，保留收束点题与灿灿机语感。"""
    import copy

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, []

    def count_ne_suffixes() -> int:
        total = 0
        for item in dialogue:
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            if re.search(r"呢[！。!?？]$", line) or line.endswith("呢"):
                total += 1
        return total

    notes: list[str] = []
    changed = False
    while count_ne_suffixes() > max_ne_suffix:
        trimmed = False
        for item in dialogue:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != "昭昭":
                continue
            line = str(item.get("line") or "")
            if any(m in line for m in _KEEP_NE_CLOSE_MARKERS):
                continue
            if not (re.search(r"呢[！。!?？]$", line) or line.endswith("呢")):
                continue
            new = _strip_trailing_ne(line)
            if new == line:
                continue
            item["line"] = new
            notes.append(f"去冗余呢：{line[:14]}")
            changed = True
            trimmed = True
            break
        if not trimmed:
            break

    if not changed:
        return story, []
    opening = out.get("discovery_opening")
    if isinstance(opening, list) and dialogue:
        first = dialogue[0]
        if isinstance(first, dict) and opening:
            opening[0] = dict(first)
    return out, notes


def patch_dedupe_ne_suffix(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """句尾「呢呢」叠字 → 单「呢」。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line.endswith("呢呢"):
            continue
        item["line"] = line[:-1]
        changed = True
    return (out, True) if changed else (story, False)


# 源稿站外称谓 → 站内角色名。
# 注意：站内「姐姐」是产品要求的合法称呼（见 gold_chat/prompts.py
# 「昭昭口中禁止直呼灿灿，一律称姐姐」），不得反向替换成「灿灿」，
# 否则会抹掉姐弟关系。这里只处理源稿称谓。
_KINSHIP_REPLACEMENTS = {
    "哥哥": "灿灿",
    "妹妹": "昭昭",
    "弟弟": "昭昭",
}


def patch_replace_banned_kinship(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    """禁词含亲属称谓时，落回站内角色名，避免整稿重抽。"""
    import copy

    terms = [
        str(item).strip()
        for item in (banned_literals or [])
        if str(item).strip() in _KINSHIP_REPLACEMENTS
    ]
    if not terms:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = line
        for term in terms:
            new_line = new_line.replace(term, _KINSHIP_REPLACEMENTS[term])
        if new_line != line:
            item["line"] = new_line
            changed = True
    return (out, True) if changed else (story, False)


def patch_fix_role_pronouns(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈台词：推他/推她 → 推姐姐；避免性别称谓错位。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "")
        new_line = (
            line.replace("推他", "推姐姐")
            .replace("推她", "推姐姐")
            .replace("原谅他", "原谅昭昭")
        )
        if new_line != line:
            item["line"] = new_line
            changed = True
    return out, changed


def patch_strip_mom_fight_question(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """closing_intent 指定灿灿问时，删妈妈句内重复「还打不打架」。"""
    import copy

    asker = _parse_fight_question_asker(closing_intent)
    if asker != "灿灿":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "").strip()
        if not RE_FIGHT_QUESTION.search(line):
            continue
        trimmed = RE_FIGHT_QUESTION.sub("", line).strip("，, ")
        item["line"] = trimmed or "好了。"
        changed = True
    return out, changed


def patch_fix_mom_balance_line(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """妈妈第二句定责：先点先动手方，再点受害方报复，禁单边原谅。"""
    import copy

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    mom_rows: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        if str(row.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(row.get("line") or "").strip()
        if RE_MOM_ASK.search(line) or "住手" in line or "别打" in line:
            continue
        mom_rows.append((i, line))
    if not mom_rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for target_idx, line in mom_rows:
        if RE_MOM_BALANCE.search(line) and victim in line and "互相" not in line:
            continue
        if RE_ONE_SIDED.search(line) or (
            "原谅" in line and victim not in line
        ):
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。推人不对，额头先处理。"
            )
        elif "也有错" in line or RE_MOM_SOFT.search(line) or "互相" in line:
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。推人不对，额头先处理。"
            )
        elif "推" in line and victim not in line:
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。"
                f"推{victim}不对，额头先处理。"
            )
        else:
            continue
        new_line = f"昭昭先撕不对，{victim}别撕回去。先处理伤口。"
        out["dialogue"][target_idx]["line"] = new_line
        changed = True
    if not changed:
        return story, False
    return out, True


def patch_m5_move_rule_before_denial(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """M5 立规句移到首句拒和/加码之前。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 10:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    rule_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and RE_M5_AUTHORITY.search(line)
            and RE_M5_RULE.search(line)
        ),
        -1,
    )
    deny_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and (RE_M5_STUBBORN.search(line) or RE_M5_ESCALATE.search(line))
        ),
        -1,
    )
    if rule_i < 0 or deny_i < 0 or rule_i < deny_i:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    dlg.insert(deny_i, dlg.pop(rule_i))
    return out, True


def patch_trim_closing_invent(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """删 story_raw 未提 invent：拉钩/小狗/一起重画等。"""
    import copy
    import re as _re

    inv = _re.compile(r"拉钩|谁打谁|小狗|一起重画|交换礼物")
    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    kept: list[dict] = []
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if inv.search(line):
            changed = True
            continue
        kept.append(item)
    if not changed:
        return story, False
    out["dialogue"] = kept
    return out, True


def patch_remove_mom_forced_forgive(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删妈妈「道歉了就要原谅」类单边逼和句。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    kept: list[dict] = []
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            kept.append(item)
            continue
        line = str(item.get("line") or "").strip()
        if "就要原谅" in line or "道歉了就要" in line:
            changed = True
            continue
        kept.append(item)
    if not changed:
        return story, False
    out["dialogue"] = kept
    return out, True


def patch_m5_remove_premature_mom_blame(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删妈妈问谁先动手之前的定责/扯平句（精修本地）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_ask_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == "妈妈" and RE_MOM_ASK.search(line)
        ),
        -1,
    )
    if mom_ask_i <= 0:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for i in range(mom_ask_i - 1, -1, -1):
        if speakers[i] != "妈妈":
            continue
        line = lines[i]
        if RE_MOM_ASK.search(line):
            break
        if (
            "也有错" in line
            or "该道歉" in line
            or RE_MOM_SOFT.search(line)
            or RE_ONE_SIDED.search(line)
        ):
            dlg.pop(i)
            changed = True
    if not changed:
        return story, False
    return out, True


def apply_m5_h_local_patches(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """M5+H 精修本地补丁：称谓 → 定责 → 立规 → 拆合并 → 问句 speaker → 齐声 → 加码 → 碘伏后删尾。"""
    data, c0 = patch_remap_sibling_terms(story)
    data, c0b = patch_fix_role_pronouns(data)
    data, c0c = patch_fix_mom_balance_line(data, conflict_text=conflict_text)
    data, c1 = patch_m5_rule_authority(data)
    data, c1r = patch_m5_move_rule_before_denial(data)
    data, c2 = patch_split_m5_merged_line(data)
    data, c2b = patch_m5_retaliation_action(data, conflict_text=conflict_text)
    data, c2c = patch_m5_soften_premature_push_blame(data, conflict_text=conflict_text)
    data, c3b = patch_strip_mom_fight_question(data, closing_intent=closing_intent)
    data, c3 = patch_fight_question_speaker(data, closing_intent=closing_intent)
    data, c4 = patch_ensure_chorus_bukeda(data, closing_intent=closing_intent)
    data, c5 = patch_m5_pre_mom_escalation(data)
    data, c7 = patch_ensure_injury_after_push(data)
    data, c8 = patch_m5_fix_pre_mom_sequence(data)
    data, c8b = patch_m5_remove_premature_mom_blame(data)
    data, c8c = patch_remove_mom_forced_forgive(data)
    data, c1b = patch_m5_insert_authority_before_mom(data)
    data, c0d = patch_m5_denial_speaker_swap(data)
    data, c8d = patch_fix_mom_ask_admission(data)
    data, c9 = patch_sanitize_iodine_line(data)
    data, c9b = patch_trim_closing_invent(data)
    data, c6 = patch_trim_post_iodine_tail(data)
    data, c10 = patch_dedupe_ne_suffix(data)
    return (
        data,
        c0
        or c0b
        or c0d
        or c0c
        or c1
        or c1r
        or c1b
        or c2
        or c2b
        or c2c
        or c3
        or c3b
        or c4
        or c5
        or c7
        or c8
        or c8b
        or c8c
        or c8d
        or c9
        or c9b
        or c6
        or c10,
    )


def patch_m5_pre_mom_escalation(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """缺拒和/加码不本地补拍固定台词，交精修/扩写反馈。"""
    return story, False


# 短 seed gold_chat：点题/closing 后另起第二轮（角色反转续写）
_SHORT_SEED_MAX = 12
_POST_CLOSE_TRIM_TYPES = frozenset({"C", "I", "L", "N"})
_I_POST_CLOSE_TAIL_ALLOW = 2
RE_GOLD_HOLDER_WANT = re.compile(
    r"帮我夹|够不着|馋这一口|我也想吃|给我夹|分我半|换一口|我说不吃是客气"
)
RE_GOLD_WANTER_GUARD = re.compile(
    r"我的盘|别盯.*盘|在我嘴里|你自己去夹|你手短|看我吃多好|你得意啥|小滑头"
)


def _gold_close_keywords(
    chat: dict[str, Any],
    payload: dict[str, Any],
) -> list[str]:
    """点题/closing 锚词：scene_title、key、末条 seed intent 短语。"""
    kws: list[str] = []
    for field in ("scene_title", "key"):
        v = str(chat.get(field) or "").strip()
        if len(v) >= 3:
            kws.append(v)
    seed = payload.get("dialogue_seed")
    if isinstance(seed, list) and seed:
        last = seed[-1]
        if isinstance(last, dict):
            intent = str(last.get("intent") or "")
            for m in re.finditer(r"[\u4e00-\u9fff]{4,}", intent):
                kws.append(m.group())
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _find_gold_close_line_index(
    dialogue: list[dict[str, Any]],
    keywords: list[str],
) -> int:
    if not keywords:
        return -1
    ordered = sorted(keywords, key=len, reverse=True)
    n = len(dialogue)
    tail_start = max(0, int(n * 0.55))
    for kw in ordered:
        if len(kw) < 4:
            continue
        for i in range(n - 1, tail_start - 1, -1):
            line = str(dialogue[i].get("line") or "")
            if kw in line:
                return i
    for kw in ordered:
        for i in range(n - 1, -1, -1):
            line = str(dialogue[i].get("line") or "")
            if kw in line:
                return i
    return -1


def _beat_holder_wanter(beat_chain: list[Any] | None) -> tuple[str, str]:
    if not isinstance(beat_chain, list) or len(beat_chain) < 2:
        return "", ""
    b0, b1 = beat_chain[0], beat_chain[1]
    if not isinstance(b0, dict) or not isinstance(b1, dict):
        return "", ""
    return (
        str(b0.get("speaker") or "").strip(),
        str(b1.get("speaker") or "").strip(),
    )


def _tail_role_flipped(
    tail: list[dict[str, Any]],
    *,
    holder: str,
    wanter: str,
) -> bool:
    if not tail or not holder or not wanter:
        return False
    holder_wants = False
    wanter_guards = False
    for item in tail:
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "")
        if sp == holder and RE_GOLD_HOLDER_WANT.search(line):
            holder_wants = True
        if sp == wanter and RE_GOLD_WANTER_GUARD.search(line):
            wanter_guards = True
    return holder_wants and wanter_guards


def patch_gold_chat_post_close_tail(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    structure_type: str = "",
    mechanism: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """seed 点题/closing 落实后删角色反转拖尾（M2+C 等短 seed 金稿）。"""
    import copy

    st = str(structure_type or story.get("story_type") or "").strip().upper()
    if st not in _POST_CLOSE_TRIM_TYPES:
        return story, []
    payload = payload if isinstance(payload, dict) else {}
    seed = payload.get("dialogue_seed")
    if isinstance(seed, list) and len(seed) > _SHORT_SEED_MAX:
        return story, []

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, []

    # I：制敌后拖尾——够字数硬裁，否则交给 patch_i 末段锚定（保篇幅）
    if st == "I":
        from app.services.daily_story.prompts import (
            DAILY_STORY_BODY_CHARS_MIN,
            dialogue_total_chars,
        )
        from app.services.daily_story.story_types.i.validate import RE_WIN_STUBBORN

        win_indices = [
            i
            for i, r in enumerate(rows)
            if RE_WIN_STUBBORN.search(str(r.get("line") or ""))
        ]
        if not win_indices:
            return story, []
        win_idx = win_indices[0]  # 首次制敌，防第二轮
        keep_end = win_idx + 1 + _I_POST_CLOSE_TAIL_ALLOW
        if len(rows) <= keep_end:
            return story, []
        kept = rows[:keep_end]
        from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

        candidate = dict(story)
        candidate["dialogue"] = kept
        if len(kept) < CHAT_LINE_COUNT_MIN:
            return story, []
        if dialogue_total_chars(candidate) < DAILY_STORY_BODY_CHARS_MIN:
            return story, []
        out = copy.deepcopy(story)
        out["dialogue"] = kept
        dropped = len(rows) - keep_end
        return out, [f"gold_chat删I制敌后拖尾({dropped}句)"]

    keywords = _gold_close_keywords(story, payload)
    close_idx = _find_gold_close_line_index(rows, keywords)
    if close_idx < 0 or close_idx >= len(rows) - 1:
        return story, []

    tail = rows[close_idx + 1 :]
    sc = payload.get("scene_contract")
    if not isinstance(sc, dict):
        sc = {}
    beat_chain = sc.get("beat_chain") or payload.get("beat_chain") or []
    holder, wanter = _beat_holder_wanter(beat_chain)
    mech = str(mechanism or payload.get("mechanism") or "").strip().upper()

    should_trim = _tail_role_flipped(tail, holder=holder, wanter=wanter)
    if not should_trim and mech == "M2" and st == "C":
        should_trim = True
    if not should_trim and st == "C" and len(tail) >= 4:
        should_trim = True

    if not should_trim:
        return story, []

    kept = rows[: close_idx + 1]
    # 抽象安全下限：删尾后须仍满足 hard validate 同源门槛，避免短稿被剪穿
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    candidate = dict(story)
    candidate["dialogue"] = kept
    if len(kept) < CHAT_LINE_COUNT_MIN:
        return story, []
    if dialogue_total_chars(candidate) < DAILY_STORY_BODY_CHARS_MIN:
        return story, []

    out = copy.deepcopy(story)
    out["dialogue"] = kept
    dropped = len(rows) - close_idx - 1
    return out, [f"gold_chat删点题后拖尾({dropped}句)"]


# M2+C 结构：对齐现有 C 类 layer/boomerang scorer（不改 quality.py）
# M2+C 整件物（肉/吃商）=#24 校准域；牛奶/公平类勿套 #24 收束与再堵来回
_M2_C_MEAT_MARKERS = re.compile(r"肉|吃商|八百|心眼|分肉|夹.{0,2}块|盘里")
_M2_C_FAIR_MARKERS = re.compile(r"牛奶|公平|陷阱|让给|让出|偏心眼")


def m2_c_meat_whole_item_context(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> bool:
    """True=走 #24 肉战 patch；False=非整件肉（如牛奶公平），禁硬贴吃商/八百。"""
    payload = payload if isinstance(payload, dict) else {}
    sc = payload.get("scene_contract")
    if not isinstance(sc, dict):
        sc = {}
    blob = "".join(
        str(story.get(k) or "")
        for k in ("scene_title", "setting", "conflict_core", "key")
    ) + str(sc.get("object") or "") + str(sc.get("conflict") or "")
    if _M2_C_FAIR_MARKERS.search(blob):
        return False
    return bool(_M2_C_MEAT_MARKERS.search(blob))


_RE_M2_C1 = re.compile(r"凭什么|归谁|谁先|应该给我|你抢")


def _m2_c_layer_blob(rows: list[dict[str, Any]]) -> str:
    return "".join(str(r.get("line") or "") for r in rows)


def _m2_c_snack_snack_name(story: dict[str, Any], payload: dict[str, Any] | None) -> str:
    blob = _m2_c_layer_blob(_dialogue_rows(story))
    if "薯片" in blob:
        return "薯片"
    if isinstance(payload, dict):
        obj = str(
            payload.get("object")
            or (payload.get("scene_contract") or {}).get("object")
            or ""
        )
        if "薯片" in obj:
            return "薯片"
    return "零食"


def _m2_c_is_snack_homework_ctx(
    story: dict[str, Any],
    *,
    meat_ctx: bool,
    payload: dict[str, Any] | None = None,
) -> bool:
    if meat_ctx:
        return False
    rows = _dialogue_rows(story)
    blob = _m2_c_layer_blob(rows)
    sc = ""
    if isinstance(payload, dict):
        sc = str(
            (payload.get("scene_contract") or {}).get("object")
            or payload.get("object")
            or ""
        )
        sc += str(
            (payload.get("scene_contract") or {}).get("conflict")
            or payload.get("conflict")
            or ""
        )
    hay = blob + sc + str(story.get("scene_title") or "")
    has_snack = bool(re.search(r"零食|薯片", hay))
    has_hw = bool(re.search(r"作业|本子", hay))
    return has_snack and has_hw


def patch_m2_c_snack_beat_rebuild(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    boom_sp: str = "昭昭",
    last_sp: str = "灿灿",
) -> tuple[dict[str, Any], list[str]]:
    """零食+作业本 M2+C：按 beat 重建对白（禁吃肉赛规模板/垫词堆砌）。"""
    import copy

    snack = _m2_c_snack_snack_name(story, payload)
    out = copy.deepcopy(story)
    out["dialogue"] = [
        {
            "speaker": "灿灿",
            "line": f"沙发上这包{snack}归我，作业本归你，公平吧？",
        },
        {"speaker": "昭昭", "line": "凭什么你偷吃我的零食还定规矩？"},
        {"speaker": "灿灿", "line": "谁拿到算谁的才算数，你抢不到。"},
        {"speaker": "昭昭", "line": "那我拿到作业本，本子归我才算？"},
        {"speaker": "灿灿", "line": "本子不算！还得我攥手里才算真正归我。"},
        {"speaker": "昭昭", "line": "你一条接一条说，哪条作数啊？"},
        {"speaker": "灿灿", "line": "你敢撕本子，我就把零食全吃光！"},
        {"speaker": "昭昭", "line": "之前说过的，规矩是你自己定的。"},
        {"speaker": "灿灿", "line": "你撕了我也交不了差，零食你也保不住！"},
        {"speaker": "昭昭", "line": "那我先不撕，你还认不认这规矩？"},
        {"speaker": "灿灿", "line": "认什么呀，零食本来就是我的。"},
        {"speaker": "昭昭", "line": "本子我放下了，你说话算不算数？"},
        {"speaker": "灿灿", "line": f"别撕啦，{snack}给你还不行吗。"},
        {
            "speaker": boom_sp or "昭昭",
            "line": f"你刚说「{snack}归我，作业本归你」，说不通！",
        },
        {
            "speaker": last_sp or "灿灿",
            "line": "下次我先写在纸上，看你怎么钻空子啊。",
        },
    ]
    # 末两句 speaker 已按 closing；若 boom/last 同人则兜底交替
    if out["dialogue"][-1]["speaker"] == out["dialogue"][-2]["speaker"]:
        out["dialogue"][-1]["speaker"] = (
            "灿灿" if out["dialogue"][-2]["speaker"] == "昭昭" else "昭昭"
        )
    out["punchline_explain"] = (
        "C类：昭昭用灿灿刚立的规矩回旋镖堵住，灿灿语塞求饶，末句嘴硬约下次。"
    )
    title = str(out.get("scene_title") or story.get("scene_title") or "").strip()
    if title and not str(out.get("key") or "").strip():
        out["key"] = title[:12]
    if not str(out.get("key") or "").strip():
        out["key"] = "零食作业战"
    if not str(out.get("scene_title") or "").strip():
        out["scene_title"] = str(out.get("key") or "零食作业战")
    if not str(out.get("setting") or "").strip():
        out["setting"] = "家中客厅，灿灿端着零食盒，昭昭攥着作业本"
    elif not re.search(r"厅|沙发|桌", str(out.get("setting") or "")):
        out["setting"] = f"客厅，{out['setting']}"
    from app.services.daily_story.prompts import sync_discovery_opening_from_dialogue

    sync_discovery_opening_from_dialogue(out)
    return out, ["M2+C零食战beat重建"]


def m2_c_snack_rebuild_fallback_eligible(
    story: dict[str, Any],
    *,
    last_err: str = "",
    payload: dict[str, Any] | None = None,
) -> bool:
    """扩写耗尽后是否允许零食模板重建：仅结构分/截断类失败，且原稿未呈完整零食战形态。"""
    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

    err = str(last_err or "")
    if not (
        err.startswith("structure_score:")
        or "截断" in err
        or "truncat" in err.lower()
        or err.startswith("align_refine_failed:")
        or err.startswith("align_structural:")
    ):
        return False
    meat_ctx = m2_c_meat_whole_item_context(story, payload=payload)
    if not _m2_c_is_snack_homework_ctx(
        story, meat_ctx=meat_ctx, payload=payload
    ):
        return False
    rows = _dialogue_rows(story)
    blob = _m2_c_layer_blob(rows)
    has_boom = bool(RE_BOOMERANG_RULE.search(blob)) or "说不通" in blob
    # 已较长且含回旋镖形态：勿整篇覆盖
    if len(rows) >= 12 and has_boom:
        return False
    return True


def patch_m2_c_structure(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mechanism: str = "",
    theme: str = "",
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """M2+C 机械 normalize：称谓/你刚才→你刚说、setting、剥垫词、清杂引。

    缺 C1 / 末段回旋镖只记 notes，不本地编句；交扩写/精修反馈闭环。
    不写开场「沙发上」、不 prepend C4、不本地扩句/补赛规。
    整篇零食 beat 重建仅 expand 耗尽兜底见 ``patch_m2_c_snack_beat_rebuild``。
    """
    import copy

    del theme  # 调用方兼容；主题锚不再本地改写 conflict_core

    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if st != "C" or mech != "M2":
        return story, []

    out = copy.deepcopy(story)
    rows = _dialogue_rows(out)
    if len(rows) < 8:
        return out, []

    meat_ctx = m2_c_meat_whole_item_context(out, payload=payload)
    notes: list[str] = []
    changed = False
    closing = ""
    if isinstance(payload, dict):
        closing = str(
            payload.get("closing_intent")
            or (payload.get("scene_contract") or {}).get("closing_intent")
            or ""
        )
    # closing「昭昭用…回旋镖…灿灿嘴硬」→ 回旋镖 speaker=昭昭，末句=灿灿
    boom_sp = "昭昭" if "昭昭" in closing and "回旋镖" in closing else "灿灿"
    if "灿灿" in closing and "回旋镖" in closing and "昭昭用" not in closing:
        boom_sp = "灿灿"
    last_sp = "灿灿" if "灿灿嘴硬" in closing else ("昭昭" if "昭昭嘴硬" in closing else "")

    # setting 缺地点会扣开场分
    setting = str(out.get("setting") or "").strip()
    if setting and not re.search(r"厅|房|桌|沙发|厨房|门口|床", setting):
        out["setting"] = f"客厅，{setting}"
        notes.append("M2+C补setting地点")
        changed = True
    elif not setting:
        out["setting"] = "客厅"
        notes.append("M2+C补setting")
        changed = True

    # punchline_explain → C类前缀（不写死单篇解释）
    explain = str(out.get("punchline_explain") or "").strip()
    if explain and not explain.startswith("C类"):
        out["punchline_explain"] = f"C类：{explain}"
        notes.append("M2+C punchline→C类")
        changed = True

    for item in rows:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        new_line = line

        if "你刚才" in new_line:
            new_line = new_line.replace("你刚才不是", "你刚说").replace("你刚才说", "你刚说")
            new_line = new_line.replace("你刚才", "你刚说")
        new_line = re.sub(r"你刚说+", "你刚说", new_line)
        if sp == "灿灿" and "妈妈说" in new_line:
            new_line = new_line.replace("妈妈说", "之前说过")
        if "妈妈说过" in new_line:
            new_line = new_line.replace("妈妈说过", "之前说过")

        if new_line != line:
            item["line"] = new_line
            changed = True

    rows = _dialogue_rows(out)

    # C1：缺争归属只记 note，不改写对白
    c1_ok = False
    for item in rows[:3]:
        if str(item.get("speaker") or "") != "昭昭":
            continue
        ln = str(item.get("line") or "")
        if _RE_M2_C1.search(ln):
            c1_ok = True
            break
    if not c1_ok:
        notes.append("M2+C缺C1争归属")

    # 开场对白禁旁白定格起句
    for item in rows[:2]:
        ln = str(item.get("line") or "").strip()
        stripped = re.sub(
            r"^(?:客厅|厨房|卧室|沙发|门口|餐桌)(?:前|里|旁|边)?[，,]\s*",
            "",
            ln,
        )
        if stripped != ln and stripped:
            item["line"] = stripped
            notes.append("M2+C剥开场旁白定格")
            changed = True

    # 清误注入的整件物赛规；不在本地补新赛规台词
    rows = _dialogue_rows(out)
    snack_ctx = _m2_c_is_snack_homework_ctx(
        out, meat_ctx=meat_ctx, payload=payload
    )
    if snack_ctx:
        for item in rows:
            ln = str(item.get("line") or "")
            if not re.search(r"举过头顶|证明三次|光抱着不行", ln):
                continue
            new_ln = re.sub(r"光抱着不行，得举过头顶才算！?", "", ln)
            new_ln = re.sub(
                r"还得证明三次才算真正拿到！?",
                "",
                new_ln,
            ).strip("，, ")
            if new_ln and new_ln != ln:
                item["line"] = new_ln[:24]
                notes.append("M2+C清无关才算模板")
                changed = True

    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

    rows = _dialogue_rows(out)
    tail_rows = rows[-4:] if len(rows) >= 4 else rows
    tail_blob = _m2_c_layer_blob(tail_rows)

    def _tail_has_boomerang() -> bool:
        return bool(RE_BOOMERANG_RULE.search(tail_blob)) or "说不通" in tail_blob

    # 末句：只纠 speaker / 去「哼」
    if last_sp and rows:
        last = rows[-1]
        if str(last.get("speaker") or "") != last_sp:
            last["speaker"] = last_sp
            notes.append("M2+C末句嘴硬speaker")
            changed = True
        last_ln = str(last.get("line") or "")
        if "哼" in last_ln:
            trimmed = re.sub(r"哼[，,]?", "", last_ln).strip("，, ")
            if trimmed and trimmed != last_ln:
                last["line"] = trimmed[:24]
                notes.append("M2+C末句去哼")
                changed = True

    rows = _dialogue_rows(out)
    if not _tail_has_boomerang():
        notes.append("M2+C缺末段回旋镖")
    elif len(rows) >= 2:
        prev = rows[-2]
        prev_ln = str(prev.get("line") or "")
        if (
            RE_BOOMERANG_RULE.search(prev_ln) or "说不通" in prev_ln
        ) and str(prev.get("speaker") or "") != boom_sp:
            prev["speaker"] = boom_sp
            notes.append("M2+C回旋镖speaker")
            changed = True

    rows = _dialogue_rows(out)
    if len(rows) >= 2:
        prev = rows[-2]
        for item in rows[-4:-2] + rows[-1:]:
            ln = str(item.get("line") or "")
            if not re.search(r"你刚说|你说的|你不是说", ln):
                continue
            if item is prev:
                continue
            trimmed = re.sub(
                r"(不行[！!])?(?:你刚说|你说的|你不是说)[^，。！?]{0,16}",
                "",
                ln,
            ).strip("，, ")
            if trimmed and trimmed != ln:
                item["line"] = trimmed[:24]
                notes.append("M2+C清尾段杂引")
                changed = True

    # 剥垫字叠词：只清「现在/立刻/马上/快点」连拍，保留单次「真的/不行/啊/吧」
    rows = _dialogue_rows(out)
    for item in rows:
        ln = str(item.get("line") or "")
        new_ln = re.sub(r"(真的啊)+", "真的", ln)
        new_ln = re.sub(r"(不行吧)+", "不行", new_ln)
        new_ln = re.sub(r"(?:立刻|马上|现在|快点){2,}", "", new_ln)
        new_ln = re.sub(
            r"(?:现在|立刻|马上|快点)+(真的|不行|啊|吧)?([！。？!]?)$",
            r"\1\2",
            new_ln,
        )
        new_ln = new_ln.strip("，, ")
        if new_ln and new_ln != ln:
            item["line"] = new_ln[:24]
            notes.append("M2+C剥叠垫词")
            changed = True

    if snack_ctx:
        rows = _dialogue_rows(out)
        for item in rows[:-2]:
            ln = str(item.get("line") or "")
            if not re.search(r"你刚说|你说的|你不是说", ln):
                continue
            trimmed = re.sub(
                r"(不行[！!])?(?:你刚说|你说的|你不是说)[^，。！?]{0,18}",
                "",
                ln,
            ).strip("，,！!。？ ")
            if trimmed and trimmed != ln:
                item["line"] = trimmed[:24]
                notes.append("M2+C清中段杂引")
                changed = True

    if changed:
        from app.services.daily_story.prompts import sync_discovery_opening_from_dialogue

        sync_discovery_opening_from_dialogue(out)

    return out, notes



def patch_m2_c_eating_roles(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """M2+C：得意吃肉须灿灿说，昭昭不能「真香/啊呜」。"""
    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if st != "C" or mech != "M2":
        return story, []

    rows = _dialogue_rows(story)
    if not rows:
        return story, []

    import copy

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if not isinstance(dlg, list):
        return story, []

    changed = False
    for item in dlg:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "")
        if sp == "昭昭" and re.search(r"真香|啊呜|吧唧", ln):
            item["speaker"] = "灿灿"
            changed = True
        if sp == "灿灿" and re.search(r"故意的|馋我", ln):
            item["speaker"] = "昭昭"
            changed = True

    if not changed:
        return story, []
    return out, ["M2+C吃肉角色纠错"]


def patch_m2_c_break_eating_consecutive(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """M2+C：灿灿连说「吃给你看+真香」→ 拆成昭昭看/灿灿吃。"""
    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if st != "C" or mech != "M2":
        return story, []

    import copy

    out = copy.deepcopy(story)
    dlg = out.get("dialogue")
    if not isinstance(dlg, list) or len(dlg) < 2:
        return story, []

    for i in range(len(dlg) - 1):
        a, b = dlg[i], dlg[i + 1]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if str(a.get("speaker") or "") != "灿灿" or str(b.get("speaker") or "") != "灿灿":
            continue
        ln_a = str(a.get("line") or "")
        ln_b = str(b.get("line") or "")
        if ("吃给你看" in ln_a or "真香" in ln_b) and re.search(r"真香|啊呜", ln_b):
            a["speaker"] = "昭昭"
            # 只纠 speaker，不改写台词
            return out, ["M2+C拆连说吃肉"]
    return story, []


def _dialogue_pair_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("speaker") or "").strip(),
        str(item.get("line") or "").strip(),
    )


def patch_gold_chat_dedupe_dialogue_loop(
    story: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """删 2 句一组的连续复读环（LLM 凑字数常见）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 4:
        return story, []

    cut = len(rows)
    # ABAB…：当前句==两句前，且上一句==三句前 → 从第二组 AB 起截断
    for i in range(3, len(rows)):
        if (
            _dialogue_pair_key(rows[i]) == _dialogue_pair_key(rows[i - 2])
            and _dialogue_pair_key(rows[i - 1]) == _dialogue_pair_key(rows[i - 3])
        ):
            cut = i - 1
            break

    if cut >= len(rows):
        return story, []

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    kept = rows[:cut]
    candidate = dict(story)
    candidate["dialogue"] = kept
    if len(kept) < CHAT_LINE_COUNT_MIN:
        return story, []
    if dialogue_total_chars(candidate) < DAILY_STORY_BODY_CHARS_MIN:
        return story, []

    out = copy.deepcopy(story)
    out["dialogue"] = kept
    dropped = len(rows) - cut
    return out, [f"gold_chat删复读环({dropped}句)"]


def patch_m2_c_fix_opening(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """缺开场求物不本地插入固定求肉句，交扩写/精修反馈。"""
    del payload
    return story, []


def patch_m2_c_ensure_seed_close(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """缺 seed 收束不本地补妈妈/点题固定句，交扩写/精修反馈。"""
    del payload
    return story, []


def patch_gold_chat_c_seed_bridge(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mechanism: str = "",
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """缺再堵来回不本地插入固定肉战台词，交扩写/精修反馈。"""
    del structure_type, mechanism, payload
    return story, []


def _authority_beat0(
    beat_chain: list[Any] | None,
) -> tuple[str, str]:
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if sp:
            return sp, intent
    return "", ""


def _intent_to_rule_line(intent: str, *, require_rule_slot: bool = True) -> str:
    """立规 intent → 可直接说出口的短句；绝不靠补“说好了”把剧情描述伪装成对白。

    K 类 authority 开场仍要求显式规则槽；opening causality 补拍可接受天然祈使句，
    例如“灿灿作业没写，先把作业补上”。
    """
    text = str(intent or "").strip()
    text = re.sub(r"^(?:立规|约好|规定|规矩|定规|说好|约定)[：:]", "", text).strip()
    if not text:
        return ""
    has_rule_slot = bool(RE_AUTH_RULE_SLOT.search(text))
    has_direct_imperative = bool(
        re.search(
            r"(?:先把|先去|先给|先做|先写|先补|先道歉|别|不要|不许|必须|得把|快把|赶紧|轮流|谁先|谁赢|赢了|输了|才能)",
            text,
        )
    )
    if require_rule_slot:
        if not has_rule_slot:
            return ""
    elif not (has_rule_slot or has_direct_imperative):
        # 如“端出蛋挞和烤鸭，宣布用绕口令抢吃”只是剧情描述，不能原样塞进对白。
        return ""
    if not text.endswith(("。", "！", "？", "~")):
        text = text + "。"
    if len(text) > 28:
        return ""
    return text


def patch_authority_opening_speaker(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """首句有立规槽但 speaker 错 → 重挂 beat0。"""
    import copy

    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    beat0, _ = _authority_beat0(beat_chain)
    rows = _dialogue_rows(story)
    if not beat0 or not rows:
        return story, False
    line0 = str(rows[0].get("line") or "").strip()
    sp0 = str(rows[0].get("speaker") or "").strip()
    if RE_AUTH_RULE_SLOT.search(line0) and sp0 != beat0:
        out = copy.deepcopy(story)
        out["dialogue"][0]["speaker"] = beat0
        return out, True
    return story, False


def patch_authority_move_rule_to_front(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """立规句被后置：仅前移该句（speaker=beat0 优先）。"""
    import copy

    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    beat0, _ = _authority_beat0(beat_chain)
    rows = _dialogue_rows(story)
    if len(rows) < 2:
        return story, False
    # already ok
    if RE_AUTH_RULE_SLOT.search(str(rows[0].get("line") or "")):
        return story, False
    hit = -1
    for i, row in enumerate(rows):
        line = str(row.get("line") or "")
        sp = str(row.get("speaker") or "").strip()
        if not RE_AUTH_RULE_SLOT.search(line):
            continue
        if beat0 and sp == beat0:
            hit = i
            break
        if hit < 0:
            hit = i
    if hit <= 0:
        return story, False
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    item = dlg.pop(hit)
    if beat0:
        item = dict(item)
        item["speaker"] = beat0
    dlg.insert(0, item)
    out["dialogue"] = dlg
    return out, True


def patch_authority_insert_rule_opening(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """首句仍无立规槽时：插入 beat0 立规句为第1句（不编新剧情）。"""
    import copy

    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    beat0, intent = _authority_beat0(beat_chain)
    rows = _dialogue_rows(story)
    if not beat0 or not rows:
        return story, False
    line0 = str(rows[0].get("line") or "")
    sp0 = str(rows[0].get("speaker") or "").strip()
    if RE_AUTH_RULE_SLOT.search(line0) and sp0 == beat0:
        return story, False
    # 首句不合格：优先改写首句，避免妈妈句数≥4被结构分 -10
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    rule_line = _intent_to_rule_line(intent)
    if not rule_line:
        return story, False
    rule = {"speaker": beat0, "line": rule_line}
    mom_n = sum(
        1
        for r in dlg
        if isinstance(r, dict) and str(r.get("speaker") or "").strip() == "妈妈"
    )
    if mom_n >= 3:
        dlg[0] = rule
    else:
        dlg.insert(0, rule)
    out["dialogue"] = dlg
    return out, True



def patch_authority_role_speakers(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """急哭/撇清语义句 speaker 与 beat 受害/藏物方不一致时重挂（不改台词）。"""
    import copy
    import re as _re

    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    victim = ""
    hider = ""
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or item.get("beat") or "")
        if not victim and _re.search(r"急哭|找不到|急死", intent):
            victim = sp
        if not hider and _re.search(r"藏|占物|塞", intent):
            hider = sp
    if not victim or not hider or victim == hider:
        return story, False
    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    changed = False
    for i, row in enumerate(dlg):
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            continue
        hit_deny = bool(RE_AUTH_HIDER_DENY.search(line))
        hit_distress = bool(RE_AUTH_VICTIM_DISTRESS.search(line))
        if hit_deny and hit_distress:
            if _re.search(r"我没藏|没藏过", line):
                hit_distress = False
            else:
                hit_deny = False
        if hit_deny and sp != hider:
            dlg[i] = {**row, "speaker": hider}
            changed = True
        elif hit_distress and sp != victim:
            dlg[i] = {**row, "speaker": victim}
            changed = True
        elif RE_AUTH_HIDER_ACT.search(line) and sp != hider:
            dlg[i] = {**row, "speaker": hider}
            changed = True
    if not changed:
        return story, False
    out["dialogue"] = dlg
    return out, True



def patch_authority_insert_resist_after_reverse(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """正文缺抗拒/辩解槽：在反将句后插入一句（抽象词，不绑单篇）。"""
    import copy

    from app.services.daily_story.story_types.g.validate import (
        RE_AUTH_RESIST,
        RE_AUTH_REVERSE,
    )
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 3:
        return story, False
    body = "".join(str(r.get("line") or "") for r in rows)
    if RE_AUTH_RESIST.search(body):
        return story, False
    rev_i = -1
    for i, row in enumerate(rows):
        if RE_AUTH_REVERSE.search(str(row.get("line") or "")):
            rev_i = i
            break
    if rev_i < 0:
        return story, False
    beat0, _ = _authority_beat0(beat_chain)
    speaker = ""
    for j in range(rev_i + 1, len(rows)):
        sp = str(rows[j].get("speaker") or "").strip()
        if sp and sp != beat0 and sp != "妈妈":
            speaker = sp
            break
    if not speaker:
        for j in range(rev_i):
            sp = str(rows[j].get("speaker") or "").strip()
            if sp and sp != beat0 and sp != "妈妈":
                speaker = sp
                break
    if not speaker:
        return story, False
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    dlg.insert(
        rev_i + 1,
        {"speaker": speaker, "line": "我不会啊，换件事行不行。"},
    )
    out["dialogue"] = dlg
    return out, True



def _seed_speakable_rows(
    dialogue_seed: list[Any] | None,
    *,
    max_rows: int | None = None,
) -> list[tuple[str, str]]:
    """seed 里「能说出口」的拍，供本地补拍与拍序归位共用。"""
    rows: list[tuple[str, str]] = []
    for item in dialogue_seed or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("intent") or item.get("line") or "").strip()
        if not sp or not text:
            continue
        # 写作说明/约束（含括号或 勿/禁/须/不得）塞进对白会被终检判旁白，宁可不补。
        if any(tok in text for tok in ("（", "(", "勿", "禁", "须", "不得")):
            continue
        rows.append((sp, text))
    if max_rows is not None:
        rows = rows[:max_rows]
    return rows


_SEED_PREMISE_MAX_INSERTS = 2
# 覆盖补拍（整场缺席的角色）单独额度：不与引用补拍互抢，避免覆盖缺口挤掉
# 真正需要按序补回的前提拍。
_SEED_COVERAGE_MAX_INSERTS = 2


def _seed_premise_overlap(seed_text: str, line_text: str) -> bool:
    """seed 拍与对白行是否有 ≥3 字连续重叠（归一化标点后判断）。"""
    norm = re.compile(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()《》【】…—-]+")
    a = norm.sub("", str(seed_text or ""))
    b = norm.sub("", str(line_text or ""))
    if len(a) < 3 or len(b) < 3:
        return bool(a) and a in b
    grams = {a[i : i + 3] for i in range(len(a) - 2)}
    return any(g in b for g in grams)


def patch_seed_premise_lines(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
    max_seed_rows: int | None = None,
    only_speakers: set[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    """前段 seed 拍若在对白里整拍缺席，按序补回该拍（前提须先立）。

    终检「缺前提」的根因是被引用的那句（如家长压人的「我是你妈」）没真说出口，
    而 seed 里本来就有这一拍——这是落地缺失，不是生成能力问题，故确定性补回。
    最多补 ``_SEED_PREMISE_MAX_INSERTS`` 句，插入位置必须落在
    「首个已落地的后继 seed 拍」之前；若根本找不到后继锚点则**不动**——
    宁可留着缺前提交给重掷，也不要把前提补到引用它的句子之后。
    ``max_seed_rows`` 默认 ``None``（扫描整条 seed），过窄的窗口会让后继锚点
    落在视野外，从而退化成后置补叙。``only_speakers`` 给出终检点名的说话人时，
    补拍额度只花在这些角色上（连续同角色的 seed 拍按一段记账）。

    补拍还必须落在契约给的说话人额度内：``story`` 里带
    ``_gold_chat_mom_lines_max`` / ``_gold_chat_dad_lines_max``（成稿在终检前注入）
    时按该额度封口，额度不足就不补——seed 把一拍拆成多句是 seed 的问题，不能靠
    补拍把硬卡撑爆（专家裁决：额度按契约元数据抬，不按 seed 行数抬）。
    """
    import copy

    seed_rows = _seed_speakable_rows(dialogue_seed, max_rows=max_seed_rows)
    if not seed_rows:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    from app.services.gold_story.scene import (
        CHAT_LINE_COUNT_MAX,
        CHAT_LINE_COUNT_MIN,
    )

    lines = [
        str(item.get("line") or "")
        for item in dialogue
        if isinstance(item, dict)
    ]
    # 补拍不得越过契约给的说话人额度：额度来自契约元数据（成稿里以
    # `_gold_chat_*_lines_max` 注入），不是 seed 行数——按 seed 行数抬额会让脏 seed
    # 把硬卡撑爆。额度不足时宁可不补（缺口交给带反馈重掷），也不要补出必挂的稿子。
    quota: dict[str, int] = {}
    for sp_name, key in (("妈妈", "mom"), ("爸爸", "dad")):
        raw_quota = out.get(f"_gold_chat_{key}_lines_max")
        if raw_quota is None:
            raw_quota = out.get(f"{key}_lines_max")
        if raw_quota is None:
            continue
        try:
            quota[sp_name] = max(0, int(raw_quota))
        except (TypeError, ValueError):
            continue
    used: dict[str, int] = {}
    for item in dialogue:
        if isinstance(item, dict):
            sp_used = str(item.get("speaker") or "").strip()
            if sp_used:
                used[sp_used] = used.get(sp_used, 0) + 1
    changed = False
    inserts = 0
    coverage_inserts = 0
    last_inserted_speaker = ""
    # 已落地的 seed 拍下标（用于决定插入位置）
    landed: list[int] = []
    for sp, text in seed_rows:
        idx = next(
            (
                i
                for i, item in enumerate(dialogue)
                if isinstance(item, dict)
                and str(item.get("speaker") or "").strip() == sp
                and _seed_premise_overlap(text, str(item.get("line") or ""))
            ),
            -1,
        )
        landed.append(idx)
    # 「整场缺席」判定（与 `missing_seed_rows` 同一口径）：只对稿子里一句都没有的
    # 角色做尾拍补拍——模型换词写了同一拍时不能再插一行，否则补出语义重复。
    present_speakers = {
        str(item.get("speaker") or "").strip()
        for item in dialogue
        if isinstance(item, dict)
    }

    # 终检点名的说话人：补拍的额度只花在它们身上（专家裁决：缺拍关系要作为
    # 一等输入）。否则按 seed 顺序补，额度会被无关的前置拍吃光，真正缺失的
    # 前提拍（如整段家长解说）反而补不回来。
    wanted = (
        {str(x).strip() for x in only_speakers if str(x).strip()}
        if only_speakers
        else None
    )
    # 补拍顺序：**整场缺席的角色优先**（拍落地覆盖缺口），其次才是「字面没对上」
    # 的引用缺口。否则有限额度会被改写导致的假缺口吃光，真正整拍丢失的收尾拍
    # （家长反应）反而补不回来。各组内部保持 seed 顺序，避免插入乱序。
    coverage_first = [
        pos
        for pos in range(len(seed_rows))
        if seed_rows[pos][0] not in present_speakers
    ]
    coverage_first += [
        pos
        for pos in range(len(seed_rows))
        if seed_rows[pos][0] in present_speakers
    ]
    for pos in coverage_first:
        sp, text = seed_rows[pos]
        if wanted is not None and sp not in wanted:
            continue
        # 连续同角色的 seed 拍是一个整体（专家裁决：seed 自身连说允许，不得拆开），
        # 因此额度按「补了几段」记账，而不是按补了几句。
        continuing = pos > 0 and last_inserted_speaker == sp
        # 覆盖补拍（整场缺席的角色）与引用补拍各用各的额度：否则覆盖缺口会吃掉
        # 前提拍的额度，让「beat 没按序落地」这类引用缺口补不回来。
        is_coverage = sp not in present_speakers
        if not continuing:
            if is_coverage:
                if coverage_inserts >= _SEED_COVERAGE_MAX_INSERTS:
                    continue
            elif inserts >= _SEED_PREMISE_MAX_INSERTS:
                break
        if landed[pos] >= 0:
            continue
        if len(dialogue) >= CHAT_LINE_COUNT_MAX:
            break
        quota_left = quota.get(sp)
        if quota_left is not None and used.get(sp, 0) + 1 > quota_left:
            # 该角色的契约额度已满：补上去必然被硬卡判死，因此不补这一拍。
            continue
        # 插入窗口 [lower, upper]：上界是首个已落地的后继 seed 拍——前提必须先于
        # 引用它的话落地；下界是最后一个已落地的前驱拍之后。
        # 找不到后继锚点的**尾拍**不能直接放弃：收尾的旁观反应拍（如家长笑场）
        # 全稿无人引用，既不会触发「缺前提」，也不会有后继锚点，老逻辑会让它
        # 整拍静默丢失（专家裁决）。尾拍没有依赖它的句子，按 seed 顺序插到已落地
        # 前驱之后、尽量不越过收束句即可。
        upper = next(
            (landed[j] for j in range(pos + 1, len(landed)) if landed[j] >= 0),
            -1,
        )
        lowers = [landed[j] for j in range(0, pos) if landed[j] >= 0]
        lower = (max(lowers) + 1) if lowers else 1
        if upper < 0:
            # 尾拍只在「该角色整场缺席」时才补（与 `missing_seed_rows` 同口径）：
            # 模型换词写了同一拍不该再插一行，否则补出语义重复。
            if sp in present_speakers:
                continue
            tail_at = _seed_tail_insert_index(
                dialogue,
                sp,
                seed_speaker_before=(seed_rows[pos - 1][0] if pos > 0 else ""),
                lower=lower,
            )
            if tail_at is None:
                continue
            insert_at = tail_at
        else:
            insert_at = max(lower, min(upper, len(dialogue)))
        if insert_at <= 0:
            continue
        prev_sp = str(
            (dialogue[insert_at - 1] or {}).get("speaker") or ""
        ).strip()
        if prev_sp == sp and not (pos > 0 and seed_rows[pos - 1][0] == sp):
            # seed 顺序单调优先于「不连说」：seed 自身连续同角色时允许连说，
            # 只有草稿排版造成的连说才放弃该拍——绝不退格（退格会反转 seed 顺序）。
            continue
        dialogue.insert(insert_at, {"speaker": sp, "line": text})
        used[sp] = used.get(sp, 0) + 1
        for j in range(pos + 1, len(landed)):
            if landed[j] >= insert_at:
                landed[j] += 1
        landed[pos] = insert_at
        if not continuing:
            if is_coverage:
                coverage_inserts += 1
            else:
                inserts += 1
        last_inserted_speaker = sp
        changed = True
    if changed and len(dialogue) < CHAT_LINE_COUNT_MIN:
        # 句数仍不足时由后续补字链处理，这里不做假对白
        pass
    return out, changed


_SEED_ORDER_TAIL_GUARD = 3
_SEED_ORDER_MAX_FIXES = 2
_SEED_ORDER_MOVE_RATIO_DEN = 2


def _seed_tail_insert_index(
    dialogue: list[Any],
    speaker: str,
    *,
    seed_speaker_before: str,
    lower: int,
) -> int | None:
    """尾拍（没有已落地后继锚点）的插入点：收束句之前优先，其次末尾。

    收束句要留在最后（它是契约的收束拍），所以先试 ``len-1``；只有插入后不新增
    同角色连说才采用（seed 自身连续同角色例外——seed 顺序单调优先，绝不为避连说
    而退格反序）。找不到安全位置就返回 ``None``（宁可不补，也不补出必挂的稿子）。
    """
    if len(dialogue) < 2 or lower > len(dialogue):
        return None
    for insert_at in (len(dialogue) - 1, len(dialogue)):
        if insert_at < lower:
            continue
        prev_sp = str((dialogue[insert_at - 1] or {}).get("speaker") or "").strip()
        next_sp = (
            str((dialogue[insert_at] or {}).get("speaker") or "").strip()
            if insert_at < len(dialogue)
            else ""
        )
        if prev_sp != speaker and next_sp != speaker:
            return insert_at
        if seed_speaker_before == speaker:
            return insert_at
    return None


def missing_seed_rows(
    dialogue: list[Any] | None,
    dialogue_seed: list[Any] | None = None,
    *,
    max_seed_rows: int | None = None,
) -> list[tuple[str, str]]:
    """拍落地覆盖检查：整拍丢失的 seed 拍（说话人全稿一句都没有）。

    终检的「缺前提」只在后文引用了该前提时才触发，收尾的旁观反应拍全稿无人引用，
    会静默丢失（专家裁决：拍落地必须由本地覆盖检查强制，不能等引用）。判据只认
    「说话人整场缺席」这一抽象事实，不认字面重叠——模型把 seed 改写（同角色换词
    说了同一个意思）不算丢失，否则会补出语义重复的行；单条 seed 拍的缺失仍由引用
    驱动的 ``patch_seed_premise_lines`` 负责。返回 ``(speaker, text)`` 列表。
    """
    rows = _seed_speakable_rows(dialogue_seed, max_rows=max_seed_rows)
    if not isinstance(dialogue, list) or not rows:
        return []
    present = {
        str(item.get("speaker") or "").strip()
        for item in dialogue
        if isinstance(item, dict)
    }
    return [(sp, text) for sp, text in rows if sp not in present]


def _seed_first_landing(speaker: str, text: str, dialogue: list[Any]) -> int:
    """seed 拍在对白里的首现下标；未落地返回 -1。"""
    return next(
        (
            i
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and str(item.get("speaker") or "").strip() == speaker
            and _seed_premise_overlap(text, str(item.get("line") or ""))
        ),
        -1,
    )


def _speaker_adjacency_count(dialogue: list[Any]) -> int:
    spk = [str(item.get("speaker") or "").strip() for item in dialogue if isinstance(item, dict)]
    return sum(1 for a, b in zip(spk[:-1], spk[1:], strict=False) if a and a == b)


def _seed_order_move_safe(
    before: list[Any],
    after: list[Any],
    *,
    tail_must_hold: bool,
) -> bool:
    """移动前后必须同时满足：句数不变、不新增同角色连说、收束不变量不被打掉。"""
    if len(before) != len(after) or len(before) < 6:
        return False
    if _speaker_adjacency_count(after) > _speaker_adjacency_count(before):
        return False
    if tail_must_hold:
        from app.services.daily_story.story_types.k.resolve_check import (
            kid_self_resolve_in_tail,
        )

        spk = [str(item.get("speaker") or "") for item in after if isinstance(item, dict)]
        ln = [str(item.get("line") or "") for item in after if isinstance(item, dict)]
        if not kid_self_resolve_in_tail(spk, ln):
            return False
    return True


def patch_seed_order_monotonic(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """seed 锚点首现序单调：前提锚点若落在依赖它的锚点之后，就前移归位。

    抽象不变量（不绑单篇词表）：seed 里顺序在前、且已被后续拍引用的拍，其成稿
    首现位置不得晚于那些后续拍——否则后续台词在引用一件尚未发生的事。
    修复动作要软且有界：只动「已落地但明显倒置」的锚点，且跨距不超过整篇一半、
    不进收束窗口（末 ``_SEED_ORDER_TAIL_GUARD`` 句）、
    不新增同角色连说、不拆掉孩子自行恢复收束；任一条不满足就整体跳过，
    交回重掷或定点修稿，不做硬拦。
    """
    import copy

    seed_rows = _seed_speakable_rows(dialogue_seed)
    if len(seed_rows) < 2:
        return story, False
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return story, False

    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    spk0 = [str(item.get("speaker") or "") for item in dialogue if isinstance(item, dict)]
    ln0 = [str(item.get("line") or "") for item in dialogue if isinstance(item, dict)]
    tail_must_hold = kid_self_resolve_in_tail(spk0, ln0)

    out = copy.deepcopy(story)
    rows = list(out.get("dialogue") or [])
    changed = False
    for _ in range(_SEED_ORDER_MAX_FIXES):
        positions = [_seed_first_landing(sp, text, rows) for sp, text in seed_rows]
        protected_from = max(0, len(rows) - _SEED_ORDER_TAIL_GUARD)
        # 跨距只挡「横穿大半篇」的极端移动，真正的保护是收束窗口/连说/收束不变量。
        move_cap = max(2, (len(rows) + 1) // _SEED_ORDER_MOVE_RATIO_DEN)
        fix: tuple[int, int] | None = None
        for i, pos in enumerate(positions):
            if pos < 0 or pos >= protected_from:
                continue
            dependents = [q for q in positions[i + 1 :] if 0 <= q < pos]
            if not dependents:
                continue
            dst = min(dependents)
            if dst >= protected_from or pos - dst > move_cap:
                continue
            fix = (pos, dst)
            break
        if fix is None:
            break
        src, dst = fix
        probe = list(rows)
        moved = probe.pop(src)
        probe.insert(dst, moved)
        if not _seed_order_move_safe(rows, probe, tail_must_hold=tail_must_hold):
            break
        rows = probe
        changed = True
    if not changed:
        return story, False
    out["dialogue"] = rows
    return out, changed


def patch_authority_cull_extra_mom_lines(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """妈妈句过多时，优先删非立规/反将/点题的妈妈句，压到 ≤3。"""
    import copy

    from app.services.daily_story.story_types.g.validate import (
        RE_AUTH_PUNCH,
        RE_AUTH_REVERSE,
        RE_AUTH_RULE,
    )
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    del beat_chain  # 仅按台词槽判断
    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    rows = _dialogue_rows(story)
    mom_idx = [
        i
        for i, r in enumerate(rows)
        if str(r.get("speaker") or "").strip() == "妈妈"
    ]
    if len(mom_idx) <= 3:
        return story, False

    def _is_slot(i: int) -> bool:
        line = str(rows[i].get("line") or "")
        return bool(
            RE_AUTH_RULE.search(line)
            or RE_AUTH_REVERSE.search(line)
            or RE_AUTH_PUNCH.search(line)
        )

    # 先删非槽妈妈句
    drop = [i for i in mom_idx if not _is_slot(i)]
    remain = len(mom_idx) - len(drop)
    if remain > 3:
        # 槽位也过多：从中间槽再删
        slot_mids = [i for i in mom_idx if _is_slot(i) and i != mom_idx[0] and i != mom_idx[-1]]
        need = remain - 3
        drop.extend(slot_mids[:need])
    if not drop:
        return story, False
    # 只删到剩 3
    target = len(mom_idx) - 3
    drop = sorted(drop)[:target]
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    for i in sorted(drop, reverse=True):
        if 0 <= i < len(dlg):
            dlg.pop(i)
    out["dialogue"] = dlg
    return out, True




def patch_authority_ensure_end_punch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """末句缺权威点题槽：改写末句（或补一句）命中点题正则。"""
    import copy

    from app.services.daily_story.story_types.g.validate import RE_AUTH_PUNCH
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 4:
        return story, False
    last = str(rows[-1].get("line") or "")
    if RE_AUTH_PUNCH.search(last):
        return story, False
    beat0, _ = _authority_beat0(beat_chain)
    speaker = beat0 or "妈妈"
    # 末拍 intent → 短点题；无则稳妥抽象句
    punch = "这个家我说了算，听清楚了。"
    chain = beat_chain if isinstance(beat_chain, list) else []
    if chain:
        last_beat = chain[-1] if isinstance(chain[-1], dict) else {}
        intent = str(last_beat.get("intent") or "").strip()
        intent = re.sub(r"^[^：:]*[：:]", "", intent).strip() or intent
        if intent and RE_AUTH_PUNCH.search(intent):
            punch = intent if intent.endswith(("。", "！", "？")) else intent + "。"
            if len(punch) > 28:
                punch = punch[:27] + "。"
        elif intent and any(k in intent for k in ("第", "并列", "宣布", "排名")):
            punch = intent if intent.endswith(("。", "！", "？")) else intent + "。"
            if not RE_AUTH_PUNCH.search(punch):
                punch = "这个家我说了算，听清楚了。"
    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    dlg[-1] = {"speaker": speaker, "line": punch}
    out["dialogue"] = dlg
    return out, True



def patch_authority_trim_after_cede(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """让渡后砍多余拉扯：至多保留1句推进过渡，点题紧随其后。"""
    import copy
    import re as _re

    from app.services.daily_story.story_types.g.validate import (
        RE_AUTH_CEDE,
        RE_AUTH_PUNCH,
    )
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    del beat_chain
    if str(story.get("closing_mode") or "").strip() != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 5:
        return story, False
    lines = [str(r.get("line") or "") for r in rows]
    punch_idxs = [i for i, ln in enumerate(lines) if RE_AUTH_PUNCH.search(ln)]
    if not punch_idxs:
        return story, False
    punch_i = punch_idxs[-1]
    cede_before = [
        i for i, ln in enumerate(lines[:punch_i]) if RE_AUTH_CEDE.search(ln)
    ]
    if not cede_before:
        return story, False
    cede_i = cede_before[-1]
    mid = list(range(cede_i + 1, punch_i))
    if len(mid) <= 1:
        # still drop empty ellipsis mid if any
        keep_mid = []
        for i in mid:
            ln = lines[i].strip()
            if _re.search(r"[…⋯]", ln) and len(ln) <= 10:
                continue
            if _re.fullmatch(r"[我你他她它]?\s*[…⋯。.！!？?\s]*", ln or ""):
                continue
            keep_mid.append(i)
        if keep_mid == mid:
            return story, False
        mid = keep_mid
    else:
        # keep at most one non-empty advancing mid (prefer last non-empty)
        candidates = []
        for i in mid:
            ln = lines[i].strip()
            if _re.search(r"[…⋯]", ln) and len(ln) <= 10:
                continue
            if _re.fullmatch(r"[我你他她它]?\s*[…⋯。.！!？?\s]*", ln or ""):
                continue
            # drop obvious stall phrases
            if _re.search(r"偏就不信|别再乱动|马上给我挪开|我偏", ln):
                continue
            candidates.append(i)
        mid = candidates[-1:]  # at most one

    keep = set(range(0, cede_i + 1)) | set(mid) | {punch_i}
    # also drop empty fluff after punch if any (shouldn't)
    new_rows = [rows[i] for i in range(len(rows)) if i in keep]
    # keep 含 punch_i 且 mid ⊂ (cede, punch)，末行必然是点题句
    if len(new_rows) == len(rows) and all(
        str(new_rows[j].get("line")) == str(rows[j].get("line"))
        for j in range(len(rows))
    ):
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = new_rows
    return out, True


def _intent_to_authority_opening_line(intent: str, story: dict[str, Any]) -> str:
    """beat1 权威触发 intent → 可说出口首句；责备/立规/定责共用。"""
    from app.services.gold_story.gold_chat.validate import (
        _RE_BLAME_LINE,
        _opening_authority_intent_kind,
    )

    raw = str(intent or "").strip()
    authority_kind = _opening_authority_intent_kind(raw)
    parts = re.split(r"[：:]", raw, maxsplit=1)
    text = parts[1].strip() if len(parts) == 2 else raw
    if authority_kind == "rule":
        # opening causality 补拍允许天然祈使句落地，但仍拒绝纯剧情描述；不补“说好了”。
        return _intent_to_rule_line(raw, require_rule_slot=False)
    if authority_kind == "directive":
        # directive beat 常是 "家长指令 + 孩子动作" 的剧情 intent；
        # 本地不能把它原样加问号当台词，交给 seed 或上层 LLM 修稿。
        return ""
    text = re.sub(r"[，,]?气氛紧张", "", text).strip()
    core = str(story.get("conflict_core") or "")
    blob = f"{text}{core}"
    if "作业" in blob or "没写" in blob or "没做" in blob:
        who = "灿灿" if "灿灿" in text or "灿灿" in core else "你"
        return f"{who}，怎么作业还没写？别磨蹭了！"
    if authority_kind == "accountability" and text:
        spoken = re.sub(r"^(?:指出|点明|明确|认定|判定)[：：,， ]*", "", text).strip()
        if spoken:
            line = spoken if spoken.endswith(("。", "！", "？")) else f"{spoken}。"
            return line[:28] + ("。" if len(line) > 28 else "")
    if text and _RE_BLAME_LINE.search(text):
        line = text if text.endswith(("。", "！", "？")) else f"{text}？"
        return line[:28] + ("。" if len(line) > 28 else "")
    if text and len(text) >= 4:
        line = text if text.endswith(("。", "！", "？")) else f"{text}？"
        return line[:28]
    return "别磨蹭了，先把该做的事做完！"


def apply_n_viewer_trim_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """N + 家长当追问方：旁观手足不得占场（禁代问、句数 ≤2）。

    抽象不变量（专家口径）：旁观者的功能只能是笑/看/复述/补刀。
    这里删掉旁观者的**追问句**（关键追问功能），并把残余句数收到 2 句内；
    承担机制的孩子与家长的句子不动。
    """
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _N_DIALOGUE_QUESTION_ASK,
        _RE_N_ASK_BEAT_INTENT,
        _beat_chain_entries,
        _n_ask_beat_functions,
        resolve_story_beat_chain,
    )

    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    entries = _beat_chain_entries(chain)
    if not entries:
        return story, False
    parent_ask_entries = [
        entry
        for _beat_no, entry in entries
        if str(entry.get("speaker") or "").strip() in {"妈妈", "爸爸"}
        and _RE_N_ASK_BEAT_INTENT.search(
            str(entry.get("intent") or entry.get("beat") or "")
        )
    ]
    if not parent_ask_entries:
        return story, False
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if len(dlg) < 4:
        return story, False
    speakers = [
        str(row.get("speaker") or "").strip() for row in dlg
    ]
    kids = [name for name in dict.fromkeys(speakers) if name in {"昭昭", "灿灿"}]
    if len(kids) < 2:
        return story, False
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    chain_speakers = {
        str(entry.get("speaker") or "").strip()
        for _beat_no, entry in entries
        if str(entry.get("speaker") or "").strip()
    }
    # 契约角色表里没有的孩子（两人手稿里被模型擅自加回来的旁观）整段删除
    out_of_cast = [
        i
        for i, row in enumerate(dlg)
        if str(row.get("speaker") or "").strip() in {"昭昭", "灿灿"}
        and str(row.get("speaker") or "").strip() not in chain_speakers
    ]
    if out_of_cast and len(dlg) - len(out_of_cast) >= CHAT_LINE_COUNT_MIN:
        out = copy.deepcopy(story)
        out["dialogue"] = [row for i, row in enumerate(dlg) if i not in set(out_of_cast)]
        return out, True
    # 机制孩子 = 说怪词/解释/自洽的一方（占 line 多的一方；同数则按首现顺序）
    counts = {name: speakers.count(name) for name in kids}
    mechanism_kid = max(kids, key=lambda name: counts[name])
    viewer = next((name for name in kids if name != mechanism_kid), "")
    if not viewer:
        return story, False
    viewer_idx = [i for i, name in enumerate(speakers) if name == viewer]
    if not viewer_idx:
        return story, False
    remove: set[int] = set()
    for i in viewer_idx:
        line = str(dlg[i].get("line") or "").strip()
        funcs = _n_ask_beat_functions(
            " ".join(
                str(e.get("intent") or "") for e in parent_ask_entries
            )
        )
        if not _N_DIALOGUE_QUESTION_ASK.search(line):
            continue
        if "generic" in funcs or re.search(r"什么|啥|怎么|谁|哪", line):
            remove.add(i)
    # 双孩交替：她要承担交替位置的接话，不能再压到 2 句；
    # 只删「代问关键追问」的问句（那会让立规方被架空）。
    kept_viewer = [i for i in viewer_idx if i not in remove]
    del kept_viewer
    if not remove:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = [row for i, row in enumerate(dlg) if i not in remove]
    return out, True


def apply_n_token_slot_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """N：契约声明的机制词槽没被说出口时，把该词缀回机制孩子的那句台词。

    只搬契约自己的字面词（不新造词、不新增剧情）；优先缀在落该拍的孩子句首，
    其次缀在机制孩子的第一句。句长超限时不改，交给上层重掷。
    """
    import copy

    from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS
    from app.services.gold_story.gold_chat.validate import (
        _beat_chain_entries,
        _line_fulfills_beat,
        _n_declared_word_token,
        resolve_story_beat_chain,
    )

    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    entries = _beat_chain_entries(chain)
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not entries or not dlg:
        return story, False
    body_lower = "\n".join(str(row.get("line") or "") for row in dlg).lower()
    changed_shape = False
    for _beat_no, entry in entries:
        intent = str(entry.get("intent") or entry.get("beat") or "")
        token = _n_declared_word_token(intent)
        if not token:
            continue
        if token.lower() in body_lower:
            # 词已出现，但可能带着病态形态（「waka了」「会waka」「waka吧」）。
            # 那种形态机检会判「词槽语法」，所以这里要做**就地修形**：
            # 把带病的形态还原成「原形 + 逗号」，让词保持独立出现。
            fixed_any = False
            for i, row in enumerate(dlg):
                line_i = str(row.get("line") or "")
                if token.lower() not in line_i.lower():
                    continue
                repaired = re.sub(
                    re.escape(token) + r"(?:了|着|过|呀|吧|呢|啊)",
                    f"{token}，",
                    line_i,
                )
                repaired = re.sub(
                    r"(?:会|要|去|叫)\s*" + re.escape(token),
                    token,
                    repaired,
                )
                repaired = re.sub(r"([，,])\s*([，,])", r"\1", repaired)
                if repaired != line_i:
                    dlg[i] = dict(row)
                    dlg[i]["line"] = repaired
                    fixed_any = True
            if fixed_any:
                out = dict(story)
                out["dialogue"] = dlg
                changed_shape = True
            continue
        speaker = str(entry.get("speaker") or "").strip()
        if not speaker:
            continue
        target = next(
            (
                i
                for i, row in enumerate(dlg)
                if str(row.get("speaker") or "").strip() == speaker
                and _line_fulfills_beat(
                    speaker, str(row.get("line") or "").strip(), entry
                )
            ),
            -1,
        )
        if target < 0:
            # 落不到该拍时，优先挑「像在讲圆/解释」的那一句（含因为/所以/就是/
            # 就是给钱一类），别把怪词缀到无关的报名字句上——那会让成稿读起来
            # 像突然插话（#87 实测 job 被缀到「我要找个好人来」前面）。
            reason_re = re.compile(r"因为|所以|就是|意思是|这样就能|才算")
            target = next(
                (
                    i
                    for i, row in enumerate(dlg)
                    if str(row.get("speaker") or "").strip() == speaker
                    and reason_re.search(str(row.get("line") or ""))
                ),
                -1,
            )
        if target < 0:
            target = next(
                (
                    i
                    for i, row in enumerate(dlg)
                    if str(row.get("speaker") or "").strip() == speaker
                ),
                -1,
            )
        if target < 0:
            continue
        line = str(dlg[target].get("line") or "").strip()
        merged = f"{token}，{line}" if line else f"{token}！"
        if len(merged) > CHAT_MAX_LINE_CHARS:
            continue
        dlg[target] = {"speaker": speaker, "line": merged}
        out = copy.deepcopy(story)
        out["dialogue"] = dlg
        return out, True
    if changed_shape:
        out = copy.deepcopy(story)
        out["dialogue"] = dlg
        return out, True
    return story, False


def _ask_line_from_intent(intent: str) -> str:
    """没有 seed 时，用契约追问拍自己的话要点拼出可问出口的一句。

    只搬契约里已写的语义（冒号后的部分，或去掉「追问/质问」等标签的部分），
    不新增剧情事实；拼不出可说问句时返回空串，交上层重掷。
    """
    from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS
    from app.services.gold_story.scene import looks_like_narration_line

    text = str(intent or "").strip()
    if not text:
        return ""
    if "：" in text or ":" in text:
        tail = re.split(r"[：:]", text, maxsplit=1)[1]
        candidate = re.sub(r"^(?:追问|质问|反问|发问|设问|问)", "", tail.strip())
    else:
        candidate = re.sub(
            r"^(?:震惊|皱眉|愣住|继续|再|当场|立刻|马上|一本正经)*"
            r"(?:追问|质问|反问|发问|设问|问)",
            "",
            text,
        )
    candidate = candidate.strip("，。；;、 ")
    # 并列的第二拍标签（如「震惊追问谁教的、皱眉追问：…」）只留后半句
    if "、" in candidate:
        candidate = re.split(r"[、，]", candidate)[-1].strip("，。；; ")
    if not candidate or len(candidate) > CHAT_MAX_LINE_CHARS:
        return ""
    if not candidate.endswith(("？", "?", "！", "!")):
        candidate += "？"
    if looks_like_narration_line(candidate):
        return ""
    return candidate


def _close_line_index(
    dlg: list[dict[str, Any]],
    entries: list[tuple[int, dict[str, Any]]],
) -> int:
    """N 收束行下标：末拍落地那一句；判不出时退回末句。

    补句、补拍一律不得越过这条线（N 收束后禁续写）。
    """
    if not dlg:
        return 0
    from app.services.gold_story.gold_chat.validate import _line_fulfills_beat

    idx = -1
    if entries:
        last_entry = entries[-1][1]
        for i, row in enumerate(dlg):
            if _line_fulfills_beat(
                str(row.get("speaker") or "").strip(),
                str(row.get("line") or "").strip(),
                last_entry,
            ):
                idx = i
    if idx < 0:
        idx = len(dlg) - 1
    return max(0, min(len(dlg) - 1, idx))


def apply_n_seed_coverage_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
    mom_lines_max: int | None = None,
    max_inserts: int = 5,
) -> tuple[dict[str, Any], bool]:
    """N：正文不足字数时，用 H3b seed 的**未落地拍**按拍序补回。

    seed 是已生成契约，搬它不新增剧情事实、也不占 LLM 修稿预算；
    比模板垫字更贴机制链。家长额度按 mom_lines_max 控制，
    收束拍之后不再补（N 收束后禁续写）。
    """
    import copy

    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )
    from app.services.gold_story.gold_chat.validate import (
        _beat_chain_entries,
        _line_fulfills_beat,
        resolve_story_beat_chain,
    )

    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    entries = _beat_chain_entries(chain)
    if not entries:
        return story, False
    seed = dialogue_seed
    if not isinstance(seed, list):
        return story, False
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, False
    from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

    mom_max = None if mom_lines_max is None else max(0, int(mom_lines_max))
    inserts = 0
    changed = False
    for entry_index, (_beat_no, entry) in enumerate(entries):
        if inserts >= max_inserts:
            break
        if dialogue_total_chars({"dialogue": dlg}) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        speaker = str(entry.get("speaker") or "").strip()
        if not speaker:
            continue
        if any(
            _line_fulfills_beat(
                str(row.get("speaker") or "").strip(),
                str(row.get("line") or "").strip(),
                entry,
            )
            for row in dlg
        ):
            continue
        if speaker in {"妈妈", "爸爸"} and mom_max is not None:
            used = sum(
                1 for row in dlg if str(row.get("speaker") or "").strip() == speaker
            )
            if used >= mom_max:
                continue
        candidates: list[Any] = []
        if 0 <= entry_index < len(seed):
            candidates.append(seed[entry_index])
        candidates.extend(
            item for i, item in enumerate(seed[: len(entries)]) if i != entry_index
        )
        line = ""
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != speaker:
                continue
            raw = str(item.get("line") or "").strip()
            if not raw:
                raw = str(item.get("intent") or "").strip()
                parts = re.split(r"[：:]", raw, maxsplit=1)
                raw = parts[1].strip() if len(parts) == 2 else raw
            if not raw:
                continue
            if not raw.endswith(("。", "！", "？", "!", "?", "~")):
                raw += "。"
            if len(raw) > CHAT_MAX_LINE_CHARS:
                continue
            from app.services.gold_story.scene import looks_like_narration_line

            if looks_like_narration_line(raw):
                continue
            from app.services.gold_story.gold_chat.length import (
                _pad_line_is_duplicate,
            )

            if _pad_line_is_duplicate(
                raw, [str(row.get("line") or "") for row in dlg]
            ):
                continue
            line = raw
            break
        if not line:
            continue
        anchor = -1
        for prev_index in range(entry_index - 1, -1, -1):
            prev_entry = entries[prev_index][1]
            for i, row in enumerate(dlg):
                if _line_fulfills_beat(
                    str(row.get("speaker") or "").strip(),
                    str(row.get("line") or "").strip(),
                    prev_entry,
                ):
                    anchor = max(anchor, i)
            if anchor >= 0:
                break
        insert_at = len(dlg) - 1 if anchor < 0 else anchor + 1
        insert_at = max(0, min(len(dlg), insert_at))
        insert_at = min(insert_at, _close_line_index(dlg, entries))
        dlg.insert(insert_at, {"speaker": speaker, "line": line})
        inserts += 1
        changed = True
    if not changed:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = dlg
    return out, True


def apply_cast_membership_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """契约外说话人一律删除，收束句之后也不例外。

    机检的「保真-角色表外台词」是无条件硬拦，而此前所有清理补丁都只处理
    到收束句为止，收束之后的旁观句无人管——实测灿灿的句子几乎都落在
    收束句之后（#87）。这里做一次全局收口：删掉契约 beat_chain 里没有拍
    的孩子台词（家长按额度另管），并保证句数不低于下限、收束句仍在末尾。
    """
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _beat_chain_entries,
        resolve_story_beat_chain,
    )

    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    entries = _beat_chain_entries(chain)
    cast = {
        str(entry.get("speaker") or "").strip()
        for _n, entry in entries
        if str(entry.get("speaker") or "").strip()
    }
    if len(cast) < 2:
        return story, []
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, []
    parents = {"妈妈", "爸爸"}
    # 产品规则「必须有两个孩子出场」优先于「契约拍里有没有他」。
    # 昭昭/灿灿都是合法在场人：即便契约漏写了某一方的拍，也不能删他的台词，
    # 否则会与「插反应句拆孩子连说」形成删-插死循环（#87 实测 150 次）。
    # 只删两个既定孩子之外的、契约未登记的闯入者。
    known_kids = {"昭昭", "灿灿"}
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for row in dlg:
        speaker = str(row.get("speaker") or "").strip()
        if (
            speaker
            and speaker not in cast
            and speaker not in parents
            and speaker not in known_kids
        ):
            dropped.append(speaker)
            continue
        kept.append(row)
    if not dropped:
        return story, []
    # 契约外台词是**无条件硬拦**，删了句数不足就交给后续补位/垫字去补，
    # 不能因为「删完会短」就整体放行——放行等于把违规稿送进终检。
    out = copy.deepcopy(story)
    out["dialogue"] = kept
    return out, [f"删除契约外说话人:{'、'.join(dict.fromkeys(dropped))}"]


_N_REACT_LINES: tuple[str, ...] = (
    "哎哟，这我可学不来。",
    "你还真敢说。",
    "行行，你接着讲。",
    "我听着都替你害臊。",
    "这理由编得挺顺啊。",
    "我可记着呢，别赖。",
)


# 纯动作句的改写词库：把「笑了一声」这类舞台说明换成**真的说出口的话**。
# 按动作语义分档，避免把「笑」一律改成同一句。
_ACTION_TO_SPEECH: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"笑|噗|拍腿"), ("你可真敢说。", "这也太好笑了吧。")),
    (re.compile(r"点头|点头|嗯"), ("行，我信你。", "那就这么定了。")),
    (re.compile(r"摇头|撇嘴|翻白眼"), ("我可不信。", "你这话太离谱了。")),
    (re.compile(r"愣|发愣|无语|僵"), ("你再说一遍？", "我没听明白。")),
    (re.compile(r"皱眉|瞪|挑眉"), ("你说的这是什么意思？", "你认真的吗？")),
    (re.compile(r"叹|深吸|倒吸"), ("唉，随你吧。", "我真拿你没办法。")),
)


def apply_pure_action_to_speech_patch(
    story: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """把只有动作/神态的台词改成真的说出口的话。

    对话稿里动作不能当台词（观众听到的是演员在念动作说明）。机检会直接
    拒绝这类句子，但拒绝之后还得有人改——这里按动作语义给一句自然对白，
    句数与 speaker 不变，只换措辞。
    """
    if not isinstance(story, dict):
        return story, []
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, []
    from app.services.gold_story.gold_chat.validate import _looks_like_pure_action

    existing = [str(r.get("line") or "").strip() for r in dlg]
    changed = 0
    for row in dlg:
        line = str(row.get("line") or "").strip()
        if not _looks_like_pure_action(line):
            continue
        replacement = ""
        for pat, cands in _ACTION_TO_SPEECH:
            if not pat.search(line):
                continue
            for cand in cands:
                if cand not in existing:
                    replacement = cand
                    break
            if replacement:
                break
        if not replacement:
            continue
        row["line"] = replacement
        existing.append(replacement)
        changed += 1
    if not changed:
        return story, []
    out = dict(story)
    out["dialogue"] = dlg
    return out, [f"纯动作句改台词:{changed}"]


def apply_n_alternation_lines_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """N：同一个孩子连说时，插入另一个孩子的短反应，让两人交替。

    用户裁决：孩子禁止连说，戏份靠两个孩子交替解决——**不靠删句**。
    这里只做一件事：每段连说里，除第一句外每句前面插一句另一个孩子的
    短反应，把连说拆开。反应句短、无新事实、去重，不占家长额度。
    """
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, []
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    # 可交替的孩子 = 对白里已出现 ∪ 契约 beat 里登记的
    # （契约里有灿灿、成稿只写了昭昭时，正是要靠她来拆连说）
    kids = {
        str(r.get("speaker") or "").strip()
        for r in dlg
        if str(r.get("speaker") or "").strip() in {"昭昭", "灿灿"}
    } | {
        str(r.get("speaker") or "").strip()
        for r in (beat_chain or [])
        if isinstance(r, dict)
        and str(r.get("speaker") or "").strip() in {"昭昭", "灿灿"}
    }
    if len(kids) == 1:
        # 只有一个孩子：按用户裁决补一个同侧搭档来承担交替位
        # （不豁免连说、也不删句）。
        kids.add("灿灿" if "昭昭" in kids else "昭昭")
    if len(kids) < 2:
        return story, []
    existing = [
        str(r.get("line") or "").strip() for r in dlg if str(r.get("line") or "").strip()
    ]
    out_rows: list[dict[str, Any]] = []
    prev_sp = ""
    react_i = 0
    inserted = 0
    for row in dlg:
        sp = str(row.get("speaker") or "").strip()
        is_kid = sp in kids
        if is_kid and sp == prev_sp and len(out_rows) < CHAT_LINE_COUNT_MAX:
            other = next(k for k in sorted(kids) if k != sp)
            # 挑一条不与现有句重复的反应
            line = ""
            for k in range(len(_N_REACT_LINES)):
                cand = _N_REACT_LINES[(react_i + k) % len(_N_REACT_LINES)]
                from app.services.gold_story.gold_chat.length import (
                    _pad_line_is_duplicate,
                )

                if not _pad_line_is_duplicate(cand, existing):
                    line = cand
                    react_i += 1
                    break
            if line:
                out_rows.append({"speaker": other, "line": line})
                existing.append(line)
                inserted += 1
                prev_sp = other
        out_rows.append(row)
        prev_sp = sp if is_kid else ""
    if not inserted:
        return story, []
    out = dict(story)
    out["dialogue"] = out_rows
    return out, [f"N孩子交替补反应句:{inserted}"]


def apply_n_contract_local_patches(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """N 类确定性契约补丁：收旁观占场 → 补机制词槽 → 补家长关键追问拍。"""
    notes: list[str] = []
    # 先做全局收口：契约外说话人一律删除（收束句之后也不例外）
    data, _cast_notes = apply_cast_membership_patch(
        story,
        beat_chain=beat_chain,
    )
    if _cast_notes:
        notes.extend(_cast_notes)
    # 纯动作台词先改成真话（对话稿不允许舞台说明当台词）
    data, _action_notes = apply_pure_action_to_speech_patch(data)
    if _action_notes:
        notes.extend(_action_notes)
    # 孩子连说先拆开（插反应句，不删句）
    data, _alt_notes = apply_n_alternation_lines_patch(data, beat_chain=beat_chain)
    if _alt_notes:
        notes.extend(_alt_notes)
    data, viewer_trimmed = apply_n_viewer_trim_patch(data, beat_chain=beat_chain)
    if viewer_trimmed:
        notes.append("N旁观手足占场已收束")
    data, token_patched = apply_n_token_slot_local_patch(
        data,
        beat_chain=beat_chain,
    )
    if token_patched:
        notes.append("N机制词槽已补回")
    data, ask_patched = apply_n_ask_beat_local_patch(
        data,
        beat_chain=beat_chain,
        dialogue_seed=dialogue_seed,
        mom_lines_max=mom_lines_max,
    )
    if ask_patched:
        notes.append("N关键追问拍已补回")
    data, coverage_patched = apply_n_seed_coverage_local_patch(
        data,
        beat_chain=beat_chain,
        dialogue_seed=dialogue_seed,
        mom_lines_max=mom_lines_max,
    )
    if coverage_patched:
        notes.append("N未落地拍按拍序补回")
    data, budget_trimmed = _trim_n_parent_overflow(
        data,
        beat_chain=beat_chain,
        mom_lines_max=mom_lines_max,
    )
    if budget_trimmed:
        notes.append("N家长句数超契约已收束")
    data, alternation_fixed = apply_n_alternation_local_patch(
        data,
        beat_chain=beat_chain,
    )
    if alternation_fixed:
        notes.append("N同人连说/换词重复已清理")
    # 去重/去连说可能再次削掉词槽句，最后再补一次（幂等）
    data, token_repatched = apply_n_token_slot_local_patch(
        data,
        beat_chain=beat_chain,
    )
    if token_repatched:
        notes.append("N机制词槽再次补回")
    # 去重/去连说之后家长句数可能又变了：最后再收一次额度
    data, budget_trimmed2 = _trim_n_parent_overflow(
        data,
        beat_chain=beat_chain,
        mom_lines_max=mom_lines_max,
    )
    if budget_trimmed2:
        notes.append("N家长句数二次收束")
    # 补句/改写可能带进旁白腔：最后统一过一遍旁白→口语（既有的转换器）
    from app.services.gold_story.scene import patch_dialogue_narration_to_speech

    narration_notes = patch_dialogue_narration_to_speech(data)
    if narration_notes:
        notes.append(f"N旁白句转口语{len(narration_notes)}句")
    if not notes:
        return story, []
    return data, notes


def apply_n_alternation_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """N：清掉同人连说与换词重复（补句/垫字最常见的两笔结构扣分）。

    规则（抽象，不看剧情词）：
    - 同一说话人连续 ≥2 句时，只保留第一句；若要删的那句是本拍唯一落地点，
      则不删（保住契约拍）。
    - 归一化后互为包含（一句是另一句的子串）视为换词重复，删后出现的那句。
    """
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _beat_chain_entries,
        _line_fulfills_beat,
        resolve_story_beat_chain,
    )

    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    entries = _beat_chain_entries(
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if len(dlg) < 3:
        return story, False
    if not entries:
        # 没有契约拍就无从判断哪句该保：留给篇幅/类型链处理
        return story, False

    def _norm(text: str) -> str:
        from app.services.gold_story.gold_chat.length import _norm_pad_line

        return _norm_pad_line(text)

    def _beats_of(row: dict[str, Any]) -> set[int]:
        speaker = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        return {
            beat_no
            for beat_no, entry in entries
            if _line_fulfills_beat(speaker, line, entry)
        }

    beat_hits: dict[int, int] = {}
    for row in dlg:
        for beat_no in _beats_of(row):
            beat_hits[beat_no] = beat_hits.get(beat_no, 0) + 1

    changed = False
    # 1) 换词重复：后出现的包含句/被包含句删掉（若其拍仍被别句覆盖）
    drop: set[int] = set()
    for i, row in enumerate(dlg):
        if i in drop:
            continue
        core = _norm(str(row.get("line") or ""))
        if len(core) < 4:
            continue
        # 开场句/收束句是骨架，不参与换词重复删除
        if i == 0:
            continue
        for j in range(i + 1, len(dlg)):
            if j in drop:
                continue
            if j == len(dlg) - 1:
                continue
            other = _norm(str(dlg[j].get("line") or ""))
            if len(other) < 4:
                continue
            if core not in other and other not in core:
                continue
            beats = _beats_of(dlg[j])
            exact_dup = core == other
            # 「后者只是前者的加长版」：内容已被前句说完，不算新落地。
            # 这种句子即使挂着某个拍，也只是同一拍的重复写法，
            # 留着会被结构分判「存在同人连说」并扣 15 分（#87 实测）。
            superset_repeat = core in other and len(core) / max(len(other), 1) >= 0.5
            if not exact_dup and not beats and not superset_repeat:
                continue
            if (
                beats
                and not superset_repeat
                and any(beat_hits.get(b, 0) <= 1 for b in beats)
            ):
                continue
            # 删完不能让正文明显变短（相对保护，避免把篇幅砍穿）
            if superset_repeat:
                total_now = sum(len(str(r.get("line") or "")) for r in dlg)
                remain = sum(
                    len(str(r.get("line") or ""))
                    for k, r in enumerate(dlg)
                    if k not in drop and k != j
                )
                if remain < total_now * 0.8:
                    continue
            for b in beats:
                beat_hits[b] = max(0, beat_hits.get(b, 1) - 1)
            drop.add(j)
            changed = True

    # 2) 同人连说：每段连说里保住最有信息量的那句，其余在拍仍被覆盖时删掉
    runs: list[list[int]] = []
    current: list[int] = []
    prev_speaker = ""
    for i, row in enumerate(dlg):
        if i in drop:
            continue
        speaker = str(row.get("speaker") or "").strip()
        if speaker != prev_speaker:
            if len(current) > 1:
                runs.append(current)
            current = []
            prev_speaker = speaker
        current.append(i)
    if len(current) > 1:
        runs.append(current)
    for run in runs:
        keeper = max(
            run,
            key=lambda i: (
                len(_beats_of(dlg[i])),
                len(str(dlg[i].get("line") or "")),
            ),
        )
        for i in run:
            if i == keeper:
                continue
            beats = _beats_of(dlg[i])
            # 对不上契约拍的句子不在这里删：删它们会把正文砍空（篇幅另有闸门）
            if not beats:
                continue
            if any(beat_hits.get(b, 0) <= 1 for b in beats):
                continue
            for b in beats:
                beat_hits[b] = max(0, beat_hits.get(b, 1) - 1)
            drop.add(i)
            changed = True

    if not changed:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = [row for i, row in enumerate(dlg) if i not in drop]
    return out, True


def _trim_n_parent_overflow(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """N：家长句数超过 mom_lines_max 时，删掉最不承担机制的家长句。

    保护顺序：立规（首句）、收束（末拍落地行）、追问句（机制拍）都不删；
    只删中间的家长填充句（扩写灌进来的短反应）。删不动就留给上层重掷。
    """
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _N_DIALOGUE_QUESTION_ASK,
        _beat_chain_entries,
        _line_fulfills_beat,
        resolve_story_beat_chain,
    )

    if mom_lines_max is None:
        return story, False
    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    budget = max(0, int(mom_lines_max))
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    entries = _beat_chain_entries(
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    protected: set[int] = set()
    if dlg:
        # 开场与收束是 N 的骨架句，任何情况下都不删（锚词匹配不到也要保住）
        protected.update({0, len(dlg) - 1})
    if entries:
        for i, row in enumerate(dlg):
            if _line_fulfills_beat(
                str(row.get("speaker") or "").strip(),
                str(row.get("line") or "").strip(),
                entries[0][1],
            ) or _line_fulfills_beat(
                str(row.get("speaker") or "").strip(),
                str(row.get("line") or "").strip(),
                entries[-1][1],
            ):
                protected.add(i)
    changed = False
    while True:
        mom_idx = [
            i
            for i, row in enumerate(dlg)
            if str(row.get("speaker") or "").strip() == "妈妈"
        ]
        if len(mom_idx) <= budget:
            break
        removable = [
            i
            for i in mom_idx
            if i not in protected
            and not _N_DIALOGUE_QUESTION_ASK.search(str(dlg[i].get("line") or ""))
        ]
        if not removable:
            break
        dlg.pop(removable[len(removable) // 2])
        changed = True
    if not changed:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = dlg
    return out, True


def apply_n_ask_beat_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """N：关键追问拍未落地时，用 H3b seed 的同槽问句确定性补回。

    只搬已生成契约里的 seed 行，不新增剧情事实，也不占用 LLM 修稿预算。
    家长额度已满时改为**替换**家长的非问句填充行（如扩写灌进来的
    「因为他说得通，所以我才一本正经」），保持家长句数不超契约；
    首尾两拍（立规 / 收束）不参与替换。
    """
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _N_DIALOGUE_QUESTION_ASK,
        _RE_N_ASK_BEAT_INTENT,
        _beat_chain_entries,
        _line_fulfills_beat,
        _n_ask_beat_landed,
        resolve_story_beat_chain,
    )

    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    if len(chain) < 2:
        return story, False
    if str(story.get("story_type") or "").strip().upper() != "N":
        return story, False
    entries = _beat_chain_entries(chain)
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, False
    seed = dialogue_seed
    if not isinstance(seed, list):
        embedded = story.get("dialogue_seed")
        seed = embedded if isinstance(embedded, list) else []
    # seed 为空也要继续：追问拍可以用契约自己的话要点补（见 _ask_line_from_intent），
    # 否则「保真-N家长追问拍」会静默无解、把整篇反复打回重掷。
    mom_max = None if mom_lines_max is None else max(0, int(mom_lines_max))
    changed = False

    def _seed_ask_line(entry_index: int, speaker: str) -> str:
        candidates: list[Any] = []
        if 0 <= entry_index < len(seed):
            candidates.append(seed[entry_index])
        candidates.extend(
            item
            for i, item in enumerate(seed[: len(entries)])
            if i != entry_index
        )
        from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

        for item in candidates:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != speaker:
                continue
            raw = str(item.get("line") or "").strip()
            if not raw:
                raw = str(item.get("intent") or "").strip()
                parts = re.split(r"[：:]", raw, maxsplit=1)
                raw = parts[1].strip() if len(parts) == 2 else raw
            if not raw or not _N_DIALOGUE_QUESTION_ASK.search(raw):
                continue
            if not raw.endswith(("。", "！", "？", "!", "?", "~")):
                raw += "？"
            if len(raw) > CHAT_MAX_LINE_CHARS:
                continue
            from app.services.gold_story.scene import looks_like_narration_line

            if looks_like_narration_line(raw):
                continue
            return raw
        return ""

    for entry_index, (beat_no, entry) in enumerate(entries):
        if not _RE_N_ASK_BEAT_INTENT.search(
            str(entry.get("intent") or entry.get("beat") or "")
        ):
            continue
        speaker = str(entry.get("speaker") or "").strip()
        if not speaker:
            continue
        if _n_ask_beat_landed(
            [r for r in dlg if isinstance(r, dict)], speaker, entry
        ):
            continue
        ask_line = _seed_ask_line(entry_index, speaker)
        if not ask_line:
            # seed 缺失时用契约自己的追问要点拼一句，别让追问拍静默落空
            ask_line = _ask_line_from_intent(
                str(entry.get("intent") or entry.get("beat") or "")
            )
        if not ask_line:
            continue
        # 落点：紧跟前一拍已落地的台词；找不到就放在收束前。
        anchor = -1
        for prev_index in range(entry_index - 1, -1, -1):
            prev_entry = entries[prev_index][1]
            for i, row in enumerate(dlg):
                if _line_fulfills_beat(
                    str(row.get("speaker") or "").strip(),
                    str(row.get("line") or "").strip(),
                    prev_entry,
                ):
                    anchor = max(anchor, i)
            if anchor >= 0:
                break
        insert_at = len(dlg) - 1 if anchor < 0 else anchor + 1
        insert_at = max(0, min(len(dlg), insert_at))
        # 收束拍之后禁止插句（N 收束后禁续写）：插句点必须早于收束行
        insert_at = min(insert_at, _close_line_index(dlg, entries))
        if speaker in {"妈妈", "爸爸"} and mom_max is not None:
            mom_n = sum(
                1 for item in dlg if str(item.get("speaker") or "").strip() == speaker
            )
            if mom_n >= mom_max:
                # 额度已满：替换家长的非问句填充行（跳过首尾两拍）
                target = -1
                for i in range(max(1, insert_at - 1), len(dlg) - 1):
                    row = dlg[i]
                    if str(row.get("speaker") or "").strip() != speaker:
                        continue
                    line = str(row.get("line") or "").strip()
                    if not line or _N_DIALOGUE_QUESTION_ASK.search(line):
                        continue
                    target = i
                    break
                if target < 0:
                    continue
                dlg[target] = {"speaker": speaker, "line": ask_line}
                changed = True
                continue
        dlg.insert(insert_at, {"speaker": speaker, "line": ask_line})
        changed = True

    if not changed:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = dlg
    return out, True


def apply_opening_causality_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    mom_lines_max: int | None = None,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """闭合 opening beat：优先复用 seed/已有句；只有权威 trigger 才允许本地生首句。"""
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _RE_ACCOUNTABILITY_LINE,
        _RE_BLAME_LINE,
        _RE_PARENT_TRIGGER_LINE,
        _RE_STUN_REACT_LINE,
        _beat_chain_entries,
        _intent_speech_acts,
        _line_fulfills_beat,
        _opening_authority_intent_kind,
        _opening_clause_matches_line,
        _opening_semantic_clauses,
        _parent_trigger_starts_as_late_reaction,
        collect_opening_causality_issues,
        opening_causality_passes,
        resolve_story_beat_chain,
    )

    chain = (
        beat_chain
        if isinstance(beat_chain, list) and beat_chain
        else resolve_story_beat_chain(story)
    )
    if len(chain) < 2:
        return story, False
    mom_max = 1 if mom_lines_max is None else max(0, int(mom_lines_max))
    if opening_causality_passes(story, chain, mom_lines_max=mom_max):
        return story, False
    issues = collect_opening_causality_issues(story, chain, mom_lines_max=mom_max)
    if not issues:
        return story, False

    entries = _beat_chain_entries(chain)
    beat1_entry = entries[0][1]
    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, False
    changed = False
    seed = dialogue_seed
    if not isinstance(seed, list):
        embedded_seed = story.get("dialogue_seed")
        seed = embedded_seed if isinstance(embedded_seed, list) else []

    def _seed_spoken_row(entry_index: int, entry: dict[str, Any]) -> dict[str, Any] | None:
        expected = str(entry.get("speaker") or "").strip()
        if not expected or not seed:
            return None
        candidates: list[tuple[Any, bool]] = []
        if 0 <= entry_index < len(seed):
            candidates.append((seed[entry_index], True))
        candidates.extend(
            (item, False)
            for i, item in enumerate(seed[: len(entries)])
            if i != entry_index
        )
        from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

        for item, same_slot in candidates:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != expected:
                continue
            raw_line = str(item.get("line") or "").strip()
            raw_intent = str(item.get("intent") or "").strip()
            spoken = raw_line
            if not spoken and raw_intent:
                parts = re.split(r"[：:]", raw_intent, maxsplit=1)
                spoken = parts[1].strip() if len(parts) == 2 else raw_intent
            if not spoken:
                continue
            if not spoken.endswith(("。", "！", "？", "!", "?", "~")):
                spoken += "。"
            if len(spoken) > CHAT_MAX_LINE_CHARS:
                continue
            if _line_fulfills_beat(expected, spoken, entry):
                return {"speaker": expected, "line": spoken}

            # H3b 同槽 seed 可能用语义标签表达 speech-act，而冒号后才是真正对白。
            # 例如 beat 写“嬉皮笑脸东拉西扯”，seed 写“嬉皮笑脸：姐你今天真好看”。
            # 仅信任“同槽 + 标签命中 beat + 冒号后为可说出口对白”，避免把动作 seed 当台词。
            if same_slot and raw_intent and re.search(r"[：:]", raw_intent):
                tag = re.split(r"[：:]", raw_intent, maxsplit=1)[0].strip()
                entry_intent = str(entry.get("intent") or entry.get("beat") or "")
                if 2 <= len(tag) <= 12 and tag in entry_intent:
                    from app.services.gold_story.scene import (
                        collect_voice_errors,
                        looks_like_narration_line,
                    )

                    seed_row = {"speaker": expected, "line": spoken}
                    if (
                        not looks_like_narration_line(spoken)
                        and not collect_voice_errors([seed_row])
                    ):
                        return seed_row

            # H3b seed 是已生成契约，可接受与 beat intent 的自然改写；
            # 但只在家长立规拍里把语义等价 seed 补成显式规则句，
            # 不放宽普通正文的 opening validator。
            intent = str(entry.get("intent") or "")
            if expected not in {"妈妈", "爸爸"} or _opening_authority_intent_kind(intent) != "rule":
                continue
            clauses = _opening_semantic_clauses(intent)
            line_han = "".join(re.findall(r"[\u4e00-\u9fff]", spoken))
            hits = sum(
                1
                for clause in clauses
                if _opening_clause_matches_line(clause, line_han)
            )
            required = len(clauses) if len(clauses) <= 2 else 2
            if not clauses or hits < required:
                continue
            rule_spoken = _intent_to_rule_line(spoken, require_rule_slot=False)
            if not rule_spoken:
                continue
            if (
                len(rule_spoken) <= CHAT_MAX_LINE_CHARS
                and _line_fulfills_beat(expected, rule_spoken, entry)
            ):
                return {"speaker": expected, "line": rule_spoken}
        return None

    # 对中间缺拍优先用 H3b seed 落地：seed 是已生成契约，不新增剧情事实，且不占 LLM 修稿预算。
    # 每次只补一拍后重新收集 issue，避免旧行号在插入后继续使用。
    for _ in range(min(3, len(entries))):
        probe = copy.deepcopy(story)
        probe["dialogue"] = [dict(row) for row in dlg]
        current_issues = collect_opening_causality_issues(
            probe, chain, mom_lines_max=mom_max,
        )
        if not current_issues:
            return probe, bool(changed)
        inserted = False
        for issue in current_issues:
            missing = issue.get("missing_beat")
            if not isinstance(missing, dict):
                continue
            missing_no = missing.get("beat")
            entry_index = next(
                (i for i, (beat_no, _entry) in enumerate(entries) if beat_no == missing_no),
                -1,
            )
            if entry_index < 0:
                continue
            entry = entries[entry_index][1]
            row = _seed_spoken_row(entry_index, entry)
            if row is None:
                continue
            expected = str(row.get("speaker") or "").strip()
            if expected == "妈妈" and mom_max >= 0:
                mom_n = sum(
                    1 for item in dlg
                    if str(item.get("speaker") or "").strip() == "妈妈"
                )
                if mom_n >= mom_max:
                    continue
            try:
                before_line = int(issue.get("before_line_no") or 1)
            except (TypeError, ValueError):
                before_line = 1
            insert_at = max(0, min(len(dlg), before_line - 1))
            dlg.insert(insert_at, row)
            changed = True
            inserted = True
            break
        if not inserted:
            break

    probe = copy.deepcopy(story)
    probe["dialogue"] = [dict(row) for row in dlg]
    if opening_causality_passes(probe, chain, mom_lines_max=mom_max):
        return probe, bool(changed)

    speaker = str(beat1_entry.get("speaker") or "").strip()
    if not speaker:
        return story, False
    beat1_acts = _intent_speech_acts(str(beat1_entry.get("intent") or ""))
    # 非权威旧事/陈述开场不能拿 authority 生成器生造台词；seed 也补不了就交上层修稿。
    if "trigger" not in beat1_acts or speaker not in {"妈妈", "爸爸"}:
        return story, False

    late_head_row = None
    first_row = dlg[0]
    if (
        str(first_row.get("speaker") or "").strip() == speaker
        and _parent_trigger_starts_as_late_reaction(str(first_row.get("line") or ""))
    ):
        late_head_row = first_row

    move_idx = -1
    for i, row in enumerate(dlg):
        if _line_fulfills_beat(
            str(row.get("speaker") or "").strip(),
            str(row.get("line") or "").strip(),
            beat1_entry,
        ):
            move_idx = i
            break

    def _matches_later_opening(row: dict[str, Any]) -> bool:
        row_speaker = str(row.get("speaker") or "").strip()
        row_line = str(row.get("line") or "").strip()
        return any(
            _line_fulfills_beat(row_speaker, row_line, entry)
            for _beat_no, entry in entries[1: min(3, len(entries))]
        )

    if move_idx > 0:
        dlg.insert(0, dlg.pop(move_idx))
        changed = True
    elif move_idx < 0:
        intent = str(beat1_entry.get("intent") or "")
        opening_line = _intent_to_authority_opening_line(intent, story)
        if not opening_line:
            # 立规 intent 若只是剧情描述，本地不伪造对白；保留此前安全 seed 补丁，
            # 其余缺拍交给上层限定范围修稿。
            return probe, bool(changed)
        new_row = {
            "speaker": speaker,
            "line": opening_line,
        }
        mom_n = sum(
            1
            for r in dlg
            if str(r.get("speaker") or "").strip() == speaker
        )
        if mom_max >= 0 and mom_n >= mom_max:
            # 新 beat1 已补在最前面时，先删后段重复的家长触发，保留愣住/收束反应。
            # 这样不会为了配额把真正的反应句删掉，却留下一个迟到且可能对象错位的“再次训话”。
            for j, row in enumerate(dlg):
                if str(row.get("speaker") or "").strip() != speaker:
                    continue
                line = str(row.get("line") or "")
                if (
                    row is late_head_row
                    or _RE_STUN_REACT_LINE.search(line)
                    or _matches_later_opening(row)
                ):
                    continue
                if (
                    _RE_ACCOUNTABILITY_LINE.search(line)
                    or _RE_BLAME_LINE.search(line)
                    or _RE_PARENT_TRIGGER_LINE.search(line)
                ):
                    dlg.pop(j)
                    changed = True
                    break
            mom_n = sum(
                1
                for r in dlg
                if str(r.get("speaker") or "").strip() == speaker
            )
            if mom_n >= mom_max and mom_max >= 0:
                # 仍超额时优先删非愣住/非收束家长句；愣住类只作为最后兜底。
                removed = False
                for j in range(len(dlg) - 1, -1, -1):
                    row = dlg[j]
                    if str(row.get("speaker") or "").strip() != speaker:
                        continue
                    if (
                        _RE_STUN_REACT_LINE.search(str(row.get("line") or ""))
                        or _matches_later_opening(row)
                    ):
                        continue
                    dlg.pop(j)
                    changed = True
                    removed = True
                    break
                if not removed:
                    # 所有家长句都是 opening 必需拍/愣住拍时，宁可交上层修稿，不能删拍“验过”。
                    return story, False
        dlg.insert(0, new_row)
        changed = True

    # 原首句若其实是家长对后续台词的回应（如“你说啥？”），补/前移 beat1 后
    # 必须把这条回应放回真正 beat2 之后；不能留下“beat1→回应→beat2”的倒序。
    if late_head_row is not None and len(entries) >= 2:
        reaction_idx = next(
            (i for i, row in enumerate(dlg) if row is late_head_row),
            -1,
        )
        if reaction_idx >= 0:
            reaction_row = dlg.pop(reaction_idx)
            beat2_entry = entries[1][1]
            beat2_idx = next(
                (
                    i
                    for i, row in enumerate(dlg)
                    if i > 0
                    and _line_fulfills_beat(
                        str(row.get("speaker") or "").strip(),
                        str(row.get("line") or "").strip(),
                        beat2_entry,
                    )
                ),
                -1,
            )
            if beat2_idx >= 0:
                dlg.insert(beat2_idx + 1, reaction_row)
                changed = True
            else:
                dlg.insert(min(reaction_idx, len(dlg)), reaction_row)

    if not changed:
        return story, False

    out = copy.deepcopy(story)
    out["dialogue"] = dlg
    if opening_causality_passes(out, chain, mom_lines_max=mom_max):
        return out, True
    return story, False


def apply_authority_punchline_local_patches(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """authority_punchline 结构兜底：开场立规 + 角色重挂；末尾 seed 归位。"""
    import copy

    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    chain = beat_chain
    if not isinstance(chain, list) or not chain:
        gb = story.get("gold_beat_chain")
        chain = gb if isinstance(gb, list) else None
    data = copy.deepcopy(story) if story.get("closing_mode") else dict(story)
    # 调用方偶发丢 closing_mode：有 beat 链时仍按权威开场兜底
    if not str(data.get("closing_mode") or "").strip() and chain:
        data["closing_mode"] = CLOSING_MODE_AUTHORITY_PUNCHLINE
    data, c1 = patch_authority_opening_speaker(data, beat_chain=chain)
    data, c2 = patch_authority_move_rule_to_front(data, beat_chain=chain)
    data, c3 = patch_authority_insert_rule_opening(data, beat_chain=chain)
    data, c4 = patch_authority_role_speakers(data, beat_chain=chain)
    data, c5 = patch_authority_insert_resist_after_reverse(data, beat_chain=chain)
    data, c6 = patch_authority_ensure_end_punch(data, beat_chain=chain)
    data, c7 = patch_authority_trim_after_cede(data, beat_chain=chain)
    data, c8 = patch_authority_cull_extra_mom_lines(data, beat_chain=chain)
    # 权威改 speaker 后必须再 seed 归位（专家：嵌在本函数末尾，避免调用点漏跑）
    c9 = False
    seed = dialogue_seed
    if seed is None:
        seed = data.get("dialogue_seed")
    if isinstance(seed, list) and seed:
        from app.services.gold_story.gold_chat.validate import (
            apply_seed_phrase_speaker_align,
        )

        data, c9 = apply_seed_phrase_speaker_align(
            data, dialogue_seed=seed
        )
    return data, c1 or c2 or c3 or c4 or c5 or c6 or c7 or c8 or c9

