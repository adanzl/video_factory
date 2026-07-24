"""日常故事矛盾类型（A–E）各自写作线路与观感打分特征。"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Sequence

STORY_TYPE_LABELS: dict[str, str] = {
    "A": "权威翻车",
    "C": "公平执念",
    "D": "字面执行",
    "B": "结盟翻车",
    "E": "妈妈破功",
}

STORY_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "A": frozenset(
        {
            "管", "教", "作业", "不许", "应该", "必须", "听我的", "你小", "大人",
            "谁怕", "写错", "管教", "指正", "功课", "练琴", "手机", "规矩",
            "辈分", "姐姐说", "得听", "批评", "顶嘴", "磨蹭",
        },
    ),
    "C": frozenset(
        {
            "争", "抢", "分", "谁先", "最后一", "平分", "归谁", "哪个",
            "大战", "之战", "马桶", "抱枕", "酸奶", "蛋糕", "橡皮",
        },
    ),
    "D": frozenset(
        {"弄", "撒", "碎", "掉了", "帮忙", "收拾", "照做", "叮嘱", "按", "照", "叠", "鞋带"},
    ),
    "B": frozenset(
        {"一起", "偷偷", "瞒", "藏", "约定", "联手", "别告诉", "俩", "暗号", "零食"},
    ),
    "E": frozenset({"妈妈", "问妈", "告状", "跟妈", "叫妈妈", "讲理"}),
}

_TYPE_CATALOG_LINE = (
    "【矛盾类型一览】A权威翻车 / C公平执念 / D字面执行 / "
    "B结盟翻车 / E妈妈破功；生成时会锁定其中一种并走该类型专属线路。"
)


@dataclass(frozen=True)
class StoryTypeLine:
    code: str
    label: str
    keywords: frozenset[str]
    prompt_block: str
    user_closing: str
    punchline_example: str
    layer_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    quality_ready: bool
    escalation_revision_hint: str
    closing_revision_hint: str
    body_user_anchor: str = ""
    opening_system_append: str = ""
    opening_user_append: str = ""
    theme_user_append: str = ""
    retry_soft_close_hint: str = ""


def _compile_layers(
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((label, re.compile(pat)) for label, pat in pairs)


_LINE_C = StoryTypeLine(
    code="C",
    label="公平执念",
    keywords=STORY_TYPE_KEYWORDS["C"],
    quality_ready=True,
    punchline_example="C类公平执念，姐姐规则被字面戳穿",
    prompt_block="""\
【本次类型：C 公平执念 — 专属线路】
- 公式：双方抢同一资源→各自抛对己有利的规则→规则互相冲突
  （你先拿 vs 我先看 / 你切你选 vs 你拿你就选了）
  →一方规则被字面执行反噬或两套规则产生荒谬结论→收束。
- 笑点：每个人在「自己的规则下」都对，两套公平标准无法兼容。

【节奏·升级路线（C 专用，须逐步推进）】
1 争归属（谁先碰/谁的）→ 2 挑战规则（你的规则不算）
→ 3 挑战权威（凭什么你定）→ 4 推出新证据 → 5 收束
每一层最多 2 个来回；超过须立刻进下一层；后半程须进入 4、5 层。

【笑点与收束（C 专用）】
- 优先回旋镖：用对方刚立的规则原路反问，逼出自相矛盾。
- 正例：昭昭「你自己说切的人先选，那你切的你选，我拿大的就行」
  →灿灿「我没说切的人先选大的」→灿灿「……哼，给你」。
- 末句须破功方（被戳穿/嘴硬）说最后一句，禁止赢家总结陈词。
""",
    user_closing="""\
9. 【C类收束模板·必遵守】末尾 4 句（[主题词]替换成当前争论的实物）：
   倒数第4句：用对方刚说的规则反问他（例："你自己说切的人先选，那你切你选，我拿大的"）
   倒数第3句：对方狡辩露馅（例："我没说切的人先选大的……"）
   倒数第2句：点出矛盾（例："那你说'切的人先选'是什么意思？"）
   末句：对方嘴硬收场（"……哼/……行/……随便"），必须他说最后一句
