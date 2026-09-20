"""I 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.i.validate import (
    RE_I_SURRENDER,
    RE_SOUL_QUESTION,
    RE_SPEECHLESS,
    RE_WIN_STUBBORN,
    find_i_close_index,
)

_I_CLOSING_TAIL_ALLOW = 1
_RE_INDOOR_SETTING = re.compile(r"卧室|客厅|厨房|餐厅|书桌|餐桌|沙发")
_ORAL_WIN_LINE = "不乐意就别拿别人低分嚷！"
_ORAL_SPEECHLESS_LINE = "我……我……"
# ≤24 字硬上限；留余量勿贴边
_I_SOUL_SWAP_LINE = "换你被到处说低分，你乐意吗？"
_RE_SOUL_WINNER = re.compile(
    r"还得会|好不好|照你这么说|那照你|评论.{0,8}吗|"
    r"爱学习|你爱吗|灵魂|拷问|换你|乐意吗|跟你无关|也没关系"
)
# 嘴硬争锋残留：语塞句里仍在辩，不算真正败北
_RE_SPEECHLESS_STILL_ARGUES = re.compile(
    r"反正|没错|就是|不怪我|没关系|偏就|不信|才能说|比别人强"
)


def _find_parent_soul_idx(dialogue: list) -> int:
    """正文首次家长灵魂拷问下标；无则 -1。"""
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "")
        if sp not in ("妈妈", "爸爸"):
            continue
        if (
            _RE_SOUL_WINNER.search(ln)
            or "换你" in ln
            or "乐意吗" in ln
            or "冰箱" in ln
        ):
            return i
    return -1


def _propaganda_roles(story: dict) -> tuple[str, str]:
    prop, vict = "昭昭", "灿灿"
    try:
        from app.services.gold_story.gold_chat.validate import (
            _parse_conflict_propaganda_roles,
        )

        roles = _parse_conflict_propaganda_roles(
            str(story.get("conflict_core") or "")
        )
        if roles:
            prop, vict = roles
    except Exception:
        pass
    return prop, vict


_RE_ADULT_DEBATE = re.compile(
    r"只有比别人强|才能评论|资格评论|有权评论|凭本事评论"
)
_RE_INVENTED_PROP = re.compile(r"拿桶|拎桶|提桶|泼水|拿刀|拿棍")
_RE_RELAY_PRESENT = re.compile(
    r"姐姐说|妹妹说|哥哥说|弟弟说|灿灿说|昭昭说|她说该|他说该"
)
_RE_SCORE_N = re.compile(r"(?<!\d)(\d{1,3})分")
_RE_YOU_SCORE = re.compile(r"你(?:也)?考了?(?P<n>\d{1,3})分")


def _setting_blob(story: dict) -> str:
    return " ".join(
        str(story.get(k) or "")
        for k in ("setting", "scene_title", "key", "conflict_core")
    )


def patch_i_seal_after_parent_soul(story: dict) -> list[str]:
    """家长灵魂拷问 + 对方语塞后立刻收束：裁抢答/空降道具/转述，补口语制敌。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    soul_idx = _find_parent_soul_idx(dialogue)
    winner = ""
    if soul_idx >= 0 and isinstance(dialogue[soul_idx], dict):
        winner = str(dialogue[soul_idx].get("speaker") or "").strip()
    if soul_idx < 0 or not winner:
        return notes

    # 被拷问方：优先 conflict 宣传方；否则取拷问前最后一句姐弟
    target = ""
    prop, _vict = _propaganda_roles(story)
    if prop:
        target = prop
    if not target:
        for j in range(soul_idx - 1, -1, -1):
            if not isinstance(dialogue[j], dict):
                continue
            sp = str(dialogue[j].get("speaker") or "").strip()
            if sp in {"昭昭", "灿灿"}:
                target = sp
                break
    if not target:
        target = "昭昭"

    speechless_idx = -1
    for i in range(soul_idx + 1, min(soul_idx + 4, len(dialogue))):
        if not isinstance(dialogue[i], dict):
            continue
        sp = str(dialogue[i].get("speaker") or "").strip()
        if sp == winner:
            continue
        if sp != target:
            # 受害方抢在语塞位 → 改归被拷问方
            if sp in {"昭昭", "灿灿"}:
                dialogue[i]["speaker"] = target
                notes.append("I语塞speaker归被拷问方")
            else:
                continue
        line = str(dialogue[i].get("line") or "")
        compact_tail = re.sub(r"[我…\.\s。！!？?，,]", "", line)
        keeps_arguing = bool(
            re.search(r"反正|才能说|比别人强|不怪我|没关系|偏就|不信|就是", line)
        )
        if (
            "说不出话" in line
            or "一时" in line
            or len(re.findall(r"真的|不行|了呀|了呢|嘛了", line)) >= 2
            or (RE_SPEECHLESS.search(line) and (keeps_arguing or len(compact_tail) > 4))
            or not RE_SPEECHLESS.search(line)
        ):
            dialogue[i]["line"] = _ORAL_SPEECHLESS_LINE
            notes.append("I拷问后改语塞")
        speechless_idx = i
        break
    if speechless_idx < 0:
        # 拷问后缺被拷问方语塞：插入
        dialogue.insert(
            soul_idx + 1,
            {"speaker": target, "line": _ORAL_SPEECHLESS_LINE},
        )
        notes.append("I补被拷问方语塞")
        speechless_idx = soul_idx + 1

    keep = dialogue[: speechless_idx + 1]
    removed = len(dialogue) - len(keep)
    if removed > 0:
        story["dialogue"] = [x for x in keep if isinstance(x, dict)]
        notes.append(f"I语塞后裁抢答拖尾 {removed}句")
    else:
        story["dialogue"] = dialogue
    notes.extend(_ensure_oral_win_at_end(story, winner))
    return notes


