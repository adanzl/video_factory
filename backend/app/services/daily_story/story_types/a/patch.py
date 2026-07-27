"""A 类正文本地修稿。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
    truncate_overlong_line,
)
from app.services.daily_story.story_types import parse_story_type_code

RE_CLOSING_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)


def quote_grounded(frag: str, hay: str) -> bool:
    clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", frag)
    hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
    if len(clean) < 3:
        return True
    run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
    for i in range(len(clean) - run + 1):
        if clean[i : i + run] in hay2:
            return True
    return False


def pick_cite_chunk(cancan_line: str) -> str:
    text = re.sub(r"^[「」\"'‘’]+|[「」\"'‘’]+$", "", cancan_line.strip())
    for m in re.finditer(r"[^，。！？…；;]{4,14}", text):
        chunk = m.group(0).strip()
        if re.search(r"不算|算停|吐水|检查|示范|咽了", chunk):
            return chunk
    compact = re.sub(r"[的话呢呀嘛吧啊啦]", "", text)
    return compact[:14] if len(compact) >= 4 else text[:14]


def lines_high_overlap(a: str, b: str, *, thresh: float = 0.5) -> bool:
    chars_a = re.sub(r"[^\u4e00-\u9fff]", "", a or "")
    chars_b = re.sub(r"[^\u4e00-\u9fff]", "", b or "")
    if len(chars_a) < 3 or len(chars_b) < 3:
        return False
    sa = {chars_a[i : i + 2] for i in range(len(chars_a) - 1)}
    sb = {chars_b[i : i + 2] for i in range(len(chars_b) - 1)}
    return len(sa & sb) / len(sa | sb) >= thresh


def a_context_blob(story: dict) -> str:
    parts = [
        str(story.get("conflict_core") or ""),
        str(story.get("scene_title") or ""),
        str(story.get("setting") or ""),
        str(story.get("punchline_explain") or ""),
    ]
    dialogue = story.get("dialogue") or []
    if isinstance(dialogue, list):
        for d in dialogue[:6]:
            if isinstance(d, dict):
                parts.append(str(d.get("line") or ""))
    return "".join(parts)


def patch_closing_quotes(story: dict) -> list[str]:
    """引话未接地：仅当灿灿前文已有相近埋点时，把昭昭引语改成可引子串。

    若前文完全没有「检查/吐水/不算」类埋点，不硬改（交给 LLM）。
    """
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(item.get("line") or "")
        m = RE_CLOSING_QUOTE.search(line)
        if not m:
            continue
        frag = m.group(1).strip()
        prior_lines = [
            str(d.get("line") or "")
            for d in dialogue[:i]
            if isinstance(d, dict)
            and str(d.get("speaker") or "").strip() == "灿灿"
            and str(d.get("line") or "").strip()
        ]
        prior = "".join(prior_lines)
        if not prior.strip():
            continue
        soft_ok = (
            (
                re.search(r"检查.{0,6}不算吃", frag)
                and re.search(r"检查.{0,10}不算", prior)
            )
            or (
                re.search(r"吐水.{0,4}停", frag)
                and re.search(r"吐水.{0,6}停", prior)
            )
            or (
                re.search(r"漱口.{0,4}停", frag)
                and re.search(r"漱口.{0,6}停", prior)
            )
        )
        # 偷吃：前文已埋「检查不算吃」时，引话须点到这句（勿只引咽了才算）
        prefer_check = (
            "检查不算吃" in prior
            and "检查不算吃" not in frag
            and re.search(r"偷吃|饭前|水果|样品|检查", prior)
        )
        if (quote_grounded(frag, prior) or soft_ok) and not prefer_check:
            continue
        donor = ""
        if prefer_check:
            for ln in reversed(prior_lines):
                if "检查不算吃" in ln:
                    donor = ln
                    break
        if not donor:
            for ln in reversed(prior_lines):
                if re.search(r"不算|吐水|检查|示范|算停", ln):
                    donor = ln
                    break
        # 没有可对齐埋点就别乱改引话
        if not donor:
            continue
        cite = (
            "检查不算吃"
            if prefer_check and "检查不算吃" in donor
            else pick_cite_chunk(donor)
        )
        if not cite or (
            not prefer_check
            and not quote_grounded(cite, donor)
            and cite not in donor
        ):
            cite = donor[: min(12, len(donor))]
        if prefer_check:
            new_line = f"你刚才说{cite}"
        else:
            head = line[: m.start(1)]
            tail = line[m.end(1) :]
            room = DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(head + tail)
            if room < 4:
                continue
            new_frag = cite if dialogue_char_count(cite) <= room else cite[:room]
            new_line = f"{head}{new_frag}{tail}"
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            new_line = truncate_overlong_line(new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"引话对齐[{i}]")
            break
    return notes


A_STEAL_TRY_TASTE_RE = re.compile(
    r"试甜|试味道|帮你试|尝一下|尝得准|尝了|只尝|尝味道|甜不甜|"
    r"试一口|确认味道|咬一口就|知道甜|先试|算尝味|是甜的|甜度|"
    r"看看熟|熟不熟|坏了没|有没有坏|测试甜|确认质量"
)
A_STEAL_GATE_RE = re.compile(
    r"把关|资格|负责质量|检查员|有特权|质量员|我负责|我有权利"
)
A_STEAL_QC_RE = re.compile(
    r"半成品|大家安全|新不新鲜|新鲜不新鲜|不新鲜|为了大家|品质检测|安全起见|合格证书|"
    r"确认甜度|确认质量|含着|检查完"
)
A_STEAL_DODGE_RE = re.compile(r"溅|手脏")  # 「那是果汁/擦过」不算赖账


def patch_steal_ensure_spit(story: dict) -> list[str]:
    """埋句后、末四拍前须有「吐出来看看→已经咽了看不了」。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    bury_i = next((i for i, ln in enumerate(lines) if "检查不算吃" in ln), None)
    if bury_i is None:
        return notes
    has_ask = any(re.search(r"吐出来|吐给我看", ln) for ln in lines)
    has_spit = any(
        re.search(r"已经咽|咽下去了|看不了|吐不出来", ln) and "才算" not in ln
        for ln in lines
    )
    if has_ask and has_spit:
        return notes
    end = len(dialogue) - 4
    i_ask, i_spit = end - 2, end - 1
    if i_ask < 2 or i_spit < 3:
        return notes
    bury_line = lines[bury_i]
    if bury_i >= i_ask:
        # 埋句占了咽下位：前移到末四拍前的灿灿句
        moved = False
        for j in range(i_ask - 1, 2, -1):
            if not isinstance(dialogue[j], dict):
                continue
            if str(dialogue[j].get("speaker") or "") != "灿灿":
                continue
            if "检查不算吃" in str(dialogue[j].get("line") or ""):
                bury_i = j
                moved = True
                break
            dialogue[j]["line"] = (
                bury_line
                if dialogue_char_count(bury_line) <= DAILY_STORY_LINE_CHARS_MAX
                else "检查不算吃，咽了才算检"
            )
            if isinstance(dialogue[bury_i], dict) and bury_i != j:
                dialogue[bury_i]["line"] = "反正你不能先吃"
            bury_i = j
            notes.append(f"偷吃埋句让咽下[{j}]")
            moved = True
            break
        if not moved or bury_i >= i_ask:
            return notes
    if not isinstance(dialogue[i_ask], dict) or not isinstance(dialogue[i_spit], dict):
        return notes
    dialogue[i_ask]["speaker"] = "昭昭"
    dialogue[i_ask]["line"] = "那你吐出来给我看一看"
    dialogue[i_spit]["speaker"] = "灿灿"
    dialogue[i_spit]["line"] = "已经咽下去了，看不了"
    notes.append(f"偷吃补咽下[{i_ask},{i_spit}]")
    return notes


