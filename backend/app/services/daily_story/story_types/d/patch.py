"""D 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
    truncate_overlong_line,
)
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.d.humor import (
    RE_BOOM_CLOSE,
    RE_FIX,
    RE_LITERAL,
    RE_MESS,
)
from app.services.daily_story.story_types.quality import RE_SOFT_LAST

_A_TAIL = re.compile(r"哪里不一样|都是听|那不一样|完全不一样|跟.{0,6}不一样")
_RE_RULE = re.compile(
    r"不许|别碰|别晃|轻点|慢点|系紧|规矩|叮嘱|不准|(?<![只])不能|"
    r"别夹|别浇|别多|别响|别堆|轻拿|轻轻|别乱|只能|别太",
)
_RE_CLOSING_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)
_WAFFLE = re.compile(
    r"没有毛病|死板|坚持执行|脑子怎么|转不过弯|特殊补救|我这是帮你",
)
_D_MAX_LINES = 16  # 成片 ≤16，17 起判拖沓扣好笑分
# 中段引话降级用：改后不再命中 RE_BOOM_CLOSE，收束那一处保持不动
_BOOM_SOFTEN_MAP = {
    "你自己说": "你说的",
    "你刚才说": "你说的",
    "你刚说": "你说的",
    "你现在也": "你这会儿也",
    "你也碰了": "你这会儿碰了",
    "你也动了": "你这会儿动了",
}
_BOOM_SOFTEN_RE = re.compile("|".join(_BOOM_SOFTEN_MAP))


def _is_d(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    return parse_story_type_code(punchline=punch) == "D"


def _quote_grounded(frag: str, hay: str) -> bool:
    clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", frag)
    hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
    if len(clean) < 3:
        return True
    run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
    for i in range(len(clean) - run + 1):
        if clean[i : i + run] in hay2:
            return True
    return False


def _pick_d_cite(cancan_line: str) -> str:
    """从灿灿叮嘱句抽可引子串（优先带别/轻/不许等，宜短）。"""
    text = re.sub(r"^[「」\"'‘’]+|[「」\"'‘’]+$", "", cancan_line.strip())
    m = re.search(
        r"((?:别|不许|不准|只能|轻点|轻轻|轻拿|慢慢|系紧)"
        r"[\u4e00-\u9fff]{1,5})",
        text,
    )
    if m:
        chunk = re.sub(r"[哦啊呀呢吧嘛啦]+$", "", m.group(1).strip())
        if len(chunk) >= 3:
            return chunk[:8]
    for m in re.finditer(r"[^，。！？…；;]{3,8}", text):
        chunk = re.sub(r"[哦啊呀呢吧嘛啦]+$", "", m.group(0).strip())
        if len(chunk) < 3:
            continue
        if _RE_RULE.search(chunk) or re.search(
            r"别|轻|不许|不准|只能|慢慢|系紧", chunk,
        ):
            return chunk[:8]
    compact = re.sub(r"[的话呢呀嘛吧啊啦哦]", "", text)
    return compact[:8] if len(compact) >= 3 else text[:8]


def _first_cancan_rule(dialogue: list) -> str:
    """取前段灿灿叮嘱句（避开末段补救/嘴硬）。"""
    n = len(dialogue)
    end = max(3, n - 4)
    for item in dialogue[:end]:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "灿灿":
            continue
        ln = str(item.get("line") or "")
        if _RE_RULE.search(ln) or re.search(
            r"别.{1,8}|只能|轻轻|轻点|轻拿", ln,
        ):
            return ln
    return ""


def patch_d_align_boomerang_quote(story: dict) -> list[str]:
    """收束引话未接地时，改成前文灿灿叮嘱的连续子串。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    rule = _first_cancan_rule(dialogue)
    if not rule:
        return notes
    cite = _pick_d_cite(rule)
    if not cite or len(cite) < 3:
        return notes

    # 优先改倒数第 2 句；否则改末 4 句里昭昭的回旋镖
    candidates = [len(dialogue) - 2]
    for i in range(len(dialogue) - 4, len(dialogue)):
        if i >= 0 and i not in candidates:
            candidates.append(i)

    for i in candidates:
        if i < 0 or i >= len(dialogue):
            continue
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(d.get("line") or "")
        m = _RE_CLOSING_QUOTE.search(line)
        if not m:
            continue
        frag = m.group(1).strip()
        prior = "".join(
            str(x.get("line") or "")
            for x in dialogue[:i]
            if isinstance(x, dict) and str(x.get("speaker") or "") == "灿灿"
        )
        if _quote_grounded(frag, prior):
            continue
        head = line[: m.start(1)]
        # 尾巴若是改写续写，收成「你现在也破了」避免再造无出处
        new_line = f"{head}{cite}"
        if not re.search(r"现在|却|也", line[m.end(1) :]):
            new_line = f"{head}{cite}，你现在也破了"
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            room = DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(head)
            short = cite if dialogue_char_count(cite) <= room else cite[: max(4, room)]
            new_line = f"{head}{short}"
            if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
                new_line = truncate_overlong_line(new_line)
        if new_line != line:
            d["line"] = new_line
            notes.append(f"D引话对齐[{i}]")
            break
    return notes


