"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

import copy
import json
import random
import re

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
DAILY_STORY_BODY_WRITE_TARGET_MIN = 390
DAILY_STORY_BODY_WRITE_TARGET_MAX = 450
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
    "改不了", "从来不", "已经.*了", "你说的", "装让",
    "反悔", "变卦", "自己说", "自己打",
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

_STORY_TYPE_LABELS = {
    "A": "权威翻车",
    "C": "公平执念",
    "D": "字面执行",
    "B": "结盟翻车",
    "E": "妈妈破功",
}

_STORY_TYPE_KEYWORDS = {
    "A": {"管", "不许", "应该", "必须", "听我的", "姐姐", "我是", "你小", "大人", "谁怕"},
    "C": {"争", "抢", "分", "谁先", "最后一", "平分", "归谁", "哪个", "大战", "之战", "我的", "你的"},
    "D": {"弄", "撒", "碎", "掉了", "帮忙", "收拾", "照做", "叮嘱", "按", "照"},
    "B": {"一起", "偷偷", "瞒", "藏", "约定", "联手", "别告诉", "俩", "暗号"},
    "E": {"妈妈", "问妈", "告状", "跟妈", "叫妈妈"},
}

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
  写作先按约 {DAILY_STORY_BODY_WRITE_TARGET_MIN}–{DAILY_STORY_BODY_WRITE_TARGET_MAX} 字铺回合，
  再压回硬卡；宁先写够再删，禁止首稿过短。
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
   写作先按约 {DAILY_STORY_BODY_WRITE_TARGET_MIN}–{DAILY_STORY_BODY_WRITE_TARGET_MAX} 字铺回合再压回硬卡
   （宁先写够再删；发现开场另计另验）。
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
}

