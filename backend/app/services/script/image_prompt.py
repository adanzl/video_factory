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
    + "的基本外貌特征与身高比例（参考图中昭昭比灿灿矮约半个头，须严格保持）。"
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
    "适配{orientation}构图。篇幅80-150字，连贯中文，禁用维度标签。"
    "顺序：地点场景→动作表情→光照→构图。"
    "【地点】开头必须写清具体室内地点（与全片 setting 一致，如客厅/厨房/卧室门口），"
    "写可见陈设（沙发、茶几、书桌、门口等）；"
    "禁止用「蜡笔彩虹/涂鸦色块背景」代替真实房间；"
    "禁止输出「竖构图/横屏/调整为」等元叙述。"
    "地点写清后写动作与表情；勿重复发型/服装（参考图前缀已注入；"
    "妈妈入画时外貌须写黑长发、米色上衣、牛仔裤）。"
    "【角色入画】只画本段 speakers；visual_brief 若出现未在 speakers 中的角色必须忽略；"
    "无 speakers 则只画场景、禁止画昭昭/灿灿/妈妈。"
    "【身高】昭昭与灿灿同框时必须写明昭昭比灿灿矮约半个头，"
    "禁止同高或弟弟更高。"
    "【表情】须夸张可读：瞪圆眼、撇嘴、叉腰、愣住张嘴、鼓腮、抿嘴鼓气等，"
    "表情强度对标本段台词情绪，禁止面无表情的站桩。"
    "【开场首镜】segment_index=1 须中近景或特写，定格冲突峰值姿势"
    "（抢/举/夺/藏道具动作最大的一瞬），冲突道具须清晰可见且占比够大，"
    "表情比后文再夸张一档；禁止平淡站桩或纯环境交代开场。"
    "单帧静态；勿写画风套话（出图前系统硬编码）。"
    "短例：'客厅地板上昭昭右手高举橡皮，瞪圆眼张大嘴喊；"
    "灿灿左手前伸眉毛倒竖张嘴争辩，昭昭比灿灿矮约半个头。"
    "窗光斜照地板。中近景，昭昭左灿灿右。'"
)

# 无参考图角色规则，仅当 segment 涉及该角色时追加
_IMAGE_PROMPT_RULE_NO_REF_CHARACTER = (
    "【无参考图角色】妈妈外貌须写为黑色长发、米色上衣、牛仔裤，禁止换装。"
)