def patch_i_expand_before_soul(story: dict) -> list[str]:
    """语塞封口后若字数不足：只在家长拷问前加争锋，勿在收束后垫字。"""
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes

    def _chars() -> int:
        return sum(
            len(str(d.get("line") or "").strip())
            for d in dialogue
            if isinstance(d, dict)
        )

    soul_idx = _find_parent_soul_idx(dialogue)
    if soul_idx < 2:
        return notes

    # 从 conflict 解析宣传/受害，勿写死昭昭宣传（防过拟合）
    prop, vict = _propaganda_roles(story)

    fillers = [
        (prop, "我就是要说，你管得着吗，全楼都该听！"),
        (vict, "你再说一次试试，我同学都笑我丢脸！"),
        (prop, "高分就该谢我，低分就怪分数，这怎么是歪理？"),
        (vict, "你拿我分数当笑话讲，也太过分了吧！"),
        (prop, "我又没瞎编，卷子上写得明明白白！"),
        (vict, "你快放下卷子，别再满屋子嚷嚷了！"),
        (prop, "事实摆那儿，我宣传怎么了！"),
        (vict, "你再宣传一次，我跟妈妈告状去！"),
    ]
    need = max(0, DAILY_STORY_BODY_CHARS_MIN - _chars())
    max_insert = 2 if need > 30 else (1 if need > 0 else 0)
    # 按拷问前上一句交替起手，降低连说改 speaker 对调风险
    prev_sp = ""
    if soul_idx > 0 and isinstance(dialogue[soul_idx - 1], dict):
        prev_sp = str(dialogue[soul_idx - 1].get("speaker") or "").strip()
    if prev_sp == prop:
        fillers = fillers[1:] + fillers[:1]
    existing = {_i_line_core(str(d.get("line") or "")) for d in dialogue if isinstance(d, dict)}
    existing.discard("")
    inserted = 0
    for sp, line in fillers:
        if _chars() >= DAILY_STORY_BODY_CHARS_MIN and len(dialogue) >= 12:
            break
        if inserted >= max_insert:
            break
        key = _i_line_core(line)
        if not key or key in existing or any(
            key in old or old in key for old in existing if len(old) >= 6
        ):
            continue
        dialogue.insert(soul_idx, {"speaker": sp, "line": line})
        existing.add(key)
        soul_idx += 1
        inserted += 1
        if inserted >= 8:
            break
    # 仍不够：把拷问前短句扩到宜长（勿叠同一尾巴造成复读感；勿超单句上限）
    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
    )

    grow_tails = {
        prop: ["，管你怎么想", "，我说定了", "，我就这理"],
        vict: ["，快还我卷子", "，我跟妈妈说", "，你别再嚷"],
    }
    # 全稿已用过的尾巴不再叠，防「我就这理」复读
    used_tails = {
        t[1:]
        for t in (
            grow_tails[prop] + grow_tails[vict]
        )
        if any(
            t[1:] in str(d.get("line") or "")
            for d in dialogue
            if isinstance(d, dict)
        )
    }
    while _chars() < DAILY_STORY_BODY_CHARS_MIN:
        grew = False
        for i in range(soul_idx):
            if not isinstance(dialogue[i], dict):
                continue
            sp = str(dialogue[i].get("speaker") or "").strip()
            line = str(dialogue[i].get("line") or "").strip()
            if sp not in {prop, vict} or dialogue_char_count(line) >= 20:
                continue
            for extra in grow_tails.get(sp, []):
                bare = extra[1:]
                if bare in line or bare in used_tails:
                    continue
                cand = line.rstrip("！。？") + extra + "！"
                if dialogue_char_count(cand) > DAILY_STORY_LINE_CHARS_MAX:
                    continue
                dialogue[i]["line"] = cand
                used_tails.add(bare)
                grew = True
                inserted += 1
                break
            if grew:
                break
        if not grew:
            break
    if inserted:
        story["dialogue"] = dialogue
        notes.append(f"I拷问前补争锋至{_chars()}字")
    notes.extend(patch_i_fix_parent_sibling_voice(story))
    return notes


