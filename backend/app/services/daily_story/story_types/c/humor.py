"""C 类好笑维硬伤、场面加分与修订 hint。"""

from __future__ import annotations

import re
from collections.abc import Callable

RE_LITERAL_RULE_PLAY = re.compile(
    # 赛规引用（结构判定，禁主题词表——主题词只认旧主题，新主题全漏）
    r"(?:你刚说|你说的|你定的|你自己说).{0,20}(?:先|后|谁|归|应该|就得|才算|负责|收拾|"
    r"先选|先拿|先用|先到|先碰|先喝|先吃|先坐|先摆|先洗|先切|先分)|"
    # 字面加赛（按对方规则执行到荒谬）
    r"(?:我也|你都|我全|你全|全都|照做|照你说的做|按你说的做|"
    r"按.{0,4}(?:规矩|赛规|规则|说的))|"
    # 竞争升级（更/再/又 + 可拍动作）
    r"(?:更|再|又|加|多).{0,8}(?:急|快|多|少|大|小|"
    r"喝|吃|拿|抢|切|分|摆|放|坐|占|用|选|叠|碰|收拾|弄|挪|推|拉|"
    r"倒|洒|摔|翻|藏|换|递|给|要|留|剩|"
    r"湿|干|热|冷|新|旧|脏|干净|整齐|乱)|"
    # 反悔/耍赖指责
    r"(?:耍赖|瞎说|胡说|乱说|作弊|反悔|赖皮|说话不算|不算数|变来变去|改口|"
    r"你.{0,3}(?:赖|骗|反悔|不算|瞎|胡))|"
    # 赛规自噬（对方也被自己规则套住）
    r"(?:你自己|你刚才|你刚刚|你之前|你也).{0,10}(?:也|就|都|怎么|不是|干嘛|在|有|"
    r"碰|拿|抢|切|分|摆|放|喝|吃|坐|用|选|叠|收拾|弄|占)",
)
# 倒装引话：引文在前，引语动词在句尾（「碰到就是咬到，你说的」）
# 句尾可有标点（。！？…），引语动词后必须结束
_RE_INVERTED_QUOTE = re.compile(
    r"([^，。！？…]{3,})\s*[，,]\s*(?:你刚才说|你自己说|你不是说|你刚说|你说的)[。！？…]?$",
)
# 前置引话失据：bare「自己说X」（无你字）——把对方的动作曲解成他立过的规。
# 共享 _RE_DIRECT_QUOTE 只认「你…说」，漏「自己说X」（L21 型）。
# (?<!我) 排除「我自己说X」反身用法（那种是说自己，不是归咎对方）。
_RE_SELF_SAID_QUOTE = re.compile(r"(?<!我)自己说([^，。！？…]{2,})")
# 规则错误归属：把对方立的规安到自己头上（「我说规则是X / 我说的是X」，L18/L20 型）。
_RE_SELF_CLAIM_RULE = re.compile(
    r"(?:我说|我说的|我定的|我立的|我定|我立)(?:的)?"
    r"(?:规则是|规矩是|的是|是)?([^，。！？…]{2,})",
)
# 陈述/立规语境词：某句若含这些词且带被引规则子串，才算「有人立过这条规」。
_RE_STMT_FRAME = re.compile(
    r"说|规则|规矩|立|定|数到|说好|讲好|说定|承诺|说死|"
    r"先到|先碰|先拿|先摸|谁先|归|该|应该|就得|才算|重来|重新",
)
_OWNERSHIP_CHATTER = re.compile(
    r"都是我的|你的没|各管各|叠了没|不公平|凭什么.*我的|"
    r"有没有我的一件|你没叠",
)
_RULE_LINE = re.compile(r"谁碰|碰了.*负责|弄乱.*负责|谁弄乱")
# 句尾语气词堆砌（2026-08-09 用户 v6 酸奶稿：好不好了呀/听着了呀/碰过了呢了呀/
# 没撒手了呢了呀/抢嘛了呀/准备好了呢呀——句尾连叠语气助词=病句，观感重罚）
_RE_TONE_STACK = re.compile(
    r"(?:[呢嘛的了着好]{2,}呀|呢了|呢呀)[！。！？]?$",
)
# 回旋镖引话标记（2026-08-12 定）：全文「你刚说/你说的+原话」最多 2 次，
# 中段 1 次、末段 1 次；同一承诺只许引 1 遍。
_RE_BOOMERANG_QUOTE = re.compile(
    r"你刚说|你说的|你不是说|你自己说|你刚才说",
)
_FILMABLE_TWIST = re.compile(
    # 可拍争法动作（结构判定，禁主题词表）
    r"歪了|乱了|倒了|洒了|摔了|碰倒|多拿|偷拿|藏了|"
    r"东倒西歪|翻乱|弄乱|乱放|叠好|给你这件|递给你|给你。|碰了|碰倒|"
    # 通用竞争动作（切/分/抢/占/挪/换/摆/选 等）
    r"切[^，。！？]{0,3}(?:开|好|完|了|断|块|半|片|刀)|"
    r"分[^，。！？]{0,3}(?:开|好|完|了|出|给|成|两|半|块)|"
    r"抢[^，。！？]{0,3}(?:走|过|到|了|去|在|先|着)|"
    r"挪[^，。！？]{0,3}(?:开|走|了|到|过|位|动)|"
    r"摆[^，。！？]{0,3}(?:好|正|齐|完|了|上|在|着|放)|"
    r"换[^，。！？]{0,3}(?:了|过|给|到|成|走|开|下|个)|"
    r"选[^，。！？]{0,3}(?:了|好|完|中|出|走|过|定|大|小|块|个)|"
    r"坐[^，。！？]{0,3}(?:下|上|了|着|过|在|到|住|稳)|"
    r"占了|占着|占住|"
    r"拿[^，。！？]{0,3}(?:走|了|到|过|起|着|出|回|来|去|给|下|上|在|"
    r"刀|勺|杯|碗|盘|块|件|个)|"
    r"用[^，。！？]{0,3}(?:了|过|完|到|上|下|着|在|来|去|"
    r"杯|碗|盘|刀|勺|块|件|个)|"
    r"你[^，。！？]{0,4}(?:先|也|又|就|才|都|不|没|别|再|"
    r"拿|抢|切|分|摆|放|坐|占|用|选|碰|喝|吃|"
    r"叠|收拾|弄|挪|推|拉|倒|洒|摔|翻|藏|换)"
)
# 仪式判据场标记（单脚站/金鸡独立/举过头顶/坚持X秒/站满十秒）——伪回旋镖检测只
# 在仪式场触发，先到先得场（谁先拿到归谁）不拦。
_RE_RITUAL_SCENE = re.compile(
    r"单脚站|金鸡独立|举过头顶|坚持.{0,4}秒|站满十秒|数满十秒",
)
# 规则漏字反噬标记：回旋镖句带「又没说/没规定/你只说/没说不许」等，说明立规人输在
# 规则没写全上（真回旋镖）；无标记 + 只有「我也做到了/你数啊」+ 末句认栽 = 伪回旋镖。
# 注意勿用裸「没写」——「酸奶又没写你名字」是通用顶嘴句，会误认成反噬标记。
_RE_RULE_GAP_MARKER = re.compile(
    r"又没说|你只说|没规定|没不许|没说.{0,4}(?:多快|不许|不能|算)|"
    r"没写.{0,4}(?:数|秒|几|快|不许|不能)",
)
_RE_PSEUDO_IMITATE = re.compile(
    r"我也|我都|我站了|我做到了|我举了|我放好了|你数啊|我也站满",
)
_RE_PSEUDO_CONCEDE = re.compile(r"算你|行吧|算了|哼|明天我")
# 中段肢体抢物链（抢/掉/捡/怀里/卡缝）——无新赛规判据时 comedy 信息不升级
_RE_PHYSICAL_POSSESSION = re.compile(
    r"掉地|捡起|抠出|拽|夺|怀里|抱得|卡.{0,4}缝|再抢|啪嗒|抢到|抱紧|搂住|"
    r"松手|砸|掉下|夺下|抢过来",
)
# 规则轮次升级：新判据追加 + 对方照字面追问（C 整件物优先好笑模式）
_RE_RULE_ESCALATION = re.compile(
    r"才算|不算|得.{0,8}才算|追加|又说|离地|着地|单脚|整个抱|立着不算|"
    r"按哪条|哪条|一条接一条|你也没说|到底按|钻空子",
)
_RE_ESTABLISH_RULE = re.compile(
    r"归谁|谁先|我定|规则|才公平|算算",
)
_RE_OPPONENT_VOID = re.compile(
    r"作废|这局不算|不算数了|重新来一局|你乱拽",
)
# 立规人连续「改定义式加赛」（同一喜剧机制：不断重写「拿到」标准）
_RE_RULE_DEFINITION_APPEND = re.compile(
    r"靠着不算|得.{0,8}才算|才算数|才算真正|我又加|追加一条|都得.{0,6}才算",
)
# 权力翻转：灿灿从被动执行转为主动追问（还有吗/哪条作数/按哪条）
_RE_POWER_FLIP = re.compile(
    r"还有吗|哪条作数|按哪条|到底按|哪条说|哪条算|你一条接一条",
)
_RE_POWER_FLIP_STRONG = re.compile(
    r"还有吗|哪条作数|按哪条|到底按哪条|哪条说我耍赖|哪条算",
)
# 主题嘴硬收尾（比「明天我抢先」更贴 C 公平执念）
_RE_THEME_STUBBORN_END = re.compile(
    r"赢规则|不算赢我|规则执行力|测你",
)

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("归属口水战", 5),
    ("偏A式那不一样", 6),
    ("缺可拍争法", 7),
    # 2026-08-07 专家对齐 C2：回旋镖引话无出处 → 好笑分封顶 6
    ("回旋镖引话失据", 6),
    # 2026-08-07 专家对齐 C2 扩展：把对方立的规安到自己头上 → 好笑分封顶 6
    ("回旋镖错误归属", 6),
    # 2026-08-08 用户定「正文禁用开场用过的理由」：立理由人正文重申开场理由
    # → 好笑分封顶 4（提示词约束 + validate 逐字复述硬卡都拦不住带变体的重申）
    ("开场理由复读", 4),
    # 2026-08-09 用户 v6 酸奶稿：句尾语气词堆砌=病句 → 好笑分封顶 4
    ("句尾语气词堆砌", 4),
    # 2026-08-09 用户 v25/v27：末句嘴硬话发明本场赛规没有的比较维度
    # （判据「举过头顶坚持三秒」末句却「比你早」=时序 /「比你举得久」=时长）
    # → 观感封顶 6（validate 同逻辑硬卡命中即重抽）
    ("末句嘴硬比法漂移", 6),
    # 2026-08-11 用户/专家/千问共识：伪回旋镖（对方复制仪式+立规人赖账，规则字面
    # 没反噬立规人，酸奶 v46）→ 好笑封顶 6，只观感压分不硬拦
    ("伪回旋镖", 6),
    # 2026-08-12 用户定：回旋镖重复（同一承诺/同一句引 ≥3 次）→ 好笑封顶 4
    ("回旋镖重复", 4),
    # 2026-08-21 抱枕 #20：中段堆抢/掉/捡无新赛规 → 结构满配也虚高
    ("肢体抢物复读", 8),
    # 2026-08-21 抱枕 #20：非立规人作废/改规（灿灿规则机器只追问按哪条）
    ("对方擅自改规", 7),
    # 2026-08-21 GPT：同一「改定义」机制连打 ≥4 次=规则清单，非笑点递进
    ("C规则机制复读", 6),
    # 2026-08-21 GPT：≥3 次改定义且无「还有吗」式权力翻转
    ("C规则缺权力翻转", 7),
)


