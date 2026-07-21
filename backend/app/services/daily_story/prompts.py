"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

import json
import re

from app.services.daily_story.cast import DAILY_CAST_NAMES

# 角色外貌固定描述，供 visual_style 和分镜生成共享
# 昭昭与灿灿有参考图，妈妈无参考图独立定义
DAILY_STORY_CHARACTERS = (
    "昭昭：7岁男孩，男孩气黑色超短发（发长在耳垂以上，清晰露出双耳及整个后颈，齐耳学生头），"
    "圆脸，穿蓝色短袖T恤，比灿灿矮约半个头；"
    "灿灿：10岁女孩，扎马尾辫，穿粉色卫衣，比昭昭高约半个头"
)

# 妈妈无参考图，外貌特征由 LLM 在 image_prompt 中文字描述，不混入有参考图角色常量
DAILY_STORY_CHARACTER_MOM = "妈妈：成年女性，黑色长发，米色上衣牛仔裤"

# 片长：语速约 3.6 字/秒、目标约 1:30–2:00
# 总字数上下限均硬性；单句上限硬性，配合分镜合并
DAILY_STORY_TOTAL_CHARS_MIN = 300
DAILY_STORY_TOTAL_CHARS_MAX = 380
DAILY_STORY_TOTAL_CHARS_TARGET_MAX = 360
DAILY_STORY_LINE_CHARS_MAX = 18

# 开场钩子仅作提示词约束，不做关键词硬卡（主题各异，固定词表易误杀）
_SOFT_ENDING_MARKERS = (
    "算了", "姐姐真棒", "听妈妈的", "我们和好", "下次注意",
    "你真棒", "和好吧", "听姐姐的",
)

_PUNCHLINE_TYPE_MARKERS = (
    "权威翻车", "公平执念", "字面执行", "结盟翻车", "妈妈破功",
    "A类", "C类", "D类", "B类", "E类",
    "A：", "C：", "D：", "B：", "E：",
)

# 后半若出现且未在 conflict_core/setting/前段出现，视为跑题
_OFFTOPIC_MARKERS = (
    "体育课", "学校", "老师", "班主任", "告爸爸", "告诉爸爸",
    "公园", "同学", "操场", "放学", "上课", "教室",
)

_CONFLICT_CORE_MAX_CHARS = 24
_CONFLICT_ANCHOR_STOP = frozenset(
    {
        "昭昭", "灿灿", "妈妈", "姐弟", "我们", "什么", "怎么",
        "这个", "那个", "不是", "就是", "可以", "不行",
    }
)

_DAILY_STORY_CONTRACT = """\
【共用设定】
- 受众：孩子和有娃的大人（家长能会心一笑，孩子觉得好玩；禁成人梗/谐音/网络热梗）。
- 角色年龄：昭昭7岁弟弟，灿灿10岁姐姐；可发言角色仅昭昭、灿灿、妈妈。
- 爸爸可「不在场被提到」，禁止作为 speaker；禁止老师入戏。
- 场景：家庭内部或家门口（客厅/厨房/卧室/门口）；禁止学校、放学路、公园等外景主场。
- 片长：对白总字数硬性 300–380 字，写作目标约 320–360 字（禁止注水车轱辘）；
  每句台词硬性≤18字；口语短句，一层意思一句说完。
"""

