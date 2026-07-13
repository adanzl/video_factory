"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）。"""

_IMAGE_PROMPT_QUALITY_RULE = (
    "⑥质量要求：写可见的材质、纹理、光影过渡与层次是否清楚，画面信息是否充实（如「高视觉密度」「细节层次清楚」）；"
    "禁止写4K/8K/分辨率/像素/超高清等规格套话（出图尺寸由系统控制）；"
    "风格形容词仅可在③风格维使用，勿在⑥重复堆砌；"
    "禁止空话凑字数（如「极致细节」「大师之作」）。"
)

_IMAGE_PROMPT_FORMAT_RULE = (
    "输出为一段连贯中文，不要用「主体：」「场景/环境：」等维度标签；"
    "六维按自然语序融入，围绕一个视觉焦点展开。"
)

_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅按画面复杂度充分展开（目标约180字，至少150字），不凑字数。"
    + _IMAGE_PROMPT_FORMAT_RULE
    + "须逐层写清可见细节，禁止空泛形容词："
    + "①主体（主要主体、姿态、关键动作或互动）；"
    + "②场景/环境（前景/中景/背景、空间纵深）；"
    + "③视觉风格（严格遵循 visual_style 全片定调）；"
    + "④光照（主光与辅光方向、明暗氛围）；"
    + "⑤构图（景别、主体位置与占比、相机角度、留白）；"
    + _IMAGE_PROMPT_QUALITY_RULE
    + "【关键约束】只描述单帧静态画面中各元素的瞬时状态，"
    + "禁止写连续运动、变化过程或时间推移（如「缓缓移动」「逐渐偏移」「鼓起又平复」），"
    + "动态描述只放在 motion_prompt 中。"
    + "另遵守语义边界：仅表达本段 text 与 visual_brief，禁止提前画后续段落内容。"
    + "禁止生成世界地图、地球仪、任何包含国界线的地图元素。"
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
        "禁止提前画后续段落内容。",
        "禁止可读大段文字/水印/品牌Logo。",
    )
)

_IMAGE_PROMPT_MOTION_TAIL = (
    "【语言要求】motion_prompt 必须使用中文撰写，禁止英文或中英混合。"
    "motion_prompt 用 15-80 字描述本镜画面中正在发生的具体动态，"
    "必须紧扣 image_prompt 中已出现的主体与场景，写清楚「谁在做什么、环境发生了什么变化」。"
    "写法要点："
    "1) 先从 image_prompt 中找出画面主体（物体、场景元素），描述它在 10 秒内的具体动作或状态变化；"
    "2) 若主体为人物或动物，须写情绪或神态变化（如神情从疑惑转为恍然、眼神中透出警觉）；"
    "3) 可补充 1 个环境元素的联动变化（如主体运动带动的烟、水、光影反应）；"
    "4) 动态须有方向、速度、幅度等可感知细节，不要只写「轻微晃动」这类模糊词；"
    "5) 末尾须说明哪些元素保持稳定不变（如「画面主体位置不变」「人物面部与服装保持一致」），防止模型在动态中丢失一致性。"
    "镜头仅可极缓推近/拉远/平移，幅度很小。"
    "禁止：使用抽象特效词（光效、光晕、粒子、能量、光圈、脉动、闪电、闪烁、图标、UI元素等），必须写画面中真实可见物体的物理动态；"
    "禁止：套话「镜头固定，主体稳定，画面平滑」及同义填空。"
    "正例：丹炉炉盖被蒸汽顶起又落下，缝隙中白烟成股涌出向右飘散，丹炉整体位置与造型保持不变。"
    "正例：烧杯中蓝色液体从底部开始冒泡，气泡逐渐密集并带动液面缓慢上涌，烧杯与桌面保持静止。"
    "正例：古书书页被风从右向左逐页翻起，书角翘起后缓缓回落，书脊与桌面接触位置不变。"
    "正例：沙盘上细沙从高处沿沟壑缓缓滑落，堆积的扇面逐渐扩大，沙盘边框固定不动。"
    "正例：老者眉头微蹙，目光缓缓移向窗外，神情从沉思转为凝重，面部特征与服装保持一致。"
    "反例：小偷手指微微弯曲。（描述人物肢体动作）"
    "反例：镜头固定，主体稳定，画面平滑。（套话填空，未说明具体动态）"
    "反例：图标轻微闪烁，能量光圈脉动。（抽象特效词）"
)

_IMAGE_PROMPT_RULE_SD15 = (
    "篇幅精简、能说明白即可，但须逐点覆盖六维："
    + "①主体；②场景/环境；③视觉风格；④光照；⑤构图；⑥质量要求；"
    + _IMAGE_PROMPT_FORMAT_RULE
    + _IMAGE_PROMPT_QUALITY_RULE
    + "【关键约束】只描述单帧静态画面，禁止写运动/变化/时间推移，动态描述只放在 motion_prompt 中。"
    + "并遵守语义边界（仅本段内容）。"
    + "禁止生成世界地图、地球仪、任何包含国界线的地图元素。"
    + "实际 SD1.5 出图以 sd15_prompt_en 为准。"
    + "image_prompt 和 sd15_prompt_en 都必须使用中文和英文分别写，禁止 image_prompt 出现英文。"
)

_IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT = (
    "每段image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实历史再现，"
    "光影考究、暗部有层次、低饱和古风色调，适配9:16竖屏构图；"
    "禁止卡通/绘本/扁平插画风。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁止提前画后续段落内容。",
        "禁止可读文字、奏折、诏书等文字元素。",
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
