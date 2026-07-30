"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

import copy
import json
import re
from collections.abc import Sequence

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count as _dialogue_char_count,
    truncate_overlong_line as _truncate_overlong_line,
)
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES
from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    STORY_TYPE_LABELS,
    append_type_body_validation_errors,
    format_block_for_code,
    parse_story_type_code,
    patch_type_body,
    resolve_story_type_code,
    select_story_type_tag,
    story_line_for_code,
    story_type_tag,
    type_catalog_system_block,
    validate_type_opening,
)

# 角色外貌固定描述，供 visual_style 和分镜生成共享
# 昭昭与灿灿有参考图，妈妈无参考图独立定义
DAILY_STORY_CHARACTERS = (
    "昭昭：7岁男孩，男孩气黑色超短发"
    "（发长须在耳垂以上、清晰露出双耳及整个后颈，齐耳学生头/圆寸感；"
    "禁止女童波波头、齐肩短发、厚刘海遮额、马尾），"
    "圆脸，穿蓝色短袖T恤、深蓝色短裤、两侧同色蓝白运动鞋"
    "（禁止左右异色鞋），比灿灿矮约半个头；"
    "灿灿：10岁女孩，单侧高马尾（仅一根，禁止双马尾/麻花辫/披发），"
    "穿粉色卫衣、蓝色长裤、两侧同色粉红运动鞋，比昭昭高约半个头"
)

# 妈妈无参考图，外貌特征由 LLM 在 image_prompt 中文字描述，不混入有参考图角色常量
DAILY_STORY_CHARACTER_MOM = (
    "妈妈：成年女性，黑色长发，米色上衣、蓝色牛仔裤、深色平底鞋"
)

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
DAILY_STORY_BODY_WRITE_TARGET_MIN = 290
DAILY_STORY_BODY_WRITE_TARGET_MAX = 330
# DAILY_STORY_LINE_CHARS_MAX 见 dialogue_text.py（上方已导入）
DAILY_STORY_OPENING_LINES_MIN = 2
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
    *DAILY_STORY_SPEAKER_NAMES,
    "姐弟",
    "vs",
    "VS",
    "对",
)

# 重试瞄准硬卡中段，避免贴边再抖出界
DAILY_STORY_BODY_RETRY_TARGET_MIN = 290
DAILY_STORY_BODY_RETRY_TARGET_MAX = 330

# 首稿：硬卡 + 写作铺垫（偏长再压回）
# 重试：按偏短/偏长分向；勿混用「禁止扩写」与「略删」
_DAILY_STORY_LENGTH_DRAFT = f"""\
- 片长（正文硬卡，放最前）：{DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  【先按句数写】写 24–28 句对话（每句约 10–14 字），直接落在硬卡中段
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
   【按句数写更准】写 24–28 句（每句约 10–14 字），直接瞄准
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


def _body_line_budget(type_code: str | None) -> tuple[int, int, int]:
    """(min_lines, max_lines, avg_chars_per_line) for draft/retry hints."""
    if type_code:
        line = STORY_TYPE_LINES.get(type_code.upper())
        if line and line.body_lines_min > 0 and line.body_lines_max > 0:
            return line.body_lines_min, line.body_lines_max, 20
    return 24, 28, 12


def _daily_story_length_draft_for_type(type_code: str | None) -> str:
    lo, hi, _avg = _body_line_budget(type_code)
    if type_code and type_code.upper() == "E":
        return f"""\
- 片长（正文硬卡，放最前）：{DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  【E类·妈妈主戏】妈妈台词宜多（立论、否认、改口、越描越黑、破功），
  笑点须在自相矛盾打脸，禁空说教连问。
  发现开场系统另写另验，不计入正文硬卡。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
- 片长（D类正文，放最前）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  【D类·首稿】先钉「规矩词 + 歪读点 + 必然后果」，写清 13–14 句节奏；
  **接受字数偏短**（留给下一轮一次补满），勿为凑字堆轻轻放×N。
  系统另拼 2 句开场。发现开场另写另验。
"""
    return _DAILY_STORY_LENGTH_DRAFT


def _daily_story_length_user_draft_for_type(type_code: str | None) -> str:
    lo, hi, _avg = _body_line_budget(type_code)
    if type_code and type_code.upper() == "E":
        return f"""\
3. 【E类·字数硬卡】正文 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
   妈妈为主戏台词宜多；每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字为宜。发现开场另计另验。speaker 仅昭昭/灿灿/妈妈。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
3. 【D类·首稿】写 **{lo}–{hi} 句**，先钉歪读点再写对白；字数偏短可接受，
   重试一轮补到 ≥{DAILY_STORY_BODY_CHARS_MIN}。发现开场另计另验。speaker 仅昭昭/灿灿。
"""
    return _DAILY_STORY_LENGTH_USER_DRAFT


def _daily_story_length_revise_expand_for_type(type_code: str | None) -> str:
    if type_code and type_code.upper() == "E":
        return f"""\
- 片长（E类偏短重试）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  可增句或句内扩字到硬卡；加妈妈开脱/孩子追问细节，勿空说教。
  须轮流说话，禁止同人连说。发现开场另写另验。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
- 片长（D类偏短重试·一次补满）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  **本轮必须一次写到 ≥{DAILY_STORY_BODY_CHARS_MIN} 字**（瞄准 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX}）。
  保留上一稿不知变通骨架：句数补到 13–14（勿超过 14）；每句尽量 ≥20 字；
  只增不删、禁止整稿重写、禁止轻轻放×N 凑字。发现开场另写另验。
"""
    return _DAILY_STORY_LENGTH_REVISE_EXPAND


def _daily_story_length_revise_patch_for_type(type_code: str | None) -> str:
    if type_code and type_code.upper() == "E":
        return f"""\
- 片长（E类句内微调）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  **禁止增删句**；把偏短句各加 2–8 字（可拍细节/语气），写到 ≥265 即可；
  末段闭环+妈妈破功原样保留。发现开场另写另验。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
- 片长（D类句内微调）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  **禁止增删句**；偏短句各加 2–8 字，写到 ≥{DAILY_STORY_BODY_CHARS_MIN}；
  末段回旋镖+嘴硬收束原样保留。发现开场另写另验。
"""
    return _DAILY_STORY_LENGTH_REVISE_PATCH


def _daily_story_length_revise_trim_for_type(type_code: str | None) -> str:
    if type_code and type_code.upper() == "D":
        return f"""\
- 片长（D类偏长重试）：硬卡 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；
  每句台词硬性≤{DAILY_STORY_LINE_CHARS_MAX}字。
  只删不增：合并重复回合/空辩论，压到 **≤14 句**、
  约 {DAILY_STORY_BODY_RETRY_TARGET_MIN}–{DAILY_STORY_BODY_RETRY_TARGET_MAX} 字；
  保留立叮嘱→字面→搞砸→破规→回旋镖链。发现开场另写另验。
"""
    return _DAILY_STORY_LENGTH_REVISE_TRIM


def _daily_story_length_user_revise_expand_for_type(type_code: str | None) -> str:
    if type_code and type_code.upper() == "E":
        return f"""\
3. 【E类·句内补字】偏短可增句或句内扩字，写到 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX}；
   发现开场另计另验。speaker 仅昭昭/灿灿/妈妈。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
3. 【D类·一次补满】本轮必须写到 ≥{DAILY_STORY_BODY_CHARS_MIN} 字；
   句数 13–14；每句尽量 ≥20 字（≤{DAILY_STORY_LINE_CHARS_MAX}）；保留骨架只增不删。
   发现开场另计另验。speaker 仅昭昭/灿灿。
"""
    return _DAILY_STORY_LENGTH_USER_REVISE_EXPAND


def _daily_story_length_user_revise_patch_for_type(type_code: str | None) -> str:
    if type_code and type_code.upper() == "E":
        return f"""\
3. 【E类·句内微调】禁止增删句；偏短句各加几个字（可拍细节），写到≥265；
   闭环与妈妈末句破功勿动；发现开场另计另验。speaker 仅昭昭/灿灿/妈妈。
"""
    if type_code and type_code.upper() == "D":
        return f"""\
3. 【D类·句内微调】禁止增删句；偏短句各加 2–8 字，写到≥{DAILY_STORY_BODY_CHARS_MIN}；
   回旋镖收束勿动；发现开场另计另验。speaker 仅昭昭/灿灿/妈妈。