def patch_steal_dedupe_wipe(story: dict) -> list[str]:
    """「擦过」最多留 1 次。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    seen = False
    for i, d in enumerate(dialogue[:-4] if len(dialogue) > 4 else dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if "擦过" not in line:
            continue
        if not seen:
            seen = True
            continue
        new_line = (
            "反正我说了你不能吃"
            if str(d.get("speaker") or "") == "灿灿"
            else "凭什么就你能先吃"
        )
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去擦过复读[{i}]")
    return notes


def patch_steal_strip_rush(story: dict) -> list[str]:
    """删催进度句，改成画面抬杠。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue[:-4] if len(dialogue) > 4 else dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "昭昭":
            continue
        line = str(d.get("line") or "")
        if not re.search(r"倒是说|你倒是|到底咽", line):
            continue
        new_line = "那你吐出来给我看一看"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去催进度[{i}]")
    return notes


def patch_steal_dedupe_sample(story: dict) -> list[str]:
    """中段「检查样品/特地挑」只留第一次。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    mid = dialogue[:-4]
    seen = False
    for i, d in enumerate(mid):
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "")
        if not re.search(r"检查样品|特地挑", line):
            continue
        if "检查不算吃" in line:
            continue
        if not seen:
            seen = True
            continue
        new_line = "反正你现在不能碰"
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            continue
        d["line"] = new_line
        notes.append(f"偷吃去样品复读[{i}]")
    return notes


def patch_steal_bury_after_anchors(story: dict) -> list[str]:
    """「检查不算吃」若早于上次/姐姐，挪到二者之后的灿灿位。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 12:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    bury_i = next((i for i, ln in enumerate(lines) if "检查不算吃" in ln), None)
    if bury_i is None:
        return notes
    sister_i = next((i for i, ln in enumerate(lines) if "我是姐姐" in ln), None)
    last_i = next(
        (i for i, ln in enumerate(lines) if re.search(r"上次是上次|上次妈妈", ln)),
        None,
    )
    anchors = [i for i in (sister_i, last_i) if i is not None]
    if not anchors or bury_i >= max(anchors):
        return notes
    bury_line = lines[bury_i]
    # 原位改成检查样品铺垫（若还没有）
    if isinstance(dialogue[bury_i], dict):
        dialogue[bury_i]["line"] = "这是检查样品，是我特地挑出来检查的"
        notes.append(f"偷吃埋句让位[{bury_i}]")
    target = max(anchors) + 1
    for j in range(target, len(dialogue) - 4):
        if not isinstance(dialogue[j], dict):
            continue
        if str(dialogue[j].get("speaker") or "") != "灿灿":
            continue
        cur = str(dialogue[j].get("line") or "")
        if "检查不算吃" in cur:
            return notes
        dialogue[j]["line"] = (
            bury_line
            if dialogue_char_count(bury_line) <= DAILY_STORY_LINE_CHARS_MAX
            else "检查不算吃，咽了才算检"
        )
        notes.append(f"偷吃埋句后移[{j}]")
        break
    return notes


