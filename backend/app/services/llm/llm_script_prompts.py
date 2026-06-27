"""脚本阶段 LLM 提示词构建（生成与预览共用）。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.utils.job_info import (
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    content_style_from_job,
    orientation_for_resolve,
)
from app.utils.media import (
    NARRATION_WRITING_TARGET_RATIO,
    default_narration_target_words,
    min_narration_chars_for_target,
    narration_accept_min_chars,
    narration_writing_plan,
    narration_writing_target_chars,
    segment_text_char_cap,
)
from app.services.llm.llm_script_timeline import (
    VideoTimeline,
    append_timeline_to_user,
    narration_range_for_timeline,
    parse_video_timeline,
    timeline_system_clause,
)
from app.services.llm.llm_script_description import (
    build_video_description_system_prompt,
    build_video_description_user_prompt,
)
from app.services.llm.llm_script_title import (
    build_title_optimize_system_prompt,
    build_title_optimize_user_prompt,
)

MIN_IMAGE_PROMPT_CHARS = 200
IMAGE_PROMPT_TARGET_CHARS = 300
MIN_IMAGE_PROMPT_CHARS_SD15 = 30
IMAGE_PROMPT_TARGET_CHARS_SD15 = 80
MIN_SD15_PROMPT_EN_WORDS = 8
TARGET_SD15_PROMPT_EN_WORDS = 12


def image_prompt_min_chars(*, sd15_mode: bool = False) -> int:
    return MIN_IMAGE_PROMPT_CHARS_SD15 if sd15_mode else MIN_IMAGE_PROMPT_CHARS


def image_prompt_target_chars(*, sd15_mode: bool = False) -> int:
    return IMAGE_PROMPT_TARGET_CHARS_SD15 if sd15_mode else IMAGE_PROMPT_TARGET_CHARS


def sd15_prompt_en_word_count(value: object) -> int:
    if not isinstance(value, str):
        return 0
    text = value.strip()
    if not text:
        return 0
    return len(text.split())


def sd15_prompt_en_ok(value: object) -> bool:
    return sd15_prompt_en_word_count(value) >= MIN_SD15_PROMPT_EN_WORDS


def image_prompt_threshold_label(*, sd15_mode: bool = False) -> str:
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    label = f"image_prompt>={min_chars}chars(target{target_chars})"
    if sd15_mode:
        label += (
            f" sd15_prompt_en>={MIN_SD15_PROMPT_EN_WORDS}words"
            f"(target{TARGET_SD15_PROMPT_EN_WORDS})"
        )
    return label


def format_image_prompt_retry_segments(segments: list[dict]) -> str:
    parts: list[str] = []
    for item in segments:
        idx = item.get("segment_index")
        metrics: list[str] = []
        if "chars" in item:
            metrics.append(f"{item['chars']}chars")
        if "words" in item:
            metrics.append(f"{item['words']}words")
        if metrics:
            parts.append(f"#{idx}({','.join(metrics)})")
        else:
            parts.append(f"#{idx}")
    return ", ".join(parts)


def format_image_prompt_retry_warning(
    *,
    attempt: int,
    reason: str,
    segments: list[dict],
    sd15_mode: bool = False,
) -> str:
    return (
        f"[SCRIPT] image_prompt retry attempt={attempt} reason={reason} "
        f"threshold={image_prompt_threshold_label(sd15_mode=sd15_mode)} "
        f"segments=[{format_image_prompt_retry_segments(segments)}]"
    )

# DeepSeek JSON Output 要求 prompt 含 json 字样并给出样例：
# https://api-docs.deepseek.com/zh-cn/guides/json_mode
_STORYBOARD_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "第一段口播正文写满本镜预算，用具体细节撑开，禁止一句带过。第二段口播同样写满本镜字数下限，补案例或步骤后再进入下一段。",
  "word_count": 68,
  "visual_style": "画风定调一句话",
  "segments": [
    {
      "segment_index": 1,
      "text": "第一段口播正文写满本镜预算，用具体细节撑开，禁止一句带过。",
      "visual_brief": "画面主旨描述",
      "visual_mode": "static_motion"
    },
    {
      "segment_index": 2,
      "text": "第二段口播同样写满本镜字数下限，补案例或步骤后再进入下一段。",
      "visual_brief": "画面主旨描述",
      "visual_mode": "static_motion"
    }
  ]
}"""

