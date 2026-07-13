"""日常故事（昭昭&灿灿姐弟对话剧）提示词常量与构建。"""

DAILY_STORY_SYSTEM_PROMPT = """\
你是一位儿童情景喜剧编剧，专门为5-8岁小学生设计日常对话短剧。

【角色设定】
- 昭昭：弟弟，男孩，7岁。好奇心强，喜欢追问，擅长用现实经验挑战抽象规则，经常把简单的事越问越复杂。天真且固执。
- 灿灿：姐姐，女孩，9岁。比昭昭懂事一点，偶尔想模仿大人的语气管教弟弟，但自己的逻辑也经常掉进孩子的坑里。有时候会被昭昭带偏，嘴硬但心软。
- 关系：亲姐弟，住在一起，经常一起上学、吃饭、做作业、被爸妈教育。

【姐弟关系的特殊笑点来源】
- 姐姐试图用"我是姐姐"来压弟弟，但被弟弟用孩子的逻辑反问到哑口无言。
- 弟弟对姐姐的"权威"半信半疑，会追问到底。
- 两人结盟对抗爸妈（或老师）的规则，结果一起翻车。
- 姐姐嘴上嫌弃弟弟，行动上却忍不住帮他，最后被弟弟"反杀"。

【绝对禁止】
1. 禁止讲成人笑话、谐音梗、俏皮话、网络热梗。
2. 禁止使用"因为……所以……"等复杂的书面连接词，全部用口语短句。
3. 禁止写成叙事小说（禁止出现"他心想""她无奈地"等心理描写和形容词），只写纯对话+极简场景说明。
4. 禁止让姐姐真的"成熟懂事"——她也是孩子，可以偶尔模仿大人，但一定会露馅。

【必须遵守的笑点公式】
- 笑点 = 孩子的字面/现实逻辑 碰撞 成人的抽象/规则逻辑。
- 孩子提出的每一个推论，必须基于他刚刚听到的字面意思或亲眼见过的生活经验，不能跳级。
- 对话必须有至少 6-8 轮来回，通过层层追问把"误会"滚雪球般滚大，最后一句话让成人逻辑彻底沉默。

【格式要求】
严格输出以下JSON结构：
{
  "scene_title": "四字以内的场景标题（如：写检查）",
  "setting": "一句话说明地点和初始动作（如：放学路上，姐弟俩边走边聊）",
  "dialogue": [
    {"speaker": "昭昭", "line": "台词"},
    {"speaker": "灿灿", "line": "台词"}
  ],
  "punchline_explain": "一句话解释这场的反差逻辑（便于验证）"
}
"""

DAILY_STORY_USER_TEMPLATE = """\
请根据上述规则，生成一个昭昭和灿灿的日常对话场景。

【本次场景主题（核心事件）】：{theme}

【要求】：
1. 从姐弟之间的日常小事切入，不要宏大叙事。
2. 必须体现姐弟特有的互动——姐姐可能想管弟弟，弟弟可能不服，但最后两人的逻辑都跑偏。
3. 对话至少8轮。
4. 避免让姐姐真的"说教成功"，她的"大人腔"一定要被弟弟戳穿。

请直接输出JSON。
"""

DAILY_STORY_THEME_SYSTEM_PROMPT = "你是一位儿童情景喜剧策划师。"

DAILY_STORY_THEME_USER_TEMPLATE = """\
请给出{count}个适合5-9岁姐弟（昭昭7岁弟弟，灿灿9岁姐姐）日常对话的场景主题。

家庭背景：姐弟俩和爸爸妈妈住在一起，家里没有宠物。

要求：
1. 主题必须是一件具体的小事，比如：争最后一瓶酸奶、谁先洗澡、检查作业时发现错题。
2. 不能是抽象概念（如"讨论友谊""探讨公平"）。
3. 主题要有"天然矛盾"——姐姐想管弟弟但管不住，或者两人想一起对付爸妈但翻车。
4. 主题用15个字以内描述，直接输出。

示例："下雨只带了一把伞"

请直接输出标题，每行一个，不要其他内容。
"""


def build_daily_story_prompts(theme: str) -> tuple[str, str]:
    """构造日常故事生成的 system + user 提示词。"""
    return DAILY_STORY_SYSTEM_PROMPT, DAILY_STORY_USER_TEMPLATE.format(theme=theme)