def patch_steal_strip_qc_jargon(story: dict) -> list[str]:
    """偷吃去掉质检说明书词，改回赖账/检查口径。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        sp = str(d.get("speaker") or "")
        new_line = line
        if A_STEAL_QC_RE.search(line) or re.search(r"新鲜", line):
            if sp == "灿灿":
                new_line = "反正饭前你不能吃"
            else:
                new_line = "凭什么你能吃我不能吃"
        elif "洗手" in line:
            if sp == "灿灿":
                new_line = "你手脏，先别碰这个盘子"
            else:
                new_line = "你手不也刚捏过水果吗"
        elif sp == "灿灿" and re.search(r"那是果汁|果汁，我没", line) and not re.search(
            r"溅|手脏",
            line,
        ):
            new_line = "果汁溅脸上了，不是偷吃"
        if (
            new_line != line
            and dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去质检词[{i}]")
    return notes


def patch_steal_strip_try_taste(story: dict) -> list[str]:
    """偷吃已走检查线时，把试甜/尝味句改回检查口径（去叠免责）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not A_STEAL_TRY_TASTE_RE.search(line):
            continue
        if re.search(r"咽|看不了", line):
            new_line = "嗯，检查完了，只好咽了"
        elif re.search(r"样品|检查", line):
            new_line = "这是检查样品，是我特地挑出来检查的"
        else:
            new_line = A_STEAL_TRY_TASTE_RE.sub("", line)
            new_line = re.sub(r"[，,]{2,}", "，", new_line)
            new_line = re.sub(r"\s{2,}", " ", new_line).strip("，,。 ")
            if len(new_line) < 4:
                new_line = "这是检查样品，是我特地挑出来检查的"
        if (
            new_line != line
            and dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去试尝[{i}]")
    return notes


def patch_steal_strip_gate(story: dict) -> list[str]:
    """偷吃已走检查线时，删把关/资格/检查员等叠套词。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    if not A_STEAL_GATE_RE.search(text):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not A_STEAL_GATE_RE.search(line):
            continue
        new_line = A_STEAL_GATE_RE.sub("", line)
        new_line = re.sub(r"[，,]{2,}", "，", new_line)
        new_line = re.sub(r"\s{2,}", " ", new_line).strip("，,。 ")
        if len(new_line) < 4:
            # 整句只剩身份话术：换成检查线短句，避免空行硬卡
            if "那不一样" in line:
                new_line = "那不一样，检样不算开饭"
            else:
                new_line = "这是检查样品，是我特地挑出来检查的"
        if (
            new_line != line
            and dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去把关[{i}]")
    return notes


def patch_steal_fix_broken_authority(story: dict) -> list[str]:
    """修好半截「我是姐姐，…啦」残句，避免补语气词后更怪。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "").strip()
        if not re.match(r"^我是姐姐[，,]", line):
            continue
        # 过短或明显截断：先/我得/得 + 可选啦
        if len(line) <= 8 or re.match(
            r"^我是姐姐[，,]\s*(先|我得|得|管)啦?$",
            line,
        ):
            new_line = "我是姐姐，饭前你不能吃"
            if (
                new_line != line
                and dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
            ):
                d["line"] = new_line
                notes.append(f"偷吃修权威残句[{i}]")
    return notes


