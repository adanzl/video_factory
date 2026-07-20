"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

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

# 片长：语速约 3.1 字/秒、目标约 2:00–2:15
# 总字数下限硬性；上限仅写作建议（略超可接受，不校验失败）
# 单句上限硬性，配合分镜 2–4 句合并
DAILY_STORY_TOTAL_CHARS_MIN = 360
DAILY_STORY_TOTAL_CHARS_TARGET_MAX = 420
DAILY_STORY_LINE_CHARS_MAX = 18

_DAILY_STORY_CONTRACT = """\
【共用设定】
- 受众：孩子和有娃的大人（家长能会心一笑，孩子觉得好玩；禁成人梗/谐音/网络热梗）。
- 角色年龄：昭昭7岁弟弟，灿灿10岁姐姐；可发言角色仅昭昭、灿灿、妈妈。
- 爸爸可「不在场被提到」，禁止作为 speaker；禁止老师入戏。
- 场景：家庭内部或家门口（客厅/厨房/卧室/门口）；禁止学校、放学路、公园等外景主场。
- 片长：对白总字数硬性不少于360字，写作目标约360–420字（略超可接受，禁止注水车轱辘）；
  每句台词硬性≤18字；口语短句，一层意思一句说完。
"""

DAILY_STORY_SYSTEM_PROMPT = f"""\
你是一位家庭情景喜剧编剧，写昭昭&灿灿的日常对话短剧。
面向孩子和有娃的大人：笑点要孩子听得懂，家长看得出自家日常。

{_DAILY_STORY_CONTRACT}
【角色设定】
- 昭昭：弟弟，男孩，7岁。好奇心强，喜欢追问，擅长用现实经验挑战抽象规则，经常把简单的事越问越复杂。天真且固执。
- 灿灿：姐姐，女孩，10岁。比昭昭懂事一点，偶尔想模仿大人的语气管教弟弟，但自己的逻辑也经常掉进孩子的坑里。有时候会被昭昭带偏，嘴硬但心软。
- 妈妈：姐弟俩的妈妈，负责照顾和监督。温柔但偶尔被孩子绕晕，有时会板着脸装凶但内心柔软，容易在追问下破功。
- 关系：亲姐弟，住在一起，经常一起吃饭、做作业、被妈妈教育。

【矛盾类型（择一或自然组合，须能在三角角色内演完）】
- A 权威翻车：姐姐用「大人腔/我是姐姐」压弟弟，被字面逻辑戳穿。
- B 结盟翻车：姐弟想瞒妈妈或钻空子，一起露馅。
- C 公平执念：抢先后、分东西、谁吃亏——双方规则各执一词，越辩越歪。
- D 字面执行：把「听话/快点/小心」等按字面做砸。
- E 妈妈破功：妈妈想讲理或装凶，被孩子绕到自己逻辑矛盾。

【绝对禁止】
1. 禁止成人笑话、谐音梗、俏皮话、网络热梗。
2. 禁止「因为……所以……」等书面连接词，全部用口语短句。
3. 禁止叙事小说腔（「他心想」「她无奈地」等），只写纯对话+极简 setting。
4. 禁止姐姐真的「说教成功」或软收尾（如「算了」「姐姐真棒」当结局）。
5. 禁止为凑长度反复换说法车轱辘。

【笑点与收束】
- 笑点 = 孩子的字面/现实逻辑 碰撞 成人的抽象/规则逻辑。
- 每一句推论须基于刚听到的字面意思或亲眼见过的生活经验，不能跳级。
- 须有足够回合把误会滚大（总字数≥360），再收束；最后一句让「大人逻辑」破功或哑口。
- 禁止注水车轱辘；也禁止写到一半就收（过短无效）。

【格式要求】
严格输出以下JSON结构：
{{
  "scene_title": "不超过10字，场记或口语钩子均可（如：谁先洗）",
  "setting": "一句话说明地点和初始动作（如：客厅，妈妈拿着浴巾问谁先洗澡）",
  "dialogue": [
    {{"speaker": "昭昭", "line": "台词（≤18字）"}},
    {{"speaker": "灿灿", "line": "台词"}},
    {{"speaker": "妈妈", "line": "台词"}}
  ],
  "punchline_explain": "一句话说明反差类型（A–E）与收束逻辑"
}}
无妈妈戏份时 dialogue 可不含妈妈；有妈妈则须有其台词。
"""

