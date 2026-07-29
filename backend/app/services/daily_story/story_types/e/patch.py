"""E 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.e.humor import (
    RE_KID_ASK,
    RE_LOOP,
    RE_MOM_RULE,
    RE_MOM_SOFT,
    RE_MOM_WAFFLE,
)

_A_TAIL = re.compile(r"哪里不一样|都是听|那不一样")
_RE_PICKY_THEME = re.compile(r"挑食|青菜|拨到碗边")
_RE_PICKY_RULE = re.compile(
    r"不准挑食|不许挑食|不能挑食|别挑食|挑食不行|"
    r"青菜.{0,6}(?:必须|得|要)吃",
)
_RE_PICKY_EYE = re.compile(r"拨到|拨开|碗边|拨了.{0,4}青菜")
_RE_PICKY_RELECTURE = re.compile(
    r"一口.{0,4}不(?:动|吃)|怎么不吃|多吃青菜|你要多吃|青菜都不动",
)
_RE_PICKY_PAD = re.compile(
    r"数数|蔫了|证明你不是|打自己脸|说话算话|夹一根|叶子都",
)


def _is_e(story: dict) -> bool:
    from app.services.daily_story.story_types import resolve_story_type_code

    return resolve_story_type_code(story) == "E"


def _theme_ctx(story: dict) -> str:
    return (
        str(story.get("conflict_core") or "")
        + str(story.get("_theme") or "")
        + str(story.get("theme") or "")
        + str(story.get("scene_title") or "")
    )


def _is_picky(story: dict) -> bool:
    return bool(_RE_PICKY_THEME.search(_theme_ctx(story)))


def _picky_rule_phrase(dialogue: list) -> str:
    for d in dialogue:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "妈妈":
            continue
        m = _RE_PICKY_RULE.search(str(d.get("line") or ""))
        if m:
            return m.group(0)
    return "不能挑食"

def _lines(dialogue: list) -> list[str]:
    return [
        str(d.get("line") or "") if isinstance(d, dict) else ""
        for d in dialogue
    ]


def _speakers(dialogue: list) -> list[str]:
    return [
        str(d.get("speaker") or "") if isinstance(d, dict) else ""
        for d in dialogue
    ]


def patch_e_strip_a_close(story: dict) -> list[str]:
    """剥 A 式末四拍，改孩子闭环 + 妈妈破功。"""
    notes: list[str] = []
    if not _is_e(story):
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
        if i == len(dialogue) - 1:
            d["speaker"] = "妈妈"
            new_line = "……行行行，算你说得对"
        elif i == len(dialogue) - 2:
            d["speaker"] = "昭昭"
            new_line = "你自己说的，你现在也这样"
        elif "那不一样" in line:
            d["speaker"] = "妈妈"
            new_line = "那是工作需要，不算数"
        else:
            d["speaker"] = "昭昭"
            new_line = "那你刚才也破规矩了"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"E去A收束[{i}]")
    return notes


def patch_e_ensure_mom_rule(story: dict) -> list[str]:
    """前段缺妈妈立论时，按主题补一句可被闭环的短规矩。

    挑食题另保因果：先立「不许挑食」，再抓拨青菜。
    """
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    theme_ctx = (
        str(story.get("conflict_core") or "")
        + str(story.get("_theme") or "")
        + str(story.get("theme") or "")
        + str(story.get("scene_title") or "")
    )
    is_picky = bool(re.search(r"挑食|青菜|拨到碗边", theme_ctx))
    if is_picky:
        rule_line = "吃饭不许挑食，青菜都得吃"
        rule_ok = re.compile(r"不准挑食|不许挑食|不能挑食|青菜.{0,6}吃")
        eye_re = re.compile(r"拨到|拨开|碗边|拨了.{0,4}青菜")
    elif re.search(r"睡觉|九点|刷手机|被窝", theme_ctx):
        rule_line = "九点了必须睡觉，快去躺着"
        rule_ok = re.compile(r"必须睡觉|九点了|说好不玩手机")
        eye_re = None
    elif re.search(r"零食|尝菜|试吃", theme_ctx):
        rule_line = "我说了，饭前不能吃零食"
        rule_ok = re.compile(r"不能吃零食|饭前")
        eye_re = None
    else:
        rule_line = "我说了，规矩就是规矩"
        rule_ok = RE_MOM_RULE
        eye_re = None

    if is_picky and eye_re is not None:
        rule_i = next(
            (
                i
                for i, d in enumerate(dialogue)
                if isinstance(d, dict)
                and str(d.get("speaker") or "") == "妈妈"
                and rule_ok.search(str(d.get("line") or ""))
            ),
            None,
        )
        eye_i = next(
            (
                i
                for i, d in enumerate(dialogue)
                if isinstance(d, dict)
                and str(d.get("speaker") or "") in ("昭昭", "灿灿")
                and eye_re.search(str(d.get("line") or ""))
            ),
            None,
        )
        if eye_i is not None and (rule_i is None or eye_i < rule_i):
            eye_line = "那你怎么把青菜拨到碗边了？"
            if isinstance(dialogue[eye_i], dict):
                raw = str(dialogue[eye_i].get("line") or "").strip()
                if eye_re.search(raw):
                    eye_line = raw
            mom_open = "昭昭，你最近菜吃得太少了，不能挑食哦"
            if dialogue_char_count(mom_open) > DAILY_STORY_LINE_CHARS_MAX:
                mom_open = "菜吃太少了，不能挑食哦"
            dialogue[0] = {"speaker": "妈妈", "line": mom_open}
            dialogue[1] = {"speaker": "昭昭", "line": eye_line}
            notes.append("E挑食因果：妈妈开场训后再抓拨开")
            return notes

        # 已有规矩但非妈妈开场：仍改成妈妈先训
        if (
            rule_i is not None
            and rule_i > 0
            and str(dialogue[0].get("speaker") or "") != "妈妈"
        ):
            eye_line = "那你怎么把青菜拨到碗边了？"
            for d in dialogue:
                if (
                    isinstance(d, dict)
                    and str(d.get("speaker") or "") in ("昭昭", "灿灿")
                    and eye_re.search(str(d.get("line") or ""))
                ):
                    eye_line = str(d.get("line") or "").strip()
                    break
            mom_open = "昭昭，你最近菜吃得太少了，不能挑食哦"
            if dialogue_char_count(mom_open) > DAILY_STORY_LINE_CHARS_MAX:
                mom_open = "菜吃太少了，不能挑食哦"
            dialogue[0] = {"speaker": "妈妈", "line": mom_open}
            if isinstance(dialogue[1], dict):
                dialogue[1]["speaker"] = "昭昭"
                dialogue[1]["line"] = eye_line
            notes.append("E挑食因果：改妈妈开场训孩子")
            return notes

    head = dialogue[: max(2, len(dialogue) // 2)]
    text = "".join(_lines(head))
    if rule_ok.search(text):
        return notes
    for d in head:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "妈妈":
            continue
        if dialogue_char_count(rule_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = rule_line
            notes.append("E补妈妈立论")
            break
    else:
        # 无妈妈句：插在第 2 句位置改写成妈妈
        if isinstance(dialogue[1], dict):
            dialogue[1]["speaker"] = "妈妈"
            dialogue[1]["line"] = rule_line
            notes.append("E补妈妈立论[1]")
    return notes

def patch_e_ensure_kid_ask(story: dict) -> list[str]:
    """中段缺孩子追问时，改一句昭昭。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[2:-3]
    text = "".join(_lines(mid))
    if RE_KID_ASK.search(text):
        return notes
    if _is_picky(story) and re.search(r"那我|算不算|拨开|晾着", text):
        return notes
    for d in mid:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") not in ("昭昭", "灿灿"):
            continue
        if _is_picky(story):
            new_line = "那我把肉拨开，也算晾着配饭？"
        else:
            new_line = "那你刚才那一口算不算啊"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("E补孩子追问")
            break
    return notes