def patch_steal_ensure_beats(story: dict) -> list[str]:
    """偷吃检查线：补「我是姐姐 / 上次 / 检查不算吃」骨架词（助冲突层+引话）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    mid = [d for d in dialogue[:-4] if isinstance(d, dict)]
    if len(mid) < 4:
        return notes

    def _set_line(d: dict, new_line: str, note: str) -> bool:
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            return False
        if new_line == str(d.get("line") or ""):
            return False
        d["line"] = new_line
        notes.append(note)
        return True

    if "我是姐姐" not in text:
        # 勿写进开场前几句；优先中后段饭前规矩句
        mid_late = mid[max(4, len(mid) // 3) :]
        for d in mid_late:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"饭前|不许|不能吃|我说不行", line):
                line_s = f"我是姐姐，{line}"
                if _set_line(d, line_s, "偷吃补我是姐姐"):
                    break
        else:
            for d in reversed(mid_late or mid):
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "我是姐姐，饭前你不能吃",
                        "偷吃补我是姐姐",
                    ):
                        break

    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"上次", text):
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"溅|手脏|别碰|果汁", line) or len(line) <= 10:
                if _set_line(
                    d,
                    "上次是上次，妈妈在今天不算",
                    "偷吃补上次",
                ):
                    break
        else:
            # 找中段第二句灿灿位改写
            for d in mid[2:]:
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "上次是上次，妈妈在今天不算",
                        "偷吃补上次",
                    ):
                        break

    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if "检查不算吃" not in text:
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"检查样品|特地挑|样品", line):
                if _set_line(
                    d,
                    "检查不算吃，咽了才算检",
                    "偷吃补检查不算吃",
                ):
                    break
        else:
            for d in reversed(mid):
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "检查不算吃，咽了才算检",
                        "偷吃补检查不算吃",
                    ):
                        break
    return notes


def patch_steal_closing(story: dict) -> list[str]:
    """偷吃收束：统一成「那不一样，检样不算开饭」。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    dodge = dialogue[-3]
    if not isinstance(dodge, dict):
        return notes
    line = str(dodge.get("line") or "")
    if "那不一样" not in line:
        return notes
    new_line = "那不一样，检样不算开饭"
    if line != new_line and dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
        dodge["line"] = new_line
        notes.append("收束改检样不算开饭")
    return notes


def patch_steal_trim_la(story: dict) -> list[str]:
    """偷吃：句尾语气词过多时剥掉，避免补字注水。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    particle_idx = [
        i
        for i, d in enumerate(dialogue)
        if isinstance(d, dict)
        and re.search(r"[啦呀嘛啊呢吧]$", str(d.get("line") or "").rstrip())
    ]
    if len(particle_idx) < 3:
        return notes
    # 最多留 1 个句尾语气词；贴下限时停剥，避免再掉回字数硬卡
    for i in particle_idx[1:]:
        if dialogue_total_chars(story) <= DAILY_STORY_BODY_CHARS_MIN:
            break
        line = str(dialogue[i].get("line") or "")
        new_line = re.sub(r"[啦呀嘛啊呢吧]+$", "", line).rstrip("，, ")
        if new_line and new_line != line:
            dialogue[i]["line"] = new_line
            notes.append(f"偷吃去语气词[{i}]")
    return notes


def patch_steal_dedupe_sister(story: dict) -> list[str]:
    """「我是姐姐」全场只留一次。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    seen = False
    for i, d in enumerate(dialogue[:-4] if len(dialogue) > 4 else dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "")
        if "我是姐姐" not in line:
            continue
        if not seen:
            seen = True
            continue
        new_line = "饭前你不能吃，听到没"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去姐姐复读[{i}]")
    return notes