"""
    return _DAILY_STORY_LENGTH_USER_REVISE_PATCH


def _daily_story_contract(
    *,
    length_mode: str = "draft",
    type_code: str | None = None,
) -> str:
    if length_mode == "draft":
        length = _daily_story_length_draft_for_type(type_code)
    elif length_mode == "revise_expand":
        length = _daily_story_length_revise_expand_for_type(type_code)
    elif length_mode == "revise_patch":
        length = _daily_story_length_revise_patch_for_type(type_code)
    elif length_mode == "revise_trim":
        length = _daily_story_length_revise_trim_for_type(type_code)
    else:
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
- A/C/D 默认可不写妈妈；主戏与破功优先纯姐弟完成；**E 类妈妈为主戏**。
- 若出场：A/C/D 建议全程 ≤2 句；**E 类妈妈宜多句**（立论、否认、改口、破功）。
- 禁止明确判赢/判平/另开赛制（如「算你赢」「一人一半」「谁先放好谁先选」）。
- 日常口气可以（叮嘱、谁也别乱动、别吵了）：但不应用一句掐灭尚未落地的破功。
- 破功/软收：A/B/C/D 优先姐弟对白；**E 类末句妈妈破功收场**。

【发现开场（系统另写，正文勿写）】
- 开场=正片第一镜：系统另写 **2 句**，须有背景地点 + 可拍画面，再前置进片。
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
- 台词须用自然口语语序：称呼语可放句首、句尾或省略，一句只喊一次；不要句句都以「呀妈」「吗妈妈」结尾，避免听起来像念经。禁止把称呼、证据词或命令语（如「你听听」「听着」）叠在句子末尾造成倒装。反例：「你刚才还笑出声了呢妈妈你听听」应改为「你刚才还笑出声了呢妈妈」；「大人工作需要，跟你们玩不一样听着」应改为「大人工作需要，跟你们玩不一样」。
- 昭昭/灿灿必须轮流说：禁止同一人连说 ≥2 句（听感碎、像注水）。
- 禁止概念绕圈：同一逻辑结论的不同措辞变体也算同一对立面，
  最多 2 个来回后必须引入新事实，禁止空转语义辩论连续超过 4 句。

【台词风格（硬约束）】
1. 称呼语不要句句都喊：只在关键句点名（如首句、收束句），其他句省略称呼，避免每句都以「妈」「妈妈」「孩子们」收尾。
2. 少用「呀/呢/啊」等轻语气词：句子用句号、问号、感叹号收尾，不要每句都带语气词。
3. 证据链要有节奏：不要均匀堆叠证据，合并同类项（如声音+笑声可放在同一回合），让攻防有快有慢、有停顿有加码。
4. 妈妈情绪须有层次：从「解释/管教」→「心虚/语塞（可用「……」）」→「认输/投降」，体现明显转折。

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
    length_req = (
        _daily_story_length_user_draft_for_type(type_code)
        if length_mode == "draft" and type_code
        else _daily_story_length_user_revise_expand_for_type(type_code)
        if length_mode == "revise_expand" and type_code
        else _daily_story_length_user_revise_patch_for_type(type_code)
        if length_mode == "revise_patch" and type_code
        else _LENGTH_MODE_USER.get(length_mode, _DAILY_STORY_LENGTH_USER_DRAFT)
    )
    mom_role_note = (
        "5. E类妈妈为主戏，台词宜多、末句妈妈破功；禁空说教连问。"
        if type_code and type_code.upper() == "E"
        else (
            "5. 妈妈默认可不写；若出场宜少；"
            "禁止「算你赢/一人一半」类判赢判平（E 类除外）。"
        )
    )
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
{mom_role_note}
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
        f"{_daily_story_contract(length_mode=length_mode, type_code=type_code)}"
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

# 轮换正例池：按类型各抽 1 条；池要够散，避免题材族变窄
_THEME_EXAMPLE_POOL: dict[str, tuple[str, ...]] = {
    "A": (
        "姐姐嫌弟弟刷牙沫溅一圈",
        "教弟弟拉拉链一直拉反",
        "批评弟弟吃饭吧唧嘴",
        "不许碰平板自己却还亮着",
        "嫌弟弟书包拉链没拉自己也没拉",
        "骂弟弟拖鞋乱甩自己也甩飞",
        "教弟弟折纸飞机自己先折垮",
        "管弟弟别玩泥巴手上全是泥",
        "嫌弟弟画画出格自己笔也歪",
        "训弟弟别抠墙皮自己指甲有灰",
        "教弟弟包饺子皮捏得太厚",
        "不许哼歌唱自己却哼出声",
        "嫌弟弟洗脸只胡乱抹一把",
        "教弟弟摆碗筷自己摆反了",
    ),
    "B": (
        "俩人约定藏起打翻的颜料",
        "偷偷一起多看五分钟动画",
        "约好把碎掉的杯子先藏起来",
        "联手把弄湿的地毯翻面骗过去",
        "一起把吃剩的糖纸塞沙发缝",
        "悄悄把摔裂的碗藏进柜底",
        "合伙把洒的牛奶用布吸干",
        "联手把吃剩的果核塞花盆",
        "约好把弄脏的桌布先卷起来",
        "一起把碰倒的花瓶扶正装傻",
        "偷偷把撕坏的书页夹回中间",
        "俩人把踩脏的脚印用拖把糊",
        "约好把空了的饼干盒先盖上",
        "联手把掉漆的玩具翻面朝下",
    ),
    "C": (
        "争沙发上最后一块靠垫归谁",
        "谁先用新洗好的水杯",
        "分最后一块布丁谁切谁选",
        "抢坐窗边那把椅子",
        "争谁先挑新买的贴纸",
        "抢冰箱里最后一根冰棍",
        "争门口谁先穿鞋出门",
        "抢卫生间最后一张纸巾",
        "争床上谁睡靠窗那边",
        "分最后两颗糖谁先挑颜色",
        "争谁先用新买的彩色笔",
        "抢阳台谁先晾自己的袜子",
        "争客厅谁先选动画片频道",
        "分半个西瓜谁先挖中间红",
    ),
    "D": (
        "浇花别浇太多结果溢出来",
        "关门轻点结果门没关严",
        "收玩具放回箱里全塞沙发底",
        "擦桌子慢慢擦结果只擦一角",
        "晾衣服夹紧结果夹住袖口撕了",
        "倒垃圾别洒结果弄脏楼道",
        "关灯要关紧却留一条缝",
        "摆鞋对齐结果摆成一溜歪的",
        "擦桌子别弄湿结果整桌透湿",
        "收衣服叠整齐结果塞成一团",
        "扫地扫干净结果只扫门口一圈",
        "洗碗别碰倒结果水龙头开太大",
        "把书放回架上结果全插反了",
        "给盆栽松土结果挖出半盆土",
    ),
    "E": (
        "说好不玩手机被窝屏幕还亮着",
        "饭前不吃零食勺子还挂着菜",
        "九点必须睡妈妈还在刷短视频",
        "说好少喝饮料冰箱自己开罐",
        "不许踩沙发妈妈脚却搁扶手上",
        "规定剩饭要吃完自己碗底留米",
        "定好不躺地板自己先趴下玩",
        "立规矩关电视自己却偷偷看",
        "说好饭桌不玩手机屏幕朝上亮",
        "不许大声嚷自己却在厨房喊",
        "规定拖鞋摆门口自己踢进客厅",
        "说好早睡闹钟响了还在刷",
        "饭前洗手自己却直接抓饼",
        "不许边走边吃自己啃着苹果进门",
    ),
}

# 高频老题：每次出题写入禁复读，模型勿换词重出
_THEME_OVERUSED_BAN: tuple[str, ...] = (
    "争最后一瓶酸奶",
    "谁先洗澡",
    "姐姐教弟弟写作业自己写错",
    "把叠好的衣服弄乱",
    "抢遥控器",
    "抢电视遥控器",
    "偷偷一起吃零食",
    "系鞋带要系紧",
    "叠衣服要轻点",
)

_THEME_TYPE_ORDER: tuple[str, ...] = ("A", "B", "C", "D", "E")

DAILY_STORY_THEME_USER_TEMPLATE = """\
请给出适合昭昭（7岁弟弟）与灿灿（10岁姐姐）日常对话的场景主题。
面向孩子和有娃的大人。

家庭背景：姐弟和爸爸妈妈住在一起，家里没有宠物；
可发言角色仅昭昭、灿灿、妈妈；妈妈可出场但戏份轻（少台词）。

【硬要求】
1. 具体小事，带动作/实物；禁抽象讨论（友谊/公平概念题）。
2. 主戏在家门口/室内；禁爸/老师入戏、禁学校公园外景主场。
3. 每条≤15字；可拍优先；口头道德题（说谎/诚实/有礼貌）禁止。
4. E 类须「规矩+妈妈可拍现行」同题写出（手机亮/勺子挂菜等）。
5. **按类型配额输出**，共 {count} 条，配额：{quota_line}。
   配额按**主类型**计数；兼适类型不占配额。
6. **每行格式必须是** `主类型[,兼适…]|主题`（类型仅 A/B/C/D/E）。
   一条主题可兼适多个类型时用逗号列出，主类型写在最前，例如：
   E,A|九点必须睡妈妈还在刷短视频
   C|争沙发上最后一块靠垫归谁
7. 勿与「已出现/禁复读」列表近义改写（换词重说也算重复）。

【类型要点（各出各的，勿串类）】
A 姐姐管教被反问翻车 · B 姐弟联手瞒事露馅 · C 争同一物/先后吵公平
D 叮嘱被字面执行搞砸 · E 妈妈立规矩自己现行被抓

【本批轮换正例（结构可参考，勿照抄原句）】
{examples_block}

【禁复读 / 已出现（勿近义改写）】
{avoid_block}