_LENGTH_MODE_USER = {
    "draft": _DAILY_STORY_LENGTH_USER_DRAFT,
    "revise": _DAILY_STORY_LENGTH_USER_REVISE,
    "revise_expand": _DAILY_STORY_LENGTH_USER_REVISE_EXPAND,
    "revise_trim": _DAILY_STORY_LENGTH_USER_REVISE_TRIM,
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


_DAILY_STORY_SYSTEM_BODY = """\
【角色设定】
- 昭昭：弟弟，男孩，7岁。好奇心强，喜欢追问，擅长用现实经验挑战抽象规则，经常把简单的事越问越复杂。天真且固执。
- 灿灿：姐姐，女孩，10岁。比昭昭懂事一点，偶尔想模仿大人的语气管教弟弟，但自己的逻辑也经常掉进孩子的坑里。有时候会被昭昭带偏，嘴硬但心软。
- 妈妈：配角。可出场，但台词少；主戏仍是姐弟，妈妈不是戏核。
- 关系：亲姐弟，住在一起；主戏是姐弟斗嘴/较真/互相带偏，不是被妈妈教育。

【矛盾类型（默认优先 A/C/D；B/E 少用）—— 每条包含写作公式，不是空标签】
- A 权威翻车（优先）：
  公式：姐姐亮家长姿态「我是姐姐/大人说了」→弟弟用字面逻辑找漏洞→姐姐规则自相矛盾→姐姐破功。
  例：姐姐说「我是姐姐你得听我的」，弟弟「那上次妈妈说你也要听我，因为我是小孩需要照顾」。
- C 公平执念（优先）：
  公式：双方抢同一资源→各自抛对己有利的规则→规则互相冲突（如你先拿 vs 我先看 / 你切你选 vs 你拿你就选了）
  →一方规则被字面执行反噬或两套规则产生荒谬结论→收束。
  关键：每个人在"自己的规则下"都是对的，笑点来自两套公平标准无法兼容。
- D 字面执行（优先）：
  公式：有人给叮嘱/规则→另一方按字面严格执行→结果与初衷相反→原叮嘱方傻眼。
  例：妈妈说「别让弟弟碰剪刀」→姐姐把剪刀锁起来，弟弟要用剪刀开零食→两人都饿着。
- B 结盟翻车（少用）：
  公式：姐弟联手瞒妈妈/钻空子→计划在执行中露馅→互相甩锅→一起暴露。
- E 妈妈破功（少用）：
  公式：妈妈想讲道理/立规矩→被孩子用字面逻辑或连环追问绕进去→妈妈自己先破功。

【妈妈戏份（硬约束）】
- A/C/D 默认可不写妈妈；主戏与破功优先纯姐弟完成。
- 若出场：建议全程 ≤2 句；禁止长篇讲理、禁止妈妈当主线。
- 禁止明确判赢/判平/另开赛制（如「算你赢」「一人一半」「谁先放好谁先选」）。
- 日常口气可以（叮嘱、谁也别乱动、别吵了）：但不应用一句掐灭姐弟尚未落地的破功。
- 破功/软收优先在姐弟对白里完成；妈妈最多旁听、附和或事后收拾。
- 仅主题明确是 E 类（妈妈破功）时，才允许妈妈被孩子绕到自相矛盾。

【发现开场（系统另写，正文勿写）】
- 发现现场的质问/惊呼（如「鞋带怎么系一块了」）由系统单独生成并前置。
- 正文 dialogue 从互怼、讲理、甩规则开始，禁止再写寒暄或重复发现现场。
- setting 仍须写清地点 + 已发生的同一冲突动作，与 conflict_core 同一件实物/规则
  （反例：setting 写「各抓一个对峙」，core 却写「争同一个蓝抱枕」）。
- setting 中若提到妈妈做了某动作（如「妈妈切好蛋糕」），正文里妈妈必须至少出场 1 句台词
  呼应这个动作；否则把该动作改由姐弟中的一人执行（如「灿灿切好蛋糕」）。

【单冲突（硬约束）】
- 全文只滚一条规则加码（如始终争「先拿 vs 先看」），禁止中途换裁决方式。
- 反例：先争归属 → 改剪刀石头布 → 再扯道歉 → 再让妈妈轮流——这是另开账。
- 「上次你也…」只可当同一规则的证据，禁止借机开新仇（砸人、红抱枕、别的玩具）。
- 必须输出 conflict_core：一句话写清「谁 vs 谁，争什么」（≤24 字），
  与 theme / setting / 前 2 句一致。
- 禁止岔开学校/体育课/告爸爸/老师/公园等与 conflict_core 无关的新主线。
- 妈妈只点破，禁止由妈妈引入新冲突、新赛制或新事件。
- punchline_explain 须说明末句如何收的就是这个 conflict_core（不是另起「明天再战」）。

【节奏（硬约束）】
- 冲突升级路线（沿路线一步步推进，禁止同层来回绕、禁止跳级又回退）：
  1争归属(谁先碰/谁的)→2挑战规则(你的规则不算)→3挑战权威(凭什么你定)→4推出新证据→5收束
  每一层最多 2 个来回；超过 2 个来回即为空转，须立刻推进到下一层。
  禁止在前3层逗留超过全文一半；后半程须进入第4、5层。
- 每 6–8 句须有一个小反转或加码（同一规则升级、证据翻车、字面钻空子），禁止平铺到结尾才抖包袱。
- 台词要具体：点名「上次你也…」「妈说过…」「这是我的…」，少讲抽象公平大道理。
- 一句说完一层意思；禁止为凑 ≤18 字把同一半截话硬拆成两句（听感断裂）。
- 昭昭/灿灿必须轮流说：禁止同一人连说 ≥2 句（听感碎、像注水）。
- 禁止概念绕圈：同一逻辑结论（如「刀碰到蛋糕=碰了蛋糕」）的不同措辞变体也算同一对立面，
  最多 2 个来回后必须引入新事实（实物证据、目击证人、过去先例），
  禁止空转语义辩论连续超过 4 句。

【立场连贯（硬约束）】
- 同一角色前后立场须连贯：可以软收、可以认栽，但禁止无铺垫的态度骤变。
- 反例：刚喊「不公平/不行」下一句立刻「好吧/算了/给你」认怂——中间缺转折理由。
- 若要改口，须有新理由（被字面戳穿、被证据打脸），不能为收束硬拧。
- 同一人若因格式错误连说，后一句也须接前一句，禁止自打嘴巴。

【绝对禁止】
1. 禁止成人笑话、谐音梗、俏皮话、网络热梗。
2. 禁止「因为……所以……」等书面连接词，全部用口语短句。
3. 禁止叙事小说腔（「他心想」「她无奈地」等），只写纯对话+极简 setting。
4. 禁止为凑长度反复换说法车轱辘，或镜像对白（「你先看到有什么用」「你先拿到有什么用」）。
5. 禁止后半段换冲突、换地点主场、新开一件事或换一套分法/赛制。
6. 禁止角色无铺垫的自相矛盾（立场/证据前后打架）。
7. 禁止用「明天再战/今晚占位」当唯一收束，却没先破本场规则。
8. 禁止无破功软收：末句「给你/算了/好吧/好了好了」前，
   须已有一句把对方规则戳穿或自相矛盾；禁止吵不动就罢休。
9. 禁止弱收束（末 2 句内出现即违规）：
   - 和解分赃：「一人一半」「平分」「倒杯子」——把冲突和稀泥；
   - 耍赖占有：「反正我要用」「反正是我的」——没戳穿只赖账；
   - 甩给妈妈：「等妈回来」「叫妈评理」——本场须姐弟内收束。
10. 禁止赢家说最后一句：末句 speaker 必须是破功/被反杀/嘴硬的一方。
    笑点永远来自输家的反应，不是赢家的总结陈词。
    反例：昭昭抢到蛋糕说"瞧就瞧，蛋糕归我"→ 赢家收束无笑点。
    正例：昭昭戳穿后，灿灿「……随便你」或灿灿一言不发转身走开。
11. setting 一致性：若 setting 中妈妈完成某动作（如切蛋糕/拿东西），
    她必须在正文至少出场 1 句台词呼应；否则把该动作改由姐弟中的一人执行。

【笑点与收束】
- 笑点 = 孩子的字面/现实逻辑 碰撞 姐姐的「装大人」规则，或两人各执一词越辩越歪。
- 每一句推论须基于刚听到的字面意思或亲眼见过的生活经验，不能跳级。
- 【收束必须用回旋镖或字面戳穿（二选一，不用其他）】：
  回旋镖模式（优先）：倒数第3句用对方刚说的规则反问ta→倒数第2句对方发现自己自相矛盾试图狡辩→末句ta嘴硬收场（"……哼/……行/……随便你"），ta说最后一句。
    正例：昭昭「你自己说切的人先选，那你切的你选，我拿大的就行」→灿灿「我没说切的人先选大的」→灿灿「……哼，给你」。
  字面戳穿模式：倒数第2句点出对方一句话里自相矛盾→末句对方破功哑口或嘴硬。
    正例：昭昭「你说晚了，我已经在了」→灿灿「……」。
  关键约束：末句说话人必须是破功/被反杀/嘴硬的那一方，禁止让赢家说最后一句。

【格式要求】
严格输出以下JSON结构：
{
  "scene_title": "不超过10字，场记或口语钩子均可（如：谁先洗）",
  "setting": "一句话说明地点和初始冲突动作（如：客厅，姐弟抢遥控器）",
  "conflict_core": "≤24字，谁vs谁争什么（如：姐弟抢新橡皮）",
  "dialogue": [
    {"speaker": "昭昭", "line": "台词（≤18字）"},
    {"speaker": "灿灿", "line": "台词"},
    {"speaker": "妈妈", "line": "台词（宜少）"}
  ],
  "punchline_explain": "类型标签+收束逻辑（例：C类公平执念，姐姐规则被字面戳穿）"
}
妈妈可有台词，但宜少（建议≤3句）；主回合仍是姐弟。
"""


def _daily_story_system_prompt(*, length_mode: str = "draft") -> str:
    return (
        "你是一位家庭情景喜剧编剧，写昭昭&灿灿的日常对话短剧。\n"
        "面向孩子和有娃的大人：笑点要孩子听得懂，家长看得出自家日常。\n\n"
        f"{_daily_story_contract(length_mode=length_mode)}"
        f"{_DAILY_STORY_SYSTEM_BODY}"
    )


def _daily_story_user_template(*, length_mode: str = "draft") -> str:
    length_req = _LENGTH_MODE_USER.get(length_mode, _DAILY_STORY_LENGTH_USER_DRAFT)
    return f"""\
请根据上述规则，生成一个昭昭和灿灿的日常对话场景。

【本次场景主题（核心事件）】：{{theme}}

【要求】：
1. 主题即冲突实物：setting、conflict_core、正文首句须锚定主题中的实物/动作。
   「分蛋糕大小不均」→ setting 须有大小两块蛋糕（非争刀/争谁切），core 写谁vs谁争大的，正文首句直接争大的归谁。
2. {{type_instruction}}
{length_req}\
4. 正文从互怼/讲理起笔，禁止发现现场开场（发现句系统另写）。
5. 妈妈默认可不写；若出场宜少（建议≤2句）；禁止「算你赢/一人一半」类判赢判平。
6. 输出 conflict_core（≤24 字）；punchline_explain 须含类型标签并说明如何收该冲突。
7. 禁止中途换分法（剪刀石头布、轮流、另算谁先碰到等）或扯无关旧账。
8. 立场须连贯：可软收，但须先破功再软收；禁无铺垫「给你/算了」；
   禁同人连说、禁对称复读注水；末句勿只甩「明天再战」。
9. 【收束模板·必遵守】末尾4句套用这个结构（把[主题词]替换成当前争论的实物）：
   倒数第4句：用对方刚说的规则反问他（例："你自己说切的人先选，那你切你选，我拿大的"）
   倒数第3句：对方试图狡辩但露馅（例："我没说切的人先选大的……"）
   倒数第2句：指出他的矛盾（例："那你说'切的人先选'是什么意思？"）
   末句：对方嘴硬收场，说"……哼"或"……行"或"……随便"（必须他说最后一句）
   禁止赢家说最后一句、禁止双方互讲道理后忽然让步。

请直接输出JSON。
"""


# 兼容旧引用：默认 = 首稿（含写作铺垫）
_DAILY_STORY_CONTRACT = _daily_story_contract(length_mode="draft")
DAILY_STORY_SYSTEM_PROMPT = _daily_story_system_prompt(length_mode="draft")
DAILY_STORY_USER_TEMPLATE = _daily_story_user_template(length_mode="draft")

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
3. 主题要有天然矛盾，且主戏能在家门口/室内由姐弟撑起来，例如：
   姐姐管不住弟弟；抢先后/分东西吵公平；把叮嘱按字面做砸。
4. 少出「妈妈讲理/教育」当主线的主题。
5. 禁止依赖爸爸入戏、老师入戏、学校/公园等外景主场的主题。
6. 主题须能用短句口语一场讲完（对白体量约一分半到两分钟）。
7. 主题用15个字以内描述，直接输出。

示例："争最后一瓶酸奶"
示例："谁先洗澡"

请直接输出标题，每行一个，不要其他内容。
"""


def _select_story_type(theme: str) -> str:
    """评估主题与各矛盾类型的贴切度，从最高分中随机选一个。"""
    scores = {
        k: sum(1 for kw in v if kw in theme)
        for k, v in _STORY_TYPE_KEYWORDS.items()
    }
    max_score = max(scores.values())
    if max_score <= 0:
        candidates = ["A", "C", "D"]
    else:
        candidates = [k for k, v in scores.items() if v >= max_score]
    selected = random.choice(candidates)
    return f"{selected}类{_STORY_TYPE_LABELS[selected]}"


def _extract_type_from_punchline(punchline: str) -> str | None:
    """从 punchline_explain 中提取矛盾类型标签。"""
    for k, v in _STORY_TYPE_LABELS.items():
        if f"{k}类{v}" in punchline or f"{k}类" in punchline or f"{k}：" in punchline:
            return f"{k}类{v}"
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
      - revise_expand：偏短重试，只增不删，瞄准中段
      - revise_trim：偏长重试，只删不增，瞄准中段
      - revise：非字数问题重试，勿故意改篇幅
    """
    type_instruction = (
        f"本次矛盾类型必须用：{story_type}。禁止用其他类型。"
        if story_type
        else "矛盾优先 A/C/D（姐弟互怼）；B/E 仅主题明确需要时才用。"
    )
    user_tpl = _daily_story_user_template(length_mode=length_mode)
    return (
        _daily_story_system_prompt(length_mode=length_mode),
        user_tpl.format(theme=theme, type_instruction=type_instruction),
    )


DAILY_STORY_OPENING_SYSTEM_PROMPT = f"""\
你为昭昭&灿灿日常短剧写「发现现场」开场：观众一听就知道在争什么。
只写 1–2 句发现/质问，不写正文互怼。

【角色】昭昭7岁弟弟、灿灿10岁姐姐；开场 speaker 仅二人，勿写妈妈。
【场景】家庭内部/门口；口语短句，每句≤{DAILY_STORY_LINE_CHARS_MAX}字；禁成人梗/网络热梗。

【开场要干什么】
把「已经发生的冲突现场」喊出来：看见实物异常、抓住正在做的动作、或质问怎么回事。
像片头定场，不是寒暄，也不是开始讲理。

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

【正文已写好的前两句】（开场勿重复、勿接下去讲理）：
{body_head}

要求：点名冲突物或正在发生的动作，让观众立刻知道在争什么；
不要寒暄，不要甩规则，不要妈妈。直接输出 JSON。
"""


def build_daily_story_opening_prompts(
    theme: str,
    story: dict,
) -> tuple[str, str]:
    """构造发现开场单抽的 system + user。"""
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
    return DAILY_STORY_OPENING_SYSTEM_PROMPT, user


DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是儿童情景对话短剧的分镜编剧，只负责把对白切成可执行镜头，不写画面描述。

【可发言角色】昭昭（7岁弟弟）、灿灿（10岁姐姐）、妈妈。场景以家庭内部/门口为主。

【分镜规则】
1. 【切分原则】按单镜 2–3 句、≤{max_sec} 秒切分（对白共 {total_chars} 字 / {line_count} 句）；
   禁止一句一镜。
2. 【默认并镜】按同一地点、同一轮互怼/同一话题合并；每镜通常 2–3 句对白，
   单镜不得超过 3 句。
3. 【单镜字数】建议 {min_chars}–{max_chars} 字（约 {min_sec}–{max_sec} 秒，
   语速 {chars_per_sec} 字/秒）。少于 {min_chars} 字必须并入邻镜；
   单镜合计不得超过 {max_chars} 字（约 ≤{max_sec} 秒）。各镜尽量均匀。
4. 为每镜标注 shot_type（全景/中景/特写），在环境交代、对话主体、情绪或道具之间穿插。
5. 【开场首镜】scene_id=1 须定格冲突峰值姿势（抢/举/夺/藏/对峙），
   shot_type **必须「特写」**（发现开场也要落在动作峰值上，用特写留住开头吸引力）；
   禁止全景空镜、中景站桩或寒暄开场。
6. 【转折用特写，不拆碎】反驳、破功、愣住、妈妈插嘴、证据翻出等转折句：
   放在该镜开头（可带紧随的 1–2 句回应），shot_type 优先「特写」；
   禁止为转折把短句单独拆成不足 {min_chars} 字的镜；
   也禁止把转折句埋进四句长镜末尾。全文特写镜不超过总镜数约 1/3。

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
1. 每镜 2–3 句、不得超过 3 句；单镜 {min_chars}–{max_chars} 字（约 ≤{max_sec} 秒）；禁止一句一镜
2. 转折句用特写并放在镜首，但须并入邻句，不得单独拆成短镜
3. 原台词须全部分配到各镜 dialogue，措辞不得改

请直接输出 JSON。
"""

# 与 DailyScriptStage 时长告警对齐
DAILY_SCRIPT_MAX_SEGMENT_SEC = 10.0
# 单镜下限（约 2 句短对白）；过短须并入邻镜
DAILY_SCRIPT_MIN_SEGMENT_SEC = 4.0


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
    if anchors and not any(a in front_ctx for a in anchors):
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
    prev = "".join(lines[-3:-1])

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

    if not any(m in last for m in _LIMP_SOFT_CLOSE_MARKERS):
        return
    # 末句是软收：前 2 句须已有破功/戳穿痕迹
    if not any(m in prev for m in _PUNCH_BEFORE_SOFT_MARKERS):
        errors.append(
            "末句疑似无破功软收（如「给你/算了/好吧」）；"
            "软收前须先有字面戳穿或自相矛盾"
        )


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

    if errors:
        raise ValueError("daily_story 校验失败: " + "; ".join(errors))


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
    if anchors and normalized and not any(a in ctx for a in anchors):
        hint = "、".join(must) if must else "、".join(anchors[:4])
        errors.append(
            f"发现开场未体现 conflict_core 锚点（须点名其一：{hint}）：{core!r}"
        )

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


def build_daily_story_theme_prompts(count: int) -> tuple[str, str]:
    """构造日常故事主题生成的 system + user 提示词。"""
    return DAILY_STORY_THEME_SYSTEM_PROMPT, DAILY_STORY_THEME_USER_TEMPLATE.format(count=count)


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


def resolve_daily_story_retry_length_mode(
    prev_story: dict | None,
    *,
    errors: str = "",
) -> str:
    """按本轮错误 + 上一稿字数选择重试 length_mode。

    优先信校验文案（总字数须≥/≤）；字数已在区间时走 revise，
    避免「只修连说」被 trim/expand 带跑篇幅。
    """
    err = errors or ""
    if "总字数须≥" in err:
        return "revise_expand"
    if "总字数须≤" in err:
        return "revise_trim"
    chars = dialogue_total_chars(prev_story if isinstance(prev_story, dict) else None)
    if chars < DAILY_STORY_BODY_CHARS_MIN:
        return "revise_expand"
    if chars > DAILY_STORY_BODY_CHARS_MAX:
        return "revise_trim"
    return "revise"


def _retry_issue_hints(errors: str, *, chars: int) -> str:
    """按本轮校验问题追加可执行修订指令。"""
    hints: list[str] = []
    err = errors or ""
    if "连说" in err:
        hints.append(
            "【连说】全文改为昭昭/灿灿严格交替；把连说拆开或改 speaker，"
            f"勿借机大删；保持约 {chars} 字（{DAILY_STORY_BODY_CHARS_MIN}–"
            f"{DAILY_STORY_BODY_CHARS_MAX}）。"
        )
    if "无破功软收" in err or "弱收束" in err:
        hints.append(
            "【收束】只改末 2–3 句：倒数第 2 句字面戳穿/自相矛盾，"
            "末句破功哑口或嘴硬软收；"
            "禁止一人一半/平分、反正我要用、等妈评理。"
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
        add_lines = max(1, (deficit + avg_line - 1) // avg_line)
        if deficit <= 24:
            add_lines = 1
        elif deficit <= 48:
            add_lines = min(add_lines, 3)
        length_hint = (
            f"【字数·只增不删】上一稿 {chars} 字，还差至少 {deficit} 字。"
            f"在破功前插入约 {add_lines} 句互怼/加码（同一 conflict_core），"
            f"须轮流说话、每轮新证据；禁止镜像复读与同人连说；"
            f"写到 {aim_lo}–{aim_hi} 字；禁止整稿重写，禁止超过 {chars_max} 字。\n"
        )
    elif chars > chars_max:
        excess = chars - chars_max
        drop_lines = max(1, (excess + avg_line - 1) // avg_line)
        if excess <= 24:
            drop_lines = 1
        length_hint = (
            f"【字数·只删不增】上一稿 {chars} 字，超出 {excess} 字。"
            f"只删约 {drop_lines} 句车轱辘/重复回合，压到 {aim_lo}–{aim_hi} 字；"
            f"禁止新增任何台词，禁止大段重写，须仍 ≥{chars_min} 字。\n"
        )
    issue_hint = _retry_issue_hints(errors, chars=chars)
    prev_json = json.dumps(prev_story, ensure_ascii=False)
    return (
        f"主题：{theme}\n"
        f"【字数硬卡】正文 {chars_min}–{chars_max} 字；"
        f"每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；重试瞄准 {aim_lo}–{aim_hi}。\n"
        f"{length_hint}"
        f"{issue_hint}"
        f"【本轮问题】{errors}\n"
        "【修订要求】只改上述问题；保留 conflict_core 与收束；"
        "勿写发现开场；勿换主题/另开账。\n"
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
        "两句时须换人；写发现/质问现场，勿寒暄、勿开辩。\n"
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