def steal_dodge_templates(prev_speaker: str) -> list[tuple[str, str]]:
    """按上一句 speaker 选交替赖账四句，避免连说。"""
    if prev_speaker == "昭昭":
        return [
            ("灿灿", "果汁溅脸上了，不是偷吃"),
            ("昭昭", "溅脸上？你整块塞嘴里了"),
            ("灿灿", "你手脏，先别碰这个盘子"),
            ("昭昭", "你手不也刚捏过水果吗"),
        ]
    return [
        ("昭昭", "那你腮帮子一动一动的"),
        ("灿灿", "果汁溅脸上了，不是偷吃"),
        ("昭昭", "溅脸上？你整块塞嘴里了"),
        ("灿灿", "你手脏，先别碰这个盘子"),
    ]


def patch_steal_fix_dodge_roles(story: dict) -> list[str]:
    """赖账借口须灿灿说；角色反了则整段重写第 2–5 句，避免连说。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    excuse_re = re.compile(r"溅脸上了|不是偷吃|手脏，先别碰|我擦过了")
    flipped = any(
        isinstance(d, dict)
        and str(d.get("speaker") or "") == "昭昭"
        and excuse_re.search(str(d.get("line") or ""))
        for d in dialogue[:-4]
    )
    if not flipped:
        return notes
    prev = str(dialogue[1].get("speaker") or "") if isinstance(dialogue[1], dict) else ""
    templates = steal_dodge_templates(prev)
    for i, (sp, ln) in enumerate(templates):
        idx = 2 + i
        if not isinstance(dialogue[idx], dict):
            return notes
        dialogue[idx]["speaker"] = sp
        dialogue[idx]["line"] = ln
        notes.append(f"偷吃纠角色[{idx}]")
    return notes


def patch_steal_ensure_dodge(story: dict) -> list[str]:
    """检查样品前须有赖账抬杠（溅脸/手脏）；缺则改写中前段 2 来回。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 12:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    check_i = next(
        (
            i
            for i, ln in enumerate(lines)
            if re.search(r"检查样品|特地挑|检查不算吃", ln)
        ),
        None,
    )
    if check_i is None:
        return notes
    cancan_dodge = any(
        isinstance(dialogue[i], dict)
        and str(dialogue[i].get("speaker") or "") == "灿灿"
        and re.search(r"溅|手脏", str(dialogue[i].get("line") or ""))
        for i in range(check_i)
    )
    if cancan_dodge:
        return notes
    if len(dialogue) < 10:
        return notes
    saved_check = ""
    for i in range(2, 6):
        if isinstance(dialogue[i], dict) and re.search(
            r"检查样品|特地挑|检查不算吃",
            str(dialogue[i].get("line") or ""),
        ):
            saved_check = str(dialogue[i].get("line") or "")
            break
    prev = str(dialogue[1].get("speaker") or "") if isinstance(dialogue[1], dict) else ""
    templates = steal_dodge_templates(prev)
    for i, (sp, ln) in enumerate(templates):
        idx = 2 + i
        if not isinstance(dialogue[idx], dict):
            return notes
        dialogue[idx]["speaker"] = sp
        dialogue[idx]["line"] = ln
        notes.append(f"偷吃补赖账[{idx}]")
    if saved_check:
        for j in range(6, len(dialogue) - 4):
            if not isinstance(dialogue[j], dict):
                continue
            if str(dialogue[j].get("speaker") or "") != "灿灿":
                continue
            cur = str(dialogue[j].get("line") or "")
            if re.search(r"检查样品|特地挑|检查不算吃", cur):
                break
            dialogue[j]["line"] = (
                saved_check
                if dialogue_char_count(saved_check) <= DAILY_STORY_LINE_CHARS_MAX
                else "这是检查样品，是我特地挑出来检查的"
            )
            notes.append(f"偷吃挪检查[{j}]")
            break
    return notes


