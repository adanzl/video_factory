"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）与构建。"""

from __future__ import annotations

from typing import Any

from app.services.daily_story.prompts import DAILY_STORY_CHARACTERS
from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    CONTENT_STYLE_TECH_SCIENCE,
    ORIENTATION_LANDSCAPE,
)

_DAILY_STORY_I2I_PREFIX = (
    "基于参考图调整人物动作，保留"
    + DAILY_STORY_CHARACTERS
    + "的基本外貌特征。"
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
    "主观夸张变形，高饱和色彩，涂色出界，"
    "橡皮擦拭痕迹，手工感，孩子气的构图。"
)
# 画风必须硬编码进 wrap：LLM 易漏写，出图侧不能依赖模型自带风格句

# 硬编码后期缀，daily_story 出图后自动拼接
_DAILY_STORY_STYLE_SUFFIX = ""

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
    "②主体（角色须写年龄/发型/脸型/服装/身高体型等外貌特征，与 visual_style 主角描述一致；表情、姿态、动作）；"
    "③场景（前景/中景/背景）；"
    "④光照（主辅光、明暗）；⑤构图（景别、占比、留白）；"
    "⑥写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "仅表达本段 text 与 visual_brief，禁提前画后续段落。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【逐段自检】每段 image_prompt 须独立覆盖全部六维，逐段对照六维清单自查，缺则补写，禁止省略任何维度。"
)

# 各风格正文：画风细节只跟 visual_style；规则只写约束与结构，用 {orientation} 占位
_IMAGE_PROMPT_RULE_SCIENCE = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成；"
    "非绘本水彩、非电影级写实摄影，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_REALISTIC = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_LIFE = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
    + "另禁可读大段文字/水印/品牌Logo。"
)

_IMAGE_PROMPT_RULE_DAILY_STORY = (
    "image_prompt严格遵循visual_style画风定调，角色外貌与visual_style主角形象一致；"
    "适配{orientation}构图。"
    "篇幅80-150字，连贯中文，禁用维度标签。"
    "按场景→动作→光照→构图顺序："
    "①场景（交代空间位置，如客厅玄关/卧室床上/学校教室等）；"
    "②角色动作表情（每个角色须写明当前动作与面部表情，"
    "不得重复发型/服装等外貌特征——系统已通过参考图前缀自动注入；"
    "妈妈无参考图时例外，须按无参考图角色规则写外貌）；"
    "③光照（主辅光、明暗）；④构图（景别、占比、留白）。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "禁写实摄影风格、禁卡通以外画风。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【表情要求】image_prompt必须写明每个角色当前的面部表情（如专注皱眉、张大嘴巴、眯眼笑等），"
    "表情须对标对话情绪强度（争吵时瞪眼张嘴吵架脸、平静时微笑放松），不得仅写动作忽略表情。"
    "【说明】画风与参考图指令由系统在出图前硬编码拼接，LLM 只写场景核心内容，勿在 image_prompt 重复整段画风套话。"
    + '内容写作范例：\'新场景中昭昭踮起脚尖，右手指在空中虚画一个"昭"字，身体略向左倾以保持平衡，脸上是认真专注的神情，嘴唇抿紧、眼睛看着手指画的线条；灿灿站在一旁，双手抱在胸前，嘴角下撇，眼神略带嘲笑。背景是客厅墙壁，挂着家庭照片。顶部吊灯暖光投射，照亮"昭"字笔画区域。中近景构图，昭昭在左、灿灿在右，头顶留白。\''
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


# 与 quality.image_prompt / user 一致：禁人物主动作，只写环境/物体微动
_IMAGE_PROMPT_MOTION_TAIL = (
    "【motion_prompt】中文，15-80字，紧扣 image_prompt 已出现的具体物体与场景。"
    "只写画面内无生命元素在约10秒内的细微物理变化（烟、水、光影、尘埃、火焰、布料等），"
    "须有方向、速度等细节，禁模糊词；末尾说明哪些主体保持稳定。"
    "镜头仅可极缓推近/拉远/平移。"
    "禁止写人物或任何有生命主体的动作/神态；"
    "禁抽象特效词（光效、光晕、粒子、能量、光圈、脉动、闪电、闪烁、图标、UI元素等）与镜头套话。"
    "正例：丹炉炉盖被蒸汽顶起又落下，缝隙中白烟成股涌出向右飘散，丹炉整体位置与造型保持不变。"
    "反例：小偷手指微微弯曲。（人物肢体动作，禁止）"
)

_IMAGE_PROMPT_RULE_SD15 = (
    "【SD1.5】另输出 sd15_prompt_en：篇幅精简的英文提示（20～40词），"
    "实际 SD1.5 出图以 sd15_prompt_en 为准；image_prompt 仍用中文保留六维信息供校对。"
)

_IMAGE_PROMPT_RULE_MYSTERY = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图；"
    "禁止卡通/绘本/扁平插画风。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
    + "另禁可读文字、奏折、诏书等文字元素。"
)

