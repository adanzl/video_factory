"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

import copy
import json
import re

from app.services.daily_story.story_type_lines import (
    STORY_TYPE_LINES,
    STORY_TYPE_LABELS,
    format_block_for_code,
    parse_story_type_code,
    select_story_type_tag,
    story_line_for_code,
    story_type_tag,
    type_catalog_system_block,
)
from app.services.daily_story.cast import DAILY_CAST_NAMES

# 角色外貌固定描述，供 visual_style 和分镜生成共享
# 昭昭与灿灿有参考图，妈妈无参考图独立定义
DAILY_STORY_CHARACTERS = (
    "昭昭：7岁男孩，男孩气黑色超短发"
    "（发长须在耳垂以上、清晰露出双耳及整个后颈，齐耳学生头/圆寸感；"
    "禁止女童波波头、齐肩短发、厚刘海遮额、马尾），"
    "圆脸，穿蓝色短袖T恤，比灿灿矮约半个头；"
    "灿灿：10岁女孩，单侧高马尾（仅一根，禁止双马尾/麻花辫/披发），"
    "穿粉色卫衣，比昭昭高约半个头"
)

# 妈妈无参考图，外貌特征由 LLM 在 image_prompt 中文字描述，不混入有参考图角色常量
DAILY_STORY_CHARACTER_MOM = "妈妈：成年女性，黑色长发，米色上衣牛仔裤"

# 片长：语速约 3.6 字/秒、目标约 1:30–2:00
# 全文/正文硬卡不变；首稿提示词写作目标约 +100，抵消偏短（写长了靠校验/重试压回）
DAILY_STORY_TOTAL_CHARS_MIN = 300
DAILY_STORY_TOTAL_CHARS_MAX = 400
DAILY_STORY_TOTAL_CHARS_TARGET_MAX = 380
DAILY_STORY_BODY_CHARS_MIN = 280
DAILY_STORY_BODY_CHARS_MAX = 370
# 还差≤此值：句内补字微调，勿按偏短插入多句重写
DAILY_STORY_RETRY_PATCH_DEFICIT_MAX = 32
# 首稿直接瞄准硬卡中段（勿先写到 390+ 再压，易反复重试）
DAILY_STORY_BODY_WRITE_TARGET_MIN = 310
DAILY_STORY_BODY_WRITE_TARGET_MAX = 350
DAILY_STORY_LINE_CHARS_MAX = 22
DAILY_STORY_OPENING_LINES_MIN = 1
DAILY_STORY_OPENING_LINES_MAX = 2

# 开场钩子仅作提示词约束，不做关键词硬卡（主题各异，固定词表易误杀）
# 同人连说：硬卡。无破功软收：轻量关键词硬卡（末句软收词 + 前两句无破功痕迹）
# 弱收束（和解/耍赖/甩妈）：末 2 句关键词硬卡

_LIMP_SOFT_CLOSE_MARKERS = (
    "给你", "算了", "好吧", "好了好了", "行吧", "随你",
    "我不管", "不管了", "随便你", "那行", "行行行",
    "哼", "吃吧", "你赢",
)

_PUNCH_BEFORE_SOFT_MARKERS = (
    "说晚了", "已经在了", "自相矛盾", "矛盾", "打脸",
    "那你也", "你也没", "那不算", "当然不算", "堵死",
    "戳穿", "说不通", "你让的", "重新说", "晚了",
    "改不了", "从来不", "已经.*了", "你说的", "你说过",
    "装让", "反悔", "变卦", "自己说", "自己打",
    "你自己说", "你刚说", "上次你说", "自己弄",
)

# 末 2 句弱收束：与观感打分口径对齐，生成时硬拦
_WEAK_END_WAIT_MOM = ("等妈", "叫妈", "问妈", "告诉妈", "妈回来", "评理")
_WEAK_END_SPLIT = ("一人一半", "平分", "倒杯子", "一人一个")
_WEAK_END_STUBBORN = ("反正我要用", "反正橡皮", "反正是我的", "谁用谁小狗")


_PUNCHLINE_TYPE_MARKERS = (
    "权威翻车", "公平执念", "字面执行", "结盟翻车", "妈妈破功",
    "A类", "C类", "D类", "B类", "E类",
    "A：", "C：", "D：", "B：", "E：",
)

# 后半若出现且未在 conflict_core/setting/前段出现，视为跑题
_OFF_TOPIC_MARKERS = (
    "体育课", "学校", "老师", "班主任", "告爸爸", "告诉爸爸",
    "公园", "同学", "操场", "放学", "上课", "教室",
)

# 妈妈台词硬卡：只拦明确「判赢/判平/另开赛制」
# 日常口气（不许再吵、谁也别用、都别…）易误杀，放给提示词约束
_MOM_JUDGE_PATTERNS = (
    "谁先放好谁先选",
    "算你赢",
    "算他赢",
    "一人一半",
    "一人一个",
)

_CONFLICT_CORE_MAX_CHARS = 24
_CONFLICT_ANCHOR_STOP = frozenset(
    {
        "昭昭", "灿灿", "妈妈", "姐弟", "我们", "什么", "怎么",
        "这个", "那个", "不是", "就是", "可以", "不行",
        "争第", "一个", "个洗", "一洗",  # 碎片噪声，优先「洗澡」「橡皮」等实物
        "后自", "反被", "却翻", "矩后", "己示", "范翻", "快立", "牙太",
        "立规", "规定", "自己", "示范", "打脸", "翻车", "却更", "却要",
    }
)
# 抽锚点前从 core 去掉角色名/连接词，避免「昭灿灿争」一类噪声
_CONFLICT_ANCHOR_STRIP = (
    *DAILY_CAST_NAMES,
    "姐弟",
    "vs",
    "VS",
    "对",
)

# 重试瞄准硬卡中段，避免贴边再抖出界
DAILY_STORY_BODY_RETRY_TARGET_MIN = 310
DAILY_STORY_BODY_RETRY_TARGET_MAX = 350

# 首稿：硬卡 + 写作铺垫（偏长再压回）
# 重试：按偏短/偏长分向；勿混用「禁止扩写」与「略删」
_DAILY_STORY_LENGTH_DRAFT = f"""\
- 片长（正文硬卡，放最前）：{DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  【先按句数写】写 22–26 句对话（每句约 12–15 字），直接落在硬卡中段
  （约 {DAILY_STORY_BODY_WRITE_TARGET_MIN}–{DAILY_STORY_BODY_WRITE_TARGET_MAX} 字）；
  禁止先写爆再砍；禁止首稿明显短于 {DAILY_STORY_BODY_CHARS_MIN}。
  发现开场系统另写另验，不计入正文硬卡。
"""

_DAILY_STORY_LENGTH_REVISE_EXPAND = f"""\
- 片长（正文偏短重试）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  只增不删：在上一稿破功前插入互怼/加码，写到
  约 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX} 字；
  增补须轮流说话、每轮带新证据；禁止镜像复读、禁止同人连说。
  禁止整稿重写，禁止超过 {DAILY_STORY_BODY_CHARS_MAX} 字。
  发现开场系统另写另验，不计入正文硬卡。
"""

_DAILY_STORY_LENGTH_REVISE_TRIM = f"""\
- 片长（正文偏长重试）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  只删不增：删车轱辘/合并重复回合，压到
  约 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX} 字；
  禁止新增台词，禁止按铺垫目标再扩写；须仍 ≥{DAILY_STORY_BODY_CHARS_MIN}。
  发现开场系统另写另验，不计入正文硬卡。
"""

_DAILY_STORY_LENGTH_REVISE_PATCH = f"""\
- 片长（正文微调重试）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  只差几个字或局部硬卡：禁止整稿重写、禁止大段增删句。
  优先在现有中段 2–3 句内各加几个字；末四拍尽量原样保留。
  发现开场系统另写另验，不计入正文硬卡。
"""

# 非字数问题重试：篇幅别乱动
_DAILY_STORY_LENGTH_REVISE = f"""\
- 片长（正文硬卡，放最前）：只遵守 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  本轮非字数问题：勿故意加长或缩短；禁止按铺垫目标再扩写。
  发现开场系统另写另验，不计入正文硬卡。
"""

_DAILY_STORY_LENGTH_USER_DRAFT = f"""\
3. 【字数硬卡优先】正文 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
   每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字且一句一层意思。
   【按句数写更准】写 22–26 句（每句约 12–15 字），直接瞄准
   {DAILY_STORY_BODY_WRITE_TARGET_MIN}–{DAILY_STORY_BODY_WRITE_TARGET_MAX} 字；
   勿先写超长再删。发现开场另计另验。
   speaker 仅昭昭/灿灿/妈妈。
"""

_DAILY_STORY_LENGTH_USER_REVISE_EXPAND = f"""\
3. 【字数：偏短只增】正文扩到 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字
   （瞄准 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX}）；
   只增不删，禁止整稿重写、禁止超上限；发现开场另计另验。
   speaker 仅昭昭/灿灿/妈妈。
"""

_DAILY_STORY_LENGTH_USER_REVISE_TRIM = f"""\
3. 【字数：偏长只删】正文压到 ≤{DAILY_STORY_BODY_CHARS_MAX} 字
   （瞄准 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX}，
   须 ≥{DAILY_STORY_BODY_CHARS_MIN}）；只删不增，禁止新增台词；发现开场另计另验。
   speaker 仅昭昭/灿灿/妈妈。
"""

_DAILY_STORY_LENGTH_USER_REVISE_PATCH = f"""\
3. 【字数：微调补齐】正文须落在 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
   只改现有句子（句内加字或改 1–2 句措辞），禁止插入大段新回合、禁止整稿重写。
   发现开场另计另验。speaker 仅昭昭/灿灿/妈妈。
"""

_DAILY_STORY_LENGTH_USER_REVISE = f"""\
3. 【字数硬卡优先】正文只遵守 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
   每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字且一句一层意思。
   非字数问题勿改篇幅；发现开场另计另验。
   speaker 仅昭昭/灿灿/妈妈。
"""

_LENGTH_MODE_SYSTEM = {
    "draft": _DAILY_STORY_LENGTH_DRAFT,
    "revise": _DAILY_STORY_LENGTH_REVISE,
    "revise_expand": _DAILY_STORY_LENGTH_REVISE_EXPAND,
    "revise_trim": _DAILY_STORY_LENGTH_REVISE_TRIM,
    "revise_patch": _DAILY_STORY_LENGTH_REVISE_PATCH,
}

_LENGTH_MODE_USER = {
    "draft": _DAILY_STORY_LENGTH_USER_DRAFT,
    "revise": _DAILY_STORY_LENGTH_USER_REVISE,
    "revise_expand": _DAILY_STORY_LENGTH_USER_REVISE_EXPAND,
    "revise_trim": _DAILY_STORY_LENGTH_USER_REVISE_TRIM,
    "revise_patch": _DAILY_STORY_LENGTH_USER_REVISE_PATCH,
}


def _daily_story_contract(*, length_mode: str = "draft") -> str:
    length = _LENGTH_MODE_SYSTEM.get(length_mode, _DAILY_STORY_LENGTH_DRAFT)
    return f"""\
【共用设定】
- 受众：孩子和有娃的大人（家长能会心一笑，孩子觉得好玩；禁成人梗/谐音/网络热梗）。
- 角色年龄：昭昭7岁弟弟，灿灿10岁姐姐；可发言角色仅昭昭、灿灿、妈妈。
- 爸爸可「不在场被提到」，禁止作为 speaker；禁止老师入戏。
- 场景：家庭内部或家门口（客厅/厨房/卧室/门口）；禁止学校、放学路、公园等外景主场。
{length}\
"""


