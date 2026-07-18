"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）。"""

from app.services.daily_story.prompts import DAILY_STORY_CHARACTERS
from app.utils.job_info import CONTENT_STYLE_DAILY_STORY

_DAILY_STORY_I2I_PREFIX = (
    "基于参考图调整人物动作，保留" + DAILY_STORY_CHARACTERS + "的基本外貌特征。"
)

# 硬编码后期缀，daily_story 出图后自动拼接
_DAILY_STORY_STYLE_SUFFIX = (
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
    "主观夸张变形，高饱和色彩，涂色出界，"
    "橡皮擦拭痕迹，手工感，孩子气的构图。"
)

# content_style → (prefix, suffix) 映射
_IMAGE_PROMPT_WRAPPERS: dict[str, tuple[str, str]] = {
    CONTENT_STYLE_DAILY_STORY: (_DAILY_STORY_I2I_PREFIX, _DAILY_STORY_STYLE_SUFFIX),
}


def wrap_image_prompts(
    segments: list[dict],
    *,
    content_style: str | None = None,
) -> list[dict]:
    """根据 content_style 给 image_prompt 添加前缀/后缀。

    LLM 只生成场景核心内容，部分 pipeline 需要在返回时给 image_prompt
    加上固定前缀（如 I2I 参考图指令）和后缀（如风格描述）。
    此函数在 LLM 生成后、消费前统一应用。

    Args:
        segments: 分镜列表（原地修改）。
        content_style: 内容风格标识，如 "daily_story"。

    Returns:
        原地修改后的 segments。
    """
    if not content_style:
        return segments
    wrapper = _IMAGE_PROMPT_WRAPPERS.get(content_style)
    if not wrapper:
        return segments
    prefix, suffix = wrapper
    for seg in segments:
        prompt = seg.get("image_prompt")
        if prompt and isinstance(prompt, str) and prompt.strip():
            seg["image_prompt"] = prefix + prompt + suffix
    return segments


_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅100-180字，连贯中文，禁用维度标签。"
    "按风格→主体→场景→光照→构图→质量顺序："
    "①视觉风格（遵循 visual_style 定调，置于句首）；"
    "主体（角色须写年龄/发型/脸型/服装/身高体型等外貌特征，与 visual_style 主角描述一致；表情、姿态、动作）；"
    "③场景（前景/中景/背景）；"
    "④光照（主辅光、明暗）；⑤构图（景别、占比、留白）；"
    "⑥写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "仅表达本段 text 与 visual_brief，禁提前画后续段落。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【逐段自检】每段 image_prompt 须独立覆盖全部六维，逐段对照六维清单自查，缺则补写，禁止省略任何维度。"
)

_IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：卡通科普插画风，"
    "明快蓝橙主色调，轮廓清晰、色块分明，偏科普示意图质感；"
    "非绘本水彩、非电影级写实摄影，适配9:16竖屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_SCIENCE_LANDSCAPE = _IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT.replace(
    "适配9:16竖屏构图", "适配16:9横屏构图"
)

_IMAGE_PROMPT_RULE_REALISTIC_PORTRAIT = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实视觉，布光考究、"
    "景深自然、材质细节真实可辨，色彩明快有层次，适配9:16竖屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_LIFE_LANDSCAPE = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配16:9横屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁提前画后续段落。",
        "禁可读大段文字/水印/品牌Logo。",
    )
)

_IMAGE_PROMPT_RULE_DAILY_STORY = (
    "image_prompt严格遵循visual_style画风定调，角色外貌与visual_style主角形象一致；"
    "适配{orientation}构图。"
    "篇幅100-180字，连贯中文，禁用维度标签。"
    "按主体→场景→光照→构图→质量顺序："
    "主体（角色须写年龄/发型/脸型/服装/身高体型等外貌特征，与 visual_style 主角描述一致；表情、姿态、动作）；"
    "③场景（前景/中景/背景）；"
    "④光照（主辅光、明暗）；⑤构图（景别、占比、留白）；"
    "⑥写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "禁写实摄影风格、禁卡通以外画风。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【逐段自检】每段 image_prompt 须独立覆盖全部六维，逐段对照六维清单自查，缺则补写，禁止省略任何维度。"
    + "【约束】image_prompt只需写场景内容部分（动作、表情、场景、光照、构图）。"
    + "【参考图说明】角色参考图为昭昭（左）与灿灿（右）并排图。"
    + "【表情要求】image_prompt必须写明每个角色当前的面部表情（如专注皱眉、张大嘴巴、眯眼笑等），表情须对标对话情绪强度（争吵时瞪眼张嘴吵架脸、平静时微笑放松），不得仅写动作忽略表情，表情是情绪涂鸦风格的关键。"
    + '内容写作范例：\'新场景中昭昭踮起脚尖，右手指在空中虚画一个"昭"字，身体略向左倾以保持平衡，脸上是认真专注的神情，嘴唇抿紧、眼睛看着手指画的线条；灿灿站在一旁，双手抱在胸前，撇着嘴摇头，马尾辫随之晃动，眼神略带嘲笑。背景是客厅墙壁，挂着家庭照片。顶部吊灯暖光投射，照亮"昭"字笔画区域。中近景构图，昭昭在左、灿灿在右，头顶留白。\''
)

