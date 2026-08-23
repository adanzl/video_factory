"""H0c/H2/H3/H3b：金故事 LLM 结构化。"""

from __future__ import annotations

import json
from typing import Any

from app.services.daily_story.gold_story.types import (
    GOLD_STORY_MECHANISM_CODES,
    GOLD_STORY_MECHANISM_LABELS,
    GOLD_STORY_TYPE_CATALOG,
    structure_type_for_mechanism,
)
from app.services.llm.llm_mgr import llm_mgr

_H0C_SYSTEM = (
    "你是短视频口播逐字稿修复师。输入为 faster-whisper 自动转写："
    "有错字、断句乱、分不清说话人。\n"
    "结合标题/简介推断角色，修正同音错字，按对话拆行并标注说话人。\n"
    "不要编造视频中未出现的情节；听不清处用 [听不清]。\n"
    "只输出 JSON。"
)

_H0C_USER = """视频标题：{title}

【简介】
{description}

【ASR 原文（可能有错，一行或多行）】
{transcript}

输出 JSON：
{{
  "speakers": ["妈妈", "宝宝"],
  "lines": [
    {{"speaker": "妈妈", "text": "修正后的这一句"}},
    {{"speaker": "宝宝", "text": "…"}}
  ],
  "repair_confidence": 0.0,
  "repair_notes": "一句说明推断依据"
}}

规则：
- speaker 用简短称谓：妈妈、爸爸、宝宝、女孩、男孩、哥哥、妹妹等；
  无法判断时用 角色1/角色2，并在 repair_notes 说明
- 合并 ASR 误切的碎句；修正明显同音错字（结合语境，勿脑补新剧情）
- **合并连续重复的同一短语**（如「为减人」连刷十遍只保留 1–2 次）
- 相邻同一 speaker 可合并为一条 line
- lines 至少 2 条；repair_confidence<0.35 视为失败
- ASR 再差也要尽力修复；confidence 表示角色/断句把握（≥0.5 为佳，≥0.35 可接受）
- text 字段不要重复 speaker 前缀
"""

_H2_SYSTEM = (
    "你是站外短视频故事抽取器。从逐字稿/热评/简介中选出 **一条** 微型故事"
    "（80–400 字第三方叙述），含冲突、升级、收束。\n"
    "合集多梗时只取最好笑的一条。\n"
    "只输出 JSON。"
)

_H2_USER = """视频标题：{title}

【逐字稿】
{transcript}

【简介】
{description}

【热评摘录】
{replies}

输出 JSON：
{{
  "story_raw": "第三方叙述全文…",
  "perspective": "third_person | mixed | direct_dialogue",
  "has_complete_arc": true,
  "extract_confidence": 0.0
}}

规则：
- story_raw **必须 80–400 字**；太短（单句笑话/只有一个梗）一律 has_complete_arc=false
- 优先选热评里 **整段复述**（有然后/最后/被问/嘴硬）的完整微型故事
- has_complete_arc=false 或 extract_confidence<0.5 即失败
- 不要输出 quote 字段；引号对白保留在 story_raw 内
"""


_H3_SYSTEM = (
    "你是金故事结构化师。输入 story_raw，输出机制 M 码 + 结构类型 + beat。\n"
    "mechanism 必须是 M1–M10 之一；structure_type 必须是 A–E 或 F。\n"
    "beat 4–6 步，禁止贴 story_raw 原文。\n"
    "只输出 JSON。"
)

_H3_USER = """视频标题：{title}

story_raw：
{story_raw}

机制表（M 码）：
{mechanism_table}

结构类型 A–E：
{type_catalog}

输出 JSON：
{{
  "title": "短标题",
  "conflict_core": "一句话冲突核",
  "funny_why": "为何好笑",
  "mechanism": "M2",
  "structure_type": "C",
  "theme_family": "占有|消耗|结盟|操作 等",
  "beat": ["…", "…", "…", "…"],
  "banned_literals": ["…"],
  "structure_confidence": 0.0,
  "structure_mapping_note": ""
}}
"""


_H3B_SYSTEM = (
    "你是金故事对话化师。把第三方叙述转成昭昭(7岁弟)/灿灿(10岁姐) 的对话骨架。\n"
    "dialogue_seed 只用 intent，不写成品台词；禁止 banned_literals 同词。\n"
    "只输出 JSON。"
)

_H3B_USER = """H3 结构化结果：
{h3_json}

story_raw：
{story_raw}

角色：昭昭=7岁弟，灿灿=10岁姐，妈妈少出场。

输出 JSON：
{{
  "setting": "可拍现场一句",
  "dialogue_seed": [
    {{"speaker": "昭昭|灿灿|妈妈", "intent": "…"}}
  ],
  "closing_intent": "与 structure_type 收束一致",
  "speaker_map_note": "站外角色如何映射",
  "dialogue_confidence": 0.0
}}
"""