_DAILY_STORY_SYSTEM_SHARED = """\
【角色设定】
- 昭昭：弟弟，男孩，7岁。好奇心强，喜欢追问，擅长用现实经验挑战抽象规则，经常把简单的事越问越复杂。天真且固执。
- 灿灿：姐姐，女孩，10岁。比昭昭懂事一点，偶尔想模仿大人的语气管教弟弟，但自己的逻辑也经常掉进孩子的坑里。有时候会被昭昭带偏，嘴硬但心软。
- 妈妈：配角。可出场，但台词少；主戏仍是姐弟，妈妈不是戏核。
- 关系：亲姐弟，住在一起；主戏是姐弟斗嘴/较真/互相带偏，不是被妈妈教育。

【妈妈戏份（硬约束）】
- A/C/D 默认可不写妈妈；主戏与破功优先纯姐弟完成；E 类妈妈可略多。
- 若出场：建议全程 ≤2 句（E 类≤5 句）；禁止长篇讲理、禁止妈妈当主线（E 除外）。
- 禁止明确判赢/判平/另开赛制（如「算你赢」「一人一半」「谁先放好谁先选」）。
- 日常口气可以（叮嘱、谁也别乱动、别吵了）：但不应用一句掐灭尚未落地的破功。
- 破功/软收优先在姐弟对白里完成；妈妈最多旁听、附和或事后收拾（E 类可在妈妈对白里破功）。

【发现开场（系统另写，正文勿写）】
- 发现现场的质问/惊呼（如「鞋带怎么系一块了」）由系统单独生成并前置。
- 正文 dialogue 从互怼、讲理、甩规则开始，禁止再写寒暄或重复发现现场。
- setting 仍须写清地点 + 已发生的同一冲突动作，与 conflict_core 同一件实物/规则
  （反例：setting 写「各抓一个对峙」，core 却写「争同一个蓝抱枕」）。
- setting 中若提到妈妈做了某动作（如「妈妈切好蛋糕」），正文里妈妈必须至少出场 1 句台词
  呼应这个动作；否则把该动作改由姐弟中的一人执行（如「灿灿切好蛋糕」）。

【单冲突（硬约束）】
- 全文只滚一条规则加码，禁止中途换裁决方式。
- 反例：先争归属 → 改剪刀石头布 → 再扯道歉 → 再让妈妈轮流——这是另开账。
- 「上次你也…」只可当同一规则的证据，禁止借机开新仇（砸人、红抱枕、别的玩具）。
- 必须输出 conflict_core：一句话写清「谁 vs 谁，争什么」（≤24 字），
  与 theme / setting / 前 2 句一致。
- 禁止岔开学校/体育课/告爸爸/老师/公园等与 conflict_core 无关的新主线。
- 妈妈只点破，禁止由妈妈引入新冲突、新赛制或新事件（E 类立规矩除外）。
- punchline_explain 须含类型标签（A–E）并说明末句如何收该 conflict_core。

【节奏（共用）】
- 每 6–8 句须有一个小反转或加码，禁止平铺到结尾才抖包袱。
- 一句说完一层意思；禁止为凑 ≤18 字把同一半截话硬拆成两句（听感断裂）。
- 昭昭/灿灿必须轮流说：禁止同一人连说 ≥2 句（听感碎、像注水）。
- 禁止概念绕圈：同一逻辑结论的不同措辞变体也算同一对立面，
  最多 2 个来回后必须引入新事实，禁止空转语义辩论连续超过 4 句。

【好笑（硬约束，观感核心）】
- **本场一锤**：须有可拍细节（数字、分钟、题号、音名、具体物件），
  笑点从这一锤长出来，不靠空辩「姐姐说了算」。
- 收束「你刚才说…」须引用前文原话；禁止编造套话。
- 「哪里不一样」全篇仅收束一处；末四拍须完整（引话→那不一样→哪里不一样→哼）。
- 同一借口/同一旧账全篇最多 2 次（旧账建议只 1 次）。

【立场连贯（硬约束）】
- 同一角色前后立场须连贯：可以软收、可以认栽，但禁止无铺垫的态度骤变。
- 反例：刚喊「不公平/不行」下一句立刻「好吧/算了/给你」认怂——中间缺转折理由。
- 若要改口，须有新理由（被字面戳穿、被证据打脸），不能为收束硬拧。
- 同一人若因格式错误连说，后一句也须接前一句，禁止自打嘴巴。

【绝对禁止】
1. 禁止成人笑话、谐音梗、俏皮话、网络热梗。
2. 禁止「因为……所以……」等书面连接词，全部用口语短句。
3. 禁止叙事小说腔（「他心想」「她无奈地」等），只写纯对话+极简 setting。
4. 禁止为凑长度反复换说法车轱辘，或镜像对白。
5. 禁止后半段换冲突、换地点主场、新开一件事或换一套分法/赛制。
6. 禁止角色无铺垫的自相矛盾（立场/证据前后打架）。
7. 禁止用「明天再战/今晚占位」当唯一收束，却没先破本场规则。
8. 禁止无破功软收：末句「给你/算了/好吧/好了好了」前，
   须已有一句把对方规则戳穿或自相矛盾；禁止吵不动就罢休。
9. 禁止弱收束（末 2 句内出现即违规）：
   - 和解分赃：「一人一半」「平分」「倒杯子」——把冲突和稀泥；
   - 耍赖占有：「反正我要用」「反正是我的」——没戳穿只赖账；
   - 甩给妈妈：「等妈回来」「叫妈评理」——本场须姐弟内收束（E 类妈妈在场除外）。
10. 禁止赢家说最后一句：末句 speaker 必须是破功/被反杀/嘴硬的一方。
11. setting 一致性：若 setting 中妈妈完成某动作（如切蛋糕/拿东西），
    她必须在正文至少出场 1 句台词呼应；否则把该动作改由姐弟中的一人执行。
"""


def _daily_story_system_body(*, type_code: str | None = None) -> str:
    catalog = type_catalog_system_block()
    if not type_code:
        return f"{_DAILY_STORY_SYSTEM_SHARED}\n{catalog}\n"
    line = STORY_TYPE_LINES.get(type_code.upper())
    if not line:
        return f"{_DAILY_STORY_SYSTEM_SHARED}\n{catalog}\n"
    return (
        f"{_DAILY_STORY_SYSTEM_SHARED}\n"
        f"{line.prompt_block}\n"
        f"{format_block_for_code(line.code)}\n"
    )


def _daily_story_user_template(
    *,
    length_mode: str = "draft",
    type_code: str | None = None,
) -> str:
    length_req = _LENGTH_MODE_USER.get(length_mode, _DAILY_STORY_LENGTH_USER_DRAFT)
    if type_code and type_code.upper() in STORY_TYPE_LINES:
        line = STORY_TYPE_LINES[type_code.upper()]
        closing = line.user_closing
        anchor = line.body_user_anchor or (
            "1. 主题即冲突实物：setting、conflict_core、正文首句须锚定主题中的实物/动作。"
        )
    else:
        closing = (
            "9. 收束须遵守本次锁定类型的专属线路（见 system）；"
            "末句破功方说最后一句。"
        )
        anchor = (
            "1. 主题即冲突实物：setting、conflict_core、正文首句须锚定主题中的实物/动作。"
        )
    return f"""\
请根据上述规则，生成一个昭昭和灿灿的日常对话场景。

【本次场景主题（核心事件）】：{{theme}}

【要求】：
{anchor}
2. {{type_instruction}}
{length_req}\
4. 正文从互怼/讲理起笔，禁止发现现场开场（发现句系统另写）。
5. 妈妈默认可不写；若出场宜少；禁止「算你赢/一人一半」类判赢判平（E 类除外）。
6. 输出 conflict_core（≤24 字）；punchline_explain 须含类型标签并说明如何收该冲突。
7. 禁止中途换分法（剪刀石头布、轮流、另算谁先碰到等）或扯无关旧账。
8. 立场须连贯：可软收，但须先破功再软收；禁无铺垫「给你/算了」；
   禁同人连说、禁对称复读注水；末句勿只甩「明天再战」。
{closing}

请直接输出JSON。
"""


def _daily_story_system_prompt(
    *,
    length_mode: str = "draft",
    type_code: str | None = None,
) -> str:
    return (
        "你是一位家庭情景喜剧编剧，写昭昭&灿灿的日常对话短剧。\n"
        "面向孩子和有娃的大人：笑点要孩子听得懂，家长看得出自家日常。\n\n"
        f"{_daily_story_contract(length_mode=length_mode)}"
        f"{_daily_story_system_body(type_code=type_code)}"
    )


# 兼容旧引用：默认 = 首稿（含写作铺垫），未锁定类型
DAILY_STORY_SYSTEM_PROMPT = _daily_story_system_prompt(length_mode="draft")
DAILY_STORY_USER_TEMPLATE = _daily_story_user_template(length_mode="draft")
_DAILY_STORY_CONTRACT = _daily_story_contract(length_mode="draft")

DAILY_STORY_THEME_SYSTEM_PROMPT = f"""\
你是一位家庭情景喜剧策划师，为昭昭&灿灿日常对话短剧策划主题。
{_DAILY_STORY_CONTRACT}
"""

DAILY_STORY_THEME_USER_TEMPLATE = """\
请给出{count}个适合昭昭（7岁弟弟）与灿灿（10岁姐姐）日常对话的场景主题。
面向孩子和有娃的大人。

家庭背景：姐弟和爸爸妈妈住在一起，家里没有宠物；
可发言角色仅昭昭、灿灿、妈妈；妈妈可出场但戏份轻（少台词）。

要求：
1. 主题必须是一件具体的小事，且最好带动作/实物（抢遥控器、弄脏裙子、藏橡皮），
   少写抽象讨论（如「讨论友谊」「探讨公平」）。
2. 不能是抽象概念。
3. 主题要有天然矛盾，且主戏能在家门口/室内由姐弟撑起来，类型须多样，例如：
   A 姐姐管教/教作业被反问到哑口；C 抢先后/分东西吵公平；
   D 把叮嘱按字面做砸；B 姐弟联手瞒事露馅；E 妈妈讲理被绕进去。
4. 少出「妈妈讲理/教育」当主线的主题（E 类除外）。
5. 禁止依赖爸爸入戏、老师入戏、学校/公园等外景主场的主题。
6. 主题须能用短句口语一场讲完（对白体量约一分半到两分钟）。
7. 主题用15个字以内描述，直接输出。

示例："争最后一瓶酸奶"
示例："谁先洗澡"
示例："姐姐教弟弟写作业自己写错"
示例："把叠好的衣服弄乱"
示例："偷偷一起吃零食"

请直接输出标题，每行一个，不要其他内容。
"""


def _select_story_type(theme: str) -> str:
    return select_story_type_tag(theme)


def _extract_type_from_punchline(punchline: str) -> str | None:
    """从 punchline_explain 中提取矛盾类型标签。"""
    text = punchline or ""
    for k in ("A", "B", "C", "D", "E"):
        label = STORY_TYPE_LABELS[k]
        if f"{k}类{label}" in text or f"{k}类" in text or f"{k}：" in text:
            return story_type_tag(k)
    return None


def build_daily_story_prompts(
    theme: str,
    *,
    story_type: str | None = None,
    length_mode: str = "draft",
) -> tuple[str, str]:
    """构造日常故事正文生成的 system + user 提示词。

    length_mode:
      - draft：首稿，含写作铺垫目标（偏长再压回硬卡）
      - revise_expand：偏短较多，只增不删，可插互怼
      - revise_patch：只差几个字/局部硬卡，句内微调，勿整稿重写
      - revise_trim：偏长重试，只删不增，瞄准中段
      - revise：非字数问题重试，勿故意改篇幅
    """
    type_instruction = (
        f"本次矛盾类型必须用：{story_type}。禁止用其他类型。"
        if story_type
        else "生成前须从 A/C/D/B/E 中择一类型并走其专属线路（见 system）。"
    )
    type_code = (
        parse_story_type_code(story_type=story_type) if story_type else None
    )
    user_tpl = _daily_story_user_template(
        length_mode=length_mode,
        type_code=type_code,
    )
    return (
        _daily_story_system_prompt(
            length_mode=length_mode,
            type_code=type_code,
        ),
        user_tpl.format(theme=theme, type_instruction=type_instruction),
    )


DAILY_STORY_OPENING_SYSTEM_PROMPT = f"""\
你为昭昭&灿灿日常短剧写「发现现场」开场：观众一听就知道在争什么。
只写 1–2 句发现/质问，不写正文互怼。

【角色】昭昭7岁弟弟、灿灿10岁姐姐；开场 speaker 仅二人，勿写妈妈。
【场景】家庭内部/门口；口语短句，每句≤{DAILY_STORY_LINE_CHARS_MAX}字；禁成人梗/网络热梗。

【开场要干什么】
写**正文开始之前**定格的一瞬：观众看见实物/动作/场面，知道马上要争什么。
不是寒暄，也不是正文里已经吵起来的那一轮。

【时间线（生成必守）】
成片顺序是：**发现开场 → 正文第 1 句 → 正文第 2 句 → …**
因此开场在剧情时间上**早于**下面 user 里的「正文前两句」。
- 正文第 1 句里才第一次说出口的指责/规矩，开场里**不能**用「还/也/你刚才」去接。
- 勿把正文前两句或更后面的反击、顶嘴、引用原话写进开场。
- 开场只写「看见/抓住」当下；互怼从正文第 1 句起。

【句式（优先挑一种，可两句接力）】
- 看见实物：点名冲突物 + 异常状态
  （例：「咦鞋带怎么系一块了」「新橡皮怎么在你手里」）
- 抓住动作：点名正在抢/藏/弄脏
  （例：「你干嘛抢我遥控器」「别藏我的彩笔」）
- 质问规则入口：点出「谁先/不给/弄坏」但不展开辩论
  （例：「谁先到的你凭什么先洗」「这酸奶不是说留给我的吗」）

【正例】
主题「把姐姐鞋带系一起」→ 灿灿：「咦我的鞋带怎么系一块了」
主题「抢新橡皮」→ 昭昭：「新橡皮怎么攥你手里」
主题「谁先洗澡」→ 灿灿：「我先到门口的我先洗澡」
主题「争最后一瓶酸奶」→ 昭昭：「最后一瓶酸奶你怎么打开了」

【反例（禁止）】
- 寒暄铺垫：「姐你在干嘛」「今天好无聊」
- 直接开辩：「规则是谁先看见谁拿」「我是姐姐我说了算」
- 抽象空话：「这不公平」「你怎么这样」——没点出实物/动作
- 片头定场，不是正文互怼：勿把需要前文才成立的反击、双标对比、引用原话写在开场第 1 句
- 妈妈出场、复述正文已有句子、续写互怼第二回合

【输出】只输出 JSON：
{{"opening":[{{"speaker":"昭昭","line":"…"}},…]}}
opening 须 1–2 句；须锚定本次 conflict_core 的实物或动作。
"""

DAILY_STORY_OPENING_USER_TEMPLATE = """\
请为下面这场戏写发现开场（1–2 句）。

【主题】{theme}
【场记】{scene_title}
【现场】{setting}
【本场只争这一件】{conflict_core}

【正文前两句】（**开场之后才发生**，勿复述、勿接下去顶嘴、勿用「还」接这里的词）：
{body_head}

要求：开场只写正文开始**之前**能看见的现场（物/动作）；
正文第 1 句尚未发生，禁止开场预支其中的「磨蹭/不许/放下」等指责后再用「还说我…」；
不要寒暄，不要妈妈。直接输出 JSON。
"""


def build_daily_story_opening_prompts(
    theme: str,
    story: dict,
    *,
    type_code: str | None = None,
) -> tuple[str, str]:
    """构造发现开场单抽的 system + user。"""
    if not type_code and isinstance(story, dict):
        type_code = parse_story_type_code(
            punchline=str(story.get("punchline_explain") or ""),
        )
    system = DAILY_STORY_OPENING_SYSTEM_PROMPT
    if type_code and type_code.upper() in STORY_TYPE_LINES:
        append = STORY_TYPE_LINES[type_code.upper()].opening_system_append
        if append.strip():
            system = f"{system}\n{append}"
    dialogue = story.get("dialogue") if isinstance(story, dict) else None
    head_lines: list[str] = []
    if isinstance(dialogue, list):
        for item in dialogue[:2]:
            if not isinstance(item, dict):
                continue
            sp = str(item.get("speaker") or "").strip() or "?"
            line = str(item.get("line") or "").strip()
            if line:
                head_lines.append(f"{sp}：{line}")
    body_head = "\n".join(head_lines) if head_lines else "（正文暂无）"
    user = DAILY_STORY_OPENING_USER_TEMPLATE.format(
        theme=theme,
        scene_title=str(story.get("scene_title") or "").strip() or "（无）",
        setting=str(story.get("setting") or "").strip() or "（无）",
        conflict_core=str(story.get("conflict_core") or "").strip() or "（无）",
        body_head=body_head,
    )
    if type_code and type_code.upper() in STORY_TYPE_LINES:
        ou = STORY_TYPE_LINES[type_code.upper()].opening_user_append.strip()
        if ou:
            user = f"{user}\n{ou}"
    return system, user


