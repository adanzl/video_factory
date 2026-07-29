"""D 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)

RE_LITERAL = re.compile(
    r"照做|按你说的|照你说的|你不是说|字面|按规矩|你让我|你说要",
)
RE_MESS = re.compile(
    r"掉了|滑落|滑掉|洒|弄乱|乱了|乱成|全乱|坏了|打不开|饿着|够不着|弄翻|摔|"
    r"倒了|全掉|洒一地|堆塌|解不开|勒|死结|死疙瘩|大马趴|溢|变形",
)
# 定位「一锤搞砸」句：勿把开场「乱七八糟」当成后果
_RE_MESS_BEAT = re.compile(
    r"倒了|掉了|全掉|掉地上|洒|滑落|滑掉|堆塌|解不开|死结|溢|"
    r"弄翻|全乱|变形了|夹变形|撑变形",
)
RE_FIX = re.compile(
    r"我来扶|我来捡|我来弄|我自己来|我来夹|我来收|我来擦|我来晾|"
    r"只好|没办法|用力夹|用力扯|夹紧|夹得?更?紧|"
    r"擦地|抹布|我擦|扫进|一把扫|我自己浇|我自己关|我自己夹",
)
# 收束回旋镖：勿用共享「你说的」，会误伤「按你说的」字面句
RE_BOOM_CLOSE = re.compile(
    r"你自己说|你刚才说|你刚说|你现在也|你也碰了|你也动了",
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
    r"不是让你|我让你.{0,6}不是|要平放|别往高|别垒|别堆高|"
    r"别码高|你理解错|我说的是|我是说",
)
# 回旋镖引的规矩，须能在叮嘱方补救动作里对上「她也破了」
_BOOM_VIOLATION_PAIRS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (re.compile(r"轻|慢"), re.compile(r"用力|重|猛|摔|砸|扯|拽|扫")),
    (re.compile(r"别碰|不许碰|不准碰|别动"), re.compile(r"碰|扶|捡|拿|摸|弄")),
    (re.compile(r"别夹|太紧|夹紧"), re.compile(r"夹紧|夹得?更?紧|更紧|用力夹|用力扯|用力捏")),
    (re.compile(r"别浇|别多|一小口|倒一次"), re.compile(r"擦|浇|倒|抹|冲")),
    (re.compile(r"别弄乱|整齐|平放|别乱翻"), re.compile(r"弄乱|乱了|乱成|扒乱|翻乱|扫乱|堆乱")),
    (re.compile(r"关.*轻|轻.*关|别响"), re.compile(r"用力关|摔门|砰|响")),
)

# 中段开讨论会：确认/辩字义，没有动作升级 → 演进无意义，不好玩
_RE_DEF_TALK = re.compile(
    r"是不是|不就是|难道不是|听见了没有|记住没|什么叫|"
    r"你说的是|我理解|算不算轻|算不算",
)
# 字面动作递进：中段至少要有两档升级痕迹
_RE_ESCALATE = re.compile(
    r"再|又|第二|第三|两下|三口|第三圈|更高|更松|更轻|太松|太紧|"
    r"第一块|第二块|第三块|下一件|再叠|再绕|再夹|再倒|再放|"
    r"一点点|只夹|只放|再试|又滑|又掉|还是",
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
    ("中段抠定义", 4),
    ("中段缺动作升级", 4),
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
    if def_talk_n >= 2:
        cons.append("中段抠定义无升级，不好玩")
    elif def_talk_n >= 1 and escalate_n < 2 and len(body) >= 4:
        # 有辩字义却几乎没有递进动作
        cons.append("中段缺动作升级，不好玩")
    elif escalate_n < 1 and len(body) >= 6:
        cons.append("中段缺动作升级，不好玩")

    if n > 16:
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

    if sum(1 for ln in body if _RE_ASK_PERMIT.search(ln)) >= 2:
        cons.append("执行方句句求同意，不好笑")

    mom_n = sum(1 for sp in (speakers or []) if sp == "妈妈")
    if mom_n > 0:
        cons.append("妈妈插话不好笑")

    boom_n = sum(1 for ln in lines if RE_BOOM_CLOSE.search(ln))
    if boom_n >= 2:
        cons.append("回旋镖复读，不好笑")

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

    soft_indices = [
        i
        for i, ln in enumerate(lines)
        if re.search(r"哼|算了|行吧", ln)
    ]
    if len(soft_indices) >= 2 and soft_indices[0] < n - 3:
        # 中段已哼/算了，后面又开第二场
        if any(RE_BOOM_CLOSE.search(lines[i]) for i in range(soft_indices[0] + 1, n)):
            cons.append("二次收束注水，不好笑")

    return cons


def closing_quote_haystack(
    lines: list[str],
    speakers: list[str] | None,
    body_text: str,
) -> str:
    """D 收束引话只认灿灿前文叮嘱，不认昭昭自报。"""
    if not speakers or len(speakers) != len(lines):
        return body_text
    body_n = len(lines[:-4]) if len(lines) > 4 else max(0, len(lines) - 1)
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
            "成片压到 ≤16 句（正文 ≤14 句）：合并中段重复回合，"
            "把删掉的字补进保留句（每句写足 ≤24 字）；"
            "立叮嘱→字面→搞砸→破规→回旋镖链勿动。"
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
            "删掉搞砸前灿灿的纠正句（不是让你垒塔/要平放/别往高）；"
            "叮嘱只说一次，让字面误解一路跑到倒/洒，回头再发现。"
        )
    if "抠定义" in issue or "缺动作升级" in issue or "不好玩" in issue:
        return (
            f"【好笑·D】{issue}。"
            "中段改成同一误解的动作递进：第一块/第二块/第三块（或再叠、再绕、再夹），"
            "删掉「是不是/不就是/记住没」讨论会；让观众只看动作就知道下一步会倒。"
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
