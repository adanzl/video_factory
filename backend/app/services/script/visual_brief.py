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
    "写成一段连贯中文，写满可出图细节（地点陈设、人物动作表情、冲突道具融在正文里）。"
    "画风/外貌/口型/光线/景别由系统补全，brief 只写本镜可见的场景与动作。"
    "【地点与陈设】开头写清室内地点（与全片 setting 一致，如客厅沙发/茶几旁）；"
    "背景陈设默认「茶几上放着遥控器和空水杯」，全片镜间沿用；"
    "仅当本段台词点名其他背景物件时再改写陈设。"
    "画面涉及门（含门口/门外）时，门一律写成「单扇门」（单扇平开门）。"
    "【站位】两人：「画面左边是A，右边是B」，再按左→右写动作；"
    "三人默认「从左到右是昭昭、妈妈、灿灿」并写清每人动作；"
    "昭昭与灿灿同框默认左昭昭、右灿灿，全片尽量固定；"
    "speakers 列出的角色都要入画，未发言者写旁听姿态。"
    "【人物关系】对标本段 dialogue：质问方进攻（指/瞪/左手叉腰+右手指），"
    "辩解方防御（摊手/耸肩/撇嘴）；每人只定格一组姿势（冲突最强一瞬）。"
    "【人物】写眉眼与肢体（瞪圆眼、皱眉、撇嘴、前倾、摊手等），强度对齐台词语气；"
    "口型由系统注入，brief 用眉眼肢体表达情绪即可。"
    "【道具】冲突道具用台词已出现的物件与状态；"
    "衣物类用「衣服/衣物堆/皱成一团的衣服」泛称（粉色卫衣/蓝色T恤是角色身上穿的，不当道具）。"
    "事实对齐台词：说皱就画「原本叠好、现已揉皱」；说只碰一下就画无辜摊手。"
    "【开场】segment_index=1 且特写时，定格冲突峰值姿势，表情再夸张一档。"
    "正例（对白：灿灿抱怨刚叠好的衣服皱成一团；昭昭说只碰一下没弄皱）："
    "'客厅沙发上，原本叠好的衣服已被揉皱成一团；"
    "画面左边是昭昭，右边是灿灿；"
    "昭昭双手摊开耸肩，撇着嘴角一脸无辜；"
    "灿灿右手食指指向身前那团皱衣服，左手叉腰，瞪圆眼睛、皱着眉；"
    "茶几上放着遥控器和空水杯。'"
)

_EMOTION_RULE_DIALOGUE = (
    "情绪须对标台词语气强度（争吵时表情激烈如瞪眼皱眉撇嘴、温和平静时表情放松）。"
)

_EMOTION_RULE_NARRATION = (
    "氛围与本段口播语气一致，点到即可，勿夸张表演或堆砌表情描写。"
)

_DAILY_SPEAKER_RULE = (
    "【角色入画】可入画 = 本段须入画角色（若输入含 speakers 字段则以其为准）"
    " = 本段 dialogue 发言 ∪ 台词写明当场在场 ∪ 同场粘性角色"
    "（setting 已点名，或前面分镜已出场的角色，后续镜继续保留）。"
    "speakers 列出的角色必须全部入画；未发言者写旁听/在场姿态"
    "（坐着吃饭、看向说话人、夹菜等），禁止消失。"
    "禁止无故旁观/路过/另一房间凑人数。"
    "仅转述或询问去向不算新授予入画（如「妈妈说过…」「妈妈呢？」）；"
    "但若台词明确是「躲着/瞒着/别让妈妈看见/别被妈妈发现」等避开妈妈视线，"
    "则妈妈本镜必须离场，不得因同场粘性继续入画。"
    "台词说「妈出来了/进来了」但本镜 speakers 不含妈妈时："
    "只画空门口（门口无人），禁止画路人/半张脸；"
    "禁止写「盯/瞟/望向门口等人」——改写角色互看或看向道具。"
    "若该段无人发言且 speakers 为空，禁止出现昭昭/灿灿/妈妈等人像，只写场景。"
)

_DAILY_SETTING_RULE = (
    "【地点锚点】全片 setting 已给定（如客厅）；"
    "每镜 visual_brief 落在该地点或其可见角落（沙发/茶几/书桌/门口）。"
)