""",
    layer_patterns=_compile_layers(
        [
            (
                "C1_争归属",
                r"凭什么.*拿|怎么在.*你手|我先|归谁|凭什么.*你的|你抢|"
                r"应该给我|我要.*块|我吃.*的|谁先|拿.*大|大的.*我|我大.*我吃",
            ),
            (
                "C2_挑战规则",
                r"谁说的|没说过|不算|你定的|你刚说|你编的|规矩|切的人|"
                r"拿到的人|谁说|又不是你定的|规则是你|反悔|变来变去|"
                r"说话不算|凭什么.*定|你说的不算|你自己.*又说",
            ),
            (
                "C3_挑战权威",
                r"凭什么你|你说了算|你又不是|你是姐姐|你凭什么|"
                r"不是.*说了算|又不是你|你定.*不算|我比你大|"
                r"大的该给|大的.*应该|大的.*给.*小|按年龄|我是姐姐",
            ),
            (
                "C4_新证据",
                r"上次|之前|上一次|妈妈说过|爸爸.*说|柜子里|第二块|"
                r"还有.*块|烤箱|里面还有|等等.*说|说过什么|你再想想|"
                r"记得.*说|谁说.*洗碗|谁先.*洗碗|吃大.*洗碗|吃完.*洗碗|"
                r"上次.*分|上次.*说|上次.*梨|上次.*规则",
            ),
            (
                "C5_收束",
                r"那.*你还|你还要|还是吃|我不要|我才不|你洗碗|那你吃|"
                r"说不过|反正我|就是|不管了|给你|那给你|下次.*算|"
                r"哼|算了算了|归我|归你|大的归|自相矛盾|嘴硬",
            ),
        ],
    ),
    escalation_revision_hint=(
        "【C·冲突升级】插入 2–4 句：先抛各自有利规则，再让一方用字面逻辑"
        "反推对方规则（你先拿/我先看类），形成双标或荒谬结论。"
    ),
    closing_revision_hint=(
        "【C·收束】倒数 3–4 句走回旋镖：用对方刚说的规则反问"
        "（切的人先选/先碰到归谁），末句被戳穿方嘴硬（……哼/……行）。"
    ),
)

_LINE_A = StoryTypeLine(
    code="A",
    label="权威翻车",
    keywords=STORY_TYPE_KEYWORDS["A"],
    quality_ready=True,
    punchline_example="A类权威翻车，灿灿管教双标被昭昭引先例追问闭环戳穿",
    prompt_block="""\
【本次类型：A 权威翻车 — 专属线路】
- 核心：灿灿用「姐姐/大人」身份立规矩；好笑点是**她的规矩或原话当场反噬**，
  不是抢东西、不是弟弟吵赢。
- 公式：亮权威→追问→**本场一锤（可拍画面）**→灿灿露馅/加例外并**埋一句可引用原话**
  →末四拍收束（引用→那不一样→哪里不一样→哼）。

【本场一锤（必写，好笑根基）】
- 正文 L2–L3 须出现**一场面级细节**，与 theme 同一件事，观众能想象画面：
  算式与得数（如 36+57 算出 93）、弹错哪个音、哪道题写错等；**也可不用数字**，
  用动作/器物/态度双标当一锤。
- **可核对事实**：一旦写出钟点、时长、算式、遍数等，全剧只认一套数，勿前后改起点或改口；
  没写具体数字则不必硬编钟点。
- 中段抬杠须围着这一锤升级；禁止通篇只辩论「我是姐姐」「你得听我的」而无新事实。
- 同一旧账（折纸、上次查资料）**最多提 1 次**；再要加码须换证据或回到本场一锤。

【禁止写成别的类型】
- 禁止 C 式抢同一物品、争先后、分大小；禁止昭昭空喊「不公平」当主笑点。
- 禁止 D 式字面执行当主线；禁止开场或全文「一人一半」「妈妈判赢」。

【节奏·升级路线（A 专用，每层≤2 来回）】
1 亮权威：指令/指正（勿复读「听我的」超过 2 次）
2 字面追问：凭什么、你算给我看、你又不是老师
3 **一锤落地**：姐姐当场出错/双标/被打脸（用数字、动作、器物写清）
4 埋句：灿灿亲口说一句≤14 字、可被后文照引的原话（例外/不算数/就得听我的）
5 末四拍收束（见下，四句缺一即不合格）

【末四拍收束（硬约束，顺序不可跳）】
- 倒数第4：昭昭「你刚才说/你自己说 + **前文灿灿原话**」
- 倒数第3：灿灿「那不一样……」（狡辩区分）
- 倒数第2：昭昭「哪里不一样？都是听/都是……」（**全文仅此一处**）
- 末句：灿灿「……哼/行吧/随便」（必须灿灿说）
- 禁止从「意外/肯定对」等闲聊**直接跳到**「哪里不一样」；收束前须已无话可说。

【对白语气】
- 灿灿：装小大人；被追问时加例外，越描越黑。
- 昭昭：冷静盘问，引用原话；不喊不公平、不总结「我赢了」。
- 妈妈：≤2 句旁听，不判赢。