def patch_e_ensure_waffle(story: dict) -> list[str]:
    """缺妈妈改口时，在闭环前改一句妈妈。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = _lines(dialogue)
    if RE_MOM_WAFFLE.search("".join(lines)):
        return notes
    if _is_picky(story) and re.search(r"晾|配饭|等会儿", "".join(lines)):
        return notes
    # 找闭环前最近的妈妈句
    loop_i = next(
        (i for i, ln in enumerate(lines) if RE_LOOP.search(ln)),
        len(dialogue) - 2,
    )
    if _is_picky(story):
        new_line = "我这是晾着，等会儿配饭吃"
    else:
        new_line = "那是尝咸淡，不算吃零食"
    for i in range(min(loop_i, len(dialogue) - 1) - 1, 1, -1):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "妈妈":
            continue
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"E补妈妈改口[{i}]")
            return notes
    # 强制改倒数第 3 句
    i = len(dialogue) - 3
    if isinstance(dialogue[i], dict):
        dialogue[i]["speaker"] = "妈妈"
        dialogue[i]["line"] = new_line
        notes.append(f"E补妈妈改口[{i}]")
    return notes


def patch_e_ensure_loop(story: dict) -> list[str]:
    """末段缺闭环时，改倒数第 2 句为孩子闭环。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    tail = "".join(_lines(dialogue[-4:]))
    if RE_LOOP.search(tail):
        return notes
    d = dialogue[-2]
    if not isinstance(d, dict):
        return notes
    d["speaker"] = "昭昭"
    if _is_picky(story):
        phrase = _picky_rule_phrase(dialogue)
        d["line"] = f"你自己说{phrase}"
    else:
        d["line"] = "你自己说不能吃，你现在也吃了"
    notes.append("E补追问闭环")
    return notes