def patch_d_fix_closing_roles(story: dict) -> list[str]:
    """末两句焊死：倒数第 2＝昭昭回旋镖，末句＝灿灿嘴硬。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    prev = dialogue[-2]
    last = dialogue[-1]
    if not isinstance(prev, dict) or not isinstance(last, dict):
        return notes
    prev_sp = str(prev.get("speaker") or "").strip()
    last_sp = str(last.get("speaker") or "").strip()
    prev_ln = str(prev.get("line") or "")
    last_ln = str(last.get("line") or "")

    # 角色反了：灿灿回旋镖 + 昭昭哼
    if prev_sp == "灿灿" and RE_BOOM_CLOSE.search(prev_ln) and last_sp == "昭昭":
        dialogue[-2], dialogue[-1] = last, prev
        notes.append("D收束角色对调")
        prev = dialogue[-2]
        last = dialogue[-1]
        prev_sp = str(prev.get("speaker") or "").strip()
        last_sp = str(last.get("speaker") or "").strip()
        prev_ln = str(prev.get("line") or "")
        last_ln = str(last.get("line") or "")

    if prev_sp != "昭昭":
        prev["speaker"] = "昭昭"
        notes.append("D回旋镖speaker→昭昭")
    if last_sp != "灿灿":
        last["speaker"] = "灿灿"
        notes.append("D末句speaker→灿灿")

    if not RE_BOOM_CLOSE.search(str(prev.get("line") or "")):
        rule = _first_cancan_rule(dialogue)
        cite = _pick_d_cite(rule) if rule else "别这样"
        boom = f"你自己说{cite}"
        if dialogue_char_count(boom) > DAILY_STORY_LINE_CHARS_MAX:
            boom = truncate_overlong_line(boom)
        prev["line"] = boom
        notes.append("D收束补回旋镖")

    if not RE_SOFT_LAST.search(str(last.get("line") or "")) and not re.search(
        r"哼|算了|行吧|我自己", str(last.get("line") or ""),
    ):
        last["line"] = "哼，算了，我自己来"
        notes.append("D末句改嘴硬")
    return notes


def patch_d_align_opening_action(story: dict) -> list[str]:
    """开场邀约与正文叮嘱串场时，把开场动词改成叮嘱同动作。

    例：开场「帮我叠刚晾好的衣服」+ 叮嘱「别夹太紧」→ 开场改「帮我挂」。
    """
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    opening = dialogue[:2]
    rule = _first_cancan_rule(dialogue)
    if not rule:
        return notes
    open_text = "".join(str(d.get("line") or "") for d in opening if isinstance(d, dict))
    # 叮嘱是夹/晾/挂，开场却是叠 → 改叠
    if re.search(r"夹|晾|挂", rule) and "叠" in open_text:
        for d in opening:
            if not isinstance(d, dict):
                continue
            ln = str(d.get("line") or "")
            if "叠" not in ln:
                continue
            new_ln = ln.replace("叠刚晾好的衣服", "挂衣服").replace("叠衣服", "挂衣服")
            new_ln = new_ln.replace("叠", "挂")
            if dialogue_char_count(new_ln) > DAILY_STORY_LINE_CHARS_MAX:
                new_ln = truncate_overlong_line(new_ln)
            if new_ln != ln:
                d["line"] = new_ln
                notes.append("D开场叠→挂对齐叮嘱")
        if notes:
            disc = story.get("discovery_opening")
            if isinstance(disc, list) and len(disc) >= 2:
                for i in range(min(2, len(disc))):
                    if isinstance(disc[i], dict) and isinstance(dialogue[i], dict):
                        disc[i]["line"] = dialogue[i].get("line")
                        disc[i]["speaker"] = dialogue[i].get("speaker")
    return notes


def patch_d_strip_mom_mentions(story: dict) -> list[str]:
    """D 禁妈妈：对白里「妈妈说」等提法删掉或改成灿灿说。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if "妈妈" not in line:
            continue
        new_line = re.sub(r"妈妈说|听妈妈的|别告诉妈妈", "听我说", line)
        new_line = new_line.replace("妈妈", "")
        new_line = re.sub(r"，，+", "，", new_line).strip("， ")
        if not new_line:
            continue
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            new_line = truncate_overlong_line(new_line)
        if new_line != line:
            d["line"] = new_line
            notes.append(f"D去妈妈提及[{i}]")
    return notes