def patch_steal_strip_mid_filler(story: dict) -> list[str]:
    """删大颗/检查工作类注水，改回抬杠短句。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果|荔枝", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    filler_re = re.compile(
        r"大颗|小的不用|容易检查|检查工作|检查过了|大的都检查|拣一颗大|"
        r"中间才准|边上不甜|比我拇指|挖的那勺"
    )
    for i, d in enumerate(dialogue[:-4] if len(dialogue) > 4 else dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not filler_re.search(line):
            continue
        sp = str(d.get("speaker") or "")
        new_line = (
            "反正你不能先吃"
            if sp == "灿灿"
            else "凭什么就你能先吃"
        )
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去中段注水[{i}]")
    return notes


def patch_steal_strip_false_spit(story: dict) -> list[str]:
    """删「吐出来了在桌上」等假吐，避免与「已经咽了」打架。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果|荔枝", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    false_re = re.compile(r"吐出来了.{0,6}(桌上|这里|那儿)|吐在桌上")
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not false_re.search(line):
            continue
        sp = str(d.get("speaker") or "")
        new_line = (
            "检查不算吃，咽了才算检"
            if sp == "灿灿"
            else "那你吐出来给我看一看"
        )
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去假吐[{i}]")
    return notes


def patch_steal_fix_early_sister(story: dict) -> list[str]:
    """开场前 4 句勿带「我是姐姐」，挪到中段再补。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果|荔枝", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    for i, d in enumerate(dialogue[:4]):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "")
        if "我是姐姐" not in line:
            continue
        new_line = re.sub(r"我是姐姐[，,]?", "", line).strip("，,。 ")
        if len(new_line) < 4:
            new_line = "饭前不许偷吃，你别瞎说"
        if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃挪开场姐姐[{i}]")
    return notes


def _steal_fruit_label(story: dict) -> tuple[str, str]:
    blob = a_context_blob(story)
    theme = str(story.get("_theme") or "")
    blob = theme + blob
    for name in (
        "荔枝",
        "芒果",
        "西瓜",
        "草莓",
        "葡萄",
        "香蕉",
        "苹果",
        "橙子",
        "猕猴桃",
        "梨",
    ):
        if name in blob:
            unit = "一颗" if name in ("荔枝", "草莓", "葡萄") else "一块"
            return name, unit
    return "水果", "一块"


def patch_steal_align_skeleton(story: dict) -> list[str]:
    """口感硬伤仍在时，对齐压缩正例骨架（换水果），避免补丁痕迹堆叠。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果|荔枝", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    from app.services.daily_story.story_types.a.humor import collect_humor_issues

    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    speakers = [
        str(d.get("speaker") or "") if isinstance(d, dict) else "" for d in dialogue
    ]
    issues = collect_humor_issues(lines, speakers)
    # 仅结构性硬伤才整段对齐；语气词/轻注水交给局部 patch，勿盖定稿
    bad = any(
        any(
            k in iss
            for k in (
                "缺赖账",
                "缺咽下一锤",
                "咽下自相矛盾",
                "权威过早",
                "催进度",
                "埋句过早",
                "样品复读",
                "角色错位",
                "多套免责",
            )
        )
        for iss in issues
    )
    if not bad:
        return notes
    fruit, unit = _steal_fruit_label(story)
    whole = "整颗" if unit.endswith("颗") else "整块"
    skeleton = [
        ("昭昭", f"{fruit}盘怎么少了{unit}？"),
        ("灿灿", "少了？我刚数过明明还在呀，你数错了吧"),
        ("昭昭", "你嘴里鼓鼓的，在嚼什么"),
        ("灿灿", "饭前不许偷吃，你别瞎说"),
        ("昭昭", "那你腮帮子一动一动的"),
        ("灿灿", "果汁溅脸上了，不是偷吃，你别乱讲"),
        ("昭昭", f"溅脸上？你{whole}塞嘴里了"),
        ("灿灿", "你手脏，先别碰这个盘子"),
        ("昭昭", f"你手不也刚捏过{fruit}吗"),
        ("灿灿", "我擦过了，你没看见吗，眼神真差"),
        ("昭昭", "你上次偷吃也是这说法"),
        ("灿灿", "上次是上次，上次妈妈在，今天不算"),
        ("昭昭", "凭什么你能吃我不能吃"),
        ("灿灿", "我是姐姐，饭前你不能吃"),
        ("昭昭", "你自己不也还没开饭吗"),
        ("灿灿", "这是检查样品，是我特地挑出来检查的"),
        ("昭昭", "检查样品就能先吃掉？"),
        ("灿灿", "检查不算吃，咽了才算检"),
        ("昭昭", "那你吐出来给我看一看"),
        ("灿灿", "已经咽下去了，看不了，吐不出来了"),
        ("昭昭", "你刚才说检查不算吃"),
        ("灿灿", "那不一样，检样不算开饭"),
        ("昭昭", "哪里不一样？都进肚子了"),
        ("灿灿", f"……行吧，给你{unit}"),
    ]
    story["dialogue"] = [{"speaker": sp, "line": ln} for sp, ln in skeleton]
    story["discovery_opening"] = [
        {"speaker": skeleton[0][0], "line": skeleton[0][1]},
        {"speaker": skeleton[1][0], "line": skeleton[1][1]},
    ]
    if not str(story.get("conflict_core") or "").strip():
        story["conflict_core"] = f"灿灿不许昭昭饭前偷吃自己却先捏了{fruit}"
    notes.append("偷吃骨架对齐")
    return notes