# 特写镜（后续走 I2V）对白上限，利于口型轮次
DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES = 2

DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是儿童情景对话短剧的分镜编剧，只负责把对白切成可执行镜头，不写画面描述。

【可发言角色】昭昭（7岁弟弟）、灿灿（10岁姐姐）、妈妈。场景以家庭内部/门口为主。

【分镜规则】
1. 【切分原则】按单镜 2–3 句、≤{max_sec} 秒切分（对白共 {total_chars} 字 / {line_count} 句）；
   禁止一句一镜。
2. 【默认并镜】按同一地点、同一轮互怼/同一话题合并；中景/全景每镜通常 2–3 句，
   单镜不得超过 3 句。
3. 【特写对白上限】shot_type 为「特写」的镜，dialogue **不得超过 2 句**
   （图生视频口型轮次限制）。若该轮还有第 3 句，须拆到下一镜（可仍特写），
   或本镜改标「中景」并保留 3 句。
4. 【单镜字数】建议 {min_chars}–{max_chars} 字（约 {min_sec}–{max_sec} 秒，
   语速 {chars_per_sec} 字/秒）。少于 {min_chars} 字必须并入邻镜；
   单镜合计不得超过 {max_chars} 字（约 ≤{max_sec} 秒）。各镜尽量均匀。
5. 为每镜标注 shot_type（全景/中景/特写），在环境交代、对话主体、情绪或道具之间穿插。
6. 【开场首镜】scene_id=1 须定格冲突峰值姿势（抢/举/夺/藏/对峙），
   shot_type **必须「特写」**（发现开场也要落在动作峰值上，用特写留住开头吸引力）；
   禁止全景空镜、中景站桩或寒暄开场；首镜 dialogue 亦须遵守特写 ≤2 句。
7. 【转折用特写，不拆碎】反驳、破功、愣住、妈妈插嘴、证据翻出等转折句：
   放在该镜开头，shot_type 优先「特写」，且本镜最多再跟 **1 句**回应（特写合计 ≤2 句）；
   禁止为转折把短句单独拆成不足 {min_chars} 字的镜；
   也禁止在特写镜里塞 3 句。全文特写镜不超过总镜数约 1/3。

【输出格式】
严格输出合法 JSON（不要 markdown 代码块）：
{{
  "scenes": [
    {{
      "scene_id": 1,
      "shot_type": "全景",
      "dialogue": [
        {{"speaker": "昭昭", "text": "台词1"}},
        {{"speaker": "灿灿", "text": "台词2"}}
      ]
    }}
  ]
}}

【重要约束】
- 台词原文照抄，禁止改写、删句、合并措辞；speaker 必须与原剧本一致。
- 不要输出 visual_description / visual_brief（画面概述由后续步骤生成）。
- 不要添加剧本中没有的旁白、动作说明或情绪标签。
"""

DAILY_SCRIPT_USER_TEMPLATE = """\
请将以下对话剧本切成分镜（只分配台词，不写画面）。

【标题】{scene_title}
【场景设定】{setting}

【对话剧本】
{dialogue_text}

【要求】
1. 中景/全景每镜 2–3 句、不得超过 3 句；**特写镜不得超过 2 句**
2. 单镜 {min_chars}–{max_chars} 字（约 ≤{max_sec} 秒）；禁止一句一镜
3. 转折句用特写并放在镜首，特写镜最多再跟 1 句回应；第 3 句须拆到下一镜或改中景
4. 原台词须全部分配到各镜 dialogue，措辞不得改

请直接输出 JSON。
"""

# 与 DailyScriptStage 时长告警对齐
DAILY_SCRIPT_MAX_SEGMENT_SEC = 10.0
# 单镜下限（约 2 句短对白）；过短须并入邻镜
DAILY_SCRIPT_MIN_SEGMENT_SEC = 4.0


def validate_daily_script_scenes(scenes: list) -> list[str]:
    """分镜硬校验：特写镜对白不得超过 DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES。"""
    max_lines = DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES
    errors: list[str] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        shot = str(scene.get("shot_type") or "").strip()
        if shot != "特写":
            continue
        dialogue = scene.get("dialogue") or []
        n = sum(1 for d in dialogue if isinstance(d, dict))
        if n > max_lines:
            sid = scene.get("scene_id", "?")
            errors.append(
                f"scene_id={sid} 为特写但含 {n} 句对白（特写镜最多 {max_lines} 句）"
            )
    return errors


def _format_prompt_number(value: float) -> str:
    """提示词里去掉无意义的小数尾（18.0 → 18）。"""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def build_daily_script_prompts(
    dialogue_script: dict,
    *,
    chars_per_sec: float = 3.0,
) -> tuple[str, str]:
    """构造日常故事分镜生成的 system + user 提示词。

    Args:
        dialogue_script: 日常故事对话剧本，格式同 generate_daily_story 输出
            （含 setting, dialogue 等字段），dialogue 为
            [{"speaker": "昭昭", "line": "台词"}, ...] 格式
        chars_per_sec: 语速基准（字/秒），默认 3.0
    """
    cps = float(chars_per_sec) if chars_per_sec else 3.0
    max_sec = DAILY_SCRIPT_MAX_SEGMENT_SEC
    min_sec = DAILY_SCRIPT_MIN_SEGMENT_SEC
    max_chars = max(20, int(max_sec * cps))
    min_chars = max(20, int(min_sec * cps))
    dialogue = dialogue_script.get("dialogue", [])
    # 纠正常见 LLM 拼写错误（speaker 错拼）
    _correct_dialogue_speaker(dialogue)
    dialogue_text = "\n".join(
        f"{d.get('speaker', '?')}：{d.get('line', '')}"
        for d in dialogue
    )
    total_chars = sum(_dialogue_char_count(str(d.get("line") or "")) for d in dialogue)
    line_count = len(dialogue)
    scene_title = str(dialogue_script.get("scene_title") or "").strip() or "（无标题）"
    setting = str(dialogue_script.get("setting") or "").strip() or "（未提供设定）"
    max_sec_text = _format_prompt_number(max_sec)
    min_sec_text = _format_prompt_number(min_sec)
    cps_text = _format_prompt_number(cps)
    fmt = dict(
        chars_per_sec=cps_text,
        max_sec=max_sec_text,
        min_sec=min_sec_text,
        max_chars=max_chars,
        min_chars=min_chars,
        total_chars=total_chars,
        line_count=line_count,
    )
    system = DAILY_SCRIPT_SYSTEM_PROMPT.format(**fmt)
    user = DAILY_SCRIPT_USER_TEMPLATE.format(
        dialogue_text=dialogue_text,
        scene_title=scene_title,
        setting=setting,
        **fmt,
    )
    return system, user


def _dialogue_char_count(line: str) -> int:
    """与成片时长估算一致：按台词字符串长度计。"""
    return len(line or "")


def _dialogue_lines_text(dialogue: list) -> list[str]:
    lines: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        text = str(item.get("line") or "").strip()
        if text:
            lines.append(text)
    return lines


def _conflict_anchor_tokens(text: str) -> list[str]:
    """从 conflict_core 抽 2–4 字锚点（先去角色名，减少噪声）。"""
    compact = "".join(re.findall(r"[\u4e00-\u9fff]+", text or ""))
    for piece in _CONFLICT_ANCHOR_STRIP:
        compact = compact.replace(piece, "")
    tokens: set[str] = set()
    for n in (4, 3, 2):
        for i in range(0, max(0, len(compact) - n + 1)):
            t = compact[i : i + n]
            if t not in _CONFLICT_ANCHOR_STOP:
                tokens.add(t)
    # 长词优先；同长度保持稳定顺序
    return sorted(tokens, key=lambda t: (-len(t), t))


def _conflict_anchors_hit(core: str, ctx: str, anchors: list[str]) -> bool:
    """开场/setting 是否点到 conflict；刷牙允许牙刷/牙膏等同场词。"""
    if anchors and any(a in ctx for a in anchors):
        return True
    # 刷牙主题：core 可能写「刷太快」而无「刷牙」二字
    if re.search(r"刷牙|刷太|漱口|牙刷", core or "") and re.search(
        r"刷牙|牙刷|牙膏|漱口|吐水|刷太|刷几|刷够",
        ctx or "",
    ):
        return True
    return False


def _conflict_anchor_must_words(conflict_core: str, *, limit: int = 4) -> list[str]:
    """开场重试用：挑应点名的锚点（短词优先，如「洗澡」而非「一个洗澡」）。"""
    anchors = _conflict_anchor_tokens(conflict_core)
    # 2–3 字优先；跳过已被更短锚点覆盖的长串
    ordered = sorted(anchors, key=lambda t: (len(t), t))
    picked: list[str] = []
    for a in ordered:
        if len(a) > 3 and picked:
            continue
        if any(p in a for p in picked):
            continue
        picked.append(a)
        if len(picked) >= limit:
            break
    return picked or anchors[:limit]


def _append_single_conflict_errors(story: dict, errors: list[str]) -> None:
    """校验单冲突：conflict_core 必填，开场对齐，后半禁无关岔开。"""
    core = str(story.get("conflict_core") or "").strip()
    if not core:
        errors.append("缺少 conflict_core（≤24字写清谁vs谁争什么）")
        return
    if len(core) > _CONFLICT_CORE_MAX_CHARS:
        errors.append(
            f"conflict_core 须≤{_CONFLICT_CORE_MAX_CHARS}字，当前{len(core)}字"
        )

    setting = str(story.get("setting") or "").strip()
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return

    lines = _dialogue_lines_text(dialogue)
    if not lines:
        return

    anchors = _conflict_anchor_tokens(core)
    front = "".join(lines[:2])
    front_ctx = core + setting + front
    if anchors and not _conflict_anchors_hit(core, front_ctx, anchors):
        errors.append(
            f"开场/setting 未体现 conflict_core 锚点（{anchors}）：{core!r}"
        )

    if len(lines) < 9:
        return
    third = max(1, len(lines) // 3)
    latter = "".join(lines[-third:])
    early = "".join(lines[:-third])
    allowed = core + setting + early
    for marker in _OFF_TOPIC_MARKERS:
        if marker in latter and marker not in allowed:
            errors.append(
                f"后半疑似跑题：出现「{marker}」，与 conflict_core={core!r} 无关"
            )
            break


def _append_dialogue_rhythm_errors(story: dict, errors: list[str]) -> None:
    """节奏硬卡：姐弟禁同人连说；弱收束/无破功软收则拦。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return

    prev_speaker = ""
    run = 0
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        if speaker not in ("昭昭", "灿灿"):
            prev_speaker = speaker
            run = 0
            continue
        if speaker == prev_speaker:
            run += 1
            if run >= 2:
                errors.append(
                    f"dialogue[{i - 1}:{i}] {speaker} 连说≥2句，须轮流说话"
                )
                break
        else:
            prev_speaker = speaker
            run = 1

    lines = _dialogue_lines_text(dialogue)
    if len(lines) < 3:
        return
    last = lines[-1]
    tail2 = "".join(lines[-2:])

    if any(m in tail2 for m in _WEAK_END_WAIT_MOM):
        errors.append(
            "末尾弱收束：甩给妈妈（等妈/评理）；"
            "须在姐弟内字面戳穿后再收"
        )
    if any(m in tail2 for m in _WEAK_END_SPLIT):
        errors.append(
            "末尾弱收束：和解分赃（一人一半/平分/倒杯子）；"
            "须先破本场规则，禁止和稀泥"
        )
    if any(m in last for m in _WEAK_END_STUBBORN):
        errors.append(
            "末尾弱收束：耍赖占有（反正我要用）；"
            "须先字面戳穿对方规则，禁止赖账收场"
        )

    # 无破功软收改由 quality 评分扣分，不再硬拦生成


def _append_mom_line_errors(story: dict, errors: list[str]) -> None:
    """校验妈妈台词：句数上限、禁止裁判式收场。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return
    mom_items = [
        (i, item)
        for i, item in enumerate(dialogue)
        if isinstance(item, dict) and item.get("speaker") == "妈妈"
    ]
    if len(mom_items) > 3:
        errors.append(
            f"妈妈台词超过3句（{len(mom_items)}句），主戏应在姐弟"
        )
    for _, item in mom_items:
        line = str(item.get("line") or "")
        for pattern in _MOM_JUDGE_PATTERNS:
            if pattern in line:
                errors.append(
                    f"妈妈台词不可当裁判（发现「{pattern}」）：{line!r}"
                )
                break
    # 妈妈的句数占比：总句数≤10 且妈妈≥3 句视为妈妈主导
    if len(dialogue) <= 10 and len(mom_items) >= 3:
        errors.append(
            f"短剧（{len(dialogue)}句）中妈妈台词过多（{len(mom_items)}句），禁止妈妈主导"
        )


def _append_winner_last_line_errors(story: dict, errors: list[str]) -> None:
    """校验末句说话人是否为被破功方（禁止赢家收束）。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 3:
        return
    # 只取正文（不含发现开场）的末尾 2 个 speaker
    siblings = [
        item for item in dialogue
        if isinstance(item, dict) and str(item.get("speaker") or "") in ("昭昭", "灿灿")
    ]
    if len(siblings) < 2:
        return
    last_sp = str(siblings[-1].get("speaker") or "")
    prev_sp = str(siblings[-2].get("speaker") or "")
    last_line = str(siblings[-1].get("line") or "")
    # 若末两句同人 + 末句不含软收/认输关键词 → 可能是赢家连说
    if last_sp == prev_sp:
        if not any(m in last_line for m in ("算了", "好吧", "给你", "随你", "不管", "哼")):
            errors.append(
                f"末 2 句同人（{last_sp}连说），疑似赢家收束；"
                "末句须由被破功方说话"
            )


def _append_setting_mom_consistency_errors(story: dict, errors: list[str]) -> None:
    """setting 中妈妈有动作但正文妈妈无台词 → 违规。"""
    setting = str(story.get("setting") or "").strip()
    if "妈妈" not in setting:
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return
    mom_lines = [
        item for item in dialogue
        if isinstance(item, dict) and item.get("speaker") == "妈妈"
    ]
    if not mom_lines:
        errors.append(
            "setting 提到妈妈动作（如切蛋糕）但正文妈妈无台词；"
            "须给妈妈至少 1 句台词呼应，或把 setting 中的动作改由姐弟执行"
        )