def patch_d_strip_mom(story: dict) -> list[str]:
    """D 主戏姐弟：删掉妈妈插话（留给 E 类）。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    dropped = 0
    for i in reversed(range(len(dialogue))):
        d = dialogue[i]
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "妈妈":
            dialogue.pop(i)
            dropped += 1
    if dropped:
        notes.append(f"D删妈妈插话×{dropped}")
    return notes


def patch_d_trim_duplicate_rule(story: dict) -> list[str]:
    """前段灿灿重复唠叨同一条规矩时删后句。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    seen_rule = False
    i = 0
    while i < min(len(dialogue), 10):
        d = dialogue[i]
        if not isinstance(d, dict):
            i += 1
            continue
        sp = str(d.get("speaker") or "").strip()
        line = str(d.get("line") or "")
        if sp in ("灿灿", "妈妈") and _RE_RULE.search(line):
            if seen_rule:
                dialogue.pop(i)
                notes.append(f"D删重复立规[{i}]")
                continue
            seen_rule = True
        i += 1
    return notes


def patch_d_trim_waffle(story: dict) -> list[str]:
    """删中段空辩/说教复读句。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    for i in range(2, len(dialogue) - 4):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if _WAFFLE.search(line):
            dialogue.pop(i)
            notes.append(f"D删空辩[{i}]")
            return patch_d_trim_waffle(story)
    return notes


def patch_d_compress_body(story: dict) -> list[str]:
    """超过 18 句时从中段删注水，保留立规/一锤/破规/回旋镖。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) <= _D_MAX_LINES:
        return notes

    while len(dialogue) > _D_MAX_LINES:
        lines = [
            str(d.get("line") or "") if isinstance(d, dict) else ""
            for d in dialogue
        ]
        speakers = [
            str(d.get("speaker") or "") if isinstance(d, dict) else ""
            for d in dialogue
        ]
        n = len(dialogue)
        mess_i = next((i for i, ln in enumerate(lines) if RE_MESS.search(ln)), None)
        fix_i = next((i for i, ln in enumerate(lines) if RE_FIX.search(ln)), None)
        boom_i = next(
            (i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)),
            n - 2,
        )
        protected = {0, 1, 2, 3, n - 1, n - 2, n - 3, n - 4, boom_i}
        if mess_i is not None:
            protected.add(mess_i)
        if fix_i is not None:
            protected.add(fix_i)

        drop_i: int | None = None
        for i in range(n - 5, 3, -1):
            if i in protected:
                continue
            if _WAFFLE.search(lines[i]):
                drop_i = i
                break
        if drop_i is None:
            for i in range(n - 5, 3, -1):
                if i in protected:
                    continue
                if speakers[i] in ("昭昭", "灿灿") and RE_LITERAL.search(lines[i]):
                    if sum(1 for ln in lines if RE_LITERAL.search(ln)) > 2:
                        drop_i = i
                        break
        if drop_i is None:
            for i in range(n - 5, 3, -1):
                if i not in protected:
                    drop_i = i
                    break
        if drop_i is None:
            break
        dialogue.pop(drop_i)
        notes.append(f"D删注水[{drop_i}]")
    return notes


