"""A 类好笑维硬伤与引话 haystack。"""

from __future__ import annotations

import re

_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)


def humor_revision_hint(issue: str) -> str | None:
    if any(
        k in issue
        for k in (
            "缺赖账", "催进度", "埋句过早", "检查样品复读", "质检说明书",
            "多套免责", "咽下后", "缺咽下一锤", "咽下自相矛盾", "权威过早",
            "角色错位", "语气词注水",
        )
    ):
        return (
            f"【偷吃口感】{issue}。"
            "严格按压缩正例换水果：少一块→溅脸手脏→上次→姐姐→样品→"
            "检查不算吃→吐出来/咽了→末四拍；删大颗检查/桌上假吐/新鲜闲聊。"
        )
    if "末四拍不完整" in issue:
        return (
            "【A·末四拍】末尾连续4句须是：昭昭「你刚才说/你自己说+灿灿原话」→"
            "灿灿「那不一样…」→昭昭「哪里不一样？都…」→灿灿软破功（行吧/哼/随便）；"
            "四句缺一即改；「哪里不一样」全篇只此一处；只改末4句。"
        )
    if "追问闭环模板复读" in issue:
        return (
            "【A·去复读】「哪里不一样/都是听」追问闭环全篇只此一处（末四拍用）；"
            "中段换别的追问（凭什么/你算给我看/那你呢），勿提前用掉闭环句。"
        )
    if "空甩身份" in issue:
        return (
            "【A·收束借口】倒数第3句「那不一样」只把刚才那一刀划出去"
            "（这刀不算 / 检样不算开饭），勿空甩「我是姐姐」。"
        )
    if "未扣一锤" in issue:
        return (
            "【A·引话扣锤】末四拍引话须扣一锤动作的原话（吐水/停手/吧唧/咽下/系反），"
            "勿只引「两分钟/我是姐姐」类空规矩。"
        )
    if "好笑不足" in issue or "格式达标但好笑" in issue:
        return (
            "【A·一锤落地】中段须有一锤当场可拍、不可否认的翻车"
            "（灿灿示范/亲自操作露馅：算错数、刷几下就吐、嚼出声、系反散开），"
            "灿灿认动作、只争「这样不算违规」，越争越露馅；"
            "好笑来自「嘴硬不认→现场被指→软下来」这条链，"
            "改稿时把新起的名称换回句位库（这刀不算 + 手上动作 + 可拍结果）；"
            "翻车落到可数细节（第几口/几下/哪个数）；"
            "「哪里不一样」全篇只此一处（末四拍用），中段换别的质问；"
            "末四拍：你刚才说+原话→那不一样→哪里不一样→行吧+让出/不再教。"
        )
    return None


def closing_quote_haystack(
    lines: list[str],
    speakers: list[str] | None,
    body_text: str,
) -> str:
    if not speakers or len(speakers) != len(lines):
        return body_text
    body_n = len(lines[:-4]) if len(lines) > 4 else len(lines) - 1
    cancan = "".join(
        lines[i] for i in range(body_n) if speakers[i] == "灿灿"
    )
    return cancan if cancan.strip() else body_text


