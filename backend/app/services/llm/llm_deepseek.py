from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import gevent
import gevent.pool

from app.config import get_settings
from app.exceptions import JobStageFailureError
from app.services.llm.llm_mgr import LLMClient
from app.services.script.description import (
    build_video_description_prompts,
    parse_video_description_payload,
)
from app.services.script.tags import (
    build_tags_prompts,
    parse_tags_payload,
)
from app.quality.image_prompt import MIN_IMAGE_PROMPT_CHARS, IMAGE_PROMPT_TARGET_CHARS
from app.services.script.image_prompt import build_image_prompts
from app.services.script.segment_split import apply_segments_from_voiceover
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_material import build_voiceover_material_prompts
from app.services.script.voiceover_standard import (
    build_voiceover_standard_expand_prompts,
    build_voiceover_standard_prompts,
    build_voiceover_standard_shrink_prompts,
)
from app.services.script.optimize_title import (
    build_title_optimize_prompts,
    parse_title_optimize_payload,
)
from app.services.script.board_timeline import narration_range_for_timeline, parse_video_timeline
from app.services.topic.parsers import (
    format_topic_parse_feedback,
    is_topic_parse_retryable,
    parse_topics_payload,
)
from app.services.topic.prompts.builder import (
    build_topic_system_prompt,
    build_topic_user_prompt,
)
from app.services.daily_story.prompts import (
    DAILY_STORY_CHARACTERS,
    DAILY_STORY_CHARACTER_MOM,
    _correct_dialogue_speaker,
    _select_story_type,
    build_daily_script_prompts,
    build_daily_story_framework_prompts,
    build_daily_story_opening_prompts,
    build_daily_story_prompts,
    build_daily_story_retry_user,
    build_daily_story_opening_retry_user,
    build_daily_story_theme_prompts,
    enforce_daily_script_closeups,
    opening_avoid_speaker_from_body,
    validate_daily_script_scenes,
    resolve_daily_story_retry_length_mode,
    stitch_daily_story_opening,
    validate_daily_story_json,
    validate_daily_story_opening,
)
from app.utils.job_cancel import raise_if_job_cancelled
from app.utils.media import (
    DEFAULT_SPEECH_CHARS_PER_SEC,
    default_narration_target_words,
    min_narration_chars_for_target,
    narration_accept_max_chars,
    narration_accept_min_chars,
    segment_text_char_cap,
)

__all__ = ["DeepSeekClient", "MIN_IMAGE_PROMPT_CHARS"]

logger = logging.getLogger(__name__)

_NARRATION_EXPAND_ATTEMPTS = 2
_TRUNCATION_RETRY_ATTEMPTS = 3

# 硬关 thinking 时的温度：越大越野。走配置（开 thinking）时勿传。
# D2 重试 / D2b 开场走配置 thinking，不传 temperature。
_TEMP_CREATIVE_HIGH = 0.95  # D1/D2 首稿
_TEMP_CREATIVE_BLUEPRINT = 1.0  # D1.5 有骨架时的 D2 首稿
_TEMP_CREATIVE_MID = 0.8  # A2/C/D4/E1
_TEMP_UTILITY = 0.5  # E2/E3/E4/封面
_TEMP_CRITERION_LOCKED = 0.4  # C 类台词锚定注入生效时的正文温度（专家定：降温度提遵从）

# C 类判据链（2026-08-09 专家死磕重设计）：从「2 句固定台词硬锁」改为「占有系
# 白名单 + 变体引导 + 允许干净仪式」。实测教训：v19-v22 两句锚定压不住中段自创
# 判据（2 句覆盖不了 16 句争论），且 pro 硬锁重复锁死创造力更差（v21/v22 1/4）。
# 专家结论：正确做法是给模型占有系白名单（拿到/抢到/攥在手里/举起/翻开/坐上）
# +「每次宣示规则句式尽量与前次不同」的变体引导，允许附加孩子气赌约仪式
# （单脚站满十秒/举过头顶坚持三秒——正是回旋镖字面反噬的燃料；用户 2026-08-11
# 点名禁「放桌上三秒」这类无张力仪式），禁接触/状态/操作系动词混入；阶段三后处理
# 把漏网漂移句单句重写回白名单。
_C_CRITERION_PACKAGE_SYSTEM = """\
你为「昭昭&灿灿」日常短剧的 C 类（公平执念）故事生成「判据链锚点」。C 类判据
占有型判据核心动词**只许用占有系白名单**：拿到/抢到/攥在手里/翻开/坐上/举起；
动作分派型判据用 切/分/搬/拆（执行权）+ 选/挑/摆/清点（优先权）。孩子争某物
归属，占有型只许宣告「我先拿到的」「我攥在手里了」「我先抢到的」「谁先拿到归谁」；
动作分派型写「我切你选」「切完你先挑」「我分你先挑」。

**默认优先动作分派型（专家三轮 + 2026-08-12 定）**：规则把不同动作/角色分派给
不同的人——「我切你选」「我分你先挑」「我搬你摆」「我拆箱你清点」「切完你先挑」，
切/分/搬/拆是执行权，选/挑/摆/清点是优先选择权，两人不做同一件事，天然没有
分级杠精。**切分/拆封即终结（2026-08-12 定）**：蛋糕/食物等资源一旦切好/拆封，
禁止重切/恢复/重新比；开篇已切好只能争「谁先挑/拿哪块」，回旋镖扣「切完你先挑」。

**孩子气赌约仪式只在题面是「双方抢做同一动作」时用**（专家 2026-08-09 细化 +
用户 2026-08-11 定「判据要有张力」）：「单脚站满十秒」「金鸡独立站满十秒」
「举过头顶坚持三秒」（正例：「谁先攥在手里再单脚站满十秒谁喝」——核心动词「攥」
是占有系，「单脚站满十秒」是赌约仪式，站不住会晃会倒，正是回旋镖字面反噬的燃料）。
**禁无趣位置仪式**——「放桌上三秒」这类谁都能做到的条件没张力、回旋镖不炸
（用户 2026-08-11 点名否决）。**禁止仪式含接触/状态/操作系动词**——「数到三松手」
（松手=状态系）、「掏出来」（操作系）、「撕开包装」（开系）、「掉/洒」（状态）
一律禁用；别写「站够十秒」的「够」（够字易误判接触系，用「站满」）。

为主题生成 JSON（只输出 JSON，不要多余解释）：
1. zhaozhao_rule：昭昭（弟弟）抛出的规则台词，一句 8-24 字、核心动词用占有系
   白名单、**默认动作分派型**（我切你选/我分你先挑/切完你先挑/我拆箱你清点）；
   只有题面确实要抢同一动作时才可带孩子气赌约仪式（谁先拿到归谁/谁先攥在手里再
   单脚站满十秒谁喝/谁先举过头顶坚持三秒谁喝）；是可被抠字眼的占有判定，
   别用「放桌上三秒」这类没张力的仪式。
2. cancan_rule：灿灿（姐姐）抛出的规则台词，与昭昭的规则对立或加码，同样核心
   用占有系白名单、默认动作分派型、可带干净仪式。
3. boomerang_quote：将被反噬的原话——**必须与 zhaozhao_rule 或 cancan_rule
   完全一致**（逐字复制其中一句，不能改动、不能另造）。
4. boomerang_source：boomerang_quote 来自哪条，填 "zhaozhao_rule" 或
   "cancan_rule"。
5. trap：**立规人被反噬的规则漏字点 + 立规人自己怎么输**，一句话 6-40 字——
   **主语必须是立规人自己**：TA 定的规则没规定数数要多快→对方快数/慢数让 TA 站不住；
   TA 没说不许扶墙→TA 自己扶墙被抓；TA 自设的条件反噬 TA 自己。例如「没规定数数要
   多快，数数人拖长音，立规人先落地」「没说不许扶墙，立规人自己扶墙被抓」。
   破段必须落在这个漏字点上：**立规人必须输**，末句由立规人嘴硬收场；
   禁止写「对手犯规/对手输/对方也做到了」——立规人赢任何一轮判定即方向反了
   （酸奶稿 v47 死这）。

禁止 碰/摸/够/搭/挨/蹭/伸/探/点（接触系）、按/打开/切换/调（操作系）、
拧/撕/掰/揭（开系）、吃/咬/舔/喝/吞/尝/擦（消耗系）、松手/放手/攥住（状态系）、
动/跑/先数到（时序系）当判据；禁止「X不算，Y才算」分级杠精句式；禁止仪式含
数到三松手/掏出来/撕开包装/掉/洒等动作。
示例（可化用勿照抄）：zhaozhao_rule「谁先拿到归谁」、cancan_rule「我先攥在手里再
单脚站满十秒才算，归我」，boomerang_quote 从其中逐字选一句，trap「没规定数数要多快，
数数人拖长音，立规人站不住先落地」；切分型示例：zhaozhao_rule「切完我先挑，谁反悔
谁小狗」、cancan_rule「好，说好切完你先挑，谁反悔谁小狗」，trap「立规人答应切完
先挑后反悔硬抢，被对方按字面先挑走大块」；若立规人说过「挑哪块都一样/绝对公平」，
回旋镖优先打这句（你刚说挑哪块都一样，我挑了大的，你认不认）。

格式：{"zhaozhao_rule": "...", "cancan_rule": "...", "boomerang_quote": "...", "boomerang_source": "zhaozhao_rule|cancan_rule", "trap": "..."}
"""
_C_CRITERION_INJECT_TEMPLATE = """\
【判据链规则（最高优先级，比上面所有规则更硬）】
- 占有型判据核心动词只许占有系白名单：拿到/抢到/攥在手里/举起/翻开/坐上；
  动作分派型判据用 切/分/搬/拆 + 选/挑/摆/清点。
- **默认动作分派型**：我切你选/我分你先挑/切完你先挑/我拆箱你清点——切/分/搬/拆
  是执行权，选/挑/摆/清点是优先权；切好/拆封后禁重切/恢复/重新比。
- 只有本稿判据链规则含仪式（单脚站/金鸡独立/举过头顶/坚持X秒）时才写仪式；
  **禁「放桌上三秒」这类没张力的位置仪式**（用户 2026-08-11 点名）。
  仪式不得引入接触/松手/打开/撕/掏/掉/洒等动作；别写「站够」（够字易误判，用
  「站满」）。
- 每次角色提出/加码新规则，判据动词从白名单中选用，且句式尽量与前次不同，
  形成围绕占有的递进争论（动作分派：切完先挑→挑大块→反悔硬抢；仪式场：拿到→
  攥手里→举起→举过头顶坚持三秒）。
- 本稿规则锚点（可逐字引用，也可在白名单内换句式）：昭昭「{zhaozhao_rule}」、
  灿灿「{cancan_rule}」。
- 本稿反噬点（破段必须落在这，禁「对方也做到了」式平手）：{trap}
- **破段剧本（按此骨架写，勿另起炉灶）**：{break_script}
- 正文 14-16 句、每句 14-18 字、全篇 ≥280 字；写不满 280 字直接不合格。
- 结尾回旋镖，被戳穿方引用**正文真出现过的规则原话**反呛（可用 {boomerang_quote}，
  须与前文逐字一致）。
- 禁止其它动词当判据（碰/摸/按/拧/撕/喝/咬/动/跑/松手等一律禁用）。"""


def _build_story_avoid_block(avoid: list[str] | None) -> str:
    """正文层避雷块：把与库内已有稿撞车的元素（判据/开场理由/挑刺动作）逐条
    钉进 user 提示词，生成各环节（判据包/框架/开场/正文/修订）都不得使用。

    2026-08-10：preview 生成新稿时显式避开库里旧稿（如 id48 的「举过头顶」）
    ——theme 塞约束会破坏「跑题」校验（校验要求主题实词落正文，避雷要求不出现，
    自相矛盾），故走独立注入通道。
    """
    items = "、".join(str(x).strip() for x in (avoid or []) if str(x).strip())
    if not items:
        return ""
    return (
        "\n\n【避雷】本故事禁止出现以下元素——判据、开场理由、挑刺动作及任何台词"
        "都不得使用，须另想别的玩法：\n"
        f"- {items}"
    )


def _force_framework_fields(story: dict, framework: dict | None) -> None:
    """把框架字段逐字覆写到正文 dict，保证框架是唯一权威锚。

    2026-08-07 架构改造：scene_title/setting/conflict_core/key 由框架先生成，
    正文围绕框架展开。正文自己输出的这几个字段可能措辞漂移，统一以框架为准，
    开场/拼接/下游用到的冲突核心才与开场锚定一致。
    """
    if not framework or not isinstance(story, dict):
        return
    for field in ("scene_title", "setting", "conflict_core", "key"):
        v = framework.get(field)
        if v:
            story[field] = v