def patch_i_strip_premature_speechless(story: dict) -> list[str]:
    """拷问前禁止伪语塞：结巴/接不上却仍嘴硬 → 改回争锋。

    抽象条件：RE_SPEECHLESS 命中且在家长灵魂拷问之前；不绑单篇词表。
    """
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    soul_idx = _find_parent_soul_idx(dialogue)
    if soul_idx < 0:
        soul_idx = len(dialogue)
    prop, vict = _propaganda_roles(story)
    prop_alts = [
        "事实摆那儿，我宣传怎么了！",
        "高分就该谢我，低分就怪分数！",
        "我就是要说，管你怎么想！",
    ]
    vict_alts = [
        "你拿我分数当笑话讲，也太过分！",
        "你再宣传一次，我跟妈妈告状去！",
        "你快放下卷子，别再满屋子嚷！",
    ]
    ai = {prop: 0, vict: 0}
    for i in range(soul_idx):
        if not isinstance(dialogue[i], dict):
            continue
        sp = str(dialogue[i].get("speaker") or "").strip()
        line = str(dialogue[i].get("line") or "").strip()
        if sp not in {prop, vict} or not line:
            continue
        if not RE_SPEECHLESS.search(line):
            continue
        # 纯短口语结巴也算提前败北，一律改争锋
        pool = prop_alts if sp == prop else vict_alts
        cand = pool[ai[sp] % len(pool)]
        ai[sp] += 1
        dialogue[i]["line"] = cand
        notes.append("I拷问前伪语塞改争锋")
    if notes:
        story["dialogue"] = dialogue
    return notes


def patch_i_ban_meta_speechless(story: dict) -> list[str]:
    """禁「我一时说不出话」类自述语塞；仅拷问后改口语结巴。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    soul_idx = _find_parent_soul_idx(dialogue)
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        meta = (
            "说不出话" in line
            or "一时语塞" in line
            or ("一时" in line and "接不上" in line)
            or (
                RE_SPEECHLESS.search(line)
                and _RE_SPEECHLESS_STILL_ARGUES.search(line)
            )
        )
        if not meta:
            continue
        if soul_idx >= 0 and i > soul_idx:
            item["line"] = _ORAL_SPEECHLESS_LINE
            notes.append("I自述语塞改口语")
        else:
            # 拷问前元话语留给 strip_premature；此处再兜底
            sp = str(item.get("speaker") or "").strip()
            item["line"] = (
                "事实摆那儿，我宣传怎么了！"
                if sp in {"昭昭", "灿灿"}
                else line
            )
            if item["line"] != line:
                notes.append("I拷问前元话语改争锋")
    return notes


def patch_i_ensure_parent_soul_from_beat(story: dict) -> list[str]:
    """beat/seed 写明家长灵魂拷问时，正文缺失则插入可说出口的拷问句。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    chain = story.get("gold_beat_chain")
    if not isinstance(chain, list):
        chain = []
    want_sp = ""
    intent = ""
    for row in chain:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        it = str(row.get("intent") or "").strip()
        if sp not in ("妈妈", "爸爸"):
            continue
        if not (
            _RE_SOUL_WINNER.search(it)
            or "冰箱" in it
            or "还得会" in it
            or "评论" in it
        ):
            continue
        want_sp, intent = sp, it
        break
    if not want_sp:
        return notes
    # 生成口语拷问：须打穿「跟我无关」，勿写成帮「谁都能评」
    spoken = intent
    spoken = re.sub(r"^(责备|反问|点破|问)[:：]?", "", spoken).strip()
    if "冰箱" in intent or "制冷" in intent or "评论" in intent:
        # 抽象换位：堵「分数问题不怪我 / 跟我无关」
        spoken = _I_SOUL_SWAP_LINE
    elif len(spoken) > 22 or not spoken.endswith(("？", "?", "吗", "嘛")):
        spoken = (
            f"那我问你，{spoken[:14]}？"
            if spoken
            else _I_SOUL_SWAP_LINE
        )
    # 已有家长强拷问：冰箱歧义句改写成打穿方向；换位句则过
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != want_sp:
            continue
        line = str(item.get("line") or "")
        if "冰箱" in line or "制冷" in line:
            item["line"] = spoken
            notes.append("I拷问改打穿方向")
            setting = str(story.get("setting") or "").rstrip("，。；; ")
            if "换位" not in setting:
                story["setting"] = (
                    f"{setting}，妈妈拿换位反问问昭昭"
                    if setting
                    else "客厅，妈妈拿换位反问问昭昭"
                )
            return notes
        if _RE_SOUL_WINNER.search(line) or "乐意吗" in line or "换你" in line:
            return notes
    # 插在首次语塞前；若无语塞则插在倒数第2句前
    insert_at = len(dialogue) - 2
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if RE_SPEECHLESS.search(str(item.get("line") or "")):
            insert_at = i
            break
    insert_at = max(2, min(insert_at, len(dialogue)))
    dialogue.insert(insert_at, {"speaker": want_sp, "line": spoken})
    story["dialogue"] = dialogue
    setting = str(story.get("setting") or "")
    if "换你" in spoken and "换位" not in setting:
        story["setting"] = (
            f"{setting.rstrip('，。；; ')}，妈妈拿换位反问问昭昭"
            if setting
            else "客厅，妈妈拿换位反问问昭昭"
        )
    notes.append("I补家长灵魂拷问")
    return notes