def patch_d_strip_a_close(story: dict) -> list[str]:
    """剥 A 式末四拍词，改回旋镖收束。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    for i in range(len(dialogue) - 4, len(dialogue)):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not _A_TAIL.search(line):
            continue
        sp = str(d.get("speaker") or "")
        if i == len(dialogue) - 1:
            new_line = "……哼，算了"
            if sp not in ("灿灿", "妈妈"):
                d["speaker"] = "灿灿"
        elif i == len(dialogue) - 2:
            new_line = "那你刚才说别碰，你现在也碰了"
            d["speaker"] = "昭昭"
        elif "那不一样" in line:
            new_line = "你自己说别碰的"
            d["speaker"] = "昭昭"
        else:
            new_line = "现在不碰谁收拾啊"
            if sp == "昭昭":
                d["speaker"] = "灿灿"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"D去A收束[{i}]")
    return notes


def patch_d_ensure_literal(story: dict) -> list[str]:
    """中段缺字面执行时，改一句昭昭为「按你说的」。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-4]
    text = "".join(str(d.get("line") or "") for d in mid if isinstance(d, dict))
    if RE_LITERAL.search(text):
        return notes
    for d in mid:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "昭昭":
            continue
        new_line = "那我按你说的，照做就是了"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("D补字面执行")
            break
    return notes


def patch_d_ensure_mess(story: dict) -> list[str]:
    """缺可见后果时，在破规前补一句搞砸。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    if RE_MESS.search("".join(lines)):
        return notes
    end = len(dialogue) - 4
    i = max(3, end - 3)
    if not isinstance(dialogue[i], dict):
        return notes
    dialogue[i]["speaker"] = "昭昭"
    dialogue[i]["line"] = "倒了……全掉地上了"
    notes.append(f"D补后果[{i}]")
    return notes


def patch_d_ensure_mess_in_mid(story: dict) -> list[str]:
    """后果只出现在末段 last4：把后果关键词挪到 body（last4 之前）。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes

    lines: list[str] = [
        str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue
    ]
    n = len(lines)
    body_text = "".join(lines[: max(0, n - 4)])
    tail4_text = "".join(lines[-4:])

    # 校验报的正是：tail4 有后果，但 body 没后果
    if not RE_MESS.search(tail4_text) or RE_MESS.search(body_text):
        return notes

    # 优先选靠中段的 i，保证仍在 body 范围（last4 之前）
    prefer_center = n - 6
    candidates = [
        idx
        for idx in range(3, max(3, n - 4))
        if isinstance(dialogue[idx], dict)
        and not RE_LITERAL.search(str(dialogue[idx].get("line") or ""))
    ]
    if candidates:
        i = min(candidates, key=lambda idx: abs(idx - prefer_center))
    else:
        i = max(3, n - 6)
        i = min(i, max(3, n - 5))
        if i < 0 or i >= n or not isinstance(dialogue[i], dict):
            # 找一个替换点（仍限制在 body 范围）
            for j in range(max(3, n - 10), max(3, n - 4)):
                if 0 <= j < n and isinstance(dialogue[j], dict):
                    i = j
                    break
            else:
                return notes

    cur_line = str(dialogue[i].get("line") or "")
    # 已有后果则不再动
    if RE_MESS.search(cur_line):
        return notes

    addition = "倒了"
    room = DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(cur_line)
    if room < dialogue_char_count(addition):
        # 没空位：不硬塞，避免截断破坏句子
        return notes

    new_line = f"{cur_line}{addition}"
    dialogue[i]["speaker"] = "昭昭"
    dialogue[i]["line"] = new_line
    notes.append(f"D追加中段后果[{i}]")
    return notes


