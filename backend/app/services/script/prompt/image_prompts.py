"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）。"""

_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅150-180字，连贯中文，禁用维度标签。"
    "按风格→主体→场景→光照→构图→质量顺序："
    "①视觉风格（遵循 visual_style 定调，置于句首）；"
    "主体（角色须写年龄/发型/脸型/服装等外貌特征，与 visual_style 主角描述一致；姿态、动作）；"
    "③场景（前景/中景/背景）；"
    "④光照（主辅光、明暗）；⑤构图（景别、占比、留白）；"
    "⑥写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "仅表达本段 text 与 visual_brief，禁提前画后续段落。"
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
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁提前画后续段落。",
        "禁写实摄影风格、禁卡通以外画风。",
    )
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