def ground_closing_quote(fragment: str, haystack: str) -> bool:
    frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,]", "", fragment)
    hay = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,]", "", haystack)
    # 回旋镖引话允许视角互换（2026-08-12 定）：「歪了算我输」被对方引作
    # 「歪了算你输」是同一承诺，校验按人称归一后比对。
    frag_norm = frag.replace("我", "X").replace("你", "X")
    hay_norm = hay.replace("我", "X").replace("你", "X")
    if len(frag) < 3:
        return True
    if "更急" in frag_norm and "更急" in hay_norm:
        return True
    if "先选" in frag_norm and "先选" in hay_norm:
        return True
    if "公平" in frag_norm and "公平" in hay_norm:
        return True
    if "先到" in frag_norm and ("先到" in hay_norm or "先拿" in hay_norm):
        return True
    if re.search(r"碰|弄乱|收拾|叠", frag_norm) and re.search(
        r"碰|弄乱|收拾|叠|规矩|赛规", hay_norm,
    ):
        return True
    if ("就算" in frag_norm or "不算" in frag_norm) and (
        "规矩" in hay_norm or "算" in hay_norm
    ):
        return True
    run = min(6, len(frag_norm))
    for i in range(len(frag_norm) - run + 1):
        if frag_norm[i:i + run] in hay_norm:
            return True
    # 引话可能是「规则原话 + 后续动作」拼成一句：只要前缀能对上原话就算有出处
    # （2026-08-12 定，修复「切完我先挑，那我挑了大的」被误判无前文）。
    for n in (6, 5, 4, 3):
        if len(frag_norm) >= n and frag_norm[:n] in hay_norm:
            return True
    return False


