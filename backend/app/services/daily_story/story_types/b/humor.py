"""B 类好笑维硬伤、末段加分与修订 hint。"""

from __future__ import annotations

import re

RE_ALLY = re.compile(
    r"一起|咱俩|别告诉|瞒着|瞒妈|约定|联手|暗号|分工|你望风|你放风|"
    r"放风|望风|说好了|盯门口|盯门|站门口|看门|放哨|盯紧|打掩护|"
    r"兜着|你盯|手快|别出声|别让妈|妈在|一人一半|一人一|拆包|拆包装|"
    r"你切|我拿|你拿|你望|我望|你负责|我负责|你动手|下手",
)
RE_BLAME = re.compile(
    r"都怪你|是你先|你答应|不是我的|你先|赖我|你不是说好|才不是我的",
)
RE_EXPOSED = re.compile(
    r"露馅|完了|糟糕|抓到了|听见了|看见了|妈妈|撞见|藏不住",
)
RE_PLAN_FAIL = re.compile(
    r"多拿|忘藏|说漏|掉了|洒了|露出来|忘了藏|袋口|碎|脚印|油渍|"
    r"响了|破了|更明显|鼓出来|撕|裂|滑|洒|掉|"
    r"卡住|卡死|摔开|摔了|滚到|滚进|散架|翻倒|掀翻|拽不",
)
RE_BLAME_MID = re.compile(r"都怪你|是你先|你答应|赖我|你还怪")
_A_STYLE_TAIL = re.compile(r"那不一样|哪里不一样|你刚才说|你自己说")
RE_MOM_PUNISH = re.compile(
    r"站好|过来|罚|不许|今晚|检讨|说清楚|墙角|罚站|别想吃|偷吃|拿的什么|"
    r"调皮|捣蛋|乱来|胡闹|惹事|闹腾|顽皮|淘气",
)
RE_DOOM = re.compile(r"完蛋|完了|糟糕|死定了|藏不住|露馅")
RE_REACT_ALT = re.compile(
    r"真倒霉|倒霉|惨了|糟了|惨喽|完犊子|死定了|这回完|这下完|惨了惨了",
)
RE_DOOM_CLUSTER = re.compile(r"完蛋|完了")
RE_PACT_DUTY = re.compile(
    r"望风|放风|暗号|分工|你拿|我盯|你拆|我望|别告诉|一人一半",
)
RE_CHAIN_ACTION = re.compile(
    r"掉|碎|滑|洒|蹭|捡|塞|压|挡|擦|摸|踩|响|破|油|印|鼓|露|咽|"
    r"卡|滚|摔|踢|掀|散|拽|翻|捅|戳|漏|黏",
)
RE_ABSURD_FIX = re.compile(
    r"鞋底|洒水|塞嘴里|靠垫|沙发垫|用脚|蹭碎|更糟|更明|别出声",
)
RE_PACT_CHATTER = re.compile(
    r"望风|盯着|快拿|赶紧|门口|咳嗽|别磨蹭|你看着",
)
RE_EMPTY_ARGUE = re.compile(
    r"你挡|我不挡|你笨|你慢|烦死了|凭什么",
)
RE_LANDING_GROUND = re.compile(
    r"藏不住|傻眼|愣住|愣住了|低头|不敢动|僵住|对视|一起完|咱俩完|"
    r"两个人都|妈都看见|一听就完|也完了|一起挨|一块儿完|咱俩全完|一起完蛋",
)
RE_STUBBORN_LAST = re.compile(r"哼|才不是|才不是我的主意")
RE_SIGNAL_PACT = re.compile(
    r"咳嗽两声|咳嗽一声|咳两声|咳一声|你就咳|咳我就|咳一声|暗号是|就咳嗽",
)
RE_SIGNAL_REF = re.compile(
    r"暗号没用|暗号没|咳嗽没用|咳给谁|咳什么咳|没咳|暗号失效",
)
RE_COUGH_LINE = re.compile(
    r"咳嗽|咳咳|咳太|咳给谁|咳什么|怎么咳|教我咳|假装咳嗽",
)
RE_DRY_DUTY_OPENING = re.compile(
    r"谁负责|谁望风|谁动手|谁来藏|谁来拿",
)
RE_VERBOSE_FREEZE = re.compile(
    r"怎么办|被抓住了|全完了|这下惨了|露馅了.*怎么办",
)
_SIBLING = frozenset({"昭昭", "灿灿"})

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺结盟约定", 5),
    ("联盟崩塌缺自保", 8),
    ("偏C式争公平", 5),
    ("中段甩锅拖沓", 8),
    ("走样连锁中甩锅打断", 7),
    ("收束缺权威落槌", 7),
    ("好笑缺越补越糟", 7),
    ("好笑空吵无场面", 6),
    ("甩锅不扣分工", 5),
    ("结盟分工复读", 6),
    ("B收束缺落槌定格", 13),
    ("B落槌定格句式重复", 4),
    ("B定格后多余对白", 12),
    ("B连锁也又还缺前句", 12),
    ("B也字过多", 12),
    ("B写实流血不宜", 8),
    ("B甩锅提暗号无前文约定", 8),
    ("B咳嗽暗号拖沓", 10),
    ("B定格啰嗦", 10),
    ("B语气垫字", 12),
)