def validate_daily_story_json(
    story: dict,
    *,
    phase: str = "full",
) -> None:
    """校验日常故事 JSON。

    phase=body：验正文（含字数硬卡 280–340）。
    phase=full：拼开场后结构/单句等终检；**不再卡全文总字数**
    （开场由 validate_daily_story_opening 单独校验）。
    """
    if phase not in ("full", "body"):
        raise ValueError(f"未知 phase: {phase!r}")
    errors: list[str] = []

    if not isinstance(story, dict):
        raise ValueError(f"daily_story 返回数据不是字典: {type(story).__name__}")

    _correct_dialogue_speaker(story.get("dialogue", []))

    # 必需字段检查
    for field in (
        "scene_title",
        "setting",
        "conflict_core",
        "dialogue",
        "punchline_explain",
    ):
        if field not in story:
            errors.append(f"缺少必需字段: {field}")

    if errors:
        raise ValueError("; ".join(errors))

    # scene_title 类型
    if not isinstance(story["scene_title"], str) or not story["scene_title"].strip():
        errors.append("scene_title 必须是非空字符串")
    if not isinstance(story["setting"], str) or not story["setting"].strip():
        errors.append("setting 必须是非空字符串")
    if (
        not isinstance(story.get("conflict_core"), str)
        or not str(story.get("conflict_core") or "").strip()
    ):
        errors.append("conflict_core 必须是非空字符串")
    if not isinstance(story["punchline_explain"], str) or not story["punchline_explain"].strip():
        errors.append("punchline_explain 必须是非空字符串")

    # dialogue 校验
    dialogue = story.get("dialogue", [])
    allowed_speakers = set(DAILY_CAST_NAMES)
    if not isinstance(dialogue, list):
        errors.append("dialogue 必须是数组")
    elif not dialogue:
        errors.append("dialogue 不能是空数组")
    else:
        total_chars = 0
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                errors.append(f"dialogue[{i}] 不是字典")
                continue
            if "speaker" not in item:
                errors.append(f"dialogue[{i}] 缺少 speaker")
            elif not isinstance(item["speaker"], str) or not item["speaker"].strip():
                errors.append(f"dialogue[{i}] speaker 必须是非空字符串")
            elif item["speaker"].strip() not in allowed_speakers:
                errors.append(
                    f"dialogue[{i}] speaker 必须是「"
                    + "」「".join(DAILY_CAST_NAMES)
                    + f"」，收到：{item['speaker']!r}"
                )
            if "line" not in item:
                errors.append(f"dialogue[{i}] 缺少 line")
            elif not isinstance(item["line"], str) or not item["line"].strip():
                errors.append(f"dialogue[{i}] line 必须是非空字符串")
            elif not re.search(r"[\u4e00-\u9fff\w]", item["line"]):
                errors.append(f"dialogue[{i}] line 不含可发音内容（仅标点符号）")
            else:
                n = _dialogue_char_count(item["line"].strip())
                total_chars += n
                if n > DAILY_STORY_LINE_CHARS_MAX:
                    errors.append(
                        f"dialogue[{i}] line 超过{DAILY_STORY_LINE_CHARS_MAX}字"
                        f"（{n}字）：{item['line']!r}"
                    )
        # 总字数硬卡仅正文；拼开场后全文不卡总字数
        if phase == "body" and total_chars:
            if total_chars < DAILY_STORY_BODY_CHARS_MIN:
                deficit = DAILY_STORY_BODY_CHARS_MIN - total_chars
                errors.append(
                    f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前{total_chars}"
                    f"（还差{deficit}字）"
                )
            if total_chars > DAILY_STORY_BODY_CHARS_MAX:
                excess = total_chars - DAILY_STORY_BODY_CHARS_MAX
                errors.append(
                    f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total_chars}"
                    f"（超出{excess}字）"
                )

    # punchline_explain 须标明类型
    explain = story.get("punchline_explain")
    if isinstance(explain, str) and explain.strip():
        if not any(m in explain for m in _PUNCHLINE_TYPE_MARKERS):
            errors.append(
                "punchline_explain 须含类型标签"
                "（如「C类公平执念」或「权威翻车」）"
            )

    _append_single_conflict_errors(story, errors)

    # 节奏：禁同人连说；无破功软收
    _append_dialogue_rhythm_errors(story, errors)

    # 妈妈台词硬约束
    _append_mom_line_errors(story, errors)

    # 末句赢家检测（仅正文阶段，拼开场后不在 body phase 执行）
    if phase == "body":
        _append_winner_last_line_errors(story, errors)

    # setting 妈妈动作一致性
    _append_setting_mom_consistency_errors(story, errors)

    _append_verifiable_fact_errors(story, errors)
    _append_homework_fact_errors(story, errors)
    _append_brush_timer_fact_errors(story, errors)
    _append_a_closing_quote_errors(story, errors)
    _append_a_mid_restatement_errors(story, errors)
    _append_a_steal_single_line_errors(story, errors)
    _append_dangling_term_errors(story, errors)

    dialogue = story.get("dialogue")
    if isinstance(dialogue, list):
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                continue
            if item.get("speaker") == "昭昭" and re.search(
                r"我是姐姐",
                str(item.get("line") or ""),
            ):
                errors.append(
                    f"dialogue[{i}] 角色反了：昭昭是弟弟，禁止自称姐姐"
                )
                break

    if errors:
        raise ValueError("daily_story 校验失败: " + "; ".join(errors))


_CN_DIGIT: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "两": 2,
}

_CLOCK_TOKEN_RE = re.compile(
    r"([零一二三四五六七八九十两]{1,3})点"
    r"(半|整|(?:零[一二三四五六七八九])|(?:[一二三四五六七八九十]{1,3}))?",
)

_DURATION_MINUTES_RE = re.compile(
    r"(\d+|"
    r"二十[一二三四五六七八九]?|"
    r"十[一二三四五六七八九]?|"
    r"[一二三四五六七八九])"
    r"分钟",
)

_DURATION_NUM = (
    r"(?:\d+|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|[一二三四五六七八九])"
)


def _parse_cn_small_int(s: str) -> int | None:
    if not s:
        return None
    if s == "十":
        return 10
    if s.startswith("十") and len(s) == 2:
        return 10 + _CN_DIGIT.get(s[1], 0)
    if "十" in s:
        head, _, tail = s.partition("十")
        hi = _CN_DIGIT.get(head, 1) if head else 1
        lo = _CN_DIGIT.get(tail, 0) if tail else 0
        return hi * 10 + lo
    if len(s) == 1 and s in _CN_DIGIT:
        return _CN_DIGIT[s]
    return None


def _parse_cn_clock_token(token: str) -> int | None:
    """将「八点十五」类短语转为当日分钟数（0–1439）。"""
    m = _CLOCK_TOKEN_RE.fullmatch(token.strip())
    if not m:
        return None
    hour = _parse_cn_small_int(m.group(1))
    if hour is None or hour > 23:
        return None
    minute_part = m.group(2)
    if not minute_part:
        minute = 0
    elif minute_part == "整":
        minute = 0
    elif minute_part == "半":
        minute = 30
    elif minute_part.startswith("零") and len(minute_part) == 2:
        minute = _CN_DIGIT.get(minute_part[1], 0)
    else:
        minute = _parse_cn_small_int(minute_part)
        if minute is None or minute > 59:
            return None
    return hour * 60 + minute