def _opening_reason_repeat_issue(
    lines: list[str],
    speakers: list[str],
) -> str | None:
    """开场理由复读（用户定 2026-08-08）：正文禁用开场用过的理由。

    C 类开场第 2 句（反对句）带「我先X」理由（书是我搬回来的/我求妈妈买的/
    攒零花钱买的）。立理由人自己在正文重申同一理由 = 炒冷饭——validate 的逐字
    复述硬卡拦不住「我搬回来的，我先翻开才对」这类带变体的重申，故在观感层压分。
    检测：取开场第 2 句里「…的」结尾段作理由核心，正文中**同 speaker** 的句子
    去虚字后含其 ≥3 字连续子串即判复读。只查立理由人（对方击穿「搬回来不算」
    是合法回旋镖，不禁），不按单篇剧情词表。
    """
    if len(lines) < 3 or len(speakers) < 2:
        return None
    opp_sp = speakers[1]
    if opp_sp not in ("昭昭", "灿灿"):
        return None
    segs = [s.strip() for s in re.split(r"[，,。]", lines[1]) if s.strip()]
    reason = max(
        (s for s in segs if s.endswith("的") and len(s) >= 4),
        key=len,
        default="",
    )
    if not reason:
        return None
    core = _RE_REASON_STRIP.sub("", reason)
    # 只用 ≥4 字连续子串比对，避免泛化短语误杀：
    # 「我求妈妈买」的 3 字片「妈妈买」会误中正文「等妈妈买新的」——
    # 而真实复读（我搬回来的/我求妈妈买的）都能共享到 4 字片
    if len(core) < 4:
        return None
    frags = {core[i:i + 4] for i in range(len(core) - 4 + 1)}
    for ln, sp in zip(lines[2:], speakers[2:]):
        if sp != opp_sp:
            continue
        txt = _RE_REASON_STRIP.sub("", ln)
        if any(frag in txt for frag in frags):
            shown = reason[:14]
            return (
                f"C中段·开场理由复读：正文{opp_sp}重申开场理由「{shown}」"
                "（开场第2句已用过；同一理由全篇最多一次，正文顶嘴换新角度："
                "谁先拿到/谁先翻开/书是大家的/你没看完别占着）"
            )
    return None