RE_FREEZE_REACT = re.compile(
    r"完蛋|完了|糟糕|死定了|死定|真倒霉|倒霉|惨了|糟了|惨喽|"
    r"被发现|露馅了|露馅|"
    r"傻眼|愣住|僵住|"
    r"妈都看见|看见了",
)
RE_FREEZE_SILENT = re.compile(
    r"低头不敢动|一动不敢动|傻眼对视|对视不敢|僵住不敢说话",
)
RE_FREEZE_SIDE_DING = re.compile(r"死定了|死定")
RE_BLEED_CONTENT = re.compile(
    r"流血|出血|鲜血|血滴|血渗|血印|止血|还在流血|用嘴吸|创可贴|"
    r"扎手|扎破|扎出血|割破|割到|划破|划伤|擦破|磕破|"
    r"手疼|手指疼|脚疼|受伤|被扎",
)
# 无意义语气垫字后缀（对齐 E 类；B 额外加真的呀/好不好）：
# 连锁/结盟里句尾叠「了呢了呀/嘛了呀/好不好/真的呀」= 注水，一句实词收尾才顺。
RE_GARBAGE_FILLER = re.compile(
    r"[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}$|对不对呀真的|"
    r"了呢[了呀]|了呀[呢]|嘛了[呀]|了呢呀|"
    r"(?:了呢|了呀|嘛了|呢吧|呀呢|呢嘛)$|"
    r"真的呀|好不好$|"
    r"[^\s，。！？!?,]{4,}你听着[。！?]?$",
)


def _sibling_landing_react(line: str) -> bool:
    return bool(
        RE_FREEZE_REACT.search(line)
        or RE_LANDING_GROUND.search(line)
    )


def _punish_freeze_react(line: str) -> bool:
    """惩罚令后定格反应（不含甩锅/哼）。"""
    return bool(RE_FREEZE_REACT.search(line))


def _landing_doom_lines_repeat(lines: list[str]) -> bool:
    doomish = [ln for ln in lines if RE_DOOM_CLUSTER.search(ln)]
    return len(doomish) >= 3


def _freeze_lines_issues(react_lines: list[str]) -> str | None:
    if not react_lines:
        return None
    if any(RE_FREEZE_SILENT.search(ln) for ln in react_lines):
        return "定格须说话勿动作描写"
    if sum(1 for ln in react_lines if RE_FREEZE_SIDE_DING.search(ln)) >= 3:
        return "死定了句式重复"
    if sum(1 for ln in react_lines if RE_DOOM_CLUSTER.search(ln)) >= 3:
        return "完蛋完了句式重复"
    return None


def _find_last_mom_punish(
    lines: list[str],
    speakers: list[str],
    *,
    tail_window: int = 12,
) -> int | None:
    n = len(lines)
    for i in range(n - 1, max(-1, n - tail_window), -1):
        if speakers[i] == "妈妈" and RE_MOM_PUNISH.search(lines[i]):
            return i
    return None


def _trim_stubborn_tail(
    post_lines: list[str],
    post_speakers: list[str],
) -> tuple[list[str], list[str]]:
    if (
        post_lines
        and post_speakers
        and post_speakers[-1] in _SIBLING
        and RE_STUBBORN_LAST.search(post_lines[-1])
    ):
        return post_lines[:-1], post_speakers[:-1]
    return post_lines, post_speakers


def _lines_before_last_punish(
    lines: list[str],
    speakers: list[str],
) -> tuple[list[str], int | None]:
    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None:
        return lines, None
    return lines[:punish_i], punish_i