def _iter_clock_tokens(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for m in _CLOCK_TOKEN_RE.finditer(text):
        tok = m.group(0)
        minutes = _parse_cn_clock_token(tok)
        if minutes is not None:
            out.append((tok, minutes))
    return out


def _start_anchor_minutes_from_line(line: str) -> list[int]:
    anchors: list[int] = []
    rm = re.search(
        r"从\s*([零一二三四五六七八九十两]+点"
        r"(?:半|整|(?:零[一二三四五六七八九])|(?:[一二三四五六七八九十]{1,3}))?)\s*到",
        line,
    )
    if rm:
        t = _parse_cn_clock_token(rm.group(1))
        if t is not None:
            anchors.append(t)
    if re.search(r"拿|起算|计时", line):
        for tok, minutes in _iter_clock_tokens(line):
            if re.search(rf"{re.escape(tok)}.{0,6}拿|拿.{0,6}{re.escape(tok)}", line):
                anchors.append(minutes)
            elif tok in line and "拿" in line:
                anchors.append(minutes)
    if re.search(r"开始|整开始", line):
        for _, minutes in _iter_clock_tokens(line):
            anchors.append(minutes)
    return anchors


def _parse_duration_minutes(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        n = int(token)
        return n if 0 < n <= 180 else None
    n = _parse_cn_small_int(token)
    if n is None or n <= 0 or n > 180:
        return None
    return n


def _line_claims_time_up(line: str) -> bool:
    if re.search(r"马上.{0,8}(到时间|时间到)|快.{0,4}到时间", line):
        return False
    return bool(re.search(r"时间到了|到点了|时间已到|到时间了", line))


def _append_clock_fact_errors(
    lines_text: list[str],
    full: str,
    errors: list[str],
) -> None:
    all_clocks: list[tuple[str, int]] = []
    for line in lines_text:
        all_clocks.extend(_iter_clock_tokens(line))
    if len(all_clocks) < 2:
        return

    start_anchors: list[int] = []
    for line in lines_text:
        start_anchors.extend(_start_anchor_minutes_from_line(line))
    unique_starts = sorted(set(start_anchors))
    if len(unique_starts) >= 2:
        errors.append(
            "可核对事实：计时起点前后不一致（如八点拿与八点整开始混用），"
            "请统一一条时间线或删掉钟点",
        )

    now_min: int | None = None
    end_min: int | None = None
    for line in lines_text:
        nm = re.search(
            r"现在\s*([零一二三四五六七八九十两]+点"
            r"(?:半|整|(?:零[一二三四五六七八九])|(?:[一二三四五六七八九十]{1,3}))?)",
            line,
        )
        if nm:
            now_min = _parse_cn_clock_token(nm.group(1))
        em = re.search(
            r"从\s*[零一二三四五六七八九十两]+点"
            r"(?:半|整|(?:零[一二三四五六七八九])|(?:[一二三四五六七八九十]{1,3}))?\s*到\s*"
            r"([零一二三四五六七八九十两]+点"
            r"(?:半|整|(?:零[一二三四五六七八九])|(?:[一二三四五六七八九十]{1,3}))?)",
            line,
        )
        if em:
            end_min = _parse_cn_clock_token(em.group(1))

    if (
        now_min is not None
        and end_min is not None
        and now_min < end_min
        and re.search(r"正好|到点|时间到|已满|够了", full)
    ):
        errors.append(
            "可核对事实：「现在」未到所述结束时刻却说已到点/正好，"
            "请改时刻或改台词",
        )


def _append_duration_fact_errors(
    lines_text: list[str],
    full: str,
    errors: list[str],
) -> None:
    """约定 X 分钟 +「才 Y 分钟」且 Y<X 时，禁止说时间已到（有锚才查）。"""
    limit: int | None = None
    lm = re.search(
        rf"(?:说好|约定|只能|限时|就玩).{{0,8}}?({_DURATION_NUM})分钟",
        full,
    )
    if lm:
        limit = _parse_duration_minutes(lm.group(1))
    if limit is None:
        lm = re.search(
            rf"({_DURATION_NUM})分钟.{{0,6}}(?:到|满|结束|不能再)",
            full,
        )
        if lm:
            limit = _parse_duration_minutes(lm.group(1))
    elapsed_m = re.search(rf"才\s*({_DURATION_NUM})分钟", full)
    if limit is None or not elapsed_m:
        return
    elapsed = _parse_duration_minutes(elapsed_m.group(1))
    if limit is None or elapsed is None or elapsed >= limit:
        return
    for line in lines_text:
        if _line_claims_time_up(line):
            errors.append(
                f"可核对事实：约定{limit}分钟、才玩{elapsed}分钟时不应说时间到/到了，"
                "请改首句催促或改数字",
            )
            return


def _append_verifiable_fact_errors(story: dict, errors: list[str]) -> None:
    """正文出现可核对事实（钟点、时长、算式等）时，检查是否自相矛盾。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return

    lines_text = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    full = "".join(lines_text)
    _append_clock_fact_errors(lines_text, full, errors)
    _append_duration_fact_errors(lines_text, full, errors)


def _append_homework_fact_errors(story: dict, errors: list[str]) -> None:
    """教作业类：首句权责与口算事实勿自相矛盾。"""
    setting = str(story.get("setting") or "")
    core = str(story.get("conflict_core") or "")
    punch = str(story.get("punchline_explain") or "")
    blob = setting + core + punch
    if not re.search(r"作业|算术|算数|口算|竖式|算题", blob):
        return

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return

    first = dialogue[0]
    if isinstance(first, dict):
        sp = str(first.get("speaker") or "").strip()
        line0 = str(first.get("line") or "")
        if sp == "昭昭" and re.search(r"也算错|也写错|你也错", line0):
            errors.append(
                "教作业：正文首句应由灿灿查/教，禁止昭昭无前提「也算错了」",
            )
        if sp == "昭昭" and "也" in line0[:10] and "姐" in line0:
            errors.append(
                "教作业：首句「也」缺前文，改灿灿先挑错",
            )

    lines_text = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    full = "".join(lines_text)
    sum_m = re.search(
        r"(\d{1,3})\s*[加＋]\s*(\d{1,3})",
        full,
    )
    if not sum_m:
        return
    a, b = int(sum_m.group(1)), int(sum_m.group(2))
    correct = a + b
    correct_s = str(correct)

    # 灿灿用正确得数批弟弟错答案，却标成「姐姐算错」
    if (
        correct_s in full
        and re.search(r"算错|写错|教.*错", punch)
        and any(
            sp == "灿灿"
            and correct_s in ln
            and str(a) in ln
            and str(b) in ln
            for sp, ln in (
                (str(d.get("speaker") or "").strip(), str(d.get("line") or ""))
                for d in dialogue
                if isinstance(d, dict)
            )
        )
    ):
        wrong_claim = re.search(
            rf"{correct_s}.*错|错.*{correct_s}",
            full,
        )
        if not wrong_claim:
            errors.append(
                f"教作业事实：{a}+{b}={correct}为正确得数，"
                "灿灿若用该数批弟弟则不算姐姐算错，须改灿灿说错的得数",
            )


_DURATION_TOKEN_RE = re.compile(
    r"(?:半分钟|"
    r"(?:\d+|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|"
    r"[一二三四五六七八九两])分半|"
    r"(?:\d+|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|"
    r"[一二三四五六七八九两])分钟)"
)

# A 开场禁止先揭穿一锤（灿灿已翻车/双标）
_A_OPENING_SPOILER_RE = re.compile(
    r"自己才|自己刷了|自己算错|自己写错|自己弹错|"
    r"草稿.{0,6}错|计时器上自己|你也错了|"
    r"刚玩过|你上次|双标|才刷了半|一分半"
)
# A 开场禁止「互怼中途读数/宣判」——须先看见场面
_A_OPENING_MID_FIGHT_RE = re.compile(
    r"计时器才走|才走了\s*\d+\s*秒|才走了\s*[一二三四五六七八九十两半]+\s*秒|"
    r"至少两分钟|牙医说的|重刷|时间到了|到点了"
)

_RE_CLOSING_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)


def _duration_token_to_seconds(token: str) -> int | None:
    t = token.strip()
    if t == "半分钟":
        return 30
    if t.endswith("分半"):
        head = t[:-2]
        n = _parse_duration_minutes(head)
        return None if n is None else n * 60 + 30
    if t.endswith("分钟"):
        n = _parse_duration_minutes(t[:-2])
        return None if n is None else n * 60
    return None


def _iter_duration_seconds(text: str) -> list[int]:
    out: list[int] = []
    for m in _DURATION_TOKEN_RE.finditer(text or ""):
        sec = _duration_token_to_seconds(m.group(0))
        if sec is not None:
            out.append(sec)
    return out


def _append_brush_timer_fact_errors(story: dict, errors: list[str]) -> None:
    """刷牙/计时类：本场一锤时长全文只认一套，禁半分钟与一分半混用。"""
    setting = str(story.get("setting") or "")
    core = str(story.get("conflict_core") or "")
    punch = str(story.get("punchline_explain") or "")
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return
    lines_text = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    full = "".join(lines_text)
    blob = setting + core + punch + full
    if not re.search(r"刷牙|刷够", blob):
        return

    all_secs = set(_iter_duration_seconds(full))
    if len(all_secs) >= 4:
        errors.append(
            "可核对事实：刷牙/计时出现≥4种不同时长，"
            "本场一锤只留一套数（规则+弟弟+姐姐各至多一个）",
        )

    sister_secs: set[int] = set()
    brother_secs: set[int] = set()
    for line in lines_text:
        secs = _iter_duration_seconds(line)
        if not secs:
            continue
        if re.search(
            r"自己.{0,8}(?:刷|才)|上次.{0,12}(?:刷|才)|我那次|计时器上自己",
            line,
        ):
            sister_secs.update(secs)
        if re.search(
            r"你刷.{0,8}才|我(?:用了计时器|刷).{0,8}|"
            r"正好.{0,4}(?:两|二|\d)|刷干净了",
            line,
        ) or (
            "正好" in line and _iter_duration_seconds(line)
        ):
            if not re.search(r"自己|我那次|上次你|上次才", line):
                brother_secs.update(secs)

    if len(sister_secs) >= 2:
        errors.append(
            "可核对事实：灿灿自己刷牙时长前后不一"
            "（如半分钟与一分半），全文只留一个数",
        )
    if len(brother_secs) >= 2:
        errors.append(
            "可核对事实：昭昭刷牙时长前后不一"
            "（如才一分钟又说正好两分钟），请统一",
        )


def _append_a_closing_quote_errors(story: dict, errors: list[str]) -> None:
    """A 类：末段「你刚才说…」须能在灿灿前文找到原话。"""
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code != "A":
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return
    body = dialogue[:-4]
    cancan = "".join(
        str(d.get("line") or "")
        for d in body
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "灿灿"
    )
    if not cancan.strip():
        return

    def _grounded(frag: str, hay: str) -> bool:
        clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", frag)
        hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
        if len(clean) < 3:
            return True
        run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
        for i in range(len(clean) - run + 1):
            if clean[i:i + run] in hay2:
                return True
        if len(clean) < 6:
            pieces = [clean[i:i + 2] for i in range(0, len(clean) - 1, 2)]
            if len(pieces) >= 3:
                hit = sum(1 for p in pieces if p in hay2)
                if hit >= (len(pieces) * 2 + 2) // 3:
                    return True
        return False

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(item.get("line") or "")
        for m in _RE_CLOSING_QUOTE.finditer(line):
            frag = m.group(1).strip()
            prior_cancan = "".join(
                str(d.get("line") or "")
                for d in dialogue[:i]
                if isinstance(d, dict)
                and str(d.get("speaker") or "").strip() == "灿灿"
            )
            if not prior_cancan.strip():
                continue
            if not _grounded(frag, prior_cancan):
                soft_ok = (
                    (
                        re.search(r"吐水.{0,4}停", frag)
                        and re.search(r"吐水.{0,6}停", prior_cancan)
                    )
                    or (
                        re.search(r"漱口.{0,4}停", frag)
                        and re.search(r"漱口.{0,6}停", prior_cancan)
                    )
                    or (
                        re.search(r"检查.{0,6}不算吃", frag)
                        and re.search(r"检查.{0,10}不算", prior_cancan)
                    )
                )
                if not soft_ok:
                    errors.append(
                        f"A类引话须出自灿灿前文原话（无「{frag[:14]}」），"
                        "禁止昭昭自造后再假装引用",
                    )
                    return


_A_MID_RULE_STEMS = (
    ("漱口", 4),
    ("两分钟", 6),
    ("停了", 4),
    ("说话算数", 3),
)


def _line_bigrams(text: str) -> set[str]:
    chars = re.sub(r"[^\u4e00-\u9fff]", "", text or "")
    if len(chars) < 2:
        return set()
    return {chars[i:i + 2] for i in range(len(chars) - 1)}


def _lines_high_overlap(a: str, b: str, *, thresh: float = 0.5) -> bool:
    sa, sb = _line_bigrams(a), _line_bigrams(b)
    if len(sa) < 3 or len(sb) < 3:
        return False
    return len(sa & sb) / len(sa | sb) >= thresh


def _a_steal_context_blob(story: dict) -> str:
    parts = [
        str(story.get("conflict_core") or ""),
        str(story.get("scene_title") or ""),
        str(story.get("setting") or ""),
        str(story.get("punchline_explain") or ""),
    ]
    dialogue = story.get("dialogue") or []
    if isinstance(dialogue, list):
        for d in dialogue[:6]:
            if isinstance(d, dict):
                parts.append(str(d.get("line") or ""))
    return "".join(parts)


def _append_a_steal_single_line_errors(story: dict, errors: list[str]) -> None:
    """A 类饭前偷吃：单线免责 + 咽下后立刻收束（硬卡）。"""
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜|香蕉", blob):
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return
    text = "".join(
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    )
    buckets: list[str] = []
    # 硬卡只拦「检查 + 把关/示范」；试尝叠检查改由质检压分，避免生成空转
    if re.search(r"检查不算|检查样品|特地挑", text):
        buckets.append("检查")
    if re.search(r"把关|资格|负责质量|检查员|有特权|我有权利", text):
        buckets.append("把关")
    if re.search(r"示范", text):
        buckets.append("示范")
    if len(buckets) >= 2:
        errors.append(
            "A类偷吃只能一套免责（检查不算吃）；"
            f"正文叠了{'+'.join(buckets)}，删到只留检查线"
            "（禁把关/示范/资格）",
        )
        return

    # 收束硬卡（结构节奏交给质检，避免生成空转）
    lines = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    if len(lines) >= 3:
        dodge = lines[-3]
        if "那不一样" in dodge and re.search(
            r"那不一样[，,]?\s*(我那是)?[…\.。]{0,3}\s*$",
            dodge,
        ):
            errors.append(
                "收束「那不一样」须说完新借口（如检样不算开饭），禁止半截省略",
            )
        elif "那不一样" in dodge and not re.search(
            r"检样不算开饭|不算开饭",
            dodge,
        ):
            errors.append(
                "收束「那不一样」须用「检样不算开饭」类区分，"
                "禁止只回样品/检查的一部分",
            )


def _append_a_mid_restatement_errors(story: dict, errors: list[str]) -> None:
    """A 类：中段同一规矩勿换措辞再立一遍。"""
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "A":
        return
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return
    body = dialogue[:-4]
    lines: list[tuple[str, str]] = []
    for d in body:
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        ln = str(d.get("line") or "").strip()
        if ln:
            lines.append((sp, ln))
    if len(lines) < 8:
        return

    for stem, limit in _A_MID_RULE_STEMS:
        hits = sum(1 for _, ln in lines if stem in ln)
        if hits >= limit:
            errors.append(
                f"中段「{stem}」出现{hits}次：同一规矩只立一次"
                "（最多再确认1句），然后立刻进一锤场面",
            )
            return

    filler_hits = sum(
        1
        for _, ln in lines
        if re.search(
            r"你确定|说到做到|绝不反悔|你好好数|我看着|我数着|"
            r"眨眼睛|换手拿|中间不能|换位置|别数|没离开嘴巴|"
            r"挤牙膏了吗|牙刷没沾|你不能作弊|数得准|数错了|我看着你|"
            r"三十下|二十下|认真数|帮你盯|偷工减料|起步|"
            r"你又没计时|你也没计时|怎么证明|怎么知道我没|"
            r"数得慢|秒表一样|我数了",
            ln,
        )
    )
    if filler_hits >= 3:
        errors.append(
            "中段注水过多（三十下/认真数/计时抬杠等），"
            "埋「吐水算停」后立刻示范翻车",
        )
        return

    # 相邻两句同义复读：你又没计时 / 你也没计时 / 怎么证明
    for i in range(1, len(lines)):
        a, b = lines[i - 1][1], lines[i][1]
        if re.search(r"计时|怎么证明|怎么知道.{0,4}没", a) and re.search(
            r"计时|怎么证明|怎么知道.{0,4}没",
            b,
        ):
            errors.append(
                "中段禁止连着两句抠「没计时/怎么证明」同义抬杠，"
                "一句带过就进立规或示范",
            )
            return

    full_mid = "".join(ln for _, ln in lines)
    if re.search(r"刷牙|漱口|牙刷", full_mid):
        timer_pad = sum(
            1
            for _, ln in lines
            if re.search(
                r"默数|电子表|掐表|没带手机|计时器呢|用那个|我盯着表|帮你掐",
                ln,
            )
        )
        if timer_pad >= 3:
            errors.append(
                "刷牙中段禁止抠计时工具（默数/电子表/掐表），"
                "立完规矩后立刻示范翻车",
            )
            return
        # 一锤过晚：以「吐水算停」埋句为起点（勿用开场「两分钟」抬杠起算）
        rule_i = next(
            (
                i
                for i, (_, ln) in enumerate(lines)
                if re.search(r"吐水.{0,4}停", ln)
            ),
            None,
        )
        if rule_i is None:
            rule_i = next(
                (
                    i
                    for i, (_, ln) in enumerate(lines)
                    if "两分钟" in ln or "连续刷" in ln
                ),
                None,
            )
        hammer_i = next(
            (
                i
                for i, (sp, ln) in enumerate(lines)
                if i > (rule_i or 0)
                and re.search(
                    r"才刷|就吐|就停|就漱|玩手机|泡沫|几下|"
                    r"[一二三四五六七八九十两\d]+下|示范.{0,6}吐|噗|"
                    r"一[、,，]\s*二",
                    ln,
                )
                and (sp == "昭昭" or sp == "灿灿")
            ),
            None,
        )
        if rule_i is not None and hammer_i is None:
            errors.append(
                "刷牙缺一锤场面：须有昭昭指出灿灿示范时"
                "刷几下就吐/停/玩手机",
            )
            return
        if (
            rule_i is not None
            and hammer_i is not None
            and hammer_i - rule_i > 8
        ):
            errors.append(
                "刷牙一锤过晚：埋「吐水算停」后勿再抬杠，立刻示范翻车",
            )
            return
        many = any(
            sp == "灿灿" and re.search(r"很多下|刷了好多|刷了不少", ln)
            for sp, ln in lines
        )
        few = any(
            re.search(r"才刷\s*[一二两三四五六七八九十两\d]+\s*下", ln)
            for _, ln in lines
        )
        if many and few:
            errors.append(
                "刷牙次数自相矛盾：先说刷了很多下，后又才刷两三下，只留一套",
            )
            return
        # 埋句取最后一次「吐水…停」（开场抬杠可先谈两分钟）
        bury_idxs = [
            i for i, (_, ln) in enumerate(lines) if re.search(r"吐水.{0,4}停", ln)
        ]
        bury_i = bury_idxs[-1] if bury_idxs else None
        spit_hammer_i = next(
            (
                i
                for i, (_, ln) in enumerate(lines)
                if re.search(
                    r"才.{0,6}下|才刷|就吐|噗|"
                    r"一[、,，]\s*二|一\s*二\s*三",
                    ln,
                )
                and i > (bury_i or -1)
            ),
            None,
        )
        if bury_i is not None and spit_hammer_i is not None and spit_hammer_i - bury_i > 6:
            errors.append(
                "刷牙不好玩：埋「吐水算停」后铺垫过长，"
                "须很快出现数下就吐/噗",
            )
            return
        if bury_i is not None and spit_hammer_i is None:
            errors.append(
                "刷牙不好玩：有吐水算停却无一锤"
                "（才X下就吐 / 一、二、噗）",
            )
            return

    if dialogue:
        last = dialogue[-1]
        if isinstance(last, dict):
            last_ln = str(last.get("line") or "")
            if re.search(
                r"算你厉害|你赢了|算你赢|你厉害|你等着|"
                r"你.{0,4}(?:重刷|再刷|过关)",
                last_ln,
            ):
                errors.append(
                    "末句禁止认赢/甩狠/继续管人（重刷/你等着），"
                    "只许哼/行吧/随便/给你一块",
                )
                return
        # 收束「那不一样」禁止空甩身份
        if len(dialogue) >= 3:
            dodge = str(dialogue[-3].get("line") or "") if isinstance(dialogue[-3], dict) else ""
            if "那不一样" in dodge and re.search(r"我是姐姐|我说了算", dodge):
                if not re.search(
                    r"示范|泡沫|教学|吐泡沫|教你|检样|开饭|样品",
                    dodge,
                ):
                    errors.append(
                        "收束「那不一样」禁止只甩「我是姐姐」，"
                        "须具体借口（示范/检样不算开饭等）",
                    )
                    return

    zhao_qs = [
        (i, ln)
        for i, (sp, ln) in enumerate(lines)
        if sp == "昭昭" and ("？" in ln or "吗" in ln or "呢" in ln)
    ]
    for i in range(len(zhao_qs)):
        for j in range(i + 1, len(zhao_qs)):
            ia, la = zhao_qs[i]
            ib, lb = zhao_qs[j]
            if ib - ia > 8:
                break
            if _lines_high_overlap(la, lb):
                errors.append(
                    "中段昭昭换措辞重复追问同一规矩"
                    f"（近重复：「{la[:10]}」≈「{lb[:10]}」），"
                    "删掉重复回合直接进一锤",
                )
                return


_RE_ASK_WHAT_TERM = re.compile(
    r"什么叫\s*([\u4e00-\u9fff]{1,8})"
    r"|([\u4e00-\u9fff]{1,8})\s*是什么意思"
    r"|什么是\s*([\u4e00-\u9fff]{1,8})"
)


def _append_dangling_term_errors(story: dict, errors: list[str]) -> None:
    """禁止「什么叫连续」类追问在前文尚未出现该词。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return
    prior = ""
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        for m in _RE_ASK_WHAT_TERM.finditer(line):
            term = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            term = re.sub(r"[的呢吗啊呀嘛吧了]$", "", term)
            if len(term) < 2:
                continue
            if term not in prior:
                errors.append(
                    f"dialogue[{i}]「什么叫{term}」前文未出现「{term}」，"
                    "须先有人说出该词再追问（常见于开场顶掉正文首句后指代断裂）",
                )
                return
        prior += line



def _coerce_opening_item(item: object, *, index: int) -> tuple[dict | None, str | None]:
    """把开场单句规范成 {speaker,line}；无法识别则返回错误信息。"""
    if not isinstance(item, dict):
        return None, f"opening[{index}] 不是字典"
    speaker = str(item.get("speaker") or "").strip()
    line = str(item.get("line") or "").strip()
    if speaker and line:
        return {"speaker": speaker, "line": line}, None
    # {"昭昭":"台词"} 简写
    for name in ("昭昭", "灿灿", "妈妈"):
        if name in item and isinstance(item.get(name), str):
            text = str(item.get(name) or "").strip()
            if text:
                return {"speaker": name, "line": text}, None
    return None, f"opening[{index}] 缺少 speaker/line"


def validate_daily_story_opening(
    opening: list | None,
    *,
    conflict_core: str = "",
    setting: str = "",
    type_code: str | None = None,
) -> list[dict]:
    """校验发现开场 1–2 句，返回规范化列表；失败抛 ValueError。"""
    errors: list[str] = []
    if not isinstance(opening, list):
        raise ValueError("opening 必须是数组")
    if not (
        DAILY_STORY_OPENING_LINES_MIN
        <= len(opening)
        <= DAILY_STORY_OPENING_LINES_MAX
    ):
        errors.append(
            f"opening 须 {DAILY_STORY_OPENING_LINES_MIN}–"
            f"{DAILY_STORY_OPENING_LINES_MAX} 句，当前 {len(opening)}"
        )
    allowed = {"昭昭", "灿灿"}
    normalized: list[dict] = []
    for i, item in enumerate(opening or []):
        coerced, err = _coerce_opening_item(item, index=i)
        if err:
            errors.append(err)
            continue
        assert coerced is not None
        speaker = coerced["speaker"]
        line = coerced["line"]
        if speaker not in allowed:
            errors.append(f"opening[{i}] speaker 须为昭昭/灿灿，收到：{speaker!r}")
        if not line or not re.search(r"[\u4e00-\u9fff\w]", line):
            errors.append(f"opening[{i}] line 须含可发音内容")
        else:
            n = _dialogue_char_count(line)
            if n > DAILY_STORY_LINE_CHARS_MAX:
                errors.append(
                    f"opening[{i}] line 超过{DAILY_STORY_LINE_CHARS_MAX}字"
                    f"（{n}字）：{line!r}"
                )
            else:
                normalized.append({"speaker": speaker, "line": line})

    # 开场内部也禁同人连说
    for i in range(1, len(normalized)):
        if normalized[i]["speaker"] == normalized[i - 1]["speaker"]:
            errors.append(
                f"opening[{i - 1}:{i}] {normalized[i]['speaker']} 连说；"
                "两句开场须换人"
            )
            break

    core = (conflict_core or "").strip()
    anchors = _conflict_anchor_tokens(core)
    must = _conflict_anchor_must_words(core)
    joined = "".join(d["line"] for d in normalized)
    # 锚点须落在开场台词或 setting（core 自身不算已体现）
    ctx = (setting or "") + joined
    if anchors and normalized and not _conflict_anchors_hit(core, ctx, anchors):
        hint = "、".join(must) if must else "、".join(anchors[:4])
        errors.append(
            f"发现开场未体现 conflict_core 锚点（须点名其一：{hint}）：{core!r}"
        )

    code = (type_code or "").strip().upper()[:1]
    if code == "A":
        for i, item in enumerate(normalized):
            line = item["line"]
            if _A_OPENING_SPOILER_RE.search(line):
                errors.append(
                    f"opening[{i}] A类禁止开场先揭穿灿灿翻车/双标"
                    "（自己才刷/算错/刚玩过等），一锤留给正文中段",
                )
                break
            if _A_OPENING_MID_FIGHT_RE.search(line):
                errors.append(
                    f"opening[{i}] A类开场须像发现现场（物/动作），"
                    "禁止读秒宣判或直接立规（如「计时器才走了30秒」）",
                )
                break

    if errors:
        raise ValueError("daily_story 开场校验失败: " + "; ".join(errors))
    return normalized


def _dialogue_lines_overlap(a: str, b: str) -> bool:
    """判断两句是否高度重叠（用于拼接时去掉正文重复发现句）。"""
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    limit = min(len(left), len(right))
    for n in range(4, limit + 1):
        if left[:n] == right[:n] or left[-n:] == right[:n]:
            return True
    return False


def stitch_daily_story_opening(
    story: dict,
    opening: list[dict],
) -> dict:
    """将发现开场前置到 dialogue。

    1) 去掉正文开头与开场高度重叠的发现句；
    2) 若开场末句与正文首句同人，丢掉正文首句（防拼后连说）。
    """
    out = copy.deepcopy(story)
    body = list(out.get("dialogue") or [])
    if not isinstance(body, list):
        body = []
    opening_norm = [
        {"speaker": str(d.get("speaker") or "").strip(),
         "line": str(d.get("line") or "").strip()}
        for d in opening
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]
    dropped = 0
    while body and opening_norm and dropped < DAILY_STORY_OPENING_LINES_MAX:
        first = body[0] if isinstance(body[0], dict) else None
        first_line = str((first or {}).get("line") or "").strip()
        if any(_dialogue_lines_overlap(o["line"], first_line) for o in opening_norm):
            body.pop(0)
            dropped += 1
            continue
        break
    # 接缝同人：丢掉正文开头连说句（最多 2 句，避免掏空）
    speaker_drops = 0
    while body and opening_norm and speaker_drops < 2:
        first = body[0] if isinstance(body[0], dict) else None
        first_sp = str((first or {}).get("speaker") or "").strip()
        last_sp = opening_norm[-1]["speaker"]
        if first_sp in ("昭昭", "灿灿") and first_sp == last_sp:
            body.pop(0)
            speaker_drops += 1
            continue
        break
    out["dialogue"] = opening_norm + body
    out["discovery_opening"] = opening_norm
    return out


def opening_avoid_speaker_from_body(body: dict | None) -> str | None:
    """正文首句说话人：开场末句应避开此人，减少拼缝连说。"""
    if not isinstance(body, dict):
        return None
    dialogue = body.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return None
    first = dialogue[0] if isinstance(dialogue[0], dict) else None
    sp = str((first or {}).get("speaker") or "").strip()
    return sp if sp in ("昭昭", "灿灿") else None


_KNOWN_SPEAKER_TYPOS = frozenset({"speayer", "speeker", "spaker"})


def _correct_dialogue_speaker(dialogue: list) -> None:
    """原地修正 dialogue 列表中 speaker 字段的常见 LLM 拼写错误。"""
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        if "speaker" not in item:
            for typo in _KNOWN_SPEAKER_TYPOS:
                if typo in item:
                    item["speaker"] = item.pop(typo)
                    break


def build_daily_story_theme_prompts(
    count: int,
    *,
    type_code: str | None = None,
) -> tuple[str, str]:
    """构造日常故事主题生成的 system + user 提示词。"""
    user = DAILY_STORY_THEME_USER_TEMPLATE.format(count=count)
    if type_code and type_code.upper() in STORY_TYPE_LINES:
        extra = STORY_TYPE_LINES[type_code.upper()].theme_user_append.strip()
        if extra:
            user = f"{user}\n{extra}"
    return DAILY_STORY_THEME_SYSTEM_PROMPT, user


def dialogue_total_chars(story: dict | None) -> int:
    """统计 story.dialogue 可发音台词总字数。"""
    if not isinstance(story, dict):
        return 0
    dialogue = story.get("dialogue") or []
    if not isinstance(dialogue, list):
        return 0
    total = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if line and re.search(r"[\u4e00-\u9fff\w]", line):
            total += _dialogue_char_count(line)
    return total


_LOCAL_PAD_TAILS = ("呀", "呢", "吧", "嘛", "啊")  # 勿用「啦」灌水
_LOCAL_TRIM_CHARS = "的了呢嘛呀啊吧啦哦喔哈嗯"


def _clone_story(story: dict) -> dict:
    return json.loads(json.dumps(story, ensure_ascii=False))


def _line_room(line: str) -> int:
    return max(0, DAILY_STORY_LINE_CHARS_MAX - _dialogue_char_count(line))


def _pad_dialogue_line(line: str, need: int) -> tuple[str, int]:
    """句尾最多补一个语气词，返回 (新句, 实际增加字数)。"""
    if need <= 0 or not line:
        return line, 0
    if line[-1] in "啦嘛呀啊呢吧哦！？。…":
        return line, 0
    room = _line_room(line)
    if room <= 0:
        return line, 0
    for suf in _LOCAL_PAD_TAILS:
        if len(suf) <= room and len(suf) <= need:
            return f"{line}{suf}", len(suf)
    return line, 0


def _trim_dialogue_line(line: str, need: int) -> tuple[str, int]:
    """从句尾虚词删起，返回 (新句, 实际删掉字数)。"""
    if need <= 0 or len(line) < 4:
        return line, 0
    out = line
    removed = 0
    while removed < need and len(out) > 4:
        ch = out[-1]
        if ch in _LOCAL_TRIM_CHARS or ch in "，。！？…、 ":
            out = out[:-1]
            removed += 1
            continue
        break
    return out, removed


def _truncate_overlong_line(line: str) -> str:
    """超长句压到硬卡：优先在标点处切。"""
    n = _dialogue_char_count(line)
    if n <= DAILY_STORY_LINE_CHARS_MAX:
        return line
    limit = DAILY_STORY_LINE_CHARS_MAX
    cut = -1
    for i, ch in enumerate(line):
        if i >= limit:
            break
        if ch in "，、；; ":
            cut = i
    if cut >= 6:
        return line[:cut].rstrip("，、；; ")
    return line[:limit]


def _patch_overlong_lines(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if _dialogue_char_count(line) <= DAILY_STORY_LINE_CHARS_MAX:
            continue
        new_line = _truncate_overlong_line(line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"超长句[{i}]截断")
    return notes


def _patch_body_char_budget(story: dict) -> list[str]:
    """仅小缺口本地补/删语气词；大缺口留给 LLM，避免硬塞口感崩。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    mid = dialogue[:-4]
    total = dialogue_total_chars(story)
    if total < DAILY_STORY_BODY_CHARS_MIN:
        need = DAILY_STORY_BODY_CHARS_MIN - total
        # 差太多硬补会怪，只处理小缺口
        if need > DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return notes
        before = total
        for item in mid:
            if need <= 0:
                break
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            if not line:
                continue
            new_line, added = _pad_dialogue_line(line, need)
            if added:
                item["line"] = new_line
                need -= added
        after = dialogue_total_chars(story)
        if after > before:
            notes.append(f"本地补字{before}→{after}")
    elif total > DAILY_STORY_BODY_CHARS_MAX:
        excess = total - DAILY_STORY_BODY_CHARS_MAX
        if excess > DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return notes
        before = total
        for item in reversed(mid):
            if excess <= 0:
                break
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            new_line, removed = _trim_dialogue_line(line, excess)
            if removed:
                item["line"] = new_line
                excess -= removed
        after = dialogue_total_chars(story)
        if after < before:
            notes.append(f"本地删字{before}→{after}")
    return notes


def _quote_grounded(frag: str, hay: str) -> bool:
    clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", frag)
    hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
    if len(clean) < 3:
        return True
    run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
    for i in range(len(clean) - run + 1):
        if clean[i:i + run] in hay2:
            return True
    return False


def _pick_cite_chunk(cancan_line: str) -> str:
    """从灿灿句抽出可引短串。"""
    text = re.sub(r"^[「」\"'‘’]+|[「」\"'‘’]+$", "", cancan_line.strip())
    for m in re.finditer(r"[^，。！？…；;]{4,14}", text):
        chunk = m.group(0).strip()
        if re.search(r"不算|算停|吐水|检查|示范|咽了", chunk):
            return chunk
    # fallback: 去掉语气后截断
    compact = re.sub(r"[的话呢呀嘛吧啊啦]", "", text)
    return compact[:14] if len(compact) >= 4 else text[:14]


def _patch_a_closing_quotes(story: dict) -> list[str]:
    """引话未接地：仅当灿灿前文已有相近埋点时，把昭昭引语改成可引子串。

    若前文完全没有「检查/吐水/不算」类埋点，不硬改（交给 LLM）。
    """
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(item.get("line") or "")
        m = _RE_CLOSING_QUOTE.search(line)
        if not m:
            continue
        frag = m.group(1).strip()
        prior_lines = [
            str(d.get("line") or "")
            for d in dialogue[:i]
            if isinstance(d, dict)
            and str(d.get("speaker") or "").strip() == "灿灿"
            and str(d.get("line") or "").strip()
        ]
        prior = "".join(prior_lines)
        if not prior.strip():
            continue
        soft_ok = (
            (
                re.search(r"检查.{0,6}不算吃", frag)
                and re.search(r"检查.{0,10}不算", prior)
            )
            or (
                re.search(r"吐水.{0,4}停", frag)
                and re.search(r"吐水.{0,6}停", prior)
            )
            or (
                re.search(r"漱口.{0,4}停", frag)
                and re.search(r"漱口.{0,6}停", prior)
            )
        )
        # 偷吃：前文已埋「检查不算吃」时，引话须点到这句（勿只引咽了才算）
        prefer_check = (
            "检查不算吃" in prior
            and "检查不算吃" not in frag
            and re.search(r"偷吃|饭前|水果|样品|检查", prior)
        )
        if (_quote_grounded(frag, prior) or soft_ok) and not prefer_check:
            continue
        donor = ""
        if prefer_check:
            for ln in reversed(prior_lines):
                if "检查不算吃" in ln:
                    donor = ln
                    break
        if not donor:
            for ln in reversed(prior_lines):
                if re.search(r"不算|吐水|检查|示范|算停", ln):
                    donor = ln
                    break
        # 没有可对齐埋点就别乱改引话
        if not donor:
            continue
        cite = (
            "检查不算吃"
            if prefer_check and "检查不算吃" in donor
            else _pick_cite_chunk(donor)
        )
        if not cite or (
            not prefer_check
            and not _quote_grounded(cite, donor)
            and cite not in donor
        ):
            cite = donor[: min(12, len(donor))]
        if prefer_check:
            new_line = f"你刚才说{cite}"
        else:
            head = line[: m.start(1)]
            tail = line[m.end(1) :]
            room = DAILY_STORY_LINE_CHARS_MAX - _dialogue_char_count(head + tail)
            if room < 4:
                continue
            new_frag = cite if _dialogue_char_count(cite) <= room else cite[:room]
            new_line = f"{head}{new_frag}{tail}"
        if _dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            new_line = _truncate_overlong_line(new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"引话对齐[{i}]")
            break
    return notes


def _patch_setting_mom_without_line(story: dict) -> list[str]:
    """setting 写了妈妈动作但正文无妈妈台词 → 改由姐弟场景。"""
    notes: list[str] = []
    setting = str(story.get("setting") or "")
    if "妈妈" not in setting:
        return notes
    dialogue = story.get("dialogue") or []
    has_mom = any(
        isinstance(d, dict) and str(d.get("speaker") or "").strip() == "妈妈"
        for d in dialogue
    )
    if has_mom:
        return notes
    new_setting = setting.replace("妈妈切", "桌上摆着").replace("妈妈", "")
    new_setting = re.sub(r"\s{2,}", " ", new_setting).strip("，,。 ")
    if new_setting and new_setting != setting:
        story["setting"] = new_setting
        notes.append("setting去妈妈")
    return notes


_A_STEAL_TRY_TASTE_RE = re.compile(
    r"试甜|试味道|帮你试|尝一下|尝得准|尝了|只尝|尝味道|甜不甜|"
    r"试一口|确认味道|咬一口就|知道甜|先试|算尝味|是甜的|甜度|"
    r"看看熟|熟不熟|坏了没|有没有坏|测试甜|确认质量"
)
_A_STEAL_GATE_RE = re.compile(
    r"把关|资格|负责质量|检查员|有特权|质量员|我负责|我有权利"
)
_A_STEAL_QC_RE = re.compile(
    r"半成品|大家安全|新不新鲜|为了大家|品质检测|安全起见|合格证书|"
    r"确认甜度|确认质量|含着|检查完"
)
_A_STEAL_DODGE_RE = re.compile(r"溅|手脏|擦过|果汁")  # 鼓鼓只算发现，不算赖账


def _patch_a_steal_strip_qc_jargon(story: dict) -> list[str]:
    """偷吃去掉质检说明书词，改回赖账/检查口径。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        sp = str(d.get("speaker") or "")
        new_line = line
        if _A_STEAL_QC_RE.search(line):
            if sp == "灿灿":
                new_line = "这是检查样品，是我特地挑出来检查的"
            else:
                new_line = "检查样品就能先吃掉？"
        elif "洗手" in line:
            if sp == "灿灿":
                new_line = "你手脏，先别碰这个盘子"
            else:
                new_line = "你手不也刚捏过水果吗"
        if (
            new_line != line
            and _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去质检词[{i}]")
    return notes


def _patch_a_steal_strip_try_taste(story: dict) -> list[str]:
    """偷吃已走检查线时，把试甜/尝味句改回检查口径（去叠免责）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not _A_STEAL_TRY_TASTE_RE.search(line):
            continue
        if re.search(r"咽|看不了", line):
            new_line = "嗯，检查完了，只好咽了"
        elif re.search(r"样品|检查", line):
            new_line = "这是检查样品，是我特地挑出来检查的"
        else:
            new_line = _A_STEAL_TRY_TASTE_RE.sub("", line)
            new_line = re.sub(r"[，,]{2,}", "，", new_line)
            new_line = re.sub(r"\s{2,}", " ", new_line).strip("，,。 ")
            if len(new_line) < 4:
                new_line = "这是检查样品，是我特地挑出来检查的"
        if (
            new_line != line
            and _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去试尝[{i}]")
    return notes


def _patch_a_steal_strip_gate(story: dict) -> list[str]:
    """偷吃已走检查线时，删把关/资格/检查员等叠套词。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    if not _A_STEAL_GATE_RE.search(text):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        line = str(d.get("line") or "")
        if not _A_STEAL_GATE_RE.search(line):
            continue
        new_line = _A_STEAL_GATE_RE.sub("", line)
        new_line = re.sub(r"[，,]{2,}", "，", new_line)
        new_line = re.sub(r"\s{2,}", " ", new_line).strip("，,。 ")
        if len(new_line) < 4:
            # 整句只剩身份话术：换成检查线短句，避免空行硬卡
            if "那不一样" in line:
                new_line = "那不一样，检样不算开饭"
            else:
                new_line = "这是检查样品，是我特地挑出来检查的"
        if (
            new_line != line
            and _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
        ):
            d["line"] = new_line
            notes.append(f"偷吃去把关[{i}]")
    return notes


def _patch_a_steal_fix_broken_authority(story: dict) -> list[str]:
    """修好半截「我是姐姐，…啦」残句，避免补语气词后更怪。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, d in enumerate(dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "").strip()
        if not re.match(r"^我是姐姐[，,]", line):
            continue
        # 过短或明显截断：先/我得/得 + 可选啦
        if len(line) <= 8 or re.match(
            r"^我是姐姐[，,]\s*(先|我得|得|管)啦?$",
            line,
        ):
            new_line = "我是姐姐，饭前你不能吃"
            if (
                new_line != line
                and _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX
            ):
                d["line"] = new_line
                notes.append(f"偷吃修权威残句[{i}]")
    return notes


def _patch_a_steal_ensure_beats(story: dict) -> list[str]:
    """偷吃检查线：补「我是姐姐 / 上次 / 检查不算吃」骨架词（助冲突层+引话）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"检查不算|检查样品|特地挑", text):
        return notes
    mid = [d for d in dialogue[:-4] if isinstance(d, dict)]
    if len(mid) < 4:
        return notes

    def _set_line(d: dict, new_line: str, note: str) -> bool:
        if _dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            return False
        if new_line == str(d.get("line") or ""):
            return False
        d["line"] = new_line
        notes.append(note)
        return True

    if "我是姐姐" not in text:
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"饭前|不许|不能吃|我说不行", line):
                cand = f"我是姐姐，{line}"
                if _set_line(d, cand, "偷吃补我是姐姐"):
                    break
        else:
            for d in mid:
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "我是姐姐，饭前你不能吃",
                        "偷吃补我是姐姐",
                    ):
                        break

    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if not re.search(r"上次", text):
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"溅|手脏|别碰|果汁", line) or len(line) <= 10:
                if _set_line(
                    d,
                    "上次是上次，妈妈在今天不算",
                    "偷吃补上次",
                ):
                    break
        else:
            # 找中段第二句灿灿位改写
            for d in mid[2:]:
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "上次是上次，妈妈在今天不算",
                        "偷吃补上次",
                    ):
                        break

    text = "".join(
        str(d.get("line") or "") for d in dialogue if isinstance(d, dict)
    )
    if "检查不算吃" not in text:
        for d in mid:
            if str(d.get("speaker") or "") != "灿灿":
                continue
            line = str(d.get("line") or "")
            if re.search(r"检查样品|特地挑|样品", line):
                if _set_line(
                    d,
                    "检查不算吃，咽了才算检",
                    "偷吃补检查不算吃",
                ):
                    break
        else:
            for d in reversed(mid):
                if str(d.get("speaker") or "") == "灿灿":
                    if _set_line(
                        d,
                        "检查不算吃，咽了才算检",
                        "偷吃补检查不算吃",
                    ):
                        break
    return notes