_RE_REASON_STRIP = re.compile(r"[的话呢呀嘛吧啊哦嗯…\s「」『』“”\"'‘’：:，,、。！？是]")


def _first_rule_maker_speaker(
    lines: list[str],
    speakers: list[str],
) -> str | None:
    """正文里首次立赛规的 speaker（用于判对方是否擅自改规）。"""
    for i, ln in enumerate(lines[2:], start=2):
        if _RE_ESTABLISH_RULE.search(ln) and i < len(speakers):
            return speakers[i]
    return None


def _mid_body_range(lines: list[str]) -> tuple[int, int]:
    """正文中间段（排除开场重复与末四拍/末句）。"""
    n = len(lines)
    if n >= 8:
        return 2, n - 4
    if n >= 6:
        return 2, n - 2
    return 2, n


def _physical_repeat_issue(lines: list[str]) -> str | None:
    """中段肢体抢物复读：多轮占有动作无规则层升级。"""
    start, end = _mid_body_range(lines)
    body = lines[start:end]
    if len(body) < 3:
        return None
    physical = sum(1 for ln in body if _RE_PHYSICAL_POSSESSION.search(ln))
    rule_esc = sum(1 for ln in body if _RE_RULE_ESCALATION.search(ln))
    if physical >= 3 and rule_esc < 2:
        return (
            "C中段肢体抢物复读：多轮抢/掉/捡/怀里没有新赛规判据——"
            "改规则轮次升级（占有→状态→姿势），每轮一句新判据+一句照字面执行"
        )
    return None


def _opponent_void_rule_issue(
    lines: list[str],
    speakers: list[str],
) -> str | None:
    """非立规人作废/改规：灿灿只追问按哪条，不许说作废。"""
    maker = _first_rule_maker_speaker(lines, speakers)
    if not maker:
        return None
    start, end = _mid_body_range(lines)
    for i, ln in enumerate(lines[start:end], start=start):
        sp = speakers[i] if i < len(speakers) else None
        if sp and sp != maker and _RE_OPPONENT_VOID.search(ln):
            shown = ln[:18]
            return (
                f"C中段·对方擅自改规：{sp}说「{shown}…」——"
                "只许立规人追加赛规，对方只追问按哪条/照字面执行"
            )
    return None


def _count_rule_definition_appends(body: list[str]) -> int:
    return sum(1 for ln in body if _RE_RULE_DEFINITION_APPEND.search(ln))