_STORYBOARD_JSON_EXAMPLE_COMPACT = """{
  "title": "标题示例",
  "visual_style": "画风定调一句话",
  "segments": [
    {
      "segment_index": 1,
      "text": "第一段口播正文写满本镜预算，用具体细节撑开，禁止一句带过。",
      "visual_brief": "画面主旨",
      "visual_mode": "static_motion"
    },
    {
      "segment_index": 2,
      "text": "第二段口播同样写满本镜字数下限，补案例或步骤后再进入下一段。",
      "visual_brief": "画面主旨",
      "visual_mode": "static_motion"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": "六层结构扩写...",
      "motion_prompt": "轻微镜头推进",
      "sd15_prompt_en": "cross-section diagram of lung alveoli, air sacs highlighted, medical illustration"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15 = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": "六层结构扩写...",
      "motion_prompt": "轻微镜头推进"
    }
  ]
}"""

_MATERIAL_SCRIPT_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "第一句口播写满本句预算，用具体细节撑开。第二句口播同样写满，补比喻或拟声后再接下一句。",
  "word_count": 42,
  "segments": [
    {"segment_index": 1, "text": "第一句口播写满本句预算，用具体细节撑开。"},
    {"segment_index": 2, "text": "第二句口播同样写满，补比喻或拟声后再接下一句。"}
  ]
}"""


def _json_output_clause(example: str) -> str:
    return (
        "请仅输出合法 JSON 对象（不要 markdown 代码块，不要解释文字）。"
        "JSON 输出样例（字段名须一致，内容为示意）：\n"
        f"{example}\n"
    )

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（80-150字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
    "visual_brief末尾须用括号标注SD15画面类型（五选一）："
    "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图）。"
    "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
)

_IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实科普视觉，布光考究、"
    "景深自然、材质细节真实可辨，色彩明快有层次，适配9:16竖屏构图。"
    f"每段image_prompt建议350-550字（任何一段不得低于{MIN_IMAGE_PROMPT_CHARS}字），"
    "须按以下六层逐层展开，每层写具体可见细节，禁止一句话带过或空泛形容词："
    "①构图景别（竖屏主体位置与占比、留白、单一视觉焦点）；"
    "②主体动作（主体是谁/何物、姿态、关键互动，或A/B对比并排）；"
    "③场景环境（前景/中景/背景元素、空间纵深、虚化程度）；"
    "④光影材质（主光与辅光方向、高光反光、主体与道具材质质感）；"
    "⑤色彩氛围（主辅色、冷暖对比、情绪基调，须有暖色点缀，忌整体发灰）；"
    "⑥语义边界（仅表达本段text与visual_brief，禁止提前画后续段落内容）。"
)

_IMAGE_PROMPT_RULE_LIFE_LANDSCAPE = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：生活Vlog质感写实画面，"
    "自然光或室内暖光、浅景深、色彩真实不过度滤镜，适配16:9横屏构图。"
    f"每段image_prompt建议350-550字（任何一段不得低于{MIN_IMAGE_PROMPT_CHARS}字），"
    "须按以下六层逐层展开："
    "①构图景别（横屏主体位置、环境留白、生活场景真实感）；"
    "②人物/物品动作（具体在做什么、与口播步骤对应）；"
    "③场景环境（家居/办公/户外等可识别生活空间）；"
    "④光影材质（自然窗光、桌面材质、屏幕/文档等细节）；"
    "⑤色彩氛围（温暖日常、不过度饱和）；"
    "⑥语义边界（仅表达本段text与visual_brief，禁止可读大段文字/水印/品牌Logo）。"
)

_IMAGE_PROMPT_MOTION_TAIL = (
    "围绕一个视觉焦点展开，避免要素平铺罗列。"
    "每段motion_prompt须30-80字，描述画面如何运动；优先「镜头固定」或「极轻微缓慢推进/拉远」，"
    "禁止快速运镜、跟拍、环绕、甩镜等易产生抖动的描述。"
    "若无明显运动，写「镜头固定，主体稳定，画面平滑」。"
)


_IMAGE_PROMPT_RULE_SD15_SHORT = (
    "image_prompt为该镜画面的简短中文描述（80-120字）："
    "写清主体是什么、在做什么、场景类型，供质检和前端展示用；"
    "无需六层扩写，禁止堆砌光影材质细节。"
)


def _image_prompt_rule(*, orientation: str, content_style: str, sd15_mode: bool = False) -> str:
    head = (
        "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
        "和video用的motion_prompt。"
    )
    if sd15_mode:
        return head + _IMAGE_PROMPT_RULE_SD15_SHORT + _IMAGE_PROMPT_MOTION_TAIL
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        body = _IMAGE_PROMPT_RULE_LIFE_LANDSCAPE
    elif orientation == ORIENTATION_LANDSCAPE:
        body = _IMAGE_PROMPT_RULE_LIFE_LANDSCAPE.replace(
            "生活Vlog质感写实画面",
            "电影级写实视觉",
        )
    else:
        body = _IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT
    return head + body + _IMAGE_PROMPT_MOTION_TAIL


_STEP_LABELS = {
    "storyboard": "口播分镜",
    "image_prompts": "文生图提示词",
    "material_script": "口播文案",
    "title_optimize": "标题优化",
    "video_description": "视频介绍",
}

_NARRATION_VOICE_RULE = (
    "口播口吻须像一个小孩子在讲给同伴听：略带稚嫩、天真，有一点童趣；"
    "可用「哇」「你看」「原来是这样呀」等儿童感感叹，句子偏短、好懂；"
    "偶尔用拟声词或简单比喻（像积木、像气球那样），但不要装婴儿语、不要刻意错别字；"
    "科普事实须准确，童趣服务于理解，不牺牲科学内容。"
)

_MATERIAL_NARRATION_LENGTH_RULE = (
    "【撑满字数的写法】每段口播须含三层——"
    "①童趣感叹或「你看」式互动；②一个准确科普点；③比喻/拟声/生活联想。"
    "禁止整段仅一句短感叹（如「哇，好厉害呀」）。"
    "【生成顺序】先逐段写满 segments，再原样拼接为 narration，最后统计 word_count；"
    "若未达字数下限，须当场扩写后再输出 JSON，禁止先输出再指望后处理。"
)

_LIFE_NARRATION_VOICE_RULE = (
    "口播口吻须像B站生活避坑/经验科普讲解：客观、口语化、像在帮观众纠错；"
    "优先用「很多人以为…其实…」「正确做法是…」「常见误区是…」；"
    "禁止整篇伪装成某一职业的亲历者（矿工、医生、司机等），禁止编造「我当时在一线」类故事。"
)

_LIFE_NARRATION_LENGTH_RULE = (
    "【撑满字数的写法】每段口播须含三层——"
    "①常见误区或错误做法；②原因/风险（为什么错）；③正确步骤或可操作结论。"
    "禁止整段仅一句空泛感叹；禁止用长篇第一人称回忆录凑字数。"
    "【生成顺序】先逐段写满 segments，再原样拼接为 narration，最后统计 word_count；"
    "若未达字数下限，须当场扩写后再输出 JSON，禁止先输出再指望后处理。"
)

_LIFE_EXPERIENCE_STRUCTURE_RULE = (
    "本片为生活避坑/经验科普：只围绕一个明确主题（避坑/流程/工具/选择），"
    "禁止多点罗列成「十条技巧」清单，禁止抖音式伪亲历回忆录。"
    "开头30秒内点明「大家常踩的坑是什么、这条视频纠正什么误区」，"
    "禁止「我当XX时」「跟班长在XX干活」等编造一线故事开场。"
    "正文按「误区→为什么错→正确做法→注意事项」展开；"
    "举例最多1句泛化案例（如「有人曾…差点…」），不得通篇第一人称扮演从业者。"
    "结尾给1条可行动建议 + 轻量互动，禁止「我一生都忘不了」类煽情收束。"
)

# 全风格口播禁用：伪亲历/职业角色扮演（生活区误区视频高发）
_NARRATION_ANTI_MEMOIR_RULE = (
    "【禁止伪亲历体】不得出现：「我当…时」「我在…干活/下井/上班」「老XX教我」"
    "「班长拉着我跑」「我条件反射」「我后来查资料才知道」「评论区聊聊你平时怎么做」"
    "等编造第一人称从业经历或互动话术；"
    "不得扮演矿工、医护、司机等具体职业身份；"
    "用第三人称或泛化「很多人/有些老说法」讲清误区与正确步骤即可。"
)

_SHORT_FORM_STRUCTURE_RULE = (
    "本片为1～2分钟竖屏短科普：只讲一个核心知识点，禁止多点罗列、章节式串讲或「第一第二第三」清单。"
    "第一句须在3秒内抛出反常识疑问、具体现象或悬念（禁止「大家好」「今天我们来聊」类开场）。"
    "正文只展开一层因果或一个机制，不贪多。"
    "结尾用1～2句收束总结；最后一句可轻量引导互动（如「觉得有用就点个赞，我们下期见」），"
    "禁止长篇回顾、禁止清单式连读多届/多段。"
)


def _format_segment_target_sec(target: float) -> str | float:
    return int(target) if target == int(target) else target


def _resolve_script_profile(
    job: dict | None,
    *,
    orientation: str | None = None,
    content_style: str | None = None,
) -> tuple[str, str]:
    resolved_orientation = orientation or (
        orientation_for_resolve(job) if job else None
    ) or ORIENTATION_PORTRAIT
    resolved_style = content_style or (
        content_style_from_job(job) if job else CONTENT_STYLE_SCIENCE_CHILD
    )
    return resolved_orientation, resolved_style


def _narration_voice_rule(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_NARRATION_VOICE_RULE
    return _NARRATION_VOICE_RULE


def _narration_length_rule(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_NARRATION_LENGTH_RULE
    return _MATERIAL_NARRATION_LENGTH_RULE


def _structure_rule(*, orientation: str, content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_EXPERIENCE_STRUCTURE_RULE
    return _SHORT_FORM_STRUCTURE_RULE


def _storyboard_role(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return "你是B站生活避坑/经验科普的内容编剧。"
    return "你是给小朋友讲科普的视频编剧。"


def _narration_word_range(target: int) -> tuple[int, int]:
    """口播字数区间：下限与验收阈值一致，上限为目标 + 余量。"""
    margin = max(50, int(target * 0.1))
    accept_min = narration_accept_min_chars(target)
    return accept_min, target + margin


def _writing_target_clause(narration_target: int) -> str:
    writing_target = narration_writing_target_chars(narration_target)
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    return (
        f"必须达到 {writing_target} 字（总目标 {narration_target} 字的 {pct}%），"
        f"不要只按验收下限凑字数"
    )


def _storyboard_length_budget(
    *,
    narration_target: int,
    segment_target_sec: float,
    content_style: str,
) -> str:
    plan = narration_writing_plan(narration_target, segment_target_sec)
    hard_min = plan["hard_min"]
    writing_target = plan["writing_target"]
    seg_count = plan["seg_count_min"]
    per_min = plan["per_seg_min"]
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    layers = (
        "误区+原因+正确做法"
        if content_style == CONTENT_STYLE_LIFE_EXPERIENCE
        else "感叹+科普点+比喻/拟声"
    )
    if segment_target_sec <= 0:
        return (
            f"【字数预算】总目标 {narration_target} 字；"
            f"写作必须达到 {writing_target} 字（总目标的 {pct}%）；"
            f"验收下限 {hard_min} 字（低于即不合格）。\n"
            f"须至少 {seg_count} 个 segments，每段至少 {per_min} 字；"
            f"各段 text 字数之和须 ≥ {writing_target}。\n"
            f"每段用「{layers}」三层写法撑满，禁止整段一句带过。\n"
            "【生成顺序】先按预算写满各段 segments，再拼接 narration，最后核对 word_count。\n"
            f"【输出前自检】segments 数量 ≥ {seg_count}；各段 text 字数之和 ≥ {writing_target}；"
            "word_count 等于 narration 实际字数。"
        )
    cap = plan["segment_cap"]
    hard_cap = int(cap * 1.15)
    per_target_lo = plan["per_seg_lo"]
    per_target_hi = plan["per_seg_hi"]
    sum_floor = per_min * seg_count
    sec = int(segment_target_sec) if segment_target_sec == int(segment_target_sec) else segment_target_sec
    return (
        f"【字数预算】总目标 {narration_target} 字；"
        f"写作必须达到 {writing_target} 字（总目标的 {pct}%）；"
        f"验收下限 {hard_min} 字（低于即不合格）。\n"
        f"单镜上限 {sec}s，每段 text 上限 {cap} 字（绝对不得超过 {hard_cap} 字，超限即不合格）。\n"
        f"须至少 {seg_count} 个 segments（{writing_target} 字 ÷ {cap} 字/段），"
        f"每段 {per_target_lo}-{per_target_hi} 字、下限 {per_min} 字；"
        f"各段下限之和约 {sum_floor} 字（须达到写作目标 {writing_target}）。\n"
        f"禁止用 3～5 个长段堆叠口播，必须按单镜上限拆段。\n"
        f"每段用「{layers}」三层写法撑满，禁止整段一句带过。\n"
        "【生成顺序】先规划段数与每段字数，再写满 segments，再拼接 narration，最后核对 word_count。\n"
        f"【输出前自检】segments 数量 ≥ {seg_count}；各段 text 字数之和 ≥ {writing_target}；"
        "word_count 等于 narration 实际字数。"
    )


def _storyboard_length_system_clause(
    *,
    narration_target: int,
    segment_target_sec: float,
    compact_output: bool,
) -> str:
    plan = narration_writing_plan(narration_target, segment_target_sec)
    seg_count = plan["seg_count_min"]
    hard_min = plan["hard_min"]
    writing_target = plan["writing_target"]
    per_min = plan["per_seg_min"]
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    if compact_output:
        return (
            f"segments 数组长度必须 ≥ {seg_count}；"
            f"各段 text 须写满（每段至少 {per_min} 字），后端会拼接为 narration；"
            f"拼接后总字数须 ≥ {writing_target} 字（总目标 {narration_target} 字的 {pct}%）。"
        )
    return (
        f"segments 数组长度必须 ≥ {seg_count}；"
        f"各段 text 按顺序拼接须与 narration 完全一致；"
        f"narration 须达到 {writing_target} 字（总目标 {narration_target} 字的 {pct}%，"
        f"验收下限 {hard_min} 字）。"
    )


def _append_supplementary_to_user(user: str, supplementary_info: str | None) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return user
    return (
        f"{user}\n\n"
        "用户补充信息（须合理融入口播与分镜，勿编造与补充信息矛盾的内容；"
        "若与科普常识冲突，以科学事实为准）：\n"
        f"{extra}"
    )


def _supplementary_system_clause(supplementary_info: str | None) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return ""
    return (
        "用户会提供补充信息：须融入口播内容与表达风格，"
        "但不得与画面时间表冲突；若冲突以时间表为准。"
    )


def _resolve_video_timeline(
    video_timeline: str | None,
    *,
    script: dict | None = None,
) -> VideoTimeline | None:
    raw = (video_timeline or "").strip()
    if not raw and script:
        saved = script.get("video_timeline")
        if isinstance(saved, str) and saved.strip():
            raw = saved.strip()
    return parse_video_timeline(raw) if raw else None


def _title_rule(title: str, max_title: int) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_title:
        return (
            f"title 必须与原标题完全一致：{cleaned}，不要改写、精简或替换。",
            f"原标题：{title}\n请输出 title（与原标题一致）、完整口播",
        )
    return (
        f"title 为精简视频标题，保留原标题核心意思，不含空格换行，字数不超过 {max_title}。",
        f"原标题：{title}\n请输出精简 title（≤{max_title}字）、完整口播",
    )


def _storyboard_segment_rule(target: float) -> str:
    common = f"segments为分镜数组；{_VISUAL_BRIEF_RULE}"
    if target <= 0:
        return common + "不约束单镜时长，按口播内容逻辑切分，段数由内容决定。"
    sec = _format_segment_target_sec(target)
    cap = segment_text_char_cap(target)
    hard_cap = int(cap * 1.15)
    lo = max(15, int(cap * 0.65))
    return (
        common
        + f"单镜口播上限{sec}秒；每段text约{lo}-{cap}字，单段绝对不得超过{hard_cap}字；"
        "段数=口播总字数÷单段上限（向上取整），按自然断句切分，禁止少数长段堆叠。"
    )


def _prompt_step(step: str, system: str, user: str) -> dict[str, str]:
    return {
        "step": step,
        "label": _STEP_LABELS.get(step, step),
        "system": system,
        "user": user,
    }


def build_storyboard_prompts(
    title: str,
    *,
    feedback: str | None = None,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    compact_output: bool = False,
) -> dict[str, str]:
    settings = get_settings()
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    target = settings.segment_target_sec if segment_target_sec is None else segment_target_sec
    seg_rule = _storyboard_segment_rule(target)
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    narration_word_target = (
        narration_target_words
        if narration_target_words is not None
        else default_narration_target_words(settings)
    )
    narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
    narration_hard_min = narration_word_min
    title_rule, title_user_prefix = _title_rule(title, max_title)
    length_rule = (
        f"口播总目标 {narration_word_target} 字；{_writing_target_clause(narration_word_target)}；"
        f"验收下限 {narration_hard_min} 字、上限 {narration_word_max} 字（不含空格换行）；"
        f"低于 {narration_hard_min} 字视为不合格；"
        f"{_narration_length_rule(profile_style)}"
    )
    length_system = _storyboard_length_system_clause(
        narration_target=narration_word_target,
        segment_target_sec=target,
        compact_output=compact_output,
    )
    if compact_output:
        json_fields = "title, visual_style, segments"
        narration_clause = (
            "【紧凑输出】不要输出 narration 与 word_count 字段；"
            "各段 text 须按字数预算写满，后端会自动拼接为 narration。"
            "每段 visual_brief 控制在 30-60 字，只写画面主旨，末尾用括号注明画面类型"
            "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图），禁止冗长描写。"
        )
        word_count_clause = ""
    else:
        json_fields = "title, narration, word_count, visual_style, segments"
        narration_clause = ""
        word_count_clause = "word_count必须等于narration实际字数，不得虚报。"
    system = (
        f"{_storyboard_role(profile_style)}输出JSON，字段：{json_fields}。"
        f"{title_rule}"
        f"{seg_rule}"
        f"{length_rule}"
        f"{length_system}"
        f"{narration_clause}"
        f"narration口吻：{_narration_voice_rule(profile_style)}"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
        f"{_structure_rule(orientation=profile_orientation, content_style=profile_style)}"
        "结构完整有开头结尾。"
        "禁止口播开头空泛自我介绍或冗长人设铺垫。"
        "各段text须与narration口吻一致。"
        f"{word_count_clause}"
        "本步只写口播与画面描述visual_brief，不写image_prompt。"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_STORYBOARD_JSON_EXAMPLE_COMPACT if compact_output else _STORYBOARD_JSON_EXAMPLE)}"
    )
    if target > 0:
        sec = _format_segment_target_sec(target)
        split_hint = f"并按单镜口播上限{sec}秒动态切分分镜"
    else:
        split_hint = "并按口播内容逻辑动态切分分镜"
    length_budget = _storyboard_length_budget(
        narration_target=narration_word_target,
        segment_target_sec=target,
        content_style=profile_style,
    )
    user = _append_supplementary_to_user(
        (
            f"{title_user_prefix}、visual_style 与分镜，{split_hint}。\n\n"
            f"{length_budget}\n\n"
            + (
                "每段 visual_brief 30-60 字，写清画面主旨，末尾用括号注明画面类型（写实场景/结构示意图/对比图/线稿解剖图/微观分子图）。"
                if compact_output
                else "每段 visual_brief 写清该镜画面主旨并在末尾注明画面类型（写实场景/结构示意图/对比图/线稿解剖图/微观分子图），便于下一步扩写文生图提示词。"
            )
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("storyboard", system, user)


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


def build_image_prompts_prompts(
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
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    if segment_indices is not None:
        wanted = {int(idx) for idx in segment_indices}
        segments = [seg for seg in segments if int(seg.get("segment_index", -1)) in wanted]
    lines = [
        f"segment {seg['segment_index']}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
        for seg in segments
    ]
    json_example = _IMAGE_PROMPTS_JSON_EXAMPLE if include_sd15_prompt else _IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15
    sd15_rule = _SD15_PROMPT_EN_RULE if include_sd15_prompt else ""
    sd15_fields = "、image_prompt、motion_prompt 与 sd15_prompt_en" if include_sd15_prompt else "、image_prompt 与 motion_prompt"
    system = (
        f"你是科普视频文生图与运动提示词专家。输出JSON，字段：image_prompts。"
        f"image_prompts为数组，每项含segment_index{sd15_fields}。"
        f"{_image_prompt_rule(orientation=profile_orientation, content_style=profile_style, sd15_mode=include_sd15_prompt)}"
        f"{sd15_rule}"
        "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"
        f"{_json_output_clause(json_example)}"
    )
    user = _append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + "\n\n请为每段扩写 image_prompt 与 motion_prompt，确保 image_prompt 满足字数与六层结构要求。"
            + ("同时为每段输出准确的 sd15_prompt_en。" if include_sd15_prompt else "")
        ),
        supplementary_info or script.get("supplementary_info"),
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("image_prompts", system, user)


def build_material_script_prompts(
    title: str,
    *,
    feedback: str | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    script: dict | None = None,
) -> dict[str, str]:
    settings = get_settings()
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    timeline = _resolve_video_timeline(video_timeline, script=script)
    if timeline:
        narration_word_min, narration_word_max = narration_range_for_timeline(timeline)
        narration_hard_min = narration_word_min
        narration_word_target = (narration_word_min + narration_word_max) // 2
    else:
        narration_word_target = (
            narration_target_words if narration_target_words is not None else 800
        )
        narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
        narration_hard_min = narration_word_min
    title_rule, title_user_prefix = _title_rule(title, max_title)
    segment_rule = (
        f"segments 必须恰好 {len(timeline.slots)} 条，与画面时间表逐段一一对应；"
        "每项含 segment_index 与 text，第 i 段只讲第 i 段画面；"
        "各段 text 按顺序拼接须与 narration 完全一致，口吻同样保持童趣。"
        if timeline
        else (
            "segments 为分句数组，每项含 segment_index 与 text；"
            "各段 text 按顺序拼接须与 narration 完全一致，口吻同样保持童趣；"
            "按自然断句切分，无需 visual 字段。"
        )
    )
    opening_rule = (
        "禁止开场钩子、悬念反问、自我介绍或全片总起；"
        "narration 第一句必须从时间表第 1 段画面内容直接讲起。"
        if timeline
        else "禁止开头自我介绍；第一句直接进入主题。"
    )
    length_rule = (
        f"narration 总目标 {narration_word_target} 字；{_writing_target_clause(narration_word_target)}；"
        f"验收下限 {narration_hard_min} 字、上限 {narration_word_max} 字（不含空格换行）；"
        f"低于 {narration_hard_min} 字视为不合格；"
        f"{_MATERIAL_NARRATION_LENGTH_RULE}"
    )
    system = (
        "你是给小朋友讲科普的视频口播编剧。视频画面已由用户上传的基底视频提供，无需描述画面。"
        "输出 JSON，字段：title, narration, word_count, segments。"
        f"{title_rule}"
        f"{length_rule}"
        f"{_NARRATION_VOICE_RULE}"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
        f"{opening_rule}"
        f"{segment_rule}"
        "word_count 必须等于 narration 实际字数，禁止虚报。"
        f"{timeline_system_clause(timeline) if timeline else ''}"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_MATERIAL_SCRIPT_JSON_EXAMPLE)}"
    )
    user_parts = [
        f"{title_user_prefix} narration 与分句 segments。",
    ]
    if not timeline:
        user_parts.append(
            _storyboard_length_budget(
                narration_target=narration_word_target,
                segment_target_sec=0,
                content_style=CONTENT_STYLE_SCIENCE_CHILD,
            )
        )
    user = _append_supplementary_to_user("\n\n".join(user_parts), supplementary_info)
    if timeline:
        user = append_timeline_to_user(user, timeline)
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("material_script", system, user)


def build_narration_expand_prompts(
    script: dict[str, Any],
    *,
    min_chars: int,
    mode: str = "storyboard",
) -> dict[str, str]:
    """在初稿字数不足时专用扩写（保留分镜与画面字段）。"""
    current = _narration_char_count_for_prompt(str(script.get("narration") or ""))
    deficit = max(1, min_chars - current)
    keep_visual = mode == "storyboard"
    system = (
        "你是口播扩写编辑。用户在初稿字数不足，须在保持主题与分镜结构的前提下扩写。"
        "输出 JSON，字段与输入一致（title, narration, word_count, segments"
        + (", visual_style" if keep_visual else "")
        + "）。"
        f"扩写后 narration 须至少 {min_chars} 字（不含空格换行），当前仅 {current} 字，还差约 {deficit} 字。"
        "规则：segments 段数与 segment_index 不得减少、不得合并；"
        "每段 text 只能扩写（补具体细节、案例、步骤或结论），禁止删减已有核心信息；"
        "narration 为各段 text 按顺序原样拼接；word_count 等于 narration 实际字数。"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
    )
    if keep_visual:
        system += (
            "须保留 visual_style 与各段 visual_brief，仅扩写 text；"
            "禁止删除 visual_brief 或改成空字符串。"
        )
        system += _json_output_clause(_STORYBOARD_JSON_EXAMPLE)
    else:
        system += _json_output_clause(_MATERIAL_SCRIPT_JSON_EXAMPLE)
    draft = {
        "title": script.get("title"),
        "narration": script.get("narration"),
        "word_count": script.get("word_count"),
        "segments": script.get("segments"),
    }
    if keep_visual:
        draft["visual_style"] = script.get("visual_style")
    user = (
        "当前稿件（字数不足，请扩写）：\n"
        f"{json.dumps(draft, ensure_ascii=False)}\n\n"
        f"请扩写至至少 {min_chars} 字后输出完整 JSON。"
    )
    return _prompt_step(f"expand_{mode}", system, user)


def _narration_char_count_for_prompt(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def build_title_optimize_prompts(
    draft_title: str,
    narration: str,
    *,
    max_title_length: int | None = None,
) -> dict[str, str]:
    settings = get_settings()
    max_len = settings.max_title_length if max_title_length is None else max_title_length
    system = build_title_optimize_system_prompt(max_title_len=max_len)
    user = build_title_optimize_user_prompt(
        draft_title=draft_title,
        narration=narration,
        max_title_len=max_len,
    )
    return _prompt_step("title_optimize", system, user)


def build_video_description_prompts(
    title: str,
    narration: str,
) -> dict[str, str]:
    system = build_video_description_system_prompt()
    user = build_video_description_user_prompt(title=title, narration=narration)
    return _prompt_step("video_description", system, user)


def _is_material_job(job: dict) -> bool:
    return job.get("pipeline") == "material"


def collect_script_prompts(
    job: dict,
    title: str,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    script: dict | None = None,
    skip_title_optimize: bool = False,
    preview_followups: bool = False,
) -> list[dict[str, str]]:
    """收集脚本阶段 LLM 提示词；script 为空时仅返回可预览的首步。"""
    extra = (supplementary_info or "").strip() or None
    if extra is None and script:
        saved = script.get("supplementary_info")
        if isinstance(saved, str) and saved.strip():
            extra = saved.strip()
    timeline_raw = (video_timeline or "").strip() or None
    if timeline_raw is None and script:
        saved_timeline = script.get("video_timeline")
        if isinstance(saved_timeline, str) and saved_timeline.strip():
            timeline_raw = saved_timeline.strip()
    prompts: list[dict[str, str]] = []
    if _is_material_job(job):
        prompts.append(
            build_material_script_prompts(
                title,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=extra,
                video_timeline=timeline_raw,
                script=script,
            )
        )
    else:
        prompts.append(
            build_storyboard_prompts(
                title,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=extra,
                job=job,
            )
        )
        if script and script.get("segments"):
            prompts.append(
                build_image_prompts_prompts(script, supplementary_info=extra, job=job)
            )

    narration = ""
    draft_title = re.sub(r"\s+", "", title.strip())
    title_for_desc = draft_title
    if script and isinstance(script, dict):
        narration = str(script.get("narration") or "").strip()
        draft_title = re.sub(
            r"\s+",
            "",
            str(script.get("draft_title") or script.get("title") or draft_title).strip(),
        )
        title_for_desc = str(script.get("title") or title or "").strip()

    if preview_followups and not narration:
        narration = "（口播分镜生成后将填入实际 narration，此处仅预览提示词结构）"

    if narration and not skip_title_optimize and draft_title:
        prompts.append(
            build_title_optimize_prompts(
                draft_title,
                narration,
                max_title_length=max_title_length,
            )
        )
    if narration and title_for_desc:
        prompts.append(build_video_description_prompts(title_for_desc, narration))
    return prompts


def attach_llm_prompts_to_script(
    script: dict,
    job: dict,
    title: str,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    skip_title_optimize: bool = False,
) -> None:
    script["llm_prompts"] = collect_script_prompts(
        job,
        title,
        segment_target_sec=segment_target_sec,
        max_title_length=max_title_length,
        narration_target_words=narration_target_words,
        supplementary_info=supplementary_info,
        video_timeline=video_timeline,
        script=script,
        skip_title_optimize=skip_title_optimize,
    )