def patch_i_collapse_same_filler(story: dict) -> list[str]:
    """同一 speaker 重复空转短句（别说了/我可不干了）只留首句。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    seen: dict[str, str] = {}
    empty_re = re.compile(
        r"^(别说了|你再这样说.?我可不干了|你别再嚷)[！!。]?$"
    )
    alts_prop = [
        "高分就该谢我，低分就怪分数，这怎么是歪理？",
        "事实摆那儿，我宣传怎么了！",
    ]
    alts_vict = [
        "你拿我分数当笑话讲，也太过分了吧！",
        "你快放下卷子，别再满屋子嚷嚷了！",
        "你再宣传一次，我跟妈妈告状去！",
    ]
    ai = 0
    shout_count = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        compact = re.sub(r"[！!。.?？…\s]", "", line)
        if sp not in {"昭昭", "灿灿"}:
            continue
        if "我就说定了" in line:
            item["line"] = re.sub(r"[，,]?我就说定了", "", line).rstrip("！!") + "！"
            notes.append("I剥扩句尾巴")
            line = str(item.get("line") or "").strip()
            compact = re.sub(r"[！!。.?？…\s]", "", line)
        if "你别再嚷" in line:
            shout_count += 1
            if shout_count >= 2:
                # 第二次起改掉「别再嚷」尾巴，减空转
                cleaned = re.sub(r"[，,]?你别再嚷了?", "", line).strip("，,！! ")
                if cleaned and cleaned != line.rstrip("！!"):
                    item["line"] = cleaned + "！"
                    notes.append("I去重别再嚷")
                    line = item["line"]
                    compact = re.sub(r"[！!。.?？…\s]", "", line)
        prev = seen.get(sp)
        if prev and (prev == compact or empty_re.match(line)):
            alts = alts_prop if sp == "昭昭" else alts_vict
            # 尽量用 conflict 角色：宣传方用 prop 备选
            try:
                from app.services.gold_story.gold_chat.validate import (
                    _parse_conflict_propaganda_roles,
                )

                roles = _parse_conflict_propaganda_roles(
                    str(story.get("conflict_core") or "")
                )
                if roles:
                    prop, vict = roles
                    alts = alts_prop if sp == prop else alts_vict
            except Exception:
                pass
            item["line"] = alts[ai % len(alts)]
            ai += 1
            notes.append("I空转短句改写")
            seen[sp] = re.sub(r"[！!。.?？…\s]", "", item["line"])
        else:
            seen[sp] = compact
    return notes


def patch_i_fix_score_blackmail(story: dict) -> list[str]:
    """已立受害方考分后，禁止受害方用「你考…分」反咬揭短。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    victim_score: int | None = None
    victim = ""
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "")
        m = re.search(
            r"(灿灿|昭昭|姐姐|她).{0,6}考了?(?P<n>\d{1,3})分",
            line,
        )
        if m and sp in ("昭昭", "灿灿") and not line.startswith("你"):
            victim_score = int(m.group("n"))
            name = m.group(1)
            victim = {
                "灿灿": "灿灿",
                "昭昭": "昭昭",
                "姐姐": "灿灿",
                "她": "灿灿" if sp == "昭昭" else "昭昭",
            }.get(name, "")
            if victim:
                break
    if not victim:
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "")
        if sp != victim:
            continue
        if not _RE_YOU_SCORE.search(line):
            continue
        # 任意「你考N分」反咬都改掉（不限同款 N）
        item["line"] = "你再到处说，我可不答应！"
        notes.append("I禁分数互相揭短")
    return notes