def _patch_a_steal_closing(story: dict) -> list[str]:
    """偷吃收束：统一成「那不一样，检样不算开饭」。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    dodge = dialogue[-3]
    if not isinstance(dodge, dict):
        return notes
    line = str(dodge.get("line") or "")
    if "那不一样" not in line:
        return notes
    new_line = "那不一样，检样不算开饭"
    if line != new_line and _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
        dodge["line"] = new_line
        notes.append("收束改检样不算开饭")
    return notes


def _patch_a_steal_trim_la(story: dict) -> list[str]:
    """偷吃：句尾语气词过多时剥掉，避免补字注水。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    particle_idx = [
        i
        for i, d in enumerate(dialogue)
        if isinstance(d, dict)
        and re.search(r"[啦呀嘛啊呢吧]$", str(d.get("line") or "").rstrip())
    ]
    if len(particle_idx) < 3:
        return notes
    # 最多留 1 个句尾语气词
    for i in particle_idx[1:]:
        line = str(dialogue[i].get("line") or "")
        new_line = re.sub(r"[啦呀嘛啊呢吧]+$", "", line).rstrip("，, ")
        if new_line and new_line != line:
            dialogue[i]["line"] = new_line
            notes.append(f"偷吃去语气词[{i}]")
    return notes


def _patch_a_steal_dedupe_sister(story: dict) -> list[str]:
    """「我是姐姐」全场只留一次。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    seen = False
    for i, d in enumerate(dialogue[:-4] if len(dialogue) > 4 else dialogue):
        if not isinstance(d, dict):
            continue
        if str(d.get("speaker") or "") != "灿灿":
            continue
        line = str(d.get("line") or "")
        if "我是姐姐" not in line:
            continue
        if not seen:
            seen = True
            continue
        new_line = "饭前你不能吃，听到没"
        if _dialogue_char_count(new_line) <= DAILY_STORY_LINE_CHARS_MAX:
            d["line"] = new_line
            notes.append(f"偷吃去姐姐复读[{i}]")
    return notes


def _steal_dodge_templates(prev_speaker: str) -> list[tuple[str, str]]:
    """按上一句 speaker 选交替赖账四句，避免连说。"""
    if prev_speaker == "昭昭":
        return [
            ("灿灿", "果汁溅脸上了，不是偷吃"),
            ("昭昭", "溅脸上？你整块塞嘴里了"),
            ("灿灿", "你手脏，先别碰这个盘子"),
            ("昭昭", "你手不也刚捏过水果吗"),
        ]
    return [
        ("昭昭", "那你腮帮子一动一动的"),
        ("灿灿", "果汁溅脸上了，不是偷吃"),
        ("昭昭", "溅脸上？你整块塞嘴里了"),
        ("灿灿", "你手脏，先别碰这个盘子"),
    ]


def _patch_a_steal_fix_dodge_roles(story: dict) -> list[str]:
    """赖账借口须灿灿说；角色反了则整段重写第 2–5 句，避免连说。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    excuse_re = re.compile(r"溅脸上了|不是偷吃|手脏，先别碰|我擦过了")
    flipped = any(
        isinstance(d, dict)
        and str(d.get("speaker") or "") == "昭昭"
        and excuse_re.search(str(d.get("line") or ""))
        for d in dialogue[:-4]
    )
    if not flipped:
        return notes
    prev = str(dialogue[1].get("speaker") or "") if isinstance(dialogue[1], dict) else ""
    templates = _steal_dodge_templates(prev)
    for i, (sp, ln) in enumerate(templates):
        idx = 2 + i
        if not isinstance(dialogue[idx], dict):
            return notes
        dialogue[idx]["speaker"] = sp
        dialogue[idx]["line"] = ln
        notes.append(f"偷吃纠角色[{idx}]")
    return notes