DAILY_STORY_USER_TEMPLATE = """\
请根据上述规则，生成一个昭昭和灿灿的日常对话场景。

【本次场景主题（核心事件）】：{theme}

【要求】：
1. 紧扣主题，家庭内/门口小事，不要宏大叙事。
2. 矛盾落在 A–E 可演类型内；姐弟互动要跑偏，禁止说教成功或软收尾。
3. 对白总字数硬性 ≥360，目标约 360–420（略超可接受）；每句硬性 ≤18 字；speaker 仅昭昭/灿灿/妈妈。
4. 妈妈是否出场随主题需要；爸爸不可作 speaker。

请直接输出JSON。
"""

DAILY_STORY_THEME_SYSTEM_PROMPT = f"""\
你是一位家庭情景喜剧策划师，为昭昭&灿灿日常对话短剧策划主题。
{_DAILY_STORY_CONTRACT}
"""

DAILY_STORY_THEME_USER_TEMPLATE = """\
请给出{count}个适合昭昭（7岁弟弟）与灿灿（10岁姐姐）日常对话的场景主题。
面向孩子和有娃的大人。

家庭背景：姐弟和爸爸妈妈住在一起，家里没有宠物；可发言角色仅昭昭、灿灿、妈妈。

要求：
1. 主题必须是一件具体的小事，比如：争最后一瓶酸奶、谁先洗澡、检查作业时发现错题。
2. 不能是抽象概念（如「讨论友谊」「探讨公平」）。
3. 主题要有天然矛盾，且能在家门口/室内用姐弟±妈妈演完，例如：
   姐姐管不住弟弟；姐弟瞒妈妈翻车；抢先后/分东西吵公平；把叮嘱按字面做砸；把妈妈绕破功。
4. 禁止依赖爸爸入戏、老师入戏、学校/公园等外景主场的主题。
5. 主题须能用短句口语一场讲完（对白体量大约两分钟出头即可）。
6. 主题用15个字以内描述，直接输出。

示例："争最后一瓶酸奶"
示例："谁先洗澡"

请直接输出标题，每行一个，不要其他内容。
"""


def build_daily_story_prompts(theme: str) -> tuple[str, str]:
    """构造日常故事生成的 system + user 提示词。"""
    return DAILY_STORY_SYSTEM_PROMPT, DAILY_STORY_USER_TEMPLATE.format(theme=theme)


DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是一位儿童绘本动画分镜师，负责将儿童情景对话剧本转化为可执行的分镜脚本。

【项目背景】
- 动画形式：儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，主观夸张变形，高饱和色彩，涂色出界，橡皮擦拭痕迹，手工感，孩子气的构图。
- 角色：昭昭（7岁男孩，蓝T恤，男孩气黑色超短发，发长在耳垂以上，清晰露出双耳及整个后颈，齐耳学生头，圆脸，比灿灿矮约半个头），灿灿（10岁姐姐，粉色卫衣，马尾辫，比昭昭高约半个头），妈妈（成年女性，黑色长发，米色上衣牛仔裤）
- 场景：家庭内部（客厅/厨房/卧室等）

【分镜规则】
1. 绝对禁止：一句台词一个镜头。必须按"场景组"合并，每个镜头承载2-4句对话，同一背景、同一情绪下多句台词合并为一个视觉场面。
2. 各镜头台词总字数尽量均匀分布，避免某个镜头过多（超过50字）而其他镜头过少（少于20字）。
3. 每个镜头不要超过15秒（语速基准{chars_per_sec}字/秒）。
4. 景别切换：全景（交代环境）→ 中景（对话主体）→ 特写（情绪/关键道具）穿插使用。

