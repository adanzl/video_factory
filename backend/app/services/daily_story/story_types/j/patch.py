"""J 类正文本地修稿：否决复读/末句镇住，以及金稿扩写后的结构补丁。

只做类型级结构修补，禁止按 theme 造句。
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.j.validate import RE_HOLD

_RE_J_HOLD = re.compile(r"我说了算")
_RE_J_STUBBORN = re.compile(r"我说不行|不行就不行")

# 与 quality._LIMP_SOFT_CLOSE_MARKERS 对齐：末句命中且无破功痕迹 → 结构 -20
_J_LIMP_LAST: tuple[str, ...] = (
    "哼",
    "算了",
    "好吧",
    "好了好了",
    "行吧",
    "随你",
    "我不管",
    "不管了",
    "随便你",
    "那行",
    "行行行",
    "吃吧",
    "你赢",
    "给你",
)

_J_HOLD_FALLBACK = "听我的，我说了算！"

# 中段否决句尾轮换池（抽象权威压住，不含主题物件）
_J_MID_VETO_TAILS: tuple[str, ...] = (
    "想都别想呀。",
    "哭也没用呀。",
    "反正我不准就不准。",
    "现在收买没用。",
)

# 句内权威尾巴 → 保留前半理由时的替换尾
_J_TAIL_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"，?出门我说了算[吧呀啊！。…]*$"), "，今天不准出门。"),
    (re.compile(r"，?这个家我说了算[吧呀啊！。…]*$"), "，反正我不准就不准。"),
    (re.compile(r"，?我说不行就不行[啊！。…]*$"), "，想都别想呀。"),
    (re.compile(r"，?我说不行[啊！。…]*$"), "，想都别想呀。"),
    (re.compile(r"，?我说了算[吧呀啊！。…]*$"), "，想都别想呀。"),
)


def _is_j(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "J"


def _cancan_indices(dialogue: list[dict]) -> list[int]:
    out: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() == "灿灿":
            out.append(i)
    return out


def _rewrite_j_veto_tail(line: str, alt: str) -> str | None:
    text = str(line or "").strip()
    if not text:
        return None
    for pat, repl in _J_TAIL_REWRITES:
        if pat.search(text):
            new_line = pat.sub(repl, text, count=1)
            if new_line != text:
                return new_line
    if _RE_J_HOLD.search(text):
        prefix = _RE_J_HOLD.split(text, maxsplit=1)[0].rstrip("，, ")
        if len(prefix) >= 4:
            return f"{prefix}，{alt.lstrip('，')}"
    if _RE_J_STUBBORN.search(text):
        prefix = _RE_J_STUBBORN.split(text, maxsplit=1)[0].rstrip("，, ")
        if len(prefix) >= 4:
            return f"{prefix}，{alt.lstrip('，')}"
    return None


def _ensure_hold_line(line: str) -> str:
    text = str(line or "").strip()
    if RE_HOLD.search(text):
        return text[:DAILY_STORY_LINE_CHARS_MAX]
    core = text.rstrip("！。？…!")
    if not core:
        return _J_HOLD_FALLBACK
    merged = f"{core}，我说了算！"
    return merged[:DAILY_STORY_LINE_CHARS_MAX]


def _patch_j_closing_hold(dialogue: list) -> list[str]:
    """末句昭昭软收（哼/算了…）时，把灿灿镇住落到末句，避免无破功软收 -20。"""
    rows = [x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()]
    if len(rows) < 2:
        return []
    last = rows[-1]
    prev = rows[-2]
    last_sp = str(last.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    prev_ln = str(prev.get("line") or "").strip()
    limp = any(m in last_ln for m in _J_LIMP_LAST)

    if last_sp == "灿灿" and RE_HOLD.search(last_ln):
        return []
    if not limp and last_sp == "灿灿":
        last["line"] = _ensure_hold_line(last_ln)
        return ["J末句补镇住"]

    notes: list[str] = []
    if last_sp == "昭昭" and limp and prev_sp == "灿灿":
        hold_line = _ensure_hold_line(prev_ln)
        last["speaker"] = "灿灿"
        last["line"] = hold_line
        prev["speaker"] = "昭昭"
        prev["line"] = last_ln
        notes.append("J末句镇住：软收与压住对调")
        # 对调后若出现昭昭连说（…昭昭认输 + 昭昭软收），并掉前一句认输
        if len(rows) >= 3:
            ante = rows[-3]
            if str(ante.get("speaker") or "").strip() == "昭昭":
                try:
                    dialogue.remove(ante)
                    notes.append("J末句镇住：并掉连说认输")
                except ValueError:
                    pass
        return notes

    if last_sp == "昭昭" and limp:
        last["speaker"] = "灿灿"
        last["line"] = _J_HOLD_FALLBACK
        notes.append("J末句镇住：软收改灿灿压住")
        return notes

    if last_sp != "灿灿" and not RE_HOLD.search(
        "".join(str(r.get("line") or "") for r in rows[-4:])
    ):
        last["speaker"] = "灿灿"
        last["line"] = _J_HOLD_FALLBACK
        notes.append("J末句镇住：补压住收场")
    return notes


def patch_j_body(story: dict) -> list[str]:
    """灿灿中段「我说了算/我说不行」同构复读 → 句尾轮换，末句保留镇住词。"""
    if not _is_j(story):
        return []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return []

    cancan = _cancan_indices(dialogue)
    notes: list[str] = []
    if len(cancan) >= 2:
        hold_seen = 0
        stubborn_seen = 0
        tail_idx = 0
        last_cancan = cancan[-1]

        for idx in cancan:
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            if not line:
                continue

            has_hold = bool(_RE_J_HOLD.search(line))
            has_stubborn = bool(_RE_J_STUBBORN.search(line))
            is_closing = idx == last_cancan

            need_rewrite = False
            if has_hold:
                hold_seen += 1
                if hold_seen > 1 and not is_closing:
                    need_rewrite = True
            if has_stubborn:
                stubborn_seen += 1
                if stubborn_seen > 1 and not is_closing:
                    need_rewrite = True

            if not need_rewrite:
                continue

            alt = _J_MID_VETO_TAILS[tail_idx % len(_J_MID_VETO_TAILS)]
            tail_idx += 1
            new_line = _rewrite_j_veto_tail(line, alt)
            if not new_line or new_line == line:
                continue
            item["line"] = new_line
            notes.append(f"J去否决复读[{idx + 1}]")

    notes.extend(_patch_j_closing_hold(dialogue))
    return notes


# ── gold_chat 扩写后结构补丁（经 story_types 公开桥调用）──


def _j_lose_line_index(dialogue: list[Any]) -> int:
    for i, x in enumerate(dialogue):
        if not isinstance(x, dict):
            continue
        if (
            str(x.get("speaker") or "").strip() == "昭昭"
            and re.search(r"我输了|认输", str(x.get("line") or ""))
        ):
            return i
    return -1


_J_ZHAO_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {
        "少跟我吵",
        "轮不到你",
        "不许再耍赖",
        "马上给我挪开",
        "给我站住",
        "我先说定",
        "说一不二",
    }
)
_J_CAN_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {"你试试看", "少跟我吵", "我才不怕", "你凭什么"}
)



def patch_j_cap_ya_particles(
    story: dict[str, Any],
    *,
    max_lines: int = 2,
) -> tuple[dict[str, Any], bool]:
    """J：全篇句尾「呀」最多保留 max_lines 处，其余剥掉防满篇垫字。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    ya_indices: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if re.search(r"呀[！。？…!]?$", line) or re.search(
            r"[来好啦了]呀[！。？…!]?$", line
        ):
            ya_indices.append(i)
    if len(ya_indices) <= max_lines:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for i in ya_indices[max_lines:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = re.sub(r"来呀来呀", "来", body)
        new_body = re.sub(r"([来啦了])呀$", r"\1", new_body)
        new_body = re.sub(r"呀$", "", new_body)
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_cap_trailing_particles(
    story: dict[str, Any],
    *,
    particles: tuple[str, ...] = ("啊", "呀"),
    max_lines: int = 3,
) -> tuple[dict[str, Any], bool]:
    """J：全篇句尾语气词（啊/呀）最多保留 max_lines 处。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    pat = re.compile(
        rf"(?:{'|'.join(re.escape(p) for p in particles)})[！。？…!]?$"
    )
    hit_indices: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if pat.search(line):
            hit_indices.append(i)
    if len(hit_indices) <= max_lines:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for i in hit_indices[max_lines:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = body
        for p in particles:
            new_body = re.sub(rf"{re.escape(p)}$", "", new_body)
        new_body = re.sub(r"([了啦呢])啊$", r"\1", new_body)
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_dedupe_cross_line_phrases(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：全篇扩写短语（你凭什么等）只保留首现，防叠灌重复。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    seen: set[str] = set()
    changed = False
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = body
        for phr in _J_CROSS_LINE_REPEAT_PHRASES:
            if phr not in new_body:
                continue
            if phr in seen:
                for variant in (f"，{phr}呀", f"，{phr}啊", f"，{phr}", phr):
                    new_body = new_body.replace(variant, "")
            else:
                seen.add(phr)
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if not new_body:
            continue
        new = new_body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_fix_strongest_form_wording(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：「最强形态」须昭昭自述挑衅，禁灿灿错位或「那你拿出」口吻。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "最强形态" not in line:
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp == "灿灿":
            item["speaker"] = "昭昭"
            item["line"] = "我拿出最强形态来，你可别怂！"
            changed = True
            continue
        if sp != "昭昭":
            continue
        if not re.search(r"那你|你拿|你出", line):
            continue
        item["line"] = "我拿出最强形态来，我可不会输！"
        changed = True
    return out, changed


def patch_j_fix_lose_speaker(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输句必须归昭昭（防连说改 speaker 后错位）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    lose_pat = re.compile(r"我输了|我认输了")
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        sp = str(item.get("speaker") or "").strip()
        if lose_pat.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
    return out, changed


def patch_j_dedupe_plea_rounds(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后最多保留 1 轮「再求/不行」；删第二轮机械求拒。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False

    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False

    plea_pat = re.compile(
        r"再求你|再给.{0,2}机会|换个理由.{0,4}求|那我保证|就这一次|姐姐，再给"
    )
    veto_pat = re.compile(
        r"不行|规矩|输了就是输了|别想反悔|休想耍赖|继续压住|赢了就是赢了"
    )
    plea_idx = [
        i
        for i, x in enumerate(dialogue)
        if i > lose_idx
        and isinstance(x, dict)
        and str(x.get("speaker") or "") == "昭昭"
        and plea_pat.search(str(x.get("line") or ""))
    ]
    if len(plea_idx) < 2:
        return story, False

    drop: set[int] = set()
    for second in plea_idx[1:]:
        drop.add(second)
        if second + 1 < len(dialogue):
            nxt = dialogue[second + 1]
            if (
                isinstance(nxt, dict)
                and str(nxt.get("speaker") or "") == "灿灿"
                and veto_pat.search(str(nxt.get("line") or ""))
            ):
                drop.add(second + 1)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


_J_CROSS_LINE_REPEAT_PHRASES: tuple[str, ...] = (
    "你凭什么",
    "你试试看",
    "少跟我吵",
    "我才不怕",
)
_J_YA_CAP_MAX_LINES = 2


def patch_j_plea_veto_speakers(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：本地加的求放行/否决句若被连说翻转，按句式归位（抽象模板，非单篇）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    plea = re.compile(r"再求你一次|那我保证|就这一次|再给一次机会")
    veto = re.compile(r"规矩就是这样|保证也没用|少讨价还价|这回听我安排")
    toy = re.compile(r"玩具.{0,6}归我|归我.{0,4}玩具")
    grow = re.compile(r"长大.{0,8}算")
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        sp = str(item.get("speaker") or "").strip()
        if plea.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
        elif veto.search(line) and sp != "灿灿":
            item["speaker"] = "灿灿"
            changed = True
        elif toy.search(line) and sp != "灿灿":
            item["speaker"] = "灿灿"
            changed = True
        elif grow.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
        # seed 扩句 intent 泄漏进对白：改成口语
        if re.match(r"^换个理由再求", line):
            item["line"] = "再求你一次，刚才那下不算！"
            item["speaker"] = "昭昭"
            changed = True
        elif re.match(r"^换个说法继续压", line):
            item["line"] = "不行，输了就是输了！"
            item["speaker"] = "灿灿"
            changed = True
        elif re.match(r"^再保证一次", line):
            item["line"] = "我保证，这次听你的！"
            item["speaker"] = "昭昭"
            changed = True
        elif re.match(r"^再否决一次", line):
            item["line"] = "不行，我说了算！"
            item["speaker"] = "灿灿"
            changed = True
    return out, changed


def patch_j_drop_post_lose_bridge(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：一锤分出胜负后删无意义桥句（别插嘴/轮到我），保收场节奏。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    bridges = (
        "等等，先听我说完",
        "你别插嘴，轮到我了",
        "你别插嘴，轮到我",
        "先别吵，听清楚",
    )
    drop: set[int] = set()
    for i in range(max(0, lose_idx - 2), lose_idx):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if any(br in line for br in bridges):
            drop.add(i)
    for i in range(lose_idx + 1, len(dialogue)):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if any(br in line for br in bridges):
            drop.add(i)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


def patch_j_drop_post_lose_plea(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后删求情-拒绝对，直进嘀咕+镇住（防审稿判拉锯）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    plea_pat = re.compile(
        r"再给.{0,2}机会|再.{0,2}给.{0,2}一次|再求你|换个理由.{0,4}求|"
        r"求一次|那我保证|姐姐，再|还没准备好|我保证不闹"
    )
    veto_pat = re.compile(
        r"不行|规矩|输了就是输了|别想反悔|休想耍赖|继续压住|赢了就是赢了|换个说法"
    )
    drop: set[int] = set()
    for i in range(lose_idx + 1, len(dialogue)):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        line = str(item.get("line") or "")
        if not plea_pat.search(line):
            continue
        drop.add(i)
        if i + 1 < len(dialogue):
            nxt = dialogue[i + 1]
            if (
                isinstance(nxt, dict)
                and str(nxt.get("speaker") or "") == "灿灿"
                and veto_pat.search(str(nxt.get("line") or ""))
            ):
                drop.add(i + 1)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


_RE_J_POST_LOSE_REMATCH = re.compile(
    r"不服|再来一回合|我还没用全力|看谁先认输|别磨蹭|"
    r"我还没发力|奉陪到底|你记住了|你真敢",
)
_RE_J_POST_LOSE_KEEP = re.compile(r"长大.{0,8}算|都归我|玩具都归")


def patch_j_drop_post_lose_rematch(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J/M8+J：认输后删本地互顶加码句，保收场节奏。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = _j_lose_line_index(dialogue)
    if lose_idx < 0:
        return story, False
    tail_guard = set(range(max(lose_idx + 1, len(dialogue) - 2), len(dialogue)))
    drop: set[int] = set()
    for i in range(lose_idx + 1, len(dialogue)):
        if i in tail_guard:
            continue
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if _RE_J_POST_LOSE_KEEP.search(line):
            continue
        if _RE_J_POST_LOSE_REMATCH.search(line):
            drop.add(i)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


def patch_j_strip_role_mismatch_expands(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：剥 speaker 禁忌扩写尾巴（如昭昭说「少跟我吵」）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        forbidden = (
            _J_ZHAO_FORBIDDEN_EXPAND
            if sp == "昭昭"
            else (_J_CAN_FORBIDDEN_EXPAND if sp == "灿灿" else frozenset())
        )
        for bare in sorted(forbidden, key=len, reverse=True):
            for suffix in ("", "啊", "呀", "吧"):
                token = bare + suffix
                body = body.replace(f"，{token}", "").replace(token, "")
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        if not body:
            continue
        new = body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_ensure_post_lose_alternate(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后若连说，插灿灿短否决，保交替与收场节奏。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 1 >= len(dialogue):
        return story, False
    nxt = dialogue[lose_idx + 1]
    if not isinstance(nxt, dict) or str(nxt.get("speaker") or "") != "昭昭":
        return story, False
    nxt_line = str(nxt.get("line") or "")
    if re.search(r"长大.{0,8}算", nxt_line):
        return story, False
    if re.search(
        r"再给|再求|换个理由.{0,4}求|求一次|那我保证|还没准备好",
        nxt_line,
    ):
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "你少废话，输了就是输了！",
        "别讨价还价，规矩定了！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 1, {"speaker": "灿灿", "line": text})
    return out, True


def patch_j_ensure_post_lose_can_press(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：删求拒后若认输直跳嘀咕，补灿灿短镇住句。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 1 >= len(dialogue):
        return story, False
    nxt = dialogue[lose_idx + 1]
    if not isinstance(nxt, dict):
        return story, False
    if str(nxt.get("speaker") or "") != "昭昭":
        return story, False
    if not re.search(r"长大.{0,8}算", str(nxt.get("line") or "")):
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "你少废话，输了就是输了！",
        "别讨价还价，这局我说了算！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 1, {"speaker": "灿灿", "line": text})
    return out, True


def patch_j_strip_post_lose_defiant(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后昭昭句剥「我才不怕/你试试看」等逆势尾巴，保怂态。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    changed = False
    defiant_bits = (
        "，我才不怕呢",
        "，我才不怕",
        "我才不怕呢",
        "我才不怕",
        "，你试试看啊",
        "，你试试看",
        "你试试看",
        "，谁怕谁",
        "谁怕谁",
    )
    for item in dialogue[lose_idx + 1 :]:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        old = str(item.get("line") or "").strip()
        if not old or re.search(r"长大.{0,8}算", old):
            continue
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = body
        for bit in defiant_bits:
            new_body = new_body.replace(bit, "")
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if not new_body:
            continue
        new = new_body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_fix_can_closing_after_grumble(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：昭昭嘀咕长大算账后，灿灿末句禁「行啊我等着」接招，改镇住命令。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return story, False
    grumble_idx = next(
        (
            i
            for i in range(len(dialogue) - 1, -1, -1)
            if isinstance(dialogue[i], dict)
            and str(dialogue[i].get("speaker") or "") == "昭昭"
            and re.search(r"长大.{0,8}算", str(dialogue[i].get("line") or ""))
        ),
        -1,
    )
    if grumble_idx < 0 or grumble_idx + 1 >= len(dialogue):
        return story, False
    last = dialogue[-1]
    if not isinstance(last, dict) or str(last.get("speaker") or "") != "灿灿":
        return story, False
    old = str(last.get("line") or "").strip()
    if not re.search(r"行啊|我等着|等着.*算|算.*账", old):
        return story, False
    stubs = (
        "别废话，趴好了！我说了算！",
        "闭嘴，现在就得听我的！",
        "少顶嘴，乖乖趴好别动！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    last["line"] = text
    return out, True


def patch_j_fix_post_lose_consecutive_can(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：删桥句后若灿灿连说，插昭昭短怂句保交替。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 2 >= len(dialogue):
        return story, False
    a = dialogue[lose_idx + 1]
    b = dialogue[lose_idx + 2]
    if not isinstance(a, dict) or not isinstance(b, dict):
        return story, False
    if str(a.get("speaker") or "") != "灿灿" or str(b.get("speaker") or "") != "灿灿":
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "姐，我知道了，别打了。",
        "好嘛，我听话还不行吗。",
        "哎呀，我服了，你说怎样就怎样。",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 2, {"speaker": "昭昭", "line": text})
    return out, True


def patch_j_soften_closing_grumble(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：末段昭昭嘀咕去掉「你等着瞧」等强势尾缀，保怂态。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        old = str(item.get("line") or "").strip()
        if not re.search(r"长大.{0,8}算", old):
            continue
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = re.sub(r"[，,]?你等着瞧[！。]?$", "", body)
        new_body = re.sub(r"[，,]?你等着呀[！。]?$", "", new_body)
        new_body = re.sub(r"^哼[，,]", "那个，", new_body)
        new_body = re.sub(r"([。！？…!])?[啊呀]+([。！？…!])$", r"\2", new_body)
        if not new_body.startswith("那个"):
            new_body = "那个，" + new_body.lstrip("那个，")
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed
