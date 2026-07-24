"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）与构建。"""

from __future__ import annotations

import re
from typing import Any

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    CONTENT_STYLE_TECH_SCIENCE,
    ORIENTATION_LANDSCAPE,
)

# ══════════════════════════════════════════════════════════════════════
#  daily_story 规则拼装 T2I（不再二次 LLM 扩写 visual_brief）
#
#  结构: 风格 + visual_brief + 角色外貌 + 光照 + 构图
# ══════════════════════════════════════════════════════════════════════

_DAILY_T2I_STYLE = (
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，线条用力不均，"
    "高饱和色彩，涂色出界，橡皮擦拭痕迹，手工感。"
)

_DAILY_CHAR_ZHAO = (
    "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，蓝色短袖T恤。"
)
_DAILY_CHAR_CANCAN = (
    "灿灿：10岁女孩，单侧高马尾，粉色卫衣。"
)
_DAILY_CHAR_MOM = (
    "妈妈：成年女性，黑色长发，米色上衣，牛仔裤。"
)
_DAILY_CHAR_HEIGHT = "昭昭比灿灿矮约半个头。"

_DAILY_CHAR_MAP: dict[str, str] = {
    "昭昭": _DAILY_CHAR_ZHAO,
    "灿灿": _DAILY_CHAR_CANCAN,
    "妈妈": _DAILY_CHAR_MOM,
}


def _daily_speakers_of(seg: dict) -> list[str]:
    """本段出场角色：优先 speakers 字段，否则从 dialogue 推导。"""
    raw = seg.get("speakers")
    if isinstance(raw, list) and raw:
        return [str(s).strip() for s in raw if str(s).strip()]
    from app.services.daily_story.cast import speakers_from_dialogue

    names = speakers_from_dialogue(seg.get("dialogue"))
    return [n for n in ("昭昭", "灿灿", "妈妈") if n in names]


_DAILY_LR_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)"
)


def _daily_layout_speakers(seg: dict, vb: str) -> list[str]:
    """左右站位：优先 visual_brief 明示，否则对白出现顺序，最后固定角色序。"""
    m = _DAILY_LR_RE.search(vb or "")
    if m:
        left, right = m.group(1), m.group(2)
        if left in _DAILY_CHAR_MAP and right in _DAILY_CHAR_MAP and left != right:
            return [left, right]
    order: list[str] = []
    for item in seg.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("speaker") or "").strip()
        if name in _DAILY_CHAR_MAP and name not in order:
            order.append(name)
    if len(order) >= 2:
        return order
    return _daily_speakers_of(seg)


def _strip_style_suffix(vb: str) -> str:
    """去掉 visual_brief 末尾画风句（含风格/线条/笔触等）。"""
    vb = vb.rstrip("。，, ")
    last_period = vb.rfind("。")
    tail = vb[last_period + 1 :] if last_period >= 0 else vb
    style_context = any(w in tail for w in ("风格", "线条", "笔触", "质感", "画风"))
    if not style_context:
        return vb + "。" if vb else ""
    style_keywords = ["彩铅", "涂鸦", "蜡笔", "水彩", "油画", "扁平", "写实风", "绘本"]
    if any(kw in tail for kw in style_keywords):
        pre = vb[:last_period].rstrip("。，, ") if last_period >= 0 else ""
        if pre:
            return pre + "。"
    return vb + "。" if vb else ""


def _daily_lighting(vb: str) -> str:
    indoor = any(w in vb for w in ("客厅", "卧室", "厨房", "房间", "室内", "书房"))
    if indoor:
        return "窗光从一侧斜照，在墙面和地面投下柔和光影。"
    return "室外自然光，柔和散射，画面明亮。"


def _daily_composition(shot_type: str, speakers: list[str]) -> str:
    names = [s for s in speakers if s in _DAILY_CHAR_MAP]
    look = {
        "昭昭": "蓝T恤短发男孩昭昭",
        "灿灿": "粉卫衣马尾女孩灿灿",
        "妈妈": "米色上衣黑长发妈妈",
    }
    if shot_type == "特写":
        if len(names) == 2:
            a, b = names[0], names[1]
            return (
                f"画面左边是{a}，右边是{b}。"
                f"中近景特写，严格左侧{look.get(a, a)}占左半、"
                f"右侧{look.get(b, b)}占右半，禁止左右对调。"
            )
        return "面部特写，占画面主体，背景虚化。"
    if shot_type == "中景":
        if len(names) == 2:
            a, b = names[0], names[1]
            return (
                f"画面左边是{a}，右边是{b}。"
                f"中景，严格左{look.get(a, a)}、右{look.get(b, b)}，"
                f"禁止左右对调，全身可见。"
            )
        return "中景，人物全身，环境可见。"
    return "根据画面自然构图。"


def strip_verify_regen_leak(prompt: str) -> str:
    """去掉误拼进 T2I 的质检改写元指令（历史污染 / 兜底）。"""
    text = (prompt or "").strip()
    marker = "出图质检连续未通过"
    idx = text.find(marker)
    if idx < 0:
        return text
    return text[:idx].rstrip(" \n\t")


def assemble_daily_t2i_prompt(
    seg: dict,
    *,
    extra: str | None = None,
) -> str:
    """规则拼装 daily_story image_prompt。

    风格 + visual_brief + 出场角色外貌 + 光照 + 构图。
    extra 仅用于显式附加的出图正文（勿传入质检/改写元指令）。
    """
    vb = str(seg.get("visual_brief") or "").strip()
    if vb:
        from app.services.script.visual_brief import scrub_daily_visual_brief

        vb = scrub_daily_visual_brief(vb)
    # visual_brief 若曾被污染，先剥掉质检元指令
    vb = strip_verify_regen_leak(vb)
    speakers = _daily_speakers_of(seg)
    shot = str(seg.get("shot_type") or "").strip()

    parts = [_DAILY_T2I_STYLE]
    if vb:
        parts.append(_strip_style_suffix(vb))

    char_parts: list[str] = []
    for name in speakers:
        if name in _DAILY_CHAR_MAP:
            char_parts.append(_DAILY_CHAR_MAP[name])
    if "昭昭" in speakers and "灿灿" in speakers:
        char_parts.append(_DAILY_CHAR_HEIGHT)
    if char_parts:
        parts.append("".join(char_parts))

    parts.append(_daily_lighting(vb))
    layout = _daily_layout_speakers(seg, vb)
    parts.append(_daily_composition(shot, layout))
    if extra and extra.strip():
        # 禁止把质检元指令当出图正文
        cleaned = strip_verify_regen_leak(extra.strip())
        if cleaned and cleaned != extra.strip():
            cleaned = ""
        if cleaned:
            parts.append(cleaned)
    return "".join(parts)


def assemble_daily_image_prompts(
    segments: list[dict],
    *,
    segment_indices: list[int] | None = None,
    extra: str | None = None,
) -> list[dict]:
    """原地为 daily 分镜写入规则拼装的 image_prompt。"""
    wanted = (
        {int(i) for i in segment_indices} if segment_indices is not None else None
    )
    for seg in segments:
        idx = int(seg.get("segment_index") or 0)
        if wanted is not None and idx not in wanted:
            continue
        seg["image_prompt"] = assemble_daily_t2i_prompt(seg, extra=extra)
    return segments


def wrap_image_prompts(
    segments: list[dict],
    *,
    content_style: str | None = None,
    extra: str | None = None,
) -> list[dict]:
    """按 content_style 定稿 image_prompt。

    daily_story：规则拼装（风格+visual_brief+外貌+光照+构图），不依赖 LLM 扩写。
    其他风格：无额外 wrap。
    """
    if content_style == CONTENT_STYLE_DAILY_STORY:
        return assemble_daily_image_prompts(segments, extra=extra)
    return segments


_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅150-300字，连贯中文，禁用维度标签。"
    "按风格→主体→场景→光照→构图→质量顺序："
    "①视觉风格（遵循 visual_style 定调，置于句首）；"
    "②主体（角色须写年龄/发型/脸型/服装/身高体型等外貌特征，与 visual_style 主角描述一致；表情扩张力、姿态、动作，至少2句细节）；"
    "③场景（前景/中景/背景，写至少 2 个具体物品）；"
    "④光照（主辅光方向、冷暖色调、明暗对比）；⑤构图（景别、占比、留白）；"
    "⑥写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "仅表达本段 text 与 visual_brief，禁提前画后续段落。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【逐段自检】每段 image_prompt 须独立覆盖全部六维，逐段对照六维清单自查，缺则补写，禁止省略任何维度。"
    "【长度】若不足 150 字，需补充主体细节（外貌/姿态）、场景陈设、光照方向/色温或构图说明；不凑字数，按画面复杂度自然充分描述。"
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

# daily_story：image_prompt 由规则拼装，LLM 只写 motion
_IMAGE_PROMPT_RULE_DAILY_STORY_MOTION = (
    "适配{orientation}构图。"
    "image_prompt 已由系统按「风格+visual_brief+角色外貌+光照+构图」规则拼装，"
    "禁止改写、禁止再输出 image_prompt 字段。"
    "仅为每段编写 motion_prompt，须紧扣已给出的 image_prompt。"
)