def patch_d_ensure_fix(story: dict) -> list[str]:
    """回旋镖前须有叮嘱方破规补救。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    fix_i = next((i for i, ln in enumerate(lines) if RE_FIX.search(ln)), None)
    boom_i = next(
        (i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)),
        None,
    )
    if fix_i is not None and (boom_i is None or fix_i < boom_i):
        return notes
    # 找末四拍前灿灿句改写
    end = len(dialogue) - 4
    for j in range(end - 1, 2, -1):
        if not isinstance(dialogue[j], dict):
            continue
        if str(dialogue[j].get("speaker") or "") not in ("灿灿", "妈妈"):
            continue
        new_line = "我来扶，你别乱动"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            dialogue[j]["line"] = new_line
            notes.append(f"D补破规[{j}]")
            break
    return notes


def patch_d_ensure_boomerang(story: dict) -> list[str]:
    """末段缺回旋镖时补「你自己说…你现在也…」。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    full = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    # 前文已有收束回旋镖则勿在尾巴硬塞第二发
    if RE_BOOM_CLOSE.search(full):
        last = dialogue[-1]
        if isinstance(last, dict) and not RE_SOFT_LAST.search(
            str(last.get("line") or ""),
        ):
            # 末句不是软收且无回旋镖词：若倒数第二已是回旋镖则只修末句
            prev = dialogue[-2]
            if isinstance(prev, dict) and RE_BOOM_CLOSE.search(
                str(prev.get("line") or ""),
            ):
                last["speaker"] = "灿灿"
                last["line"] = "……哼，算了"
                notes.append("D补末句嘴硬")
        return notes
    d = dialogue[-2]
    if not isinstance(d, dict):
        return notes
    d["speaker"] = "昭昭"
    rule_hint = _first_cancan_rule(dialogue)
    cite = _pick_d_cite(rule_hint) if rule_hint else ""
    if cite:
        boom_line = f"你自己说{cite}"
    elif "晃" in rule_hint or "晃" in str(story.get("conflict_core") or ""):
        boom_line = "你自己说不许晃，你现在也晃了"
    elif "碰" in rule_hint:
        boom_line = "你自己说别碰，你现在也碰了"
    elif "慢" in rule_hint or "擦" in rule_hint:
        boom_line = "你自己说慢慢擦，你现在也用力了"
    else:
        boom_line = "你自己说过的，你现在也破了"
    if dialogue_char_count(boom_line) > DAILY_STORY_LINE_CHARS_MAX:
        boom_line = truncate_overlong_line(boom_line)
    d["line"] = boom_line
    notes.append("D补回旋镖")
    last = dialogue[-1]
    if isinstance(last, dict) and not RE_SOFT_LAST.search(str(last.get("line") or "")):
        last["speaker"] = "灿灿"
        last["line"] = "……哼，算了"
        notes.append("D补末句嘴硬")
    return notes


def patch_d_closing_speaker(story: dict) -> list[str]:
    """末句若为妈妈但无破功语气，且上一句已是回旋镖，改末句 speaker 为灿灿。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 3:
        return notes

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes

    last_sp = str(last.get("speaker") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "")

    if last_sp == "妈妈" and prev_sp in ("昭昭", "灿灿"):
        if RE_SOFT_LAST.search(last_ln) or "行吧" in last_ln or "算了" in last_ln:
            return notes
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("D末句speaker妈妈→姐弟嘴硬")
    return notes


def patch_d_strip_nitpick(story: dict) -> list[str]:
    """中段抠「你又没说/也包括」车轱辘，改回动作抬杠。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-4]
    nit_re = re.compile(r"你又没说|只说了|也包括|没说别的|当然包括")
    seen = 0
    for i, d in enumerate(mid):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not nit_re.search(line):
            continue
        seen += 1
        if seen <= 1:
            continue
        sp = str(d.get("speaker") or "")
        new_line = (
            "我一直在轻轻叠啊"
            if sp == "昭昭"
            else "你叠歪了，快停手"
        )
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"D去空辩[{i + 2}]")
    return notes