def _rule_mechanism_repeat_issue(lines: list[str]) -> str | None:
    """规则清单化：改定义式加赛连打，喜剧机制不升级。"""
    start, end = _mid_body_range(lines)
    body = lines[start:end]
    appends = _count_rule_definition_appends(body)
    if appends >= 4:
        return (
            "C规则机制复读：立规人连续改「拿到」定义≥4次（规则清单）——"
            "压缩为3层：正常→钻定义→荒谬一条；禁离沙发/双脚/单脚层层叠加"
        )
    if appends >= 3 and not _body_has_power_flip(body):
        return (
            "C规则缺权力翻转：改定义≥3次但缺翻转质疑句——"
            "中间加「哪条作数/还有吗/你一条接一条说的」等昭昭继续作死"
        )
    return None


def _body_has_power_flip(body: list[str]) -> bool:
    """翻转质疑句：哪条作数与还有吗同档（专家 2026-08-21 P0-2）。"""
    return any(_RE_POWER_FLIP_STRONG.search(ln) for ln in body)


def _power_flip_bonus(body: list[str]) -> tuple[int, list[str]]:
    pts = 0
    pros: list[str] = []
    if _body_has_power_flip(body):
        pts += 3
        pros.append("权力翻转")
    return pts, pros


def _rule_round_escalation_issue(lines: list[str]) -> str | None:
    """三轮升级不足或缺递进：结构向降分提示。"""
    start, end = _mid_body_range(lines)
    body = lines[start:end]
    appends = _count_rule_definition_appends(body)
    if appends < 2:
        return (
            "C规则轮次升级不足：缺少占有→状态→姿势三轮动作递进（-4）——"
            "每轮一句新判据+一句照字面执行，第三轮须姿势控制"
        )
    if appends == 2:
        return (
            "C规则轮次升级偏少：仅 2 层升级，缺第三轮姿势控制（-2）"
        )
    return None


def _rule_round_escalation_score(lines: list[str]) -> tuple[int, list[str]]:
    """规则轮次升级：结构向加分；清单化时降档。"""
    start, end = _mid_body_range(lines)
    body = lines[start:end]
    if len(body) < 4:
        return 0, []
    appends = _count_rule_definition_appends(body)
    flip_pts, flip_pros = _power_flip_bonus(body)
    follow_n = sum(
        1
        for ln in body
        if re.search(
            r"算不算|哪条|照|你也没说|一条接一条|到底按|钻空子",
            ln,
        )
    )
    if appends >= 4:
        pts = 2 + min(flip_pts, 1)
        pros = ["规则清单化"]
        if flip_pros:
            pros.extend(flip_pros[:1])
        return pts, pros
    if appends == 3 and follow_n >= 1:
        return 4 + min(flip_pts, 2), ["规则轮次升级", *flip_pros[:1]]
    if appends >= 2 and follow_n >= 1:
        return 5 + min(flip_pts, 2), ["规则轮次升级", *flip_pros[:1]]
    if appends >= 2:
        return 3, ["规则轮次升级"]
    return 0, []