def _patch_a_steal_ensure_dodge(story: dict) -> list[str]:
    """检查样品前须有赖账抬杠（溅脸/手脏）；缺则改写中前段 2 来回。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(punchline=punch)
    if code and code != "A":
        return notes
    blob = _a_steal_context_blob(story)
    if not re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄|西瓜", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 12:
        return notes
    lines = [str(d.get("line") or "") if isinstance(d, dict) else "" for d in dialogue]
    check_i = next(
        (
            i
            for i, ln in enumerate(lines)
            if re.search(r"检查样品|特地挑|检查不算吃", ln)
        ),
        None,
    )
    if check_i is None:
        return notes
    cancan_dodge = any(
        isinstance(dialogue[i], dict)
        and str(dialogue[i].get("speaker") or "") == "灿灿"
        and re.search(r"溅|手脏|擦过|果汁", str(dialogue[i].get("line") or ""))
        for i in range(check_i)
    )
    if cancan_dodge:
        return notes
    if len(dialogue) < 10:
        return notes
    saved_check = ""
    for i in range(2, 6):
        if isinstance(dialogue[i], dict) and re.search(
            r"检查样品|特地挑|检查不算吃",
            str(dialogue[i].get("line") or ""),
        ):
            saved_check = str(dialogue[i].get("line") or "")
            break
    prev = str(dialogue[1].get("speaker") or "") if isinstance(dialogue[1], dict) else ""
    templates = _steal_dodge_templates(prev)
    for i, (sp, ln) in enumerate(templates):
        idx = 2 + i
        if not isinstance(dialogue[idx], dict):
            return notes
        dialogue[idx]["speaker"] = sp
        dialogue[idx]["line"] = ln
        notes.append(f"偷吃补赖账[{idx}]")
    if saved_check:
        for j in range(6, len(dialogue) - 4):
            if not isinstance(dialogue[j], dict):
                continue
            if str(dialogue[j].get("speaker") or "") != "灿灿":
                continue
            cur = str(dialogue[j].get("line") or "")
            if re.search(r"检查样品|特地挑|检查不算吃", cur):
                break
            dialogue[j]["line"] = (
                saved_check
                if _dialogue_char_count(saved_check) <= DAILY_STORY_LINE_CHARS_MAX
                else "这是检查样品，是我特地挑出来检查的"
            )
            notes.append(f"偷吃挪检查[{j}]")
            break
    return notes


def _patch_consecutive_speakers(story: dict) -> list[str]:
    """同人连说：把后一句 speaker 改成另一方（仅修硬卡，少动文案）。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    for i in range(1, len(dialogue)):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa in {"昭昭", "灿灿"} and sa == sb:
            b["speaker"] = "灿灿" if sa == "昭昭" else "昭昭"
            notes.append(f"连说改speaker[{i}]")
            # 每处只改一次，避免连锁乱改
            break
    return notes