请直接按 `主类型[,兼适…]|主题` 逐行输出，不要序号，不要其他内容。
"""


# 主题出题后过滤：口头道德/抽象题难写出合格稿，直接丢掉
_THEME_ABSTRACT_ORAL = re.compile(
    r"说谎|撒谎|敷衍|诚实|假话|骗奶奶|善意谎言|有礼貌|讲礼貌|"
    r"讨论|探讨|什么叫公平|什么是友谊",
)
_THEME_VISUAL_EYE = re.compile(
    r"手机|刷|勺子|尝|嘴角|油|睡|九点|瓜子|屏幕|亮着|试吃|"
    r"抢|争|藏|弄|碎|洒|倒|叠|鞋带|酸奶|零食|橡皮|抱枕|"
    r"作业|写错|刷牙|牙膏|平板|靠垫|水杯|布丁|贴纸|浇花|"
    r"关门|拖把|颜料|地毯|糖纸|扶手|短视频|饮料",
)
_RE_THEME_PUNCT = re.compile(r"[，。！？…、：；~—\s·「」“”\"'?!.,|｜]")


def allocate_theme_type_quotas(count: int) -> dict[str, int]:
    """把 count 尽量均分到 A–E。"""
    n = max(1, int(count))
    base, rem = divmod(n, len(_THEME_TYPE_ORDER))
    out = {c: base for c in _THEME_TYPE_ORDER}
    for i in range(rem):
        out[_THEME_TYPE_ORDER[i]] += 1
    return out


def _pick_rotating_examples(*, per_type: int = 1) -> list[str]:
    import random

    picked: list[str] = []
    for code in _THEME_TYPE_ORDER:
        pool = list(_THEME_EXAMPLE_POOL.get(code) or ())
        if not pool:
            continue
        k = min(per_type, len(pool))
        for ex in random.sample(pool, k=k):
            picked.append(f"{code}|{ex}")
    return picked


def _format_avoid_block(avoid: list[str], *, limit: int = 36) -> str:
    rows: list[str] = []
    seen: set[str] = set()
    for raw in [*_THEME_OVERUSED_BAN, *(avoid or [])]:
        t = str(raw or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        rows.append(t)
        if len(rows) >= limit:
            break
    if not rows:
        return "（无）"
    return "\n".join(f"- {t}" for t in rows)


def theme_is_writable(theme: str) -> bool:
    """粗判主题能否写成合格短剧：抽象口头题且无可拍眼 → 否。"""
    text = (theme or "").strip()
    if not text:
        return False
    if _THEME_ABSTRACT_ORAL.search(text) and not _THEME_VISUAL_EYE.search(text):
        return False
    return True


def _theme_norm(text: str) -> str:
    return _RE_THEME_PUNCT.sub("", text or "")


def _theme_bigrams(text: str) -> set[str]:
    n = _theme_norm(text)
    if len(n) < 2:
        return {n} if n else set()
    return {n[i : i + 2] for i in range(len(n) - 1)}


def themes_near_duplicate(a: str, b: str, *, threshold: float = 0.45) -> bool:
    """同批/对历史的近义：包含关系"""
    na, nb = _theme_norm(a), _theme_norm(b)
    if len(na) < 4 or len(nb) < 4:
        return na == nb and bool(na)
    if na == nb or na in nb or nb in na:
        return True
    ga, gb = _theme_bigrams(a), _theme_bigrams(b)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= threshold


def parse_typed_theme_lines(content: str) -> list[tuple[tuple[str, ...], str]]:
    """解析 `A|主题` / `E,A|主题` / `A：主题`。

    返回 [(codes, theme), ...]；codes[0] 为主类型（占配额）。
    """
    out: list[tuple[tuple[str, ...], str]] = []
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[.、)\s]*", "", line).strip()
        m = re.match(
            r"^[\[【]?\s*([ABCDE](?:\s*[,/、+]\s*[ABCDE])*)\s*[\]】]?"
            r"\s*[|｜:：\-–—]\s*(.+)$",
            line,
        )
        if not m:
            if theme_is_writable(line):
                out.append(((), line))
            continue
        codes_raw, theme = m.group(1), m.group(2).strip().strip("\"'")
        codes: list[str] = []
        for part in re.split(r"[,/、+\s]+", codes_raw):
            c = part.strip().upper()[:1]
            if c in _THEME_TYPE_ORDER and c not in codes:
                codes.append(c)
        if theme and codes:
            out.append((tuple(codes), theme))
        elif theme and theme_is_writable(theme):
            out.append(((), theme))
    return out


def merge_theme_story_types(
    theme: str,
    *,
    declared: Sequence[str] | None = None,
) -> list[str]:
    """合并模型标注 + 关键词提示，去重保序；至少返回一个类型。"""
    from app.services.daily_story.story_types.model import STORY_TYPE_KEYWORDS

    out: list[str] = []
    for raw in declared or ():
        c = str(raw or "").strip().upper()[:1]
        if c in _THEME_TYPE_ORDER and c not in out:
            out.append(c)
    scores = {
        k: sum(1 for kw in STORY_TYPE_KEYWORDS.get(k, ()) if kw in (theme or ""))
        for k in _THEME_TYPE_ORDER
    }
    for k, sc in sorted(
        scores.items(),
        key=lambda kv: (-kv[1], _THEME_TYPE_ORDER.index(kv[0])),
    ):
        if sc > 0 and k not in out:
            out.append(k)
    if not out:
        out = ["C"]
    return out


def filter_writable_themes(
    themes: list[str],
    *,
    avoid: list[str] | None = None,
) -> list[str]:
    """可写性 + 精确去重 + 对历史/同批近义去重。"""
    avoid_list = [str(x).strip() for x in (avoid or []) if str(x).strip()]
    out: list[str] = []
    for raw in themes:
        t = str(raw or "").strip()
        if not t or not theme_is_writable(t):
            continue
        if any(themes_near_duplicate(t, a) for a in avoid_list):
            continue
        if any(themes_near_duplicate(t, kept) for kept in out):
            continue
        out.append(t)
    return out


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
你为昭昭&灿灿日常短剧写「正片开端」开场：像片头第一镜，观众立刻入戏。
必须写 **2 句**（换人说），不写正文互怼中段。

【角色】昭昭7岁弟弟、灿灿10岁姐姐、妈妈；开场 speaker 仅此三人。
两句须换人；可以是姐弟互说，也可以是孩子与妈妈对说。
【场景】家庭内部/门口；口语短句，每句≤{DAILY_STORY_LINE_CHARS_MAX}字；禁成人梗/网络热梗。

【开场要干什么】
开场=正片开端，不是旁白寒暄，也不是正文已经吵起来的那一轮。
两句合起来必须同时有：
1. **背景**：地点或场记里能看见的环境（厨房/卧室门口/洗手台/餐桌旁…）
2. **画面**：冲突物 + 异常状态或正在发生的动作（可拍特写）
禁止单句干问、抽象「不公平」、或只点名无场面。

【双句分工】
- 第1句：定场——环境 + 物/动作异常（观众脑内出画面）
- 第2句：接住异常，点出马上要争什么（仍不展开辩论）
须换人说，勿同人连说。可借用【现场】setting 里的地点词。

【时间线（生成必守）】
成片顺序是：**开场2句 → 正文第 1 句 → 正文第 2 句 → …**
因此开场在剧情时间上**早于**下面 user 里的「正文前两句」。
- 正文第 1 句里才第一次说出口的指责/规矩，开场里**不能**用「还/也/你刚才」去接。
- 勿把正文前两句或更后面的反击、顶嘴、引用原话写进开场。
- 开场只写「看见/抓住」当下；互怼从正文第 1 句起。

【正例（须双句·有背景有画面）】
主题「把姐姐鞋带系一起」→
  昭昭：玄关地板上鞋带怎么绕一块了
  灿灿：谁把我鞋带系成死结了
主题「抢新橡皮」→
  昭昭：书桌上新橡皮怎么攥你手里
  灿灿：刚拆封的你怎么先拿走了
主题「谁先洗澡」→
  灿灿：浴室门口拖鞋我先摆好的
  昭昭：水龙头我先拧开的凭什么你先
主题「争最后一瓶酸奶」→
  昭昭：冰箱门开着最后一瓶酸奶
  灿灿：你怎么已经撕开吸管了
主题「九点必须睡觉」（可含妈妈）→
  昭昭：妈，卧室挂钟都指向九了
  妈妈：九点了必须睡觉，快去躺着

【反例（禁止）】
- 单薄一句：「鞋带怎么系一块了」（缺背景、缺第二镜）
- 寒暄铺垫：「姐你在干嘛」「今天好无聊」
- 直接开辩：「规则是谁先看见谁拿」「我是姐姐我说了算」
- 抽象空话：「这不公平」「你怎么这样」——没点出地点/实物/动作
- 把需要前文才成立的反击、双标对比、引用原话写在开场
- 妈妈已破功（行行行）、复述正文已有句子、续写互怼第二回合

【输出】只输出 JSON：
{{"opening":[{{"speaker":"昭昭","line":"…"}},{{"speaker":"灿灿","line":"…"}}]}}
opening 必须恰好 2 句、换人说；speaker 为昭昭/灿灿/妈妈；
须锚定本次 conflict_core 的实物或动作，并带地点/画面。
"""

