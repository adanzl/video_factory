"""分镜画面概述规则与构建函数。"""

from __future__ import annotations

# ── JSON 样例 ─────────────────────────────────────────────────────

_VISUAL_BRIEF_JSON_EXAMPLE_FULL = """{
  "segments": [
    {"segment_index": 1, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"},
    {"segment_index": 2, "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""

_VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL = """{
  "segments": [
    {"segment_index": 2, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"}
  ]
}

注意：仅输出标记为【需生成】的 segment；【仅上下文】无需输出；不要修改各段 text。"""


# ── builders（常量须在上方）───────────────────────────────────────

from typing import Any
import re

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
)

from app.services.script.prompt_common import (
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
    supplementary_system_clause,
)
from app.services.script.voiceover_standard.styles import resolve_style_rules


_DAILY_VISUAL_ROLE = "你是日常亲子对话短剧的分镜画面设计师。"

_VISUAL_BRIEF_CONTENT_RULE = (
    "visual_brief 为该镜画面描述（80-150 字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与氛围，帮助后续扩写文生图提示词；"
    "不写镜头焦距、光线方向、材质参数等细节。"
)

# daily：visual_brief 直接进入规则拼装 image_prompt，不再二次 LLM 扩写
_DAILY_VISUAL_BRIEF_CONTENT_RULE = (
    "visual_brief 为该镜核心场景描述（100-200 字），将直接拼入文生图提示词，"
    "须写满可出图细节，禁止空泛概述；写成一段连贯中文，禁用小标题。"
    "须覆盖：地点陈设、人物动作表情、冲突道具（三者融在正文里，勿分条）。"
    "【地点】开头写清具体室内地点（与全片 setting 一致，如客厅沙发/茶几旁），"
    "写至少 2 个可见陈设物品；禁止「蜡笔彩虹/涂鸦色块背景」代替真实房间。"
    "【人物关系】须对标本段 dialogue 谁在质问/谁在辩解："
    "质问方动作更进攻（指/瞪/叉腰），辩解方更防御（摊手/耸肩/撇嘴）；"
    "禁止双方动作表情对调或都站桩。"
    "【站位】两人及以上同框时必须写清「画面左边是A，右边是B」，"
    "再按左→右分别写各自动作表情；禁止只写动作不写左右"
    "（否则出图常把指责方画到左边另一个人身上）。"
    "【单帧定格】每角色仅写一组动作表情（一个姿势）；"
    "本镜有多句对白时，只取冲突最强的一瞬，禁止同一角色写两段动作"
    "（如先写昭昭比划再吃冰棍、又写昭昭双手叉腰）。"
    "站位须与人物关系一致：质问/进攻方在左、辩解/防御方在右"
    "（或按对白先后：先发言者在左）；左右与动作禁止对调。"
    "【人物】只写动作姿态与面部表情"
    "（瞪圆眼、撇嘴、叉腰、身体前倾、摊手耸肩等），强度对标本段台词语气；"
    "禁止面无表情站桩；禁止写发型/服装/鞋帽（外貌由系统硬编码注入）。"
    "【道具】冲突道具只能用台词已出现的物件与状态，禁止编造台词没有的衣物品类/颜色；"
    "例：台词说「刚叠好的衣服怎么皱成一团了」→ 画面写「沙发上原本叠好的衣服已被揉皱成一团」，"
    "禁止写成「皱成一团的刚叠好的衣服」（自相矛盾）；"
    "禁止写成粉色卫衣/蓝色T恤/牛仔裤等具体款式"
    "（蓝T恤是昭昭身上穿的，粉卫衣是灿灿身上穿的，不能当道具）；"
    "禁止输出「冲突道具：」「地点：」「人物：」等冒号小标题。"
    "【服装色禁令】粉色卫衣=灿灿身上穿的、蓝色T恤=昭昭身上穿的、米色上衣=妈妈身上穿的，"
    "三者禁止出现在道具/衣堆描述里（否则出图会把角色衣服画成道具或换装）；"
    "台词未点名款式时只用「衣服/衣物堆/皱成一团的衣服」泛称。"
    "【开场首镜】segment_index=1 且 shot_type=特写时，"
    "须定格冲突峰值姿势（抢/举/夺/藏/指着的最大一瞬），"
    "表情再夸张一档；禁止全景空镜或平淡站桩开场。"
    "【事实一致】与台词事实严格一致，先核对 dialogue 再写画面："
    "台词说刚叠好却皱成一团→须画「原本叠好、现已揉皱成一团」的衣服，"
    "禁止仍画整齐衣堆，也禁止「皱成一团的刚叠好的衣服」这种矛盾定语；"
    "台词说碰了一下/没弄皱→辩解方须无辜摊手耸肩，禁止画成承认弄皱；"
    "禁止与台词矛盾（说乱却写整齐、说没有却画出有、台词未提的款式颜色）。"
    "【禁写】画风/笔触/色彩风格（系统硬编码）；"
    "光线方向与构图景别（系统按规则补）；"
    "禁止「竖构图/横屏/调整为」等元叙述；"
    "禁止心理旁白引号（如「不关我事」），只写可见表情动作。"
    "正例（对白：灿灿抱怨刚叠好的衣服皱成一团；昭昭说只碰一下没弄皱）："
    "'客厅沙发上，原本叠好的衣服已被揉皱成一团；"
    "画面左边是灿灿，右边是昭昭；"
    "灿灿右手食指指向身前那团皱衣服，左手叉腰，瞪圆眼睛嘴巴大张；"
    "昭昭双手摊开耸肩，撇着嘴角一脸无辜。"
    "茶几上放着空水杯，沙发扶手搭着叠衣板。'"
)

_EMOTION_RULE_DIALOGUE = (
    "情绪须对标台词语气强度（争吵时表情激烈如瞪眼皱眉张嘴、温和平静时表情放松）。"
)

_EMOTION_RULE_NARRATION = (
    "氛围与本段口播语气一致，点到即可，勿夸张表演或堆砌表情描写。"
)

_DAILY_CAST_RULE = (
    "【角色入画】本段画面人物必须且仅等于 dialogue 中的发言角色"
    "（speaker 去重后的集合）；未发言角色禁止以任何形式入画"
    "（旁观、路过、背景、另一房间等都不允许）。"
    "台词中提及某人姓名不等于其在该段发言；仅以 dialogue.speaker 为准。"
    "妈妈同样遵守：仅 speaker=\"妈妈\" 时才可入画；"
    "若该段无人发言，visual_brief 禁止出现昭昭/灿灿/妈妈等人像，只写场景。"
)

_DAILY_SETTING_RULE = (
    "【地点锚点】全片 setting 已给定（如客厅）；"
    "每镜 visual_brief 须落在该地点或其可见角落（沙发/茶几/书桌/门口），"
    "禁止换成学校/公园等外景。"
)

_MOM_DIALOGUE_RULE = (
    "【角色约束】妈妈角色只在该段有妈妈台词（dialogue中speaker=\"妈妈\"）时才出现在画面中；"
    "若该段dialogue数组中没有speaker为妈妈的项，则visual_brief绝对禁止出现妈妈（包括不让妈妈旁观、路过、做背景动作、"
    "在厨房方向、在另一房间等任何形式）。特别注意：台词中提及「妈妈」字样（如\"妈妈说…\"）不等于妈妈在该段说话，"
    "妈妈未发言时不可出现在该段画面中。"
)

# 角色身上固定着装：禁止当道具（蓝T恤=昭昭穿的，粉卫衣=灿灿穿的）
_DAILY_OUTFIT_PROP_REWRITES: tuple[tuple[str, str], ...] = (
    ("粉色卫衣、蓝色T恤等", "衣服"),
    ("蓝色T恤、粉色卫衣等", "衣服"),
    ("粉色卫衣", "衣服"),
    ("蓝色T恤", "衣服"),
    ("蓝色短袖T恤", "衣服"),
    ("米色上衣", "衣服"),
    ("彩色衣物", "衣服"),
    ("彩色T恤", "衣服"),
)

_DAILY_BRIEF_LABEL_RE = re.compile(
    r"(?:冲突道具|地点|人物|道具|场景|主体|构图|光照)\s*[：:]"
)

# visual_brief 中「昭昭右手…」类单角色动作句（单帧只保留每人首句）
_POSE_CLAUSE_START_RE = re.compile(
    r"^(昭昭|灿灿|妈妈)(?:[，,]|右手|左手|双手|身体|瞪|点|叉|摊|耸|仰头|点头|张嘴|比划)"
)


def _collapse_duplicate_pose_clauses(body: str) -> str:
    """同一角色多段动作只保留首段（文生图为单帧）。"""
    parts = re.split(r"([；;。])", body)
    if not parts:
        return body
    seen: set[str] = set()
    out: list[str] = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        clause = segment.strip()
        drop = False
        if clause:
            m = _POSE_CLAUSE_START_RE.match(clause)
            if m:
                name = m.group(1)
                if name in seen:
                    drop = True
                else:
                    seen.add(name)
        if not drop:
            out.append(segment)
            if delim:
                out.append(delim)
        i += 2 if delim else 1
    return "".join(out)


def scrub_daily_visual_brief(text: str) -> str:
    """去掉 daily visual_brief 中易破坏拼装出图的标签与固定着装词。"""
    body = (text or "").strip()
    if not body:
        return body
    body = _DAILY_BRIEF_LABEL_RE.sub("", body)
    for src, dst in _DAILY_OUTFIT_PROP_REWRITES:
        body = body.replace(src, dst)
    # 矛盾定语：叠好 ≠ 皱成一团
    body = body.replace(
        "皱成一团的刚叠好的衣服",
        "原本叠好现已揉皱成一团的衣服",
    )
    body = body.replace(
        "刚叠好的皱成一团的衣服",
        "原本叠好现已揉皱成一团的衣服",
    )
    body = re.sub(r"[，,]{2,}", "，", body)
    body = _collapse_duplicate_pose_clauses(body)
    return body.strip("，, ").strip()



def _segments_have_dialogue(segments: list[dict]) -> bool:
    return any(bool(seg.get("dialogue")) for seg in segments)


def _cast_and_emotion_rules(
    profile_style: str,
    segments: list[dict],
) -> tuple[str, str, bool]:
    """返回 (cast_rule, emotion_rule, include_dialogue)。

    角色入画规则仅在日常，或 segments 已带 dialogue 时注入；
    纯口播生活片不再无 dialogue 却禁画妈妈。
    """
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        return _DAILY_CAST_RULE, _EMOTION_RULE_DIALOGUE, True
    if _segments_have_dialogue(segments):
        return _MOM_DIALOGUE_RULE, _EMOTION_RULE_DIALOGUE, True
    return "", _EMOTION_RULE_NARRATION, False


def _visual_role(profile_style: str) -> str:
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        return _DAILY_VISUAL_ROLE
    return resolve_style_rules(profile_style).role


def _format_one_visual_brief_segment(
    seg: dict,
    *,
    prefix: str = "",
    include_dialogue: bool = False,
) -> str:
    idx = seg.get("segment_index")
    text = str(seg.get("text") or "")
    line = f"{prefix}segment {idx}: text={text!r}"
    shot = str(seg.get("shot_type") or "").strip()
    if shot:
        line += f"; shot_type={shot!r}"
    if include_dialogue:
        dialogue = seg.get("dialogue") or []
        dl_parts = [
            f'{d["speaker"]}:"{d["text"]}"'
            for d in dialogue
            if d.get("speaker") and d.get("text")
        ]
        if dl_parts:
            line += "; dialogue=" + " ".join(dl_parts)
    return line


def format_visual_brief_segments_for_prompt(
    segments: list[dict],
    *,
    include_dialogue: bool = False,
    segment_indices: list[int] | None = None,
) -> str:
    ordered = sorted(
        segments,
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    if segment_indices is None:
        return "\n".join(
            _format_one_visual_brief_segment(seg, include_dialogue=include_dialogue)
            for seg in ordered
        )

    wanted = {int(idx) for idx in segment_indices}
    max_idx = max(
        (int(seg.get("segment_index") or 0) for seg in ordered),
        default=0,
    )
    extra: set[int] = set()
    for idx in wanted:
        if idx - 1 >= 1:
            extra.add(idx - 1)
        if idx + 1 <= max_idx:
            extra.add(idx + 1)
    extra -= wanted
    shown = wanted | extra

    lines: list[str] = []
    for seg in ordered:
        idx = int(seg.get("segment_index") or 0)
        if idx not in shown:
            continue
        tag = "【仅上下文】" if idx in extra else "【需生成】"
        lines.append(
            _format_one_visual_brief_segment(
                seg,
                prefix=tag,
                include_dialogue=include_dialogue,
            )
        )
    return "\n".join(lines)


def build_visual_brief_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    segment_indices: list[int] | None = None,
) -> dict[str, str]:
    """第二步：基于已切分的 segments 与全文 narration 生成 visual_brief。

    segment_indices 非空时只要求 LLM 输出这些段（邻段作上下文）。
    """
    _profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    narration = str(script.get("narration") or "").strip()
    visual_style = str(script.get("visual_style") or "").strip()
    title = str(script.get("title") or "").strip()
    cast_rule, emotion_rule, include_dialogue = _cast_and_emotion_rules(
        profile_style, segments
    )
    setting_rule = (
        _DAILY_SETTING_RULE if profile_style == CONTENT_STYLE_DAILY_STORY else ""
    )
    content_rule = (
        _DAILY_VISUAL_BRIEF_CONTENT_RULE
        if profile_style == CONTENT_STYLE_DAILY_STORY
        else _VISUAL_BRIEF_CONTENT_RULE
    )
    partial = segment_indices is not None
    coverage = (
        "segments 仅需输出标记为【需生成】的分镜；【仅上下文】分段无需输出；"
        if partial
        else "segments 为分镜数组，须与输入逐段一一对应；"
    )
    seg_rule = (
        f"{coverage}"
        "各段含 segment_index, visual_brief, visual_mode=static_motion；"
        "不要输出或修改各段 text。"
        f"{content_rule}"
        f"{emotion_rule}"
        f"{cast_rule}"
        f"{setting_rule}"
        "须通读全文 narration，保证相邻分镜画面衔接自然、叙事节奏连贯，"
        "避免前后镜主体/场景毫无关联的跳跃；"
        "同时每镜 visual_brief 只表达本段 text 内容，禁止提前画后续段落情节。"
    )
    example = (
        _VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL
        if partial
        else _VISUAL_BRIEF_JSON_EXAMPLE_FULL
    )
    system = (
        f"{_visual_role(profile_style)}输出 JSON，字段：segments。"
        f"{seg_rule}"
        f"{supplementary_system_clause(supplementary_info, scope='visual')}"
        f"{json_output_clause(example)}"
    )
    seg_lines = format_visual_brief_segments_for_prompt(
        segments,
        include_dialogue=include_dialogue,
        segment_indices=segment_indices,
    )
    style_line = (
        f"全片 visual_style：{visual_style}\n\n"
        if visual_style
        else ""
    )
    setting = str(script.get("setting") or "").strip()
    setting_line = f"全片地点 setting：{setting}\n" if setting else ""
    if partial:
        seg_header = (
            "【各分镜口播 text】（已固定；仅【需生成】段输出 visual_brief，"
            "【仅上下文】勿输出）：\n"
        )
    else:
        seg_header = "【各分镜口播 text】（已固定，请为每一段生成 visual_brief）：\n"
    user = append_supplementary_to_user(
        (
            f"标题：{title}\n"
            f"{setting_line}"
            f"{style_line}"
            f"【口播全文 narration】（供把握画面节奏与连贯性，勿改写）：\n{narration}\n\n"
            f"{seg_header}"
            f"{seg_lines}"
        ),
        supplementary_info,
        scope="visual",
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return prompt_step("visual_brief", system, user)