def patch_steal_open_cohere(story: dict) -> list[str]:
    """开场若已喊偷吃，勿接「少了？」；缺盘少锚则改成盘少问句。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果|荔枝", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    if not isinstance(dialogue[0], dict) or not isinstance(dialogue[1], dict):
        return notes
    l0 = str(dialogue[0].get("line") or "")
    l1 = str(dialogue[1].get("line") or "")
    fruit, unit = _steal_fruit_label(story)
    if re.search(r"^少了", l1) and not re.search(r"少|盘", l0):
        new0 = f"{fruit}盘怎么少了{unit}？"
        if dialogue_char_count(new0) <= DAILY_STORY_LINE_CHARS_MAX:
            dialogue[0]["speaker"] = "昭昭"
            dialogue[0]["line"] = new0
            notes.append("偷吃开场对齐盘少")
            opening = story.get("discovery_opening")
            if isinstance(opening, list) and opening and isinstance(opening[0], dict):
                opening[0]["speaker"] = "昭昭"
                opening[0]["line"] = new0
    # 埋句质检腔：统一成短埋句
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "")
        if "检查不算吃" not in line:
            continue
        if line == "检查不算吃，咽了才算检":
            continue
        if re.search(r"检验|完成|专业", line) or len(line) > 14:
            new_line = "检查不算吃，咽了才算检"
            if dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
                d["line"] = new_line
                notes.append(f"偷吃埋句收短[{i}]")
    return notes


def patch_a_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_steal_strip_try_taste(story))
    notes.extend(patch_steal_strip_gate(story))
    notes.extend(patch_steal_strip_qc_jargon(story))
    notes.extend(patch_steal_strip_rush(story))
    notes.extend(patch_steal_strip_mid_filler(story))
    notes.extend(patch_steal_strip_false_spit(story))
    notes.extend(patch_steal_fix_early_sister(story))
    notes.extend(patch_steal_open_cohere(story))
    notes.extend(patch_steal_ensure_dodge(story))
    notes.extend(patch_steal_fix_dodge_roles(story))
    notes.extend(patch_steal_fix_broken_authority(story))
    notes.extend(patch_steal_ensure_beats(story))
    notes.extend(patch_steal_dedupe_sister(story))
    notes.extend(patch_steal_bury_after_anchors(story))
    notes.extend(patch_steal_dedupe_sample(story))
    notes.extend(patch_steal_dedupe_wipe(story))
    notes.extend(patch_steal_ensure_spit(story))
    notes.extend(patch_closing_quotes(story))
    notes.extend(patch_steal_closing(story))
    notes.extend(patch_steal_trim_la(story))
    notes.extend(patch_steal_strip_try_taste(story))
    notes.extend(patch_steal_strip_gate(story))
    notes.extend(patch_steal_strip_qc_jargon(story))
    notes.extend(patch_steal_strip_rush(story))
    notes.extend(patch_steal_strip_mid_filler(story))
    notes.extend(patch_steal_strip_false_spit(story))
    notes.extend(patch_steal_open_cohere(story))
    notes.extend(patch_steal_dedupe_wipe(story))
    notes.extend(patch_steal_trim_la(story))
    notes.extend(patch_steal_fix_broken_authority(story))
    notes.extend(patch_steal_ensure_spit(story))
    notes.extend(patch_steal_closing(story))
    notes.extend(patch_steal_align_skeleton(story))
    return notes