def patch_i_strip_relay_and_invented_prop(story: dict) -> list[str]:
    """禁转述在场对方；禁 setting 未出现的空降道具。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    setting = _setting_blob(story)
    out: list[dict] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if _RE_RELAY_PRESENT.search(line):
            notes.append("I删在场转述句")
            continue
        if _RE_INVENTED_PROP.search(line):
            prop = _RE_INVENTED_PROP.search(line)
            token = prop.group(0) if prop else ""
            if token and token not in setting and "桶" not in setting:
                notes.append("I删空降道具句")
                continue
        if _RE_ADULT_DEBATE.search(line):
            sp = str(item.get("speaker") or "").strip()
            if sp in ("昭昭", "灿灿"):
                notes.append("I删成人辩经抢答")
                continue
        out.append(item)
    if len(out) != len(dialogue):
        story["dialogue"] = out
    return notes


def patch_i_second_person_present(story: dict) -> list[str]:
    """在场姐弟互指：宣传/分数句里的「她/他」改成「你」。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            continue
        line = str(item.get("line") or "")
        if not re.search(
            r"(她|他)(?:要)?考|宣传.{0,6}(她|他)|(她|他)还得谢|"
            r"全班就(她|他)|(她|他)最低|(她|他)得谢|(她|他)还得感谢",
            line,
        ):
            continue
        new = (
            line.replace("她要考", "你要考")
            .replace("他要考", "你要考")
            .replace("她考", "你考")
            .replace("他考", "你考")
            .replace("她还得谢", "你还得谢")
            .replace("他还得谢", "你还得谢")
            .replace("她得谢", "你得谢")
            .replace("他得谢", "你得谢")
            .replace("她还得感谢", "你还得感谢")
            .replace("他还得感谢", "你还得感谢")
            .replace("宣传她", "宣传你")
            .replace("宣传他", "宣传你")
            .replace("全班就她", "全班就你")
            .replace("全班就他", "全班就你")
            .replace("她最低", "你最低")
            .replace("他最低", "你最低")
        )
        if new != line:
            item["line"] = new
            notes.append("I在场改第二人称")
    return notes


def patch_i_rewrite_ambiguous_fridge_soul(story: dict) -> list[str]:
    """宣传类冲突里，家长「评论冰箱/制冷」易读成帮腔，统一改换位反问。

    抽象条件：I 类 + conflict 含宣传/分数口舌；不绑单篇分数或人名。
    """
    notes: list[str] = []
    conflict = str(story.get("conflict_core") or "")
    if not re.search(r"宣传|宣扬|分数|低分|高分", conflict):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    swap = _I_SOUL_SWAP_LINE
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in ("妈妈", "爸爸"):
            continue
        line = str(item.get("line") or "")
        if "冰箱" not in line and "制冷" not in line:
            continue
        if line.strip() == swap:
            continue
        item["line"] = swap
        notes.append("I冰箱类比改换位")
    if notes:
        setting = str(story.get("setting") or "")
        if "换位" not in setting:
            story["setting"] = (
                f"{setting.rstrip('，。；; ')}，妈妈拿换位反问问宣传方"
                if setting
                else "客厅，妈妈拿换位反问问宣传方"
            )
    # 宣传稿：凡家长换位拷问，元数据勿再写冰箱梗
    punch = str(story.get("punchline_explain") or "")
    if "冰箱" in punch and re.search(r"宣传|宣扬|分数", conflict):
        story["punchline_explain"] = re.sub(
            r"评论冰箱[^，。；;]*|用['「]?评论冰箱[^'」]*['」]?",
            "用换位反问打穿「跟我无关」",
            punch,
        )
        if "冰箱" in str(story.get("punchline_explain") or ""):
            story["punchline_explain"] = (
                "I类：家长换位反问打穿宣传方「跟我无关」借口，"
                "对方语塞，赢家口语制敌收束。"
            )
        notes.append("I元数据去冰箱梗")
    return notes


def patch_i_fix_parent_sibling_voice(story: dict) -> list[str]:
    """宣传稿角色硬锁：姐弟宣传/受害腔 + 家长误说姐弟腔归位。"""
    notes: list[str] = []
    conflict = str(story.get("conflict_core") or "")
    if not re.search(r"宣传|宣扬|分数|低分|高分", conflict):
        return notes
    prop, vict = "昭昭", "灿灿"
    try:
        from app.services.gold_story.gold_chat.validate import (
            _parse_conflict_propaganda_roles,
        )

        roles = _parse_conflict_propaganda_roles(conflict)
        if roles:
            prop, vict = roles
    except Exception:
        pass
    claim = re.compile(
        r"我宣传|我宣扬|宣传高分|低分怪|高分.{0,8}谢|全楼都该听|"
        r"跟我有啥关系|我举着卷子|全班都该|全班都听见|这规矩|没瞎编|明明白白|"
        r"宣传出去|事实又不是我|我.{0,4}楼下.{0,6}喊|又喊了一遍|"
        r"我.{0,4}门口喊|去门口喊|门口喊给"
    )
    parent_claim = re.compile(
        r"我宣传|我宣扬|我.{0,6}喊|我举着|跟我有啥关系|我又没瞎编"
    )
    victim = re.compile(
        r"同学都笑我|你到处说|拿我.{0,8}分|当笑话|也太过分|笑我丢脸|"
        r"放下卷子|满屋子嚷嚷|告状去|别到处说|"
        r"你.{0,4}门口喊|我同学全知道|同学会笑我"
    )
    keep_parent = re.compile(
        r"换你|乐意吗|还得会|照你|评论.{0,8}吗|嘴硬|别跟我吵|"
        r"不乐意|别乱说|把卷子给我|轮不到你"
    )
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "")
        if not line:
            continue
        if sp in ("妈妈", "爸爸"):
            if keep_parent.search(line):
                continue
            if parent_claim.search(line):
                item["speaker"] = prop
                notes.append("I家长误说宣传腔归位")
            elif victim.search(line):
                item["speaker"] = vict
                notes.append("I家长误说受害腔归位")
            continue
        if sp not in {"昭昭", "灿灿"}:
            continue
        # 对妈喊却说姐弟宣传腔：改回对受害方争锋（抽象错位，不绑单篇）
        if (
            sp == prop
            and re.match(r"^妈[妈]?[！!，,]", line)
            and claim.search(line)
        ):
            item["line"] = "事实摆那儿，我宣传怎么了！"
            notes.append("I对妈错位宣传改争锋")
            continue
        if claim.search(line) and sp != prop:
            item["speaker"] = prop
            notes.append("I宣传腔speaker归位")
        elif victim.search(line) and sp != vict:
            item["speaker"] = vict
            notes.append("I受害腔speaker归位")
    return notes