def try_local_patch_daily_story_body(story: dict) -> tuple[dict, list[str]]:
    """校验前确定性修补：超长句/字数小缺口/引话/setting妈妈。

    能修则少打一轮 LLM；修不干净仍交重试。
    """
    if not isinstance(story, dict):
        return story, []
    out = _clone_story(story)
    notes: list[str] = []
    notes.extend(_patch_overlong_lines(out))
    notes.extend(_patch_setting_mom_without_line(out))
    notes.extend(_patch_consecutive_speakers(out))
    notes.extend(_patch_a_steal_strip_try_taste(out))
    notes.extend(_patch_a_steal_strip_gate(out))
    notes.extend(_patch_a_steal_strip_qc_jargon(out))
    notes.extend(_patch_a_steal_ensure_dodge(out))
    notes.extend(_patch_a_steal_fix_dodge_roles(out))
    notes.extend(_patch_a_steal_fix_broken_authority(out))
    notes.extend(_patch_a_steal_ensure_beats(out))
    notes.extend(_patch_a_steal_dedupe_sister(out))
    notes.extend(_patch_a_closing_quotes(out))
    notes.extend(_patch_a_steal_closing(out))
    notes.extend(_patch_a_steal_trim_la(out))
    notes.extend(_patch_body_char_budget(out))
    # 补字后可能又超单句硬卡 / 又引出连说 / 又叠试尝
    notes.extend(_patch_overlong_lines(out))
    notes.extend(_patch_consecutive_speakers(out))
    notes.extend(_patch_a_steal_strip_try_taste(out))
    notes.extend(_patch_a_steal_strip_gate(out))
    notes.extend(_patch_a_steal_strip_qc_jargon(out))
    notes.extend(_patch_a_steal_trim_la(out))
    notes.extend(_patch_a_steal_fix_broken_authority(out))
    notes.extend(_patch_a_steal_closing(out))
    return out, notes


def _parse_body_char_deficit(errors: str) -> int | None:
    """从校验文案解析还差 N 字。"""
    m = re.search(r"还差\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None


def _parse_body_char_excess(errors: str) -> int | None:
    """从校验文案解析超出 N 字。"""
    m = re.search(r"超出\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None


def resolve_daily_story_retry_length_mode(
    prev_story: dict | None,
    *,
    errors: str = "",
) -> str:
    """按本轮错误 + 上一稿字数选择重试 length_mode。

    优先信校验文案（总字数须≥/≤）；只差几个字走 revise_patch；
    字数已在区间时走 revise，避免「只修连说」被 trim/expand 带跑篇幅。
    """
    err = errors or ""
    deficit = _parse_body_char_deficit(err)
    excess = _parse_body_char_excess(err)
    if "总字数须≥" in err:
        if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        return "revise_expand"
    if "总字数须≤" in err:
        if excess is not None and excess <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        return "revise_trim"
    # 引话局部问题：优先微调 1–2 句，勿整篇扩写冲垮骨架
    if "引话" in err:
        return "revise_patch"
    chars = dialogue_total_chars(prev_story if isinstance(prev_story, dict) else None)
    if chars < DAILY_STORY_BODY_CHARS_MIN:
        gap = DAILY_STORY_BODY_CHARS_MIN - chars
        if gap <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        return "revise_expand"
    if chars > DAILY_STORY_BODY_CHARS_MAX:
        gap = chars - DAILY_STORY_BODY_CHARS_MAX
        if gap <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        return "revise_trim"
    return "revise"


def _retry_issue_hints(
    errors: str,
    *,
    chars: int,
    type_code: str | None = None,
) -> str:
    """按本轮校验问题追加可执行修订指令。"""
    hints: list[str] = []
    err = errors or ""
    if "连说" in err:
        hints.append(
            "【连说】全文改为昭昭/灿灿严格交替；把连说拆开或改 speaker，"
            f"勿借机大删；保持约 {chars} 字（{DAILY_STORY_BODY_CHARS_MIN}–"
            f"{DAILY_STORY_BODY_CHARS_MAX}）。"
        )
    if "注水" in err or "三十下" in err or "认真数" in err:
        hints.append(
            "【删注水】删掉三十下/认真数/帮你盯/换位置/检查员把关；"
            "用拌嘴抬杠补字，只留一套免责埋句。"
        )
    if "多套免责" in err or "借口复读" in err or "只能一套免责" in err:
        hints.append(
            "【单线借口】偷吃只留「检查不算吃」；删试甜/示范/资格/把关；"
            "咽下后立刻末四拍，勿写质检说明书。"
        )
    if "咽下" in err and ("末四拍" in err or "质检" in err):
        hints.append(
            "【偷吃收束】已经咽/看不了后最多再 1 来回，立刻："
            "你刚才说检查不算吃→检样不算开饭→都进肚子了→行吧给你一块。"
        )
    if "提前引话" in err:
        hints.append(
            "【引话位置】删掉中段所有「你刚才说」；只保留末四拍那一句引「检查不算吃」。"
        )
    if "半截" in err or ("那不一样" in err and ("省略" in err or "样品" in err)):
        hints.append(
            "【收束说完】那不一样须接「检样不算开饭」，禁止半截或只说这是样品。"
        )
    if "不好玩" in err or ("吐水算停" in err and "一锤" in err):
        hints.append(
            "【刷牙一锤】埋「吐水也算停」后下一来回必须示范："
            "灿灿「一、二、三——噗」或昭昭「才刷几下就吐」。"
        )
    if "引话" in err:
        hints.append(
            "【引话·只改1–2句】保留全文骨架：要么把灿灿前文埋句改成昭昭所引原话，"
            "要么把昭昭引话改成灿灿已说过的子串；禁止整篇重写。"
        )
    deficit = _parse_body_char_deficit(err)
    if "总字数须≥" in err:
        if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            hints.append(
                f"【补字·句内】只差 {deficit} 字：在中段 2–3 句各加 2–6 字抬杠语气，"
                f"禁止插入新句、禁止动末四拍；写到 ≥{DAILY_STORY_BODY_CHARS_MIN}。"
            )
        else:
            hints.append(
                "【补字】在立规前加抬杠、一锤后加追问；"
                "禁止用三十下/认真数/计时器注水凑字。"
            )
    if "无破功软收" in err or "弱收束" in err:
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        hints.append(
            soft
            or (
                "【收束】只改末 2–3 句：倒数第 2 句字面戳穿/自相矛盾，"
                "末句破功哑口或嘴硬软收；"
                "禁止一人一半/平分、反正我要用、等妈评理。"
            )
        )
    if "超过" in err and f"{DAILY_STORY_LINE_CHARS_MAX}字" in err:
        hints.append(
            f"【单句】超长句压到 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；"
            "可拆给两人轮流说，禁止同人连说硬拆。"
        )
    if "跑题" in err:
        hints.append("【跑题】删掉后半无关主线，回到 conflict_core。")
    if not hints and "总字数" not in err:
        hints.append(
            f"【篇幅】字数已在硬卡内（当前约 {chars}），"
            "只改本轮问题，禁止大幅增删。"
        )
    return ("\n".join(hints) + "\n") if hints else ""


def build_daily_story_retry_user(
    theme: str,
    *,
    prev_story: dict,
    errors: str,
    phase: str = "body",
    story_type: str | None = None,
) -> str:
    """构造垂直修订重试 user：只列本轮问题 + 上一稿，不复述全套规则。

    偏短：只增不删；偏长：只删不增（超出少则只删 1 句，防砍过猛）。
    连说/软收等非字数问题走专项 hint，避免越修越短。
    system 须用同向 length_mode（见 resolve_daily_story_retry_length_mode）。
    phase 保留兼容，正文重试固定走 body 硬卡。
    """
    _ = phase
    chars = dialogue_total_chars(prev_story)
    chars_min = DAILY_STORY_BODY_CHARS_MIN
    chars_max = DAILY_STORY_BODY_CHARS_MAX
    aim_lo = DAILY_STORY_BODY_RETRY_TARGET_MIN
    aim_hi = DAILY_STORY_BODY_RETRY_TARGET_MAX
    avg_line = 12
    length_hint = ""
    if chars < chars_min:
        deficit = chars_min - chars
        err_deficit = _parse_body_char_deficit(errors)
        if err_deficit is not None:
            deficit = err_deficit
        if deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            length_hint = (
                f"【字数·句内补】上一稿 {chars} 字，还差 {deficit} 字。"
                f"禁止增删句数、禁止整稿重写；只把中段 2–3 句各加几个字"
                f"（每句仍 ≤{DAILY_STORY_LINE_CHARS_MAX}），末四拍原样保留；"
                f"写到 ≥{chars_min} 即可，勿冲到上限猛扩。\n"
            )
        else:
            add_lines = max(1, (deficit + avg_line - 1) // avg_line)
            if deficit <= 48:
                add_lines = min(add_lines, 2)
            length_hint = (
                f"【字数·只增不删】上一稿 {chars} 字，还差至少 {deficit} 字。"
                f"在破功前插入约 {add_lines} 句互怼/加码（同一 conflict_core），"
                f"须轮流说话、每轮新证据；禁止镜像复读与同人连说；"
                f"写到 {aim_lo}–{aim_hi} 字；禁止整稿重写，禁止超过 {chars_max} 字。\n"
            )
    elif chars > chars_max:
        excess = chars - chars_max
        err_excess = _parse_body_char_excess(errors)
        if err_excess is not None:
            excess = err_excess
        if excess <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            length_hint = (
                f"【字数·句内删】上一稿 {chars} 字，超出 {excess} 字。"
                f"只从中段 1–2 句各删几个虚词/重复，禁止删整句关键回合；"
                f"末四拍尽量保留；压到 ≤{chars_max}。\n"
            )
        else:
            drop_lines = max(1, (excess + avg_line - 1) // avg_line)
            if excess <= 24:
                drop_lines = 1
            length_hint = (
                f"【字数·只删不增】上一稿 {chars} 字，超出 {excess} 字。"
                f"只删约 {drop_lines} 句车轱辘/重复回合，压到 {aim_lo}–{aim_hi} 字；"
                f"禁止新增任何台词，禁止大段重写，须仍 ≥{chars_min} 字。\n"
            )
    type_code = parse_story_type_code(
        story_type=story_type,
        punchline=str(prev_story.get("punchline_explain") or ""),
    )
    issue_hint = _retry_issue_hints(errors, chars=chars, type_code=type_code)
    prev_json = json.dumps(prev_story, ensure_ascii=False)
    return (
        f"主题：{theme}\n"
        f"【字数硬卡】正文 {chars_min}–{chars_max} 字；"
        f"每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；重试瞄准 {aim_lo}–{aim_hi}。\n"
        f"{length_hint}"
        f"{issue_hint}"
        f"【本轮问题】{errors}\n"
        "【修订要求】只改上述问题；保留 conflict_core 与收束；"
        "差几个字就句内补，勿整稿重开；勿写发现开场；勿换主题/另开账。\n"
        "请输出修订后的完整 JSON。\n"
        f"【上一稿】\n{prev_json}"
    )


def build_daily_story_opening_retry_user(
    theme: str,
    body: dict,
    *,
    errors: str,
    avoid_speaker: str | None = None,
) -> str:
    """开场重试：点名须出现的 conflict_core 锚点词；可选避开正文首句说话人。"""
    base = build_daily_story_opening_prompts(theme, body)[1]
    core = str(body.get("conflict_core") or "").strip()
    must = _conflict_anchor_must_words(core)
    must_txt = "、".join(must) if must else core or "冲突实物/动作"
    avoid = (avoid_speaker or "").strip()
    other = "灿灿" if avoid == "昭昭" else ("昭昭" if avoid == "灿灿" else "")
    speaker_hint = ""
    if other:
        speaker_hint = (
            f"开场末句说话人必须是「{other}」"
            f"（正文以「{avoid}」起句，避免拼后连说）；"
            f"若只写 1 句也须是「{other}」。\n"
        )
    return (
        f"{base}\n\n"
        f"【重试】上一轮开场未通过：{errors}\n"
        f"{speaker_hint}"
        f"开场台词必须点名以下至少一词：{must_txt}；"
        "两句时须换人；写正文开始前的定格现场，勿接正文前两句顶嘴。\n"
        "请只输出合法 JSON："
        '{"opening":[{"speaker":"昭昭","line":"..."}]}；'
        "禁止写成 {\"speaker\":\"昭昭\":\"台词\"}。"
    )


def build_daily_story_quality_retry_user(
    theme: str,
    prev_story: dict,
    revision_hints: str,
) -> str:
    """构造质量定向修订 user prompt。

    不是重写，是在现有骨架基础上修补指定弱点。
    """
    import json
    return (
        f"主题：{theme}\n\n"
        f"以下是已生成的剧本草稿，整体结构可用，但有几个维度需要针对性修补。\n"
        f"【核心原则】保留原有对话骨架（角色、冲突主线、台词风格），"
        f"只修补下面列出的短板。禁止推翻重写、禁止另起冲突、禁止改变角色立场。\n\n"
        f"【待修补维度】\n{revision_hints}\n\n"
        f"【字数硬卡】正文 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字，"
        f"每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字。修补后不能超上限，删改的字数在别处补回。\n"
        f"speaker 仅昭昭/灿灿，轮流说话，禁同人连说。\n"
        f"setting / conflict_core 如已正确则保留不动。\n\n"
        f"【上一稿】\n{json.dumps(prev_story, ensure_ascii=False)}\n\n"
        "请输出修订后的完整 JSON。"
    )
