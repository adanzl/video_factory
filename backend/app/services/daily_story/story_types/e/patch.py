"""E 类正文本地修稿。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地，
  以及不含主题词的类型通用短句（如「自己说的规矩，自己先破了」）。
- 禁止绑定具体 theme 的规则（按「挑食/青菜/零食」等关键词分支
  改写台词）——主题落到分支外时会整段盖成不贴题的模板文。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
- 改 speaker 须保住**主体一致**：帮腔孩子的讽刺句勿改判给妈妈
  （不一样/大人只许孩子说）；闭环句须戳穿方孩子说。
"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
)
from app.services.daily_story.story_types.e.humor import (
    RE_KID_ASK,
    RE_KID_FAKE_OPEN,
    RE_LOOP,
    RE_MOM_RULE,
    RE_MOM_SOFT,
    RE_MOM_WAFFLE,
)

_A_TAIL = re.compile(r"哪里不一样|都是听|那不一样")
_MOM_LINE_CAP = 8


def _is_e(story: dict) -> bool:
    from app.services.daily_story.story_types import resolve_story_type_code

    return resolve_story_type_code(story) == "E"


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


def _kid_roles(dialogue: list) -> tuple[str, str, dict[str, int]]:
    """按假开脱帮腔命中数判 (戳穿方, 帮腔方, 命中表)。

    帮腔命中相同则看谁追问多（追问多者为戳穿方）；默认 (昭昭, 灿灿)。
    """
    fake = {"昭昭": 0, "灿灿": 0}
    ask = {"昭昭": 0, "灿灿": 0}
    for d in dialogue:
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        if sp not in fake:
            continue
        ln = str(d.get("line") or "")
        if RE_KID_FAKE_OPEN.search(ln):
            fake[sp] += 1
        if RE_KID_ASK.search(ln):
            ask[sp] += 1
    if fake["昭昭"] == fake["灿灿"]:
        prober = "昭昭" if ask["昭昭"] >= ask["灿灿"] else "灿灿"
    else:
        prober = "昭昭" if fake["昭昭"] < fake["灿灿"] else "灿灿"
    return prober, ("灿灿" if prober == "昭昭" else "昭昭"), fake


def _adjacent_speaker(dialogue: list, i: int, name: str) -> bool:
    for j in (i - 1, i + 1):
        if 0 <= j < len(dialogue) and isinstance(dialogue[j], dict):
            if str(dialogue[j].get("speaker") or "").strip() == name:
                return True
    return False


def _next_kid_speaker(dialogue: list, before_i: int) -> str:
    """取 before_i 之前最近孩子句的另一人，避免末两句孩子同人硬卡。"""
    for j in range(before_i - 1, -1, -1):
        d = dialogue[j]
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        if sp == "昭昭":
            return "灿灿"
        if sp == "灿灿":
            return "昭昭"
    return "昭昭"


def patch_e_strip_a_close(story: dict) -> list[str]:
    """剥 A 式末四拍，改孩子闭环 + 妈妈破功。"""
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    prober, defender, _ = _kid_roles(dialogue)
    for i in range(len(dialogue) - 4, len(dialogue)):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        sp = str(d.get("speaker") or "").strip()
        if not _A_TAIL.search(line):
            continue
        if i == len(dialogue) - 1:
            d["speaker"] = "妈妈"
            new_line = "……行行行，算你说得对"
        elif i == len(dialogue) - 2:
            d["speaker"] = prober
            new_line = "你自己说的，你现在也这样"
        elif "那不一样" in line:
            # 「不一样」只许孩子2讽刺帮腔说；孩子句不动，妈妈句改判帮腔方
            if sp in ("昭昭", "灿灿"):
                continue
            d["speaker"] = defender
            new_line = "那不一样，妈妈是大人嘛"
        else:
            d["speaker"] = prober
            new_line = "那你刚才也破规矩了"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"E去A收束[{i}]")
    return notes


def patch_e_ensure_kid_ask(story: dict) -> list[str]:
    """中段缺孩子追问时，改一句孩子（通用自套反例，无主题词）。"""
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
    new_line = "那我也可以照你这样？"
    for d in mid:
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") not in ("昭昭", "灿灿"):
            continue
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append("E补孩子追问")
            break
    return notes


def patch_e_ensure_waffle(story: dict) -> list[str]:
    """缺妈妈改口时，在闭环前改一句妈妈（通用开脱，无主题词）。

    若已有孩子假替妈开脱（讽刺帮腔），不再硬塞妈妈自辩。
    """
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    lines = _lines(dialogue)
    speakers = _speakers(dialogue)
    if RE_MOM_WAFFLE.search("".join(lines)):
        return notes
    # 假开脱已在：孩子帮腔带开脱词 → 跳过
    if any(
        sp in ("昭昭", "灿灿")
        and re.search(r"你不懂|大人|不一样|不算", ln)
        for sp, ln in zip(speakers, lines)
    ):
        return notes
    # 找闭环前最近的妈妈句（模板勿用「不一样」——那是孩子讽刺专用词）
    loop_i = next(
        (i for i, ln in enumerate(lines) if RE_LOOP.search(ln)),
        len(dialogue) - 2,
    )
    new_line = "那是特殊情况，就这一次"
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
    prober, _, _ = _kid_roles(dialogue)
    d["speaker"] = prober
    d["line"] = "自己说的规矩，自己先破了"
    notes.append("E补追问闭环")
    return notes


def patch_e_loop_speaker(story: dict) -> list[str]:
    """闭环句主体修正：帮腔孩子说闭环属角色断裂，只改 speaker 给戳穿方。

    仅在帮腔线清晰（假开脱命中≥2 且比另一孩子多≥2）且不造成
    相邻同人时动手；单句局部修，不动台词内容。
    """
    notes: list[str] = []
    if not _is_e(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    prober, defender, fake = _kid_roles(dialogue)
    if fake[defender] < 2 or fake[defender] - fake[prober] < 2:
        return notes
    for i in range(len(dialogue) - 1, max(len(dialogue) - 5, -1), -1):
        d = dialogue[i]
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        ln = str(d.get("line") or "")
        if sp != defender or not RE_LOOP.search(ln):
            continue
        # 帮腔句本身（大人/不一样）不算闭环错位
        if RE_KID_FAKE_OPEN.search(ln):
            continue
        if _adjacent_speaker(dialogue, i, prober):
            break
        d["speaker"] = prober
        notes.append(f"E闭环换戳穿方[{i}]")
        break
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
    soft = "……行行行，算你说得对"
    loop_line = "自己说的规矩，自己先破了"
    last_sp = str(last.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "")
    prev = dialogue[-2] if isinstance(dialogue[-2], dict) else {}
    prev_sp = str(prev.get("speaker") or "").strip()
    prev_ln = str(prev.get("line") or "")

    # 末两句同人（孩子连说）时，倒数第二改闭环，末句改妈妈破功
    if (
        last_sp == prev_sp
        and last_sp in ("昭昭", "灿灿")
        and dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX
    ):
        if not RE_LOOP.search(prev_ln):
            prev["line"] = loop_line
            notes.append("E末前补闭环")
        last["speaker"] = "妈妈"
        last["line"] = soft
        notes.append("E末句改妈妈破功")
    else:
        soft_norm = soft.strip().rstrip("。！？")
        last_norm = last_ln.strip().rstrip("。！？")
        if last_sp == "妈妈" and RE_MOM_SOFT.search(last_ln) and last_norm == soft_norm:
            pass
        elif not RE_LOOP.search(prev_ln) and last_sp == "妈妈":
            if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
                last["line"] = soft
                notes.append("E末句补妈妈破功词")
        elif not RE_LOOP.search(prev_ln):
            if dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
                if last_sp != "妈妈":
                    if isinstance(prev, dict) and prev_sp == "妈妈":
                        dialogue[-2], dialogue[-1] = dialogue[-1], dialogue[-2]
                        dialogue[-1]["speaker"] = "妈妈"
                        dialogue[-1]["line"] = soft
                        notes.append("E末句对调妈妈破功")
                    else:
                        last["speaker"] = "妈妈"
                        last["line"] = soft
                        notes.append("E末句改妈妈破功")
        elif dialogue_char_count(soft) <= DAILY_STORY_LINE_CHARS_MAX:
            last["speaker"] = "妈妈"
            last["line"] = soft
            notes.append("E末句改妈妈破功")

    # 兜底：正文里末两句「孩子」若同人，改倒数第二孩子为另一人
    # （硬卡看的是孩子序列末两人，不是对白末两句）
    kids = [
        (i, d)
        for i, d in enumerate(dialogue)
        if isinstance(d, dict)
        and str(d.get("speaker") or "").strip() in ("昭昭", "灿灿")
    ]
    if len(kids) >= 2:
        i_a, a = kids[-2]
        _i_b, b = kids[-1]
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa == sb:
            a["speaker"] = "灿灿" if sa == "昭昭" else "昭昭"
            notes.append(f"E末两孩换人[{i_a}]")
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
    if len(mom_idx) <= _MOM_LINE_CAP:
        return notes
    # 砍中间多余妈妈句（保留首立论、改口、末破功）
    keep_first = mom_idx[0]
    keep_last = mom_idx[-1]
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
    dropped = 0
    for i in reversed(drop):
        if len(mom_idx) - dropped <= _MOM_LINE_CAP:
            break
        if isinstance(dialogue[i], dict):
            dialogue[i]["speaker"] = _next_kid_speaker(dialogue, i)
            dialogue[i]["line"] = "那你刚才呢？"
            dropped += 1
            notes.append(f"E削妈妈说教[{i}]")
    return notes


def patch_e_compress_body(story: dict) -> list[str]:
    """正文超过 16 句时，从中段删同型揭穿句（保留立论/闭环/破功）。"""
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
_RE_FILLER_TAIL = re.compile(
    r"(?:[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}|"
    r"了呢[了呀]|了呀[呢]|嘛了[呀]|了呢呀|"
    r"了呢|了呀|嘛了|呢吧|呀呢|呢嘛)$",
)
_RE_FILLER_INLINE = re.compile(
    r"了呢了呀|了呢呀|嘛了呀|了呢了|了呀呢",
)


def patch_e_strip_patch_garbage(story: dict) -> list[str]:
    """剥掉句内补字 patch 误粘的尾巴（还在亮着/你看/明明/了呢了呀等）。"""
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
        # 混合语气垫字（句中或句尾）
        new_line = _RE_FILLER_INLINE.sub("", new_line)
        new_line = _RE_FILLER_TAIL.sub("", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"E剥补字残[{i}]")
    return notes


def patch_e_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_e_strip_patch_garbage(story))
    notes.extend(patch_e_strip_a_close(story))
    notes.extend(patch_e_ensure_kid_ask(story))
    notes.extend(patch_e_ensure_waffle(story))
    notes.extend(patch_e_ensure_loop(story))
    notes.extend(patch_e_loop_speaker(story))
    notes.extend(patch_e_trim_mom_lecture(story))
    notes.extend(patch_e_closing_mom_soft(story))
    return notes
