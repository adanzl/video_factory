"""脚本阶段 LLM 提示词构建（生成与预览共用）。"""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.utils.media import NARRATION_CHARS_PER_SEC, default_narration_target_words
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

MIN_IMAGE_PROMPT_CHARS = 300

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（60-120字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
    "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
)

_IMAGE_PROMPT_RULE = (
    "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
    "和video用的motion_prompt。"
    "image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实科普视觉，布光考究、"
    "景深自然、材质细节真实可辨，色彩明快有层次，适配9:16竖屏构图。"
    f"每段image_prompt须350-550字（任何一段不得低于{MIN_IMAGE_PROMPT_CHARS}字），"
    "须按以下六层逐层展开，每层写具体可见细节，禁止一句话带过或空泛形容词："
    "①构图景别（竖屏主体位置与占比、留白、单一视觉焦点）；"
    "②主体动作（主体是谁/何物、姿态、关键互动，或A/B对比并排）；"
    "③场景环境（前景/中景/背景元素、空间纵深、虚化程度）；"
    "④光影材质（主光与辅光方向、高光反光、主体与道具材质质感）；"
    "⑤色彩氛围（主辅色、冷暖对比、情绪基调，须有暖色点缀，忌整体发灰）；"
    "⑥语义边界（仅表达本段text与visual_brief，禁止提前画后续段落内容）。"
    "围绕一个视觉焦点展开，避免要素平铺罗列。"
    "若口播涉及对比（A/B、前后变化），画面须并排展示两种状态，"
    "用箭头、流向线、对勾/叉号等视觉编码辅助说明，禁用可读文字/数字/化学式/水印。"
    "每段motion_prompt须30-80字，描述画面如何运动，如镜头运动（推近/环绕/平移）、"
    "主体运动（旋转/流动/吸附/弹开）、指示动画（箭头延伸/对勾出现/光晕脉动）、"
    "原理可视化（电流流动/板块挤压/细胞分裂），要求自然流畅不突兀。"
    "若无明显运动，写'静态画面，轻微镜头呼吸感'。"
)

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

_SHORT_FORM_STRUCTURE_RULE = (
    "本片为1～2分钟竖屏短科普：只讲一个核心知识点，禁止多点罗列、章节式串讲或「第一第二第三」清单。"
    "第一句须在3秒内抛出反常识疑问、具体现象或悬念（禁止「大家好」「今天我们来聊」类开场）。"
    "正文只展开一层因果或一个机制，不贪多。"
    "结尾用1～2句收束总结；最后一句可轻量引导互动（如「觉得有用就点个赞，我们下期见」），"
    "禁止长篇回顾、禁止清单式连读多届/多段。"
)


def _format_segment_target_sec(target: float) -> str | float:
    return int(target) if target == int(target) else target