DAILY_STORY_OPENING_USER_TEMPLATE = """\
请为下面这场戏写正片开端开场（必须 2 句，换人说）。

【主题】{theme}
【场记】{scene_title}
【现场】{setting}
【本场只争这一件】{conflict_core}

【正文前两句】（**开场之后才发生**，勿复述、勿接下去顶嘴、勿用「还」接这里的词）：
{body_head}

要求：开场=正片第一镜，须有**背景地点 + 可拍画面**；
从【现场】里借地点词；第1句定场，第2句点冲突；
speaker 为昭昭/灿灿/妈妈（可孩子对说，也可孩子与妈妈对说）；
正文第 1 句尚未发生，禁止开场预支其中的「磨蹭/不许/放下」等指责后再用「还说我…」；
不要寒暄，不要只写一句干问。直接输出 JSON。
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


# 特写镜（后续走 I2V）对白上限，图生视频口型轮次限制
DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES = 2
# 特写镜数量：约 1/4 下限、1/3 上限（关键帧 i2v 节奏）
_CLOSEUP_TURNING_RE = re.compile(
    r"妈脚步声|站好|干什么|完蛋|破功|愣住|证据|翻出|拆穿|露馅|"
    r"啊呀|哎呀|不对|才怪|才不是"
)

DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是儿童情景对话短剧的分镜编剧，只负责把对白切成可执行镜头，不写画面描述。

【可发言角色】昭昭（7岁弟弟）、灿灿（10岁姐姐）、妈妈。场景以家庭内部/门口为主。

【分镜规则】
1. 【切分原则】按单镜**倾向 2 句**、≤{max_sec} 秒切分（对白共 {total_chars} 字 / {line_count} 句）；
   禁止一句一镜。默认两人一轮对答并成一镜；不要为凑满而硬塞第 3 句。
2. 【默认并镜】按同一地点、同一轮互怼/同一话题合并；中景/全景**优先每镜 2 句**，
   仅当邻句过短、不足 {min_chars} 字时才并到 3 句；单镜不得超过 3 句。
3. 【特写对白上限·硬性】shot_type 为「特写」的镜，dialogue **不得超过 2 句**
   （图生视频口型限制，超 2 句会生成失败）。若该轮有 3 句：
   **优先**把第 3 句拆到下一镜——**禁止特写塞 3 句**；勿为省镜把 3 句塞进中景。
4. 【单镜字数】建议 {min_chars}–{max_chars} 字（约 {min_sec}–{max_sec} 秒，
   语速 {chars_per_sec} 字/秒）。少于 {min_chars} 字必须并入邻镜；
   单镜合计不得超过 {max_chars} 字（约 ≤{max_sec} 秒）。各镜尽量均匀。
5. 为每镜标注 shot_type（全景/中景/特写），在环境交代、对话主体、情绪或道具之间穿插。
6. 【开场首镜】scene_id=1 须定格冲突峰值姿势（抢/举/夺/藏/对峙），
   shot_type **必须「特写」**（发现开场也要落在动作峰值上，用特写留住开头吸引力）；
   禁止全景空镜、中景站桩或寒暄开场；首镜 dialogue **必须 ≤2 句**（多出的拆到 scene_id=2）。
7. 【转折用特写，不拆碎】反驳、破功、愣住、妈妈插嘴、证据翻出等转折句：
   放在该镜开头，shot_type 优先「特写」，且本镜最多再跟 **1 句**回应（特写合计 ≤2 句）；
   禁止为转折把短句单独拆成不足 {min_chars} 字的镜；
   若转折轮共 3 句：特写只留前 2 句，第 3 句进下一镜（可中景）。
8. 【特写数量·硬性】按你**实际切出的镜数 N** 计（勿按估算偷懒）：
   特写个数须落在 max(2, ⌈N/4⌉)–⌊N/3⌋，与程序校验一致。
   参考：8 镜→2–3，10 镜→3–4，12 镜→3–4（约估 {scene_count} 镜时约
   {closeup_min}–{closeup_max}）。开场首镜 + 至少 1 个中段转折 +
   妈妈破功/收场镜须特写；**禁止** N≥8 时全文只有 1–2 个特写。
   凑特写只改 shot_type 或拆/并镜，**禁止为凑特写删改、遗漏原台词**。

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
- 输出后自检：特写个数是否落在上述 N 对应区间；原台词句数是否全部进 dialogue。
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
1. 中景/全景**倾向每镜 2 句**（默认两人一轮），仅邻句过短才并到 3 句、不得超过 3 句；
   **特写镜硬性不得超过 2 句**（超了拆到下一镜，勿塞 3 句中景糊弄）
2. 单镜 {min_chars}–{max_chars} 字（约 ≤{max_sec} 秒）；禁止一句一镜
3. 转折句用特写并放在镜首，特写镜最多再跟 1 句回应；第 3 句须拆到下一镜
4. 【特写数量·硬性】按实际镜数 N：特写须在 max(2,⌈N/4⌉)–⌊N/3⌋
   （例 8→2–3、10→3–4；约估 {scene_count} 镜约 {closeup_min}–{closeup_max}）；
   首镜 + 中段转折 + 妈妈收场至少各 1 特写，禁止只标 1–2 个特写糊弄
5. 原台词须全部分配到各镜 dialogue，措辞不得改；调特写/拆并镜时不得丢句

请直接输出 JSON。
"""

# 与 DailyScriptStage 时长告警对齐
DAILY_SCRIPT_MAX_SEGMENT_SEC = 10.0
# 单镜下限（约 2 句短对白）；过短须并入邻镜
DAILY_SCRIPT_MIN_SEGMENT_SEC = 4.0