【正例骨架（教作业）】
- 前提：36+57 正确得数是 **93**；昭昭若写 92 才是错。
- 一锤：灿灿骂昭昭 92 不对，自己板书却写成 **94**（或口算说 91），
  竖式一列被昭昭拆穿——**必须是灿灿的数真算错**，不能把 93 当错。
- 埋句：灿灿「我错一次就不算数」。
- 收束：昭昭引这句 →「那不一样」→「哪里不一样」→灿灿哼。

【教作业/算术（硬约束）】
- 正文 **第 1 句** 须灿灿在查/教/挑错（如「这题怎么写 92」），
  禁止昭昭开场「你也错了/也算错了」——没有「也」的前文。
- 发现开场可与正文首句同人，但勿与正文首句完全重复；
  优先灿灿开口点题，昭昭第二句不服。
- 凡写加法式子：先定正确得数，再写灿灿说错的那个数；
  竖式/口算前后须一致，禁止姐姐其实算对却装翻车。
""",
    user_closing="""\
9. 【A类正文锚定】首句须灿灿管教/指正（查作业、挑错、立规矩）；
   禁止昭昭首句「你也/也算错了」；禁止无指代的「也」。
10. 【A类·本场一锤】L2–L3 可画细节；若用数字/时刻/算式作场面锚，全文须自洽。
    教作业时灿灿须有一处**真算错**的得数（与正确得数不同），竖式与口算勿矛盾。
11. 【A类·埋句】L3–L4 灿灿须有一句≤14 字、可逐字被末段引用的原话；
    禁止收束引用正文未出现的句子；禁止默认「大人也要听小孩」。
12. 【A类·末四拍】末尾连续 4 句 speaker 顺序：昭昭→灿灿→昭昭→灿灿，
    台词功能依次为：引用前文原话 / 那不一样 / 哪里不一样 / 哼或行吧。
    「哪里不一样」全篇只此一处；倒数第3 句必须含「那不一样」。
13. punchline_explain 以「A类权威翻车」开头，写明一锤是什么、引用了哪句原话。
""",
    body_user_anchor="""\
1. 【A类·主题锚定】管教/指正/立规矩（教作业、练琴、手机、收拾房间）。
   首句锚定管教动作；并规划「本场一锤」（如自己算错题、自己弹错音）。
   例：「姐姐教弟弟写作业自己写错」→ 首句灿灿挑题；
   一锤=灿灿把 36+57 说成 94（正确 93）。
""",
    opening_system_append="""\

【A 类开场补充】
- 片头先让观众看见管教现场（动作/物），再进入抬杠；勿把正文后半段的反击、双标对比挪到开场。
- 正例：灿灿「说了作业写完才能碰手机」；昭昭「你又抱着手机笑半天了，还说我磨蹭」。
- 反例：「谁先洗澡」「酸奶你怎么开了」（那是 C，不是 A 开场）。
- 禁止开场末句直接甩「我是姐姐我说了算」（留到正文互怼）。
""",
    opening_user_append="""\
本场为 A 权威翻车：发现开场先点管教现场（动作/物），勿预支正文才成立的反击或对比。
""",
    theme_user_append="""\