def _build_deepseek_chat_payload(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    thinking_enabled: bool,
    json_mode: bool = True,
    temperature: float | None = None,
) -> dict[str, Any]:
    """构建 chat/completions JSON；V4 默认 thinking=enabled，结构化输出须显式关闭。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def _storyboard_length_max_attempts() -> int:
    return get_settings().script_qa_max_attempts


_VISUAL_STYLE_BY_CONTENT_STYLE = {
    "daily_story": (
        "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
        "主观夸张变形，高饱和色彩，涂色出界，"
        "橡皮擦拭痕迹，手工感，孩子气的构图。"
        "主角：" + DAILY_STORY_CHARACTERS + "；" + DAILY_STORY_CHARACTER_MOM
    ),
    "life_experience": "生活 Vlog 质感写实画面：自然光或室内暖光，色彩真实不过度滤镜。",
    "history_mystery": "电影级写实历史再现：光影考究、暗部有层次、低饱和古风色调。",
    "tech_science": "电影级写实科技视觉：布光考究、材质细节真实、信息感强。",
    "science_child": "卡通科普插画风：明快蓝橙主色调，轮廓清晰、色块分明，偏科普示意图质感。",
}


def _resolve_visual_style(job: dict | None) -> str:
    """按 job 的 content_style 返回硬编码 visual_style。"""
    from app.utils.job_info import content_style_from_job
    style = content_style_from_job(job) if job else "science_child"
    return _VISUAL_STYLE_BY_CONTENT_STYLE.get(
        style, _VISUAL_STYLE_BY_CONTENT_STYLE["science_child"]
    )


def _narration_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _narration_length_feedback(
    chars: int,
    min_chars: int,
    *,
    prefix: str | None = None,
    narration_only: bool = False,
) -> str:
    deficit = max(1, min_chars - chars)
    if narration_only:
        msg = (
            f"narration 仅 {chars} 字，验收下限 {min_chars} 字，还差 {deficit} 字。"
            "请扩写 narration（补具体细节/案例/步骤/比喻），"
            "输出前核对 word_count 后再输出 JSON。"
        )
    else:
        msg = (
            f"narration 仅 {chars} 字，验收下限 {min_chars} 字，还差 {deficit} 字。"
            "请扩写各段 text（每层补具体细节/案例/步骤），"
            "先写 segments 再拼接 narration，输出前核对 word_count 与拼接一致性后再输出 JSON。"
        )
    if prefix:
        return f"{prefix}\n{msg}"
    return msg


def _narration_too_long_feedback(
    chars: int,
    max_chars: int,
    *,
    prefix: str | None = None,
    narration_only: bool = False,
) -> str:
    excess = max(1, chars - max_chars)
    if narration_only:
        msg = (
            f"narration 达 {chars} 字，超过验收上限 {max_chars} 字（超出 {excess} 字）。"
            "请删繁就简：删重复例子、合并并列知识点、缩短句子；"
            "输出前核对 word_count 后再输出 JSON。"
        )
    else:
        msg = (
            f"narration 达 {chars} 字，超过验收上限 {max_chars} 字（超出 {excess} 字）。"
            "请删繁就简：删重复例子、合并并列知识点、缩短每层句子；"
            "总字数靠删内容不靠堆段，禁止加长单段或新增话题；"
            "先写 segments 再拼接 narration，输出前逐段核对字数与总和后再输出 JSON。"
        )
    if prefix:
        return f"{prefix}\n{msg}"
    return msg


def _min_narration_chars_for_script(
    *,
    narration_target_words: int | None,
    video_timeline: str | None = None,
    chars_per_sec: float | None = None,
) -> int:
    timeline = parse_video_timeline(video_timeline, chars_per_sec=chars_per_sec)
    if timeline:
        lo, _ = narration_range_for_timeline(timeline)
        return lo
    target = narration_target_words or default_narration_target_words()
    return narration_accept_min_chars(target)


def _strip_markdown_json_fence(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.rstrip())
    return text.strip()


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _escape_control_chars_in_json_strings(raw: str) -> str:
    """将 JSON 字符串字面量内未转义的控制字符转为 \\n / \\uXXXX。"""
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == "\\":
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(ch):04x}")
            continue
        result.append(ch)
    return "".join(result)


def _fix_trailing_commas(text: str) -> str:
    """移除 JSON 数组和对象中非法的尾部逗号。"""
    import re
    # 移除数组中 ] 前的尾部逗号
    text = re.sub(r',\s*]', ']', text)
    # 移除对象中 } 前的尾部逗号
    text = re.sub(r',\s*}', '}', text)
    return text


def _repair_speaker_line_colon_json(text: str) -> str:
    """修常见笔误：\"speaker\":\"昭昭\":\"台词\" → \"speaker\":\"昭昭\",\"line\":\"台词\"。"""
    return re.sub(
        r'"speaker"\s*:\s*"(昭昭|灿灿|妈妈)"\s*:\s*"',
        r'"speaker":"\1","line":"',
        text,
    )


def _loads_llm_json(content: str) -> dict[str, Any]:
    text = _strip_markdown_json_fence(content)
    candidates = [text]
    extracted = _extract_json_object(text)
    if extracted != text:
        candidates.append(extracted)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        for variant in (
            candidate,
            _escape_control_chars_in_json_strings(candidate),
            _fix_trailing_commas(candidate),
            _repair_speaker_line_colon_json(candidate),
            _fix_trailing_commas(_repair_speaker_line_colon_json(candidate)),
        ):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_exc = exc
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError(f"LLM returned invalid JSON: {last_exc}") from last_exc


def _assemble_storyboard_narration(data: dict[str, Any]) -> dict[str, Any]:
    narration = str(data.get("narration") or "").strip()
    segments = data.get("segments") or []
    if not narration and segments:
        ordered = sorted(
            segments,
            key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
        )
        narration = "".join(str(seg.get("text") or "") for seg in ordered)
        data["narration"] = narration
    data["word_count"] = _narration_char_count(str(data.get("narration") or ""))
    return data


def _merge_visual_briefs(
    script: dict[str, Any],
    payload: dict[str, Any],
    *,
    required_indices: list[int] | None = None,
) -> None:
    # visual_style 已由 _generate_storyboard 硬编码设置，忽略 LLM 输出
    by_index = {
        int(item["segment_index"]): item
        for item in payload.get("segments") or []
        if item.get("segment_index") is not None
    }
    required = required_indices or [
        int(seg["segment_index"]) for seg in script.get("segments") or []
    ]
    missing = [idx for idx in required if idx not in by_index]
    if missing:
        raise ValueError(f"visual_brief response missing segments: {missing}")
    required_set = set(required)
    for seg in script.get("segments") or []:
        idx = int(seg["segment_index"])
        if idx not in required_set:
            continue
        item = by_index[idx]
        subjects = item.get("visual_subjects")
        brief = str(item.get("visual_brief") or "").strip()
        if isinstance(subjects, list) and subjects:
            from app.services.script.visual_brief import render_visual_subjects

            rendered = render_visual_subjects(subjects)
            if not rendered:
                raise ValueError(f"visual_subjects empty for segment {idx}")
            seg["visual_subjects"] = [
                s for s in subjects if isinstance(s, dict)
            ]
            seg["visual_brief"] = rendered
        elif brief:
            seg["visual_brief"] = brief
            seg.pop("visual_subjects", None)
        else:
            raise ValueError(f"visual_brief empty for segment {idx}")
        seg["visual_mode"] = item.get("visual_mode") or seg.get("visual_mode") or "static_motion"
        # object_states：结构化道具状态（S5 状态机输入）
        obj_states = item.get("object_states")
        if isinstance(obj_states, list):
            seg["object_states"] = [
                st for st in obj_states if isinstance(st, dict)
            ]
        # scene_anchors：场景硬锚点名词（S2 输入，代码负责压缩裁剪）
        anchors = item.get("scene_anchors")
        if isinstance(anchors, list):
            seg["scene_anchors"] = [
                str(a).strip() for a in anchors if str(a).strip()
            ]
        # cast：额外在场且非常态的角色（如妈妈），昭昭/灿灿由代码兜底补入
        cast = item.get("cast")
        if isinstance(cast, list):
            seg["cast"] = [
                str(c).strip() for c in cast if str(c).strip()
            ]


def _truncation_feedback() -> str:
    """A1 口播 JSON 被截断时的重试说明（不含 visual_brief / segments）。"""
    return (
        "上次 JSON 输出被截断（token 用尽）。"
        "请只输出 title、narration、word_count；"
        "不要输出 segments / visual_brief；"
        "适当缩短 narration，确保 JSON 完整闭合。"
    )


def _chunk_indices(indices: list[int], batch_size: int) -> list[list[int]]:
    size = max(1, batch_size)
    ordered = sorted({int(idx) for idx in indices})
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