DAILY_STORY_SYSTEM_PROMPT = f"""\
你是一位家庭情景喜剧编剧，写昭昭&灿灿的日常对话短剧。
面向孩子和有娃的大人：笑点要孩子听得懂，家长看得出自家日常。

{_DAILY_STORY_CONTRACT}
【角色设定】
- 昭昭：弟弟，男孩，7岁。好奇心强，喜欢追问，擅长用现实经验挑战抽象规则，经常把简单的事越问越复杂。天真且固执。
- 灿灿：姐姐，女孩，10岁。比昭昭懂事一点，偶尔想模仿大人的语气管教弟弟，但自己的逻辑也经常掉进孩子的坑里。有时候会被昭昭带偏，嘴硬但心软。
- 妈妈：配角。可出场，但台词少；主戏仍是姐弟，妈妈不是戏核。
- 关系：亲姐弟，住在一起；主戏是姐弟斗嘴/较真/互相带偏，不是被妈妈教育。

【矛盾类型（默认优先 A/C/D；B/E 少用）】
- A 权威翻车（优先）：姐姐用「大人腔/我是姐姐」压弟弟，被字面逻辑戳穿。
- C 公平执念（优先）：抢先后、分东西、谁吃亏——双方规则各执一词，越辩越歪。
- D 字面执行（优先）：把叮嘱/规则按字面做砸（叮嘱可来自不在场的大人）。
- B 结盟翻车（少用）：姐弟想瞒妈妈或钻空子，一起露馅。
- E 妈妈破功（少用）：妈妈想讲理或装凶，被孩子绕到自己逻辑矛盾。

【妈妈戏份（硬约束）】
- 妈妈可出场，但台词要少：建议全程 ≤3 句，只起触发/收口/点破。
- 主笑点与大部分回合须在昭昭、灿灿之间；禁止妈妈长篇讲理或占半场以上对白。
- 禁止把「妈妈教育孩子」写成主线。

【开场钩子（硬约束）】
- 前 2 句必须露出具体冲突（抢/藏/弄脏/谁先/不给等），禁止寒暄铺垫。
- setting 也要写清冲突已发生（如：客厅，姐弟抢遥控器）。

【单冲突（硬约束）】
- 全文只围绕一件小事加码（规则升级、证据翻车、字面钻空子），禁止后半另开账。
- 必须输出 conflict_core：一句话写清「谁 vs 谁，争什么」（≤24 字），
  与 theme / setting / 前 2 句一致。
- 禁止岔开学校/体育课/告爸爸/老师/公园等与 conflict_core 无关的新主线。
- 妈妈只收口/点破，禁止由妈妈引入新冲突或新事件。
- punchline_explain 须说明末句如何破的就是这个 conflict_core。

【节奏（硬约束）】
- 每 6–8 句须有一个小反转或加码（规则升级、证据翻车、第三方插嘴），禁止平铺到结尾才抖包袱。
- 台词要具体：点名「上次你也…」「妈说过…」「这是我的…」，少讲抽象公平大道理。

【绝对禁止】
1. 禁止成人笑话、谐音梗、俏皮话、网络热梗。
2. 禁止「因为……所以……」等书面连接词，全部用口语短句。
3. 禁止叙事小说腔（「他心想」「她无奈地」等），只写纯对话+极简 setting。
4. 禁止姐姐真的「说教成功」或软收尾（如「算了」「姐姐真棒」当结局）。
5. 禁止为凑长度反复换说法车轱辘。
6. 禁止后半段换冲突、换地点主场、新开一件事。

【笑点与收束】
- 笑点 = 孩子的字面/现实逻辑 碰撞 姐姐的「装大人」规则，或两人各执一词越辩越歪。
- 每一句推论须基于刚听到的字面意思或亲眼见过的生活经验，不能跳级。
- 在 300–380 字内把误会滚大再收束；最后一句让「装大人/规则逻辑」破功或哑口。
- punchline_explain 须写明类型（如「C类公平执念」）+ 末句如何破功，禁止空话。

【格式要求】
严格输出以下JSON结构：
{{
  "scene_title": "不超过10字，场记或口语钩子均可（如：谁先洗）",
  "setting": "一句话说明地点和初始冲突动作（如：客厅，姐弟抢遥控器）",
  "conflict_core": "≤24字，谁vs谁争什么（如：姐弟抢新橡皮）",
  "dialogue": [
    {{"speaker": "昭昭", "line": "台词（≤18字）"}},
    {{"speaker": "灿灿", "line": "台词"}},
    {{"speaker": "妈妈", "line": "台词（宜少）"}}
  ],
  "punchline_explain": "类型标签+收束逻辑（例：C类公平执念，姐姐规则被字面戳穿）"
}}
妈妈可有台词，但宜少（建议≤3句）；主回合仍是姐弟。
"""

