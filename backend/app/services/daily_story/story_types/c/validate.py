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

# 正文首句「我早就不X了」顶回式无出处残句（v33 酸奶「不疼了」、v35「不怕凉了」）：
# 开场第 2 句没提出任何「你…X」弱项指控时，第 3 句用「早就不X」= 顶空——X 无出处即残句。
# 顶回式只在第 2 句真写过「你上次喝多肚子疼/你怕凉别喝」这类指控时才合法。
RE_EARLY_RETORT = re.compile(r"我早就不[^，。！]{1,12}了")
RE_WEAK_ACCUSE = re.compile(
    r"你.{0,10}(?:疼|痛|闹|怕|凉|慢|脏|坏|散|丑|矮|瘦|懒|磨蹭|挑食|贪|馋|"
    r"晕|腻|软|没长好|生病|哭|吵|笨|咳嗽|着凉|怕冷|怕热|胆小)",
)

# 逐字照抄正例硬卡（v35 酸奶稿抓：第 11-18 句整段复刻 line.py 酸奶合规示范 9-16 句）——
# 「仿照论辩骨架」不等于逐字复用；正例全文已进提示词，LLM 会直接搬，须机读兜底。
# 收录 line.py 81-97 行示范的中后段招牌句（去语气词/标点后）；正文 ≥2 句命中即整稿重抽。
_EXAMPLE_NORM_SKIP = re.compile(r"[的了吗呢啊呀哼！？。，、…\s「」“”\"'‘’：:]")
_C_EXAMPLE_PHARASES_NORM = {
    _EXAMPLE_NORM_SKIP.sub("", s)
    for s in (
        "我早就不闹肚子了",
        "酸奶又没写你名字谁先拿到谁喝",
        "我先抓到手都攥出汗了松开",
        "你攥那么紧瓶身都热了我攥着瓶盖呢我先拿的",
        "瓶盖也算那你把瓶身给我我喝的时候你拿盖儿玩",
        "不行整瓶都是我的你松开手",
        "你数三下我数到二你就松手咱们同时放",
        "好我喊到三就松手你可别提前抢",
        "谁抢谁小狗我数一二你手松了我拿到了",
        "你耍赖我还没喊三呢你二就动手了",
        "你刚说数到三就松手可我数到二你还没放",
        "我那是数到二准备松你倒好二还没落音就抢了",
        "我不管现在瓶子在我手里我先喝你等下喝汤",
        "你刚才说谁抢谁小狗你抢了你才是小狗",
        "那是我说的可你也没按规矩来你赖皮",
        "反正我先拿到的你抢了不算酸奶归我",
        "哼明天我比你早",
        # 2026-08-11 三方定稿 v52（慢数漏字反噬）中后段招牌句——禁逐字照抄
        "那咱俩说好谁攥着酸奶再单脚站满十秒酸奶归谁",
        "行你先站我数着数满十秒才算你",
        "一二三你腿别抖我慢慢数",
        "四五你只说站满十秒又没说数数要多快",
        "你这是耍赖我站不住快数到十",
        "六七八你脚落地没站满十秒",
        "是你数太慢我才倒不算",
        "你刚说站满十秒就算慢数也是数你输",
        "可你那是故意拖长音赖皮",
        "你刚说谁攥着酸奶单脚站满十秒归谁你输归我",
        "明天我定规矩必须快数你一个字也别想拖",
    )
}

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
# 立规人必须输硬卡（2026-08-11 专家/千问共识）：仪式判据场（单脚站/金鸡独立/
# 举过头顶/坚持X秒/站满十秒），找到第一条「仪式+胜负判定」立规句，其说话人
# 就是立规人（被戳穿方）——末句必须由 TA 嘴硬收场。v47 酸奶稿死这：灿灿立规
# 却灿灿赢、末句昭昭嘴硬，方向反了。转述式引话（你刚说谁先举过头顶坚持三秒
# 谁喝）的逐字出处由 facts 层兜底，这里只卡归属方向。
_RE_C_RITUAL_RULE_LINE = re.compile(
    r"(?:单脚站|金鸡独立|举过头顶|坚持.{0,4}秒|站满十秒|数满十秒).{0,8}"
    r"(?:归|算|才|谁|该)",
)
# 句尾语气词堆砌硬卡（2026-08-11 专家/千问共识：v47 第 3/4/7/10 句病句尾）：
# 与 c/humor 的 _RE_TONE_STACK 同源——「了呢了呀/着了呀/嘛了呀/好了呀/呢呀」
# 是病句尾，每句结尾语气词最多一个，全篇 ≥2 句命中即整稿重抽。
_RE_C_TONE_STACK_HARD = re.compile(
    r"(?:[呢嘛的了着好]{2,}呀|呢了|呢呀)[！。！？…]?$",
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
# 「够」字歧义（2026-08-11 酸奶稿误伤）：够着/够到/够上/够一下 是接触动词，但
# 攥够了/够了/够三秒 的「够」是程度副词（足够/撑够），非接触——从主词表剥离，
# 单独只认「够+完成态+胜出裁定词」才算判据（够到归我/够着算我攥住/够不着算我赢）；
# 回旋镖描述（你举起来我够不着/够不到/够不上）不带裁定词，不构成占有主张，放行。
# 接触系须落在判据/自证语境（2026-08-21 GPT+Run2）：「你数到二就伸手了」
# 是冲突动作描述，不是赛规——须带裁定词或「我先X到的」自证，否则不误触。
_RE_CONTACT_CRITERION = re.compile(
    r"(?:"
    r"(?:碰|摸|搭|挨|蹭|伸|探|点)(?![心几灯名头卯货将数子滴])"
    r"(?:(?:到|着|了|一下|上|过|的)|[^。！？]{1,4}(?:了|过|的))"
    r"[^。！？]{0,10}(?:不算|(?:(?<!不)(?:算|就算|算数)|该|归|赢|谁))|"
    r"我(?:手)?(?:先|已经)[^。！？]{0,4}"
    r"(?:碰|摸|搭|挨|蹭|伸|探|点)(?![心几灯名头卯货将数子滴])"
    r"(?:(?:到|着|了|一下|上|过|的)|[^。！？]{1,4}(?:了|过|的))"
    r")|"
    r"够(?:到|着|上|一下|得着)?[^。！？]{0,4}"
    r"(?:(?<!不)(?:算|就算|算数)|该|归|赢|谁)",
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
    r"[^。！？]{0,4}(?:(?<!不)算|输|赢|谁|该|归)|"
    r"(?:还没|没有|尚未|仍)[^。！？]{0,8}(?:松手|放手|撒手|松开|手松)",
)
# 松手仪式判据（2026-08-21）：「同时松手/数到三一起松/松手后谁先归谁」——
# 状态系+放弃控制，不是占有系公平判据；旧 _RE_STATE_CRITERION 窗口仅 4 字，
# 「同时松手，谁先抢到归谁」漏网，故单列抽象 pattern（非单篇词表）。
_RE_RELEASE_RITUAL = re.compile(
    r"同时(?:松手|放手|撒手|松)|"
    r"(?:一起|同时)(?:松手|放手|撒手|松)|"
    r"数到[一二三四五六七八九十\d]+[^。！？]{0,8}(?:一起)?松(?:手|)|"
    r"(?:松手|放手|撒手|松)[^。！？]{0,16}谁先",
)
# 开场理由复读（用户定 2026-08-08 + 专家 2026-08-08）：正文不得变体重申开场已用过的
# 理由。逐字复述硬卡只拦逐字照抄，拦不住「我搬回来的，我自然有优先权」这类换说法重申。
# 检测是抽象不变量（非单篇词表）：取开场第 2 句（反对句）的「…的」理由段，正文中
# **同一说话人**的句子去虚字后含其 ≥4 字连续子串即判复读——只查立理由人自己炒冷饭；
# 对方击穿「搬回来不算」说话人不同（且「搬回来不算」不含「我搬回来」4 字串）不误伤。
_RE_REASON_STRIP = re.compile(r"[的话呢呀嘛吧啊哦嗯…\s「」『』“”\"'‘’：:，,、。！？是]")
# 正文首句「X就X」接招（用户 2026-08-09 v27 酸奶稿抓）：「举就举，我举过头顶了」——
# 接招句式=回应一个比赛提议，但开场末句只做了占有宣告（我先拿到的，归我）、从没提议
# 比赛，正文首句凭空接一个不存在的比赛=凭空进入未立赛规。只有 X 字面出现在开场两句
# （开场真提议过这个动作）才合法。顶回理由/抛占有判据（正文首句两法）不带接招词不命中。
_RE_C_AGREE_CONTEST = re.compile(r"([一-鿿]{1,2})就\1")


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
# 切分/拆封即终结（2026-08-12 用户定）：蛋糕/食物等资源一旦切好/拆封，
# 禁止重切/恢复/重新比——切完的蛋糕物理上无法恢复，正文出现即重抽。
_RE_C_RECUT = re.compile(
    r"重新切|再切(?:一刀|一次|一回)?|切回来|恢复原样|重新比|重切一",
)
# 回旋镖直接引话（2026-08-12 定）：全文「你刚说/你刚才说/你自己说/你不是说」
# 式原话反问最多 2 次——中段最多 1 次、末段收束 1 次；「你说的」语义太泛不硬卡，
# 由 c/humor 观感层兜底。
_RE_C_BOOMERANG_QUOTE = re.compile(
    r"你刚说|你刚才说|你自己说|你不是说",
)
# 整件非消耗品误用分派型赛规（2026-08-21 batch）：抱枕/遥控器/枕头/马桶/橡皮
# 等争点须占有型或动作达标型，禁「我分你先挑/谁反悔谁小狗/切完你先挑」等分派骨架。
_RE_WHOLE_ITEM_ANCHOR = re.compile(
    r"抱枕|靠垫|遥控器|枕头|马桶|橡皮",
)
_RE_DISPATCH_RULE = re.compile(
    r"我分你(?:先)?(?:挑|选)|谁反悔谁小狗|我拆箱你清点|"
    r"切完(?:你)?(?:先)?挑|我切你选|我搬你摆|分完(?:你)?(?:先)?挑",
)
_RE_CUT_FOOD_THEME = re.compile(
    r"蛋糕|披萨|切好|切完|切开|切块|分.{0,2}(?:蛋糕|块)",
)


def c_criterion_theme_profile(anchor: str) -> str:
    """C 判据链选题：cut_food | whole_item | default。"""
    text = anchor or ""
    if _RE_CUT_FOOD_THEME.search(text):
        return "cut_food"
    if _RE_WHOLE_ITEM_ANCHOR.search(text):
        return "whole_item"
    return "default"


# 整件物 Stage3/姿势升级禁独立身体仪式（类型级，非主题词表；专家 2026-08-21）
_RE_C_WHOLE_ITEM_RITUAL = re.compile(
    r"数到[一二三四五六七八九十\d]+|数.{0,3}[三3]|"
    r"单脚站|金鸡独立|站满.{0,4}秒|数满十秒|"
    r"十秒|转.{0,2}圈|闭眼|蛙跳|蹲下举手",
)


def c_whole_item_ritual_in_line(line: str) -> bool:
    """整件物题：计时/计数/平衡仪式出现在判据句 → 非法。"""
    return bool(_RE_C_WHOLE_ITEM_RITUAL.search(line or ""))


def c_criterion_rule_reject_reason(profile: str, rule: str) -> str | None:
    """判据链单条规则是否与本题 profile 冲突；冲突则返回原因码。"""
    if profile == "whole_item" and _RE_DISPATCH_RULE.search(rule):
        return "whole_item_dispatch"
    if profile == "whole_item" and re.search(
        r"单脚站|金鸡独立|举过头顶|坚持.{0,4}秒|站满十秒|数满十秒",
        rule,
    ):
        return "whole_item_ritual"
    if profile == "cut_food" and re.search(
        r"单脚站|金鸡独立|举过头顶|站满十秒|数满十秒",
        rule,
    ):
        return "cut_food_ritual"
    return None
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
            "C类赛规漂移：全文换比法/重开 ≥3 次（重来/重新比/换一种）且无人宣判旧局，"
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


def _whole_item_dispatch_error(story: dict, lines: list[str]) -> str | None:
    """整件物题面误套分派型赛规（我分你先挑/谁反悔谁小狗等）→ 硬卡重抽。"""
    anchor = (
        str(story.get("theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return None
    hits = [
        i + 1
        for i, ln in enumerate(lines)
        if _RE_DISPATCH_RULE.search(ln)
    ]
    if not hits:
        return None
    shown = ",".join(str(i) for i in hits[:3])
    more = "…" if len(hits) > 3 else ""
    return (
        f"C类整件物误用分派型赛规（第{shown}句{more}）："
        "抱枕/遥控器/枕头/马桶/橡皮等整件争点须占有型（谁先拿到/攥手里）"
        "或动作达标型（谁先举起/坐到），禁「我分你先挑/谁反悔谁小狗/切完你先挑/"
        "我切你选/我拆箱你清点」——分派型只限已切好/已分盘的食物（蛋糕/披萨）"
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
        if _RE_RELEASE_RITUAL.search(ln):
            hit = "松手仪式判据（同时松手/数到三一起松/松手后谁先）"
        elif _RE_RESULT_CRITERION.search(ln):
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

    # 正文首句凭空进入未立赛规（用户 2026-08-09 v27 酸奶稿抓）：「举就举，我举过头顶了」
    # 以接招句式回应一个比赛，但开场两句从没提议过「举」这个比赛（开场末句只做了占有
    # 宣告/理由反对）——正文首句合法形式只有两法（顶回开场末句理由+抛占有判据 /
    # 已拿到者宣示占有），接招不在其列；接招只许回应开场第 2 句真提议过的动作。
    if n >= 3:
        m = _RE_C_AGREE_CONTEST.search(lines[2])
        if m and m.group(1) not in (lines[0] + lines[1]):
            errors.append(
                f"C类正文首句凭空进入未立赛规：第 3 句「{lines[2][:16]}」以接招句式"
                f"（{m.group(1)}就{m.group(1)}）回应比赛，但开场两句从没提议过"
                f"「{m.group(1)}」——正文首句只能顶回开场末句的反对理由或抛占有判据，"
                "接招须是开场第 2 句真提议过的动作才有得接",
            )
            return

    # 正文首句「我早就不X了」顶回无出处（v33 酸奶「不疼了」、v35「不怕凉了」）：
    # 开场第 2 句没提过「你…X」弱项指控时，「早就不X」顶的是没人说过的理由——残句。
    # 合法前提：第 2 句真写过「你上次喝多肚子疼/你怕凉别喝」类指控才可用顶回式；
    # 否则正文首句只能顶回真实理由或直接抛占有判据。
    if n >= 3 and RE_EARLY_RETORT.search(lines[2]) and not RE_WEAK_ACCUSE.search(lines[1]):
        errors.append(
            f"C类正文首句无出处残句：第 3 句「{lines[2][:16]}」用「早就不X」顶回，"
            f"但开场第 2 句「{lines[1][:16]}」没提过「你…X」类弱项指控——X 无出处即残句；"
            "正文首句只能顶回第 2 句真写出的理由（有指控才顶），否则直接抛占有判据"
            "（酸奶又没写你名字，谁先拿到归谁）",
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

    # 句尾语气词堆砌（用户 2026-08-09 v6 病句尾；2026-08-11 升硬卡，v47 酸奶稿
    # 第 3/4/7/10 句「了呢了呀/嘛了呀/了吗了啊」）：每句结尾语气词最多一个，
    # 全篇 ≥2 句连叠即病句，整稿重抽（观感层 humor 已有同源检测兜底）。
    tone_hits = [
        i + 1 for i, ln in enumerate(lines) if _RE_C_TONE_STACK_HARD.search(ln)
    ]
    if len(tone_hits) >= 2:
        shown = ",".join(str(i) for i in tone_hits[:4])
        more = "…" if len(tone_hits) > 4 else ""
        errors.append(
            f"C类句尾语气词堆砌（第{shown}句{more}）：「了呢了呀/着了呀/嘛了呀/"
            "好了呀/呢呀」是病句尾——每句结尾语气词最多一个（我先拿到的！/我攥手里"
            "了！/该我！），全篇禁连叠堆砌，整稿重抽",
        )
        return

    dispatch_on_whole = _whole_item_dispatch_error(story, lines)
    if dispatch_on_whole:
        errors.append(dispatch_on_whole)
        return

    criterion_drift = _criterion_drift_error(lines)
    if criterion_drift:
        errors.append(criterion_drift)
        return

    recut_hits = [
        i + 1 for i, ln in enumerate(lines) if _RE_C_RECUT.search(ln)
    ]
    if recut_hits:
        shown = ",".join(str(i) for i in recut_hits[:4])
        more = "…" if len(recut_hits) > 4 else ""
        errors.append(
            f"C类切分即终结（第{shown}句{more}）：资源一旦切好/拆封，"
            "禁止重切/恢复/重新比——切完的蛋糕物理上无法恢复；"
            "开篇已切好只能争「谁先挑/拿哪块」，回旋镖扣「切完你先挑」"
        )
        return

    # 逐字照抄正例（v35 酸奶稿抓）：≥2 句与 line.py 酸奶合规示范逐字重复即整段复刻。
    # 开场两句（场景定格）除外——「姐姐，冰箱里最后一瓶酸奶给我喝吧」式开场是通用模板。
    copy_hits = [
        f"第{j + 1}句「{ln}」"
        for j, ln in enumerate(lines[2:], 2)
        if _EXAMPLE_NORM_SKIP.sub("", ln) in _C_EXAMPLE_PHARASES_NORM
    ]
    if len(copy_hits) >= 2:
        errors.append(
            "C类正文逐字照抄正例（" + "；".join(copy_hits) + "）："
            "正例只许仿照论辩骨架与句式，禁逐字复用原句——须换自己的措辞，"
            "整段搬正例中后段即废稿",
        )
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

    # 立规人必须输（2026-08-11 硬卡）：仪式判据场，第一条「仪式+判定」立规句的
    # 说话人 = 立规人 = 被戳穿方 = 末句嘴硬的人；立规人赢任何一轮判定即方向反了
    # （酸奶稿 v47 死这：灿灿立规却末句昭昭嘴硬）。
    if last_sp in ("昭昭", "灿灿"):
        for _i, _ln in enumerate(lines):
            if _RE_C_RITUAL_RULE_LINE.search(_ln):
                _maker = speakers[_i] if _i < len(speakers) else ""
                if _maker and _maker != last_sp:
                    errors.append(
                        f"C类立规人必须输：仪式立规句（第{_i + 1}句「{_ln[:14]}」）"
                        f"由「{_maker}」提出，末句却由「{last_sp}」嘴硬收场——"
                        "立规人（被戳穿方）须是末句说话人；立规人赢任何一轮判定"
                        "即方向反了（酸奶稿 v47 死这：灿灿立规却末句昭昭嘴硬）",
                    )
                    return
                break

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

    boom_hits = [
        i + 1 for i, ln in enumerate(lines) if _RE_C_BOOMERANG_QUOTE.search(ln)
    ]
    if len(boom_hits) >= 3:
        shown = ",".join(str(i) for i in boom_hits[:4])
        more = "…" if len(boom_hits) > 4 else ""
        errors.append(
            f"C类回旋镖重复（第{shown}句{more}共{len(boom_hits)}次）："
            "全文「你刚说/你刚才说/你自己说/你不是说」式原话反问最多 2 次，"
            "中段最多 1 次、末段收束 1 次；同一承诺只许引 1 遍"
        )