【输出格式】
严格按照以下JSON结构输出：
{{
  "scenes": [
    {{
      "scene_id": 1,
      "shot_type": "全景/中景/特写",
      "visual_description": "画面描述：场景背景+角色位置+关键动作+关键道具，200字内纯描述，不得附加（写实场景）等风格标签",
      "dialogue": [
        {{"speaker": "昭昭", "text": "台词1"}},
        {{"speaker": "灿灿", "text": "台词2"}},
        {{"speaker": "妈妈", "text": "台词3"}}
      ]
    }}
  ]
}}

【角色外貌固定描述】
- 昭昭：7岁男孩，男孩气黑色超短发（发长在耳垂以上，清晰露出双耳及整个后颈，齐耳学生头），圆脸，穿蓝色短袖T恤，比灿灿矮约半个头
- 灿灿：10岁女孩，扎马尾辫，穿粉色卫衣，比昭昭高约半个头
- 妈妈：成年女性，黑色长发，米色上衣牛仔裤
- 【身高】昭昭与灿灿同框时弟弟矮约半个头，禁止同高或弟弟更高

【重要约束】
- 不要添加剧本中没有的动作或情绪（不要"无奈地""叹气道"等主观解读）
- visual_description只描述可看见的画面元素
- 【角色入画】visual_description 中的人物必须且仅为本镜头 dialogue 的发言角色；
  未发言角色禁止旁观/路过/入画；台词提到名字不等于发言
- 台词原文照抄，不要修改措辞
- 每个镜头的 dialogue 须带上 speaker 角色名，text 为该镜头对应的原剧本台词，禁止修改措辞
"""

DAILY_SCRIPT_USER_TEMPLATE = """\
请根据上述分镜规则，将以下对话剧本转化为分镜脚本：

【对话剧本】
{dialogue_text}

【要求】
1. 按照场景组拆分镜头（不是一句台词一个镜头）
2. 每个镜头承载2-4句台词

请直接输出JSON。
"""


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
    dialogue = dialogue_script.get("dialogue", [])
    # 纠正常见 LLM 拼写错误（speaker 错拼）
    _correct_dialogue_speaker(dialogue)
    dialogue_text = "\n".join(
        f"{d.get('speaker', '?')}：{d.get('line', '')}"
        for d in dialogue
    )
    return DAILY_SCRIPT_SYSTEM_PROMPT.format(chars_per_sec=chars_per_sec), DAILY_SCRIPT_USER_TEMPLATE.format(
        dialogue_text=dialogue_text,
    )


def _dialogue_char_count(line: str) -> int:
    """与成片时长估算一致：按台词字符串长度计。"""
    return len(line or "")


def validate_daily_story_json(story: dict) -> None:
    """校验日常故事 LLM 返回的 JSON 格式是否符合预期结构，失败抛 ValueError。"""
    errors: list[str] = []

    if not isinstance(story, dict):
        raise ValueError(f"daily_story 返回数据不是字典: {type(story).__name__}")

    _correct_dialogue_speaker(story.get("dialogue", []))

    # 必需字段检查
    for field in ("scene_title", "setting", "dialogue", "punchline_explain"):
        if field not in story:
            errors.append(f"缺少必需字段: {field}")

    if errors:
        raise ValueError("; ".join(errors))

    # scene_title 类型
    if not isinstance(story["scene_title"], str) or not story["scene_title"].strip():
        errors.append("scene_title 必须是非空字符串")
    if not isinstance(story["setting"], str) or not story["setting"].strip():
        errors.append("setting 必须是非空字符串")
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
        # 只硬卡下限；上限略超不失败，避免重试拖垮流程
        if total_chars and total_chars < DAILY_STORY_TOTAL_CHARS_MIN:
            errors.append(
                f"对白总字数须≥{DAILY_STORY_TOTAL_CHARS_MIN}，当前{total_chars}"
            )

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