_MOM_DIALOGUE_RULE = (
    "【角色约束】妈妈可入画当且仅当："
    "本段 dialogue 含 speaker=\"妈妈\"，或台词写明妈妈当场可见动作/状态"
    "（如躺着刷手机、手里亮屏）；二者皆无则禁止妈妈入画"
    "（旁观、路过、另一房间等都不允许）。"
    "仅转述旧话或询问去向（如「妈妈说过…」「妈妈呢？」）不算在场，不可入画。"
    "若台词是「躲着妈妈」「瞒着妈妈」「别让妈妈看见/发现」等，"
    "表示妈妈不在当前视线内，禁止把妈妈画到人物面前。"
    "「妈出来了/进来了」若本镜未把妈妈列入 speakers："
    "门口须写空无无人，禁止用盯门口暗示第三人入画。"
    "不要为了让妈妈入画而改写/强加台词。"
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

# brief 禁写口型（拼装层会硬加「微微张嘴」）；顺带剥语气词
_MOUTH_AND_TONE_RE = re.compile(
    r"(?:嘴巴大张|张着嘴|微微张嘴|正在开口说话|"
    r"嘴巴闭合不露齿|嘴巴闭合|不露齿|"
    r"语气\S{1,4})"
)

# 句内双手互斥：双手叉腰 + 右手指/比划 → 左手叉腰
_RIGHT_HAND_ACTION_RE = re.compile(r"右手(?:指|食指|指向|比划)")

# 默认背景陈设；茶几「放着/摆着」句若无遥控器则归一（冲突物摊开等另句保留）
_DEFAULT_TABLE_SET = "茶几上放着遥控器和空水杯"
_TABLE_SET_CLAUSE_RE = re.compile(r"茶几上(?:放着|摆着)[^。；]*")
_TABLE_CONFLICT_KEEP_RE = re.compile(
    r"薯片|衣服|衣物|零食|饼干|酸奶|冰棍|拖把|皱成一团"
)
_TABLE_STRAY_DECOR_RE = re.compile(
    r"月饼|杂志|书堆|扫帚|花瓶|果盘|纸巾盒|零食罐|蜡笔"
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


def _fix_hands_on_hips_conflict(body: str) -> str:
    """同一分句「双手叉腰」又写右手动作时，改为左手叉腰。"""
    parts = re.split(r"([；;。])", body)
    if not parts:
        return body
    out: list[str] = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        if "双手叉腰" in segment and _RIGHT_HAND_ACTION_RE.search(segment):
            segment = segment.replace("双手叉腰", "左手叉腰")
        out.append(segment)
        if delim:
            out.append(delim)
        i += 2 if delim else 1
    return "".join(out)


def _normalize_default_table_set(body: str) -> str:
    """茶几背景陈设归一为遥控器+空水杯；台词冲突物另句不改。"""

    def _repl(m: re.Match[str]) -> str:
        clause = m.group(0)
        if "遥控器" in clause and ("水杯" in clause or "杯子" in clause):
            return _DEFAULT_TABLE_SET
        if _TABLE_STRAY_DECOR_RE.search(clause):
            return _DEFAULT_TABLE_SET
        if _TABLE_CONFLICT_KEEP_RE.search(clause):
            return clause
        # 普通「放着A和B」类背景句 → 默认陈设
        return _DEFAULT_TABLE_SET

    return _TABLE_SET_CLAUSE_RE.sub(_repl, body)


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
    body = _MOUTH_AND_TONE_RE.sub("", body)
    body = _fix_hands_on_hips_conflict(body)
    body = _normalize_default_table_set(body)
    body = re.sub(r"[，,]{2,}", "，", body)
    body = re.sub(r"[，,]\s*(?=[；;。]|$)", "", body)
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
    日常可入画 = 发言 ∪ 台词在场 ∪ 同场粘性（setting/前镜已出场）。
    """
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        return _DAILY_SPEAKER_RULE, _EMOTION_RULE_DIALOGUE, True
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
    speakers = seg.get("speakers")
    if isinstance(speakers, list) and speakers:
        names = [str(s).strip() for s in speakers if str(s).strip()]
        if names:
            line += f"; speakers={('、'.join(names))!r}"
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
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        from app.services.daily_story.speaker import annotate_sticky_stage_speakers

        annotate_sticky_stage_speakers(
            segments,
            setting=str(script.get("setting") or "").strip(),
        )
    narration = str(script.get("narration") or "").strip()
    visual_style = str(script.get("visual_style") or "").strip()
    title = str(script.get("title") or "").strip()
    cast_rule, emotion_rule, include_dialogue = _cast_and_emotion_rules(
        profile_style, segments
    )
    setting_rule = (
        _DAILY_SETTING_RULE if profile_style == CONTENT_STYLE_DAILY_STORY else ""
    )
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        setting_text = str(script.get("setting") or "").strip()
        if setting_text:
            # 本片物件锚点：setting 里出现的场景物件须每镜在场（状态可随剧情演变）
            setting_rule += (
                "【本片物件锚点】以下为本片 setting 全句，"
                "其中出现的冲突相关物件（如薯片袋、衣服）每镜保持在场，状态可随剧情演变；"
                "背景陈设仍用默认遥控器和空水杯："
                f"「{setting_text}」"
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
