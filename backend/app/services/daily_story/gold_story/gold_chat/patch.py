"""gold_chat 本地补丁（M5/H、M2/C 结构）。"""

from __future__ import annotations

import re
from typing import Any

from app.services.daily_story.gold_story.gold_chat.validate import (
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
    RE_PRIOR_DAMAGE,
    RE_RETALIATION_DONE,
    _dialogue_rows,
    _iodine_close_line_index,
    _m5_phrase_hits,
    _parse_conflict_victim,
    _parse_fight_question_asker,
    _retaliation_missing_action,
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


def _escalate_line_for_context(pre_mom_lines: list[str]) -> str:
    blob = "".join(pre_mom_lines)
    if "画" in blob:
        return "这画我弄了好久呢！"
    if RE_PRIOR_DAMAGE.search(blob):
        return "哼，变不回来了！"
    return "哼，没那么容易算！"


_MAX_M5_CONSECUTIVE_FIXES = 8


def _pick_m5_bridge_line(
    speaker: str,
    prev_line: str,
    next_line: str,
) -> tuple[str, str]:
    alt = "昭昭" if speaker == "灿灿" else "灿灿"
    blob = prev_line + next_line
    if "拉手" in prev_line or "还打不" in next_line:
        return alt, "嗯……好吧。"
    if "不原谅" in next_line or "道歉也没用" in next_line:
        return alt, "哼！别说了！"
    if "赔" in blob or "撕" in blob or "弄花" in blob:
        return alt, "呜……别闹了！"
    if "画" in blob:
        return alt, "你住手！"
    return alt, "别说了！"


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
_M5_RULE_CANONICAL = "家规就是谁先动手谁道歉！"
_RE_MOM_RULE_REF = re.compile(r"妈妈(?:说过|说|讲|告诉)")


def patch_m5_retaliation_action(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """受害方互毁句缺当场动作时，改为「抢你画撕啦」类已完成破坏。"""
    import copy

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 6:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    out = copy.deepcopy(story)
    changed = False
    for idx, (sp, line) in enumerate(zip(speakers, lines)):
        if sp != victim:
            continue
        following = lines[idx + 1 : idx + 3]
        if RE_RETALIATION_DONE.search(line) and not re.search(
            r"也抢|那我也|我也", line
        ):
            out["dialogue"][idx]["line"] = "我也抢你画撕啦！你赔！"
            changed = True
            continue
        if not _retaliation_missing_action(line, following):
            continue
        new_line = "我也抢你画撕啦！你赔！"
        if len(new_line) > 30:
            new_line = "我也抢你画撕啦！"
        out["dialogue"][idx]["line"] = new_line
        changed = True
    return out, changed


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
    """服软方说了拒和/加码时，改由另一方 speaker（Pass2 本地）。"""
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
    """M5 立规缺 authority 词时句首补「家规就是」（Pass2 本地修，不打回 Pass1）。"""
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
            if len(new_line) <= max_line_chars:
                item["line"] = new_line
                changed = True
            elif len(_M5_RULE_CANONICAL) <= max_line_chars:
                item["line"] = _M5_RULE_CANONICAL
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
        elif len(_M5_RULE_CANONICAL) <= max_line_chars:
            item["line"] = _M5_RULE_CANONICAL
            changed = True
    return out, changed


def patch_m5_insert_authority_before_mom(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """妈妈介入前全无家规/规矩时，补一句 canonical 立规（句数满则替换嘴硬句）。"""
    import copy

    from app.services.daily_story.gold_story.scene import (
        CHAT_LINE_COUNT_MAX,
    )

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False
    first_mom = mom_indices[0]
    pre_mom = lines[: first_mom - 1]
    if any(RE_M5_AUTHORITY.search(x) for x in pre_mom):
        return story, False
    if len(_M5_RULE_CANONICAL) > max_line_chars:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    rule = {"speaker": "灿灿", "line": _M5_RULE_CANONICAL}
    insert_at = first_mom - 1
    if len(dlg) < CHAT_LINE_COUNT_MAX:
        dlg.insert(insert_at, rule)
        return out, True

    for j in range(first_mom - 2, -1, -1):
        if speakers[j] not in {"昭昭", "灿灿"}:
            continue
        cur = lines[j]
        if RE_M5_STUBBORN.search(cur) or RE_M5_ESCALATE.search(cur):
            dlg[j]["line"] = _M5_RULE_CANONICAL
            return out, True
    if insert_at >= 0 and speakers[insert_at - 1] in {"昭昭", "灿灿"}:
        dlg[insert_at - 1]["line"] = _M5_RULE_CANONICAL
        return out, True
    return story, False


_INJURY_LINE = "啊！额头磕到了，好疼！"


def patch_ensure_injury_after_push(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏收场稿：推搡后缺伤情时补一句受害方喊疼。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    if not any(RE_IODINE_CLOSE.search(x) for x in lines):
        return story, False
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_i = next((i for i, sp in enumerate(speakers) if sp == "妈妈"), len(rows))
    pre_mom = lines[:mom_i]
    if any(RE_INJURY.search(x) for x in pre_mom):
        return story, False
    push_i = next((i for i, x in enumerate(pre_mom) if "推" in x), -1)
    if push_i < 0:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    target = push_i + 1
    if target >= len(dlg):
        return story, False
    dlg[target]["speaker"] = "灿灿"
    dlg[target]["line"] = _INJURY_LINE
    return out, True


def patch_m5_fix_pre_mom_sequence(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈问谁先动手须晚于服软+立规+拒和+加码（Pass2 本地重排）。"""
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
    insert_at = last_i if last_i < mom_ask_i else last_i
    dlg.insert(insert_at + 1, mom_row)
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
    """碘伏/涂药妈妈句后删拖句 invent（Pass2 本地，不手改 export）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    iodine_idx = _iodine_close_line_index(lines)
    if iodine_idx <= 0 or iodine_idx >= len(rows):
        return story, False
    if iodine_idx == len(rows):
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
    """Pass2：M5 立规/拒和/加码同句合并时只保留立规（其余靠邻句/本地补拍）。"""
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
    """Pass2：「还打不打架」speaker 对齐 closing_intent（允许改 speaker）。"""
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
    """Pass2：站外兄弟称谓 → 姐弟映射（哥哥→姐姐，弟弟→昭昭）。"""
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
    """closing 齐声：缺问句则整段插入；有问句则补第二句「不打了」。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    fight_idx = next(
        (i for i, line in enumerate(lines, 1) if RE_FIGHT_QUESTION.search(line)),
        0,
    )
    asker = _parse_fight_question_asker(closing_intent) or "灿灿"
    closing_needed = bool(RE_FIGHT_QUESTION.search(closing_intent or ""))

    if fight_idx <= 0:
        if not closing_needed:
            return story, False
        iodine_idx = _iodine_close_line_index(lines)
        hand_i = next(
            (i for i, line in enumerate(lines) if "拉手" in line),
            -1,
        )
        if hand_i >= 0:
            insert_at = hand_i + 1
        elif iodine_idx > 0:
            insert_at = iodine_idx - 1
        else:
            insert_at = len(rows)
        out = copy.deepcopy(story)
        dlg = out["dialogue"]
        block = [
            {"speaker": asker, "line": "以后还打不打架？"},
            {"speaker": "昭昭", "line": "不打了！"},
            {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        ]
        for j, item in enumerate(block):
            dlg.insert(insert_at + j, item)
        return out, True

    kid_bukeda = [
        i
        for i in range(fight_idx + 1, len(lines) + 1)
        if speakers[i - 1] in {"昭昭", "灿灿"} and "不打了" in lines[i - 1]
    ]
    if len(kid_bukeda) >= 2:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if len(kid_bukeda) == 1:
        only_i = kid_bukeda[0]
        only_sp = speakers[only_i - 1]
        other = _sibling_partner(only_sp)
        insert_at = only_i
        insert_line = "不打了！这还差不多。" if other == "灿灿" else "不打了！"
        dlg.insert(insert_at, {"speaker": other, "line": insert_line})
        return out, True
    if closing_needed:
        insert_at = fight_idx
        dlg.insert(insert_at, {"speaker": "昭昭", "line": "不打了！"})
        dlg.insert(insert_at + 1, {"speaker": "灿灿", "line": "不打了！这还差不多。"})
        return out, True
    return story, False


def patch_fix_mom_ask_admission(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """妈妈问谁先动手后，昭昭须承认推/动手/先弄画。"""
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
    if mom_ask_i < 0 or mom_ask_i >= len(rows) - 1:
        return story, False
    next_i = mom_ask_i + 1
    if speakers[next_i] != "昭昭":
        return story, False
    line = lines[next_i]
    blames_sister = bool(
        re.search(r"姐姐先|是姐姐|都怪姐姐", line)
        and not re.search(r"我.{0,6}先", line)
    )
    admits = bool(re.search(r"推|动手|弄花|弄坏|我先|我……先", line))
    if admits and not blames_sister:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"][next_i]["line"] = "我……我先弄花的，姐姐对不起！"
    return out, True


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
        if "拉手" in line:
            item["line"] = "来，拉手。"
        else:
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
    """删妈妈问谁先动手之前的定责/扯平句（Pass2 本地）。"""
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
    """M5+H Pass2 本地补丁：称谓 → 定责 → 立规 → 拆合并 → 问句 speaker → 齐声 → 加码 → 碘伏后删尾。"""
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
    """妈妈介入前缺 M5 拒和/加码时本地补拍（与是否道歉无关）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 10:
        return story, False

    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False

    first_mom = mom_indices[0]
    pre_mom = lines[: first_mom - 1]
    stubborn_idx = next(
        (i for i, x in enumerate(pre_mom) if RE_M5_STUBBORN.search(x)),
        -1,
    )
    has_hard = stubborn_idx >= 0 or any(RE_M5_STUBBORN.search(x) for x in pre_mom)
    if stubborn_idx >= 0:
        has_escalate = any(
            RE_M5_ESCALATE.search(x) for x in pre_mom[stubborn_idx + 1 :]
        )
    else:
        has_escalate = any(RE_M5_ESCALATE.search(x) for x in pre_mom)
    if has_hard and has_escalate:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    candidate = _escalate_line_for_context(pre_mom)

    if stubborn_idx >= 0 and not has_escalate:
        insert_at = stubborn_idx + 1
        sp = str(dlg[insert_at].get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            sp = str(dlg[stubborn_idx].get("speaker") or "灿灿").strip()
        if len(candidate) <= 30:
            from app.services.daily_story.gold_story.scene import (
                CHAT_LINE_COUNT_MAX,
            )

            if len(dlg) >= CHAT_LINE_COUNT_MAX:
                dlg[stubborn_idx]["line"] = candidate
            else:
                dlg.insert(insert_at, {"speaker": sp, "line": candidate})
            return out, True

    kid_idx = _last_kid_idx_before_mom(dlg, first_mom)
    if kid_idx < 0:
        return story, False

    if not has_escalate:
        candidate = _escalate_line_for_context(pre_mom)
        cur = str(dlg[kid_idx].get("line") or "").strip()
        if RE_M5_STUBBORN.search(cur):
            for j in range(kid_idx - 1, -1, -1):
                if str(dlg[j].get("speaker") or "") not in {"昭昭", "灿灿"}:
                    continue
                prev = str(dlg[j].get("line") or "").strip()
                if not RE_M5_ESCALATE.search(prev) and len(candidate) <= 30:
                    dlg[j]["line"] = candidate
                    return out, True
                break
        elif len(candidate) <= 30 and not RE_M5_ESCALATE.search(cur):
            dlg[kid_idx]["line"] = candidate
            return out, True

    if not has_hard:
        stub = "哼，不原谅！"
        cur = str(dlg[kid_idx].get("line") or "").strip()
        if RE_M5_AUTHORITY.search(cur):
            return story, False
        if RE_M5_ESCALATE.search(cur):
            for j in range(kid_idx - 1, -1, -1):
                if str(dlg[j].get("speaker") or "") not in {"昭昭", "灿灿"}:
                    continue
                prev = str(dlg[j].get("line") or "").strip()
                if not RE_M5_STUBBORN.search(prev) and len(stub) <= 30:
                    dlg[j]["line"] = stub
                    return out, True
                break
        elif len(stub) <= 30 and not RE_M5_STUBBORN.search(cur):
            dlg[kid_idx]["line"] = stub
            return out, True

    return story, False


# 短 seed gold_chat：点题/closing 后另起第二轮（角色反转续写）
_SHORT_SEED_MAX = 12
_POST_CLOSE_TRIM_TYPES = frozenset({"C", "I", "L"})
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
        from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN

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
    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN
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
_RE_M2_C2 = re.compile(r"你刚说|你定的|规矩|你不是说")
_RE_M2_C3 = re.compile(r"凭什么你|你说了算|你又不是")
_RE_M2_C4 = re.compile(r"妈妈说过|上次|之前说过")


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
    if title and not str(out.get("scene_title") or "").strip():
        out["scene_title"] = title
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


def patch_m2_c_structure(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mechanism: str = "",
    theme: str = "",
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """M2+C 金稿：补 C1–C4 层触发词 + 末段回旋镖 + C类 punchline（仅 normalize）。"""
    import copy

    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

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

    snack_ctx = _m2_c_is_snack_homework_ctx(
        out, meat_ctx=meat_ctx, payload=payload
    )
    if snack_ctx:
        rebuilt, rebuild_notes = patch_m2_c_snack_beat_rebuild(
            out,
            payload=payload,
            boom_sp=boom_sp,
            last_sp=last_sp or "灿灿",
        )
        return rebuilt, rebuild_notes

    # setting 缺地点会扣开场分
    setting = str(out.get("setting") or "").strip()
    if setting and not re.search(r"厅|房|桌|沙发|厨房|门口|床", setting):
        out["setting"] = f"客厅，{setting}"
        notes.append("M2+C补setting地点")
        changed = True
    elif not setting:
        out["setting"] = "客厅沙发前，零食在灿灿手里"
        notes.append("M2+C补setting")
        changed = True

    # punchline_explain → C类前缀
    explain = str(out.get("punchline_explain") or "").strip()
    if explain and not explain.startswith("C类"):
        if meat_ctx and ("八百" in explain or "堵" in explain):
            out["punchline_explain"] = (
                "C类：灿灿用昭昭原话与妈妈规矩双重堵截，昭昭无奈嘀咕八百个心眼子。"
            )
        else:
            out["punchline_explain"] = f"C类：{explain}"
        notes.append("M2+C punchline→C类")
        changed = True

    # 主题锚定（relevancy 查 conflict_core+setting+前4句）
    theme_anchor = str(theme or out.get("scene_title") or "").strip()
    core = str(out.get("conflict_core") or "")
    setting = str(out.get("setting") or "")
    first4 = _m2_c_layer_blob(rows[:4])
    if (
        meat_ctx
        and theme_anchor
        and theme_anchor[:2] not in core + setting + first4
    ):
        suffix = "，昭昭无奈称妹妹八百个心眼子"
        if suffix not in core:
            out["conflict_core"] = (core.rstrip("。") + suffix + "。").replace("。。", "。")
            notes.append("M2+C conflict_core主题锚")
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
    blob = _m2_c_layer_blob(rows)

    # C1：首句求物须带争归属
    for item in rows[:3]:
        if str(item.get("speaker") or "") != "昭昭":
            continue
        ln = str(item.get("line") or "")
        if _RE_M2_C1.search(ln):
            break
        if "夹" in ln or "肉" in ln:
            item["line"] = ln.replace(
                "给我夹", "凭什么不能给我夹", 1,
            ).replace(
                "分我", "凭什么不能分我", 1,
            )
            if item["line"] == ln:
                item["line"] = f"凭什么不能{ln.lstrip('，,')}"
            notes.append("M2+C补C1争归属")
            changed = True
            break

    rows = _dialogue_rows(out)

    # 开场对白缺地点词：嵌进口语（禁「沙发前，」旁白定格起句）
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
    rows = _dialogue_rows(out)
    open_blob = _m2_c_layer_blob(rows[:3])
    if not re.search(r"客厅|沙发|餐桌|厨房|门口|床", open_blob):
        for item in rows[:2]:
            if str(item.get("speaker") or "") not in {"昭昭", "灿灿"}:
                continue
            ln = str(item.get("line") or "").strip()
            if re.search(r"零食|薯片|肉", ln):
                new_ln = re.sub(
                    r"(这包|那包)?(零食|薯片|肉)",
                    r"沙发上那包\2",
                    ln,
                    count=1,
                )
            else:
                m = re.match(r"^((?:昭昭|灿灿)[，,])?(.*)$", ln)
                prefix = (m.group(1) if m else "") or ""
                rest = (m.group(2) if m else ln) or ""
                new_ln = f"{prefix}沙发上{rest}".replace("沙发上沙发上", "沙发上")
            item["line"] = new_ln[:24]
            notes.append("M2+C开场嵌地点")
            changed = True
            break

    # 规则轮次：仅整件物/吃肉语境才补「才算」模板；零食作业本战禁注入举过头顶
    rows = _dialogue_rows(out)
    mid = rows[2:-4] if len(rows) >= 10 else rows[2:-2]
    mid_blob = _m2_c_layer_blob(mid)
    append_n = len(re.findall(r"才算|不算|追加一条", mid_blob))
    snack_ctx = (not meat_ctx) and bool(
        re.search(r"薯片|作业本|(?:零食.{0,8}作业)|(?:作业.{0,8}零食)", _m2_c_layer_blob(rows))
        or re.search(r"零食", _m2_c_layer_blob(rows[:4]))
        and re.search(r"作业|本子", _m2_c_layer_blob(rows))
    )
    if meat_ctx and append_n < 2 and mid:
        targets = [
            it
            for it in mid
            if str(it.get("speaker") or "") == "灿灿"
            and not re.search(
                r"之前|你刚说|凭什么|才算",
                str(it.get("line") or ""),
            )
        ]
        if len(targets) < 2:
            more = [
                it
                for it in mid
                if it not in targets
                and not re.search(r"之前|你刚说", str(it.get("line") or ""))
            ]
            targets = targets + more
        if targets:
            targets[0]["line"] = "光抱着不行，得举过头顶才算！"
            notes.append("M2+C补规则定义轮")
            changed = True
        if len(targets) >= 2:
            targets[1]["line"] = "还得证明三次才算真正拿到！"
            notes.append("M2+C补荒谬规则轮")
            changed = True
        elif len(mid) >= 2 and targets:
            other = next(
                (
                    it
                    for it in mid
                    if str(it.get("speaker") or "")
                    != str(targets[0].get("speaker") or "")
                ),
                None,
            )
            if other is not None:
                other["line"] = "那按哪条才算？你一条接一条！"
                notes.append("M2+C补规则追问")
                changed = True
    elif snack_ctx and mid:
        # 清掉误注入的整件物赛规
        for item in rows:
            ln = str(item.get("line") or "")
            if re.search(r"举过头顶|证明三次|光抱着不行", ln):
                sp = str(item.get("speaker") or "")
                if sp == "灿灿":
                    item["line"] = "零食归我，作业本归你，这才公平！"
                else:
                    item["line"] = "你偷吃还讲公平？"
                notes.append("M2+C清无关才算模板")
                changed = True
        # 零食战递进：威胁本子 / 吃光加码（贴 beat，不发明新赛规维度）
        rows = _dialogue_rows(out)
        blob = _m2_c_layer_blob(rows)
        if "撕" not in blob and len(rows) >= 8:
            for item in rows[3:8]:
                if str(item.get("speaker") or "") == "昭昭":
                    item["line"] = "你不还，我就撕你作业本！"
                    notes.append("M2+C补撕本威胁")
                    changed = True
                    break
        rows = _dialogue_rows(out)
        blob = _m2_c_layer_blob(rows)
        if "吃光" not in blob and "全吃" not in blob and len(rows) >= 8:
            for item in rows[4:9]:
                if str(item.get("speaker") or "") == "灿灿":
                    item["line"] = "你敢撕，我就把零食全吃光！"
                    notes.append("M2+C补吃光加码")
                    changed = True
                    break

    rows = _dialogue_rows(out)
    blob = _m2_c_layer_blob(rows)

    # C3：昭昭反驳须挑战权威
    if not _RE_M2_C3.search(blob):
        for item in rows[4:10]:
            if str(item.get("speaker") or "") != "昭昭":
                continue
            ln = str(item.get("line") or "")
            if "胖" in ln or "哼" in ln:
                item["line"] = f"凭什么你说了算，{ln.lstrip('，,')}"
                notes.append("M2+C补C3挑战权威")
                changed = True
                break

    rows = _dialogue_rows(out)
    blob = _m2_c_layer_blob(rows)

    # 从正文抽出可核对的规矩短句（供回旋镖引语有前文）
    rule_frag = ""
    for item in rows[:-4]:
        ln = str(item.get("line") or "")
        # 优先完整双归句，避免截成「作业本归你，公平」
        m = re.search(
            r"((?:零食|薯片).{0,4}归我.{0,2}(?:作业本|本子).{0,2}归你)",
            ln,
        )
        if m:
            rule_frag = re.sub(r"[呢呀嘛吧啊「」]", "", m.group(1))[:14]
            break
        m = re.search(r"((?:零食|作业|肉|牛奶).{0,6}归.{0,4})", ln)
        if m:
            rule_frag = m.group(1)[:10]
            break
        if "不吃就不吃" in ln or "不爱吃" in ln:
            rule_frag = "不吃就不吃"
            break
    if meat_ctx or rule_frag == "不吃就不吃":
        boom_line = "你刚说「不吃就不吃」，说不通！"
    elif rule_frag:
        boom_line = f"你刚说「{rule_frag}」，说不通！"
    elif snack_ctx or "零食" in blob or "作业" in blob:
        # 确保前文有出处后再引
        has_src = any(
            re.search(r"零食.{0,4}归我", str(it.get("line") or ""))
            for it in rows[:-4]
        )
        if not has_src:
            for item in rows[0:4]:
                if str(item.get("speaker") or "") == "灿灿":
                    item["line"] = "零食归我，作业本归你，公平吧？"
                    notes.append("M2+C补规矩出处")
                    changed = True
                    break
        boom_line = "你刚说「零食归我，作业本归你」，说不通！"
    else:
        boom_line = "你刚说的规矩，现在说不通了！"
    boom_line = boom_line[:24]

    # 末句嘴硬：禁「哼」（会触发无破功软收 -20）
    if last_sp and rows:
        last = rows[-1]
        want_last = "下次我还这样！"
        if str(last.get("speaker") or "") != last_sp or "哼" in str(
            last.get("line") or ""
        ):
            last["speaker"] = last_sp
            last["line"] = want_last
            notes.append("M2+C末句嘴硬speaker")
            changed = True
        elif not re.search(r"下次|还这样|嘴硬|算你|藏", str(last.get("line") or "")):
            last["line"] = want_last
            notes.append("M2+C末句嘴硬话")
            changed = True

    rows = _dialogue_rows(out)
    # 倒数第二句固定为 boom_sp 回旋镖（须落在 validate 的 tail4）
    if len(rows) >= 2:
        prev = rows[-2]
        prev["speaker"] = boom_sp
        prev["line"] = boom_line
        notes.append("M2+C末段回旋镖")
        changed = True
        for item in rows[-4:-2] + rows[-1:]:
            ln = str(item.get("line") or "")
            if not re.search(r"你刚说|你说的|你不是说", ln):
                continue
            if item is prev:
                continue
            item["line"] = re.sub(
                r"(不行[！!])?(?:你刚说|你说的|你不是说)[^，。！?]{0,16}",
                "",
                ln,
            ).strip("，, ") or "真的不行！"
            notes.append("M2+C清尾段杂引")
            changed = True

    # C4：新证据（之前/妈妈）
    rows = _dialogue_rows(out)
    blob = _m2_c_layer_blob(rows)
    if not re.search(r"之前|妈妈说过|上次|柜子里", blob):
        for item in rows[4:10]:
            if str(item.get("speaker") or "") not in {"昭昭", "灿灿"}:
                continue
            ln = str(item.get("line") or "").strip()
            item["line"] = f"之前说过的，{ln}".replace("，，", "，")[:24]
            notes.append("M2+C补C4新证据")
            changed = True
            break

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

    # 零食战：清掉中段误引的残缺回旋镖（只保留末二句那条）
    if snack_ctx:
        rows = _dialogue_rows(out)
        for item in rows[:-2]:
            ln = str(item.get("line") or "")
            if not re.search(r"你刚说|你说的|你不是说", ln):
                continue
            item["line"] = re.sub(
                r"(不行[！!])?(?:你刚说|你说的|你不是说)[^，。！?]{0,18}",
                "",
                ln,
            ).strip("，,！!。？ ") or "你休想！"
            notes.append("M2+C清中段杂引")
            changed = True

        # 字数不够时用本场语义扩句，禁止靠「现在立刻」凑字
        rows = _dialogue_rows(out)
        from app.services.daily_story.prompts import (
            DAILY_STORY_BODY_CHARS_MIN,
            dialogue_total_chars,
        )

        expands = (
            (r"^你等着", "你等着，薯片不还我就撕本子！"),
            (r"^你敢撕", "你敢撕，我就把零食全吃光！"),
            (r"^你休想", "你休想，规矩是你自己定的！"),
            (r"^放下", "放下我的作业本，那是明天要交的！"),
            (r"^你偷吃", "你偷吃我的零食，还敢讲公平？"),
            (r"^好好好", "好好好，薯片给你，别撕我本子！"),
            (r"^下次", "下次我先把规矩写清楚！"),
        )
        guard = 0
        while dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN and guard < 10:
            guard += 1
            grew = False
            for item in rows:
                ln = str(item.get("line") or "").strip()
                if len(ln) >= 22:
                    continue
                for pat, repl in expands:
                    if re.search(pat, ln) and ln != repl[:24]:
                        item["line"] = repl[:24]
                        notes.append("M2+C零食扩句")
                        changed = True
                        grew = True
                        break
                if grew:
                    break
            if not grew:
                # 给偏短中段句加本场细节（不增句）
                for item in rows[2:-2]:
                    ln = str(item.get("line") or "").strip()
                    if len(ln) >= 20:
                        continue
                    sp = str(item.get("speaker") or "")
                    if sp == "昭昭" and "本子" not in ln and "撕" not in ln:
                        item["line"] = (ln.rstrip("！。") + "，不还就撕本子！")[:24]
                    elif sp == "灿灿" and "吃" not in ln:
                        item["line"] = (ln.rstrip("！。") + "，敢撕我全吃光！")[:24]
                    else:
                        continue
                    notes.append("M2+C零食扩句")
                    changed = True
                    grew = True
                    break
            if not grew:
                break
            rows = _dialogue_rows(out)

        # 扩句后可能冲掉末二拍，再钉一次
        rows = _dialogue_rows(out)
        if len(rows) >= 2 and last_sp:
            rows[-1]["speaker"] = last_sp
            if "下次" not in str(rows[-1].get("line") or ""):
                rows[-1]["line"] = "下次我先把规矩写清楚！"
            rows[-2]["speaker"] = boom_sp
            rows[-2]["line"] = boom_line
            notes.append("M2+C零食末拍重钉")
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
            if "吃给你看" in ln_a:
                a["line"] = "哼，那你吃吧，我看着你吃呢。"
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

    out = copy.deepcopy(story)
    out["dialogue"] = rows[:cut]
    dropped = len(rows) - cut
    return out, [f"gold_chat删复读环({dropped}句)"]


def patch_m2_c_fix_opening(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """M2+C：首句须昭昭求肉，灿灿不能无前置引话堵截。"""
    import copy

    payload = payload if isinstance(payload, dict) else {}
    rows = _dialogue_rows(story)
    if not rows:
        return story, []

    first = rows[0]
    sp0 = str(first.get("speaker") or "").strip()
    ln0 = str(first.get("line") or "")
    if sp0 != "灿灿" or not re.search(r"不爱吃|你刚说", ln0):
        return story, []

    sc = payload.get("scene_contract")
    if isinstance(sc, dict):
        chain = sc.get("beat_chain") or []
        if chain and isinstance(chain[0], dict):
            b0_sp = str(chain[0].get("speaker") or "")
            if b0_sp == "昭昭":
                return story, []

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if not isinstance(dlg, list):
        return story, []
    dlg.insert(
        0,
        {
            "speaker": "昭昭",
            "line": "餐桌旁，灿灿，你盘里肉好香，凭什么不能给我夹一块？",
        },
    )
    return out, ["M2+C补开场求肉"]


def patch_m2_c_ensure_seed_close(
    story: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """M2+C 整件肉：缺 seed 收束则补妈妈+八百个心眼子；牛奶/公平类不注入。"""
    import copy

    payload = payload if isinstance(payload, dict) else {}
    if not m2_c_meat_whole_item_context(story, payload=payload):
        return story, []

    rows = _dialogue_rows(story)
    if not rows:
        return story, []

    blob = _m2_c_layer_blob(rows)
    notes: list[str] = []
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if not isinstance(dlg, list):
        return story, []

    seed = payload.get("dialogue_seed")
    mom_line = "吃商这方面谁能比得过我。"
    close_line = "这妹妹，八百个心眼子呢。"
    if isinstance(seed, list):
        for item in seed:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "") == "妈妈":
                intent = str(item.get("intent") or "")
                m = re.search(r"[「\"]([^」\"]+)[」\"]", intent)
                if m:
                    mom_line = m.group(1)
                elif "吃商" in intent:
                    mom_line = "吃商这方面谁能比得过我。"
            if str(item.get("speaker") or "") == "昭昭" and "八百" in str(
                item.get("intent") or ""
            ):
                close_line = "这妹妹，八百个心眼子呢！"

    if "八百个心眼" not in blob:
        if not any(str(r.get("speaker") or "") == "妈妈" for r in rows):
            dlg.append({"speaker": "妈妈", "line": mom_line})
            notes.append("M2+C补妈妈收束")
        dlg.append({"speaker": "昭昭", "line": close_line})
        notes.append("M2+C补点题收束")

    return out, notes


def patch_gold_chat_c_seed_bridge(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mechanism: str = "",
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """M2+C 整件肉：妈妈出场前补「再要/再堵」短来回；非肉战跳过。"""
    import copy

    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if st != "C" or mech != "M2":
        return story, []
    if not m2_c_meat_whole_item_context(story, payload=payload):
        return story, []

    rows = _dialogue_rows(story)
    if len(rows) < 6:
        return story, []

    blob = "".join(str(r.get("line") or "") for r in rows)
    if (
        "故意馋" in blob
        or "谁让你先说不爱吃" in blob
        or "明天的是明天的" in blob
    ):
        return story, []

    mom_i = next(
        (i for i, r in enumerate(rows) if str(r.get("speaker") or "") == "妈妈"),
        -1,
    )
    if mom_i < 2:
        return story, []

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if not isinstance(dlg, list):
        return story, []
    insert = [
        {"speaker": "昭昭", "line": "你……你就故意馋我！"},
        {"speaker": "灿灿", "line": "馋的就是你，谁让你先说不爱吃。"},
        {"speaker": "昭昭", "line": "我明天不吃零食了，换一口肉行不行？"},
        {"speaker": "灿灿", "line": "明天的是明天的，今天的肉我说了算，不分！"},
        {"speaker": "昭昭", "line": "哼，你就仗着自己盘里有肉！"},
    ]
    dlg[mom_i:mom_i] = insert
    return out, ["gold_chat补seed再堵来回"]