def _i_line_core(line: str) -> str:
    s = re.sub(r"[！!。.?？…\s]", "", str(line or "").strip())
    return re.sub(
        r"你给我说清楚|我就这理|我就说定了|了吧|吧|呢|呀|嘛|啦",
        "",
        s,
    )


def patch_i_dedupe_sibling_lines(story: dict) -> list[str]:
    """姐弟近重复台词：后出现的改写，防凑字空转。

    语塞短句（我……）禁止被近重复改写成嘴硬争锋，否则会打穿
    「拷问→语塞→制敌」骨架。
    """
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    prop, vict = _propaganda_roles(story)
    alts = {
        prop: [
            "事实摆那儿，我宣传怎么了！",
            "卷子上写得明明白白，我又没瞎编！",
            "我宣传怎么了，又不是我改的分！",
        ],
        vict: [
            "你快放下卷子，别再满屋子嚷嚷了！",
            "你再宣传一次，我跟妈妈告状去！",
            "同学都拿这个笑我，你太过分了！",
        ],
    }
    seen: set[str] = set()
    ai = {prop: 0, vict: 0}
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in {prop, vict} or not line:
            continue
        # 真正语塞：跳过去重，勿改回争锋
        if RE_SPEECHLESS.search(line) and not _RE_SPEECHLESS_STILL_ARGUES.search(
            line
        ):
            continue
        key = _i_line_core(line)
        if not key:
            continue
        # 近重复：完全相同，或双方核心均够长时的互相包含
        # （短核「我我」不可 substring 命中长句，否则会误伤语塞）
        dup = key in seen or (
            len(key) >= 6
            and any(
                key in old or old in key for old in seen if len(old) >= 6
            )
        )
        if dup:
            pool = alts.get(sp) or []
            replaced = False
            for _ in range(len(pool) + 2):
                cand = pool[ai[sp] % max(len(pool), 1)] if pool else ""
                ai[sp] += 1
                if not cand:
                    break
                ck = _i_line_core(cand)
                if ck and ck not in seen and not any(
                    ck in old or old in ck for old in seen if len(old) >= 6
                ):
                    item["line"] = cand
                    seen.add(ck)
                    notes.append("I去重重复台词")
                    replaced = True
                    break
            if not replaced:
                # 无可用备选：改成短异句，避免删到篇幅不够
                item["line"] = (
                    "你再这样说，我不依了！"
                    if sp == vict
                    else "我就是要说，管你怎么想！"
                )
                seen.add(_i_line_core(item["line"]))
                notes.append("I去重重复台词")
        else:
            seen.add(key)
    return notes