DAILY_STORY_USER_TEMPLATE = """\
请根据上述规则，生成一个昭昭和灿灿的日常对话场景。

【本次场景主题（核心事件）】：{theme}

【要求】：
1. 紧扣主题，家庭内/门口小事，不要宏大叙事；全文只服务同一 conflict_core。
2. 矛盾优先 A/C/D（姐弟互怼）；B/E 仅主题明确需要时才用。
3. 对白总字数硬性 300–380，目标约 320–360；每句硬性 ≤18 字；
   speaker 仅昭昭/灿灿/妈妈。
4. 前 2 句必须露出具体冲突；禁止寒暄开场。
5. 妈妈可出场，但台词宜少（建议≤3句）；禁止写成妈妈教育戏。爸爸不可作 speaker。
6. 输出 conflict_core（≤24 字）；punchline_explain 须含类型标签并说明如何破该冲突。
7. 禁止后半另开账（学校/体育课/告爸爸等与主题无关主线）。

请直接输出JSON。
"""

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


def build_daily_story_prompts(theme: str) -> tuple[str, str]:
    """构造日常故事生成的 system + user 提示词。"""
    return DAILY_STORY_SYSTEM_PROMPT, DAILY_STORY_USER_TEMPLATE.format(theme=theme)


DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是儿童情景对话短剧的分镜编剧，只负责把对白切成可执行镜头，不写画面描述。

【可发言角色】昭昭（7岁弟弟）、灿灿（10岁姐姐）、妈妈。场景以家庭内部/门口为主。

【分镜规则】
1. 【目标镜数】全文切成约 {target_min}–{target_max} 镜（对白 {total_chars} 字 / {line_count} 句）。
   禁止一句一镜；禁止拆成远超目标的碎镜。
2. 【默认并镜】按同一地点、同一轮互怼/同一话题合并；每镜通常 2–5 句对白。
3. 【单镜字数】建议 {min_chars}–{max_chars} 字（约 {min_sec}–{max_sec} 秒，
   语速 {chars_per_sec} 字/秒）。少于 {min_chars} 字必须并入邻镜；
   单镜合计不得超过 {max_chars} 字（约 ≤{max_sec} 秒）。各镜尽量均匀。
4. 为每镜标注 shot_type（全景/中景/特写），在环境交代、对话主体、情绪或道具之间穿插。
5. 【转折用特写，不拆碎】反驳、破功、愣住、妈妈插嘴、证据翻出等转折句：
   放在该镜开头（可带紧随的 1–2 句回应），shot_type 优先「特写」；
   禁止为转折把短句单独拆成不足 {min_chars} 字的镜；
   也禁止把转折句埋进五句长镜末尾。全文特写镜不超过总镜数约 1/3。

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
1. 目标约 {target_min}–{target_max} 镜；禁止一句一镜、禁止碎镜
2. 每镜通常 2–5 句；单镜建议 {min_chars}–{max_chars} 字（约 ≤{max_sec} 秒）
3. 转折句用特写并放在镜首，但须并入邻句，不得单独拆成短镜
4. 原台词须全部分配到各镜 dialogue，措辞不得改