def _closing_stubborn_echo_issue(lines: list[str]) -> str | None:
    """末句嘴硬话发明本场赛规没有的比较维度（用户 2026-08-09 v25/v27 抓）。

    C 类收束末句嘴硬话的比较维度须字面出现在本场立规句里：赛规是
    **时长/姿势仪式**（举过头顶坚持三秒/坐稳才算/稳住不放）时，末句只能
    锚定仪式动词（「明天我抢先举过头顶」）或万能胜负（「明天我一定赢过你」），
    禁发明立规句里没有的比法——「比你早/比你快」是时序（本场不比先后）、
    「比你举得久/比你高/比你标准」是时长/质量比较（本场是达标制，不比谁久）。
    与 validate 硬卡共用一个判定函数（quality.c_closing_echo_error），
    避免观感层与硬卡逻辑漂移；此处命中即观感降分，validate 命中即整稿重抽。
    """
    from app.services.daily_story.story_types.quality import c_closing_echo_error

    return c_closing_echo_error(lines)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    from app.services.daily_story.story_types.quality import (
        RE_BOOMERANG_RULE,
        RE_REVELATION_PROP,
    )

    cons: list[str] = []
    sp_arr = list(speakers) if speakers else []
    physical_issue = _physical_repeat_issue(lines)
    if physical_issue:
        cons.append(physical_issue)
    void_issue = _opponent_void_rule_issue(lines, sp_arr)
    if void_issue:
        cons.append(void_issue)
    mechanism_issue = _rule_mechanism_repeat_issue(lines)
    if mechanism_issue:
        cons.append(mechanism_issue)
    round_issue = _rule_round_escalation_issue(lines)
    if round_issue:
        cons.append(round_issue)
    reason_issue = _opening_reason_repeat_issue(lines, sp_arr)
    if reason_issue:
        cons.append(reason_issue)
    tone_hits = [i + 1 for i, ln in enumerate(lines) if _RE_TONE_STACK.search(ln)]
    if tone_hits:
        first = ",".join(str(i) for i in tone_hits[:4])
        more = "…" if len(tone_hits) > 4 else ""
        cons.append(f"句尾语气词堆砌（第{first}句{more}，禁叠「呢了呀/着了呀/嘛了呀」病句尾）")
    boom_hits = [i + 1 for i, ln in enumerate(lines) if _RE_BOOMERANG_QUOTE.search(ln)]
    if len(boom_hits) >= 3:
        shown = ",".join(str(i) for i in boom_hits[:4])
        more = "…" if len(boom_hits) > 4 else ""
        cons.append(
            f"C回旋镖重复（第{shown}句{more}共{len(boom_hits)}次）："
            "全文「你刚说/你说的」最多 2 次，中段最多 1 次、末段收束 1 次；"
            "同一承诺/同一句原话只许引 1 遍"
        )
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    tail_text = "".join(tail4)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else tail_text

    has_boomerang = bool(RE_BOOMERANG_RULE.search(tail_text))
    has_literal = bool(RE_LITERAL_RULE_PLAY.search(late6))
    has_prop = bool(RE_REVELATION_PROP.search(tail_text))

    if "那不一样" in tail_text and not has_literal:
        cons.append("C收束偏A式那不一样")

    pre_close = lines[: max(0, len(lines) - 8)]
    ownership_chatter = sum(1 for ln in pre_close if _OWNERSHIP_CHATTER.search(ln))
    rule_i = next(
        (i for i, ln in enumerate(lines) if _RULE_LINE.search(ln)),
        None,
    )
    chatter_after = 0
    if rule_i is not None:
        tail_start = max(0, len(lines) - 8)
        for ln in lines[rule_i + 1 : tail_start]:
            if _OWNERSHIP_CHATTER.search(ln):
                chatter_after += 1
    if ownership_chatter >= 4 and (rule_i is None or chatter_after >= 3):
        cons.append("C中段归属口水战")

    if has_boomerang and not has_literal and not has_prop:
        filmable = bool(_FILMABLE_TWIST.search(late6))
        if not filmable and not RE_LITERAL_RULE_PLAY.search(late6):
            cons.append("C收束缺可拍争法")

    # 2026-08-11 伪回旋镖：仪式判据场，末段回旋镖只是「对方复制仪式成功 + 立规人
    # 赖账认栽」，没有「规则漏字」反噬点——立规人没输在自己那行字上（酸奶 v46 死这：
    # 单脚站规则，灿灿「我也站满了」，昭昭赖计数认栽）。只做观感压分，不硬拦。
    if (
        _RE_RITUAL_SCENE.search("".join(lines))
        and has_boomerang
        and not _RE_RULE_GAP_MARKER.search(late6)
        and _RE_PSEUDO_IMITATE.search(late6)
        and bool(lines)
        and _RE_PSEUDO_CONCEDE.search(lines[-1])
    ):
        cons.append(
            "伪回旋镖：立规人的规则没字面反噬自己，只靠对方复制仪式（我也站满了/"
            "我做到了）+ 立规人赖账认栽收场——改「规则漏字」反噬（没规定数数要多快/"
            "没说不许晃/自设条件），让立规人输在自己亲手写的那行字上"
        )

    # 2026-08-07 专家对齐 C2：回旋镖**倒装引话**出处检测。
    # 共享 _RE_DIRECT_QUOTE 只认「你（刚/自己/不是）说X」前置形态；
    # 「碰到就是咬到，你说的」这种引文在前、引语动词在句尾的倒装句漏检，
    # 导致伪拼凑原话（正文没说过）也能当回旋镖收束。补一条倒装检测：
    # 引语动词出现在句尾（…，你说的/你刚说/你刚才说/你不是说）时，
    # 提取逗号前的引文，验证是否在正文出现过。
    # 内联出处判定（不 import quality，避免循环依赖）：
    # 连续 ≥3 字命中正文即认有出处；伪拼凑（片断不在正文）判失据。
    body_text = "".join(lines[: max(0, len(lines) - 4)])
    for ln in tail4:
        for m in _RE_INVERTED_QUOTE.finditer(ln):
            frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,]", "", m.group(1))
            if len(frag) < 3:
                continue
            grounded = any(
                frag[i:i + run] in body_text
                for run in (6, 5, 4, 3)
                for i in range(len(frag) - run + 1)
            )
            if not grounded:
                cons.append(f"回旋镖引话失据（倒装「{frag[:12]}」无出处）")
                break

    # 2026-08-07 专家对齐 C2 扩展：前置引话失据（自己说X）+ 规则错误归属（我说规则是X）。
    # 共享 _RE_DIRECT_QUOTE 只认「你…说」；「自己说X」把对方动作曲解成他立过的规，
    # 「我说规则是X」把对方立的规安到自己头上。两条都需 speakers 才能判归属。
    _STRIP = r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,是]"
    for i, ln in enumerate(lines):
        if i < 1:
            continue
        cur_sp = sp_arr[i] if i < len(sp_arr) else None
        prior = lines[:i]
        prior_sps = sp_arr[:i]
        # ① 自己说X：X 须是「对方」（≠当前说话人）立过的规——同一句既含语境词又含子串，
        #   且说话人是对方。当前说话人自己的指责句（「你数到二就碰了」）不算出处。
        for m in _RE_SELF_SAID_QUOTE.finditer(ln):
            frag = re.sub(_STRIP, "", m.group(1))
            if len(frag) < 3:
                continue
            grounded = any(
                (cur_sp is None or p_sp != cur_sp)
                and _RE_STMT_FRAME.search(p_line)
                and any(
                    frag[k:k + run] in p_line
                    for run in (6, 5, 4, 3)
                    for k in range(len(frag) - run + 1)
                )
                for p_line, p_sp in zip(prior, prior_sps)
            )
            if not grounded:
                cons.append(f"回旋镖引话失据（自己说「{frag[:12]}」无出处）")
                break
        # ② 我说规则是X：X 先前若由对方立规，判错误归属；X 无任何陈述出处则并入引话失据
        for m in _RE_SELF_CLAIM_RULE.finditer(ln):
            frag = re.sub(_STRIP, "", m.group(1))
            if len(frag) < 3:
                continue
            rule_hits = [
                (p_line, p_sp)
                for p_line, p_sp in zip(prior, prior_sps)
                if _RE_STMT_FRAME.search(p_line)
                and any(
                    frag[k:k + run] in p_line
                    for run in (6, 5, 4, 3)
                    for k in range(len(frag) - run + 1)
                )
            ]
            if not rule_hits:
                cons.append(f"回旋镖引话失据（我说规则「{frag[:12]}」无出处）")
                break
            if cur_sp is not None and rule_hits[0][1] != cur_sp:
                cons.append(f"回旋镖错误归属（规则「{frag[:12]}」是对方立的）")
                break

    # 末句嘴硬话未呼应本场仪式判据（用户 2026-08-09 v25 抓）：本场判据是
    # 「举过头顶坚持三秒」，末句却用「比你早」——「早」比先后，本场比时长。
    echo = _closing_stubborn_echo_issue(lines)
    if echo:
        cons.append(echo)

    return cons


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat: Callable[[str], bool],
) -> tuple[int, list[str]]:
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    full_text = "".join(lines)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else full_text

    rr_pts, rr_pros = _rule_round_escalation_score(lines)
    if rr_pts >= 4:
        return rr_pts, rr_pros

    start, end = _mid_body_range(lines)
    flip_pts, flip_pros = _power_flip_bonus(lines[start:end])
    if flip_pts >= 3:
        return flip_pts, flip_pros

    # 字面加赛（赛规引用/竞争升级/反悔指责/赛规自噬）——C 类核心好笑模式
    if RE_LITERAL_RULE_PLAY.search(mid_text):
        return 5, ["字面加赛场面"]
    if RE_LITERAL_RULE_PLAY.search(late6):
        return 3, ["字面加赛场面"]
    # 可拍争法：争抢/占位/选/挪等通用竞争动作
    if _FILMABLE_TWIST.search(full_text):
        return 2, ["有可拍争法"]
    return 0, []


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    from app.services.daily_story.story_types.quality import (
        RE_BOOMERANG_RULE,
        RE_TWIST_SEGUE,
    )

    _ = speakers
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    late4_text = "".join(tail4)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else late4_text
    rr_pts, _ = _rule_round_escalation_score(lines)
    rule_round_mode = rr_pts >= 4
    theme_end = bool(lines) and _RE_THEME_STUBBORN_END.search(lines[-1])
    points = 0
    pros: list[str] = []
    if RE_BOOMERANG_RULE.search(late4_text):
        points += 3
        pros.append("回旋镖收束")
        if RE_TWIST_SEGUE.search(late6):
            twist_pts = 2 if rule_round_mode else 3
            points += twist_pts
            pros.append("字面回旋好笑")
        if RE_LITERAL_RULE_PLAY.search(late6):
            literal_pts = 1 if rule_round_mode else 3
            if literal_pts:
                points += literal_pts
                pros.append("字面加赛好笑")
    if theme_end and points >= 3:
        points += 1
        pros.append("主题嘴硬收尾")
    return points, pros