【本次只出 A 类主题】姐姐管教/指正/立规矩，弟弟不服或被反问到哑口。
适合场景：教作业、练琴、玩手机、收拾房间、说话态度、乱动姐姐东西（注意是「管」不是「抢」）。
禁止：争先后、分东西、抢遥控器、谁先洗澡、分蛋糕、瞒妈妈结盟、妈妈讲理主线。
示例："姐姐嫌弟弟刷牙太快"
示例："教弟弟系鞋带一直系反"
示例："批评弟弟吃饭吧唧嘴"
""",
    retry_soft_close_hint=(
        "【A·好笑】若无「本场一锤」（算错数/弹错音/双标动作等），在中段补一场面细节。"
        "【A·事实】写了钟点、时长或算式须全剧一致；约定X分钟且才Y分钟时勿说时间到了。"
        "【A·埋句】补灿灿一句≤14字可引用原话。"
        "【A·末四拍】末4句必须：昭昭引原话→灿灿那不一样→昭昭哪里不一样→灿灿哼；"
        "禁止跳过「那不一样」或空降「哪里不一样」。"
    ),
    layer_patterns=_compile_layers(
        [
            (
                "A1_亮权威",
                r"我是姐姐|你得听|听我的|我比你大|比你大|我说了算|"
                r"你得|应该听|大人|我教你|我管",
            ),
            (
                "A2_字面追问",
                r"凭什么|为什么|哪里不一样|谁说的|又不算|"
                r"你也|你不也|那你也",
            ),
            (
                "A3_规则露馅",
                r"那不一样|刚说|没说|不算|你定的|反悔|变卦|"
                r"我是教你|不是那个意思",
            ),
            (
                "A4_引先例",
                r"上次|之前|上一次|妈妈说过|你也|明明说|"
                r"你不是说|你自己也|你也这样",
            ),
            (
                "A5_破功收束",
                r"哼|算了|行吧|随便|说不通|认栽|好吧|"
                r"不管了|那行",
            ),
        ],
    ),
    escalation_revision_hint=(
        "【A·一锤】补一场面细节：数字/动作/器物，让灿灿当场露馅。"
        "【A·埋句】灿灿亲口一句≤14字可被「你刚才说」引用；同一旧账勿重复。"
    ),
    closing_revision_hint=(
        "【A·末四拍】昭昭引前文原话→灿灿「那不一样」→昭昭「哪里不一样」"
        "→灿灿哼；四句缺一即改。禁止未引原话直接「哪里不一样」。"
    ),
)

_LINE_D = StoryTypeLine(
    code="D",
    label="字面执行",
    keywords=STORY_TYPE_KEYWORDS["D"],
    quality_ready=False,
    punchline_example="D类字面执行，叮嘱方为补救违反自己立的规矩被回旋镖",
    prompt_block="""\
【本次类型：D 字面执行 — 专属线路（初版）】
- 公式：一方立叮嘱/规矩→另一方按字面严格执行→后果跑偏
  →原叮嘱方为收拾残局被迫违反自己的规矩→执行方用其规则回旋镖收束。
- 关键：不能只写到「搞砸了傻眼」，须叮嘱方自陷矛盾后再被反堵。

【节奏·升级路线（D 专用）】
1 立规矩 → 2 字面执行 → 3 后果跑偏 → 4 叮嘱方违规补救 → 5 回旋镖收束

【收束】执行方用对方原话点破「你自己说的，你现在也破了」；末句叮嘱方嘴硬。
""",
    user_closing="""\
9. 【D类收束模板】末尾 3–4 句：点出叮嘱方为补救而违反自己立的规矩，
   末句叮嘱方（灿灿或妈妈，视谁立的规）嘴硬收场。
""",
    layer_patterns=_compile_layers(
        [
            ("D1_立规矩", r"不许|别碰|不能|应该|要|得|规矩|叮嘱|说了"),
            ("D2_字面执行", r"照做|按你说的|你不是说|字面|打开|碰了|动了"),
            ("D3_后果跑偏", r"掉了|滑|洒|乱|坏|打不开|饿着|够不着"),
            ("D4_违规补救", r"我来|我捡|我弄|只好|只能|没办法"),
            ("D5_回旋镖", r"你自己说|你刚才|你现在|你也|不算吗"),
        ],
    ),
    escalation_revision_hint="【D·升级】补一层「字面执行搞砸现场」再让叮嘱方被迫破规。",
    closing_revision_hint="【D·收束】用叮嘱方原话回旋镖，末句叮嘱方嘴硬。",
)

_LINE_B = StoryTypeLine(
    code="B",
    label="结盟翻车",
    keywords=STORY_TYPE_KEYWORDS["B"],
    quality_ready=False,
    punchline_example="B类结盟翻车，姐弟瞒妈计划互相甩锅一起露馅",
    prompt_block="""\
【本次类型：B 结盟翻车 — 专属线路（初版）】
- 公式：姐弟联手瞒妈妈/钻空子→执行中露馅→互相甩锅→一起暴露。
- 主戏仍是姐弟；妈妈可在末段撞见，禁止妈妈长篇讲理。

【节奏】1 结盟约定 → 2 执行走样 → 3 互相甩锅 → 4 露馅收场
""",
    user_closing="""\
9. 【B类收束】末 3–4 句：互相「都怪你」后同时露馅（妈妈撞见或证据落地），
   末句一方嘴硬仍想甩锅。
""",
    layer_patterns=_compile_layers(
        [
            ("B1_结盟", r"一起|咱俩|别告诉|瞒|约定|联手|暗号"),
            ("B2_走样", r"怎么|不对|坏了|露馅|看见|听到了"),
            ("B3_甩锅", r"都怪你|是你|你先|不是我|你答应"),
            ("B4_露馅", r"妈妈|完了|糟糕|抓到了|露馅"),
        ],
    ),
    escalation_revision_hint="【B·升级】加一轮执行走样与互相甩锅，别只吵联盟分工。",
    closing_revision_hint="【B·收束】露馅后一方仍嘴硬甩锅，末句破功方说。",
)

_LINE_E = StoryTypeLine(
    code="E",
    label="妈妈破功",
    keywords=STORY_TYPE_KEYWORDS["E"],
    quality_ready=False,
    punchline_example="E类妈妈破功，妈妈讲理被孩子字面追问绕进去",
    prompt_block="""\