# 无参考图角色规则，仅当 segment 涉及该角色时追加
_IMAGE_PROMPT_RULE_NO_REF_CHARACTER = (
    "【无参考图角色】妈妈角色无参考图，image_prompt中妈妈的外貌必须严格写为黑色长发、米色上衣、牛仔裤，禁止以剧情需要为由替妈妈换其他服装。"
)

# 带妈妈角色的补充示例，帮助模型理解如何描写妈妈
_IMAGE_PROMPT_EXAMPLE_WITH_MOM = (
    "含妈妈角色的例子（仅场景内容，不含固定前后缀）：'新场景中昭昭和灿灿跪坐争夺拼图盒，昭昭瞪大眼睛张大嘴巴、灿灿眯眼笑伸手去抢，"
    "妈妈站在门口双手叉腰无奈摇头，黑色长发垂肩、米色上衣牛仔裤。'"
)


_IMAGE_PROMPT_MOTION_TAIL = (
    "【motion_prompt】中文，15-80字，紧扣 image_prompt 主体与场景。"
    "写主体10秒内具体动作/神态变化，可补1个环境联动（烟、水、光影等），"
    "须有方向、速度等细节，禁模糊词；末尾说明稳定元素。"
    "镜头仅可极缓推近/拉远/平移。"
    "禁抽象特效词（光效、光晕、粒子、能量、光圈、脉动、闪电、闪烁、图标、UI元素等）与镜头套话。"
    "正例：丹炉炉盖被蒸汽顶起又落下，缝隙中白烟成股涌出向右飘散，丹炉整体位置与造型保持不变。"
    "反例：小偷手指微微弯曲。（仅肢体动作，无环境联动）"
)

_IMAGE_PROMPT_RULE_SD15 = (
    "篇幅精简，覆盖六维（风格→主体→场景→光照→构图→质量），连贯中文，禁维度标签。"
    "写材质纹理光影，禁4K/8K套话与空话。"
    "【约束】仅单帧静态，动态只放 motion_prompt；仅本段内容。"
    "实际 SD1.5 出图以 sd15_prompt_en 为准。"
    "image_prompt 用中文，sd15_prompt_en 用英文。"
)

_IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT = (
    "每段image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实历史再现，"
    "光影考究、暗部有层次、低饱和古风色调，适配9:16竖屏构图；"
    "禁止卡通/绘本/扁平插画风。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁提前画后续段落。",
        "禁可读文字、奏折、诏书等文字元素。",
    )
)

_IMAGE_PROMPT_RULE_MYSTERY_LANDSCAPE = _IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT.replace(
    "适配9:16竖屏构图", "适配16:9横屏构图"
)

_SD15_PROMPT_EN_RULE = (
    "同时为每段输出 sd15_prompt_en：专为 Stable Diffusion 1.5 优化的英文提示词（20～40 词），"
    "格式为「[核心主体] [动作/状态], [场景类型], [一个关键视觉特征]」；"
    "先读 visual_brief 末尾的画面类型标签确定主体方向，再提炼主体；"
    "只写一个核心主体，禁止并列堆砌多个名词；"
    "禁止写 lora 标签、style 词和背景后缀（系统自动追加）；"
    "science 类禁止 person/face/head 等人物词。\n"
    "sd15_prompt_en 正确示例：\n"
    "  写实场景：\"stainless steel pot on stove, close-up surface detail, kitchen counter\"\n"
    "  结构示意图：\"cross-section diagram of battery cell, labeled anode cathode layers\"\n"
    "  对比图：\"healthy lung tissue vs damaged lung, side by side, medical illustration\"\n"
    "  线稿解剖图：\"line art diagram of human lung anatomy, labeled air sacs, white background\"\n"
    "  微观分子图：\"carbon monoxide molecules passing through wet fabric mesh, glowing science\"\n"
)


# ── JSON 样例 ─────────────────────────────────────────────────────

_IMAGE_PROMPT_JSON_EXAMPLE_TEXT = (
    "古老的青铜丹炉占据画面左侧，炉内青绿色火焰与绿烟向上弥漫，炉壁锈迹与烟熏清晰；"
    "前景散落赤色丹药与药渣，背景昏暗炼丹房内木质药柜虚化。"
    "清宫写实风格，暗调青灰主色，炉口底光为主、侧面炭火余烬为辅。"
    "极近景特写，丹炉占左侧三分之二，右侧丹药清晰，略低角度。"
    "金属、火焰与烟雾质感真实，细节层次清楚。"
)

_IMAGE_PROMPTS_JSON_EXAMPLE = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": """ + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """,
      "motion_prompt": "炉口青烟缓缓上升，火光轻闪，镜头极缓推进",
      "sd15_prompt_en": "cross-section diagram of lung alveoli, air sacs highlighted, medical illustration"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15 = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": """ + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """,
      "motion_prompt": "炉口青烟缓缓上升，火光轻闪，镜头极缓推进"
    }
  ]
}"""
