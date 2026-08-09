"""C 类正文硬卡（收束形态、防写成 A 式末四拍）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_C_BARE_TONE_END,
    RE_C_LAST_BANNED,
    RE_C_STUBBORN_LAST,
    RE_REVELATION_PROP,
    RE_SOFT_LAST,
    RE_SURRENDER,
    RE_TWIST_SEGUE,
    c_closing_echo_error,
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
# 赛规漂移：换比法/重开的句（"重来""重新""换一种"等字面词）。
# 同一篇累计 ≥3 且全程无宣判句 → 判定规则被反复单方面推翻（无规则漂移），
# 与「换赛规须当场点破旧局」契约冲突（2026-08-07 专家定夺 3，见稿B 76分）。
# 注意：**不含「不算」**——C 稿「碰到手不算/后放上去不算/喊开始才动不算」
# 是质疑动作有效性，不是换比法（稿A 85/稿C 88 均含 3 次「不算」却非漂移）。
# 合法平局重赛豁免：稿中含「明明说/妈妈裁定/作废」等宣判句则放行（稿A 型）。
# **不含「数到[一二三几]」**（2026-08-09 用户+专家修正）：「我数三下同时动」
# 是对启动方式提公平条件（接规三选一 ②），不是换比法——RE_RULE_SWITCH 此前
# 把「数到二/三」合法启动误计为换比法，switches≥3 误拦整稿浪费重抽。真正的
# 时序判据（「数到一先摸的算」）由 _RE_SEQUENCE_CRITERION 另行拦截。
_RE_RULE_SWITCH = re.compile(r"重来|重新比|换一种|重新|再来")
_RE_RULE_VERDICT = re.compile(r"明明说|作废|重赛|妈妈|大人|宣判|点破|这次.*算|重来.*说好")
# 妈妈裁定被无视：妈妈已出场裁定赛规，末段须引用妈妈原规或让妈妈判决收束
# （2026-08-07 专家审 C 橡皮 92：L6 妈妈裁定后正文又吵 17 句，末段双方各说「我先」僵局）
_RE_MOM_RULING_REF = re.compile(
    r"妈妈(?:刚说|刚才说|说的|说的话|定的|定了|的话)|"
    r"妈(?:说|刚说|说的|定的)|按妈妈|听妈妈的|妈妈说的",
)
# 判据动词白名单（专家六轮 2026-08-07；2026-08-09 用户三连纠正定「接触弱词零容忍」）。
# 接触系（碰/摸/够/搭/挨/蹭/伸/探/点）接动作完成态（到/着/了/一下/上）**出现即漂移**——
# 不再要求带胜出裁定词：用户点名否决「按谁先碰到谁喝」「我先摸到的」「我手先搭上的，
# 我赢了」，弱接触词作判据/作自证/作击穿句（「碰到不算」）都不许，判据全程占有系
# （拿到/抢到/攥手里/翻开/坐上/举起）。「谁先拿到归谁」不中。操作系（按/打开/切换/调）
# /结果系（画面/屏幕/灯/声音+出来/亮了）+胜出裁定词 → 立即判据漂移（次级目标侵入）；
# 状态系当判据（松手/放手/撒手+算/输/赢/谁/该/归——「松手算输」「谁先松手谁输」）也漂移；
# 补连续占有状态（拿稳/拿住/攥住/攥牢/一直拿着——「谁先攥住谁就赢了」）当判据即漂移。
# 不含「掉/捡」（物态变化，回旋镖合法「掉地上不算拿到/捡起来才算」）、不含「攥手里」
# （「攥手里才算拿到」是占有完成标志，等价「拿到」）。分级杠精（「X不算，Y才算」逐级
# 发明新词 ≥2 次）由 _grading_bickering_error 拦截。
# 接触系弱词（碰/摸/够/搭/挨/蹭/伸/探/点）后缀：紧跟完成态（到/着/了/一下/上/过）
# 或「的」（我先碰的/我摸的——先X碰的漏网，2026-08-09 v10 稿），或插宾语后接了/过/的
# （碰我手了/摸一下）。「别碰我」这类无后缀词的施压句不命中。
# 「点」字歧义（2026-08-09 专家稿漏网）：点心/几点/点灯/点名/点头 是名词/时间词，
# 非接触动词，负向前瞻排除，防「当点心了」被误判成接触判据。
_RE_CONTACT_CRITERION = re.compile(
    r"(?:碰|摸|够|搭|挨|蹭|伸|探|点)(?![心几灯名头卯货将数子滴])"
    r"(?:(?:到|着|了|一下|上|过|的)|[^。！？]{1,2}(?:了|过|的))",
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
# 开场理由复读（用户定 2026-08-08 + 专家 2026-08-08）：正文不得变体重申开场已用过的
# 理由。逐字复述硬卡只拦逐字照抄，拦不住「我搬回来的，我自然有优先权」这类换说法重申。
# 检测是抽象不变量（非单篇词表）：取开场第 2 句（反对句）的「…的」理由段，正文中
# **同一说话人**的句子去虚字后含其 ≥4 字连续子串即判复读——只查立理由人自己炒冷饭；
# 对方击穿「搬回来不算」说话人不同（且「搬回来不算」不含「我搬回来」4 字串）不误伤。
_RE_REASON_STRIP = re.compile(r"[的话呢呀嘛吧啊哦嗯…\s「」『』“”\"'‘’：:，,、。！？是]")


def _opening_reason_repeat_error(
    lines: list[str],
    speakers: list[str],
) -> str | None:
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
    if len(core) < 4:
        return None
    frags = {core[i:i + 4] for i in range(len(core) - 4 + 1)}
    for ln, sp in zip(lines[2:], speakers[2:]):
        if sp != opp_sp:
            continue
        if any(frag in _RE_REASON_STRIP.sub("", ln) for frag in frags):
            return (
                f"C类开场理由复读：正文{opp_sp}变体重申开场理由「{reason[:14]}」"
                "（开场第2句已说过；同一理由全篇只许1次，被顶嘴方只能三选一——"
                "攻击对方规则/论证自己更强/补全新理由，禁止把开场理由换说法重申）"
            )
    return None


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
    r"(?:吃|咬|舔|喝|吞|尝|擦)(?:到|了|一下|完)?"
    r"[^。！？]{0,4}(?:(?<!不)(?:算|就算|算数)|该|归|赢|谁)",
)
# 开系判据（专家 2026-08-09 消耗品根治）：拧开/撕开/掰开/揭盖等「打开包装」操作当判据
# （「得先拧开盖子才算拿到」「谁先撕开包装谁吃」）——拧/撕是**拿到后的包装处理**，
# 不是占有，酸奶稿最常见的判据重构终点（占有→操作终点）。裁定词收敛同消耗系；
# 「我先拿到的，我拧开喝」等享用描述不带裁定词不命中。
_RE_OPEN_CRITERION = re.compile(
    r"(?:拧|撕|掰|揭)(?:开|掉|下来|完)?"
    r"[^。！？]{0,6}(?:(?<!不)(?:算|就算|算数)|该|归|赢|谁)",
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
    """判据动词白名单（专家六轮 2026-08-07；2026-08-09 用户三轮反馈定「零容忍」）。

    接触系当胜出主张（我先摸到→该我看）是失方自封弱判据；操作系（按到电视→就算）
    与结果系（画面没出来→不算）是次级目标侵入；状态/时序/消耗系同理。
    **2026-08-09 用户三连纠正（搭→碰→碰摸）：孩子判据只认占有系强动作，碰/摸/搭
    这类弱接触词**不作判据也不作自证**，出现即漂移**——即使紧跟击穿句也不豁免**
    （「按谁先碰到谁喝」「我先摸到的」「我手先搭上的，我赢了」都被用户点名否决）。
    命中即整稿重抽（含「X到不算」击穿句里的弱词——用户不要弱词，判据全程占有系：
    拿到/抢到/攥手里/翻开/坐上/举起）。「谁先拿到归谁」不中。分级杠精（「X不算，
    Y才算」逐级发明新词 ≥2 次）仍由 _grading_bickering_error 拦截。
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
        elif _RE_OPEN_CRITERION.search(ln):
            hit = "开系判据（拧开/撕开包装才算拿到）"
        elif _RE_CONTACT_CRITERION.search(ln):
            hit = "接触系弱判据（碰/摸/搭…→该/归/赢/谁）"
        if hit:
            return (
                f"C类判据漂移[{i}]：{hit}——判据/自证动词只许占有系"
                "（拿到/抢到/攥手里/翻开/坐上/举起）；碰/摸/搭/咬/吃/喝/拧/撕/按/松手/"
                "画面当判据即换赛规（用户 2026-08-09 定：弱接触词零容忍，命中即重抽，"
                "不豁免）；题面若含「按/打开/画面」等操作词只作冲突由头，正文判据一律"
                "翻成「谁先拿到归谁」，回旋镖落在抢到手/攥着/翻开"
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

    # 整篇交替发言（用户定 2026-08-08）：开场+正文合并后任意相邻两句须换人。
    # 常见漏网：body 承接开场续写时，第 1 句与开场末句（第 2 句）同人连说——
    # 开场「昭昭→灿灿」后 body 又由灿灿开讲。系统提示词的「严格交替」只约束
    # 正文内部，跨 opening 衔接这一跳不覆盖，故在此补机读硬卡。
    for i in range(1, n):
        if speakers[i] and speakers[i] == speakers[i - 1]:
            errors.append(
                f"C类对白须交替发言[{i}]：{speakers[i]}连说两句"
                "（含正文第1句与开场末句衔接处）；正文首句须由开场第2句的对立方"
                "开讲，全篇严格轮着说，禁止同人连说",
            )
            return

    # 正文复述开场台词（2026-08-08：body 首句照抄开场，或正文某句原样复读开场
    # 已说的台词/理由——「书是我搬回来的」开场说过、正文又逐字搬一遍）。
    # 开场强制 2 句，故 lines[:2] 即开场，正文从 lines[2] 起；去句末标点逐字比对，
    # 命中即整稿重抽（含虚字变体靠提示词约束，见 line.py「禁复用开场理由」）。
    if n >= 3:
        def _norm(s: str) -> str:
            return re.sub(r"[。！？…\s]+$", "", s or "").strip()

        head = (_norm(lines[0]), _norm(lines[1]))
        for j in range(2, n):
            if _norm(lines[j]) and _norm(lines[j]) in head:
                errors.append(
                    "C类正文不得原样复述开场台词（正文某句照抄了开场第 1/2 句）；"
                    "开场说过的理由/台词正文不逐字复用，须从新角度推进冲突",
                )
                return

    # 变体重申开场理由（专家 2026-08-08）：逐字复述硬卡只拦照抄，拦不住
    # 「我搬回来的，我自然有优先权」这类换说法重申——动态比对开场理由段
    # vs 正文同说话人句，命中即整稿重抽（不让 refine 硬修，避免引出判据漂移）。
    reason_repeat = _opening_reason_repeat_error(lines, speakers)
    if reason_repeat:
        errors.append(reason_repeat)
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
        RE_SOFT_LAST.search(last)
        or RE_SURRENDER.search(last)
        or RE_C_STUBBORN_LAST.search(last)
    ):
        errors.append(
            "C类末句须写完整或嘴硬话收场（认栽/撂狠话/退出等）",
        )
        return

    if RE_C_BARE_TONE_END.search(last):
        errors.append(
            "C类末句禁光杆叹词单字收尾（哼/行吧/算了），"
            "须一句有内容的嘴硬话（认栽不认输/撂狠话告状/情绪退出），"
            "如「行，算你手快！」「明天我比你早！」「那我不玩了！」",
        )
        return

    # 排除式：末句既非光杆叹词、又未命中禁词（赢家总结/解释/重分赃/发新规则）
    # 即视为被戳穿方合格的嘴硬话收场——不穷举口语变体
    # （LLM 会写「我告诉妈去」「那我不拆了」等，词表白名单会误拦）。
    if RE_C_LAST_BANNED.search(last):
        errors.append(
            "C类末句禁赢家总结/解释/重分赃/发新规则（你赢了/算你狠/归你了/因为…/"
            "籽归你西瓜归我/重新比），须被戳穿方一句嘴硬话收场——"
            "认栽不认输（行，算你手快）/撂狠话告状（明天我比你早，我告诉妈妈去）/"
            "情绪退出（那我不玩了）",
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

    closing_echo = c_closing_echo_error(lines)
    if closing_echo:
        errors.append(closing_echo)