def daily_script_closeup_bounds(scene_count: int) -> tuple[int, int]:
    """特写镜数量上下限（约 1/4 下限、1/3 上限）。"""
    if scene_count <= 0:
        return (0, 0)
    min_cu = max(2, (scene_count + 3) // 4)
    max_cu = max(min_cu, (scene_count + 2) // 3)
    return (min_cu, max_cu)


def _scene_dialogue_line_count(scene: dict) -> int:
    dialogue = scene.get("dialogue") or []
    return sum(1 for d in dialogue if isinstance(d, dict))


def _scene_closeup_eligible(scene: dict) -> bool:
    return (
        _scene_dialogue_line_count(scene)
        <= DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES
    )


def _closeup_promotion_score(scene: dict, *, index: int, total: int) -> int:
    score = 0
    sid = int(scene.get("scene_id") or index)
    if sid == 1:
        score += 100
    if index == total:
        score += 80
    dialogue = scene.get("dialogue") or []
    if dialogue and isinstance(dialogue[0], dict):
        if dialogue[0].get("speaker") == "妈妈":
            score += 70
    text = "".join(
        str(d.get("text") or d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    )
    if _CLOSEUP_TURNING_RE.search(text):
        score += 50
    if "！" in text:
        score += 20
    if index > total * 2 // 3:
        score += 15
    return score


def enforce_daily_script_closeups(scenes: list) -> list[str]:
    """本地修正特写：超对白上限降中景，数量不足则按转折优先级升格。"""
    if not scenes:
        return []
    max_lines = DAILY_SCRIPT_KEYFRAME_MAX_DIALOGUE_LINES
    min_cu, _ = daily_script_closeup_bounds(len(scenes))
    notes: list[str] = []

    def is_closeup(scene: dict) -> bool:
        return str(scene.get("shot_type") or "").strip() == "特写"

    # 特写超口型上限 → 降中景（保留 3 句并镜，避免 i2v 失败）
    for scene in scenes:
        if not is_closeup(scene):
            continue
        n = _scene_dialogue_line_count(scene)
        if n <= max_lines:
            continue
        sid = scene.get("scene_id", "?")
        scene["shot_type"] = "中景"
        notes.append(
            f"scene_id={sid} demoted to 中景 ({n}>{max_lines} dialogue lines)"
        )

    closeup_count = sum(1 for s in scenes if is_closeup(s))

    if scenes and not is_closeup(scenes[0]) and _scene_closeup_eligible(scenes[0]):
        scenes[0]["shot_type"] = "特写"
        notes.append("scene_id=1 promoted to 特写 (opening)")
        closeup_count += 1

    if closeup_count >= min_cu:
        return notes

    candidates: list[tuple[int, int]] = []
    for i, scene in enumerate(scenes):
        if is_closeup(scene) or not _scene_closeup_eligible(scene):
            continue
        score = _closeup_promotion_score(scene, index=i + 1, total=len(scenes))
        if score > 0:
            candidates.append((score, i))
    candidates.sort(key=lambda x: (-x[0], x[1]))

    for _, idx in candidates:
        if closeup_count >= min_cu:
            break
        scenes[idx]["shot_type"] = "特写"
        sid = scenes[idx].get("scene_id", idx + 1)
        notes.append(f"scene_id={sid} promoted to 特写")
        closeup_count += 1
    return notes


def validate_daily_script_closeup_count(scenes: list) -> list[str]:
    """特写镜数量硬校验。"""
    if not scenes:
        return []
    min_cu, max_cu = daily_script_closeup_bounds(len(scenes))
    count = sum(
        1 for s in scenes if str(s.get("shot_type") or "").strip() == "特写"
    )
    errors: list[str] = []
    if count < min_cu:
        errors.append(
            f"特写镜仅 {count} 个，全文 {len(scenes)} 镜宜至少 {min_cu} 个（约 1/4）"
        )
    if count > max_cu:
        errors.append(
            f"特写镜 {count} 个超过上限 {max_cu}（约 1/3）"
        )
    return errors


def validate_daily_script_scenes(scenes: list) -> list[str]:
    """分镜硬校验：特写对白上限 + 特写数量区间。"""
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
    errors.extend(validate_daily_script_closeup_count(scenes))
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
    # 倾向每镜 2 句（与提示词一致）；仍夹在 6–14
    est_scenes = max(6, min(14, (line_count + 1) // 2))
    closeup_min, closeup_max = daily_script_closeup_bounds(est_scenes)
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
        scene_count=est_scenes,
        closeup_min=closeup_min,
        closeup_max=closeup_max,
    )
    system = DAILY_SCRIPT_SYSTEM_PROMPT.format(**fmt)
    user = DAILY_SCRIPT_USER_TEMPLATE.format(
        dialogue_text=dialogue_text,
        scene_title=scene_title,
        setting=setting,
        **fmt,
    )
    return system, user


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


def _is_self_apply_beat(story: dict, line: str) -> bool:
    """E 说谎题「孩子把妈妈逻辑套自己」那一句允许提老师，不算跑题。"""
    from app.services.daily_story.story_types.e.humor import (
        RE_KID_SELF_APPLY,
        RE_LIE_TOPIC,
    )

    topic = (
        str(story.get("conflict_core") or "")
        + str(story.get("_theme") or "")
        + str(story.get("scene_title") or "")
    )
    if not RE_LIE_TOPIC.search(topic):
        return False
    return bool(RE_KID_SELF_APPLY.search(line))


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
    latter = "".join(
        ln for ln in lines[-third:] if not _is_self_apply_beat(story, ln)
    )
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
    """校验妈妈台词：句数上限、禁止裁判式收场。

    E 类妈妈为主戏，不设句数上限；其它类型主戏在姐弟，≤3。
    """
    from app.services.daily_story.story_types import resolve_story_type_code

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return
    mom_items = [
        (i, item)
        for i, item in enumerate(dialogue)
        if isinstance(item, dict) and item.get("speaker") == "妈妈"
    ]
    type_code = resolve_story_type_code(story)
    if type_code != "E" and len(mom_items) > 3:
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
    # 妈妈的句数占比：总句数≤10 且妈妈≥3 句视为妈妈主导（E 除外）
    if type_code != "E" and len(dialogue) <= 10 and len(mom_items) >= 3:
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


# 句子末尾把称呼/命令语塞在陈述之后，造成倒装或叠词
_INVERTED_VOCATIVE_PATTERN = re.compile(
    r"[了呢啊么嘛]\s*(?:妈妈|妈)\s*(?:你听听|你看|你说|你讲|听着)|"
    r"[了呢啊么嘛]\s*(?:你听听|听着)",
    re.UNICODE,
)


def _append_natural_word_order_errors(story: dict, errors: list[str]) -> None:
    """检查台词是否存在倒装/叠称呼/叠命令语问题。"""
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if _INVERTED_VOCATIVE_PATTERN.search(line):
            errors.append(
                f"dialogue[{i}] 语序不自然，称呼/证据词/命令语叠在句尾："
                f"{line!r}；请改为正常口语语序"
            )


def validate_daily_story_json(
    story: dict,
    *,
    phase: str = "full",
) -> None:
    """校验日常故事 JSON。

    phase=body：验正文（含字数硬卡 280–370）。
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
    allowed_speakers = set(DAILY_STORY_SPEAKER_NAMES)
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
                    + "」「".join(DAILY_STORY_SPEAKER_NAMES)
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
            chars_min = DAILY_STORY_BODY_CHARS_MIN
            type_code = resolve_story_type_code(story)
            n_lines = len(dialogue) if isinstance(dialogue, list) else 0
            theme_ctx = (
                str(story.get("conflict_core") or "")
                + str(story.get("_theme") or "")
                + str(story.get("theme") or "")
                + str(story.get("scene_title") or "")
            )
            # 挑食宜短稿，勿与通用 ≥280/265 硬顶死
            if type_code == "E" and re.search(
                r"挑食|青菜|拨到碗边",
                theme_ctx,
            ):
                chars_min = 200
            elif type_code == "E" and n_lines >= 10:
                chars_min = 265
            if total_chars < chars_min:
                deficit = chars_min - total_chars
                errors.append(
                    f"正文总字数须≥{chars_min}，当前{total_chars}"
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

    # 语序自然：禁止句尾叠称呼/证据词造成倒装
    _append_natural_word_order_errors(story, errors)

    # 妈妈台词硬约束
    _append_mom_line_errors(story, errors)

    # 末句赢家检测（仅正文阶段，拼开场后不在 body phase 执行）
    if phase == "body":
        _append_winner_last_line_errors(story, errors)

    # setting 妈妈动作一致性
    _append_setting_mom_consistency_errors(story, errors)

    _append_verifiable_fact_errors(story, errors)
    append_type_body_validation_errors(story, errors)
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
    """校验发现开场 2 句，返回规范化列表；失败抛 ValueError。"""
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
    allowed = {"昭昭", "灿灿", "妈妈"}
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
            errors.append(
                f"opening[{i}] speaker 须为昭昭/灿灿/妈妈，收到：{speaker!r}"
            )
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

    validate_type_opening(
        normalized,
        type_code=type_code,
        errors=errors,
        conflict_core=core,
        setting=setting or "",
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


def sync_discovery_opening_from_dialogue(story: dict) -> None:
    """人工改 dialogue 后，把 discovery_opening 对齐为前 2 句。

    拼稿后 discovery_opening 即 dialogue 前缀；页面保存/同步须保持一致。
    """
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return
    opening: list[dict[str, str]] = []
    for item in dialogue[:DAILY_STORY_OPENING_LINES_MAX]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        speaker = str(item.get("speaker") or "").strip()
        if line and speaker:
            opening.append({"speaker": speaker, "line": line})
    if len(opening) >= DAILY_STORY_OPENING_LINES_MIN:
        story["discovery_opening"] = opening[:DAILY_STORY_OPENING_LINES_MAX]


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
    avoid: list[str] | None = None,
    quotas: dict[str, int] | None = None,
) -> tuple[str, str]:
    """构造日常故事主题生成的 system + user 提示词。

    - 默认按 A–E 配额出题（`主类型[,兼适…]|主题`）。
    - 若传入 type_code，改为单类型出题，并追加该类 theme_user_append。
    """
    n = max(1, int(count))
    if type_code and type_code.upper() in STORY_TYPE_LINES:
        code = type_code.upper()
        quota_map = {c: 0 for c in _THEME_TYPE_ORDER}
        quota_map[code] = n
        quota_line = f"{code}×{n}"
        examples = [
            f"{code}|{ex}"
            for ex in list(_THEME_EXAMPLE_POOL.get(code) or ())[:2]
        ]
        user = DAILY_STORY_THEME_USER_TEMPLATE.format(
            count=n,
            quota_line=quota_line,
            examples_block="\n".join(examples) or "（无）",
            avoid_block=_format_avoid_block(list(avoid or [])),
        )
        extra = STORY_TYPE_LINES[code].theme_user_append.strip()
        if extra:
            user = f"{user}\n{extra}"
        return DAILY_STORY_THEME_SYSTEM_PROMPT, user

    quota_map = quotas or allocate_theme_type_quotas(n)
    quota_line = "、".join(
        f"{c}×{quota_map.get(c, 0)}"
        for c in _THEME_TYPE_ORDER
        if quota_map.get(c, 0) > 0
    )
    examples = _pick_rotating_examples(per_type=1)
    user = DAILY_STORY_THEME_USER_TEMPLATE.format(
        count=n,
        quota_line=quota_line or "A–E 尽量均分",
        examples_block="\n".join(examples) or "（无）",
        avoid_block=_format_avoid_block(list(avoid or [])),
    )
    return DAILY_STORY_THEME_SYSTEM_PROMPT, user


def select_themes_by_quota(
    typed: list[tuple[tuple[str, ...], str]],
    quotas: dict[str, int],
    *,
    avoid: list[str] | None = None,
) -> list[dict]:
    """按主类型 A–E 配额挑选；返回 [{theme, story_types}, ...]。"""
    avoid_list = [str(x).strip() for x in (avoid or []) if str(x).strip()]
    # primary -> [(theme, story_types)]
    buckets: dict[str, list[tuple[str, list[str]]]] = {
        c: [] for c in _THEME_TYPE_ORDER
    }
    untyped: list[tuple[str, list[str]]] = []

    def _theme_texts(rows: list[dict]) -> list[str]:
        return [r["theme"] for r in rows]

    def _accept(theme: str, existing: list[str]) -> bool:
        if not theme or not theme_is_writable(theme):
            return False
        if any(themes_near_duplicate(theme, a) for a in avoid_list):
            return False
        if any(themes_near_duplicate(theme, x) for x in existing):
            return False
        return True

    def _primary_count(rows: list[dict], code: str) -> int:
        return sum(
            1
            for r in rows
            if (r.get("story_types") or [""])[0] == code
        )

    seen_bucket_themes: set[str] = set()
    for codes, theme in typed:
        t = theme.strip()
        types = merge_theme_story_types(t, declared=codes)
        primary = types[0]
        if t in seen_bucket_themes:
            continue
        if not _accept(t, list(seen_bucket_themes)):
            continue
        if codes:
            buckets[primary].append((t, types))
            seen_bucket_themes.add(t)
        else:
            untyped.append((t, types))
            seen_bucket_themes.add(t)

    picked: list[dict] = []
    for code in _THEME_TYPE_ORDER:
        need = int(quotas.get(code) or 0)
        for t, types in buckets[code]:
            if need <= 0:
                break
            if not _accept(t, _theme_texts(picked)):
                continue
            # 保证配额主类型在首位
            ordered = [code] + [c for c in types if c != code]
            picked.append({"theme": t, "story_types": ordered})
            need -= 1
        for t, types in untyped:
            if need <= 0:
                break
            if not _accept(t, _theme_texts(picked)):
                continue
            ordered = [code] + [c for c in types if c != code]
            picked.append({"theme": t, "story_types": ordered})
            need -= 1

    total_need = sum(int(quotas.get(c) or 0) for c in _THEME_TYPE_ORDER)
    if len(picked) < total_need:
        leftovers: list[tuple[str, str, list[str]]] = [
            (code, t, types)
            for code in _THEME_TYPE_ORDER
            for t, types in buckets[code]
        ] + [("", t, types) for t, types in untyped]
        for code, t, types in leftovers:
            if len(picked) >= total_need:
                break
            if not _accept(t, _theme_texts(picked)):
                continue
            st = code or next(
                (
                    c
                    for c in _THEME_TYPE_ORDER
                    if _primary_count(picked, c) < int(quotas.get(c) or 0)
                ),
                (types[0] if types else _THEME_TYPE_ORDER[0]),
            )
            ordered = [st] + [c for c in types if c != st]
            picked.append({"theme": t, "story_types": ordered})
    return picked[:total_need]


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


_LOCAL_PAD_TAILS = (
    "好不好",
    "你听着",
    "真的呀",
    "呢",
    "吧",
    "嘛",
    "啊",
    "呀",
)  # 优先多字少句，勿满篇单「呀」
# D 大缺口本地补：可拍短尾巴，一次重试后只差几十时垫满
_LOCAL_PAD_TAILS_D = (
    "，我按你说的认真做",
    "，一点都不含糊",
    "，照做就是了",
    "，我数着做",
    "呢",
    "吧",
)
# D 句内顶字：只用可拍长片段，禁「好不好」求同意、禁单字连叠
_LOCAL_FILL_CHUNKS_D = (
    "，我按你说的认真做",
    "，一点都不含糊",
    "，照做就是了",
    "，我数着做",
    "，绝不偷懒",
    "，一步不差",
    "，你看着",
    "，听你的",
    "，马上好",
    "，别催我",
)
# 句内残缺口：短片段顶满 room（禁「好不好」）
_LOCAL_FILL_SHORT_D = (
    "，你看",
    "呀",
    "呢",
    "啊",
)
# 灿灿催促垫字：禁第一人称照做
_LOCAL_FILL_CHUNKS_CAN_D = (
    "，别乱动",
    "，快点",
    "，小心点",
    "啊",
)
_LOCAL_TRIM_CHARS = "的了呢嘛呀啊吧啦哦喔哈嗯"



def _clone_story(story: dict) -> dict:
    return json.loads(json.dumps(story, ensure_ascii=False))


def _line_room(line: str) -> int:
    return max(0, DAILY_STORY_LINE_CHARS_MAX - _dialogue_char_count(line))


def _pad_dialogue_line(
    line: str,
    need: int,
    used: set[str] | None = None,
    *,
    tails: tuple[str, ...] | None = None,
) -> tuple[str, int]:
    """句尾最多补一个语气词/短尾巴，返回 (新句, 实际增加字数)。

    used 记录整篇已用过的垫字，避免多句复读同一个「好不好」。
    句末若是 。！？…，垫在标点前，避免「有标点就补不动」。
    """
    pad_tails = tails or _LOCAL_PAD_TAILS
    if need <= 0 or not line:
        return line, 0
    trail = ""
    core = line
    if core[-1] in "。！？…":
        trail = core[-1]
        core = core[:-1]
        if not core:
            return line, 0
    if core[-1] in "啦嘛呀啊呢吧哦":
        return line, 0
    # 已补过垫字的句子不再叠加（防「好不好呢」）
    if any(core.endswith(suf) for suf in (*_LOCAL_PAD_TAILS, *_LOCAL_PAD_TAILS_D)):
        return line, 0
    room = max(0, DAILY_STORY_LINE_CHARS_MAX - _dialogue_char_count(line))
    if room <= 0:
        return line, 0
    # 缺口大时优先长尾巴
    ordered = sorted(pad_tails, key=len, reverse=(need >= 8))
    for suf in ordered:
        if used is not None and suf in used:
            continue
        if len(suf) <= room and len(suf) <= need:
            if used is not None:
                used.add(suf)
            return f"{core}{suf}{trail}", len(suf)
    return line, 0


def _fill_d_dialogue_line(
    line: str,
    need: int,
    used: dict[str, int] | None = None,
    *,
    chunks: tuple[str, ...] | None = None,
) -> tuple[str, int]:
    """D：把单句顶到上限；剥句末标点/语气词再垫；长片段不够再用短片段。"""
    if need <= 0 or not line:
        return line, 0
    trail = ""
    core = line
    if core and core[-1] in "。！？…":
        trail = core[-1]
        core = core[:-1]
    if core and core[-1] in "啦嘛呀啊呢吧哦":
        trail = core[-1] + trail
        core = core[:-1]
    if not core:
        return line, 0
    added = 0
    appends = 0
    local_used: set[str] = set()
    pool = chunks or _LOCAL_FILL_CHUNKS_D
    start = _dialogue_char_count(core) % len(pool)
    ordered = pool[start:] + pool[:start]
    while need > 0 and appends < 2:
        room = max(
            0,
            DAILY_STORY_LINE_CHARS_MAX
            - _dialogue_char_count(core)
            - _dialogue_char_count(trail),
        )
        if room < 3:
            break
        picked = ""
        for suf in sorted(ordered, key=len, reverse=True):
            if suf in local_used:
                continue
            if used is not None and used.get(suf, 0) >= 3:
                continue
            if len(suf) > room or len(suf) > need:
                continue
            if core.endswith(suf) or suf.lstrip("，") in core:
                continue
            picked = suf
            break
        if not picked:
            break
        core = f"{core}{picked}"
        need -= len(picked)
        added += len(picked)
        appends += 1
        local_used.add(picked)
        if used is not None:
            used[picked] = used.get(picked, 0) + 1
    # 残缺口：短片段把 room 吃满（差 20+ 时常因长片段塞不进）
    while need > 0 and appends < 5:
        room = max(
            0,
            DAILY_STORY_LINE_CHARS_MAX
            - _dialogue_char_count(core)
            - _dialogue_char_count(trail),
        )
        if room <= 0:
            break
        picked = ""
        for suf in sorted(_LOCAL_FILL_SHORT_D, key=len, reverse=True):
            if suf in local_used:
                continue
            if len(suf) > room or len(suf) > need:
                continue
            if core.endswith(suf) or (
                len(suf) > 1 and suf.lstrip("，") in core
            ):
                continue
            picked = suf
            break
        if not picked:
            break
        core = f"{core}{picked}"
        need -= len(picked)
        added += len(picked)
        appends += 1
        local_used.add(picked)
    if not added:
        return line, 0
    return f"{core}{trail}", added


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


def _patch_d_ensure_min_lines(
    story: dict,
    *,
    target_lines: int = 13,
) -> list[str]:
    """D 句数不足时，在末四拍前插入轮流短句；昭昭演歪读，灿灿只催/慌。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    target = max(13, min(14, int(target_lines)))
    need_lines = target - len(dialogue)
    if need_lines <= 0:
        return notes
    insert_at = max(2, len(dialogue) - 4)
    prev_sp = str(dialogue[insert_at - 1].get("speaker") or "灿灿").strip()
    zhao_fillers = (
        "我按你说的，一步都不含糊",
        "再紧一点，我认真系死结",
        "我数着做，绕成花生米",
        "还是按你说的，再焊一圈",
    )
    can_fillers = (
        "你小心点，鞋带别扯断了",
        "快点系，别在这儿磨蹭",
        "你倒是系啊，别光使劲",
        "小心点，别把鞋弄坏了",
    )
    z_i = 0
    c_i = 0
    for i in range(need_lines):
        sp = "昭昭" if prev_sp == "灿灿" else "灿灿"
        if sp == "昭昭":
            line = zhao_fillers[z_i % len(zhao_fillers)]
            z_i += 1
        else:
            line = can_fillers[c_i % len(can_fillers)]
            c_i += 1
        if _dialogue_char_count(line) > DAILY_STORY_LINE_CHARS_MAX:
            line = _truncate_overlong_line(line)
        dialogue.insert(insert_at + i, {"speaker": sp, "line": line})
        prev_sp = sp
        notes.append(f"D补句[{insert_at + i}]")
    return notes


def _d_mid_zhao_targets(
    dialogue: list,
    *,
    include_cancan: bool = False,
) -> list[dict]:
    """D 补字只动中段：昭昭执行/后果；灿灿催促/破规可句内顶满。"""
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return []
    # 末两句收束不垫；末四里若有昭昭执行/后果句可垫（回旋镖除外）
    mid = dialogue[2:-2]
    boom_skip = re.compile(r"你自己说|你刚才说")
    soft_skip = re.compile(r"哼|算了|行吧")
    out = [
        item
        for item in mid
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() == "昭昭"
        and not boom_skip.search(str(item.get("line") or ""))
        and not soft_skip.search(str(item.get("line") or ""))
    ]
    # 灿灿：催促/破规都可垫（禁照做口吻）
    can_bad = re.compile(r"按你说的|照做|我数着|一步都不含糊")
    if include_cancan or len(out) < 3:
        for item in mid:
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != "灿灿":
                continue
            ln = str(item.get("line") or "")
            if can_bad.search(ln) or soft_skip.search(ln):
                continue
            if item not in out:
                out.append(item)
    return out


def _patch_body_char_budget(
    story: dict,
    *,
    allow_insert_lines: bool = True,
) -> list[str]:
    """仅小缺口本地补/删语气词；D 在重试后可把句内顶满以一次过硬卡。"""
    from app.services.daily_story.story_types import resolve_story_type_code

    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    total = dialogue_total_chars(story)
    code = resolve_story_type_code(story)
    locked = str(story.get("_story_type") or "").strip()
    if locked.upper().startswith("D") or "字面执行" in str(
        story.get("punchline_explain") or "",
    ):
        code = "D"
    n_lines = len(dialogue)
    chars_min = DAILY_STORY_BODY_CHARS_MIN
    max_pad = DAILY_STORY_RETRY_PATCH_DEFICIT_MAX
    theme_ctx = (
        str(story.get("conflict_core") or "")
        + str(story.get("_theme") or "")
        + str(story.get("theme") or "")
        + str(story.get("scene_title") or "")
    )
    if code == "E" and re.search(r"挑食|青菜|拨到碗边", theme_ctx):
        chars_min = 200
        max_pad = 48
    elif code == "E" and 10 <= n_lines <= 16:
        chars_min = 265
        max_pad = 72
    if code == "D" and allow_insert_lines:
        # 接受首稿偏短；重试后常差 80–150，本地把句顶满即可过硬卡
        max_pad = max(max_pad, 160)
        if n_lines < 13:
            notes.extend(_patch_d_ensure_min_lines(story, target_lines=13))
            dialogue = story.get("dialogue") or dialogue
            n_lines = len(dialogue) if isinstance(dialogue, list) else n_lines
            total = dialogue_total_chars(story)
        if total < chars_min and n_lines < 14:
            notes.extend(_patch_d_ensure_min_lines(story, target_lines=14))
            dialogue = story.get("dialogue") or dialogue
            n_lines = len(dialogue) if isinstance(dialogue, list) else n_lines
            total = dialogue_total_chars(story)
    elif code == "D":
        max_pad = max(max_pad, 160)
    mid = dialogue[:-4] if len(dialogue) >= 8 else dialogue[1:]
    if total < chars_min:
        need = chars_min - total
        if need > max_pad and code != "D":
            return notes
        before = total
        if code == "D":
            # 只垫昭昭中段，禁止垫灿灿/末四拍；缺口大时顺带垫催促灿灿
            need0 = need
            targets = _d_mid_zhao_targets(
                dialogue, include_cancan=(need0 > 8),
            )
            used_fills: dict[str, int] = {}
            for _ in range(3):
                if need <= 0:
                    break
                progressed = False
                for item in targets:
                    if need <= 0:
                        break
                    line = str(item.get("line") or "")
                    if not line:
                        continue
                    sp = str(item.get("speaker") or "").strip()
                    pool = (
                        _LOCAL_FILL_CHUNKS_CAN_D
                        if sp == "灿灿"
                        else _LOCAL_FILL_CHUNKS_D
                    )
                    new_line, added = _fill_d_dialogue_line(
                        line, need, used_fills, chunks=pool,
                    )
                    if added:
                        item["line"] = new_line
                        need -= added
                        progressed = True
                if not progressed:
                    break
            # 还差几个字：放开复用，仍只动安全目标句
            need = chars_min - dialogue_total_chars(story)
            if 0 < need <= 80:
                targets = _d_mid_zhao_targets(
                    dialogue, include_cancan=True,
                )
                for item in reversed(targets):
                    if need <= 0:
                        break
                    line = str(item.get("line") or "")
                    if not line:
                        continue
                    sp = str(item.get("speaker") or "").strip()
                    pool = (
                        _LOCAL_FILL_CHUNKS_CAN_D
                        if sp == "灿灿"
                        else _LOCAL_FILL_CHUNKS_D
                    )
                    new_line, added = _fill_d_dialogue_line(
                        line, need, None, chunks=pool,
                    )
                    if added:
                        item["line"] = new_line
                        need -= added
            # 仍差：目标句标点前补短尾巴
            need = chars_min - dialogue_total_chars(story)
            if 0 < need <= 48:
                targets = _d_mid_zhao_targets(
                    dialogue, include_cancan=True,
                )
                for item in reversed(targets):
                    if need <= 0:
                        break
                    line = str(item.get("line") or "")
                    room = _line_room(line)
                    if not line or room <= 0:
                        continue
                    trail = ""
                    core = line
                    if core[-1] in "。！？…":
                        trail = core[-1]
                        core = core[:-1]
                    if core and core[-1] in "啦嘛呀啊呢吧哦":
                        trail = core[-1] + trail
                        core = core[:-1]
                    if not core:
                        continue
                    sp = str(item.get("speaker") or "").strip()
                    take = min(need, room, 4)
                    if take <= 0:
                        continue
                    if sp == "灿灿":
                        pad = ("小心" * 2)[:take]
                    else:
                        pad = ("好呀" * 2)[:take] if take >= 2 else "呀"
                    item["line"] = f"{core}{pad}{trail}"
                    need -= len(pad)
            # 中段已顶满仍差：垫前两句（立规/接令），禁「好不好」
            need = chars_min - dialogue_total_chars(story)
            if need > 0 and len(dialogue) >= 2:
                head_targets = [
                    item
                    for item in dialogue[:2]
                    if isinstance(item, dict) and _line_room(str(item.get("line") or "")) > 0
                ]
                used_head: dict[str, int] = {}
                for item in head_targets:
                    if need <= 0:
                        break
                    line = str(item.get("line") or "")
                    sp = str(item.get("speaker") or "").strip()
                    pool = (
                        _LOCAL_FILL_CHUNKS_CAN_D
                        if sp == "灿灿"
                        else _LOCAL_FILL_CHUNKS_D
                    )
                    new_line, added = _fill_d_dialogue_line(
                        line, need, used_head, chunks=pool,
                    )
                    if added:
                        item["line"] = new_line
                        need -= added
        else:
            used_pads = {
                suf
                for suf in _LOCAL_PAD_TAILS
                for item in dialogue
                if isinstance(item, dict)
                and str(item.get("line") or "").endswith(suf)
            }
            for item in mid:
                if need <= 0:
                    break
                if not isinstance(item, dict):
                    continue
                line = str(item.get("line") or "")
                if not line:
                    continue
                new_line, added = _pad_dialogue_line(line, need, used_pads)
                if added:
                    item["line"] = new_line
                    need -= added
        after = dialogue_total_chars(story)
        if after > before:
            notes.append(f"本地补字{before}→{after}")
    elif total > DAILY_STORY_BODY_CHARS_MAX:
        excess = total - DAILY_STORY_BODY_CHARS_MAX
        trim_max = DAILY_STORY_RETRY_PATCH_DEFICIT_MAX
        if code == "E" and 10 <= n_lines <= 16:
            trim_max = 48
        if excess > trim_max:
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


def _patch_consecutive_speakers(story: dict) -> list[str]:
    """同人连说：把后一句 speaker 改成另一方（仅修硬卡，少动文案）。"""
    from app.services.daily_story.story_types import resolve_story_type_code

    code = resolve_story_type_code(story)
    if code == "B":
        return []
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes
    # D 末四拍勿被连说翻 speaker 冲垮
    protect_tail = 4 if code == "D" else 0
    end = max(1, len(dialogue) - protect_tail)
    fixes = 0
    for i in range(1, end):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa in {"昭昭", "灿灿"} and sa == sb:
            new_sp = "灿灿" if sa == "昭昭" else "昭昭"
            b["speaker"] = new_sp
            notes.append(f"连说改speaker[{i}]")
            if code == "D":
                ln = str(b.get("line") or "")
                if new_sp == "灿灿" and re.search(
                    r"按你说的|照做|我数着|一步都不含糊|绝不偷懒|我认真系",
                    ln,
                ):
                    b["line"] = "你小心点，别乱动"
                    notes.append(f"D连说改口催[{i}]")
                elif new_sp == "昭昭" and re.search(
                    r"我来扶|我来弄|你别乱动|小心点|你倒是|快点",
                    ln,
                ):
                    b["line"] = "那我按你说的，照做就是了"
                    notes.append(f"D连说改口照做[{i}]")
            fixes += 1
            if fixes >= 6:
                break
    return notes


_VOCATIVE_NAMES = ("妈妈", "妈", "孩子们", "孩子", "昭昭", "灿灿")
_FINAL_PARTICLES = "呀啊呢吧吗了啦"


def _patch_vocative_punctuation(story: dict) -> list[str]:
    """句尾多余「听着」时去掉；不强制补逗号，避免句句尾都带标点。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    vocatives = "|".join(re.escape(v) for v in _VOCATIVE_NAMES)
    # 句尾多余「听着」：「啊孩子们听着」→「啊孩子们」
    pattern_trailing_listen = re.compile(
        rf"([{_FINAL_PARTICLES}]|{vocatives})听着$",
        re.UNICODE,
    )

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").rstrip()
        if not line:
            continue
        new_line = pattern_trailing_listen.sub(r"\1", line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"去句尾听着[{i}]")
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
    notes.extend(patch_type_body(out))
    notes.extend(_patch_vocative_punctuation(out))
    notes.extend(_patch_overlong_lines(out))
    notes.extend(_patch_consecutive_speakers(out))
    notes.extend(patch_type_body(out))
    notes.extend(_patch_consecutive_speakers(out))
    # 字数垫最后做：避免被 patch_type_body / 截断吃掉
    notes.extend(_patch_body_char_budget(out))
    notes.extend(_patch_overlong_lines(out))
    notes.extend(_patch_consecutive_speakers(out))
    # D：连说/补字后再次焊死收束角色，防回旋镖落到灿灿
    locked = str(out.get("_story_type") or "").strip()
    is_d = (
        locked.upper().startswith("D")
        or "字面执行" in str(out.get("punchline_explain") or "")
        or resolve_story_type_code(out) == "D"
    )
    if is_d:
        from app.services.daily_story.story_types.d.patch import (
            patch_d_align_boomerang_quote,
            patch_d_ensure_fix,
            patch_d_fix_closing_roles,
            patch_d_strip_executor_voice_from_cancan,
        )

        notes.extend(patch_d_strip_executor_voice_from_cancan(out))
        notes.extend(patch_d_ensure_fix(out))
        notes.extend(_patch_consecutive_speakers(out))
        notes.extend(patch_d_fix_closing_roles(out))
        # 收束可能在中段末制造连说；再修中段，末四拍仍保护
        notes.extend(_patch_consecutive_speakers(out))
        notes.extend(patch_d_align_boomerang_quote(out))
        prev = (out.get("dialogue") or [None, None])[-2]
        last = (out.get("dialogue") or [None])[-1]
        if isinstance(prev, dict) and str(prev.get("speaker") or "") != "昭昭":
            prev["speaker"] = "昭昭"
            notes.append("D回旋镖speaker→昭昭")
        if isinstance(last, dict) and str(last.get("speaker") or "") != "灿灿":
            last["speaker"] = "灿灿"
            notes.append("D末句speaker→灿灿")
        # 收束/合并可能吃字：再垫；末轮补字后再修一次连说
        if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
            notes.extend(
                _patch_body_char_budget(out, allow_insert_lines=True),
            )
            notes.extend(_patch_overlong_lines(out))
            notes.extend(_patch_consecutive_speakers(out))
            if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
                notes.extend(
                    _patch_body_char_budget(out, allow_insert_lines=False),
                )
                notes.extend(_patch_overlong_lines(out))
        notes.extend(_patch_consecutive_speakers(out))
        if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
            notes.extend(
                _patch_body_char_budget(out, allow_insert_lines=False),
            )
            notes.extend(_patch_overlong_lines(out))
            notes.extend(_patch_consecutive_speakers(out))
        # 末两句角色再焊一次（不合并中段，防吃字）
        prev = (out.get("dialogue") or [None, None])[-2]
        last = (out.get("dialogue") or [None])[-1]
        if isinstance(prev, dict) and str(prev.get("speaker") or "") != "昭昭":
            prev["speaker"] = "昭昭"
            notes.append("D回旋镖speaker→昭昭")
        if isinstance(last, dict) and str(last.get("speaker") or "") != "灿灿":
            last["speaker"] = "灿灿"
            notes.append("D末句speaker→灿灿")
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
    story_type: str | None = None,
) -> str:
    """按本轮错误 + 上一稿字数选择重试 length_mode。

    优先信校验文案（总字数须≥/≤）；只差几个字走 revise_patch；
    字数已在区间时走 revise，避免「只修连说」被 trim/expand 带跑篇幅。
    """
    err = errors or ""
    type_code = parse_story_type_code(
        story_type=story_type,
        punchline=str(
            (prev_story or {}).get("punchline_explain") or "",
        ),
    )
    if isinstance(prev_story, dict):
        locked = resolve_story_type_code(prev_story)
        if locked in STORY_TYPE_LABELS:
            type_code = locked
    n_lines = 0
    chars = dialogue_total_chars(prev_story if isinstance(prev_story, dict) else None)
    if isinstance(prev_story, dict) and isinstance(prev_story.get("dialogue"), list):
        n_lines = len(prev_story["dialogue"])
    e_chars_min = (
        265
        if type_code == "E" and n_lines >= 10
        else DAILY_STORY_BODY_CHARS_MIN
    )
    if type_code == "E" and n_lines >= 10 and chars < e_chars_min:
        gap = e_chars_min - chars
        if gap <= 72:
            return "revise_patch"
    if type_code == "D" and isinstance(prev_story, dict):
        dialogue = prev_story.get("dialogue")
        if isinstance(dialogue, list) and len(dialogue) > 18:
            if (
                "D类正文过长" in err
                or "中段拖沓" in err
                or "妈妈插话" in err
            ):
                return "revise_trim"
    deficit = _parse_body_char_deficit(err)
    excess = _parse_body_char_excess(err)
    if "总字数须≥" in err:
        if type_code == "E" and n_lines >= 10:
            return "revise_patch"
        if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        # D 偏短：走 expand 在上一稿上一次补满，勿打回 draft 整开
        return "revise_expand"
    if "总字数须≤" in err:
        if excess is not None and excess <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            return "revise_patch"
        return "revise_trim"
    # 引话局部问题：优先微调 1–2 句，勿整篇扩写冲垮骨架
    if "引话" in err:
        return "revise_patch"
    chars = dialogue_total_chars(prev_story if isinstance(prev_story, dict) else None)
    if chars < e_chars_min:
        gap = e_chars_min - chars
        if type_code == "E" and n_lines >= 10:
            return "revise_patch"
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
    """按本轮**首要**校验问题追加一条可执行修订指令。"""
    from app.services.daily_story.retry_hints import build_validation_retry_hints

    return build_validation_retry_hints(
        errors, chars=chars, type_code=type_code, max_issues=1,
    )


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
    type_code = parse_story_type_code(
        story_type=story_type,
        punchline=str(prev_story.get("punchline_explain") or ""),
    )
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
            # D 类：正文句数预算固定（13–14 句），缺字时不让模型去“插很多句”走偏，
            # 而是优先补到 13 句；若已在 13–14 句内，则只做句内顶字。
            if type_code == "D":
                dialogue = prev_story.get("dialogue")
                n_lines = len(dialogue) if isinstance(dialogue, list) else 0
                avg = (chars // n_lines) if n_lines else 0
                length_hint = (
                    f"【D·一次补满·硬验收】上一稿 {chars} 字 / {n_lines} 句"
                    f"（均 {avg} 字/句），还差 {deficit} 字。\n"
                    f"本轮输出须同时满足：① 正文恰好 13 或 14 句；"
                    f"② 中段每句尽量 20–{DAILY_STORY_LINE_CHARS_MAX} 字；"
                    f"③ dialogue 总字数 ≥{aim_lo}（至少 ≥{chars_min}）。\n"
                    f"保留不知变通骨架只增不删；轮流说话；"
                    f"禁止整稿重写、禁止轻轻放×N 凑字。"
                    f"写不满 {chars_min} 字视为失败，勿交短稿。\n"
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
    from app.services.daily_story.retry_hints import pick_primary_validation_errors

    dialogue = prev_story.get("dialogue")
    n_lines = len(dialogue) if isinstance(dialogue, list) else 0
    if type_code == "E" and chars < chars_min and not length_hint:
        deficit = chars_min - chars
        if n_lines >= 10:
            length_hint = (
                f"【E·补字】上一稿 {chars}字/{n_lines}句，还差 {deficit} 字。"
                f"句内扩字或加妈妈开脱/追问细节，写到 ≥{chars_min} 即可。\n"
            )
    issue_hint = _retry_issue_hints(errors, chars=chars, type_code=type_code)
    if "D类后果跑偏宜在中段已可见" in errors:
        issue_hint = (
            "【D·中段后果】中段（建议第 5–10 句）必须出现至少 1 个后果关键词："
            "洒/掉/乱/倒了/弄乱/坏了/打不开/死结/溢/变形；不要只在末句才出现。\n"
            + issue_hint
        )
    primary = pick_primary_validation_errors(errors, max_items=1)
    primary_line = primary[0] if primary else errors
    prev_json = json.dumps(prev_story, ensure_ascii=False)
    return (
        f"主题：{theme}\n"
        f"【字数硬卡】正文 {chars_min}–{chars_max} 字；"
        f"每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；重试瞄准 {aim_lo}–{aim_hi}。\n"
        f"{length_hint}"
        f"{issue_hint}"
        f"【本轮问题·优先修此项】{primary_line}\n"
        "【修订要求】只改上述专项指令；保留 conflict_core；"
        "一次只修优先项，其余下轮再验；"
        "差几个字就句内补，勿整稿重开；勿写发现开场；勿换主题。\n"
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
    speaker_hint = ""
    if avoid in {"昭昭", "灿灿", "妈妈"}:
        speaker_hint = (
            f"开场末句说话人不能是「{avoid}」"
            f"（正文以「{avoid}」起句，避免拼后连说）；"
            "可为另外两人之一。\n"
        )
    return (
        f"{base}\n\n"
        f"【重试】上一轮开场未通过：{errors}\n"
        f"{speaker_hint}"
        f"开场台词必须点名以下至少一词：{must_txt}；"
        "必须 2 句且换人；写正文开始前的定格现场，勿接正文前两句顶嘴。\n"
        "请只输出合法 JSON："
        '{"opening":[{"speaker":"昭昭","line":"..."},'
        '{"speaker":"妈妈","line":"..."}]}；'
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
        f"speaker 仅昭昭/灿灿/妈妈，禁同人连说。\n"
        f"setting / conflict_core 如已正确则保留不动。\n\n"
        f"【上一稿】\n{json.dumps(prev_story, ensure_ascii=False)}\n\n"
        "请输出修订后的完整 JSON。"
    )