_SD15_PROMPT_EN_RULE = (
    "同时为每段输出 sd15_prompt_en：专为 Stable Diffusion 1.5 优化的英文提示词（20～40 词），"
    "格式为「[核心主体] [动作/状态], [场景类型], [一个关键视觉特征]」；"
    "根据 visual_brief 画面描述确定主体方向，再提炼主体；"
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
      "sd15_prompt_en": "bronze alchemy furnace with green flame, close-up, dark workshop"
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


# ── builders（常量须在上方）───────────────────────────────────────

from app.services.script.prompt_common import (  # noqa: E402
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
)


def _orientation_label(orientation: str) -> str:
    """横竖屏文案统一：9:16竖屏 / 16:9横屏。"""
    if orientation == ORIENTATION_LANDSCAPE:
        return "16:9横屏"
    return "9:16竖屏"


def _with_orientation(template: str, orientation: str) -> str:
    return template.format(orientation=_orientation_label(orientation))


_IMAGE_PROMPT_ROLES: dict[str, str] = {
    CONTENT_STYLE_HISTORICAL_MYSTERY: "你是历史悬案视频文生图与运动提示词专家。",
    CONTENT_STYLE_SCIENCE_CHILD: "你是童趣科普视频文生图与运动提示词专家。",
    CONTENT_STYLE_TECH_SCIENCE: "你是科技/产业科普视频文生图与运动提示词专家。",
    CONTENT_STYLE_LIFE_EXPERIENCE: "你是生活避坑/经验类视频文生图与运动提示词专家。",
    CONTENT_STYLE_DAILY_STORY: "你是儿童日常故事视频文生图与运动提示词专家。",
}

_IMAGE_PROMPT_STYLE_BODIES: dict[str, str] = {
    CONTENT_STYLE_DAILY_STORY: _IMAGE_PROMPT_RULE_DAILY_STORY,
    CONTENT_STYLE_HISTORICAL_MYSTERY: _IMAGE_PROMPT_RULE_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE: _IMAGE_PROMPT_RULE_LIFE,
    CONTENT_STYLE_SCIENCE_CHILD: _IMAGE_PROMPT_RULE_SCIENCE,
}

_MAP_COMPLIANCE = (
    "【地图合规】image_prompt禁止出现「世界地图」「全球地图」字样；"
    "地图场景必须限定为局部区域地图（如中东地图、非洲地图），"
    "不得出现完整世界地图或包含东亚/中国部分的画面。"
)

_MOTION_USER_RULE = (
    "motion_prompt 必须紧扣本段 image_prompt 中已出现的具体物体，从中选 1-2 个写其细微动态，"
    "禁止写人物或任何有生命主体的动作，禁止脱离画面编造元素，各段互不重复，禁止套话。"
)


def _image_prompt_role(content_style: str) -> str:
    return _IMAGE_PROMPT_ROLES.get(
        content_style,
        "你是视频文生图与运动提示词专家。",
    )


def image_prompt_rule(*, orientation: str, content_style: str, sd15_mode: bool = False) -> str:
    """按 content_style / orientation 选择文生图规则；sd15 仅附加，不替换风格正文。"""
    head = (
        "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
        "和video用的motion_prompt。"
    )
    # tech_science 等未单独列出的风格走电影级写实
    body = _IMAGE_PROMPT_STYLE_BODIES.get(content_style, _IMAGE_PROMPT_RULE_REALISTIC)
    text = head + _with_orientation(body, orientation) + _IMAGE_PROMPT_MOTION_TAIL
    if sd15_mode:
        text += _IMAGE_PROMPT_RULE_SD15
    return text


def _format_segment_brief(seg: dict, *, prefix: str = "") -> str:
    return (
        f"{prefix}segment {seg.get('segment_index')}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
    )


def _collect_segment_prompt_lines(
    segments: list[dict],
    segment_indices: list[int] | None,
) -> tuple[list[str], set[int] | None]:
    """拼装分镜行；返回 (lines, wanted)。wanted 为 None 表示全量生成。"""
    if segment_indices is None:
        return [_format_segment_brief(seg) for seg in segments], None

    wanted = {int(idx) for idx in segment_indices}
    # 目标段前后各留一段作上下文，便于 LLM 把握连贯性
    extra: set[int] = set()
    for idx in wanted:
        if idx - 1 >= 1:
            extra.add(idx - 1)
        if idx + 1 <= len(segments):
            extra.add(idx + 1)
    extra -= wanted
    shown = wanted | extra

    lines: list[str] = []
    for seg in segments:
        idx = int(seg.get("segment_index", 0))
        if idx not in shown:
            continue
        tag = "【仅上下文】" if idx in extra else "【需生成】"
        lines.append(_format_segment_brief(seg, prefix=tag))
    return lines, wanted


def _has_mom_speaker(segments: list[dict], wanted: set[int] | None) -> bool:
    for seg in segments:
        idx = int(seg.get("segment_index", 0))
        if wanted is not None and idx not in wanted:
            continue
        if any(d.get("speaker") == "妈妈" for d in (seg.get("dialogue") or [])):
            return True
    return False


def _coverage_clause(*, partial: bool) -> str:
    if partial:
        return (
            "image_prompts仅需输出标记为【需生成】的segment，"
            "【仅上下文】分段无需输出。"
        )
    return "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"


def _user_tail(*, include_sd15_prompt: bool) -> str:
    if include_sd15_prompt:
        head = (
            "请为每段编写 image_prompt 与 motion_prompt。"
            "image_prompt 按本风格规则写成一段连贯中文，勿用维度标签，不写分辨率套话。"
        )
        tail = "同时为每段输出准确的 sd15_prompt_en。"
    else:
        head = (
            "请为每段扩写 image_prompt 与 motion_prompt。"
            "image_prompt 按本风格规则写成一段连贯中文（勿用「主体：」等标签），"
            "篇幅按画面复杂度充分写，不凑字数、不写4K/8K/分辨率等规格套话。"
        )
        tail = ""
    return "\n\n" + head + _MOTION_USER_RULE + tail


def _build_system_prompt(
    *,
    content_style: str,
    orientation: str,
    include_sd15_prompt: bool,
    has_mom: bool,
    partial: bool,
) -> str:
    fields = (
        "、image_prompt、motion_prompt 与 sd15_prompt_en"
        if include_sd15_prompt
        else "、image_prompt 与 motion_prompt"
    )
    parts = [
        f"{_image_prompt_role(content_style)}输出JSON，字段：image_prompts。",
        f"image_prompts为数组，每项含segment_index{fields}。",
        image_prompt_rule(
            orientation=orientation,
            content_style=content_style,
            sd15_mode=include_sd15_prompt,
        ),
    ]
    if has_mom:
        parts.append(_IMAGE_PROMPT_RULE_NO_REF_CHARACTER)
        parts.append(_IMAGE_PROMPT_EXAMPLE_WITH_MOM)
    if include_sd15_prompt:
        parts.append(_SD15_PROMPT_EN_RULE)
    parts.append(_coverage_clause(partial=partial))
    parts.append(_MAP_COMPLIANCE)
    json_example = (
        _IMAGE_PROMPTS_JSON_EXAMPLE
        if include_sd15_prompt
        else _IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15
    )
    parts.append(json_output_clause(json_example))
    return "".join(parts)


def _build_user_prompt(
    script: dict[str, Any],
    *,
    lines: list[str],
    include_sd15_prompt: bool,
    supplementary_info: str | None,
    feedback: str | None,
) -> str:
    user = append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + _user_tail(include_sd15_prompt=include_sd15_prompt)
        ),
        supplementary_info or script.get("supplementary_info"),
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return user


def build_image_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    segment_indices: list[int] | None = None,
    include_sd15_prompt: bool = False,
) -> dict[str, str]:
    profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    lines, wanted = _collect_segment_prompt_lines(segments, segment_indices)
    system = _build_system_prompt(
        content_style=profile_style,
        orientation=profile_orientation,
        include_sd15_prompt=include_sd15_prompt,
        has_mom=_has_mom_speaker(segments, wanted),
        partial=wanted is not None,
    )
    user = _build_user_prompt(
        script,
        lines=lines,
        include_sd15_prompt=include_sd15_prompt,
        supplementary_info=supplementary_info,
        feedback=feedback,
    )
    return prompt_step("image_prompts", system, user)