def _close_four_beat_complete(
    tail4: list[str],
    tail4_speakers: list[str] | None = None,
) -> bool:
    if len(tail4) < 4:
        return False
    words_ok = (
        "那不一样" in tail4[-3]
        and ("哪里不一样" in tail4[-2] or "都是听" in tail4[-2])
        and any(m in tail4[-1] for m in ("哼", "行吧", "随便", "好吧", "算了"))
    )
    if not words_ok:
        return False
    # speaker 顺序：昭昭引话(-4) → 灿灿那不一样(-3) → 昭昭哪里不一样(-2) → 灿灿软破功(-1)
    if tail4_speakers and len(tail4_speakers) >= 4:
        s = tail4_speakers[-4:]
        if s != ["昭昭", "灿灿", "昭昭", "灿灿"]:
            return False
    return True


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    cons: list[str] = []
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    body_text = "".join(body)
    tail_text = "".join(tail4)

    if ("哪里不一样" in body_text or "都是听" in body_text) and (
        "哪里不一样" in tail_text or "都是听" in tail_text
    ):
        cons.append("追问闭环模板复读")
    if "不公平" in body_text and "凭什么" not in body_text[:40]:
        cons.append("偏C式争公平口号")
    last = tail4[-1] if tail4 else ""
    if re.search(r"哼", last) and re.search(
        r"你.{0,4}(?:重刷|再刷|漱口|过关)|明天你|你等着",
        last,
    ):
        cons.append("末句哼完仍发指令，破功不干净")
    if re.search(r"算你厉害|你赢了|算你赢|你厉害", last):
        cons.append("末句认赢或甩狠，破功不干净")
    if len(tail4) >= 3 and "那不一样" in tail4[-3]:
        dodge = tail4[-3]
        if re.search(r"我是姐姐|我说了算", dodge) and not re.search(
            r"示范|泡沫|教学|吐泡沫|教你",
            dodge,
        ):
            cons.append("收束空甩身份，不好笑")
        if re.search(r"试味道|试甜|尝一下|帮你试|尝了|只尝|试一口", dodge) and re.search(
            r"试甜|试味道|帮你试|尝了|只尝|尝味道|甜不甜|试一口|确认味道",
            body_text,
        ):
            cons.append("收束借口复读中段，不好笑")
        if re.search(r"把关|负责|我说了算", dodge) and not re.search(
            r"样品|耗掉|泡沫|教学",
            dodge,
        ):
            cons.append("收束空甩身份，不好笑")
        if re.search(r"那不一样[，,]?\s*(我那是)?[…\.。]{0,3}\s*$", dodge):
            cons.append("收束空甩身份，不好笑")
    excuse_n = 0
    if re.search(
        r"试甜|试味道|帮你试|尝一下|尝得准|尝了|只尝|尝味道|甜不甜|"
        r"试一口|确认味道|咬一口就|知道甜|先试|算尝味|"
        r"看看熟|熟不熟|坏了没|有没有坏|是甜的|甜度|确认质量",
        body_text,
    ):
        excuse_n += 1
    if re.search(r"检查不算|检查样品|特地挑", body_text):
        excuse_n += 1
    if re.search(r"把关|资格|负责质量|检查员|有特权", body_text):
        excuse_n += 1
    if re.search(r"示范|教你吐|特批", body_text):
        excuse_n += 1
    if excuse_n >= 2:
        cons.append("中段多套免责借口叠罗汉")
    if re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉|芒果", "".join(lines)):
        if re.search(
            r"半成品|大家安全|新不新鲜|新鲜不新鲜|不新鲜|合格证书|专业方法|含三秒|"
            r"为了大家|品质检测|安全起见|确认甜度|确认质量|是甜的",
            body_text,
        ):
            cons.append("偷吃质检说明书注水，不好笑")
        if sum(1 for ln in lines if "洗手" in ln) >= 2:
            cons.append("偷吃质检说明书注水，不好笑")
        if sum(1 for ln in lines if "擦过" in ln) >= 2:
            cons.append("偷吃质检说明书注水，不好笑")
        if any(re.search(r"倒是说|你倒是|到底咽|你倒是说", ln) for ln in lines):
            cons.append("偷吃催进度，不好笑")
        if any(
            re.search(r"大颗|小的不用|容易检查|检查工作|检查过了|大的都检查", ln)
            for ln in lines
        ):
            cons.append("偷吃质检说明书注水，不好笑")
        if any(
            re.search(r"吐出来了.{0,6}(桌上|这里|那儿)|吐在桌上", ln)
            for ln in lines
        ):
            cons.append("偷吃咽下自相矛盾，不好笑")
        mid = lines[:-4] if len(lines) > 4 else lines
        mid_pairs = list(
            zip(
                (speakers or [""] * len(lines))[: len(mid)],
                mid,
                strict=False,
            )
        )
        sample_n = sum(
            1
            for sp, ln in mid_pairs
            if sp == "灿灿" and re.search(r"检查样品|特地挑", ln)
        )
        if sample_n >= 2:
            cons.append("偷吃检查样品复读，不好笑")
        if any(
            sp == "昭昭"
            and (
                re.search(r"这是检查样品|特地挑出来", ln)
                or (
                    "检查不算吃" in ln
                    and not re.search(r"你刚才说|你自己说|你不是说|你刚说", ln)
                )
            )
            for sp, ln in zip(speakers or [""] * len(lines), lines, strict=False)
        ):
            cons.append("偷吃角色错位，不好笑")
        if any(
            re.search(r"中间才准|边上不甜|比我拇指|挖的那勺", ln) for ln in lines
        ):
            cons.append("偷吃质检说明书注水，不好笑")
        bury_i = next(
            (i for i, ln in enumerate(lines) if "检查不算吃" in ln),
            None,
        )
        sister_i = next(
            (i for i, ln in enumerate(lines) if "我是姐姐" in ln),
            None,
        )
        last_i = next(
            (i for i, ln in enumerate(lines) if re.search(r"上次是上次|上次妈妈", ln)),
            None,
        )
        if sister_i is not None and sister_i < 4:
            cons.append("偷吃权威过早，不好笑")
        if bury_i is not None:
            anchors = [i for i in (sister_i, last_i) if i is not None]
            if anchors and bury_i < max(anchors):
                cons.append("偷吃埋句过早，不好笑")
        check_i = next(
            (
                i
                for i, ln in enumerate(lines)
                if re.search(r"检查样品|特地挑|检查不算吃", ln)
            ),
            None,
        )
        if check_i is not None:
            # 须灿灿真赖账（溅/手脏）；「擦过/那是果汁」不算
            cancan_dodge = any(
                (speakers[i] if speakers and i < len(speakers) else "") == "灿灿"
                and re.search(r"溅|手脏", lines[i])
                for i in range(check_i)
            )
            if not cancan_dodge:
                cons.append("偷吃缺赖账抬杠，不好笑")
        if sum(1 for ln in lines if re.search(r"[啦呀嘛]$", str(ln).rstrip())) >= 6:
            cons.append("偷吃语气词注水，不好笑")
        pairs = list(zip(speakers or [""] * len(lines), lines, strict=False))
        spit_i = next(
            (
                i
                for i, (sp, ln) in enumerate(pairs)
                if sp == "灿灿"
                and (
                    re.search(r"已经咽|咽下去了|看不了|吐不出来", ln)
                    or (
                        re.search(r"咽了", ln)
                        and "才算" not in ln
                        and "不咽" not in ln
                    )
                )
            ),
            None,
        )
        ask_spit = any(
            re.search(r"吐出来|吐给我看|吐出来看看", ln) for ln in lines
        )
        quote_indices = [
            i
            for i, (_sp, ln) in enumerate(pairs)
            if re.search(
                r"你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你刚说",
                ln,
            )
        ]
        quote_i = quote_indices[-1] if quote_indices else None
        if bury_i is not None and (
            spit_i is None
            or not ask_spit
            or (quote_i is not None and spit_i is not None and spit_i > quote_i)
        ):
            cons.append("偷吃缺咽下一锤，不好笑")
        if len(quote_indices) >= 2 or (
            quote_i is not None and quote_i < len(pairs) - 4
        ):
            cons.append("中段提前引话，不好笑")
        if spit_i is not None and quote_i is not None and quote_i - spit_i > 3:
            cons.append("咽下后质检说明书注水，不好笑")
    if re.search(r"反正我说了算|我说了算", "".join(tail4[-1:])):
        cons.append("末句仍嘴硬甩权，破功不干净")
    if re.search(r"刷牙|漱口|牙刷|吐水", "".join(lines)):
        fun_beat = bool(re.search(
            r"噗|一[、,，]二|才[一二两三四五六\d]+下|才刷.{0,4}下",
            "".join(lines),
        ))
        if not fun_beat:
            cons.append("刷牙缺可拍一锤声画（噗/数下就吐）")
    if re.search(r"刷牙|漱口|牙刷", "".join(lines)):
        quote_frags = [
            m.group(1)
            for line in tail4
            for m in _RE_DIRECT_QUOTE.finditer(line)
        ]
        hammer_hit = bool(re.search(
            r"才刷|就吐|就停|就漱|玩手机|泡沫|几下|二十秒|五十秒",
            body_text,
        ))
        if quote_frags and hammer_hit:
            joined_q = "".join(quote_frags)
            if (
                re.search(r"两分钟", joined_q)
                and not re.search(r"吐|停|连续|漱口|手", joined_q)
                and re.search(r"吐水|漱口|停手|连续", body_text)
            ):
                cons.append("收束未扣一锤（应引吐水/停手类原话）")
    tail4_speakers = speakers[-4:] if speakers and len(speakers) >= 4 else None
    if not _close_four_beat_complete(tail4, tail4_speakers):
        cons.append("末四拍不完整")
    return cons