def patch_i_strip_mid_pad(story: dict) -> list[str]:
    """剥中段凑字脏尾：好不好/呢、啦了呀、可记住啦等。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line:
            continue
        new = re.sub(r"好不好(?:呀|呢|啊)?([！!。？?]?)$", r"\1", line)
        new = re.sub(r"(歪理)好不好", r"\1", new)
        new = re.sub(r"([了吧])呢([！!。？?]?)$", r"\1\2", new)
        new = re.sub(r"[，,]?我就这理好不好.*$", "，我就这理！", new)
        new = re.sub(
            r"(?:不行)?真的(?:呀|呢|了)?([！!。？?]?)$",
            r"\1",
            new,
        )
        new = re.sub(r"真的([！!。？?]?)$", r"\1", new)
        new = re.sub(r"[，,]?我偏就不信[！!。？?]?$", "！", new)
        # 抽象凑字堆叠：啦了呀 / 可记住啦 / 乱动尾巴（分数口舌无关）
        new = re.sub(r"啦了呀", "啦", new)
        new = re.sub(r"听见啦了", "听见啦", new)
        new = re.sub(r"[，,]?我可记住啦?[了]?[！!。？?]?", "", new)
        new = re.sub(r"[，,]?别再乱动了", "", new)
        new = re.sub(r"我才不怕了([！!。？?]?)", r"我才不怕\1", new)
        new = re.sub(r"歪理了([？?])", r"歪理\1", new)
        new = re.sub(r"告状去?呢([！!。？?]?)", r"告状\1", new)
        new = re.sub(r"妈妈说呢([！!。？?]?)", r"妈妈说\1", new)
        new = re.sub(r"[，,]{2,}", "，", new).strip("，, ")
        if new and new[-1] not in "！!。？?":
            new = new.rstrip("，, ") + "！"
        if new != line:
            item["line"] = new if new.strip() else line
            notes.append("I剥中段垫字")
    return notes


def patch_i_enforce_line_max(story: dict) -> list[str]:
    """I 补丁后强制单句 ≤ 上限，避免 expand/注入顶破硬卡。"""
    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
        truncate_overlong_line,
    )

    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        if dialogue_char_count(line) <= DAILY_STORY_LINE_CHARS_MAX:
            continue
        item["line"] = truncate_overlong_line(
            line, max_chars=DAILY_STORY_LINE_CHARS_MAX
        )
        notes.append("I截断超长句")
    return notes


def patch_i_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "I":
        return notes
    lines = [
        str(item.get("line") or "")
        for item in (story.get("dialogue") or [])
        if isinstance(item, dict)
    ]
    closure_complete = any(
        RE_WIN_STUBBORN.search(lines[i])
        and RE_SPEECHLESS.search(lines[i + 1])
        for i in range(len(lines) - 1)
    )
    if closure_complete:
        notes.extend(patch_i_trim_trailing_subplot(story))
        notes.extend(patch_i_strip_meta_type_labels(story))
        notes.extend(patch_i_indoor_dialogue(story))
        notes.extend(patch_i_clean_win_line_suffix(story))
        notes.extend(patch_i_enforce_line_max(story))
        return notes
    notes.extend(patch_i_align_soul_speaker(story))
    notes.extend(patch_i_ensure_parent_soul_from_beat(story))
    notes.extend(patch_i_rewrite_ambiguous_fridge_soul(story))
    notes.extend(patch_i_fix_parent_sibling_voice(story))
    notes.extend(patch_i_fix_score_blackmail(story))
    notes.extend(patch_i_second_person_present(story))
    notes.extend(patch_i_strip_relay_and_invented_prop(story))
    notes.extend(patch_i_collapse_same_filler(story))
    notes.extend(patch_i_strip_premature_speechless(story))
    notes.extend(patch_i_ban_meta_speechless(story))
    notes.extend(patch_i_strip_premature_speechless(story))
    notes.extend(patch_i_seal_after_parent_soul(story))
    notes.extend(patch_i_expand_before_soul(story))
    notes.extend(patch_i_seal_after_parent_soul(story))
    notes.extend(patch_i_fix_parent_sibling_voice(story))
    notes.extend(patch_i_dedupe_sibling_lines(story))
    # dedupe 可能误伤语塞：再封一次
    notes.extend(patch_i_seal_after_parent_soul(story))
    notes.extend(patch_i_strip_mid_pad(story))
    notes.extend(patch_i_enforce_line_max(story))
    notes.extend(patch_i_trim_trailing_subplot(story))
    notes.extend(patch_i_strip_meta_type_labels(story))
    notes.extend(patch_i_indoor_dialogue(story))
    notes.extend(patch_i_clean_win_line_suffix(story))
    notes.extend(patch_i_enforce_line_max(story))
    return notes



def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def _ensure_oral_win_at_end(story: dict, winner: str) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return notes
    sp = winner or "昭昭"
    for item in dialogue[-4:]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not RE_WIN_STUBBORN.search(line):
            continue
        cur = str(item.get("speaker") or "").strip()
        if cur == sp:
            return notes
        # 非赢家误用制敌句式：改成嘴硬辩解，末句再补赢家制敌
        item["line"] = "我偏就不认，怎么了。"
        notes.append("I非赢家制敌句改写")
    last = dialogue[-1] if isinstance(dialogue[-1], dict) else None
    if last and str(last.get("speaker") or "").strip() == sp:
        last["line"] = _ORAL_WIN_LINE
        notes.append("I末句补口语制敌")
    else:
        dialogue.append({"speaker": sp, "line": _ORAL_WIN_LINE})
        notes.append("I补末句口语制敌")
    story["dialogue"] = dialogue
    return notes


def patch_i_trim_trailing_subplot(story: dict) -> list[str]:
    """语塞后首次服软/制敌即收束；其后第二轮一律裁掉。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes

    lines = _dialogue_lines(story)
    close_idx = find_i_close_index(lines)

    def _soul_winner() -> str:
        # 先家长后姐弟；须命中强拷问（勿把「凭啥怪我」当灵魂拷问赢家）
        for prefer in (("妈妈", "爸爸"), ("灿灿", "昭昭")):
            for i, ln in enumerate(lines):
                if not _RE_SOUL_WINNER.search(ln):
                    continue
                if not isinstance(dialogue[i], dict):
                    continue
                sp = str(dialogue[i].get("speaker") or "").strip()
                if sp in prefer:
                    return sp
        return ""

    if close_idx < 0:
        winner0 = _soul_winner()
        if winner0:
            notes.extend(_ensure_oral_win_at_end(story, winner0))
        return notes

    trailing = len(lines) - close_idx - 1
    winner = ""
    for i, ln in enumerate(lines):
        if RE_WIN_STUBBORN.search(ln) and isinstance(dialogue[i], dict):
            winner = str(dialogue[i].get("speaker") or "").strip()
    if not winner:
        for i in range(close_idx, -1, -1):
            if not isinstance(dialogue[i], dict):
                continue
            sp = str(dialogue[i].get("speaker") or "").strip()
            ln = str(dialogue[i].get("line") or "")
            if sp in ("昭昭", "灿灿") and not RE_I_SURRENDER.search(ln):
                winner = sp
                break
    # 灵魂拷问方才是赢家（含妈妈/爸爸戏核拷问），勿默认安在昭昭身上
    soul = _soul_winner()
    if soul and (not winner or winner in ("昭昭", "灿灿")):
        winner = soul

    # 末段已有**赢家**口语制敌且无拖尾，才可提前返回
    if trailing <= _I_CLOSING_TAIL_ALLOW and winner:
        for item in dialogue[-4:]:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != winner:
                continue
            if RE_WIN_STUBBORN.search(str(item.get("line") or "")):
                return notes

    min_keep = close_idx + 1 + _I_CLOSING_TAIL_ALLOW
    if len(dialogue) > min_keep:
        removed = len(dialogue) - min_keep
        story["dialogue"] = [x for x in dialogue[:min_keep] if isinstance(x, dict)]
        notes.append(f"I首次收束后裁拖尾 {removed}句")

    notes.extend(_ensure_oral_win_at_end(story, winner))
    return notes