请直接输出 JSON。
"""

# 与 DailyScriptStage 时长告警对齐
DAILY_SCRIPT_MAX_SEGMENT_SEC = 18.0
# 单镜下限：过短会碎镜、出图浪费；与近期正常任务（约 24+ 字/镜）对齐
DAILY_SCRIPT_MIN_SEGMENT_SEC = 8.0
# 目标镜字数中位（用总字数估算镜数）
DAILY_SCRIPT_TARGET_CHARS_PER_SHOT = 40


def _format_prompt_number(value: float) -> str:
    """提示词里去掉无意义的小数尾（18.0 → 18）。"""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _daily_script_shot_targets(total_chars: int) -> tuple[int, int]:
    """按总字数估算目标镜数区间（对齐近期正常任务约 7–11 镜）。"""
    per = DAILY_SCRIPT_TARGET_CHARS_PER_SHOT
    ideal = max(1, round(total_chars / per)) if total_chars else 8
    target_min = max(1, ideal - 2)
    target_max = ideal + 2
    if total_chars >= DAILY_STORY_TOTAL_CHARS_MIN:
        # 完整篇幅：压在 6–14，避免再出现 30+ 碎镜
        target_min = max(6, min(target_min, 12))
        target_max = min(14, max(target_max, target_min + 2))
    return target_min, target_max


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
    target_min, target_max = _daily_script_shot_targets(total_chars)
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
        target_min=target_min,
        target_max=target_max,
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
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
    return [t for t in tokens if t not in _CONFLICT_ANCHOR_STOP]


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
    for marker in _OFFTOPIC_MARKERS:
        if marker in latter and marker not in allowed:
            errors.append(
                f"后半疑似跑题：出现「{marker}」，与 conflict_core={core!r} 无关"
            )
            break


def validate_daily_story_json(story: dict) -> None:
    """校验日常故事 LLM 返回的 JSON 格式是否符合预期结构，失败抛 ValueError。"""
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
        # 总字数硬卡上下限
        if total_chars and total_chars < DAILY_STORY_TOTAL_CHARS_MIN:
            errors.append(
                f"对白总字数须≥{DAILY_STORY_TOTAL_CHARS_MIN}，当前{total_chars}"
                f"（还差{DAILY_STORY_TOTAL_CHARS_MIN - total_chars}字）"
            )
        if total_chars and total_chars > DAILY_STORY_TOTAL_CHARS_MAX:
            errors.append(
                f"对白总字数须≤{DAILY_STORY_TOTAL_CHARS_MAX}，当前{total_chars}"
                f"（超出{total_chars - DAILY_STORY_TOTAL_CHARS_MAX}字）"
            )

        # 禁止软收尾
        last_line = ""
        for item in reversed(dialogue):
            if isinstance(item, dict):
                last_line = str(item.get("line") or "").strip()
                if last_line:
                    break
        if last_line and any(m in last_line for m in _SOFT_ENDING_MARKERS):
            errors.append(
                f"末句禁止软收尾（算了/和好等）：{last_line!r}"
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

    if errors:
        raise ValueError("daily_story 校验失败: " + "; ".join(errors))


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


def build_daily_story_retry_user(
    theme: str,
    *,
    prev_story: dict,
    errors: str,
) -> str:
    """基于上一稿构造修订重试 user（扩写/删减，避免另起炉灶）。"""
    _, base_user = build_daily_story_prompts(theme)
    chars = dialogue_total_chars(prev_story)
    length_hint = ""
    if chars < DAILY_STORY_TOTAL_CHARS_MIN:
        deficit = DAILY_STORY_TOTAL_CHARS_MIN - chars
        length_hint = (
            f"\n【字数】上一稿仅 {chars} 字，还差 {deficit} 字才能过线。"
            f"请在上一稿冲突上增补姐弟互怼回合，扩到"
            f"{DAILY_STORY_TOTAL_CHARS_MIN}–{DAILY_STORY_TOTAL_CHARS_MAX} 字；"
            "不要换主题、不要重写开场。"
        )
    elif chars > DAILY_STORY_TOTAL_CHARS_MAX:
        excess = chars - DAILY_STORY_TOTAL_CHARS_MAX
        length_hint = (
            f"\n【字数】上一稿 {chars} 字，超出 {excess} 字。"
            f"请删车轱辘/合并回合，压到 ≤{DAILY_STORY_TOTAL_CHARS_MAX} 字，"
            "保留冲突与收束。"
        )
    conflict_hint = (
        "\n【单冲突】禁止换 conflict_core / 换主题 / 后半另开账；"
        "只在上一稿同一冲突上修订。"
    )
    prev_json = json.dumps(prev_story, ensure_ascii=False)
    return (
        f"{base_user}\n\n"
        f"【重试】上一轮 JSON 校验未通过：{errors}"
        f"{length_hint}"
        f"{conflict_hint}\n"
        "请直接输出修订后的完整 JSON（仍须满足全部硬约束）。\n"
        f"【上一稿】\n{prev_json}"
    )