def _client():
    return llm_mgr._get_client()


def _mechanism_table() -> str:
    lines = [
        f"- {code} {GOLD_STORY_MECHANISM_LABELS[code]}"
        for code in sorted(GOLD_STORY_MECHANISM_CODES)
    ]
    return "\n".join(lines)


def _type_catalog() -> str:
    lines = [
        f"- {row['code']} {row['name']}：{row['formula']}"
        for row in GOLD_STORY_TYPE_CATALOG
    ]
    return "\n".join(lines)


def _chat_json(system: str, user: str) -> dict[str, Any]:
    raw, _finish = _client()._chat_json(
        system,
        user,
        thinking_enabled=False,
        temperature=0.35,
    )
    if not isinstance(raw, dict):
        raise ValueError("LLM JSON must be object")
    return raw


def repair_transcript(
    *,
    title: str,
    transcript: str,
    description: str = "",
) -> dict[str, Any]:
    """H0c：ASR 逐字稿 → 纠错 + 说话人标注。"""
    transcript_text = str(transcript or "").strip()
    if not transcript_text:
        raise ValueError("H0c missing transcript")
    user = _H0C_USER.format(
        title=title,
        description=str(description or "").strip()[:2000] or "（无）",
        transcript=transcript_text[:12000],
    )
    data = _chat_json(_H0C_SYSTEM, user)
    lines = data.get("lines") or []
    if not isinstance(lines, list) or len(lines) < 2:
        raise ValueError("H0c lines must have at least 2 entries")
    cleaned: list[dict[str, str]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker") or "").strip() or "未知"
        text = str(row.get("text") or "").strip()
        if text:
            cleaned.append({"speaker": speaker, "text": text})
    if len(cleaned) < 2:
        raise ValueError("H0c cleaned lines too short")
    confidence = float(data.get("repair_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H0c low repair_confidence={confidence:.2f}")
    speakers = data.get("speakers") or []
    if not isinstance(speakers, list):
        speakers = []
    return {
        "lines": cleaned,
        "speakers": [str(s).strip() for s in speakers if str(s).strip()],
        "repair_confidence": confidence,
        "repair_notes": str(data.get("repair_notes") or "").strip(),
    }


def extract_story_raw(
    *,
    title: str,
    transcript: str,
    description: str = "",
    replies: list[str] | None = None,
) -> dict[str, Any]:
    """H2：逐字稿 + 热评 → story_raw。"""
    reply_text = "\n---\n".join(replies or []) or "（无）"
    transcript_text = str(transcript or "").strip() or "（无逐字稿）"
    user = _H2_USER.format(
        title=title,
        transcript=transcript_text[:12000],
        description=str(description or "").strip()[:2000] or "（无）",
        replies=reply_text[:6000],
    )
    data = _chat_json(_H2_SYSTEM, user)
    story_raw = str(data.get("story_raw") or "").strip()
    if not story_raw:
        raise ValueError("H2 missing story_raw")
    confidence = float(data.get("extract_confidence") or 0.0)
    has_arc = bool(data.get("has_complete_arc"))
    if not has_arc or confidence < 0.5:
        raise ValueError(
            f"H2 rejected arc={has_arc} confidence={confidence:.2f}"
        )
    if len(story_raw) < 80:
        raise ValueError(f"H2 story_raw too short: {len(story_raw)} chars (min 80)")
    if len(story_raw) > 450:
        raise ValueError(f"H2 story_raw too long: {len(story_raw)} chars (max 400)")
    return {
        "story_raw": story_raw,
        "perspective": str(data.get("perspective") or "third_person"),
        "extract_confidence": confidence,
        "has_complete_arc": has_arc,
    }


def structurize_story(
    *,
    title: str,
    story_raw: str,
) -> dict[str, Any]:
    """H3：story_raw → mechanism + beat。"""
    user = _H3_USER.format(
        title=title,
        story_raw=story_raw[:4000],
        mechanism_table=_mechanism_table(),
        type_catalog=_type_catalog(),
    )
    data = _chat_json(_H3_SYSTEM, user)
    mechanism = str(data.get("mechanism") or "").strip().upper()
    if mechanism not in GOLD_STORY_MECHANISM_CODES:
        raise ValueError(f"H3 invalid mechanism: {mechanism!r}")
    mapped = structure_type_for_mechanism(mechanism)
    data["mechanism"] = mechanism
    data["structure_type"] = mapped
    beat = data.get("beat") or []
    if not isinstance(beat, list) or len(beat) < 4:
        raise ValueError("H3 beat must have 4–6 steps")
    confidence = float(data.get("structure_confidence") or 0.0)
    if confidence < 0.5:
        raise ValueError(f"H3 low structure_confidence={confidence:.2f}")
    return data


def build_dialogue_seed(
    *,
    story_raw: str,
    h3: dict[str, Any],
) -> dict[str, Any]:
    """H3b：第三方叙述 → dialogue_seed。"""
    user = _H3B_USER.format(
        h3_json=json.dumps(h3, ensure_ascii=False, indent=2),
        story_raw=story_raw[:4000],
    )
    data = _chat_json(_H3B_SYSTEM, user)
    seed = data.get("dialogue_seed") or []
    if not isinstance(seed, list) or len(seed) < 2:
        raise ValueError("H3b dialogue_seed too short")
    confidence = float(data.get("dialogue_confidence") or 0.0)
    if confidence < 0.5:
        raise ValueError(f"H3b low dialogue_confidence={confidence:.2f}")
    return data


_H4A_SYSTEM = (
    "你是金故事机审员。判断站外微型故事能否迁移为"
    "昭昭(7岁弟)+灿灿(10岁姐)姐弟日常冲突短视频。\n"
    "采集词可以宽，但你须严格卡掉：母子/婴儿婴语为主、"
    "冲突太短、映射距离太远、妈妈当主角的稿子。\n"
    "只输出 JSON。"
)

_H4A_USER = """原视频标题：{video_title}
结构化标题：{title}
机制/结构：{mechanism} / {structure_type}

冲突核：{conflict_core}

story_raw：
{story_raw}

speaker_map_note：
{speaker_map_note}

dialogue_seed：
{dialogue_seed}

beat：
{beat}

逐字稿摘录：
{transcript}

输出 JSON：
{{
  "pass": true,
  "sibling_fit": 0.0,
  "age_fit": 0.0,
  "conflict_usable": 0.0,
  "mapping_fit": 0.0,
  "reject_reasons": [],
  "audit_notes": "一句"
}}

评分说明（0–1，越高越好）：
- sibling_fit：是否姐弟/兄妹/两孩冲突，而非母子育儿/纯可爱
- age_fit：能否自然落到 7 岁弟 + 10 岁姐（拒绝婴语、过小）
- conflict_usable：是否有可拍争/抢/歪理/Threat 链，不是温馨旁白
- mapping_fit：映射到昭昭/灿灿是否牵强（妈妈当第三主角应降分）

pass=true 仅当四维均 ≥0.55 且无硬伤；否则 pass=false 并列出 reject_reasons。
"""


def audit_story_fit(
    *,
    video_title: str,
    title: str,
    story_raw: str,
    conflict_core: str,
    mechanism: str,
    structure_type: str,
    speaker_map_note: str,
    dialogue_seed: list[Any],
    beat: list[Any],
    transcript: str = "",
    description: str = "",
    min_sibling_fit: float = 0.55,
    min_age_fit: float = 0.55,
    min_conflict_usable: float = 0.55,
    min_mapping_fit: float = 0.55,
) -> dict[str, Any]:
    """H4a LLM 机审。"""
    user = _H4A_USER.format(
        video_title=video_title,
        title=title,
        mechanism=mechanism,
        structure_type=structure_type,
        conflict_core=conflict_core[:500],
        story_raw=story_raw[:4000],
        speaker_map_note=speaker_map_note[:800] or "（无）",
        dialogue_seed=json.dumps(dialogue_seed, ensure_ascii=False, indent=2)[:4000],
        beat=json.dumps(beat, ensure_ascii=False)[:2000],
        transcript=str(transcript or description or "")[:4000] or "（无）",
    )
    data = _chat_json(_H4A_SYSTEM, user)
    sibling_fit = float(data.get("sibling_fit") or 0.0)
    age_fit = float(data.get("age_fit") or 0.0)
    conflict_usable = float(data.get("conflict_usable") or 0.0)
    mapping_fit = float(data.get("mapping_fit") or 0.0)
    llm_pass = bool(data.get("pass"))
    reasons = [str(r) for r in (data.get("reject_reasons") or []) if str(r).strip()]
    thresholds_ok = (
        sibling_fit >= min_sibling_fit
        and age_fit >= min_age_fit
        and conflict_usable >= min_conflict_usable
        and mapping_fit >= min_mapping_fit
    )
    passed = llm_pass and thresholds_ok
    if not thresholds_ok:
        if sibling_fit < min_sibling_fit:
            reasons.append(f"sibling_fit_low:{sibling_fit:.2f}")
        if age_fit < min_age_fit:
            reasons.append(f"age_fit_low:{age_fit:.2f}")
        if conflict_usable < min_conflict_usable:
            reasons.append(f"conflict_usable_low:{conflict_usable:.2f}")
        if mapping_fit < min_mapping_fit:
            reasons.append(f"mapping_fit_low:{mapping_fit:.2f}")
    return {
        "pass": passed,
        "sibling_fit": sibling_fit,
        "age_fit": age_fit,
        "conflict_usable": conflict_usable,
        "mapping_fit": mapping_fit,
        "reject_reasons": reasons,
        "audit_notes": str(data.get("audit_notes") or "").strip(),
    }