def patch_i_strip_meta_type_labels(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "一招制敌" not in line and "问倒你" not in line:
            continue
        new = (
            line.replace("一招制敌，", "")
            .replace("一招制敌", "")
            .replace("问倒你", "看你还嘴硬")
        )
        new = re.sub(r"[，,]{2,}", "，", new).strip("，、 ")
        if not new or not RE_WIN_STUBBORN.search(new):
            new = _ORAL_WIN_LINE
        if new != line:
            item["line"] = new
            notes.append("I去类型标签自指")
    return notes


def patch_i_indoor_dialogue(story: dict) -> list[str]:
    notes: list[str] = []
    setting = str(story.get("setting") or "")
    if not _RE_INDOOR_SETTING.search(setting):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "看窗外" not in line:
            continue
        item["line"] = (
            line.replace("看窗外还不行", "别说了还不行")
            .replace("看窗外", "别说了")
        )
        notes.append("I室内场景：看窗外→别说了")
    return notes


def patch_i_clean_win_line_suffix(story: dict) -> list[str]:
    """制敌句收束锚干净：句尾垫字尾巴（好不好/你听着/语气词）剥离。

    尾巴定义复用 daily_story 垫字集合（_LOCAL_PAD_TAILS / _LOCAL_TRIM_CHARS），
    收束锚不承载垫字尾巴。
    """
    from app.services.daily_story.prompts import (
        _LOCAL_PAD_TAILS,
        _LOCAL_TRIM_CHARS,
    )

    parts = [re.escape(t) for t in _LOCAL_PAD_TAILS] + [
        re.escape(c) for c in _LOCAL_TRIM_CHARS
    ]
    re_win_pad_tail = re.compile(
        r"[，,、]*(?:" + "|".join(parts) + r")+(?=[！!。？?]?$)"
    )
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not RE_WIN_STUBBORN.search(line):
            continue
        new = re_win_pad_tail.sub("", line)
        if new != line:
            item["line"] = new
            notes.append("I制敌句去句尾语气词")
    return notes


def patch_i_align_soul_speaker(
    story: dict,
    *,
    beat_chain: list | None = None,
) -> list[str]:
    """beat 写明的拷问方（常为妈妈）须说灵魂拷问句；误安到姐弟则归位。"""
    notes: list[str] = []
    chain = beat_chain if isinstance(beat_chain, list) else (
        story.get("gold_beat_chain")
        if isinstance(story.get("gold_beat_chain"), list)
        else []
    )
    want = ""
    for row in chain:
        if not isinstance(row, dict):
            continue
        intent = str(row.get("intent") or "")
        if not (
            _RE_SOUL_WINNER.search(intent)
            or "冰箱" in intent
            or "还得会" in intent
        ):
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp:
            want = sp
            break
    if not want:
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    def _is_soul_line(line: str) -> bool:
        return bool(
            _RE_SOUL_WINNER.search(line)
            or "换你" in line
            or "乐意吗" in line
            or "冰箱" in line
            or "还得会" in line
        )

    if any(
        isinstance(d, dict)
        and str(d.get("speaker") or "").strip() == want
        and _is_soul_line(str(d.get("line") or ""))
        for d in dialogue
    ):
        return notes
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not _is_soul_line(line):
            continue
        if str(item.get("speaker") or "").strip() != want:
            item["speaker"] = want
            notes.append("I灵魂拷问speaker归位")
            return notes
    return notes
