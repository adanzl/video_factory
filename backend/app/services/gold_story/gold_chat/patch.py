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


def patch_remap_sibling_terms(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """精修：站外兄弟称谓 → 姐弟映射（哥哥→姐姐，弟弟→昭昭）。"""
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


def _intent_to_rule_line(intent: str) -> str:
    """beat0 intent → 可说出口的短立规句（须命中立规槽正则）。"""
    text = str(intent or "").strip()
    text = re.sub(r"^(?:立规|约好|规定|规矩|定规|说好|约定)[：:]", "", text).strip()
    if not text:
        text = "谁先完成谁先用"
    # 无抽象立规槽时补「说好了，」保证机审可识别（不绑单篇词）
    if not RE_AUTH_RULE_SLOT.search(text):
        text = f"说好了，{text}"
    if not text.endswith(("。", "！", "？", "~")):
        text = text + "。"
    if len(text) > 28:
        text = text[:27] + "。"
    # 截断后若槽位丢失，回退到稳妥短句
    if not RE_AUTH_RULE_SLOT.search(text):
        return "说好了，谁先完成谁先用。"
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
    rule = {"speaker": beat0, "line": _intent_to_rule_line(intent)}
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
    if authority_kind == "rule" and not (
        "作业" in text or "没写" in text or "没做" in text
    ):
        return _intent_to_rule_line(raw)
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


def apply_opening_causality_local_patch(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """缺 beat_chain 首句触发时：前移已有责备句或插入首句妈妈触发。"""
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _RE_BLAME_LINE,
        _RE_STUN_REACT_LINE,
        _beat_chain_entries,
        _line_fulfills_beat,
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
    speaker = str(beat1_entry.get("speaker") or "").strip()
    if not speaker:
        return story, False

    dlg = [dict(x) for x in (story.get("dialogue") or []) if isinstance(x, dict)]
    if not dlg:
        return story, False

    move_idx = -1
    for i, row in enumerate(dlg):
        if _line_fulfills_beat(
            str(row.get("speaker") or "").strip(),
            str(row.get("line") or "").strip(),
            beat1_entry,
        ):
            move_idx = i
            break

    changed = False
    if move_idx > 0:
        dlg.insert(0, dlg.pop(move_idx))
        changed = True
    elif move_idx < 0:
        intent = str(beat1_entry.get("intent") or "")
        new_row = {
            "speaker": speaker,
            "line": _intent_to_authority_opening_line(intent, story),
        }
        mom_n = sum(
            1
            for r in dlg
            if str(r.get("speaker") or "").strip() == speaker
        )
        if mom_max >= 0 and mom_n >= mom_max:
            for j in range(len(dlg) - 1, -1, -1):
                row = dlg[j]
                if str(row.get("speaker") or "").strip() != speaker:
                    continue
                line = str(row.get("line") or "")
                if _RE_STUN_REACT_LINE.search(line) and not _RE_BLAME_LINE.search(line):
                    dlg.pop(j)
                    changed = True
                    break
            mom_n = sum(
                1
                for r in dlg
                if str(r.get("speaker") or "").strip() == speaker
            )
            if mom_n >= mom_max and mom_max >= 0:
                for j in range(len(dlg) - 1, -1, -1):
                    if str(dlg[j].get("speaker") or "").strip() == speaker:
                        dlg.pop(j)
                        changed = True
                        break
        dlg.insert(0, new_row)
        changed = True

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

