"""A 类正文硬卡。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_CLOSING_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)
def append_closing_quote_errors(story: dict, errors: list[str]) -> None:
    """A 类：末段「你刚才说…」须能在灿灿前文找到原话。"""
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code != "A":
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return
    body = dialogue[:-4]
    cancan = "".join(
        str(d.get("line") or "")
        for d in body
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "灿灿"
    )
    if not cancan.strip():
        return

    def _grounded(frag: str, hay: str) -> bool:
        clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", frag)
        hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
        if len(clean) < 3:
            return True
        run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
        for i in range(len(clean) - run + 1):
            if clean[i:i + run] in hay2:
                return True
        if len(clean) < 6:
            pieces = [clean[i:i + 2] for i in range(0, len(clean) - 1, 2)]
            if len(pieces) >= 3:
                hit = sum(1 for p in pieces if p in hay2)
                if hit >= (len(pieces) * 2 + 2) // 3:
                    return True
        return False

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(item.get("line") or "")
        for m in RE_CLOSING_QUOTE.finditer(line):
            frag = m.group(1).strip()
            prior_cancan = "".join(
                str(d.get("line") or "")
                for d in dialogue[:i]
                if isinstance(d, dict)
                and str(d.get("speaker") or "").strip() == "灿灿"
            )
            if not prior_cancan.strip():
                continue
            if not _grounded(frag, prior_cancan):
                soft_ok = (
                    (
                        re.search(r"吐水.{0,4}停", frag)
                        and re.search(r"吐水.{0,6}停", prior_cancan)
                    )
                    or (
                        re.search(r"漱口.{0,4}停", frag)
                        and re.search(r"漱口.{0,6}停", prior_cancan)
                    )
                    or (
                        re.search(r"检查.{0,6}不算吃", frag)
                        and re.search(r"检查.{0,10}不算", prior_cancan)
                    )
                )
                if not soft_ok:
                    errors.append(
                        f"A类引话须出自灿灿前文原话（无「{frag[:14]}」），"
                        "禁止昭昭自造后再假装引用",
                    )
                    return


A_MID_RULE_STEMS = (
    ("漱口", 4),
    ("两分钟", 6),
    ("停了", 4),
    ("说话算数", 3),
)


def _line_bigrams(text: str) -> set[str]:
    chars = re.sub(r"[^\u4e00-\u9fff]", "", text or "")
    if len(chars) < 2:
        return set()
    return {chars[i:i + 2] for i in range(len(chars) - 1)}


def lines_high_overlap(a: str, b: str, *, thresh: float = 0.5) -> bool:
    sa, sb = _line_bigrams(a), _line_bigrams(b)
    if len(sa) < 3 or len(sb) < 3:
        return False
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

def append_steal_single_line_errors(story: dict, errors: list[str]) -> None:
    """A 类饭前偷吃：单线免责 + 咽下后立刻收束（硬卡）。"""
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return
    blob = a_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉", blob):
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return
    text = "".join(
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    )
    buckets: list[str] = []
    # 硬卡只拦「检查 + 把关/示范」；试尝叠检查改由质检压分，避免生成空转
    if re.search(r"检查不算|检查样品|特地挑", text):
        buckets.append("检查")
    if re.search(r"把关|资格|负责质量|检查员|有特权|我有权利", text):
        buckets.append("把关")
    if re.search(r"示范", text):
        buckets.append("示范")
    if len(buckets) >= 2:
        errors.append(
            "A类偷吃只能一套免责（检查不算吃）；"
            f"正文叠了{'+'.join(buckets)}，删到只留检查线"
            "（禁把关/示范/资格）",
        )
        return

    # 收束硬卡（结构节奏交给质检，避免生成空转）
    lines = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    if len(lines) >= 3:
        dodge = lines[-3]
        if "那不一样" in dodge and re.search(
            r"那不一样[，,]?\s*(我那是)?[…\.。]{0,3}\s*$",
            dodge,
        ):
            errors.append(
                "收束「那不一样」须说完新借口（如检样不算开饭），禁止半截省略",
            )
        elif "那不一样" in dodge and not re.search(
            r"检样不算开饭|不算开饭",
            dodge,
        ):
            errors.append(
                "收束「那不一样」须用「检样不算开饭」类区分，"
                "禁止只回样品/检查的一部分",
            )


def append_mid_restatement_errors(story: dict, errors: list[str]) -> None:
    """A 类：中段同一规矩勿换措辞再立一遍。"""
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "A":
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return
    body = dialogue[:-4]
    lines: list[tuple[str, str]] = []
    for d in body:
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        ln = str(d.get("line") or "").strip()
        if ln:
            lines.append((sp, ln))
    if len(lines) < 8:
        return

    for stem, limit in A_MID_RULE_STEMS:
        hits = sum(1 for _, ln in lines if stem in ln)
        if hits >= limit:
            errors.append(
                f"中段「{stem}」出现{hits}次：同一规矩只立一次"
                "（最多再确认1句），然后立刻进一锤场面",
            )
            return

    filler_hits = sum(
        1
        for _, ln in lines
        if re.search(
            r"你确定|说到做到|绝不反悔|你好好数|我看着|我数着|"
            r"眨眼睛|换手拿|中间不能|换位置|别数|没离开嘴巴|"
            r"挤牙膏了吗|牙刷没沾|你不能作弊|数得准|数错了|我看着你|"
            r"三十下|二十下|认真数|帮你盯|偷工减料|起步|"
            r"你又没计时|你也没计时|怎么证明|怎么知道我没|"
            r"数得慢|秒表一样|我数了",
            ln,
        )
    )
    if filler_hits >= 3:
        errors.append(
            "中段注水过多（三十下/认真数/计时抬杠等），"
            "埋「吐水算停」后立刻示范翻车",
        )
        return

    # 相邻两句同义复读：你又没计时 / 你也没计时 / 怎么证明
    for i in range(1, len(lines)):
        a, b = lines[i - 1][1], lines[i][1]
        if re.search(r"计时|怎么证明|怎么知道.{0,4}没", a) and re.search(
            r"计时|怎么证明|怎么知道.{0,4}没",
            b,
        ):
            errors.append(
                "中段禁止连着两句抠「没计时/怎么证明」同义抬杠，"
                "一句带过就进立规或示范",
            )
            return

    full_mid = "".join(ln for _, ln in lines)
    if re.search(r"刷牙|漱口|牙刷", full_mid):
        timer_pad = sum(
            1
            for _, ln in lines
            if re.search(
                r"默数|电子表|掐表|没带手机|计时器呢|用那个|我盯着表|帮你掐",
                ln,
            )
        )
        if timer_pad >= 3:
            errors.append(
                "刷牙中段禁止抠计时工具（默数/电子表/掐表），"
                "立完规矩后立刻示范翻车",
            )
            return
        # 一锤过晚：以「吐水算停」埋句为起点（勿用开场「两分钟」抬杠起算）
        rule_i = next(
            (
                i
                for i, (_, ln) in enumerate(lines)
                if re.search(r"吐水.{0,4}停", ln)
            ),
            None,
        )
        if rule_i is None:
            rule_i = next(
                (
                    i
                    for i, (_, ln) in enumerate(lines)
                    if "两分钟" in ln or "连续刷" in ln
                ),
                None,
            )
        hammer_i = next(
            (
                i
                for i, (sp, ln) in enumerate(lines)
                if i > (rule_i or 0)
                and re.search(
                    r"才刷|就吐|就停|就漱|玩手机|泡沫|几下|"
                    r"[一二三四五六七八九十两\d]+下|示范.{0,6}吐|噗|"
                    r"一[、,，]\s*二",
                    ln,
                )
                and (sp == "昭昭" or sp == "灿灿")
            ),
            None,
        )
        if rule_i is not None and hammer_i is None:
            errors.append(
                "刷牙缺一锤场面：须有昭昭指出灿灿示范时"
                "刷几下就吐/停/玩手机",
            )
            return
        if (
            rule_i is not None
            and hammer_i is not None
            and hammer_i - rule_i > 8
        ):
            errors.append(
                "刷牙一锤过晚：埋「吐水算停」后勿再抬杠，立刻示范翻车",
            )
            return
        many = any(
            sp == "灿灿" and re.search(r"很多下|刷了好多|刷了不少", ln)
            for sp, ln in lines
        )
        few = any(
            re.search(r"才刷\s*[一二两三四五六七八九十两\d]+\s*下", ln)
            for _, ln in lines
        )
        if many and few:
            errors.append(
                "刷牙次数自相矛盾：先说刷了很多下，后又才刷两三下，只留一套",
            )
            return
        # 埋句取最后一次「吐水…停」（开场抬杠可先谈两分钟）
        bury_idxs = [
            i for i, (_, ln) in enumerate(lines) if re.search(r"吐水.{0,4}停", ln)
        ]
        bury_i = bury_idxs[-1] if bury_idxs else None
        spit_hammer_i = next(
            (
                i
                for i, (_, ln) in enumerate(lines)
                if re.search(
                    r"才.{0,6}下|才刷|就吐|噗|"
                    r"一[、,，]\s*二|一\s*二\s*三",
                    ln,
                )
                and i > (bury_i or -1)
            ),
            None,
        )
        if bury_i is not None and spit_hammer_i is not None and spit_hammer_i - bury_i > 6:
            errors.append(
                "刷牙不好玩：埋「吐水算停」后铺垫过长，"
                "须很快出现数下就吐/噗",
            )
            return
        if bury_i is not None and spit_hammer_i is None:
            errors.append(
                "刷牙不好玩：有吐水算停却无一锤"
                "（才X下就吐 / 一、二、噗）",
            )
            return

    if dialogue:
        last = dialogue[-1]
        if isinstance(last, dict):
            last_ln = str(last.get("line") or "")
            if re.search(
                r"算你厉害|你赢了|算你赢|你厉害|你等着|"
                r"你.{0,4}(?:重刷|再刷|过关)",
                last_ln,
            ):
                errors.append(
                    "末句禁止认赢/甩狠/继续管人（重刷/你等着），"
                    "只许哼/行吧/随便/给你一块",
                )
                return
        # 收束「那不一样」禁止空甩身份
        if len(dialogue) >= 3:
            dodge = str(dialogue[-3].get("line") or "") if isinstance(dialogue[-3], dict) else ""
            if "那不一样" in dodge and re.search(r"我是姐姐|我说了算", dodge):
                if not re.search(
                    r"示范|泡沫|教学|吐泡沫|教你|检样|开饭|样品",
                    dodge,
                ):
                    errors.append(
                        "收束「那不一样」禁止只甩「我是姐姐」，"
                        "须具体借口（示范/检样不算开饭等）",
                    )
                    return

    zhao_qs = [
        (i, ln)
        for i, (sp, ln) in enumerate(lines)
        if sp == "昭昭" and ("？" in ln or "吗" in ln or "呢" in ln)
    ]
    for i in range(len(zhao_qs)):
        for j in range(i + 1, len(zhao_qs)):
            ia, la = zhao_qs[i]
            ib, lb = zhao_qs[j]
            if ib - ia > 8:
                break
            if _lines_high_overlap(la, lb):
                errors.append(
                    "中段昭昭换措辞重复追问同一规矩"
                    f"（近重复：「{la[:10]}」≈「{lb[:10]}」），"
                    "删掉重复回合直接进一锤",
                )
                return



def append_a_body_errors(story: dict, errors: list[str]) -> None:
    append_closing_quote_errors(story, errors)
    append_mid_restatement_errors(story, errors)
    append_steal_single_line_errors(story, errors)
