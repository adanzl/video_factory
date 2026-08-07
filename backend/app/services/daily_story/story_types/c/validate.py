"""C 类正文硬卡（收束形态、防写成 A 式末四拍）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_SOFT_LAST,
    RE_SURRENDER,
    RE_TWIST_SEGUE,
)

# A 类末四拍标志性组合（C 稿勿全套照搬）
RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩|大人要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
# 末句须收完整（24 字/句限制下尤忌写到一半）
RE_C_LINE_END_OK = re.compile(
    r"(?:[。！？…]|哼|行吧|随便|好吧|算了|认了|你赢|我先|你先|算了算)",
)
# 赛规漂移：换比法/重开的句（"数到三""重来""重新""换一种"等字面词）。
# 同一篇累计 ≥3 且全程无宣判句 → 判定规则被反复单方面推翻（无规则漂移），
# 与「换赛规须当场点破旧局」契约冲突（2026-08-07 专家定夺 3，见稿B 76分）。
# 注意：**不含「不算」**——C 稿「碰到手不算/后放上去不算/喊开始才动不算」
# 是质疑动作有效性，不是换比法（稿A 85/稿C 88 均含 3 次「不算」却非漂移）。
# 合法平局重赛豁免：稿中含「明明说/妈妈裁定/作废」等宣判句则放行（稿A 型）。
# 数到[一二三几]：v10b 用「数到一」换时序判据，单列「数到三」漏网。
_RE_RULE_SWITCH = re.compile(r"重来|重新比|数到[一二三几]|换一种|重新|再来")
_RE_RULE_VERDICT = re.compile(r"明明说|作废|重赛|妈妈|大人|宣判|点破|这次.*算|重来.*说好")
# 妈妈裁定被无视：妈妈已出场裁定赛规，末段须引用妈妈原规或让妈妈判决收束
# （2026-08-07 专家审 C 橡皮 92：L6 妈妈裁定后正文又吵 17 句，末段双方各说「我先」僵局）
_RE_MOM_RULING_REF = re.compile(
    r"妈妈(?:刚说|刚才说|说的|说的话|定的|定了|的话)|"
    r"妈(?:说|刚说|说的|定的)|按妈妈|听妈妈的|妈妈说的",
)
# 判据动词白名单（专家六轮，2026-08-07）：胜出/归属主张的判据动词必须属占有系。
# 接触系（碰/摸/够/搭/挨/蹭/伸/探/点）+胜出裁定词（该/归/赢/看/就算/算数/谁）
#   → 判据漂移——失方自封弱判据（「我先摸到→该我看」）；「X到不算」击穿豁免（不含裸「算」，
#   故「碰到不算」不中）。操作系（按/打开/切换/调）/结果系（画面/屏幕/灯/声音+出来/亮了）
#   +胜出裁定词 → 立即判据漂移（次级目标侵入，无一豁免）。
# 状态系当判据（松手/放手/撒手+算/输/赢/谁/该/归——「松手算输」「谁先松手谁输」）也漂移；
# 补连续占有状态（拿稳/拿住/攥住/攥牢/一直拿着——「谁先攥住谁就赢了」与「拿稳」同类，
# 草莓稿 67 漏网，2026-08-07）：是连续谱状态不是瞬时不可逆占有变更，当判据即漂移。
# 不含「掉/捡」（物态变化，回旋镖合法「掉地上不算拿到/捡起来才算」）、
# 不含「攥手里」（「攥手里才算拿到」是占有完成标志的击穿句，等价「拿到」），
# 「松手+不算」豁免。
# 只打「动词类+胜出裁定」结构，不按单篇剧情词表；「谁先拿到归谁」不中。
_RE_CONTACT_CRITERION = re.compile(
    r"(?:碰|摸|够|搭|挨|蹭|伸|探|点)(?:到|着|了|一下|上)"
    r"[^。！？]{0,4}(?:该|归|赢|看|就算|算数|谁)",
)
_RE_OPERATE_CRITERION = re.compile(
    r"(?:按|打开|切换|调)(?:到|着|了|一下)?"
    r"(?:电视|按钮|频道|音量|静音|开关|键)?"
    r"[^。！？]{0,6}(?:该|归|赢|看|就算|算数|谁)",
)
_RE_RESULT_CRITERION = re.compile(
    r"(?:(?:画面|屏幕|灯|声音|动画|频道|音量)[^。！？]{0,5}"
    r"(?:出来|亮了|响了|有|没出|没有|不出|来了)|"
    r"出(?:了)?(?:画面|屏幕|动画))"
    r"[^。！？]{0,4}(?:该|归|赢|看|就算|算数|算|谁)",
)
_RE_STATE_CRITERION = re.compile(
    r"(?:松手|放手|撒手|拿稳|拿住|攥住|攥牢|一直拿着)"
    r"[^。！？]{0,4}(?:(?<!不)算|输|赢|谁|该|归)",
)
# 时序判据（v10b 新漏网向量）：把胜负系在「动/跑/抢跑/出手/先数到」等时序动作上
# （「我先动算赢」「谁先跑谁赢」「数到一才准动」），而非占有系动作。动/跑/出手
# 只描述动作先后，不构成占有。「你抢跑，不算」击穿豁免（(?<!不)）。
_RE_SEQUENCE_CRITERION = re.compile(
    r"(?:抢跑|先动|先跑|先出手|先数到|谁先动)[^。！？]{0,4}(?:(?<!不)(?:算|赢|归|该)|谁|输)|"
    r"(?:动|跑)(?:了|着)?[^。！？]{0,3}(?:算赢|算我赢|归我|该我|算你赢|算输)",
)
# 消耗系判据（专家评审冰棍稿，2026-08-07）：咬到/吃到/舔到/喝到/吞下等**消耗/破坏
# 资源状态**的动作当胜出判据（「谁先咬到谁吃」「我咬到了该我吃」）——咬一口冰棍后
# 资源不可逆改变，「重来/重新比」在物理上不成立（对比分蛋糕「谁切谁选」：切/选是
# 分割非消耗，资源保持完整可回溯），是继接触/操作/结果/状态/时序后的第六类漂移向量。
# 与接触系同规则：「X到不算」当场击穿（咬到不算，拿到才算）豁免（(?<!不)）；完整消耗
# 终点赛规「谁先吃完/喝光」不受影响（吃完就结束，不搭配重来）。「谁先拿到谁吃」的
# 吃是拿到后的结果描述，不命中。裁定词收敛为 该/归/赢/谁/就算/算数/(?<!不)算，
# 不含「看」（你看/我看/看动画片 语义太泛易误伤）。
_RE_CONSUME_CRITERION = re.compile(
    r"(?:吃|咬|舔|喝|吞|尝)(?:到|了|一下|完)?"
    r"[^。！？]{0,4}(?:(?<!不)(?:算|就算|算数)|该|归|赢|谁)",
)
# 分级杠精（专家三轮，2026-08-07）：模型把任何「双方同时执行、争完成度」的动作展开成
# 连续谱（碰→抓→攥→拿稳；坐到→坐稳→坐实；撕开→撕多少；倒满→戳进→接着），逐级发明
# 新判据词。结构特征 = 「X不算，Y才算」（或倒装「Y才算，X不算」）比较型杠精句成对出现。
# 合法击穿句（「碰到不算，拿到才算」当场击穿）只许 1 次；**≥2 次**即分级杠精漂移，整稿
# 重抽。动作词表覆盖手部接触（碰/摸/搭/勾/抓/攥/握/拿稳）与动作仪式（坐/撕/削/倒/举/戳/
# 坐稳/坐实/坐上去/撕开/削出/倒满/举起来/戳进）。不含切/分/挑/搬/摆/拆——动作分派型
# （我切你选/我分你先挑）是专家三轮治本方向，其合法对白「你选吧/你先挑/摆好就行」不得误伤。
_RE_GRADING_BICKER = re.compile(
    r"(?:碰|摸|搭|勾|抓|攥|握|拿稳|坐稳|坐实|坐上去|撕开|削出|倒满|"
    r"举起来|戳进|坐|撕|削|倒|举|戳)"
    r"[^。！？]{0,8}(?:不算[^。！？]{0,8}才算|才算[^。！？]{0,8}不算)",
)


def _rule_drift_error(lines: list[str]) -> str | None:
    """规则漂移：切换句 ≥3 且无宣判句 → 硬卡（整稿重抽）。"""
    switches = sum(1 for ln in lines if _RE_RULE_SWITCH.search(ln))
    verdicts = sum(1 for ln in lines if _RE_RULE_VERDICT.search(ln))
    if switches >= 3 and verdicts == 0:
        return (
            "C类赛规漂移：全文换比法/重开 ≥3 次（数到三/不算/重来）且无人宣判旧局，"
            "规则被反复单方面推翻；只许一次平局重赛，换规须当场点破旧局"
        )
    return None


def _mom_ruling_ignored_error(
    speakers: list[str],
    lines: list[str],
) -> str | None:
    """妈妈裁定被无视：妈妈出场后，末 3 句须引用妈妈原规或由妈妈本人判决。

    稿B 型错误（专家审 C 橡皮 92）：妈妈 L6 裁定「谁先碰到谁用」后正文又吵
    17 句，末段灿灿「我先碰」/昭昭「我先碰」僵局无人判定。
    末 3 句含妈妈 speaker（妈妈结尾判决）或含「妈妈说/刚说」引用都放行。
    """
    if "妈妈" not in speakers:
        return None
    if "妈妈" in speakers[-3:]:
        return None
    tail3 = "".join(lines[-3:])
    if _RE_MOM_RULING_REF.search(tail3):
        return None
    return (
        "C类：妈妈已出场裁定赛规，末段须引用妈妈原规作决胜证据"
        "（妈妈说/刚说…）或让妈妈本人判决收束，禁止双方末段各说「我先」僵局无人判定"
    )


def _grading_bickering_error(lines: list[str]) -> str | None:
    """分级杠精硬卡（专家三轮，2026-08-07）：「X不算，Y才算」比较型杠精句 ≥2 次。

    模型把任何「双方同时执行、争完成度」的动作展开成连续谱（碰→抓→攥→拿稳；坐稳→
    坐实；撕开→撕多少；倒满→戳进），逐级发明新判据词，是 C 类 FAIL 稿主引擎。
    合法击穿句（「碰到不算，拿到才算」当场击穿抢占理由）只许 1 次；≥2 次即分级杠精
    漂移，整稿重抽。配合「动作分派型铁律」（我切你选/我分你先挑）——分派型对白
    （你选吧/你先挑/摆好就行）不命中词表，不受影响。
    """
    full = "".join(lines)
    n = len(_RE_GRADING_BICKER.findall(full))
    if n >= 2:
        return (
            f"C类分级杠精漂移[{n}]：「X不算，Y才算」分级辩论 ≥2 次——动作完成度是连续谱"
            "（碰到/抓到/攥住/拿稳，坐到/坐实/撕开/撕多少），逐级发明新判据词即换赛规；"
            "击穿抢占理由只许 1 句「X到不算，拿到才算」，之后回到占有/分派主线，"
            "不许再细分；赛规应优先动作分派型（我切你选/我分你先挑/我搬你摆），"
            "冲突靠规则字面反噬（选走大块/挑走多的）而非争动作完成度"
        )
    return None


def _criterion_drift_error(lines: list[str]) -> str | None:
    """判据动词白名单（专家六轮，2026-08-07）：胜出/归属主张的判据动词必须属占有系。

    接触系当胜出主张（我先摸到→该我看）是失方自封弱判据；
    操作系（按到电视→就算）与结果系（画面没出来→不算）是次级目标侵入。
    任一命中即判据漂移，整稿重抽。「X到不算」击穿（碰到不算，拿到才算）
    因不含胜出裁定词而豁免；「谁先拿到归谁」不中。分级杠精（「X不算，Y才算」
    逐级发明新词 ≥2 次）由 _grading_bickering_error 另行拦截。
    """
    for i, ln in enumerate(lines):
        hit: str | None = None
        if _RE_RESULT_CRITERION.search(ln):
            hit = "结果系判据（画面出来/灯亮/有声音才算）"
        elif _RE_OPERATE_CRITERION.search(ln):
            hit = "操作系判据（按到电视/按键就算）"
        elif _RE_STATE_CRITERION.search(ln):
            hit = "状态系判据（松手/放手算输）"
        elif _RE_SEQUENCE_CRITERION.search(ln):
            hit = "时序判据（我先动/谁先跑/抢跑算输）"
        elif _RE_CONSUME_CRITERION.search(ln):
            hit = "消耗系判据（谁先咬到/吃到/喝到→该谁吃）"
        elif _RE_CONTACT_CRITERION.search(ln):
            hit = "接触系当胜出主张（我先摸到→该我看）"
        if hit:
            return (
                f"C类判据漂移[{i}]：{hit}——判据动词只许占有系"
                "（拿到/抢到/抓到手/攥着）；碰/摸/咬/吃/按/松手/画面当判据即换赛规；"
                "题面若含「按/打开/画面」等操作词只作冲突由头，正文判据一律翻成"
                "「谁先拿到归谁」，回旋镖落在掉地上/捡起来/抢到手；"
                "接触系/消耗系抢占理由用「X到不算，拿到才算」当场击穿"
            )
    return None


def _line_incomplete(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s[-1] in "'\"‘’「」":
        return True
    if s.count("'") % 2 == 1 or s.count('"') % 2 == 1:
        return True
    if s.count("「") != s.count("」"):
        return True
    if RE_C_LINE_END_OK.search(s[-4:]):
        return False
    if RE_SOFT_LAST.search(s) or RE_SURRENDER.search(s[-8:]):
        return False
    if s[-1] in "呀嘛啊呢吧了哼":
        return False
    return not bool(re.search(r"[。！？…]$", s))


def _dialogue_lines(story: dict) -> tuple[list[str], list[str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], []
    lines: list[str] = []
    speakers: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if not ln:
            continue
        speakers.append(sp)
        lines.append(ln)
    return lines, speakers


def _closing_ok(tail4: str, tail3: str) -> bool:
    if RE_BOOMERANG_RULE.search(tail4) or RE_BOOMERANG_RULE.search(tail3):
        return True
    if RE_REVELATION_PROP.search(tail4) and (
        RE_TWIST_SEGUE.search(tail3) or RE_BOOMERANG_RULE.search(tail4)
    ):
        return True
    return False


def append_c_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("C类正文过短，不足以完成公平执念收束（至少约 8 句对白）")
        return

    criterion_drift = _criterion_drift_error(lines)
    if criterion_drift:
        errors.append(criterion_drift)
        return

    grading = _grading_bickering_error(lines)
    if grading:
        errors.append(grading)
        return

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""

    if last_sp == "妈妈":
        errors.append("C类末句须姐弟一方嘴硬收场，禁止妈妈收束")
        return

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "C类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
            "应走回旋镖或实物反转",
        )
        return

    for ln in lines[-3:-1]:
        if _line_incomplete(ln):
            errors.append(
                "C类收束对白须写完整（每句≤24字且以。！？或哼/行吧等收束，"
                "禁止停在引号或未说完）",
            )
            return

    if not _closing_ok(tail4, tail3):
        errors.append(
            "C类末段须有回旋镖（用对方刚立的规则反问）"
            "或实物真相反转收束",
        )
        return

    if _line_incomplete(last) and not (
        RE_SOFT_LAST.search(last) or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须写完整或嘴硬软收（哼/行吧/给你/算了等）",
        )
        return

    if not (
        RE_SOFT_LAST.search(last)
        or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须被戳穿方嘴硬软收（哼/行吧/给你/算了等），"
            "禁止赢家总结或继续立规矩",
        )
        return

    if len(speakers) >= 2 and speakers[-1] == speakers[-2]:
        errors.append("C类收束末两句须换人，禁止同人连说")
        return

    drift = _rule_drift_error(lines)
    if drift:
        errors.append(drift)

    mom_ignored = _mom_ruling_ignored_error(speakers, lines)
    if mom_ignored:
        errors.append(mom_ignored)