# ── 好笑加分（A 类校准落地）──

# 一锤可拍动作/器物词：当场看见灿灿犯规的可见细节
# 物理类：数字+量词、嘴部动作、器物变化
# 知识类：书/图鉴/本子上的错误、算错写错、上次说过的错
_RE_HAMMER_COUNTABLE = re.compile(
    r"第[一二三四五六七八九十\d]+[口下个次步粒颗块片根条只]|"
    r"[一二三四五六七八九\d]+[口下个次步粒颗块片根条只]|"
    r"几[口下个次步粒颗块片根条只]|哪个数|算错|得数|"
    r"噗|咽下|咽了|吐出来|泡沫|腮帮|嘴角|牙签|汁水|果渣|"
    r"断了|碎了|洒了|溅|散了|滑了|掉了|塞进|鼓鼓|油乎|黏黏|"
    r"书上.{0,6}(?:写|印|说|画)|图鉴.{0,6}(?:写|印|说|画)|"
    r"百科.{0,6}(?:写|印|说|画)|本子上.{0,6}(?:写|印|画)|"
    r"印错|写错|记错|弄错|搞错|查了.{0,4}(?:说|写|是)|"
    r"翻到.{0,4}(?:页|写|说)|自己查|自己看|翻书|"
    r"上次也说|上次还说|上次说|你上次|明明写|明明说|"
    r"手机查|百度|搜了.{0,4}(?:说|写|是)",
)
_RE_HAMMER_EXPOSE = re.compile(
    r"(?:你看|你听|你闻|你摸|你尝|瞧|听这|看这|"
    r"你.*[自己也还就在].*[了着呢吧]|"
    r"那书上|那图鉴|那本子|你自己看|你自己查|"
    r"明明.{0,4}(?:写|说|印|是|有)|怎么.{0,4}(?:写|说|印|解释))",
)
_RE_CLOSING_GROUNDED_HAMMER = re.compile(
    r"(?:吐水|停手|咽下|咽了|吐出来|吧唧|系反|系错|散了|"
    r"断了|碎了|洒了|算错|写错|弹错|嚼|塞|噗|溅|掉了|滑了|"
    r"印错|记错|弄错|搞错|书上说|图鉴说|百科说|上次说|明明说|"
    r"自己说|查了|翻过|搜过)",
)


HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("末四拍不完整", 5),
    ("追问闭环模板复读", 5),
    ("偏C式争公平口号", 5),
    ("末句哼完仍发指令", 4),
    ("末句仍嘴硬甩权", 4),
    ("收束空甩身份", 5),
    ("收束借口复读中段", 5),
    ("中段多套免责借口叠罗汉", 6),
    ("质检说明书注水", 5),
    ("催进度", 4),
    ("咽下自相矛盾", 5),
    ("检查样品复读", 5),
    ("角色错位", 6),
    ("偷吃权威过早", 4),
    ("偷吃埋句过早", 5),
    ("偷吃缺赖账", 4),
    ("偷吃缺咽下一锤", 6),
    ("咽下后质检注水", 4),
    ("中段提前引话", 5),
    ("偷吃语气词注水", 4),
    ("刷牙缺可拍一锤声画", 6),
    ("收束未扣一锤", 6),
)


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    """A 类一锤场面分：中段有可拍/可核对的犯规细节。

    物理类（咽下/吐水/断了）+ 知识类（书上写错/上次说错/算错）均有效。
    有可数/可核细节+当场戳穿=5分，仅有可拍/可核细节=3分。
    """
    _ = text_has_hammer_beat
    n = len(lines)
    if n < 8:
        return 0, []

    mid = "".join(lines[max(6, n // 3) : max(8, n - 6)])
    mid_wide = "".join(lines[max(4, n // 4) : max(6, n - 4)])
    all_text = "".join(lines)

    has_countable = bool(_RE_HAMMER_COUNTABLE.search(mid_wide))
    has_expose = bool(_RE_HAMMER_EXPOSE.search(all_text))

    if has_countable and has_expose:
        return 5, ["有一锤场面"]
    elif has_countable:
        return 3, ["有可拍细节"]
    elif has_expose:
        return 2, ["有当场戳穿"]
    return 0, []


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """A 类末四拍好笑加分：引话扣一锤 + 那不一样有新借口 + 软破功落点。

    满分 13 分（引话扣锤4 + 那不一样新借口3 + 哪里不一样到位3 + 软破功甜3）。
    """
    n = len(lines)
    if not speakers or len(speakers) != n or n < 8:
        return 0, []

    tail4 = lines[-4:] if n >= 4 else lines
    tail4_text = "".join(tail4)
    points = 0
    pros: list[str] = []

    # 1. 引话扣一锤：收束引用的话须扣住一锤动作词（吐水/咽下/系反等），非空规矩
    if n >= 4:
        cite_line = lines[-4] if speakers[-4] == "昭昭" else (
            lines[-5] if n >= 5 and speakers[-5] == "昭昭" else ""
        )
        if cite_line and _RE_CLOSING_GROUNDED_HAMMER.search(cite_line):
            points += 4
            pros.append("引话扣一锤")
        elif cite_line and _RE_DIRECT_QUOTE.search(cite_line):
            points += 2
            pros.append("引话有出处")

    # 2. 那不一样有新借口（非空甩身份）
    if n >= 3 and speakers[-3] == "灿灿":
        bu_yi_yang = lines[-3]
        if "那不一样" in bu_yi_yang:
            # 有实质借口词（示范/教学/检样/开饭/样品/试吃/把关/特批）加分
            if re.search(
                r"示范|教学|检样|开饭|样品|试[吃尝]|把关|特批|检查|"
                r"不算|不停|例外|咽下|吐水|系法|交叉|嚼",
                bu_yi_yang,
            ):
                points += 3
                pros.append("那不一样有新借口")
            elif "我是姐姐" in bu_yi_yang or "我说了算" in bu_yi_yang:
                # 空甩身份不加分
                pass
            else:
                points += 1
                pros.append("那不一样有区分")

    # 3. 哪里不一样到位（全文仅此一处）
    if n >= 2 and speakers[-2] == "昭昭" and "哪里不一样" in lines[-2]:
        points += 3
        pros.append("哪里不一样收束到位")

    # 4. 软破功落点甜（给东西/认输 优于 干哼）
    if speakers[-1] == "灿灿":
        last = lines[-1]
        if re.search(r"给[你我他]|吃吧|玩吧|去吧|算你对|你赢了", last):
            points += 3
            pros.append("软破功落点甜")
        elif re.search(r"哼|行吧|算了|随便|好吧", last):
            points += 1
            pros.append("软破功收束")

    return points, pros
def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """A 类收束好笑尾段独立加分（待校准后补齐）。

    目标：末四拍（引话/那不一样/哪里不一样/破功）各有独立加权。
    """
    _ = lines, speakers
    # TODO: 另一台机器校准后，填入真实评分逻辑
    return 0, []