def patch_e_picky_mid(story: dict) -> list[str]:
    """挑食中段：禁回训孩子、禁不一样、引话对齐开场原词、削注水。"""
    notes: list[str] = []
    if not _is_e(story) or not _is_picky(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes

    speakers = _speakers(dialogue)
    lines = _lines(dialogue)
    eye_i = next(
        (
            i
            for i, (sp, ln) in enumerate(zip(speakers, lines))
            if sp in ("昭昭", "灿灿") and _RE_PICKY_EYE.search(ln)
        ),
        None,
    )
    if eye_i is not None:
        for i in range(eye_i + 1, min(eye_i + 4, len(dialogue) - 1)):
            if speakers[i] != "妈妈":
                continue
            if _RE_PICKY_RELECTURE.search(lines[i]) or (
                _RE_PICKY_RULE.search(lines[i]) and i > 0
            ):
                dialogue[i]["line"] = "我这是晾着，等会儿配饭吃"
                notes.append(f"E挑食去回训[{i}]")
                speakers = _speakers(dialogue)
                lines = _lines(dialogue)
            break

    for i, (sp, ln) in enumerate(zip(speakers, lines)):
        if sp != "妈妈" or "不一样" not in ln:
            continue
        dialogue[i]["line"] = "我这是晾着，等会儿配饭吃"
        notes.append(f"E挑食去不一样[{i}]")
        speakers = _speakers(dialogue)
        lines = _lines(dialogue)

    phrase = _picky_rule_phrase(dialogue)
    for i in range(max(0, len(dialogue) - 4), len(dialogue) - 1):
        if speakers[i] not in ("昭昭", "灿灿"):
            continue
        ln = lines[i]
        if not RE_LOOP.search(ln):
            continue
        m = re.search(
            r"(不准挑食|不许挑食|不能挑食|别挑食)",
            ln,
        )
        if m and m.group(1) != phrase and phrase in (
            "不准挑食", "不许挑食", "不能挑食", "别挑食",
        ):
            dialogue[i]["line"] = ln.replace(m.group(1), phrase, 1)
            notes.append(f"E挑食引话对齐[{i}]")
            speakers = _speakers(dialogue)
            lines = _lines(dialogue)

    # 末段前注水：打自己脸/数叶子等改成自套反例
    for i in range(2, max(2, len(dialogue) - 3)):
        if speakers[i] not in ("昭昭", "灿灿"):
            continue
        if not _RE_PICKY_PAD.search(lines[i]):
            continue
        dialogue[i]["line"] = "那我把肉拨开，也算晾着配饭？"
        notes.append(f"E挑食去注水[{i}]")
        speakers = _speakers(dialogue)
        lines = _lines(dialogue)
        break

    # 挑食宜短：超 16 句砍中段
    while len(dialogue) > 16:
        n = len(dialogue)
        protected = {0, 1, n - 1, n - 2, n - 3}
        if eye_i is not None:
            protected.add(eye_i)
            protected.add(min(eye_i + 1, n - 1))
        drop_i = None
        for i in range(n - 4, 2, -1):
            if i in protected:
                continue
            drop_i = i
            break
        if drop_i is None:
            break
        dialogue.pop(drop_i)
        notes.append(f"E挑食删注水[{drop_i}]")
        speakers = _speakers(dialogue)
        lines = _lines(dialogue)
        eye_i = next(
            (
                i
                for i, (sp, ln) in enumerate(zip(speakers, lines))
                if sp in ("昭昭", "灿灿") and _RE_PICKY_EYE.search(ln)
            ),
            None,
        )

    return notes

def patch_e_closing_mom_soft(story: dict) -> list[str]:
    """末句须妈妈破功。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    last = dialogue[-1]
    if not isinstance(last, dict):
        return notes
    last_sp = str(last.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "")
    if last_sp == "妈妈" and RE_MOM_SOFT.search(last_ln):
        return notes
    # 上一句已闭环才改
    prev_ln = ""
    if isinstance(dialogue[-2], dict):
        prev_ln = str(dialogue[-2].get("line") or "")
    if not RE_LOOP.search(prev_ln) and last_sp == "妈妈":
        # 仅补软词
        soft = "……行行行，算你说得对"
        if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
            last["line"] = soft
            notes.append("E末句补妈妈破功词")
        return notes
    if not RE_LOOP.search(prev_ln):
        return notes
    soft = "……行行行，算你说得对"
    if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
        last["speaker"] = "妈妈"
        last["line"] = soft
        notes.append("E末句改妈妈破功")
    return notes


def patch_e_trim_mom_lecture(story: dict) -> list[str]:
    """妈妈台词过多时，合并中段空说教句为短句。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    speakers = _speakers(dialogue)
    mom_idx = [i for i, sp in enumerate(speakers) if sp == "妈妈"]
    if len(mom_idx) <= 8:
        return notes
    # 砍中间多余妈妈句（保留首立论、改口、末破功）
    keep_first = mom_idx[0]
    keep_last = mom_idx[-1]
    # 找改口句
    lines = _lines(dialogue)
    waffle_i = next(
        (i for i in mom_idx if RE_MOM_WAFFLE.search(lines[i])),
        mom_idx[min(2, len(mom_idx) - 1)],
    )
    drop = [
        i
        for i in mom_idx
        if i not in (keep_first, waffle_i, keep_last)
        and 1 < i < len(dialogue) - 2
    ]
    # 从后往前删，最多删到剩 8 句妈妈
    dropped = 0
    for i in reversed(drop):
        if len(mom_idx) - dropped <= 8:
            break
        # 改成昭昭短追问，避免句数塌
        if isinstance(dialogue[i], dict):
            dialogue[i]["speaker"] = "昭昭"
            dialogue[i]["line"] = "那你刚才呢"
            dropped += 1
            notes.append(f"E削妈妈说教[{i}]")
    return notes


def patch_e_compress_body(story: dict) -> list[str]:
    """正文超过 18 句时，从中段删同型揭穿句（保留立论/闭环/破功）。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) <= 16:
        return notes

    while len(dialogue) > 16:
        speakers = _speakers(dialogue)
        lines = _lines(dialogue)
        n = len(dialogue)
        loop_i = next(
            (i for i, ln in enumerate(lines) if RE_LOOP.search(ln)),
            n - 2,
        )
        waffle_i = next(
            (
                i
                for i, ln in enumerate(lines)
                if speakers[i] == "妈妈" and RE_MOM_WAFFLE.search(ln)
            ),
            None,
        )
        mom_rule_i = next(
            (
                i
                for i, ln in enumerate(lines[: max(3, n // 3)])
                if speakers[i] == "妈妈" and RE_MOM_RULE.search(ln)
            ),
            0,
        )
        protected = {
            0, 1, 2, 3,
            n - 1, n - 2, n - 3,
            loop_i, mom_rule_i,
        }
        if waffle_i is not None:
            protected.add(waffle_i)

        drop_i: int | None = None
        for i in range(n - 4, 3, -1):
            if i in protected:
                continue
            if speakers[i] in ("昭昭", "灿灿"):
                drop_i = i
                break
        if drop_i is None:
            for i in range(n - 4, 3, -1):
                if i in protected:
                    continue
                if speakers[i] == "妈妈" and i != mom_rule_i and i != n - 1:
                    drop_i = i
                    break
        if drop_i is None:
            for i in range(n - 4, 3, -1):
                if i not in protected:
                    drop_i = i
                    break
        if drop_i is None:
            break
        dialogue.pop(drop_i)
        notes.append(f"E删注水[{drop_i}]")
    return notes


_RE_PATCH_GARBAGE = re.compile(
    r"，(?:还在亮着呢?|你看呢?|明明呢?|地上也见|刚才那样|明明这样)$",
)
_RE_FILLER_TAIL = re.compile(r"(?:[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,})$")


def patch_e_strip_patch_garbage(story: dict) -> list[str]:
    """剥掉句内补字 patch 误粘的尾巴（还在亮着/你看/明明等）。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = _RE_PATCH_GARBAGE.sub("", line)
        # 叠词残留：「，你看，明明」
        new_line = re.sub(r"，你看，明明呢?$", "", new_line)
        new_line = re.sub(r"，明明，还在亮着呢?$", "", new_line)
        new_line = _RE_FILLER_TAIL.sub("", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"E剥补字残[{i}]")
    return notes


def patch_e_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_e_strip_patch_garbage(story))
    notes.extend(patch_e_strip_a_close(story))
    notes.extend(patch_e_ensure_mom_rule(story))
    notes.extend(patch_e_picky_mid(story))
    notes.extend(patch_e_ensure_kid_ask(story))
    notes.extend(patch_e_ensure_waffle(story))
    notes.extend(patch_e_ensure_loop(story))
    notes.extend(patch_e_closing_mom_soft(story))
    notes.extend(patch_e_picky_mid(story))
    notes.extend(patch_e_strip_patch_garbage(story))
    notes.extend(patch_e_strip_a_close(story))
    notes.extend(patch_e_ensure_loop(story))
    notes.extend(patch_e_closing_mom_soft(story))
    return notes