# 与 quality.image_prompt / user 一致：禁人物主动作，只写环境/物体微动
_IMAGE_PROMPT_MOTION_TAIL = (
    "【motion_prompt】中文，40-200字，上限 600 字，紧扣 image_prompt 已出现的具体物体与场景。"
    "只写画面内无生命元素在约10秒内的细微物理变化（烟、水、光影、尘埃、火焰、布料等），"
    "须有方向、速度、幅度等细节，禁模糊词；末尾说明哪些主体保持稳定。"
    "镜头仅可极缓推近/拉远/平移。"
    "禁止写人物或任何有生命主体的动作/神态；"
    "禁抽象特效词（光效、光晕、粒子、能量、光圈、脉动、闪电、闪烁、图标、UI元素等）与镜头套话。"
    "正例：丹炉炉盖被蒸汽顶起又落下，缝隙中白烟成股涌出向右飘散，丹炉整体位置与造型保持不变。"
    "反例：小偷手指微微弯曲。（人物肢体动作，禁止）"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT = (
    "【ambient】40-200字，上限 600 字，只写画面内无生命元素微动（光影、纱帘、尘埃、蜡笔屑等），"
    "须写方向、速度、幅度细节；禁人物/有生命体动作；末尾须写「人物姿势保持不变」。"
    "正例：窗边纱帘被风轻轻掀起又落下，窗帘下摆向右飘动约10厘米后回摆，人物姿势保持不变。"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME = (
    "【keyframe】按以下模板输出 motion_prompt（120-280 字）：\n"
    "画面左边是{角色A}，右边是{角色B}。\n"
    "【说话句】必须按本段 dialogue 顺序，每一句台词各写一行"
    "「{该句说话人}说话，同时{微动作}后停止」；"
    "句间格式完全相同，微动作须贴合本镜画面；"
    "同人说多句就要写多行，禁止合并、漏句或打乱对白顺序。"
    "禁止写「后定格」（末句由系统在 TTS 后改为定格）。\n"
    "【站位】左右必须与本段 image_prompt/visual_brief 中"
    "「画面左边是…，右边是…」完全一致，禁止对调。\n"
    "【时间轴】禁止自编起止秒数；写成「{角色}说话，同时…」即可，"
    "出片前系统按 TTS 句时长自动写入「X.X-Y.Y秒」。\n"
    "有台词角色必须含「说话，同时」；无台词角色可不写「说话，同时」，只写微动作。\n"
    "【收束表情】可选。若写，以「两人说话后面部表情恢复与静图一致：」起头；"
    "每位角色的神态须贴合本镜剧情与 visual_brief（如质问、委屈、赌气），"
    "两人可不同，禁止无差别套「无辜状」；第二人可用「表情不变」表相对静图。"
    "若不写收束段，须保证 image_prompt 已定格表情，motion 侧重说话与肢体即可。\n"
    "【锁定】服装发型稳定，身高比例（{角色B}比{角色A}矮半个头）不变。\n"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。\n"
    "禁止镜头推近/推进/拉远/变焦/放大；禁止大位移换位、全身换姿势、多人齐跑、抽象光效。\n"
    "出片前系统按 TTS 将说话句改为「X.X-Y.Y秒左侧女孩/右侧男孩张嘴说话…此时…闭嘴」。\n"
    "正例（dialogue 三句：灿灿→昭昭→灿灿）：\n"
    "画面左边是灿灿，右边是昭昭。"
    "灿灿说话，同时右手食指微微向下点动约2厘米后停止；"
    "昭昭说话，同时肩膀轻轻耸起约3厘米后停止；"
    "灿灿说话，同时下巴微微抬起约1厘米后停止。"
    "两人说话后面部表情恢复与静图一致："
    "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；"
    "昭昭撇着嘴角耸肩（无辜状），表情不变。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。\n"
    "反例：0.0-1.5秒灿灿说话…（禁止自编秒数）；"
    "只写两句说话但 dialogue 有三句（漏句）；"
    "灿灿右手点动持续0.5秒（缺「说话，同时」，系统无法注入时间）。\n"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY = (
    "【motion_prompt 分流】按该段 motion_mode 选择规则："
    "motion_mode=ambient（默认）→"
    + _IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT
    + "motion_mode=keyframe（特写/i2v 关键帧）→"
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

_IMAGE_PROMPTS_JSON_EXAMPLE_DAILY_MOTION = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "motion_prompt": "窗边纱帘被微风掀起下摆向右飘动约10厘米后缓缓回摆，沙发靠垫绒面光影随帘动明暗交替，地毯蜡笔屑被气流吹动向前翻滚半圈停下，人物姿势保持不变"
    },
    {
      "segment_index": 2,
      "motion_prompt": "画面左边是灿灿，右边是昭昭。灿灿说话，同时右手食指微微向下点动约2厘米后停止；昭昭说话，同时肩膀轻轻耸起约3厘米后停止。两人说话后面部表情恢复与静图一致：灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；昭昭撇着嘴角耸肩（委屈不服状），表情不变。服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
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
    CONTENT_STYLE_DAILY_STORY: _IMAGE_PROMPT_RULE_DAILY_STORY_MOTION,
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
    "keyframe 写成「{角色}说话，同时…」微动作并锁住面部表情与静图一致（不微笑），"
    "禁止自编起止秒数（系统按 TTS 注入），"
    "末尾镜头固定不推近不拉远（禁止变焦放大），禁大位移、禁纯环境晃动套话；"
    "各段互不重复，禁止套话。"
)


def _image_prompt_role(content_style: str) -> str:
    return _IMAGE_PROMPT_ROLES.get(
        content_style,
        "你是视频文生图与运动提示词专家。",
    )


def image_prompt_rule(*, orientation: str, content_style: str, sd15_mode: bool = False) -> str:
    """按 content_style / orientation 选择文生图规则；sd15 仅附加，不替换风格正文。"""
    if content_style == CONTENT_STYLE_DAILY_STORY:
        # daily：image_prompt 规则拼装，LLM 只写 motion
        text = (
            "根据每段已拼装的 image_prompt 与口播，仅为 video 编写 motion_prompt。"
            + _with_orientation(_IMAGE_PROMPT_RULE_DAILY_STORY_MOTION, orientation)
            + _IMAGE_PROMPT_MOTION_TAIL_DAILY
        )
        return text
    head = (
        "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
        "和video用的motion_prompt。"
    )
    # tech_science 等未单独列出的风格走电影级写实
    body = _IMAGE_PROMPT_STYLE_BODIES.get(content_style, _IMAGE_PROMPT_RULE_REALISTIC)
    motion = _IMAGE_PROMPT_MOTION_TAIL
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
    include_image_prompt: bool = False,
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
    if include_image_prompt:
        line += f"; image_prompt={seg.get('image_prompt', '')!r}"
    if mark_motion_mode:
        from app.utils.job_info import is_keyframe_segment

        mode = "keyframe" if is_keyframe_segment(seg) else "ambient"
        line += f"; motion_mode={mode}"
        dur = seg.get("duration_sec")
        if dur is not None:
            try:
                line += f"; duration_sec={float(dur):.1f}"
            except (TypeError, ValueError):
                pass
    return line


def _collect_segment_prompt_lines(
    segments: list[dict],
    segment_indices: list[int] | None,
    *,
    include_speakers: bool = False,
    mark_motion_mode: bool = False,
    include_image_prompt: bool = False,
) -> tuple[list[str], set[int] | None]:
    """拼装分镜行；返回 (lines, wanted)。wanted 为 None 表示全量生成。"""
    if segment_indices is None:
        return [
            _format_segment_brief(
                seg,
                include_speakers=include_speakers,
                mark_motion_mode=mark_motion_mode,
                include_image_prompt=include_image_prompt,
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
                include_image_prompt=include_image_prompt,
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
    if content_style == CONTENT_STYLE_DAILY_STORY:
        return (
            "\n\n请仅为每段编写 motion_prompt，不要输出 image_prompt。"
            + _MOTION_USER_RULE_DAILY
        )
    motion_rule = _MOTION_USER_RULE
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
    _ = has_mom  # daily 外貌已在规则拼装；其它风格不再注入妈妈补充例
    is_daily = content_style == CONTENT_STYLE_DAILY_STORY
    if is_daily:
        fields = "、motion_prompt"
        role = "你是儿童日常故事视频运动提示词专家。"
    elif include_sd15_prompt:
        fields = "、image_prompt、motion_prompt 与 sd15_prompt_en"
        role = _image_prompt_role(content_style)
    else:
        fields = "、image_prompt 与 motion_prompt"
        role = _image_prompt_role(content_style)
    parts = [
        f"{role}输出JSON，字段：image_prompts。",
        f"image_prompts为数组，每项含segment_index{fields}。",
        image_prompt_rule(
            orientation=orientation,
            content_style=content_style,
            sd15_mode=include_sd15_prompt and not is_daily,
        ),
    ]
    if include_sd15_prompt and not is_daily:
        parts.append(_SD15_PROMPT_EN_RULE)
    parts.append(_coverage_clause(partial=partial))
    if content_style != CONTENT_STYLE_DAILY_STORY:
        parts.append(_MAP_COMPLIANCE)
    if is_daily:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE_DAILY_MOTION
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
        include_image_prompt=is_daily,
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
