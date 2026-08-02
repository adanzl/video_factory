"""D 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)

RE_LITERAL = re.compile(
    r"照做|按你说的|照你说的|你不是说|字面|按规矩|你让我|你说要|"
    r"你说[^，。！？]{1,8}，?我就|我按你|你叫我|你要我|我照你",
)
RE_MESS = re.compile(
    r"掉了|滑落|滑掉|洒|弄乱|乱了|乱成|全乱|坏了|打不开|饿着|够不着|弄翻|摔|"
    r"倒了|全掉|洒一地|堆塌|滚了一地|散架|全散|哗啦|晃成|塌了|垮了|"
    r"解不开|勒|死结|死疙瘩|大马趴|溢|变形|"
    r"流|淌|泡|淹|漫|漏|渗|满|皱|鼓|肿|挤|碎|破|断|歪|"
    r"泼|甩|滴水|滴到|滴在|湿透|水痕|水渍|水印|"
    r"[削剪切磨啃抠]没|只剩|就剩|快没了|小一圈|露出来|[削切剪磨啃]成",
)
# 定位「一锤搞砸」句：勿把开场「乱七八糟」当成后果
_RE_MESS_BEAT = re.compile(
    r"倒了|掉了|全掉|掉地上|洒|滑落|滑掉|堆塌|解不开|死结|溢|"
    r"弄翻|全乱|变形了|夹变形|撑变形|"
    r"[削剪切磨啃抠]没|只剩|就剩|露出来",
)
# 破规动作认「方式」不认具体动词：我来X/我自己X/用力X/一把X 通用；
# 另认「自我违规宣言」：我不X了 / 直接X行了吧（叮嘱方亲手违反自己的规矩）
RE_FIX = re.compile(
    r"我来[^，。！？]{1,3}|我自己[^，。！？]{1,3}|我解开|我抠|我擦|"
    r"指甲抠|抠进去|拆平|掰开|掰掉|压平|拍平|"
    r"给你解|帮你解|赶紧解|赶紧拆|得解|去解|"
    r"只好|没办法|用力[^，。！？]{1,3}|夹紧|夹得?更?紧|"
    r"擦地|抹布|扫进|抓进|抓起|一把抓|猛抓|扒拉|一把[^，。！？]{1,2}|"
    r"上手[^，。！？]{0,4}[推塞扫压倒]|直接[^，。！？]{1,8}[推塞扫压倒]|"
    r"(?:呼啦|哗啦)[^，。！？]{0,3}[推塞扫压倒]|"
    r"我不[^，。！？]{1,6}了|直接[^，。！？]{1,6}(?:行了吧|得了|算了)|"
    # 水类主题的破规补救动作（浇花/擦桌水战等）：
    r"抢[过]|往[^，。！？]{0,4}泼|泼(?:掉|出去|过来)|端起[^，。！？]{0,4}|舀[^，。！？]{0,2}水|"
    # 拢/托/接/端/兜/抱 类「上手收拾」破规（叠衣拢塔、端走壶、兜住漏的等）：
    r"拢住|扶住|托住|接住|端走|端起来|拿走|抱走|抱进|兜住|"
    r"(?:两手|双手)[^，。！？]{0,4}(?:拢|抓|抱|托|端|压|按|扶|挡|拍|兜)",
)
# 收束回旋镖：勿用共享「你说的」，会误伤「按你说的」字面句
RE_BOOM_CLOSE = re.compile(
    r"你自己说|你刚才说|你刚说|你现在也|你也碰了|你也动了|"
    r"你[^，。！？]{0,4}也破",
)
# 回旋镖「点破当场矛盾」的特征：须指出她此刻的破规动作
RE_BOOM_POINT = re.compile(
    r"上手|来解|又解|现在又|你却|自己却|自己倒|你现在也|怎么现在|现在你|"
    r"大手|一挥|猛|全推|塞进|呼啦|[推塞扫压倒]",
)
_A_STYLE = re.compile(r"那不一样.*哪里不一样|哪里不一样.*都是听")
_EMPTY_DEBATE = re.compile(r"谁对谁错|到底谁有理|你赢了|我不听你的了")
# 叮嘱方搞砸前批准了执行方的做法 → 后果成了她自己的方案失败，笑点作废
_RE_PREAPPROVE = re.compile(
    r"可以啊|行啊，?你|就那样|没错，?就|你试一?试|你试试吧|对，?就这样|这样就行|"
    r"不错|挺好|对了就|这样就对|你这样行",
)
# 执行方句句征求同意 = 没有「闷头字面做」的反差
_RE_ASK_PERMIT = re.compile(r"好不好|行不行|可以吗|对吧|行吗")
# 搞砸前灿灿拆穿/纠正字面误解 → 意外感没了
_RE_SPOIL_LITERAL = re.compile(
    r"不是让你|我是让你|我让你.{0,8}不是|要平放|别往高|别垒|别堆高|"
    r"别码高|你理解错|我说的是|我是说|"
    r"你.{0,8}地上.{0,14}干(?:什么|嘛)|"
    r"你[^，。！？]{0,8}(?:码|垒|叠|堆|搭|摞|绕|缠|卷)[^，。！？]{0,10}(?:干嘛|干什么)|"
    r"要直接放|直接放箱子|"
    r"直接.{0,10}(?:不好吗|才对)|"
    r"绕成死结|打成死结|要绕成|这是死结|死结了|"
    r"你这是要|别绕那么|别绕成",
)
# 收束引话 haystack：只认前段可抠叮嘱，不认中段「不能再塞」催促
_RE_RULE_CORE = re.compile(
    r"不许|别碰|别晃|轻点|慢点|系紧|轻轻|轻拿|别浇|别多|别夹|"
    r"别响|别堆|别乱|规矩|叮嘱|不准|只能|别太",
)
# 中段叮嘱方催停/劝阻复读（一句慌即可，堆「快停/别拉」稀释歪读）
_RE_MID_STOP_NAG = re.compile(
    r"快停|停下|别拉|别绕|别再|悠着|够了|别搞|别弄那么",
)
_RE_ALARM_BEAT = re.compile(
    r"白印|勒红|鼓成|鼓起|麻了|麻花|陷进肉|焊死|脚背|脚趾|解不开",
)
# 回旋镖引的规矩，须能在叮嘱方补救动作里对上「她也破了」
_BOOM_VIOLATION_PAIRS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (re.compile(r"轻|慢"), re.compile(r"用力|重|猛|摔|砸|扯|拽|扫|挥")),
    (re.compile(r"别碰|不许碰|不准碰|别动"), re.compile(r"碰|扶|捡|拿|摸|弄")),
    (re.compile(r"别夹|太紧|夹紧"), re.compile(r"夹紧|夹得?更?紧|更紧|用力夹|用力扯|用力捏")),
    (re.compile(r"系紧|用力拉|拉紧|别老散"), re.compile(r"解|抠|拆|扯开")),
    # 浇花类破规=继续浇/倒/灌（拿抹布拖地是收拾不是违犯，勿放行）
    (re.compile(r"别浇|别多|一小口|倒一次"), re.compile(r"浇|倒|灌|冲")),
    (re.compile(r"别弄乱|整齐|平放|别乱翻"), re.compile(r"弄乱|乱了|乱成|扒乱|翻乱|扫乱|堆乱")),
    (re.compile(r"关.*轻|轻.*关|别响"), re.compile(r"用力关|摔门|砰|响")),
)

# 中段开讨论会：确认/辩字义，没有动作升级 → 演进无意义，不好玩
_RE_DEF_TALK = re.compile(
    r"是不是|不就是|难道不是|听见了没有|记住没|什么叫|"
    r"你说的是|我理解|算不算轻|算不算",
)
# 字面动作递进：中段至少要有两档升级痕迹（含计量式递进）
_RE_ESCALATE = re.compile(
    r"再|又|第二|第三|两下|三口|第三圈|更[^，。]{1}|太松|太紧|"
    r"下一件|一点点|只[挪推夹放倒开抠捏拿摆]|还是|"
    r"越[^，。]{0,3}越|整整|不到半?(?:毫米|厘米|寸|格)|头发丝",
)
# 「执行歪」可拍画面：判「怎么演」的通用特征，不写主题名词词表
# （名词表只认旧主题，新主题必被误杀清零）。特征组：
# 变形动词 / 极端计量 / 越做越极端 / 比喻演法 / 物理封死形变
RE_TWIST_VISUAL = re.compile(
    r"[绕叠垒码堆挤卷捆扎打削切剪磨缩瘦]成|"
    r"只剩|就剩|露出来|"
    r"[一半两]\s?(?:毫米|厘米|根|粒|滴|格)|[一二两三四五六七\d]+滴|"
    r"一小口|一口|一杯|头发丝|"
    r"一秒只|只[挪推夹放倒开抠捏拿按碰吸吹让摸浇]|数着|"
    r"踮脚|悬空|瞄准|堵住|塞住|绷直|屏住|垫平|吹口气|"
    r"整整[^，。]{0,4}(?:秒|分钟|小时)|"
    r"越[^，。]{1,3}越[^，。]{1,4}|"
    r"像[^，。]{1,8}(?:一样|那样)|"
    r"死结|死疙瘩|解不开|打不开|卡住|进不去|动不了|"
    r"[焊锁关卡]死|勒红|变形|溢|满出来|满了|冒出来|渗出来|一把扫|扫进",
)
_RE_TWIST_VISUAL = RE_TWIST_VISUAL
# 把主冲突写成辩定义，不是演歪读
_RE_DEF_CORE = re.compile(
    r"多紧算紧|算不算轻|算不算紧|什么叫轻|什么叫紧|谁对谁错",
)

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺字面执行", 7),
    ("缺后果场面", 6),
    ("缺叮嘱方破规", 7),
    ("回旋镖过早", 5),
    ("破规未先于回旋镖", 6),
    ("空辩论注水", 5),
    ("中段拖沓注水", 5),
    ("回旋镖复读", 5),
    ("二次收束注水", 5),
    ("妈妈插话", 8),
    ("叮嘱方事先批准", 5),
    ("执行方句句求同意", 5),
    ("字面笑点被提前拆穿", 4),
    ("回旋镖未扣破规", 4),
    ("回旋镖未点破", 5),
    ("中段抠定义", 4),
    ("中段缺动作升级", 4),
    ("中段催停复读", 4),
    ("哼后第二场", 5),
    ("末句发指令", 4),
    ("缺字面歪读点", 0),
    # 模板/动作复读：不是“扣结构”，是好笑加分归零（无有意思的点）
    ("模板复读", 0),
    ("中段动作复读", 0),
)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    body = lines[:-4] if n > 4 else lines[:-2]
    tail4 = lines[-4:] if n >= 4 else lines
    body_text = "".join(body)
    tail_text = "".join(tail4)
    all_text = "".join(lines)

    if _A_STYLE.search(tail_text) or (
        "哪里不一样" in tail_text and "那不一样" in tail_text
    ) or re.search(r"完全不一样|跟.{0,6}不一样", tail_text):
        cons.append("偏A式末四拍，不好笑")

    if not RE_LITERAL.search(body_text):
        cons.append("缺字面执行，不好笑")

    if RE_LITERAL.search(body_text) and not RE_MESS.search(all_text):
        cons.append("缺后果场面，不好笑")

    boom_i = next((i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)), None)
    fix_i = None
    for i, ln in enumerate(lines):
        if boom_i is not None and i >= boom_i:
            break
        if not RE_FIX.search(ln):
            continue
        if speakers and len(speakers) == len(lines) and speakers[i] not in (
            "灿灿",
            "妈妈",
        ):
            continue
        fix_i = i  # 回旋镖前最后一个补救句

    if boom_i is not None and fix_i is None:
        cons.append("缺叮嘱方破规，不好笑")
    elif fix_i is None and RE_BOOM_CLOSE.search(tail_text):
        cons.append("缺叮嘱方破规，不好笑")

    if boom_i is not None and fix_i is not None and boom_i < fix_i:
        cons.append("破规未先于回旋镖，不好笑")

    if boom_i is not None and boom_i < n // 3:
        cons.append("回旋镖过早，不好笑")

    if _EMPTY_DEBATE.search(all_text) or (
        sum(1 for ln in body if re.search(r"公平|谁先|不公平", ln)) >= 2
    ):
        cons.append("空辩论注水，不好笑")

    # 中段抠定义过久
    nit_n = sum(
        1
        for ln in body
        if re.search(r"你又没说|只说了|也包括|没说别的|当然包括", ln)
    )
    if nit_n >= 3:
        cons.append("空辩论注水，不好笑")

    # 中段开讨论会 / 缺动作递进 → 演进无意义，不好玩
    def_talk_n = sum(1 for ln in body if _RE_DEF_TALK.search(ln))
    escalate_n = sum(1 for ln in body if _RE_ESCALATE.search(ln))
    if def_talk_n >= 2 or _RE_DEF_CORE.search(all_text):
        cons.append("中段抠定义无升级，不好玩")
    elif def_talk_n >= 1 and escalate_n < 2 and len(body) >= 4:
        # 有辩字义却几乎没有递进动作
        cons.append("中段缺动作升级，不好玩")
    elif escalate_n < 1 and len(body) >= 6:
        cons.append("中段缺动作升级，不好玩")

    # 有「照做」但没有歪读可拍画面 → 缺「执行歪」的点
    mid_for_twist = body[1:] if len(body) > 2 else body
    mid_twist_text = "".join(mid_for_twist)
    if (
        RE_LITERAL.search(body_text)
        and not _RE_TWIST_VISUAL.search(mid_twist_text)
        and not _RE_TWIST_VISUAL.search("".join(tail4[:2]))
    ):
        cons.append("缺字面歪读点，不好笑")

    # 中段动作模板复读：如“轻轻放第一块/第二块/第三块…”堆块式照做
    # 这种容易被观众当成“节拍平铺”，即使后面有一锤场面也未必好笑。
    # 只数「动作词+量词/序号」的堆块句（放一块/再码一层/第二块），
    # 勿把立规句/招牌话（无堆量）当复读——主题词（轻轻放）本身不算信号。
    _RE_STACK = re.compile(
        r"(?:轻轻|慢慢|小声|小心|用力|认真)?"
        r"(?:"
        r"(?:放|码|铺|摆|叠|堆|搁|搭|垒|绕|系|卷|缠)"
        r"[^，。！？]{0,5}"
        r"(?:[一两三][块层件圈格]|又?一[块层件圈格]|第[一二三四1234][块层件圈格])"
        r"|"
        r"[一两三][块层件圈格].{0,4}"
        r"(?:放|码|铺|摆|叠|堆|搁|搭|垒|绕|系|卷|缠)"
        r")",
    )
    stack_n = sum(1 for ln in body if _RE_STACK.search(ln))
    if stack_n >= 3:
        cons.append("模板复读，不好笑")
        cons.append("中段动作复读，不好笑")

    # 本地补字残渣：呀呢叠词 / 照做口头禅复读
    if re.search(r"(?:呀|呢|啊){3,}|你看呀呢", all_text):
        cons.append("补字垫片注水，不好笑")
    literal_echo_n = sum(
        1
        for ln in body
        if RE_LITERAL.search(ln)
        and not _RE_TWIST_VISUAL.search(ln)
        and not RE_MESS.search(ln)
    )
    if literal_echo_n >= 3:
        cons.append("照做口头禅复读，不好笑")

    # 成片宜 15–16；17–20 不硬卡好笑；≥21 才记拖沓
    if n >= 21:
        cons.append("中段拖沓注水，不好笑")

    # 搞砸（一锤）之前灿灿若已点头批准 / 拆穿字面，笑点作废
    mess_i = next((i for i, ln in enumerate(lines) if _RE_MESS_BEAT.search(ln)), None)
    if mess_i is None:
        mess_i = next((i for i, ln in enumerate(lines) if RE_MESS.search(ln)), None)
    before_mess = lines[:mess_i] if mess_i is not None else body
    before_mess_text = "".join(before_mess)
    if _RE_PREAPPROVE.search(before_mess_text):
        cons.append("叮嘱方事先批准，不好笑")

    # 搞砸前灿灿拆穿字面误解（「不是让你垒塔」）→ 意外没了
    cancan_before = before_mess
    if speakers and len(speakers) == len(lines) and mess_i is not None:
        cancan_before = [
            lines[i]
            for i in range(mess_i)
            if speakers[i] == "灿灿"
        ]
    if _RE_SPOIL_LITERAL.search("".join(cancan_before)):
        cons.append("字面笑点被提前拆穿，不好笑")

    # 中段催停复读：叮嘱方慌 ≥3 句 = 劝阻会，不是歪读递进
    stop_n = 0
    alarm_n = 0
    for i, ln in enumerate(body):
        if speakers and len(speakers) == len(lines) and speakers[i] != "灿灿":
            continue
        if _RE_MID_STOP_NAG.search(ln):
            stop_n += 1
        if _RE_ALARM_BEAT.search(ln):
            alarm_n += 1
    if stop_n >= 3:
        cons.append("中段催停复读，不好笑")
    elif stop_n >= 2 and alarm_n < 2:
        cons.append("中段只会催，没有连续报新惨状，不好笑")

    if sum(1 for ln in body if _RE_ASK_PERMIT.search(ln)) >= 2:
        cons.append("执行方句句求同意，不好笑")

    mom_n = sum(1 for sp in (speakers or []) if sp == "妈妈")
    if mom_n > 0:
        cons.append("妈妈插话不好笑")

    # 末段相邻再引一次常见于 LLM 结巴，不硬杀；
    # 中段（末 6 句之外）+ 收束各一枪、或 ≥3 次才记复读
    boom_idx = [i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)]
    boom_n = len(boom_idx)
    mid_boom = any(i < n - 6 for i in boom_idx)
    if boom_n >= 3 or (boom_n >= 2 and mid_boom):
        cons.append("回旋镖复读，不好笑")

    # 哼/算了后不许再开第二场（含新叮嘱、再问要不要花生米）
    soft_indices = [
        i
        for i, ln in enumerate(lines)
        if re.search(r"哼|算了|行吧", ln)
    ]
    if soft_indices and soft_indices[0] < n - 1:
        cons.append("哼后第二场，不好笑")

    # 末句须嘴硬收束，勿发新指令（轻轻拉一下就够了 / 哼完拿剪刀）
    last = lines[-1] if lines else ""
    last_sp = speakers[-1] if speakers and len(speakers) == n else ""
    if last_sp == "灿灿" and not re.search(r"哼|算了|行吧", last):
        if re.search(
            r"轻轻|别提|就够|下次|以后|别再|要|不许|不准|得",
            last,
        ):
            cons.append("末句发指令，不好笑")
    if last_sp == "灿灿" and re.search(r"哼|算了|行吧", last):
        if re.search(r"拿剪刀|剪开|解开吧|下次|以后|你忍着", last):
            cons.append("末句发指令，不好笑")

    # 回旋镖须点破「现在又上手破规」，不能只引原话
    if boom_i is not None:
        boom_ln = lines[boom_i]
        if RE_BOOM_CLOSE.search(boom_ln) and not RE_BOOM_POINT.search(boom_ln):
            cons.append("回旋镖未点破，不好笑")

    # 回旋镖引的规矩，须对应叮嘱方补救时的破规动作
    if boom_i is not None:
        boom_line = lines[boom_i]
        m = _RE_DIRECT_QUOTE.search(boom_line)
        cite = m.group(1) if m else boom_line
        # 只取引文本体，去掉「我照做了你却…」这类尾巴
        cite = re.split(r"[，。！？]|你现在|你却|怎么|我照", cite)[0]
        cite = re.sub(r"的$", "", cite.strip())
        if len(cite) < 3:
            cite = boom_line
        # 看回旋镖前灿灿近几句补救，勿被开场「我帮你」带偏
        start = max(0, boom_i - 5)
        if fix_i is not None:
            start = max(start, fix_i - 1)
        fix_window_lines = []
        for i in range(start, boom_i):
            if speakers and len(speakers) == len(lines):
                if speakers[i] not in ("灿灿", "妈妈"):
                    continue
            fix_window_lines.append(lines[i])
        fix_window = "".join(fix_window_lines) or "".join(tail4)
        matched_rule = False
        violated = False
        for rule_re, viol_re in _BOOM_VIOLATION_PAIRS:
            if rule_re.search(cite):
                matched_rule = True
                if viol_re.search(fix_window) or viol_re.search(boom_line):
                    violated = True
                break
        if matched_rule and not violated:
            cons.append("回旋镖未扣破规动作，不好笑")

    return cons


def closing_quote_haystack(
    lines: list[str],
    speakers: list[str] | None,
    body_text: str,
) -> str:
    """D 收束引话只认前段灿灿叮嘱，不认昭昭自报、不认中段催促。"""
    if not speakers or len(speakers) != len(lines):
        return body_text
    body_n = len(lines[:-4]) if len(lines) > 4 else max(0, len(lines) - 1)
    early_n = min(6, body_n)
    early_rules = [
        lines[i]
        for i in range(early_n)
        if speakers[i] == "灿灿" and _RE_RULE_CORE.search(lines[i])
    ]
    if early_rules:
        return "".join(early_rules)
    cancan = "".join(
        lines[i] for i in range(body_n) if speakers[i] == "灿灿"
    )
    return cancan if cancan.strip() else body_text


def humor_revision_hint(issue: str) -> str | None:
    keys = (
        "字面",
        "后果",
        "破规",
        "回旋镖",
        "末四拍",
        "空辩论",
        "拖沓",
        "复读",
        "二次收束",
        "哼后",
        "末句发指令",
        "催停",
        "提前拆穿",
        "D",
    )
    if "无出处" in issue or "引话" in issue:
        return (
            f"【好笑·D】{issue}。"
            "倒数第 2 句「你自己说…」后的引文须是前文灿灿叮嘱的连续子串"
            "（≥6 字原样抄），勿改写成「只浇一小口」这类近似话。"
        )
    if "拖沓" in issue:
        return (
            f"【好笑·D】{issue}。"
            "成片压到 ≤20 句（正文 ≤17 句为佳）：合并中段重复回合，"
            "把删掉的字补进保留句（每句写足 ≤24 字）；"
            "立叮嘱→字面→搞砸→破规→回旋镖链勿动。"
        )
    if "口头禅复读" in issue:
        return (
            f"【好笑·D】{issue}。"
            "「你说要…我就…」招牌话全文只准出现 1 次（第一回合立住即可）；"
            "之后每一回合换新讲究，报新的具体动作或数量"
            "（我只夹了一个角/我数着夹了两下/只剩一小口），"
            "勿把同一句「你说要…我就…」当口头禅连排。"
        )
    if "复读" in issue:
        return (
            f"【好笑·D】{issue}。"
            "全文「你自己说/你刚才说/你现在也」只准留末段那 1 句；"
            "中段同类引话改写成「照你说的」「按你说的」。"
        )
    if "事先批准" in issue:
        return (
            f"【好笑·D】{issue}。"
            "把搞砸前灿灿的「可以啊/不错/你试试吧」改成她没在看；"
            "后果必须是灿灿回头才发现，勿让她提前点过头。"
        )
    if "提前拆穿" in issue:
        return (
            f"【好笑·D】{issue}。"
            "删掉搞砸前灿灿的纠正句（不是让你垒塔/要平放/绕成死结了）；"
            "叮嘱只说一次，中段最多一句慌，让字面误解一路跑到倒/洒再发现。"
        )
    if "催停" in issue:
        return (
            f"【好笑·D】{issue}。"
            "中段灿灿最多一句慌（白印了/悠着点），勿「快停/别拉/停下」连喊；"
            "把回合留给昭昭把同一歪读做极端。"
        )
    if "哼后" in issue or "二次收束" in issue:
        return (
            f"【好笑·D】{issue}。"
            "回旋镖 1 句后立刻灿灿哼/算了收束；哼后禁止再开场、再叮嘱、再问要不要花生米。"
        )
    if "末句发指令" in issue:
        return (
            f"【好笑·D】{issue}。"
            "末句只许「哼，行吧。」这类短词收束；"
            "勿「你赢了」（认输）、勿「以后都…/下次我…/拿剪刀吧」（发新指令）补半句。"
        )
    if "未点破" in issue:
        return (
            f"【好笑·D】{issue}。"
            "回旋镖须引原话并点破矛盾："
            "「你自己说系紧点，怎么现在又上手来解了」；"
            "禁止只写「你自己说鞋带要系紧」就停。"
        )
    if "抠定义" in issue or "缺动作升级" in issue or "不好玩" in issue or "模板复读" in issue or "动作复读" in issue or "歪读点" in issue:
        return (
            f"【好笑·D】{issue}。"
            "先钉歪读点：合理规矩词 + 第二种读法 + 必然后果；"
            "中段演歪读（死结/小山/塔/溢），勿辩「多紧算紧」；"
            "每回合把同一歪读推更极端：更慢/更轻/更密/数更多"
            "（数到十→数到二十、隔一指→隔三指），用「再…一点/又…」推进；"
            "禁止只换序号——「轻轻放第一/二/三块」「绕第一圈/第二圈/三圈」"
            "只递增数字=流程复读；也禁止每回合只换新手法不加深"
            "（悬手腕→隔两指→抚平 是同一力度平铺）；"
            "错误结果须由歪读必然推出。"
        )
    if "未扣破规" in issue:
        return (
            f"【好笑·D】{issue}。"
            "灿灿补救须亲手违反同一条叮嘱（说轻点却用力扫、说别碰却上手捡）；"
            "回旋镖引的就是这条被她刚破的原话，勿引无关的「别弄乱」。"
        )
    if "求同意" in issue:
        return (
            f"【好笑·D】{issue}。"
            "删掉昭昭句尾的「好不好/行不行/对吧」，改成他自顾自认真汇报动作"
            "（我只夹了一个角、我数着夹了两下），字面执行才有反差。"
        )
    if any(k in issue for k in keys):
        return (
            f"【好笑·D】{issue}。"
            "立具体叮嘱→认真字面画面（绕成花生米/叠成小山/夹住一角）→意外一锤→"
            "上手破规→回旋镖只 1 句→哼；最多一句尾巴，勿第二场回旋镖。"
        )
    return None
