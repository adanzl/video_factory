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
    r"半成品|大家安全|新不新鲜|为了大家|品质检测|安全起见|合格证书|"
    r"确认甜度|确认质量|含着|检查完"
)
A_STEAL_DODGE_RE = re.compile(r"溅|手脏|擦过|果汁")  # 鼓鼓只算发现，不算赖账


def patch_steal_strip_qc_jargon(story: dict) -> list[str]:
    """偷吃去掉质检说明书词，改回赖账/检查口径。"""
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
        line = str(d.get("line") or "")
        sp = str(d.get("speaker") or "")
        new_line = line
        if A_STEAL_QC_RE.search(line):
            if sp == "灿灿":
                new_line = "这是检查样品，是我特地挑出来检查的"
            else:
                new_line = "检查样品就能先吃掉？"
        elif "洗手" in line:
            if sp == "灿灿":
                new_line = "你手脏，先别碰这个盘子"
            else:
                new_line = "你手不也刚捏过水果吗"
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
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"饭前|不许|不能吃|我说不行", line):
                line_s = f"我是姐姐，{line}"
                if _set_line(d, line_s, "偷吃补我是姐姐"):
                    break
        else:
            for d in mid:
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
    particle_idx = [
        i
        for i, d in enumerate(dialogue)
        if isinstance(d, dict)
        and re.search(r"[啦呀嘛啊呢吧]$", str(d.get("line") or "").rstrip())
    ]
    if len(particle_idx) < 3:
        return notes
    # 最多留 1 个句尾语气词
    for i in particle_idx[1:]:
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
        and re.search(r"溅|手脏|擦过|果汁", str(dialogue[i].get("line") or ""))
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


def patch_a_body(story: dict) -> list[str]:
    notes: list[str] = []
    notes.extend(patch_steal_strip_try_taste(story))
    notes.extend(patch_steal_strip_gate(story))
    notes.extend(patch_steal_strip_qc_jargon(story))
    notes.extend(patch_steal_ensure_dodge(story))
    notes.extend(patch_steal_fix_dodge_roles(story))
    notes.extend(patch_steal_fix_broken_authority(story))
    notes.extend(patch_steal_ensure_beats(story))
    notes.extend(patch_steal_dedupe_sister(story))
    notes.extend(patch_closing_quotes(story))
    notes.extend(patch_steal_closing(story))
    notes.extend(patch_steal_trim_la(story))
    notes.extend(patch_steal_strip_try_taste(story))
    notes.extend(patch_steal_strip_gate(story))
    notes.extend(patch_steal_strip_qc_jargon(story))
    notes.extend(patch_steal_trim_la(story))
    notes.extend(patch_steal_fix_broken_authority(story))
    notes.extend(patch_steal_closing(story))
    return notes