def analyze_pre_punish_self_preservation(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """段 4：妈妈惩罚令之前须有互甩自保（联盟崩塌）。"""
    if not speakers or len(speakers) != len(lines) or len(lines) < 8:
        return False, ""

    pre_lines, punish_i = _lines_before_last_punish(lines, speakers)
    if punish_i is None:
        return False, ""

    tail_pre = pre_lines[-10:] if len(pre_lines) >= 10 else pre_lines
    if RE_BLAME.search("".join(tail_pre)):
        return False, ""
    return True, "妈妈惩罚令前缺自保甩锅"


def analyze_post_freeze_bloat(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """段 5 定格之后不应再有对白（甩锅/哼均算多余）。"""
    if not speakers or len(speakers) != len(lines):
        return False, ""

    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None:
        return False, ""

    post_lines = lines[punish_i + 1 :]
    post_speakers = speakers[punish_i + 1 :]
    if not post_lines:
        return False, ""

    freeze_end = 0
    for i, (sp, ln) in enumerate(zip(post_speakers, post_lines)):
        if sp in _SIBLING and _punish_freeze_react(ln):
            freeze_end = i + 1
            continue
        if sp in _SIBLING:
            break

    if freeze_end == 0:
        return False, ""

    extra = post_lines[freeze_end:]
    if not extra:
        return False, ""

    extra_text = "".join(extra)
    # 放宽：定格后允许一句 ≤10 字的纯收尾（非甩锅/非嘴硬）
    if (
        len(extra) == 1
        and len(extra[0]) <= 10
        and not RE_BLAME.search(extra[0])
        and not RE_STUBBORN_LAST.search(extra[0])
    ):
        return False, ""
    if RE_BLAME.search(extra_text):
        return True, "定格后仍甩锅"
    if RE_STUBBORN_LAST.search(extra_text):
        return True, "定格后仍嘴硬"
    return True, "定格后多余对白"


def analyze_freeze_after_punish(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """返回 (是否缺落槌定格, 标签)。定格=惩罚令后姐弟同框反应，可戛然而止收束。"""
    n = len(lines)
    if n < 6 or not speakers or len(speakers) != n:
        return False, ""

    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None:
        return False, ""

    post_lines = lines[punish_i + 1 :]
    post_speakers = speakers[punish_i + 1 :]
    if not post_lines:
        return True, "惩罚令后无姐弟反应"

    post_doom_speakers = {
        sp
        for sp, ln in zip(post_speakers, post_lines)
        if sp in _SIBLING and _punish_freeze_react(ln)
    }
    post_blame_n = sum(
        1
        for sp, ln in zip(post_speakers, post_lines)
        if sp in _SIBLING and RE_BLAME.search(ln)
    )
    if len(post_doom_speakers) >= 2:
        return False, ""

    if len(post_doom_speakers) == 1:
        return True, "仅单人定格缺同框"

    if post_blame_n > 0:
        pre_doom = any(
            RE_DOOM.search(ln)
            for ln in lines[max(0, punish_i - 4) : punish_i]
        )
        if pre_doom:
            return True, "完蛋写在惩罚前缺定格"
        return True, "惩罚后无定格直接甩锅"

    return True, "惩罚后缺定格反应"


def analyze_punish_landing(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """兼容旧名；见 analyze_freeze_after_punish。"""
    return analyze_freeze_after_punish(lines, speakers)


def analyze_bottom_punchline(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """兼容旧名；B 类不再要求末句底包袱，改查定格后是否多余。"""
    return analyze_post_freeze_bloat(lines, speakers)


def is_weak_freeze_after_punish(
    lines: list[str],
    speakers: list[str] | None,
) -> bool:
    return analyze_freeze_after_punish(lines, speakers)[0]


def is_weak_bottom_punchline(
    lines: list[str],
    speakers: list[str] | None,
) -> bool:
    return analyze_post_freeze_bloat(lines, speakers)[0]


def is_weak_punish_landing(
    lines: list[str],
    speakers: list[str] | None,
) -> bool:
    return is_weak_freeze_after_punish(lines, speakers)


def freeze_revision_hint(tag: str) -> str:
    if tag == "惩罚后无定格直接甩锅":
        return (
            "妈妈愤怒短令后先写定格（从词池抽两句不同反应），"
            "互甩应写在惩罚令之前的段4，禁止站好后下一句就「都怪你」。"
        )
    if tag == "完蛋写在惩罚前缺定格":
        return (
            "露馅慌张可说「完了」，但惩罚令后须再写定格一拍，然后戛然而止。"
        )
    if tag == "仅单人定格缺同框":
        return (
            "惩罚令后须俩人都有定格反应，各用不同句式（从词池抽两句），"
            "须开口说话，勿低头不敢动。"
        )
    if "句式重复" in tag or "落槌定格句式重复" in tag:
        if tag == "定格须说话勿动作描写":
            return "定格须姐弟开口（被发现了/这下死定了等），勿写低头不敢动。"
        if tag == "死定了句式重复":
            return "定格两句勿都用死定了；死定了/完了类词各最多出现一次。"
        if tag == "完蛋完了句式重复":
            return "定格两句勿都用完蛋/完了；从词池各抽不同句式。"
        return (
            "定格两句从词池各抽不同句式（被发现了/露馅了/惨了/真倒霉/"
            "这下死定了等）；死定了、完了类词各最多用一次。"
        )
    return (
        "段5：妈妈短令→姐弟定格（完蛋了+真倒霉）即收；"
        "笑料写在段2/3连锁与段4互甩，勿在定格后再写。"
    )


def bloat_revision_hint(tag: str) -> str:
    if "甩锅" in tag:
        return "互甩锅写在妈妈惩罚令之前（段4自保）；定格后禁止都怪你/是你先。"
    if "嘴硬" in tag:
        return "禁止定格后再写哼/才不是；末句停在完蛋了+真倒霉即可。"
    return "定格后戛然而止，勿再补任何姐弟对白。"


def bottom_revision_hint(tag: str) -> str:
    return bloat_revision_hint(tag)


def landing_revision_hint(tag: str) -> str:
    return freeze_revision_hint(tag)


RE_CHAIN_STEM = re.compile(
    r"踩|滑|掉|洒|蹭|捡|塞|压|破|碎|露|响|黏|脏|印|泼|抹|擦|踢|冲|流|倒|崩|溅|鼓|"
    r"卡|滚|摔|掀|散|拽|翻|捅|戳|漏",
)
RE_ANAPHORA_SKIP = re.compile(
    r"还是|还好|还有|还行|还没|还不错|说不定|"
    r"妈还在|妈妈在|别告诉|你说好|说好了|最好|越",
)
RE_ANAPHORA_MARK = re.compile(
    r"我也|你又|他又|她又|"
    r"又(?!错|好|是|行|可以|来|给|不一|没说|没听|没看见|怎么样)|"
    r"还(?!是|有|行|好|可以|没|不错|不如|算|得|没呢|没听|没看见|没弄)",
)


def _chain_zone_bounds(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[int, int]:
    n = len(lines)
    start = next(
        (i for i, ln in enumerate(lines) if RE_PLAN_FAIL.search(ln)),
        None,
    )
    if start is None:
        start = next(
            (i for i, ln in enumerate(lines) if RE_CHAIN_ACTION.search(ln)),
            min(4, n),
        )
    end = n
    if speakers and len(speakers) == n:
        punish_i = _find_last_mom_punish(lines, speakers)
        if punish_i is not None:
            end = punish_i
        else:
            mom_i = next(
                (i for i, sp in enumerate(speakers) if sp == "妈妈"),
                n,
            )
            end = min(end, mom_i)
    while end > start and RE_BLAME_MID.search(lines[end - 1]):
        end -= 1
    return start, end


def _stems_in(text: str) -> set[str]:
    return set(RE_CHAIN_STEM.findall(text))


def _chain_anaphora_tag(line: str, prev2: str) -> str | None:
    if RE_ANAPHORA_SKIP.search(line):
        return None
    if not RE_ANAPHORA_MARK.search(line):
        return None

    if "我也" in line:
        tail = line.split("我也", 1)[-1]
        stems = _stems_in(tail)
        if not stems and tail.strip():
            stems = _stems_in(tail) or (
                {tail.strip()[0]} if tail.strip() else set()
            )
        if stems and not any(s in prev2 for s in stems):
            return "我也缺前句动作"

    for m in re.finditer(r"又([^，。！？]{1,10})", line):
        frag = m.group(1)
        if re.match(r"^[错好是不行可没]", frag):
            continue
        stems = _stems_in(frag)
        if stems and not any(s in prev2 for s in stems):
            # 「又」常接新意外（又挤碎/又洒了）；前文已有连锁动作则放过
            if RE_CHAIN_ACTION.search(prev2) or RE_PLAN_FAIL.search(prev2):
                continue
            return "又字缺前句动作"

    for m in re.finditer(r"还([^，。！？]{1,10})", line):
        frag = m.group(1)
        if re.match(r"^[是有好行可没不]", frag):
            continue
        stems = _stems_in(frag)
        if stems and not any(s in prev2 for s in stems):
            # 「还」常接转折/意外（还咧嘴笑/还带响）；连锁中已动作则放过
            if RE_CHAIN_ACTION.search(prev2) or RE_PLAN_FAIL.search(prev2):
                continue
            return "还字缺前句动作"

    return None


def _anaphora_scan_bounds(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[int, int]:
    """正文扫描上界：结盟段 + 连锁段，止于妈妈惩罚令前（不含甩锅尾）。"""
    n = len(lines)
    end = n
    if speakers and len(speakers) == n:
        punish_i = _find_last_mom_punish(lines, speakers)
        if punish_i is not None:
            end = punish_i
        else:
            mom_i = next(
                (i for i, sp in enumerate(speakers) if sp == "妈妈"),
                n,
            )
            end = min(end, mom_i)
    while end > 0 and RE_BLAME_MID.search(lines[end - 1]):
        end -= 1
    return 0, end


def collect_chain_anaphora_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    start, end = _anaphora_scan_bounds(lines, speakers)
    if end - start < 2:
        return []
    for i in range(start, end):
        # 「我也」仍看近邻；「又/还」允许扣本连锁段前文（同动作再现）
        if "又" in lines[i] or (
            "还" in lines[i] and "我也" not in lines[i]
        ):
            prev = "".join(lines[start:i])
        else:
            prev = "".join(lines[max(0, i - 2) : i])
        tag = _chain_anaphora_tag(lines[i], prev)
        if tag:
            zone = "结盟" if i < 6 else "连锁"
            return [f"B连锁也又还缺前句（{tag}·{zone}）"]
    return []


def collect_ye_overuse_issues(
    lines: list[str],
    speakers: list[str] | None,
    *,
    max_ye: int = 3,
) -> list[str]:
    """全篇「也」宜少；结盟段尤忌凭空「我也…」。观感层允许到 3，超过再压分。"""
    _, end = _anaphora_scan_bounds(lines, speakers)
    if end < 4:
        return []
    body = "".join(lines[:end])
    ye_count = body.count("也")
    if ye_count > max_ye:
        return [f"B也字过多（{ye_count}处，宜≤{max_ye}）"]
    return []


def chain_anaphora_revision_hint(tag: str) -> str:
    if tag == "我也缺前句动作":
        return (
            "优先去掉「也」：结盟用「想吃！」勿写「我也想吃」；"
            "连锁如「我不敢用手捡」；"
            "或前句先写「用手捡？」再写「我也不敢捡」。"
        )
    if tag == "又字缺前句动作":
        return "「又…」须前句已写过同类意外；如先洒了再写「又洒了」。"
    if tag == "还字缺前句动作":
        return "「还…」须前句已写过该动作；勿凭空「还在漏」。"
    return (
        "连锁「我也/又/还」须扣前 1–2 句已有动作，"
        "一句接一句，勿凭空续接。"
    )


def _longest_chain_run(lines: list[str], pattern: re.Pattern[str]) -> int:
    best = 0
    cur = 0
    for ln in lines:
        if pattern.search(ln):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _freeze_line_verbose(line: str) -> bool:
    text = (line or "").strip()
    if len(text) > 14:
        return True
    if RE_VERBOSE_FREEZE.search(text):
        return True
    doom_hits = sum(
        1 for m in ("完了", "完蛋", "惨了", "露馅", "倒霉") if m in text
    )
    return doom_hits >= 2


def collect_signal_and_freeze_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    alliance = "".join(lines[: min(6, n)])
    punish_i = (
        _find_last_mom_punish(lines, speakers)
        if speakers and len(speakers) == n
        else None
    )
    blame_end = punish_i if punish_i is not None else max(4, n - 2)
    blame_zone = "".join(lines[4:blame_end]) if blame_end > 4 else ""
    if RE_SIGNAL_REF.search(blame_zone) and not RE_SIGNAL_PACT.search(alliance):
        cons.append("B甩锅提暗号无前文约定")

    cough_n = sum(1 for ln in lines if RE_COUGH_LINE.search(ln))
    if cough_n >= 2:
        cons.append("B咳嗽暗号拖沓")

    if not speakers or len(speakers) != n:
        return cons
    if punish_i is None:
        return cons
    for sp, ln in zip(speakers[punish_i + 1 :], lines[punish_i + 1 :]):
        if sp in _SIBLING and _punish_freeze_react(ln) and _freeze_line_verbose(ln):
            cons.append("B定格啰嗦")
            break
    return cons


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    head6 = "".join(lines[:6])
    head8 = "".join(lines[:8])
    tail6 = "".join(lines[-6:])
    tail4 = "".join(lines[-4:])
    tail8 = "".join(lines[-8:]) if n >= 8 else "".join(lines)
    body = lines[:-6] if n > 6 else lines[:-1]
    body_text = "".join(body)

    if _A_STYLE_TAIL.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏A式末四拍")

    if not RE_ALLY.search(head6) and not RE_ALLY.search("".join(lines[: n // 3])):
        cons.append("B缺结盟约定")

    if RE_DRY_DUTY_OPENING.search(head6):
        if not re.search(r"别告诉|瞒|偷吃|藏起|藏好|快拿|快藏|别让妈|妈在", head6):
            cons.append("B开场空谈谁负责，未点名同盟要瞒什么")

    if RE_EXPOSED.search(tail4):
        pre_weak, pre_tag = analyze_pre_punish_self_preservation(lines, speakers)
        if pre_weak:
            cons.append(
                "B联盟崩塌缺自保"
                + (f"（{pre_tag}）" if pre_tag else ""),
            )

    body_pre = "".join(lines[: max(0, n - 8)])
    if body_pre.count("不公平") >= 2 and not RE_ALLY.search(head6):
        cons.append("B偏C式争公平口号")

    if RE_BOOMERANG_RULE.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏回旋镖非甩锅")

    body_mid = lines[6 : max(6, n - 8)]
    blame_mid = sum(1 for ln in body_mid if RE_BLAME_MID.search(ln))
    if blame_mid >= 4:
        cons.append("B中段甩锅拖沓")

    chain_zone = lines[6 : min(n - 6, 20)]
    fail_i = next(
        (i for i, ln in enumerate(chain_zone) if RE_PLAN_FAIL.search(ln)),
        None,
    )
    if fail_i is not None:
        chain_slice = chain_zone[fail_i : fail_i + 6]
        if any(RE_BLAME_MID.search(ln) for ln in chain_slice):
            cons.append("B走样连锁中甩锅打断")

    cons.extend(collect_chain_anaphora_issues(lines, speakers))
    cons.extend(collect_ye_overuse_issues(lines, speakers))
    cons.extend(collect_signal_and_freeze_issues(lines, speakers))

    mid_chain = body[1:] if len(body) > 1 else body
    chain_run = _longest_chain_run(mid_chain, RE_CHAIN_ACTION)
    fail_hits = sum(1 for ln in mid_chain if RE_PLAN_FAIL.search(ln))
    if chain_run < 3 and fail_hits < 2:
        cons.append("B好笑缺越补越糟连锁")

    empty_argue = sum(1 for ln in body_mid if RE_EMPTY_ARGUE.search(ln))
    if empty_argue >= 3 and chain_run < 3:
        cons.append("B好笑空吵无场面")

    blame_lines = [ln for ln in body_mid if RE_BLAME_MID.search(ln)]
    if blame_lines and RE_PACT_DUTY.search(head8):
        if not any(RE_PACT_DUTY.search(ln) for ln in blame_lines):
            cons.append("B甩锅不扣分工")

    if len(head8) > 80 and not RE_PLAN_FAIL.search("".join(lines[6:12])):
        if head8.count("不许") + head8.count("规矩") >= 2:
            cons.append("B同盟严肃说明书不好笑")

    pact_chatter = sum(1 for ln in lines[:14] if RE_PACT_CHATTER.search(ln))
    if pact_chatter >= 5:
        cons.append("B结盟分工复读拖沓")

    doom_i = next((i for i, ln in enumerate(lines) if RE_DOOM.search(ln)), None)
    punish_i = _find_last_mom_punish(lines, speakers) if speakers else None
    if (
        doom_i is not None
        and punish_i is not None
        and doom_i > punish_i
        and doom_i < n - 1
    ):
        tail_blame = sum(
            1 for ln in lines[doom_i + 1 :] if RE_BLAME_MID.search(ln)
        )
        if tail_blame >= 2:
            cons.append("B定格后多余对白")

    mom_late = bool(
        speakers
        and len(speakers) == n
        and any(speakers[i] == "妈妈" for i in range(max(0, n - 8), n))
    )
    if mom_late or RE_EXPOSED.search(tail8):
        if not RE_MOM_PUNISH.search(tail8) or not RE_DOOM.search(tail8):
            cons.append("B收束缺权威落槌")

    if is_weak_freeze_after_punish(lines, speakers):
        _, freeze_tag = analyze_freeze_after_punish(lines, speakers)
        cons.append(
            "B收束缺落槌定格"
            + (f"（{freeze_tag}）" if freeze_tag else ""),
        )

    bloat, bloat_tag = analyze_post_freeze_bloat(lines, speakers)
    if bloat:
        cons.append(
            "B定格后多余对白"
            + (f"（{bloat_tag}）" if bloat_tag else ""),
        )

    if speakers and len(speakers) == n:
        punish_i = _find_last_mom_punish(lines, speakers)
        if punish_i is not None:
            post_lines = lines[punish_i + 1 :]
            post_speakers = speakers[punish_i + 1 :]
            react_lines = [
                ln
                for sp, ln in zip(post_speakers, post_lines)
                if sp in _SIBLING and _punish_freeze_react(ln)
            ]
            if freeze_tag := _freeze_lines_issues(react_lines):
                cons.append(
                    "B落槌定格句式重复"
                    + (f"（{freeze_tag}）" if freeze_tag else ""),
                )
            elif _landing_doom_lines_repeat(react_lines):
                cons.append("B落槌定格句式重复")

    if RE_BLEED_CONTENT.search(body_text):
        cons.append("B写实流血不宜")

    for ln in lines:
        if RE_GARBAGE_FILLER.search(ln):
            cons.append("B语气垫字（句尾叠了呢了呀/好不好/真的呀等）")
            break

    return cons


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    n = len(lines)
    body = lines[:-6] if n > 6 else lines[:-1]
    tail8 = "".join(lines[-8:]) if n >= 8 else "".join(lines)
    weak_freeze = is_weak_freeze_after_punish(lines, speakers)
    has_bloat = analyze_post_freeze_bloat(lines, speakers)[0]

    points = 0
    pros: list[str] = []

    mid_chain = body[1:] if len(body) > 1 else body
    chain_run = _longest_chain_run(mid_chain, RE_CHAIN_ACTION)
    if chain_run >= 4:
        points += 6
        pros.append("越补越糟连锁好笑")
    elif chain_run >= 3:
        points += 4
        pros.append("走样连锁好笑")

    absurd_n = sum(1 for ln in mid_chain if RE_ABSURD_FIX.search(ln))
    if absurd_n >= 2:
        points += 3
        pros.append("荒谬补救好笑")

    pre_lines, punish_i = (
        _lines_before_last_punish(lines, speakers)
        if speakers
        else (lines, None)
    )
    if punish_i is not None:
        tail_pre = pre_lines[-8:] if len(pre_lines) >= 8 else pre_lines
        if RE_BLAME.search("".join(tail_pre)):
            points += 3
            pros.append("联盟自保好笑")

    if (
        RE_MOM_PUNISH.search(tail8)
        and RE_DOOM.search(tail8)
        and not weak_freeze
        and not has_bloat
    ):
        points += 4
        pros.append("定格戛然而止好笑")
    elif (
        RE_MOM_PUNISH.search(tail8)
        and not weak_freeze
        and not has_bloat
    ):
        points += 2
        pros.append("落槌定格好笑")

    if RE_ALLY.search("".join(lines[: max(1, n // 4)])) and RE_PLAN_FAIL.search(
        "".join(body),
    ):
        points += 1
        pros.append("同盟翻车好笑")

    return points, pros


def humor_revision_hint(issue: str) -> str | None:
    if "缺结盟" in issue:
        return (
            f"【好笑·B】{issue}。"
            "前 6 句姐弟亲口约定分工或暗号（望风/下手/别告诉妈），扣主题实物。"
        )
    if "缺互甩" in issue or "联盟崩塌" in issue or "自保" in issue:
        return (
            f"【好笑·B】{issue}。"
            "段4：连锁崩后、妈妈惩罚令前互甩 1–2 句，扣同盟分工。"
        )
    if "偏A" in issue:
        return (
            f"【好笑·B】{issue}。"
            "收束用互甩锅+一起露馅+末句嘴硬推给对方；"
            "勿「那不一样/哪里不一样」四连拍。"
        )
    if "偏C" in issue or "回旋镖" in issue:
        return (
            f"【好笑·B】{issue}。"
            "主线是同盟裂了互推，不是争公平赛规或回旋镖扣原话。"
        )
    if "拖沓" in issue or "空吵" in issue or "复读" in issue or "过长" in issue:
        return (
            f"【好笑·B】{issue}。"
            "删口头互怼；结盟分工说清一次即进连锁；"
            "段5定格后勿再写对白。"
        )
    if "定格后" in issue or "多余对白" in issue:
        tag = ""
        if "（" in issue and "）" in issue:
            tag = issue.split("（", 1)[-1].rstrip("）")
        return f"【好笑·B】{issue}。" + bloat_revision_hint(tag)
    if "连锁" in issue and "好笑" not in issue and "也又还" not in issue:
        return (
            f"【好笑·B】{issue}。"
            "连锁期间只写动作与慌张，勿插入都怪你。"
        )
    if "也又还缺前句" in issue:
        tag = ""
        if "（" in issue and "）" in issue:
            tag = issue.split("（", 1)[-1].rstrip("）")
            if "·" in tag:
                tag = tag.split("·", 1)[0]
        return f"【好笑·B】{issue}。" + chain_anaphora_revision_hint(tag)
    if "也字过多" in issue:
        return (
            f"【好笑·B】{issue}。"
            "全篇少用「也」（宜≤2处）；结盟同意用「想吃！」「好！」；"
            "并列意外直接说「蛋糕掉了一块」，勿写「蛋糕也掉了一块」。"
        )
    if "暗号无前文" in issue:
        return (
            f"【好笑·B】{issue}。"
            "结盟没约定咳嗽/暗号就别写「暗号没用」；甩锅扣望风/下手/谁弄洒。"
        )
    if "咳嗽暗号拖沓" in issue:
        return (
            f"【好笑·B】{issue}。"
            "默认不用咳嗽暗号；没约定不写，约定了也全篇≤2句，删中段讨论怎么咳。"
        )
    if "空谈谁负责" in issue:
        return (
            f"【好笑·B】{issue}。"
            "开场直接点名一起瞒妈妈做什么，并顺手下分工；"
            "别两句都在问谁负责望风。"
        )
    if "定格啰嗦" in issue:
        return (
            f"【好笑·B】{issue}。"
            "惩罚令后定格各一句短反应（被发现了/这下死定了），勿叠「怎么办全完了」。"
        )
    if "越补越糟" in issue or "说明书" in issue:
        return (
            f"【好笑·B】{issue}。"
            "结盟≤4句后立刻进段2/3：连续≥4句每句都有新意外动作"
            "（掉/卡/滚/摔/踢/掀/洒/塞），少写「那怎么办」空慌；"
            "补救须立刻造成下一意外（用脚踢→更散/拿扫把→更响）。"
        )
    if "流血" in issue:
        return (
            f"【好笑·B】{issue}。"
            "勿写实流血/止血/创可贴；可说怕扎到不敢动、不敢捡、不敢挪脚。"
        )
    if "落槌定格" in issue or "句式重复" in issue:
        tag = ""
        if "（" in issue and "）" in issue:
            tag = issue.split("（", 1)[-1].rstrip("）")
        return f"【好笑·B】{issue}。" + freeze_revision_hint(tag)
    if "权威落槌" in issue:
        return (
            f"【好笑·B】{issue}。"
            "段5：妈妈愤怒短令（你俩站好）+姐弟定格，隐喻受罚即可。"
        )
    if "分工" in issue:
        return (
            f"【好笑·B】{issue}。"
            "甩锅须扣望风/暗号/谁多拿：「都怪你没咳嗽」「是你让我换那片」。"
        )
    if any(k in issue for k in ("好笑", "幽默", "不足")):
        return (
            f"【好笑·B】{issue}。"
            "段2/3写 3–5 句越补越糟连锁；段4惩罚令前互甩自保；"
            "段5妈妈短令→定格（完蛋了+真倒霉）戛然而止。"
        )
    if "语气垫字" in issue:
        return (
            f"【好笑·B】{issue}。"
            "删句尾「了呢了呀/嘛了呀/好不好/真的呀/了你听」等垫字，"
            "每句以实词收尾（如「奶油蹭你裤腿了！」而非「奶油蹭你裤腿了呢了呀」）。"
        )
    from app.services.daily_story.story_types.b.facts import fact_revision_hint
    from app.services.daily_story.story_types.b.opening import opening_revision_hint

    return fact_revision_hint(issue) or opening_revision_hint(issue)