def humor_revision_hint(issue: str) -> str | None:
    if "开场理由复读" in issue:
        return (
            f"【C·开场理由】{issue}。"
            "正文禁用开场第 2 句已用过的理由：开场说过的理由全文不再重复，"
            "立理由的人正文换新角度顶嘴（谁先拿到/谁先翻开/书是大家的/"
            "你没看完别占着），禁止自己重申「搬回来的/买的/攒零花钱」；"
            "对方击穿（搬回来不算，拿到才算）可以，但理由出处只讲一次。"
        )
    if "肢体抢物复读" in issue:
        return (
            f"【好笑·C】{issue}。"
            "整件物中间段改「规则三轮升级」：靠着不算→整个抱→离地/单脚算不算，"
            "每轮一句新判据+灿灿照字面追问；删抢→掉→捡→卡缝循环。"
        )
    if "对方擅自改规" in issue:
        return (
            f"【好笑·C】{issue}。"
            "灿灿只执行+追问（算不算/哪条/你一条接一条说的），"
            "禁作废/这局不算/你乱拽；追加赛规只许立规人。"
        )
    if "C规则机制复读" in issue or "C规则缺权力翻转" in issue:
        return (
            f"【好笑·C】{issue}。"
            "整件物中间段只许3次规则升级：①谁先拿到 ②钻定义（靠着不算/得抱怀里）"
            "③荒谬一条（连续抱满三秒/得自己承认）——禁离沙发→双脚→单脚清单；"
            "灿灿中间加「哪条作数/还有吗/你一条接一条说的」翻转权力，"
            "末句嘴硬锚主题（你赢规则不算赢我）。"
        )
    if "归属口水战" in issue:
        return (
            f"【好笑·C】{issue}。"
            "删掉「归谁/你没叠」多轮；前 8 句内立一条可判定、可拍的赛规"
            "（如谁先碰到归谁、谁切谁选、先挖先得）。"
            "中段用量化或动作升级，勿空吵所有权。"
        )
    if "缺可拍争法" in issue:
        return (
            f"【好笑·C】{issue}。"
            "收束前加一件能拍的动作（按赛规字面加赛、"
            "或实物状态变化），再回旋镖扣原话；"
            "勿只靠「指一下/不算」口头诡辩。"
        )
    if "末句嘴硬比法漂移" in issue:
        return (
            f"【好笑·C】{issue}。"
            "末句嘴硬话锚定的比法必须字面在本场立规句里：最稳写「明天我一定赢过你！」"
            "（任何赛规都成立）；想收出彩可锚定赛规动词——赛规「举过头顶坚持三秒」→"
            "「明天我抢先举过头顶！」「明天我坚持到三秒给你看！」。"
            "禁「比你早/比你快」（时序，本场不比先后）、禁「比你举得久/比你高/"
            "比你标准」（时长/质量比较，本场是达标制，不比谁久/谁高）。"
        )
    if "伪回旋镖" in issue:
        return (
            f"【好笑·C】{issue}。"
            "破段改「规则漏字」反噬：立规人定的规则没写全（没规定数数要多快/没说不许"
            "晃/没规定谁数数），对方按字面利用漏字赢，赢家引原规反问（你刚说站满十秒，"
            "又没说数数要多快），末句输家嘴硬锚定仪式动词（明天我定规矩必须快数）。"
            "别写「我也站满了，你数啊」式平手收束。"
        )
    if "偏A式那不一样" in issue:
        return (
            f"【好笑·C】{issue}。"
            "末段用对方赛规反问，少用「那不一样」甩脱；"
            "破功方嘴硬收场即可。"
        )
    if any(k in issue for k in ("无出处", "模板", "拖沓", "末四拍", "好笑")):
        return (
            f"【好笑·C】{issue}。"
            "中段用一件具体争法升级；"
            "末段用对方规则回旋镖反问，末句嘴硬收场。"
        )
    from app.services.daily_story.story_types.c.facts import fact_revision_hint
    from app.services.daily_story.story_types.c.opening import opening_revision_hint

    return fact_revision_hint(issue) or opening_revision_hint(issue)