# 带妈妈角色的补充示例，帮助模型理解如何描写妈妈
_IMAGE_PROMPT_EXAMPLE_WITH_MOM = (
    "含妈妈短例：'客厅里昭昭与灿灿对峙，妈妈站中间手臂微张，"
    "黑长发米色上衣牛仔裤，面露无奈。'"
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

_IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT = (
    "【ambient】15-80字，只写画面内无生命元素微动（光影、纱帘、尘埃、蜡笔屑等），"
    "禁人物/有生命体动作；末尾须写「人物姿势保持不变」。"
    "正例：窗边纱帘被风轻轻掀起又落下，人物姿势保持不变。"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME = (
    "【keyframe / 图生视频】20-90字，按 Agnes I2V 写法："
    "先写 1 个可见微动作（举手停、眉毛一挑、侧头等），"
    "再写必须保持不变的内容（面部表情与静图一致、不微笑不大笑、"
    "服装发型五官不变、其余姿势稳定）；可带极缓镜头推近。"
    "禁止只写动作不锁表情；禁止大位移换位、全身换姿势、多人齐跑、抽象光效。"
    "正例：妈妈右手微微前推做停势，面部表情保持严肃与静图一致不微笑，"
    "昭昭侧脸微抬，五官表情不变，服装发型稳定，镜头极缓推近。"
    "反例：妈妈举手眼神一亮，其余姿势稳定。（未锁表情，易被改成笑）"
    "反例：背景彩铅色块微微晃动，人物姿势保持不变。（关键帧禁止纯环境微动）"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY = (
    "【motion_prompt 分流】按该段 motion_mode 选择规则："
    "motion_mode=ambient（默认）→"
    + _IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT
    + "motion_mode=keyframe（特写/开场首镜/i2v 关键帧）→"
    + _IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME
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

_IMAGE_PROMPT_JSON_EXAMPLE_DAILY = (
    "客厅地板上昭昭举手比石头，脸不服气嘴角下撇；灿灿双手叉腰抿嘴瞪着他。"
    "窗光斜照地板。中景，昭昭左灿灿右。"
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

_IMAGE_PROMPTS_JSON_EXAMPLE_DAILY = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": """ + _IMAGE_PROMPT_JSON_EXAMPLE_DAILY + """,
      "motion_prompt": "窗边纱帘被风轻轻掀起又落下，人物姿势保持不变"
    },
    {
      "segment_index": 2,
      "image_prompt": "特写妈妈举手做停势，昭昭侧头仰望，背景虚化彩铅色块。",
      "motion_prompt": "妈妈右手微微前推做停势，面部表情保持严肃与静图一致不微笑，昭昭侧脸微抬，五官表情不变，服装发型稳定，镜头极缓推近"
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

_MOTION_USER_RULE_DAILY = (
    "motion_prompt 须按该段 motion_mode："
    "ambient 只写无生命微动且末尾写人物姿势保持不变；"
    "keyframe 写 1 个微动作并明确锁住面部表情与静图一致（不微笑），"
    "禁大位移、禁纯环境晃动套话；"
    "各段互不重复，禁止套话。"
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
    motion = (
        _IMAGE_PROMPT_MOTION_TAIL_DAILY
        if content_style == CONTENT_STYLE_DAILY_STORY
        else _IMAGE_PROMPT_MOTION_TAIL
    )
    text = head + _with_orientation(body, orientation) + motion
    if sd15_mode:
        text += _IMAGE_PROMPT_RULE_SD15
    return text


def _format_segment_brief(
    seg: dict,
    *,
    prefix: str = "",
    include_speakers: bool = False,
    mark_motion_mode: bool = False,
) -> str:
    line = (
        f"{prefix}segment {seg.get('segment_index')}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
    )
    if include_speakers:
        speakers = sorted(
            {
                str(d.get("speaker") or "").strip()
                for d in (seg.get("dialogue") or [])
                if str(d.get("speaker") or "").strip()
            }
        )
        line += f"; speakers={speakers!r}"
    if mark_motion_mode:
        from app.utils.job_info import is_keyframe_segment

        mode = "keyframe" if is_keyframe_segment(seg) else "ambient"
        line += f"; motion_mode={mode}"
    return line


def _collect_segment_prompt_lines(
    segments: list[dict],
    segment_indices: list[int] | None,
    *,
    include_speakers: bool = False,
    mark_motion_mode: bool = False,
) -> tuple[list[str], set[int] | None]:
    """拼装分镜行；返回 (lines, wanted)。wanted 为 None 表示全量生成。"""
    if segment_indices is None:
        return [
            _format_segment_brief(
                seg,
                include_speakers=include_speakers,
                mark_motion_mode=mark_motion_mode,
            )
            for seg in segments
        ], None

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
        lines.append(
            _format_segment_brief(
                seg,
                prefix=tag,
                include_speakers=include_speakers,
                mark_motion_mode=mark_motion_mode,
            )
        )
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


def _user_tail(*, include_sd15_prompt: bool, content_style: str | None = None) -> str:
    motion_rule = (
        _MOTION_USER_RULE_DAILY
        if content_style == CONTENT_STYLE_DAILY_STORY
        else _MOTION_USER_RULE
    )
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
    return "\n\n" + head + motion_rule + tail


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
    if content_style != CONTENT_STYLE_DAILY_STORY:
        parts.append(_MAP_COMPLIANCE)
    if content_style == CONTENT_STYLE_DAILY_STORY and not include_sd15_prompt:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE_DAILY
    elif include_sd15_prompt:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE
    else:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15
    parts.append(json_output_clause(json_example))
    return "".join(parts)


def _build_user_prompt(
    script: dict[str, Any],
    *,
    lines: list[str],
    include_sd15_prompt: bool,
    supplementary_info: str | None,
    feedback: str | None,
    content_style: str | None = None,
) -> str:
    setting = str(script.get("setting") or "").strip()
    setting_line = f"全片地点 setting：{setting}\n" if setting else ""
    user = append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"{setting_line}"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + _user_tail(
                include_sd15_prompt=include_sd15_prompt,
                content_style=content_style,
            )
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
    is_daily = profile_style == CONTENT_STYLE_DAILY_STORY
    lines, wanted = _collect_segment_prompt_lines(
        segments,
        segment_indices,
        include_speakers=is_daily,
        mark_motion_mode=is_daily,
    )
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
        content_style=profile_style,
    )
    return prompt_step("image_prompts", system, user)