def _narration_word_range(target: int) -> tuple[int, int]:
    margin = max(50, int(target * 0.1))
    return max(200, target - margin), target + margin


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
    lo = max(15, int(target * NARRATION_CHARS_PER_SEC * 0.65))
    hi = max(20, int(target * NARRATION_CHARS_PER_SEC))
    return (
        common
        + f"单镜口播上限{sec}秒；每段text约{lo}-{hi}字，单段禁止超过{hi}字；"
        "段数由口播总长与该上限动态决定，按自然断句切分。"
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
) -> dict[str, str]:
    settings = get_settings()
    target = settings.segment_target_sec if segment_target_sec is None else segment_target_sec
    seg_rule = _storyboard_segment_rule(target)
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    narration_word_target = (
        narration_target_words
        if narration_target_words is not None
        else default_narration_target_words(settings)
    )
    narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
    title_rule, title_user_prefix = _title_rule(title, max_title)
    system = (
        "你是给小朋友讲科普的视频编剧。输出JSON，字段：title, narration, word_count, "
        "visual_style, segments。"
        f"{title_rule}"
        f"{seg_rule}"
        f"narration为完整口播，总字数{narration_word_min}-{narration_word_max}（不含空格换行），{_NARRATION_VOICE_RULE}"
        f"{_SHORT_FORM_STRUCTURE_RULE}"
        "结构完整有开头结尾；选题撑不满时可略短，但须结构完整。"
        "禁止口播开头自我介绍或人设铺垫。"
        "各段text须与narration口吻一致。"
        "word_count必须等于narration实际字数，不得虚报。"
        "本步只写口播与画面描述visual_brief，不写image_prompt。"
        f"{_supplementary_system_clause(supplementary_info)}"
    )
    if target > 0:
        sec = _format_segment_target_sec(target)
        split_hint = f"并按单镜口播上限{sec}秒动态切分分镜"
    else:
        split_hint = "并按口播内容逻辑动态切分分镜"
    user = _append_supplementary_to_user(
        (
            f"{title_user_prefix}、visual_style 与分镜，{split_hint}。"
            "每段 visual_brief 写清该镜画面主旨与对比关系，便于下一步扩写文生图提示词。"
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("storyboard", system, user)


def build_image_prompts_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
) -> dict[str, str]:
    segments = script.get("segments") or []
    lines = [
        f"segment {seg['segment_index']}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
        for seg in segments
    ]
    system = (
        "你是科普视频文生图与运动提示词专家。输出JSON，字段：image_prompts。"
        "image_prompts为数组，每项含segment_index、image_prompt与motion_prompt。"
        f"{_IMAGE_PROMPT_RULE}"
        "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"
    )
    user = _append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + "\n\n请为每段扩写 image_prompt 与 motion_prompt，确保 image_prompt 满足字数与六层结构要求。"
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
    else:
        narration_word_target = (
            narration_target_words if narration_target_words is not None else 800
        )
        narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
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
        f"narration 总字数硬性 {narration_word_min}-{narration_word_max} 字（不含空格换行），"
        f"低于 {narration_word_min} 字视为不合格；"
        f"{_MATERIAL_NARRATION_LENGTH_RULE}"
    )
    system = (
        "你是给小朋友讲科普的视频口播编剧。视频画面已由用户上传的基底视频提供，无需描述画面。"
        "输出 JSON，字段：title, narration, word_count, segments。"
        f"{title_rule}"
        f"{length_rule}"
        f"{_NARRATION_VOICE_RULE}"
        f"{opening_rule}"
        f"{segment_rule}"
        "word_count 必须等于 narration 实际字数，禁止虚报。"
        f"{timeline_system_clause(timeline) if timeline else ''}"
        f"{_supplementary_system_clause(supplementary_info)}"
    )
    user_parts = [
        f"{title_user_prefix} narration 与分句 segments。",
        f"口播总字数须在 {narration_word_min}-{narration_word_max} 字之间，至少 {narration_word_min} 字。",
    ]
    if not timeline:
        seg_hint = max(4, narration_word_min // 45)
        per_seg_min = max(25, narration_word_min // seg_hint)
        user_parts.append(
            f"建议切分约 {seg_hint} 段，每段至少 {per_seg_min} 字，"
            f"各段用「感叹+科普点+比喻」三层写法撑满字数。"
        )
    user = _append_supplementary_to_user("\n".join(user_parts), supplementary_info)
    if timeline:
        user = append_timeline_to_user(user, timeline)
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("material_script", system, user)


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
            )
        )
        if script and script.get("segments"):
            prompts.append(build_image_prompts_prompts(script, supplementary_info=extra))

    if script:
        narration = str(script.get("narration") or "")
        if (
            not skip_title_optimize
            and (script.get("draft_title") or narration)
        ):
            draft = str(script.get("draft_title") or script.get("title") or "")
            if draft and narration:
                prompts.append(
                    build_title_optimize_prompts(
                        draft,
                        narration,
                        max_title_length=max_title_length,
                    )
                )
        title_for_desc = str(script.get("title") or title or "")
        if title_for_desc and narration:
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