class DeepSeekClient(LLMClient):
    def __init__(self) -> None:
        import requests

        self._requests = requests
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model
        self._pro_model = settings.deepseek_pro_model or settings.deepseek_model

    def _chat(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        json_mode: bool = True,
        thinking_enabled: bool | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[str, str | None]:
        settings = get_settings()
        limit = settings.deepseek_max_tokens if max_tokens is None else max_tokens
        use_thinking = settings.deepseek_thinking_enabled if thinking_enabled is None else thinking_enabled
        use_model = model or self._model
        resp = self._requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=_build_deepseek_chat_payload(
                model=use_model,
                system=system,
                user=user,
                max_tokens=limit,
                thinking_enabled=use_thinking,
                json_mode=json_mode,
                temperature=temperature,
            ),
            # 剧本/分镜生成长输出实测 103~181s，180s 超时贴线（超时重试成本更高），放宽到 300s
            timeout=300,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        finish = choice.get("finish_reason")
        content = choice.get("message", {}).get("content") or ""
        if finish == "length":
            logger.warning(
                "LLM response truncated (finish_reason=length), max_tokens=%d model=%s",
                limit,
                use_model,
            )
        return content, finish

    def _chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        thinking_enabled: bool | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        _EMPTY_RETRIES = 3
        for _ in range(_EMPTY_RETRIES):
            content, finish = self._chat(
                system,
                user,
                max_tokens=max_tokens,
                thinking_enabled=thinking_enabled,
                temperature=temperature,
                model=model,
            )
            if content.strip():
                break
            logger.warning(
                "LLM returned empty response, retrying (max=%d)",
                _EMPTY_RETRIES,
            )
            time.sleep(1)
        else:
            raise ValueError("LLM returned empty response after %d retries" % _EMPTY_RETRIES)
        try:
            parsed = _loads_llm_json(content)
        except ValueError as exc:
            # 记录 LLM 响应片段以便排查
            preview = content[:300].replace("\n", "\\n")
            logger.warning(
                "LLM JSON 解析失败: %s\n  content_preview=%r",
                exc,
                preview,
            )
            raise ValueError(str(exc)) from exc
        return parsed, finish

    def _expand_narration_if_needed(
        self,
        data: dict[str, Any],
        *,
        min_chars: int,
        mode: str,
        job: dict | None = None,
        max_chars: int | None = None,
    ) -> dict[str, Any]:
        chars = _narration_char_count(str(data.get("narration") or ""))
        if chars >= min_chars or chars < int(min_chars * 0.5):
            return data
        current = data
        segments = current.get("segments") or []
        default_mode = (
            segments[0].get("visual_mode", "static_motion") if segments else "static_motion"
        )
        for _ in range(_NARRATION_EXPAND_ATTEMPTS):
            raise_if_job_cancelled(job)
            prompts = build_voiceover_standard_expand_prompts(
                current,
                min_chars=min_chars,
                mode=mode,
                max_chars=max_chars,
                job=job,
            )
            expanded, _ = self._chat_json(
                prompts["system"],
                prompts["user"],
            )
            raise_if_job_cancelled(job)
            if mode == "narration_only":
                if not str(expanded.get("narration") or "").strip():
                    break
                if not expanded.get("visual_style"):
                    expanded["visual_style"] = current.get("visual_style")
                if not expanded.get("title"):
                    expanded["title"] = current.get("title")
            elif "segments" not in expanded:
                break
            else:
                for seg in expanded.get("segments") or []:
                    seg.setdefault("visual_mode", default_mode)
            new_chars = _narration_char_count(str(expanded.get("narration") or ""))
            if new_chars > chars:
                current = expanded
                chars = new_chars
            if chars >= min_chars:
                break
        return current

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        if not segment_indices:
            return script
        cps = chars_per_sec
        if cps is None and job:
            from app.utils.job_info import (
                content_style_from_job,
                resolve_speech_chars_per_sec,
                script_params_from_info,
            )

            cps = resolve_speech_chars_per_sec(
                script_params_from_info(job.get("info")),
                content_style=content_style_from_job(job),
            )
        if cps is None:
            cps = DEFAULT_SPEECH_CHARS_PER_SEC
        cap = segment_text_char_cap(segment_target_sec, chars_per_sec=cps)
        started = time.perf_counter()
        prompts = build_voiceover_standard_shrink_prompts(
            script,
            segment_indices=segment_indices,
            cap=cap,
            segment_target_sec=segment_target_sec,
            job=job,
        )
        raw, _ = self._chat_json(
            prompts["system"],
            prompts["user"],
        )
        raise_if_job_cancelled(job)
        items = raw.get("segments") if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            raise ValueError("LLM segment shrink response missing segments")
        by_idx: dict[int, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            idx = item.get("segment_index")
            text = item.get("text")
            if idx is None or not isinstance(text, str) or not text.strip():
                continue
            by_idx[int(idx)] = text.strip()
        missing = [idx for idx in segment_indices if idx not in by_idx]
        if missing:
            raise ValueError(f"segment shrink missing indices: {missing}")
        for seg in script.get("segments") or []:
            idx = int(seg.get("segment_index", -1))
            if idx in by_idx:
                seg["text"] = by_idx[idx]
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] segment_shrink done indices=%s cap=%d cps=%.2f elapsed=%.1fs",
            segment_indices,
            cap,
            cps,
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["segment_shrink_sec"] = round(
            float(timing.get("segment_shrink_sec") or 0) + elapsed, 1
        )
        return _assemble_storyboard_narration(script)

    def _generate_narration_only(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
        )
        max_chars = narration_accept_max_chars(narration_target_words)
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_storyboard_length_max_attempts()):
            raise_if_job_cancelled(job)
            # 首稿 Flash；字数/截断重试升 Pro
            use_model = self._model if attempt == 0 else self._pro_model
            if attempt > 0 and use_model != self._model:
                logger.info(
                    "[SCRIPT] A1 narration retry attempt=%d model=%s",
                    attempt + 1,
                    use_model,
                )
            prompts = build_voiceover_standard_prompts(
                title,
                feedback=length_feedback,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                job=job,
            )
            data, finish = self._chat_json(
                prompts["system"],
                prompts["user"],
                model=use_model,
            )
            raise_if_job_cancelled(job)
            if finish == "length":
                length_feedback = _truncation_feedback()
                if feedback and attempt == 0:
                    length_feedback = f"{feedback}\n{length_feedback}"
                data = None
                continue
            narration = str(data.get("narration") or "").strip()
            if not narration:
                raise ValueError("LLM narration response missing narration")
            chars = _narration_char_count(narration)
            data["narration"] = narration
            data["word_count"] = chars
            if chars > max_chars:
                length_feedback = _narration_too_long_feedback(
                    chars,
                    max_chars,
                    prefix=feedback if attempt == 0 and feedback else None,
                    narration_only=True,
                )
                continue
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
                narration_only=True,
            )
        if data is not None:
            chars = _narration_char_count(str(data.get("narration") or ""))
            if chars <= max_chars:
                data = self._expand_narration_if_needed(
                    data,
                    min_chars=min_chars,
                    mode="narration_only",
                    job=job,
                    max_chars=max_chars,
                )
                data["word_count"] = _narration_char_count(str(data.get("narration") or ""))
        if data is None:
            raise ValueError("LLM narration generation failed")
        raise_if_job_cancelled(job)
        return data

    def _fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        segments = script.get("segments") or []
        if not segments:
            raise ValueError("script has no segments for visual_brief")
        if not str(script.get("visual_style") or "").strip():
            script["visual_style"] = _resolve_visual_style(job)
        required = segment_indices or [
            int(seg["segment_index"]) for seg in segments
        ]
        started = time.perf_counter()
        prompts = build_visual_brief_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
        )
        payload, finish = self._chat_json(
            prompts["system"],
            prompts["user"],
            thinking_enabled=False,
            temperature=_TEMP_CREATIVE_MID,
        )
        raise_if_job_cancelled(job)
        if finish == "length":
            raise ValueError("LLM visual_brief response truncated")
        _merge_visual_briefs(script, payload, required_indices=required)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] visual_brief done segments=%d elapsed=%.1fs",
            len(required),
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["visual_brief_sec"] = round(elapsed, 1)
        return script

    def fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        return self._fill_visual_briefs(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
        )

    def _generate_storyboard(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        seg_target = (
            get_settings().segment_target_sec
            if segment_target_sec is None
            else segment_target_sec
        )
        narration_started = time.perf_counter()
        data = self._generate_narration_only(
            title,
            feedback=feedback,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        narration_elapsed = time.perf_counter() - narration_started
        data = apply_segments_from_voiceover(data, segment_target_sec=seg_target)
        # visual_style 硬编码，须在 A2 之前写入，供画面概述对齐画风
        data["visual_style"] = _resolve_visual_style(job)
        data = self._fill_visual_briefs(
            data,
            supplementary_info=supplementary_info,
            job=job,
        )
        timing = data.setdefault("_llm_timing", {})
        timing["narration_sec"] = round(narration_elapsed, 1)
        timing["storyboard_sec"] = round(
            narration_elapsed + float(timing.get("visual_brief_sec") or 0),
            1,
        )
        raise_if_job_cancelled(job)
        return data

    def _generate_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        prompts = build_image_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
            include_sd15_prompt=include_sd15_prompt,
        )
        # 模板化改写任务，无需推理；开思考模式一批要 ~100s
        raw, finish = self._chat_json(
            prompts["system"],
            prompts["user"],
            thinking_enabled=False,
        )
        raise_if_job_cancelled(job)
        if finish == "length":
            raise ValueError("LLM image_prompts 被截断 (finish_reason=length)")
        if isinstance(raw, list):
            prompt_items = raw
        elif isinstance(raw, dict):
            prompt_items = raw.get("image_prompts")
        else:
            raise ValueError("LLM image prompt response has unexpected shape")
        if not prompt_items:
            raise ValueError("LLM image prompt response missing image_prompts")
        return {"image_prompts": prompt_items}

    def review_image_prompts(
        self,
        script: dict[str, Any],
        *,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> list[dict]:
        """L2 语义审核：LLM reviewer 审查已拼装的 image_prompt，返回 issues。"""
        from app.services.script.image_prompt import build_image_prompt_review_prompts

        prompts = build_image_prompt_review_prompts(
            script,
            segment_indices=segment_indices,
        )
        # 审核任务是模式识别，无需深度推理；不传 thinking/temperature 以兼容各 provider
        raw, finish = self._chat_json(
            prompts["system"],
            prompts["user"],
        )
        raise_if_job_cancelled(job)
        if finish == "length":
            raise ValueError("LLM image_prompt_review 被截断 (finish_reason=length)")
        if not isinstance(raw, dict):
            return []
        reviews = raw.get("reviews") or []
        return [r for r in reviews if isinstance(r, dict)]

    def _merge_image_prompts(
        self,
        script: dict[str, Any],
        prompts: list[dict],
        *,
        required_indices: list[int] | None = None,
        motion_only: bool = False,
    ) -> None:
        if motion_only:
            by_index: dict[int, dict] = {
                int(item["segment_index"]): item
                for item in prompts
                if item.get("segment_index") is not None
                and str(item.get("motion_prompt") or "").strip()
            }
        else:
            by_index = {
                int(item["segment_index"]): item
                for item in prompts
                if item.get("image_prompt")
            }
        required = required_indices or [
            int(seg["segment_index"]) for seg in script.get("segments") or []
        ]
        missing = [idx for idx in required if idx not in by_index]
        if missing:
            raise ValueError(f"image_prompts missing segments: {missing}")
        index_set = set(required)
        for seg in script["segments"]:
            idx = int(seg["segment_index"])
            if idx not in index_set:
                continue
            item = by_index[idx]
            if not motion_only and item.get("image_prompt"):
                seg["image_prompt"] = item["image_prompt"]
            seg["motion_prompt"] = item.get("motion_prompt", "")
            # 存储 SD15 专用英文 prompt（仅当 LLM 输出了该字段时）
            sd15_en = item.get("sd15_prompt_en")
            if sd15_en and isinstance(sd15_en, str) and sd15_en.strip():
                seg["sd15_prompt_en"] = sd15_en.strip()

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        from app.services.script.image_prompt import assemble_daily_image_prompts
        from app.utils.job_info import CONTENT_STYLE_DAILY_STORY, content_style_from_job

        settings = get_settings()
        segments = script.get("segments") or []
        if not segments:
            raise ValueError("script has no segments")
        all_indices = segment_indices or [int(seg["segment_index"]) for seg in segments]
        style = content_style_from_job(job) if job else script.get("content_style")
        is_daily = style == CONTENT_STYLE_DAILY_STORY
        if is_daily:
            from app.services.daily_story.speaker import (
                annotate_sticky_stage_speakers,
                allowed_cast_from_segment,
                scrub_leaked_speaker_names,
            )

            setting = str(script.get("setting") or "").strip() or None
            # 先粘性标注再 scrub，避免 cast 仍按本段对白把同场角色 scrub 掉
            annotate_sticky_stage_speakers(segments, setting=setting)
            if feedback and "speaker leak" in feedback:
                wanted = {int(i) for i in all_indices}
                for seg in segments:
                    if int(seg.get("segment_index") or 0) not in wanted:
                        continue
                    allowed = allowed_cast_from_segment(seg)
                    seg["visual_brief"] = scrub_leaked_speaker_names(
                        str(seg.get("visual_brief") or ""),
                        allowed,
                    )
            # feedback 只给后续 LLM（motion）；禁止拼进规则组装的 T2I 正文
            assemble_daily_image_prompts(
                segments,
                segment_indices=all_indices,
                setting=setting,
            )
        batch_size = settings.llm_image_prompt_batch_size
        started = time.perf_counter()

        def _run_batch(batch_indices: list[int]) -> list[dict]:
            result = self._generate_image_prompts(
                script,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=batch_indices,
                include_sd15_prompt=include_sd15_prompt,
            )
            return result["image_prompts"]

        def _run_all(batches: list[list[int]]) -> list[dict]:
            """多批并行：用 gevent 绿程，勿用 ThreadPoolExecutor。

            script 阶段跑在 hub 主线程 greenlet 上；OS 线程 + as_completed
            会堵死整个 WSGI hub（接口不返回），且 thread 里打 patched
            requests 易与 hub 死锁。绿程并行时 socket 可让出，其它接口仍响应。
            """
            if len(batches) <= 1:
                return _run_batch(batches[0])
            pool = gevent.pool.Pool(size=len(batches))
            green_lets = [pool.spawn(_run_batch, batch) for batch in batches]
            gevent.joinall(green_lets, raise_error=True)
            items: list[dict] = []
            for g in green_lets:
                items.extend(g.value)
                raise_if_job_cancelled(job)
            return items

        # 首次尝试
        batches = _chunk_indices(all_indices, batch_size)
        try:
            prompt_items = _run_all(batches)
        except ValueError as exc:
            if "被截断" not in str(exc) or batch_size <= 1:
                raise
            # 截断时缩小批次（逐段生成）重试一次
            logger.warning(
                "image_prompts truncated with batch_size=%d, retrying with batch_size=1",
                batch_size,
            )
            batches = _chunk_indices(all_indices, 1)
            prompt_items = _run_all(batches)

        self._merge_image_prompts(
            script,
            prompt_items,
            required_indices=all_indices,
            motion_only=is_daily,
        )
        raise_if_job_cancelled(job)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] image_prompts done segments=%d batches=%d elapsed=%.1fs",
            len(all_indices),
            len(batches),
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["image_prompts_sec"] = round(elapsed, 1)
        timing["image_prompt_batches"] = len(batches)
        return script

    def _fill_image_prompts_with_retries(
        self,
        script: dict[str, Any],
        *,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        feedback: str | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        self.fill_image_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
            include_sd15_prompt=include_sd15_prompt,
        )
        return script

    def generate_storyboard(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        data = self._generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        raise_if_job_cancelled(job)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] storyboard done segments=%d words=%d elapsed=%.1fs",
            len(data.get("segments") or []),
            _narration_char_count(str(data.get("narration") or "")),
            elapsed,
        )
        data["_llm_timing"] = {"storyboard_sec": round(elapsed, 1)}
        return data

    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        existing_script: dict[str, Any] | None = None,
        retry_scope: str | None = None,
        generate_image_prompts: bool = True,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        if retry_scope == "image_prompts" and existing_script is not None:
            data = existing_script
            self._fill_image_prompts_with_retries(
                data,
                supplementary_info=supplementary_info,
                job=job,
                feedback=feedback,
                include_sd15_prompt=include_sd15_prompt,
            )
            return data

        if retry_scope == "visual_brief" and existing_script is not None:
            data = existing_script
            self._fill_visual_briefs(
                data,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
            )
            return data

        data = self.generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        if generate_image_prompts:
            self._fill_image_prompts_with_retries(
                data,
                supplementary_info=supplementary_info,
                job=job,
                include_sd15_prompt=include_sd15_prompt,
            )
        return data

    def _shrink_longest_segments_to_fit(
        self,
        data: dict[str, Any],
        max_chars: int,
    ) -> None:
        """总口播超长时，按长度降序缩句最长的 segments，直到总字数 <= max_chars。"""
        segments = data.get("segments") or []
        if not segments:
            return
        seg_texts = [str(s.get("text") or "") for s in segments]
        total = _narration_char_count("".join(seg_texts))
        excess = total - max_chars
        if excess <= 0:
            return
        # 按文本长度降序排列，优先缩最长的段
        indexed = sorted(
            enumerate(segments),
            key=lambda pair: _narration_char_count(str(pair[1].get("text") or "")),
            reverse=True,
        )
        for _orig_idx, seg in indexed:
            if excess <= 0:
                break
            text = str(seg.get("text") or "")
            cur_len = _narration_char_count(text)
            if cur_len <= 10:
                continue
            # 目标：至少砍掉 excess，但不低于 10 字
            target_len = max(10, cur_len - excess)
            system = (
                "将以下口播段落精简缩短，保留核心信息与自然口吻，"
                f"字数控制在 {target_len} 字以内（当前 {cur_len} 字）。"
                "直输出精简后的段落文本，不要 JSON、不要解释。"
            )
            user = f"口播段落：{text}"
            try:
                content, _ = self._chat(
                    system,
                    user,
                    json_mode=False,
                )
                fixed = content.strip()
                if fixed:
                    old_len = cur_len
                    seg["text"] = fixed
                    new_len = _narration_char_count(fixed)
                    excess -= (old_len - new_len)
                    logger.info(
                        "shrunk segment %s: %d -> %d chars (excess remaining: %d)",
                        seg.get("segment_index", _orig_idx), old_len, new_len, excess,
                    )
            except Exception as exc:
                logger.warning("shrink segment %s failed: %s", seg.get("segment_index", _orig_idx), exc)
        # 重新拼接 narration
        seg_texts = [str(s.get("text") or "") for s in segments]
        data["narration"] = "".join(seg_texts)
        data["word_count"] = _narration_char_count(data["narration"])

    def _fix_material_segments(
        self,
        data: dict[str, Any],
        segments: list[dict],
        mode: str,
        timeline: Any,
        chars_per_sec: float,
    ) -> None:
        """对超长/不足的 segments 逐段调 LLM 缩句或扩句，原地修改 data。"""
        from app.services.script.board_timeline import _max_chars_for_duration, slot_min_chars
        for seg in segments:
            idx = int(seg.get("segment_index", 0))
            slot = next((s for s in timeline.slots if s.index == idx), None)
            if not slot:
                continue
            mc = _max_chars_for_duration(slot.duration_sec, chars_per_sec)
            mn = slot_min_chars(mc)
            text = str(seg.get("text") or "")
            if mode == "shrink":
                system = (
                    "将以下口播段落精简缩短，保留核心科普信息与童趣口吻，"
                    f"字数控制在 {mn}-{mc} 字之间（当前 {_narration_char_count(text)} 字）。直输出精简后的段落文本，不要 JSON。"
                )
            else:
                system = (
                    "将以下口播段落扩充写长，补充更多科普细节、比喻或互动感叹，"
                    f"字数达到 {mn}-{mc} 字之间（当前 {_narration_char_count(text)} 字）。直输出扩充后的段落文本，不要 JSON。"
                )
            user = f"口播段落：{text}\n\n该段对应画面：{slot.scene}，{slot.description}"
            try:
                content, _ = self._chat(
                    system,
                    user,
                    json_mode=False,
                )
                fixed = content.strip()
                if fixed:
                    seg["text"] = fixed
            except Exception as exc:
                logger.warning("material segment %s failed for seg %s: %s", mode, idx, exc)

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        from app.utils.job_info import resolve_speech_chars_per_sec, script_params_from_info
        from app.services.script.voiceover_material import resolve_need_opening

        _script_params = script_params_from_info(job.get("info")) if job else {}
        _cps = (
            resolve_speech_chars_per_sec(
                _script_params or (job.get("script") if job else None)
            )
            if job
            else None
        )
        _need_opening = resolve_need_opening(job)

        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
            video_timeline=video_timeline,
            chars_per_sec=_cps,
        )
        max_chars = narration_accept_max_chars(narration_target_words)
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_storyboard_length_max_attempts()):
            raise_if_job_cancelled(job)
            prompts = build_voiceover_material_prompts(
                title,
                feedback=length_feedback,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                video_timeline=video_timeline,
                chars_per_sec=_cps,
                need_opening=_need_opening,
                job=job,
            )
            data, _ = self._chat_json(
                prompts["system"],
                prompts["user"],
            )
            raise_if_job_cancelled(job)
            if "segments" not in data:
                raise ValueError("LLM material script response missing segments")
            for seg in data["segments"]:
                seg.setdefault("visual_mode", "material")
            # 重新拼接 narration 并计算 word_count
            seg_texts = [str(s.get("text") or "") for s in data["segments"]]
            data["narration"] = "".join(seg_texts)
            data["word_count"] = _narration_char_count(data["narration"])
            chars = data["word_count"]
            if chars > max_chars:
                length_feedback = _narration_too_long_feedback(
                    chars,
                    max_chars,
                    prefix=feedback if attempt == 0 and feedback else None,
                )
                logger.warning(
                    "material script narration too long (attempt %d): %d > %d",
                    attempt + 1,
                    chars,
                    max_chars,
                )
                continue
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
            )
        if data is not None:
            # 重新拼接 narration 并计算 word_count
            seg_texts = [str(s.get("text") or "") for s in (data.get("segments") or [])]
            data["narration"] = "".join(seg_texts)
            data["word_count"] = _narration_char_count(data["narration"])
            chars = data["word_count"]
            if chars <= max_chars:
                data = self._expand_narration_if_needed(
                    data,
                    min_chars=min_chars,
                    mode="material",
                    job=job,
                    max_chars=max_chars,
                )
            # 有时间表时，逐段校验预算并扩/缩句
            if video_timeline and data.get("segments"):
                from app.services.script.board_timeline import parse_video_timeline, _max_chars_for_duration, slot_min_chars
                tl = parse_video_timeline(video_timeline, chars_per_sec=_cps)
                if tl and tl.slots:
                    cps = _cps or DEFAULT_SPEECH_CHARS_PER_SEC
                    expand_seg_lst: list[dict] = []
                    shrink_seg_lst: list[dict] = []
                    seg_idx_map: dict[int, dict] = {}
                    for seg in data["segments"]:
                        seg_idx_map[int(seg.get("segment_index", 0))] = seg
                    for slot in tl.slots:
                        seg = seg_idx_map.get(slot.index)
                        if not seg:
                            continue
                        mc = _max_chars_for_duration(slot.duration_sec, cps)
                        mn = slot_min_chars(mc)
                        text = str(seg.get("text") or "")
                        chars_seg = _narration_char_count(text)
                        if chars_seg < mn:
                            expand_seg_lst.append(seg)
                        elif chars_seg > mc:
                            shrink_seg_lst.append(seg)
                    # 缩句（超长段）
                    if shrink_seg_lst:
                        self._fix_material_segments(data, shrink_seg_lst, "shrink", tl, cps)
                    # 扩句（不足段）
                    if expand_seg_lst:
                        self._fix_material_segments(data, expand_seg_lst, "expand", tl, cps)
                    if shrink_seg_lst or expand_seg_lst:
                        seg_texts = [str(s.get("text") or "") for s in (data.get("segments") or [])]
                        data["narration"] = "".join(seg_texts)
                        data["word_count"] = _narration_char_count(data["narration"])
            # 最终兜底：如果总口播仍超长，按长度降序缩句最长段落
            final_chars = _narration_char_count(data.get("narration", ""))
            if final_chars > max_chars:
                logger.warning(
                    "material script still too long after retries (%d > %d), shrinking longest segments",
                    final_chars, max_chars,
                )
                self._shrink_longest_segments_to_fit(data, max_chars)
        raise_if_job_cancelled(job)
        return data

    def optimize_script_title(
        self,
        draft_title: str,
        narration: str,
        *,
        max_title_length: int | None = None,
    ) -> str:
        prompts = build_title_optimize_prompts(
            draft_title,
            narration,
            max_title_length=max_title_length,
        )
        raw, _ = self._chat_json(
            prompts["system"],
            prompts["user"],
            thinking_enabled=False,
            temperature=_TEMP_CREATIVE_MID,
        )
        settings = get_settings()
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        return parse_title_optimize_payload(raw, max_title_len=max_len)

    def generate_video_description(
        self,
        title: str,
        narration: str,
        *,
        content_style: str | None = None,
    ) -> str:
        prompts = build_video_description_prompts(
            title,
            narration,
            content_style=content_style,
        )
        raw, _ = self._chat_json(
            prompts["system"],
            prompts["user"],
            thinking_enabled=False,
            temperature=_TEMP_UTILITY,
        )
        return parse_video_description_payload(raw)

    def generate_tags(
        self,
        title: str,
        narration: str,
        *,
        content_style: str | None = None,
    ) -> list[str]:
        prompts = build_tags_prompts(title, narration, content_style=content_style)
        raw, _ = self._chat_json(
            prompts["system"],
            prompts["user"],
            thinking_enabled=False,
            temperature=_TEMP_UTILITY,
        )
        return parse_tags_payload(raw)

    def rewrite_pixabay_query(
        self,
        query: str,
        *,
        language: str | None = None,
    ) -> str:
        from app.services.clip_search.query_rewrite_prompts import (
            build_pixabay_query_system_prompt,
            build_pixabay_query_user_prompt,
            parse_pixabay_query_payload,
        )

        prompts_system = build_pixabay_query_system_prompt()
        prompts_user = build_pixabay_query_user_prompt(query=query, language=language)
        raw, _ = self._chat_json(
            prompts_system,
            prompts_user,
            thinking_enabled=False,
            temperature=_TEMP_UTILITY,
        )
        return parse_pixabay_query_payload(raw)

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
        from app.services.segment.image.image_sd15 import (
            build_sd15_prompt_system,
            build_sd15_prompt_user,
            parse_image_size,
            parse_sd15_prompt_payload,
        )

        raw, _ = self._chat_json(
            build_sd15_prompt_system(business_override=business_override),
            build_sd15_prompt_user(
                prompt=prompt,
                size_hint=size_hint,
                parse_size=parse_image_size,
            ),
        )
        return parse_sd15_prompt_payload(
            raw,
            business_override=business_override,
        )

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        category: str | None = None,
        keywords: str | list[str] | None = None,
    ) -> list[dict[str, str]]:
        settings = get_settings()
        count = max(1, min(count, 20))
        system = system_prompt or build_topic_system_prompt(
            max_title_len=settings.max_title_length,
            category=category,
            keywords=keywords,
            count=count,
        )
        user = (
            user_prompt.strip()
            if user_prompt
            else build_topic_user_prompt(
                category=category,
                theme=theme,
                count=count,
                keywords=keywords,
            )
        )
        user_base = user
        last_exc: ValueError | None = None
        max_attempts = 3 if user_prompt else 2
        for attempt in range(max_attempts):
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                temperature=_TEMP_CREATIVE_MID,
            )
            try:
                topics = parse_topics_payload(raw, max_title_len=settings.max_title_length)
                return topics[:count]
            except ValueError as exc:
                if not is_topic_parse_retryable(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    break
                feedback = format_topic_parse_feedback(
                    raw,
                    max_title_len=settings.max_title_length,
                )
                retry_extra_parts: list[str] = []
                if any(
                    token in feedback
                    for token in ("问号对话体", "问号后", "须为问号", "半句问法")
                ):
                    retry_extra_parts.append(
                        "【特别强调】title 必须包含中文问号「？」并写完整反驳半句；"
                        "禁止再次输出无问号的陈述句。"
                    )
                if "画面锚点" in feedback:
                    retry_extra_parts.append(
                        "【特别强调】title 须从本题主题提炼可见载体，"
                        "配合图解词（规则、能量、表…）；"
                        "禁止油路、备用道、命脉等抽象比喻。"
                        "但仍须保持「问句？反驳」一整句结构。"
                    )
                retry_extra = "\n".join(retry_extra_parts)
                logger.warning(
                    "[TOPIC] llm retry all entries filtered attempt=%d/%d",
                    attempt + 1,
                    max_attempts,
                )
                user = (
                    f"{user_base}\n\n"
                    "【重试】上一轮输出的标题均未通过规则，请严格按对话反转式重写："
                    "「误区问句？+一步反驳（够你跑路、真以为、压根等，勿句句明明开头）」，"
                    "禁止百科式提问、半句问法、仅语气词收尾。\n"
                    f"{feedback}"
                    + (f"\n{retry_extra}" if retry_extra else "")
                )
        assert last_exc is not None
        raise last_exc

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        cps = chars_per_sec
        if cps is None and job:
            from app.utils.job_info import (
                content_style_from_job,
                resolve_speech_chars_per_sec,
                script_params_from_info,
            )

            cps = resolve_speech_chars_per_sec(
                script_params_from_info(job.get("info")),
                content_style=content_style_from_job(job),
            )
        if cps is None:
            from app.utils.job_info import DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC

            cps = DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC

        system, user = build_daily_script_prompts(
            dialogue_script, chars_per_sec=cps
        )
        user_base = user
        last_exc: Exception | None = None
        max_attempts = get_settings().script_qa_max_attempts

        # 提取原始台词列表（跳过纯标点行，与下游过滤逻辑一致）
        original_dialogue = dialogue_script.get("dialogue") or []
        _correct_dialogue_speaker(original_dialogue)
        original_lines: list[str] = []
        for d in original_dialogue:
            line = (d.get("line") or "").strip()
            if line and re.search(r"[\u4e00-\u9fff\w]", line):
                original_lines.append(line)

        for attempt in range(max_attempts):
            started = time.perf_counter()
            try:
                # 切分镜是结构化分配任务，无需推理；开思考模式实测 181s→关后大幅下降（同 image_prompts 先例）
                raw, finish = self._chat_json(
                    system,
                    user,
                    thinking_enabled=False,
                    temperature=_TEMP_CREATIVE_MID,
                )
            except ValueError as exc:
                last_exc = JobStageFailureError(str(exc))
                if attempt + 1 >= max_attempts:
                    break
                logger.warning(
                    "[DAILY_STORY] generate script json parse failed attempt=%d/%d: %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                user = (
                    f"{user_base}\n\n"
                    "【重试】上一轮输出的 JSON 格式无效，请确保输出合法的 JSON 格式，"
                    "包含 scenes 数组。"
                )
                continue
            raise_if_job_cancelled(job)
            if finish == "length":
                last_exc = JobStageFailureError("LLM daily_script response truncated")
                if attempt + 1 >= max_attempts:
                    break
                logger.warning(
                    "[DAILY_STORY] generate script truncated attempt=%d/%d",
                    attempt + 1,
                    max_attempts,
                )
                user = (
                    f"{user_base}\n\n"
                    "【重试】上一轮 JSON 被截断。请只输出 scenes；"
                    "适当合并镜头（仍须保留全部原台词），确保 JSON 完整闭合。"
                )
                continue
            elapsed = time.perf_counter() - started
            scenes = raw.get("scenes") or []
            if scenes:
                promoted = enforce_daily_script_closeups(scenes)
                if promoted:
                    logger.info(
                        "[DAILY_STORY] closeup promote attempt=%d/%d: %s",
                        attempt + 1,
                        max_attempts,
                        promoted,
                    )
                # 验证所有原始台词是否都被 LLM 分配到各镜头中
                generated_text = "".join(
                    str(d.get("text") or d.get("line") or "")
                    for scene in scenes
                    for d in (scene.get("dialogue") or [])
                    if isinstance(d, dict)
                )
                missing = [line for line in original_lines if line not in generated_text]
                if missing:
                    last_exc = JobStageFailureError(
                        f"LLM 遗漏 {len(missing)} 句台词: {missing}"
                    )
                    if attempt + 1 >= max_attempts:
                        break
                    logger.warning(
                        "[DAILY_STORY] generate script missing %d lines attempt=%d/%d: %s",
                        len(missing),
                        attempt + 1,
                        max_attempts,
                        missing,
                    )
                    user = (
                        f"{user_base}\n\n"
                        "【重试】上一轮输出的 scenes 遗漏了以下台词，"
                        "请重新将所有原台词完整分配到各镜头的 dialogue 数组中，不要修改措辞：\n"
                        + "\n".join(f"- {m}" for m in missing)
                    )
                    continue

                closeup_errs = validate_daily_script_scenes(scenes)
                if closeup_errs:
                    last_exc = JobStageFailureError(
                        "分镜特写校验失败: " + "; ".join(closeup_errs)
                    )
                    if attempt + 1 >= max_attempts:
                        break
                    logger.warning(
                        "[DAILY_STORY] generate script closeup attempt=%d/%d: %s",
                        attempt + 1,
                        max_attempts,
                        closeup_errs,
                    )
                    retry_hint = (
                        "【重试】特写镜 dialogue 不得超过 2 句（图生视频口型限制）。"
                        "请把多出的台词拆到下一镜（分镜倾向每镜 2 句），"
                        "不要为省镜把 3 句塞进中景：\n"
                    )
                    if any("特写镜仅" in e or "超过上限" in e for e in closeup_errs):
                        retry_hint = (
                            "【重试】特写镜数量不足或过多（硬性：按实际镜数 N，"
                            "特写须在 max(2,⌈N/3⌉)–⌈N/2⌉（进一法）；"
                            "例 8→3–4、10→4–5、11→4–6）。"
                            "开场首镜、中段转折、妈妈收场须标「特写」，"
                            "每特写 ≤2 句对白；只改 shot_type 或拆/并镜，"
                            "**禁止删改或遗漏原台词**：\n"
                        )
                    user = f"{user_base}\n\n{retry_hint}" + "\n".join(
                        f"- {e}" for e in closeup_errs
                    )
                    continue

                logger.info(
                    "[DAILY_STORY] script done scenes=%d attempt=%d/%d elapsed=%.1fs",
                    len(scenes),
                    attempt + 1,
                    max_attempts,
                    elapsed,
                )
                return raw
            last_exc = JobStageFailureError(
                "generate_daily_script returned empty scenes"
            )
            if attempt + 1 >= max_attempts:
                break
            logger.warning(
                "[DAILY_STORY] generate script empty scenes attempt=%d/%d",
                attempt + 1,
                max_attempts,
            )
            user = (
                f"{user_base}\n\n"
                "【重试】上一轮输出的 JSON 缺少 scenes 数组，"
                "请确保输出格式包含 scenes 数组。"
            )
        assert last_exc is not None
        raise last_exc

    def generate_daily_story(
        self,
        theme: str,
        *,
        story_type: str | None = None,
        avoid: list[str] | None = None,
        framework: dict | None = None,
        opening: list[dict] | None = None,
    ) -> dict[str, Any]:
        """2026-08-07 架构改造：框架先行 → 开场 → 正文 → 拼接。

        先生成剧本框架（scene_title/setting/conflict_core/key）作定盘锚，
        开场吃框架、正文吃框架+开场续写，避免 body 自造冲突与开场脱锚。

        avoid：正文层避雷（避免与库内已有稿撞车的判据/开场理由/挑刺动作），
        各生成环节统一注入 _build_story_avoid_block。
        framework / opening：外层重试时传入，避免整条重跑。
        """
        if not story_type:
            story_type = _select_story_type(theme)
        # C 类台词锚定：包先生成一次（开场与正文共用），开场也注入——
        # 否则开场先于正文生成、不知规则，可能用禁用动词当判据（v19 开场
        # 漂移[1]），注入开场后开场立的规自然用白名单台词。
        from app.services.daily_story.story_types import parse_story_type_code

        avoid_block = _build_story_avoid_block(avoid)
        criterion_block = ""
        if parse_story_type_code(story_type=story_type) == "C":
            pkg = self._generate_c_criterion_package(
                theme,
                avoid_block=avoid_block,
            )
            if pkg:
                criterion_block = _C_CRITERION_INJECT_TEMPLATE.format(**pkg)
        if not isinstance(framework, dict) or not framework:
            framework = self._generate_daily_story_framework(
                theme,
                story_type=story_type,
                avoid_block=avoid_block,
            )
        if not isinstance(opening, list) or not opening:
            opening = self._generate_daily_story_opening(
                theme,
                framework,
                story_type=story_type,
                criterion_block=criterion_block,
                avoid_block=avoid_block,
            )
        beats = None
        if parse_story_type_code(story_type=story_type) == "B":
            beats = self._generate_daily_story_beats(
                theme,
                story_type=story_type,
                framework=framework,
            )
        try:
            body = self._generate_daily_story_body(
                theme,
                story_type=story_type,
                framework=framework,
                opening=opening,
                criterion_block=criterion_block,
                avoid_block=avoid_block,
                beats=beats,
            )
            story = self._stitch_daily_story_full(
                theme,
                body,
                story_type=story_type,
                framework=framework,
                opening=opening,
                criterion_block=criterion_block,
            )
        except ValueError as exc:
            if not getattr(exc, "_framework", None):
                exc._framework = framework  # type: ignore[attr-defined]
            if not getattr(exc, "_opening", None):
                exc._opening = opening  # type: ignore[attr-defined]
            raise
        if beats and isinstance(beats, dict) and beats.get("theme_object"):
            # 节拍表主题物随稿带走，供润色定向修「妈妈句未点名主题物」；
            # 入库前由 llm_mgr 剥掉，不落库。
            story["_beats_theme_object"] = str(beats["theme_object"]).strip()
        return story

    def refine_daily_story_for_quality(
        self,
        theme: str,
        story: dict[str, Any],
        revision_hints: str,
        *,
        story_type: str | None = None,
        avoid: list[str] | None = None,
    ) -> dict[str, Any]:
        """按观感短板定向修订正文；开场保留、失配（连说等）才重拼。

        2026-08-07 架构改造：不再每轮重抽开场——原稿 discovery_opening 先保留，
        只有拼接硬伤（如修订后正文首句与开场末句连说）才在 _stitch 里重拼。
        """
        from app.services.daily_story.story_types import parse_story_type_code

        hints = (revision_hints or "").strip()
        if not hints:
            return story
        opening = story.get("discovery_opening")
        body = {
            k: v
            for k, v in story.items()
            if k not in ("discovery_opening", "quality")
        }
        rev_code = parse_story_type_code(
            story_type=story_type,
            punchline=str(body.get("punchline_explain") or ""),
        )
        avoid_block = _build_story_avoid_block(avoid)
        new_body = self._revise_daily_story_body(
            theme, body, hints, avoid_block=avoid_block
        )
        # 正文已锚定框架字段（scene_title/setting/conflict_core/key），
        # 取回作开场重拼时的锚
        framework = {
            f: body.get(f)
            for f in ("scene_title", "setting", "conflict_core", "key")
            if body.get(f)
        }
        return self._stitch_daily_story_full(
            theme,
            new_body,
            story_type=rev_code,
            framework=framework or None,
            opening=opening,
        )

    def _stitch_daily_story_full(
        self,
        theme: str,
        body: dict[str, Any],
        *,
        story_type: str | None = None,
        framework: dict | None = None,
        opening: list[dict] | None = None,
        criterion_block: str = "",
    ) -> dict[str, Any]:
        from app.services.daily_story.prompts import (
            _patch_body_part_char_budget,
            stitch_daily_story_opening,
            validate_daily_story_json,
        )

        avoid = opening_avoid_speaker_from_body(body)
        last_exc: ValueError | None = None
        # 架构改造后开场先生成传入：优先用传入开场（round 0），拼接硬伤
        # （连说）才在 round 1 重拼避连说；无传入时保持原行为，最多 2 轮重拼。
        max_open_rounds = 2
        for round_i in range(max_open_rounds):
            if opening is not None and round_i == 0:
                cur_opening = opening
            else:
                # 重拼轮：避开正文首句说话人；无传入开场时首轮不避（同旧行为）
                use_avoid = avoid if (round_i > 0 or opening is not None) else None
                cur_opening = self._generate_daily_story_opening(
                    theme,
                    framework if framework is not None else body,
                    avoid_speaker=use_avoid,
                    story_type=story_type,
                    criterion_block=criterion_block,
                )
            story = stitch_daily_story_opening(body, cur_opening)
            # 拼接删正文开头发现句后 body-part 可能跌破 280：本地收口回硬卡内
            bp_notes = _patch_body_part_char_budget(story)
            if bp_notes:
                logger.info(
                    "[DAILY_STORY] body-part char budget patch: %s",
                    ",".join(bp_notes),
                )
            try:
                validate_daily_story_json(story, phase="full")
                return story
            except ValueError as exc:
                last_exc = exc
                # Stage 3 判据链安全网（phase=full 兜底）：拼开场后判据漂移索引含
                # 开场 2 句，正文修复过但开场/拼接句漂移时在此单句重写再复检。
                if "判据漂移" in str(exc):
                    try:
                        fixed = self._stage3_fix_c_criterion_drift(
                            story,
                            theme=theme,
                        )
                    except Exception as exc3:  # noqa: BLE001
                        fixed = None
                        logger.warning(
                            "[DAILY_STORY] Stage3 full fix raised: %s",
                            exc3,
                        )
                    if fixed is not None:
                        try:
                            validate_daily_story_json(fixed, phase="full")
                            logger.info(
                                "[DAILY_STORY] Stage3 fixed full criterion "
                                "drift, saved opening regen"
                            )
                            return fixed
                        except ValueError:
                            pass
                if "连说" not in str(exc) or round_i + 1 >= max_open_rounds:
                    break
                logger.warning(
                    "[DAILY_STORY] stitch consecutive after opening "
                    "round=%d/%d: %s; retry opening avoid=%r",
                    round_i + 1,
                    max_open_rounds,
                    exc,
                    avoid,
                )
        assert last_exc is not None
        raise last_exc

    def _design_punchline_blueprint(
        self,
        theme: str,
        *,
        story_type: str | None = None,
    ) -> dict[str, Any] | None:
        """D1.5：Pro 设计短笑点骨架；失败返回 None（降级无卡 D2）。"""
        from app.services.daily_story.story_design import (
            build_punchline_blueprint_prompts,
            clean_blueprint,
            parse_blueprint_response,
            story_plan_enabled,
            validate_punchline_blueprint,
        )

        if not story_plan_enabled(story_type=story_type):
            return None
        try:
            system, user = build_punchline_blueprint_prompts(
                theme,
                story_type=story_type,
            )
        except ValueError as exc:
            logger.warning("[DAILY_STORY] D1.5 skip: %s", exc)
            return None

        last_err = ""
        retry_user = user
        for attempt in range(2):
            try:
                raw, _ = self._chat_json(
                    system,
                    retry_user,
                    model=self._pro_model,
                )
                bp = parse_blueprint_response(raw)
                errors = validate_punchline_blueprint(bp, story_type=story_type)
                if errors:
                    # 确定性格式错误（序号前缀/空条）本地剥掉复检，省一次 Pro
                    bp2, clean_notes = clean_blueprint(
                        bp, story_type=story_type,
                    )
                    if clean_notes:
                        err2 = validate_punchline_blueprint(
                            bp2, story_type=story_type,
                        )
                        if not err2:
                            logger.info(
                                "[DAILY_STORY] D1.5 local clean saved "
                                "Pro retry: %s",
                                "; ".join(clean_notes),
                            )
                            return bp2
                    last_err = "; ".join(errors)
                    retry_user = (
                        f"{user}\n上一稿骨架被拒：{last_err}。"
                        "请修正后重新只输出一个 JSON 对象。"
                    )
                    logger.warning(
                        "[DAILY_STORY] D1.5 blueprint invalid "
                        "attempt=%d/2: %s",
                        attempt + 1,
                        last_err,
                    )
                    continue
                logger.info(
                    "[DAILY_STORY] D1.5 blueprint ok model=%s keys=%s",
                    self._pro_model,
                    ",".join(sorted(bp.keys())),
                )
                return bp
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                logger.warning(
                    "[DAILY_STORY] D1.5 blueprint failed attempt=%d/2: %s",
                    attempt + 1,
                    exc,
                )
        logger.warning(
            "[DAILY_STORY] D1.5 fallback to plain D2: %s",
            last_err or "unknown",
        )
        return None

    def _generate_daily_story_framework(
        self,
        theme: str,
        *,
        story_type: str | None = None,
        avoid_block: str = "",
    ) -> dict[str, Any]:
        """先生成剧本框架（scene_title/setting/conflict_core/key）作定盘锚。

        2026-08-07 架构改造：开场与正文都围绕框架生成。4 字段必须齐全，
        conflict_core ≤24 字、key 2–8 字，失败重抽 1 次。
        """
        from app.services.daily_story.prompts import (
            DAILY_STORY_KEY_CHARS_MAX,
            DAILY_STORY_KEY_CHARS_MIN,
        )
        from app.services.daily_story.story_types import parse_story_type_code

        if not story_type:
            story_type = _select_story_type(theme)
        system, user = build_daily_story_framework_prompts(
            theme,
            story_type=story_type,
        )
        if avoid_block:
            user = f"{user}\n\n{avoid_block}"
        last_exc: ValueError | None = None
        for attempt in range(2):
            try:
                raw, _ = self._chat_json(
                    system,
                    user,
                    thinking_enabled=False,
                    temperature=_TEMP_CREATIVE_HIGH,
                )
                if not isinstance(raw, dict):
                    raise ValueError("框架须为 JSON 对象")
                errors: list[str] = []
                for field in ("scene_title", "setting", "conflict_core", "key"):
                    v = str(raw.get(field) or "").strip()
                    if not v:
                        errors.append(f"缺少字段 {field}")
                    else:
                        raw[field] = v
                cc = str(raw.get("conflict_core") or "").strip()
                if cc and len(cc) > 24:
                    errors.append(f"conflict_core 须≤24字（当前{len(cc)}字）")
                key = str(raw.get("key") or "").strip()
                if key and not (
                    DAILY_STORY_KEY_CHARS_MIN
                    <= len(key)
                    <= DAILY_STORY_KEY_CHARS_MAX
                ):
                    errors.append(
                        f"key 须{DAILY_STORY_KEY_CHARS_MIN}–"
                        f"{DAILY_STORY_KEY_CHARS_MAX}字（当前{len(key)}字）"
                    )
                from app.services.daily_story.story_types.a.opening import (
                    append_a_framework_errors,
                )

                append_a_framework_errors(
                    raw,
                    type_code=parse_story_type_code(story_type=story_type),
                    errors=errors,
                )
                if errors:
                    raise ValueError("; ".join(errors))
                raw["_framework_type"] = story_type
                return raw
            except ValueError as exc:
                last_exc = exc
                if attempt + 1 >= 2:
                    break
                logger.warning(
                    "[DAILY_STORY] framework generation failed "
                    "attempt=%d/2: %s",
                    attempt + 1,
                    exc,
                )
                user = (
                    f"{user}\n\n"
                    f"【重试】上一轮框架未通过：{exc}\n"
                    "补齐缺失字段；conflict_core ≤24 字；key 用 2–8 字标签；"
                    "仍只输出 scene_title/setting/conflict_core/key 四字段 JSON。"
                )
        assert last_exc is not None
        raise last_exc

    def _generate_c_criterion_package(
        self,
        theme: str,
        *,
        avoid_block: str = "",
    ) -> dict[str, Any] | None:
        """C 类台词锚定·第一阶段：生成「昭昭/灿灿各一条规则台词 + 回旋镖原话」。

        专家 2026-08-09 重设计（白名单池 0/4 失败后的治本方案）：判据可选集合
        坍缩到 2 句固定台词，正文强制一字不差说出。代码校验：
        - 两条规则各含至少一个占有系动词，且不命中任何判据正则（接触/操作/
          结果/状态/时序/消耗/开系）；
        - boomerang_quote 必须与 boomerang_source 指向的那条规则**逐字相同**。
        不合格低成本重试 3 次（小 JSON 比整稿快得多）；全败返回 None，正文
        生成走原流程（不阻断）。返回 {"zhaozhao_rule", "cancan_rule",
        "boomerang_quote", "boomerang_source", "trap"}。
        """
        from app.services.daily_story.story_types.c.validate import (
            _RE_CONTACT_CRITERION,
            _RE_CONSUME_CRITERION,
            _RE_OPEN_CRITERION,
            _RE_OPERATE_CRITERION,
            _RE_RESULT_CRITERION,
            _RE_SEQUENCE_CRITERION,
            _RE_STATE_CRITERION,
        )

        _FORBIDDEN = (
            _RE_CONTACT_CRITERION,
            _RE_OPERATE_CRITERION,
            _RE_RESULT_CRITERION,
            _RE_STATE_CRITERION,
            _RE_SEQUENCE_CRITERION,
            _RE_CONSUME_CRITERION,
            _RE_OPEN_CRITERION,
        )
        # 仪式白名单（专家 2026-08-09 死磕细化 + 用户 2026-08-11 定「判据要有张力」）：
        # 占有判据核心动词仍是占有系白名单，允许附加有失败风险的孩子气赌约仪式（单脚站
        # 满十秒/金鸡独立/举过头顶坚持三秒）——正是回旋镖字面反噬的燃料；用户点名禁
        # 「放桌上三秒」这类无张力位置仪式。只禁会拖出 接触/状态/操作系 动作的仪式词：
        # 掏（操作）、坐稳/起身/松手/放手（状态）、掉/洒（状态，酸奶滴落）。「坚持」
        # 「举过头顶」「单脚站满十秒」等时间/身体词不再禁用（合法启动/仪式条件）。
        _RE_RITUAL_GATE = re.compile(r"掏出|坐稳|起身|松手|放手|掉|洒")
        _POSSESSIVE = re.compile(
            r"拿|抢|攥|翻|坐|举|占|归|切|分|搬|拆|选|挑|摆|清点|洗|晾",
        )
        user = (
            f"主题：{theme}\n\n"
            "输出昭昭/灿灿各一条规则台词 + 被反噬原话。"
        )
        if re.search(r"蛋糕|切好|切完|切开|切块|分.{0,2}(?:蛋糕|块)", theme):
            user += (
                "\n\n本主题是切分型资源：判据必须用「切完你先挑/我切你选/你切我选」，"
                "禁止单脚站/举过头顶等身体仪式；trap 写「立规人答应切完先挑后反悔"
                "硬抢/换小块，被对方按字面先挑走大块」。"
            )
        if avoid_block:
            user = f"{user}\n\n{avoid_block}"
        for attempt in range(3):
            raw, _ = self._chat_json(
                _C_CRITERION_PACKAGE_SYSTEM,
                user,
                thinking_enabled=False,
                # 包生成用中温求规则多样（正文才锁 0.4）；禁用动词由代码校验兜底
                temperature=_TEMP_CREATIVE_MID,
                model=self._model,
            )
            if not isinstance(raw, dict):
                logger.warning(
                    "[DAILY_STORY] C criterion package attempt=%d non-dict",
                    attempt + 1,
                )
                continue
            zz = str(raw.get("zhaozhao_rule") or "").strip()
            cc = str(raw.get("cancan_rule") or "").strip()
            bq = str(raw.get("boomerang_quote") or "").strip()
            src = str(raw.get("boomerang_source") or "").strip()
            trap = str(raw.get("trap") or "").strip()
            if not (zz and cc and bq and trap):
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d missing "
                    "fields zz=%r cc=%r bq=%r trap=%r",
                    attempt + 1,
                    zz,
                    cc,
                    bq,
                    trap,
                )
                continue
            if any(r.search(t) for r in _FORBIDDEN for t in (zz, cc)):
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d forbidden "
                    "rule: %s | %s",
                    attempt + 1,
                    zz,
                    cc,
                )
                continue
            if _RE_RITUAL_GATE.search(zz) or _RE_RITUAL_GATE.search(cc):
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d ritual gate "
                    "rule: %s | %s",
                    attempt + 1,
                    zz,
                    cc,
                )
                continue
            if zz == cc:
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d identical "
                    "rules: %s",
                    attempt + 1,
                    zz,
                )
                continue
            if not _POSSESSIVE.search(zz) or not _POSSESSIVE.search(cc):
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d rule missing "
                    "possessive verb: %s | %s",
                    attempt + 1,
                    zz,
                    cc,
                )
                continue
            src_rule = {"zhaozhao_rule": zz, "cancan_rule": cc}.get(src)
            if src_rule is None or bq != src_rule:
                logger.info(
                    "[DAILY_STORY] C criterion package attempt=%d boomerang "
                    "mismatch src=%s bq=%s",
                    attempt + 1,
                    src,
                    bq,
                )
                continue
            logger.info(
                "[DAILY_STORY] C criterion package ok attempt=%d zz=%s cc=%s "
                "bq=%s src=%s",
                attempt + 1,
                zz,
                cc,
                bq,
                src,
            )
            ritual = bool(
                re.search(
                    r"单脚站|金鸡独立|举过头顶|坚持.{0,4}秒|站满十秒|数满十秒",
                    zz + cc + trap,
                )
            )
            if ritual:
                break_script = (
                    "立规人提出仪式规则后，由对方负责数数；数数人故意拖长音"
                    "（一……二……三……），立规人单脚站不住、脚落地；对方用原规反问"
                    "「你刚说站满十秒，又没说数数要多快」当场判输；末句由立规人嘴硬"
                    "收场并锚定仪式动词（明天我定规矩必须快数）。**立规人必须输，"
                    "禁立规人宣布自己赢/站满/酸奶归我**；执行纠纷只用 数快慢/脚落地/"
                    "扶墙，禁 松手/放手/拽/拉扯/碰 当判据。"
                )
            else:
                break_script = (
                    "按动作分派/占有规则字面执行：立规人立规后，对方按字面行使"
                    "优先权（先挑走大块/先选多的/先拿）；立规人反悔硬抢/换条件，"
                    "被对方用原规反问当场判输；末句由立规人嘴硬收场。**立规人必须输，"
                    "禁立规人宣布自己赢/站满/归我**；执行纠纷只用 换/端/抢/抱/藏，"
                    "禁 松手/放手/拽/拉扯/碰 当判据；若立规人说过「挑哪块都一样/"
                    "绝对公平」，回旋镖优先打这句（你刚说挑哪块都一样，我挑了大的，"
                    "你认不认）。"
                )
            return {
                "zhaozhao_rule": zz,
                "cancan_rule": cc,
                "boomerang_quote": bq,
                "boomerang_source": src,
                "trap": trap,
                "break_script": break_script,
            }
        logger.warning(
            "[DAILY_STORY] C criterion package failed after 3 attempts, "
            "body generation proceeds without it"
        )
        return None

    def _generate_daily_story_beats(
        self,
        theme: str,
        *,
        story_type: str | None,
        framework: dict | None,
    ) -> dict:
        """节拍表先导（B 类）：先锁骨架，质量门通过后才进正文展开。"""
        from app.services.daily_story.prompts import (
            build_daily_story_beats_prompts,
            validate_daily_story_beats,
        )

        system, user = build_daily_story_beats_prompts(
            theme,
            story_type=story_type,
            framework=framework,
        )
        last_exc: ValueError | None = None
        for attempt in range(3):
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                temperature=_TEMP_CRITERION_LOCKED,
            )
            if not isinstance(raw, dict):
                last_exc = ValueError("节拍表不是 JSON 对象")
                user = f"{user}\n\n上一版不是 JSON，请严格按键输出。"
                continue
            try:
                validate_daily_story_beats(raw, theme)
                return raw
            except ValueError as exc:
                last_exc = exc
                logger.warning(
                    "[DAILY_STORY] beats gate failed attempt=%d: %s",
                    attempt + 1,
                    exc,
                )
                user = f"{user}\n\n上一版不合格：{exc}\n请修正后重出节拍表。"
        raise last_exc or ValueError("节拍表 3 次未过质量门")

    def _generate_daily_story_body(
        self,
        theme: str,
        *,
        story_type: str | None = None,
        framework: dict | None = None,
        opening: list[dict] | None = None,
        criterion_block: str = "",
        avoid_block: str = "",
        beats: dict | None = None,
    ) -> dict[str, Any]:
        if not story_type:
            story_type = _select_story_type(theme)
        blueprint = self._design_punchline_blueprint(
            theme,
            story_type=story_type,
        )
        # 首稿 draft（含铺垫字数）；重试 revise（只走校验硬卡）
        system, user = build_daily_story_prompts(
            theme,
            story_type=story_type,
            length_mode="draft",
            punchline_blueprint=blueprint,
            framework=framework,
            opening=opening,
            beats=beats,
        )
        # C 类台词锚定（2026-08-09 专家终极方案）：criterion_block 由
        # generate_daily_story 层生成并传入（开场共用同一包），硬注入 user
        # （重试各分支同样注入），并把正文温度降到 0.4 提高遵从。

        def _inject_c_criterion(u: str) -> str:
            # criterion_block + avoid_block 统一注入：首稿与所有重试分支共用，
            # 重试重建 user 时不会再丢锚定块（v35 开场「闹肚子」即漏注入）
            if criterion_block:
                u = f"{u}\n\n{criterion_block}"
            if avoid_block:
                u = f"{u}\n\n{avoid_block}"
            return u

        user = _inject_c_criterion(user)
        last_exc: ValueError | None = None
        # 实验结论：关 thinking + 高温一次即达标（297 字/6.4s），开 thinking
        # 虽更长但慢 36 倍。全部走关 thinking + 高温，靠次数+本地补字兜住。
        # C 类台词锚定注入生效时降温度（专家定 0.4）：约束越硬温度越低，
        # 否则闭集选择会被发散冲垮。
        max_attempts = 3
        prev_story: dict | None = None
        same_err_streak = 0
        prev_err_key = ""
        draft_temp = (
            _TEMP_CRITERION_LOCKED
            if criterion_block
            else (_TEMP_CREATIVE_BLUEPRINT if blueprint else _TEMP_CREATIVE_HIGH)
        )
        for attempt in range(max_attempts):
            # 全程 Flash：关 thinking + 高温，不用 Pro/thinking（太慢）。
            # pro 两轮实测 1/4 更差（v21/v22：过稿质量 47/62 反而更低、慢 2-3 倍），
            # 判据漂移不是换更强模型能解决的，回 flash（v20 基线 2/4、质量 83/84）。
            use_model = self._model
            if attempt > 0:
                logger.info(
                    "[DAILY_STORY] D2 body retry attempt=%d model=%s",
                    attempt + 1,
                    use_model,
                )
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                temperature=draft_temp,
                model=use_model,
            )
            if isinstance(raw, dict):
                from app.services.daily_story.prompts import (
                    try_local_patch_daily_story_body,
                )
                from app.services.daily_story.story_design import (
                    apply_blueprint_to_story,
                )

                raw["_theme"] = theme
                raw["_story_type"] = story_type
                _force_framework_fields(raw, framework)
                # 妈妈句照抄节拍表：正文妈妈句缺短惩罚令时，用 beats.mom_line 覆盖
                if beats and isinstance(raw.get("dialogue"), list):
                    mom_target = str(beats.get("mom_line") or "").strip()
                    if mom_target:
                        for d in reversed(raw.get("dialogue") or []):
                            if isinstance(d, dict) and d.get("speaker") == "妈妈":
                                if not re.search(
                                    r"站好|过来|罚|今晚|别想|拿的什么|交出来|端过来",
                                    str(d.get("line") or ""),
                                ):
                                    d["line"] = mom_target
                                    logger.info(
                                        "[DAILY_STORY] mom line patched from "
                                        "beats (punish missing)",
                                    )
                                break
                # 双人定格确定性补丁：妈妈句（最后一处）之后若无两个不同
                # 姐弟角色的反应，用节拍表 freeze 覆盖收尾（防止仅单人定格）
                if beats and isinstance(raw.get("dialogue"), list):
                    freeze = beats.get("freeze") or []
                    if isinstance(freeze, list) and len(freeze) >= 2:
                        mom_idx = None
                        for i, d in enumerate(raw["dialogue"]):
                            if (
                                isinstance(d, dict)
                                and d.get("speaker") == "妈妈"
                            ):
                                mom_idx = i
                        if mom_idx is not None:
                            after = raw["dialogue"][mom_idx + 1 :]
                            sib = [
                                d
                                for d in after
                                if isinstance(d, dict)
                                and d.get("speaker") in ("昭昭", "灿灿")
                            ]
                            sib_speakers = {
                                d.get("speaker") for d in sib
                            }
                            if len(sib) < 2 or len(sib_speakers) < 2:
                                new_after = [
                                    {
                                        "speaker": x.get("speaker"),
                                        "line": str(x.get("line") or "").strip(),
                                    }
                                    for x in freeze[:2]
                                    if isinstance(x, dict)
                                    and x.get("speaker") in ("昭昭", "灿灿")
                                    and str(x.get("line") or "").strip()
                                ]
                                if len(new_after) >= 2:
                                    raw["dialogue"] = (
                                        raw["dialogue"][: mom_idx + 1]
                                        + new_after
                                    )
                                    logger.info(
                                        "[DAILY_STORY] freeze patched from "
                                        "beats (double-landing missing)",
                                    )
                if blueprint:
                    apply_blueprint_to_story(
                        raw,
                        blueprint,
                        story_type=story_type,
                    )
                patched, patch_notes = try_local_patch_daily_story_body(raw)
                if patch_notes:
                    logger.info(
                        "[DAILY_STORY] local body patch attempt=%d: %s",
                        attempt + 1,
                        ",".join(patch_notes),
                    )
                    raw = patched
                    _force_framework_fields(raw, framework)
                    if blueprint:
                        apply_blueprint_to_story(
                            raw,
                            blueprint,
                            story_type=story_type,
                        )
            try:
                validate_daily_story_json(raw, phase="body")
                if isinstance(raw, dict):
                    raw.pop("_theme", None)
                    raw.pop("_story_type", None)
                    if blueprint:
                        from app.services.daily_story.story_design import (
                            apply_blueprint_to_story,
                        )

                        apply_blueprint_to_story(
                            raw,
                            blueprint,
                            story_type=story_type,
                        )
                return raw
            except ValueError as exc:
                last_exc = exc
                prev_story = raw if isinstance(raw, dict) else prev_story
                # 失败后再本地修一次（针对本轮错误文案能覆盖的缺口）
                if isinstance(prev_story, dict):
                    from app.services.daily_story.prompts import (
                        try_local_patch_daily_story_body,
                    )
                    from app.services.daily_story.story_design import (
                        apply_blueprint_to_story,
                    )

                    prev_story["_theme"] = theme
                    prev_story["_story_type"] = story_type
                    _force_framework_fields(prev_story, framework)
                    if blueprint:
                        apply_blueprint_to_story(
                            prev_story,
                            blueprint,
                            story_type=story_type,
                        )
                    patched2, notes2 = try_local_patch_daily_story_body(prev_story)
                    if notes2:
                        try:
                            if blueprint:
                                apply_blueprint_to_story(
                                    patched2,
                                    blueprint,
                                    story_type=story_type,
                                )
                            _force_framework_fields(patched2, framework)
                            validate_daily_story_json(patched2, phase="body")
                            logger.info(
                                "[DAILY_STORY] local body patch saved LLM "
                                "retry: %s",
                                ",".join(notes2),
                            )
                            if isinstance(patched2, dict):
                                patched2.pop("_theme", None)
                                patched2.pop("_story_type", None)
                            return patched2
                        except ValueError:
                            prev_story = patched2
                errors = str(exc).removeprefix("daily_story 校验失败: ")
                # Stage 3 判据链安全网（专家 2026-08-09）：判据漂移时先单句重写
                # 漏网漂移句回白名单动词，成功即返回，不必整稿重抽。
                if "判据漂移" in errors and isinstance(prev_story, dict):
                    try:
                        fixed = self._stage3_fix_c_criterion_drift(
                            prev_story,
                            theme=theme,
                            avoid_block=avoid_block,
                        )
                    except Exception as exc3:  # noqa: BLE001
                        fixed = None
                        logger.warning(
                            "[DAILY_STORY] Stage3 fix raised: %s",
                            exc3,
                        )
                    if fixed is not None:
                        if isinstance(fixed, dict):
                            fixed.pop("_theme", None)
                            fixed.pop("_story_type", None)
                        logger.info(
                            "[DAILY_STORY] Stage3 fixed criterion drift "
                            "attempt=%d, saved full regen",
                            attempt + 1,
                        )
                        return fixed
                if "大人例外" in errors and isinstance(prev_story, dict):
                    try:
                        fixed_e = self._stage3_fix_e_adult_exception(
                            prev_story,
                            theme=theme,
                        )
                    except Exception as exc_e:  # noqa: BLE001
                        fixed_e = None
                        logger.warning(
                            "[DAILY_STORY] E adult-exception fix raised: %s",
                            exc_e,
                        )
                    if fixed_e is not None:
                        if isinstance(fixed_e, dict):
                            fixed_e.pop("_theme", None)
                            fixed_e.pop("_story_type", None)
                        logger.info(
                            "[DAILY_STORY] Stage3 fixed E adult exception "
                            "attempt=%d, saved full regen",
                            attempt + 1,
                        )
                        return fixed_e
                # 跑题稿是毒样本：丢掉上一稿，重试走全新首稿而非修订
                if "正文跑题" in errors:
                    prev_story = None
                # 同一硬伤连撞 2 次即停：整稿重抽对大人例外这类槽位错误收益低
                err_key = (
                    "A偷吃"
                    if "A类偷吃" in errors or "检样不算开饭" in errors
                    else errors[:48]
                )
                if err_key == prev_err_key:
                    same_err_streak += 1
                else:
                    same_err_streak = 1
                    prev_err_key = err_key
                if attempt + 1 >= max_attempts or same_err_streak >= 2:
                    logger.warning(
                        "[DAILY_STORY] generate story body validation failed "
                        "attempt=%d/%d streak=%d: %s",
                        attempt + 1,
                        max_attempts,
                        same_err_streak,
                        exc,
                    )
                    break
                logger.warning(
                    "[DAILY_STORY] generate story body validation failed "
                    "attempt=%d/%d: %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                # 重试按错误文案+字数分向；非字数问题走 revise 保篇幅
                length_mode = resolve_daily_story_retry_length_mode(
                    prev_story if isinstance(prev_story, dict) else None,
                    errors=errors,
                    story_type=story_type,
                )
                system, _ = build_daily_story_prompts(
                    theme,
                    story_type=story_type,
                    length_mode=length_mode,
                    punchline_blueprint=blueprint,
                    framework=framework,
                    opening=opening,
                    beats=beats,
                )
                if isinstance(prev_story, dict):
                    user = build_daily_story_retry_user(
                        theme,
                        prev_story=prev_story,
                        errors=errors,
                        phase="body",
                        story_type=story_type,
                    )
                    if beats and beats.get("division"):
                        user = (
                            f"【分工钉死（不许换手）】{beats.get('division')}"
                            "——可围绕该分工自然化表达，但角色与任务对应关系"
                            "必须完全保持\n\n"
                            f"{user}"
                        )
                    if framework or opening:
                        from app.services.daily_story.prompts import (
                            _daily_story_anchor_block,
                        )

                        anchor = _daily_story_anchor_block(
                            framework=framework,
                            opening=opening,
                        )
                        if anchor:
                            user = f"{anchor}\n\n{user}"
                    if blueprint:
                        from app.services.daily_story.story_design import (
                            expansion_outline_for,
                            format_blueprint_block,
                        )

                        user = (
                            f"{format_blueprint_block(blueprint)}\n\n"
                            f"{expansion_outline_for(blueprint, story_type=story_type)}\n\n"
                            f"{user}"
                        )
                    user = _inject_c_criterion(user)
                else:
                    user = (
                        f"{build_daily_story_prompts(theme, story_type=story_type, length_mode=length_mode, punchline_blueprint=blueprint, framework=framework, opening=opening, beats=beats)[1]}\n\n"
                        f"【重试】上一轮校验未通过：{errors}\n"
                        "请直接输出符合硬约束的完整 JSON（正文勿写发现开场）。"
                    )
                    user = _inject_c_criterion(user)
        assert last_exc is not None
        # 诊断：把最后一次被拒稿挂到异常上，便于上层/测试定位硬卡失败原因
        if isinstance(prev_story, dict):
            last_exc._failed_body = prev_story  # type: ignore[attr-defined]
        raise last_exc

    def _stage3_fix_c_criterion_drift(
        self,
        story: dict[str, Any],
        *,
        theme: str = "",
        avoid_block: str = "",
    ) -> dict[str, Any] | None:
        """Stage 3 判据链安全网（专家 2026-08-09 死磕重设计）。

        专家结论：两句固定台词锚定压不住中段自创判据（v19-v22 2/4 卡死在这），
        阶段三不是「改回锚定台词」而是「判据链安全网」——把漏网的漂移判据句
        单句重写为只用占有系白名单动词（可附加纯时长/纯位置仪式），替换后复检。

        逻辑（对齐专家 4）：
        1. 提取疑似判据句：含「谁先/归谁/才算/算你的」等宣示规则模式的句子。
        2. 动词过滤：命中判据正则（接触/操作/结果/状态/时序/消耗/开系）即漂移句。
        3. 单句重写：每句调 LLM 生成 3 个候选，正则选出完全无黑名单动词的替换原文。
        4. 复检全文判据句 + validate phase=body，通过才返回。
        任一失败返回 None（交由上层整稿重抽兜底）。
        """
        from app.services.daily_story.prompts import (
            _clone_story,
            validate_daily_story_json,
        )
        from app.services.daily_story.story_types.c.validate import (
            _RE_CONTACT_CRITERION,
            _RE_CONSUME_CRITERION,
            _RE_OPEN_CRITERION,
            _RE_OPERATE_CRITERION,
            _RE_RESULT_CRITERION,
            _RE_SEQUENCE_CRITERION,
            _RE_STATE_CRITERION,
        )

        _FORBIDDEN = (
            _RE_CONTACT_CRITERION,
            _RE_OPERATE_CRITERION,
            _RE_RESULT_CRITERION,
            _RE_STATE_CRITERION,
            _RE_SEQUENCE_CRITERION,
            _RE_CONSUME_CRITERION,
            _RE_OPEN_CRITERION,
        )
        # 疑似判据句：宣示归属/规则的句子里命中判据正则 → 漂移候选
        _RE_CRITERION_LIKE = re.compile(
            r"谁先|谁|归谁|归我|算我的|算你的|归你|才算|算数|算赢|"
            r"该我|该你|赢|输|拿到|抢到|攥|翻开|坐上|举起|举过头顶",
        )
        _POSSESSIVE = re.compile(r"拿|抢|攥|翻|坐|举|占|归")

        dialogue = story.get("dialogue")
        if not isinstance(dialogue, list) or not dialogue:
            return None

        # 1+2：提取漂移判据句（命中判据正则是硬信号；「谁先」句漏判据正则也查白名单缺失）
        drift_idxs: list[int] = []
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                continue
            ln = str(item.get("line") or "").strip()
            if not ln:
                continue
            if not _RE_CRITERION_LIKE.search(ln):
                continue
            if any(r.search(ln) for r in _FORBIDDEN):
                drift_idxs.append(i)
                continue
            # 明显宣示规则（谁先X归Y/得X才算）但没有任何占有系白名单动词 → 漂移
            if re.search(r"(?:谁先.{0,8}归谁|得.{0,8}才算|先.{0,6}(?:的|了))", ln):
                if not _POSSESSIVE.search(ln):
                    drift_idxs.append(i)

        if not drift_idxs:
            return None

        # 3：逐句单句重写（每句最多重写 3 次；一次成功即替换）
        rewrite_system = """\
你是「昭昭&灿灿」日常短剧 C 类（公平执念）的台词修稿器。只改一句对白中的
「规则宣告/判定归属」部分：
- 判据核心动词只用占有系白名单：拿到/抢到/攥在手里/举起/翻开/坐上。
- 可附加孩子气赌约仪式（单脚站满十秒/金鸡独立站满十秒/举过头顶坚持三秒）；
  **禁「放桌上三秒」这类没张力的仪式**（用户 2026-08-11 点名）。
- 不得引入 碰/摸/松手/掉/洒/打开/撕/掏/按/喝/咬/动/跑 等动作当判据；别写「站够」。
- 保持原句气势、角色立场、说话人语气；字数尽量相近（±4 字）。
只输出改写后的完整一句对白，不要解释、不要 JSON。"""
        if avoid_block:
            rewrite_system = f"{rewrite_system}\n{avoid_block.strip()}"
        # 避雷词表：与 _build_story_avoid_block 的「- A、B、C」行同格式解析
        _avoid_items: list[str] = []
        m = re.search(r"\n- (.+)$", avoid_block)
        if m:
            _avoid_items = [x.strip() for x in m.group(1).split("、") if x.strip()]
        out = _clone_story(story)
        fixed_any = False
        for idx in drift_idxs:
            ln = str(out["dialogue"][idx].get("line") or "").strip()
            candidate = None
            for _ in range(3):
                try:
                    content, _ = self._chat(
                        rewrite_system,
                        f"原句：{ln}\n改写后：",
                        json_mode=False,
                        thinking_enabled=False,
                        temperature=_TEMP_CRITERION_LOCKED,
                        model=self._model,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[DAILY_STORY] Stage3 rewrite llm fail idx=%d: %s",
                        idx,
                        exc,
                    )
                    break
                cand = (content or "").strip().strip("「」\"'“”")
                if not cand:
                    continue
                if any(r.search(cand) for r in _FORBIDDEN):
                    continue
                if not _POSSESSIVE.search(cand):
                    continue
                if any(a and a in cand for a in _avoid_items):
                    continue
                candidate = cand
                break
            if candidate:
                out["dialogue"][idx]["line"] = candidate
                fixed_any = True
                logger.info(
                    "[DAILY_STORY] Stage3 rewrite idx=%d: %r -> %r",
                    idx,
                    ln,
                    candidate,
                )
        if not fixed_any:
            return None

        # 4：复检全文判据句 + 整稿 validate
        for item in out["dialogue"]:
            ln = str(item.get("line") or "").strip()
            if ln and _RE_CRITERION_LIKE.search(ln) and any(
                r.search(ln) for r in _FORBIDDEN
            ):
                return None
        try:
            validate_daily_story_json(out, phase="body")
        except ValueError as exc:
            logger.info(
                "[DAILY_STORY] Stage3 fixed story still invalid: %s",
                exc,
            )
            return None
        return out

    def _stage3_fix_e_adult_exception(
        self,
        story: dict[str, Any],
        *,
        theme: str = "",
    ) -> dict[str, Any] | None:
        """E 大人例外超标：先本地定点改，仍不过再单句 LLM，禁止整稿重抽。"""
        from app.services.daily_story.prompts import (
            _clone_story,
            validate_daily_story_json,
        )
        from app.services.daily_story.story_types.e.patch import (
            patch_e_adult_exception_overrun,
        )
        from app.services.daily_story.story_types.e.validate import (
            is_cancan_adult_exception_line,
        )

        out = _clone_story(story)
        notes = patch_e_adult_exception_overrun(out)
        if notes:
            try:
                validate_daily_story_json(out, phase="body")
                logger.info(
                    "[DAILY_STORY] E adult-exception local patch: %s",
                    ",".join(notes),
                )
                return out
            except ValueError:
                pass

        dialogue = out.get("dialogue")
        if not isinstance(dialogue, list):
            return None
        speakers = [
            str(d.get("speaker") or "") if isinstance(d, dict) else ""
            for d in dialogue
        ]
        lines = [
            str(d.get("line") or "") if isinstance(d, dict) else ""
            for d in dialogue
        ]
        adult_hits = [
            i
            for i, (sp, ln) in enumerate(zip(speakers, lines))
            if is_cancan_adult_exception_line(sp, ln)
        ]
        mom_idx = [i for i, sp in enumerate(speakers) if sp == "妈妈"]
        mid_mom = mom_idx[-2] if len(mom_idx) >= 3 else None
        keep: set[int] = set()
        kept = 0
        for i in adult_hits:
            if mid_mom is not None and i > mid_mom:
                continue
            if kept < 2:
                keep.add(i)
                kept += 1
        rewrite_idxs = [i for i in adult_hits if i not in keep]
        if not rewrite_idxs:
            return None

        rewrite_system = """\
你是日常短剧 E 类台词修稿器。只改这一句灿灿假帮腔：
- 禁止出现「大人」「小孩」「孩子不一样」「规矩给小孩」。
- 优先删掉原句里「大人…」那截，留下后半句帮腔；后半不够再重写。
- 重写须接上一句孩子的物证做轻描开脱；禁止空指代套话
  （勿「当场那个还在」「痕迹还在呢」「哪能算按规矩做完」）。
- 保持讽刺帮腔口吻，不要训妈妈，不要抢闭环。
只输出改写后的完整一句，不要解释。"""
        if theme:
            rewrite_system = f"{rewrite_system}\n主题：{theme}"
        for idx in rewrite_idxs:
            ln = str(out["dialogue"][idx].get("line") or "").strip()
            prev = ""
            if idx > 0 and isinstance(out["dialogue"][idx - 1], dict):
                prev = str(out["dialogue"][idx - 1].get("line") or "").strip()
            candidate = None
            for _ in range(2):
                try:
                    user = f"原句：{ln}\n改写后："
                    if prev:
                        user = f"上一句：{prev}\n{user}"
                    content, _ = self._chat(
                        rewrite_system,
                        user,
                        json_mode=False,
                        thinking_enabled=False,
                        temperature=_TEMP_CREATIVE_HIGH,
                        model=self._model,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[DAILY_STORY] E adult rewrite llm fail idx=%d: %s",
                        idx,
                        exc,
                    )
                    break
                cand = str(content or "").strip().splitlines()[0].strip(" \"'")
                if not cand or is_cancan_adult_exception_line("灿灿", cand):
                    continue
                candidate = cand
                break
            if not candidate:
                return None
            out["dialogue"][idx]["line"] = candidate
        try:
            validate_daily_story_json(out, phase="body")
        except ValueError as exc:
            logger.info(
                "[DAILY_STORY] E adult-exception rewrite still invalid: %s",
                exc,
            )
            return None
        return out

    def _revise_daily_story_body(
        self,
        theme: str,
        prev_story: dict[str, Any],
        revision_hints: str,
        *,
        max_attempts: int = 2,
        avoid_block: str = "",
    ) -> dict[str, Any]:
        """定向修订：保持骨架，只修补短板。"""
        from app.services.daily_story.prompts import (
            DAILY_STORY_BODY_CHARS_MIN,
            DAILY_STORY_BODY_CHARS_MAX,
            DAILY_STORY_LINE_CHARS_MAX,
            build_daily_story_prompts,
            build_daily_story_retry_user,
            resolve_daily_story_retry_length_mode,
            try_local_patch_daily_story_body,
            validate_daily_story_json,
        )
        import json

        punch = str(prev_story.get("punchline_explain") or "")
        from app.services.daily_story.story_types import parse_story_type_code, story_type_tag

        rev_code = parse_story_type_code(punchline=punch)
        rev_type = story_type_tag(rev_code)
        system, _ = build_daily_story_prompts(
            theme, story_type=rev_type, length_mode="revise",
        )
        preserve_note = ""
        if rev_code == "D":
            preserve_note = (
                "【D类·必留硬卡】上一稿已过校验的招牌话不许丢："
                "中段昭昭「按你说的/你说…我就…」字面原话、回旋镖「你自己说」"
                "+逐字引前段叮嘱原话、灿灿搞砸前禁拆穿、句数 15–17。"
                "只修点名的那条短板，其余原文保留，禁止整段重写。\n"
            )
        base_user = (
            f"主题：{theme}\n"
            f"【字数硬卡】正文 {DAILY_STORY_BODY_CHARS_MIN}–{DAILY_STORY_BODY_CHARS_MAX} 字；"
            f"每句 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；只修补不扩写。\n"
            f"【核心原则】保留对话骨架，只修补下面**一条**短板（做完即停）。"
            f"禁止推翻重写、禁止另起冲突。\n\n"
            f"{preserve_note}"
            f"【待修补】\n{revision_hints}\n\n"
            f"【上一稿】\n{json.dumps(prev_story, ensure_ascii=False)}\n\n"
            "请输出修订后的完整 JSON，格式与上一稿一致。"
        )
        if avoid_block:
            base_user = f"{base_user}\n\n{avoid_block}"
        user = base_user
        last_exc: ValueError | None = None

        for attempt in range(max_attempts):
            # 质量修订：Flash + 关 thinking，按短板改，不走首稿高发散；
            # 不用 Pro（Pro+thinking 曾产出 268 短稿且白烧 ~170s）
            if attempt == 0:
                logger.info(
                    "[DAILY_STORY] D2 quality revise model=%s",
                    self._model,
                )
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                model=self._model,
            )
            if isinstance(raw, dict):
                raw["_theme"] = theme
                _force_framework_fields(raw, prev_story)
                patched, notes = try_local_patch_daily_story_body(raw)
                if notes:
                    logger.info(
                        "[DAILY_STORY] local patch on quality revise: %s",
                        ",".join(notes),
                    )
                    raw = patched
                    _force_framework_fields(raw, prev_story)
            try:
                # _theme 留到校验后再弹出：贴题硬卡要用
                validate_daily_story_json(raw, phase="body")
                if isinstance(raw, dict):
                    raw.pop("_theme", None)
                return raw
            except ValueError as exc:
                last_exc = exc
                if isinstance(raw, dict):
                    _force_framework_fields(raw, prev_story)
                    patched2, notes2 = try_local_patch_daily_story_body(raw)
                    if notes2:
                        try:
                            _force_framework_fields(patched2, prev_story)
                            validate_daily_story_json(patched2, phase="body")
                            patched2.pop("_theme", None)
                            return patched2
                        except ValueError:
                            raw = patched2
                if attempt + 1 >= max_attempts:
                    break
                errors = str(exc).removeprefix("daily_story 校验失败: ")
                logger.warning(
                    "[DAILY_STORY] quality revise validation failed "
                    "attempt=%d/%d: %s",
                    attempt + 1, max_attempts, errors,
                )
                # 用已有重试机制处理字数等格式问题
                length_mode = resolve_daily_story_retry_length_mode(
                    raw if isinstance(raw, dict) else None,
                    errors=errors,
                    story_type=rev_type,
                )
                system, _ = build_daily_story_prompts(
                    theme, story_type=rev_type, length_mode=length_mode,
                )
                user = build_daily_story_retry_user(
                    theme,
                    prev_story=raw if isinstance(raw, dict) else prev_story,
                    errors=errors,
                    story_type=rev_type,
                )
                # 把质量提示词追加到 error feedback 后面
                user += f"\n\n【同时修补】\n{revision_hints}"
        assert last_exc is not None
        # 诊断：把最后一次被拒修订稿挂到异常上
        if isinstance(raw, dict):
            last_exc._failed_body = raw  # type: ignore[attr-defined]
        raise last_exc

    def _generate_daily_story_opening(
        self,
        theme: str,
        framework: dict[str, Any],
        *,
        avoid_speaker: str | None = None,
        story_type: str | None = None,
        criterion_block: str = "",
        avoid_block: str = "",
    ) -> list[dict]:
        """基于剧本框架生成开场 2 句。

        2026-08-07 架构改造：开场吃 framework（scene_title/setting/
        conflict_core），不再依赖 body——body 此时尚未生成。
        criterion_block：C 类台词锚定注入块；开场也注入，开场立的规才
        不会用禁用动词当判据（v19 开场漂移[1]教训）。
        """
        from app.services.daily_story.story_types import parse_story_type_code

        framework = framework or {}
        open_type = parse_story_type_code(
            story_type=story_type,
            punchline=str(framework.get("punchline_explain") or ""),
        )
        system, user = build_daily_story_opening_prompts(
            theme,
            framework,
            type_code=open_type,
        )
        if criterion_block:
            user = f"{user}\n\n{criterion_block}"
        if avoid_block:
            user = f"{user}\n\n{avoid_block}"
        avoid = (avoid_speaker or "").strip() or None
        if avoid in ("昭昭", "灿灿"):
            other = "灿灿" if avoid == "昭昭" else "昭昭"
            user = (
                f"{user}\n\n"
                f"【说话人】开场末句须是「{other}」"
                f"（正文以「{avoid}」起句，避免拼后连说）。"
            )
        last_exc: ValueError | None = None
        max_attempts = max(1, min(2, get_settings().script_qa_max_attempts))
        core = str(framework.get("conflict_core") or "")
        setting = str(framework.get("setting") or "")
        for attempt in range(max_attempts):
            try:
                # 开场短约束：关 thinking，快失败快重试
                raw, _ = self._chat_json(
                    system, user, thinking_enabled=False,
                )
                opening_raw = raw.get("opening") if isinstance(raw, dict) else None
                opening = validate_daily_story_opening(
                    opening_raw,
                    conflict_core=core,
                    setting=setting,
                    type_code=open_type,
                )
                if (
                    avoid in ("昭昭", "灿灿")
                    and opening
                    and opening[-1].get("speaker") == avoid
                ):
                    raise ValueError(
                        "daily_story 开场校验失败: "
                        f"开场末句不可与正文首句同为「{avoid}」"
                    )
                return opening
            except ValueError as exc:
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    break
                errors = str(exc).removeprefix("daily_story 开场校验失败: ")
                logger.warning(
                    "[DAILY_STORY] generate opening validation failed "
                    "attempt=%d/%d: %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                user = build_daily_story_opening_retry_user(
                    theme,
                    framework,
                    errors=errors,
                    avoid_speaker=avoid,
                    type_code=open_type,
                )
                # 重试重建 user 会丢锚定块，重新注入（否则重试稿可能用禁用
                # 动词当判据 / 撞避雷元素，v35 开场「闹肚子」即此漏）
                if criterion_block:
                    user = f"{user}\n\n{criterion_block}"
                if avoid_block:
                    user = f"{user}\n\n{avoid_block}"
        assert last_exc is not None
        raise last_exc

    def review_daily_story_issues(
        self,
        theme: str,
        story: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """审读一次：以读者身份逐句挑硬伤，同时评好笑分，合并一次调用。

        返回 (issues, humor)；humor = {funny_score, best_moment, humor_type}
        或 None（LLM 未给合法好笑字段时降级为旧行为）。
        """
        from app.services.daily_story.review import (
            build_review_prompts,
            parse_humor,
            parse_review_issues,
        )

        system, user = build_review_prompts(theme, story)
        try:
            # 审读关 thinking：单遍+程序本地检已够用，开 thinking 动辄数分钟
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                temperature=0.0,
            )
        except ValueError as exc:
            logger.warning("[DAILY_STORY] review call failed: %s", exc)
            return [], None
        n_lines = len(story.get("dialogue") or [])
        return (
            parse_review_issues(raw, line_count=n_lines),
            parse_humor(raw),
        )

    def spot_fix_daily_story(
        self,
        theme: str,
        story: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """定点修一次：只回被点出的行，落盘与降级由 review 模块决定。"""
        from app.services.daily_story.prompts import DAILY_STORY_LINE_CHARS_MAX
        from app.services.daily_story.review import build_spot_fix_prompts

        system, user = build_spot_fix_prompts(
            theme,
            story,
            issues,
            line_chars_max=DAILY_STORY_LINE_CHARS_MAX,
        )
        try:
            raw, _ = self._chat_json(system, user)
        except ValueError as exc:
            logger.warning("[DAILY_STORY] spot fix call failed: %s", exc)
            return {}
        return raw

    def check_local_coherence(
        self,
        prev: str,
        revised: str,
        next_line: str,
    ) -> bool:
        """定点修后的局部衔接快验：返回 False 表示修改句与前后句断裂。"""
        from app.services.daily_story.review import (
            build_local_coherence_prompts,
        )

        system, user = build_local_coherence_prompts(
            prev,
            revised,
            next_line,
        )
        try:
            raw, _ = self._chat_json(
                system,
                user,
                thinking_enabled=False,
                temperature=0.0,
            )
        except ValueError as exc:
            logger.warning("[DAILY_STORY] local coherence check failed: %s", exc)
            return True
        if isinstance(raw, dict):
            return bool(raw.get("coherent", True))
        return True

    def polish_daily_story_wording(
        self,
        theme: str,
        story: dict[str, Any],
        issues: list[dict[str, Any]],
        *,
        type_code: str | None = None,
        full_scan: bool = False,
    ) -> dict[str, Any]:
        """童语化润色一次：只回被点行的口语化改写，落盘由 review 模块决定。"""
        from app.services.daily_story.prompts import DAILY_STORY_LINE_CHARS_MAX
        from app.services.daily_story.review import (
            build_wording_polish_prompts,
        )

        system, user = build_wording_polish_prompts(
            theme,
            story,
            issues,
            type_code=type_code,
            line_chars_max=DAILY_STORY_LINE_CHARS_MAX,
            full_scan=full_scan,
        )
        try:
            raw, _ = self._chat_json(system, user)
        except ValueError as exc:
            logger.warning("[DAILY_STORY] wording polish call failed: %s", exc)
            return {}
        return raw

    def generate_daily_story_themes(
        self,
        count: int = 15,
        *,
        avoid: list[str] | None = None,
    ) -> list[dict]:
        from app.repositories import repo_daily_story
        from app.services.daily_story.prompts import (
            allocate_theme_type_quotas,
            build_daily_story_theme_prompts,
            filter_writable_themes,
            merge_theme_story_types,
            parse_typed_theme_lines,
            select_themes_by_quota,
        )

        n = max(1, min(int(count), 20))
        recent: list[str] = []
        try:
            recent = repo_daily_story.list_recent_themes(40)
        except Exception as exc:  # noqa: BLE001 — 出题不因读库失败中断
            logger.warning("[DAILY_STORY] list_recent_themes failed: %s", exc)

        recent_keys: list[str] = []
        try:
            recent_keys = repo_daily_story.list_recent_keys(40)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DAILY_STORY] list_recent_keys failed: %s", exc)

        avoid_all: list[str] = []
        seen_avoid: set[str] = set()
        for raw in [*(avoid or []), *recent, *recent_keys]:
            t = str(raw or "").strip()
            if not t or t in seen_avoid:
                continue
            seen_avoid.add(t)
            avoid_all.append(t)

        quotas = allocate_theme_type_quotas(n)
        # 多要一点，过滤近义后仍够配额
        ask = min(n + 5, 25)
        ask_quotas = allocate_theme_type_quotas(ask)
        system, user = build_daily_story_theme_prompts(
            ask,
            avoid=avoid_all,
            quotas=ask_quotas,
        )
        content, _ = self._chat(
            system,
            user,
            json_mode=False,
            thinking_enabled=False,
            temperature=_TEMP_CREATIVE_HIGH,
        )
        typed = parse_typed_theme_lines(content)
        picked = select_themes_by_quota(typed, quotas, avoid=avoid_all)
        if len(picked) < n:
            # 兜底：把解析出的纯主题再滤一遍补齐
            plain = [t for _codes, t in typed]
            codes_by_theme = {
                t: list(codes) for codes, t in typed if codes and t
            }

            def _primary_count(code: str) -> int:
                return sum(
                    1
                    for r in picked
                    if (r.get("story_types") or [""])[0] == code
                )

            extra = filter_writable_themes(
                plain,
                avoid=[*avoid_all, *[r["theme"] for r in picked]],
            )
            for t in extra:
                if len(picked) >= n:
                    break
                declared = codes_by_theme.get(t) or []
                if not declared:
                    st = next(
                        (
                            c
                            for c in ("A", "B", "C", "D", "E")
                            if _primary_count(c) < int(quotas.get(c) or 0)
                        ),
                        "C",
                    )
                    declared = [st]
                types = merge_theme_story_types(t, declared=declared)
                picked.append({"theme": t, "story_types": types})
        if len(picked) < n:
            logger.warning(
                "[DAILY_STORY] theme quota short got=%d want=%d",
                len(picked),
                n,
            )
        return picked[:n]
