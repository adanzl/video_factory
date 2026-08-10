"""C 类好笑维硬伤、场面加分与修订 hint。"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_TWIST_SEGUE,
    c_closing_echo_error,
)

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
)


def ground_closing_quote(fragment: str, haystack: str) -> bool:
    frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,]", "", fragment)
    hay = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:，,]", "", haystack)
    if len(frag) < 3:
        return True
    if "更急" in frag and "更急" in hay:
        return True
    if "先选" in frag and "先选" in hay:
        return True
    if "公平" in frag and "公平" in hay:
        return True
    if "先到" in frag and ("先到" in hay or "先拿" in hay):
        return True
    if re.search(r"碰|弄乱|收拾|叠", frag) and re.search(
        r"碰|弄乱|收拾|叠|规矩|赛规", hay,
    ):
        return True
    if ("就算" in frag or "不算" in frag) and ("规矩" in hay or "算" in hay):
        return True
    run = min(6, len(frag))
    for i in range(len(frag) - run + 1):
        if frag[i:i + run] in hay:
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
    return c_closing_echo_error(lines)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    sp_arr = list(speakers) if speakers else []
    reason_issue = _opening_reason_repeat_issue(lines, sp_arr)
    if reason_issue:
        cons.append(reason_issue)
    tone_hits = [i + 1 for i, ln in enumerate(lines) if _RE_TONE_STACK.search(ln)]
    if tone_hits:
        first = ",".join(str(i) for i in tone_hits[:4])
        more = "…" if len(tone_hits) > 4 else ""
        cons.append(f"句尾语气词堆砌（第{first}句{more}，禁叠「呢了呀/着了呀/嘛了呀」病句尾）")
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
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    late4_text = "".join(tail4)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else late4_text
    points = 0
    pros: list[str] = []
    if RE_BOOMERANG_RULE.search(late4_text):
        points += 3
        pros.append("回旋镖收束")
        if RE_TWIST_SEGUE.search(late6):
            points += 3
            pros.append("字面回旋好笑")
        if RE_LITERAL_RULE_PLAY.search(late6):
            points += 3
            pros.append("字面加赛好笑")
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