def patch_d_trim_second_boom(story: dict) -> list[str]:
    """哼/算了后若再开回旋镖，砍到第一次软收（可留一句无回旋镖的尾巴）。"""
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    soft_i = next(
        (
            i
            for i, d in enumerate(dialogue)
            if isinstance(d, dict)
            and re.search(r"哼|算了", str(d.get("line") or ""))
        ),
        None,
    )
    if soft_i is None or soft_i >= len(dialogue) - 2:
        return notes
    later_boom = any(
        isinstance(dialogue[i], dict)
        and RE_BOOM_CLOSE.search(str(dialogue[i].get("line") or ""))
        for i in range(soft_i + 1, len(dialogue))
    )
    if not later_boom:
        return notes
    # 保留软收 + 最多 2 句无回旋镖尾巴
    keep = soft_i + 1
    for i in range(soft_i + 1, min(len(dialogue), soft_i + 3)):
        ln = str(dialogue[i].get("line") or "") if isinstance(dialogue[i], dict) else ""
        if RE_BOOM_CLOSE.search(ln):
            break
        keep = i + 1
    if keep < len(dialogue):
        del dialogue[keep:]
        notes.append(f"D砍二次回旋镖→{keep}句")
    return notes


def patch_d_dedupe_boomerang(story: dict) -> list[str]:
    """引话回旋镖只留末段那一处，前面的改写成普通引述。

    「你自己说/你刚才说」出现两次就判复读压好笑分；中段本该用
    「你说的/照你说的」，把正式回旋镖留给收束。
    """
    notes: list[str] = []
    if not _is_d(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes

    hits = [
        i
        for i, d in enumerate(dialogue)
        if isinstance(d, dict) and RE_BOOM_CLOSE.search(str(d.get("line") or ""))
    ]
    if len(hits) < 2:
        return notes

    for i in hits[:-1]:
        line = str(dialogue[i].get("line") or "")
        new_line = _BOOM_SOFTEN_RE.sub(
            lambda m: _BOOM_SOFTEN_MAP[m.group(0)], line,
        )
        if new_line != line:
            dialogue[i]["line"] = new_line
            notes.append(f"D去回旋镖复读[{i}]")
    return notes


def patch_d_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_d_strip_mom(story))
    notes.extend(patch_d_strip_mom_mentions(story))
    notes.extend(patch_d_align_opening_action(story))
    notes.extend(patch_d_trim_duplicate_rule(story))
    notes.extend(patch_d_strip_a_close(story))
    notes.extend(patch_d_strip_nitpick(story))
    notes.extend(patch_d_trim_waffle(story))
    notes.extend(patch_d_ensure_literal(story))
    notes.extend(patch_d_ensure_mess(story))
    notes.extend(patch_d_ensure_mess_in_mid(story))
    # 若“挪后果”覆盖了中段字面执行关键词，这里再兜底一次
    notes.extend(patch_d_ensure_literal(story))
    notes.extend(patch_d_ensure_fix(story))
    notes.extend(patch_d_ensure_boomerang(story))
    notes.extend(patch_d_fix_closing_roles(story))
    notes.extend(patch_d_closing_speaker(story))
    notes.extend(patch_d_align_boomerang_quote(story))
    notes.extend(patch_d_trim_second_boom(story))
    notes.extend(patch_d_compress_body(story))
    notes.extend(patch_d_strip_a_close(story))
    notes.extend(patch_d_trim_waffle(story))
    notes.extend(patch_d_ensure_fix(story))
    notes.extend(patch_d_ensure_boomerang(story))
    notes.extend(patch_d_fix_closing_roles(story))
    notes.extend(patch_d_align_boomerang_quote(story))
    notes.extend(patch_d_trim_second_boom(story))
    notes.extend(patch_d_dedupe_boomerang(story))
    return notes
