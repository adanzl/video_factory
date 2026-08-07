"""C 类好笑维硬伤、场面加分与修订 hint。"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_TWIST_SEGUE,
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
    r"(?:耍赖|作弊|反悔|赖皮|说话不算|不算数|变来变去|改口|"
    r"你.{0,3}(?:赖|骗|反悔|不算))|"
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

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("归属口水战", 5),
    ("偏A式那不一样", 6),
    ("缺可拍争法", 7),
    # 2026-08-07 专家对齐 C2：回旋镖引话无出处 → 好笑分封顶 6
    ("回旋镖引话失据", 6),
    # 2026-08-07 专家对齐 C2 扩展：把对方立的规安到自己头上 → 好笑分封顶 6
    ("回旋镖错误归属", 6),
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


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    sp_arr = list(speakers) if speakers else []
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
