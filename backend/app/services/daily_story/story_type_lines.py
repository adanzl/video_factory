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
- 核心：灿灿用「姐姐/大人」身份立规矩、管教、指正；笑点不是抢东西，而是规则说不圆。
- 公式：亮权威→弟弟字面追问（凭什么/哪里不一样）→姐姐改口或加例外
  →弟弟引先例/生活细节揭双标→姐姐破功。
- conflict_core 须写「谁管/教谁、因什么事」（≤24 字），勿写成「抢/分/谁先」。

【禁止写成别的类型】
- 禁止 C 式抢同一物品、争先后、分大小、切蛋糕选大的。
- 禁止 D 式「把叮嘱照字面做砸」当主线（那是另一方钻空子，不是管教翻车）。
- 禁止开场或全文主冲突变成「一人一半」「妈妈来判」。

【节奏·升级路线（A 专用，须逐步推进）】
1 亮权威：我是姐姐/你得听/我教你/我比你大（最多 2 来回，勿复读）
2 字面追问：凭什么、为什么、谁说的、你又不是妈妈（最多 2 来回）
3 规则露馅：那不一样、我是教你、不是那个意思、刚不是说（最多 2 来回）
4 引先例（后半段必出）：须先由灿灿或妈妈在前文说过可被引用的原话
  （双标、例外、旧账），昭昭收束再点名；禁空降「妈妈说过你也…」而无前文。
5 破功收束：弟弟用前文原话追问闭环→姐姐嘴硬/认输，末句必须灿灿说

【对白语气】
- 灿灿：装小大人、爱下结论，被追问时会加「例外」但越描越黑。
- 昭昭：不吵不闹，连环追问；用姐姐**本场刚承认**的话反堵，不喊「不公平」空话。
- 妈妈：可不写；若写 ≤2 句旁听，禁止判赢、禁止一人一半。

【笑点与收束（A 专用）】
- 收束用「追问闭环」，不用 C 的切蛋糕回旋镖。
- 正例（注意 L4 先埋句再收）：
  中段灿灿「大人说话小孩也得听啊」（已出口）
  →后段昭昭「你刚才说大人说话小孩也得听」
  →灿灿「那不一样我是教你」→昭昭「哪里不一样？都是听」
  →灿灿「……哼，随便」
- 反例：前文从未提「听小孩」，末句硬套「大人也要听小孩」——不好笑、违规。
- 末句 speaker 必须是灿灿（权威方破功），禁止昭昭总结「我赢了」。
""",
    user_closing="""\
9. 【A类正文锚定】首 2 句须是管教现场：灿灿下指令/指正，或昭昭反抗「凭什么你听我的」；
   禁止首句抢物品、争洗澡顺序、分零食。
10. 【A类收束模板·必遵守】末尾 4 句：
   倒数第4句：昭昭抛**前文已出现**的一句原话（例：前文灿灿说过
   「查资料可以久一点」，此处「你刚才说查资料可以久一点」）
   禁止引用正文没说过的话；禁止默认套「大人也要听小孩」除非前文埋过。
   倒数第3句：灿灿区分「那不一样」（例："那不一样，我是教你"）
   倒数第2句：昭昭闭环（例："哪里不一样？都是听"）——此句式全文仅末段一次
   末句：灿灿嘴硬（"……哼/……行吧/……随便"），必须灿灿说最后一句
11. 【A类·埋句】在 L3–L4 须让灿灿亲口说出一句可被收束引用的话
   （承认双标、加例外、甩锅妈妈），昭昭末段才能「你刚才说…」。
12. punchline_explain 必须以「A类权威翻车」开头，并写明引用了前文哪句、末句如何破功。
""",
    body_user_anchor="""\
1. 【A类·主题锚定】主题须是「管教/指正/立规矩」类小事（教作业、练琴、玩手机、收拾房间）。
   setting、conflict_core、正文首句须锚定该管教动作，勿写成抢东西、争先后。
   例：「姐姐教弟弟写作业自己写错」→ core「姐弟教作业谁说了算」、首句「这题我刚教过你」。""",
    opening_system_append="""\

【A 类开场补充】
- 抓住「姐姐正在管/教/挑错」或「弟弟不服管」的瞬间，不是抢物品。
- 正例：主题「教作业写错」→昭昭「姐你这道题好像也错了」
  主题「不许玩手机」→灿灿「说了作业写完才能碰手机」
  主题「练琴磨蹭」→灿灿「琴还没练你玩什么玩」
- 反例：「谁先洗澡」「酸奶你怎么开了」（那是 C，不是 A 开场）。
- 禁止开场末句直接甩「我是姐姐我说了算」（留到正文互怼）。
""",
    opening_user_append="""\
本场为 A 权威翻车：开场只点管教现场（教、管、不许、写错、练琴等），勿写成抢/分/谁先。
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
        "【A·收束】只改末 3–4 句：倒数第4句只能引用前文 dialogue 里"
        "灿灿/妈妈已说过的半句；若无埋句，先在 L3–L4 补灿灿一句可引用原话再收。"
        "灿灿「那不一样」→昭昭「哪里不一样」仅收束用一次；末句灿灿哼/行吧。"
        "禁止抢东西、一人一半、等妈评理、禁止空降「大人也要听小孩」。"
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
        "【A·冲突升级】在 L3–L4 插入 2–3 句具体旧账，并让灿灿亲口说出"
        "一句可被后文引用的话（双标/例外/「就得听我的」类），"
        "再让昭昭末段「你刚才说…」；禁止只复读「我是姐姐」。"
    ),
    closing_revision_hint=(
        "【A·收束】末 4 句：昭昭「你刚才说」须指向前文真实台词；"
        "灿灿「那不一样」→昭昭「哪里不一样」→灿灿哼/行吧；末句必须灿灿。"
        "若缺埋句，先在中段补灿灿原话再改收束，禁止套未出现的金句。"
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