【本次类型：E 妈妈破功 — 专属线路（初版）】
- 公式：妈妈想讲道理/立规矩→孩子字面追问或连环反例→妈妈自己先破功。
- 妈妈台词可略多（建议≤5句），但笑点须在妈妈逻辑自相矛盾。

【节奏】1 妈妈立论 → 2 孩子追问 → 3 妈妈改口 → 4 孩子闭环 → 5 妈妈破功
""",
    user_closing="""\
9. 【E类收束】末 3–4 句：孩子用妈妈刚说的话反问，末句妈妈破功（……唉/……行行行）。
""",
    layer_patterns=_compile_layers(
        [
            ("E1_妈妈立论", r"妈妈|应该|必须|规矩|听我的|我说"),
            ("E2_孩子追问", r"为什么|凭什么|那你|你也|上次"),
            ("E3_妈妈改口", r"不是|不一样|那是|总之|反正"),
            ("E4_闭环", r"你自己说|你刚才|那你也是"),
            ("E5_妈妈破功", r"唉|行了|好吧|随便|说不通"),
        ],
    ),
    escalation_revision_hint="【E·升级】加连环追问，逼妈妈改口一次。",
    closing_revision_hint="【E·收束】孩子闭环反问，末句妈妈破功。",
)

STORY_TYPE_LINES: dict[str, StoryTypeLine] = {
    r.code: r
    for r in (_LINE_A, _LINE_B, _LINE_C, _LINE_D, _LINE_E)
}

# 解析不到类型标签时的默认质检配置（与 C 公平执念一致）
QUALITY_FALLBACK_CODE = "C"


def story_line_for_code(code: str) -> StoryTypeLine:
    return STORY_TYPE_LINES.get(code.upper(), _LINE_C)


def parse_story_type_code(
    *,
    story_type: str | None = None,
    punchline: str | None = None,
) -> str:
    if story_type:
        m = re.match(r"^([ABCDE])", story_type.strip())
        if m:
            return m.group(1).upper()
    text = punchline or ""
    for k in ("A", "B", "C", "D", "E"):
        if f"{k}类" in text or f"{k}：" in text:
            return k
    return QUALITY_FALLBACK_CODE


def story_type_tag(code: str) -> str:
    c = code.upper()
    return f"{c}类{STORY_TYPE_LABELS[c]}"


def select_story_type_tag(theme: str) -> str:
    """按主题关键词选类型；无匹配时在已校准类型 A/C 中随机。"""
    scores = {
        k: sum(1 for kw in line.keywords if kw in theme)
        for k, line in STORY_TYPE_LINES.items()
    }
    max_score = max(scores.values())
    if max_score <= 0:
        candidates = ["A", "C"]
    else:
        candidates = [k for k, v in scores.items() if v >= max_score]
    if not candidates:
        candidates = ["A", "C"]
    selected = random.choice(candidates)
    return story_type_tag(selected)


def layer_patterns_for_story(story: dict | None) -> tuple[tuple[str, re.Pattern[str]], ...]:
    if not isinstance(story, dict):
        return _LINE_C.layer_patterns
    code = parse_story_type_code(punchline=str(story.get("punchline_explain") or ""))
    return story_line_for_code(code).layer_patterns


def revision_hints_for_type(code: str) -> tuple[str, str]:
    line = story_line_for_code(code)
    return line.escalation_revision_hint, line.closing_revision_hint


def type_catalog_system_block() -> str:
    return _TYPE_CATALOG_LINE


def format_block_for_code(code: str) -> str:
    line = story_line_for_code(code)
    return f"""\
【格式要求】
严格输出以下JSON结构：
{{
  "scene_title": "不超过10字，场记或口语钩子均可",
  "setting": "一句话说明地点和初始冲突动作",
  "conflict_core": "≤24字，谁vs谁争什么",
  "dialogue": [
    {{"speaker": "昭昭", "line": "台词（≤18字）"}},
    {{"speaker": "灿灿", "line": "台词"}},
    {{"speaker": "妈妈", "line": "台词（宜少）"}}
  ],
  "punchline_explain": "{line.punchline_example}"
}}
妈妈可有台词，但宜少（建议≤3句）；主回合仍是姐弟。
"""