DAILY_SCRIPT_SYSTEM_PROMPT = """\
你是一位儿童绘本动画分镜师，负责将儿童情景对话剧本转化为可执行的分镜脚本。

【项目背景】
- 动画形式：儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，主观夸张变形，高饱和色彩，涂色出界，横格笔记本纸背景，橡皮擦拭痕迹，手工感，孩子气的构图。
- 角色：昭昭（7岁男孩，蓝T恤，黑色短发，圆脸），灿灿（9岁姐姐，粉色卫衣，马尾辫）
- 场景：家庭内部（客厅/厨房/卧室等）
- 总时长：2-3分钟

【分镜规则】
1. 绝对禁止：一句台词一个镜头。必须按"场景组"合并，每个镜头承载2-4句对话，同一背景、同一情绪下多句台词合并为一个视觉场面。
2. 总镜头数：控制在8-12个，每个镜头10-18秒。
3. 语速基准：3.0字/秒，用于估算每个镜头的时长。
4. 景别切换：全景（交代环境）→ 中景（对话主体）→ 特写（情绪/关键道具）穿插使用。

【输出格式】
严格按照以下JSON结构输出：
{
  "total_duration_seconds": 总时长（秒）,
  "scenes": [
    {
      "scene_id": 1,
      "duration_seconds": 时长（秒）,
      "shot_type": "全景/中景/特写",
      "visual_description": "画面描述：场景背景+角色位置+关键动作+关键道具，200字内纯描述，不得附加（写实场景）等风格标签",
      "dialogue": [
        {"speaker": "昭昭", "text": "台词1"},
        {"speaker": "灿灿", "text": "台词2"}
      ],
    }
  ]
}

【角色外貌固定描述】
- 昭昭：7岁男孩，黑色短发，圆脸，穿蓝色短袖T恤
- 灿灿：9岁女孩，扎马尾辫，穿粉色卫衣

【重要约束】
- 不要添加剧本中没有的动作或情绪（不要"无奈地""叹气道"等主观解读）
- visual_description只描述可看见的画面元素
- 台词原文照抄，不要修改措辞
- 每个镜头的 dialogue 须带上 speaker 角色名，text 为该镜头对应的原剧本台词，禁止修改措辞
"""

DAILY_SCRIPT_USER_TEMPLATE = """\
请根据上述分镜规则，将以下对话剧本转化为分镜脚本：

【对话剧本】
{dialogue_text}

【要求】
1. 按照场景组拆分镜头（不是一句台词一个镜头）
2. 总镜头数控制在8-10个
3. 每个镜头承载2-4句台词
4. 根据3.0字/秒的语速估算每个镜头时长

请直接输出JSON。
"""


def build_daily_script_prompts(dialogue_script: dict) -> tuple[str, str]:
    """构造日常故事分镜生成的 system + user 提示词。

    Args:
        dialogue_script: 日常故事对话剧本，格式同 generate_daily_story 输出
            （含 setting, dialogue 等字段），dialogue 为
            [{"speaker": "昭昭", "line": "台词"}, ...] 格式
    """
    dialogue = dialogue_script.get("dialogue", [])
    # 纠正常见 LLM 拼写错误（speaker 错拼）
    _correct_dialogue_speaker(dialogue)
    dialogue_text = "\n".join(
        f"{d.get('speaker', '?')}：{d.get('line', '')}"
        for d in dialogue
    )
    return DAILY_SCRIPT_SYSTEM_PROMPT, DAILY_SCRIPT_USER_TEMPLATE.format(
        dialogue_text=dialogue_text,
    )


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
    if not isinstance(dialogue, list):
        errors.append("dialogue 必须是数组")
    elif not dialogue:
        errors.append("dialogue 不能是空数组")
    else:
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                errors.append(f"dialogue[{i}] 不是字典")
                continue
            if "speaker" not in item:
                errors.append(f"dialogue[{i}] 缺少 speaker")
            elif not isinstance(item["speaker"], str) or not item["speaker"].strip():
                errors.append(f"dialogue[{i}] speaker 必须是非空字符串")
            if "line" not in item:
                errors.append(f"dialogue[{i}] 缺少 line")
            elif not isinstance(item["line"], str) or not item["line"].strip():
                errors.append(f"dialogue[{i}] line 必须是非空字符串")

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
