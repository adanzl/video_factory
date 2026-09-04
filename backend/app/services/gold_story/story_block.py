"""H5–H7：金故事检索与 D2 注入块。"""

from __future__ import annotations

from typing import Any, cast

from app.config import Config
from app.repositories import repo_daily_story, repo_gold_story
from app.services.gold_story.scene import (
    format_scene_block,
    sanitize_banned_literals,
)
from app.services.gold_story.types import (
    GOLD_STORY_INJECTABLE_CODES,
    is_injectable_structure_type,
    mechanism_label,
    normalize_structure_type,
    structure_type_label,
)
from app.services.daily_story.prompts import themes_near_duplicate


def format_beat_numbered(beat: list[Any]) -> str:
    lines: list[str] = []
    for i, item in enumerate(beat or [], start=1):
        text = str(item or "").strip()
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines)


def format_dialogue_seed(dialogue_seed: list[Any]) -> str:
    lines: list[str] = []
    for item in dialogue_seed or []:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if speaker and intent:
            lines.append(f"- {speaker}：{intent}")
    return "\n".join(lines)


def build_gold_story_block(story: dict[str, Any]) -> str:
    """H6/H7：组装注入块（禁止贴 story_raw / 成品对白）。"""
    payload = cast(dict[str, Any], story.get("payload") or {})
    beat = payload.get("beat") or []
    dialogue_seed = payload.get("dialogue_seed") or []
    scene_contract = payload.get("scene_contract") or {}
    banned = sanitize_banned_literals(
        payload.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    closing = str(payload.get("closing_intent") or "").strip()
    mechanism = str(story.get("mechanism") or "").strip()
    structure_type = str(story.get("structure_type") or "").strip()
    conflict_core = str(story.get("conflict_core") or "").strip()

    mech_label = mechanism_label(mechanism) if mechanism else ""
    type_label = structure_type_label(structure_type) if structure_type else ""
    banned_text = "、".join(str(x).strip() for x in banned if str(x).strip())

    parts = [
        "【金故事·对话方向·禁照抄站外原文】",
        f"冲突核：{conflict_core}" if conflict_core else "冲突核：（未填）",
        f"机制：{mechanism}（{mech_label}）" if mechanism else "机制：（未填）",
        (
            f"结构收束：{structure_type}（{type_label}，与任务类型一致）"
            if structure_type
            else "结构收束：（未填）"
        ),
        "故事 beat：",
        format_beat_numbered(beat) or "（无）",
        format_scene_block(scene_contract),
        "对话骨架（intent 仅供参考，须重写为昭昭/灿灿 口语对白）：",
        format_dialogue_seed(dialogue_seed) or "（无）",
    ]
    if closing:
        parts.append(f"收束意图：{closing}")
    if banned_text:
        parts.append(f"禁词：{banned_text}")
    parts.append("须按 beat 与 intent 重写对白，禁止照搬站外叙述或 seed 字面。")
    return "\n".join(parts)


def _gold_near_duplicate_of_daily_story(row: dict[str, Any]) -> bool:
    """金故事 conflict_core/标题 是否与已有 daily_story 稿子雷同。"""
    gold_bits = [
        str(row.get("conflict_core") or "").strip(),
        str(row.get("title") or "").strip(),
    ]
    gold_bits = [text for text in gold_bits if text]
    if not gold_bits:
        return False
    existing = repo_daily_story.list_stories(limit=200)
    for item in existing:
        theme = str(item.get("theme") or "").strip()
        story = item.get("story") if isinstance(item.get("story"), dict) else {}
        conflict = str(story.get("conflict_core") or "").strip()  # type: ignore[union-attr]
        for gold in gold_bits:
            if theme and themes_near_duplicate(gold, theme):
                return True
            if conflict and themes_near_duplicate(gold, conflict):
                return True
    return False


def pick_for_injection(
    *,
    theme: str,
    story_type: str,
    theme_family: str | None = None,
) -> dict[str, Any] | None:
    """H5：取 1 条可注入金故事；与已有 daily_story 雷同则跳过。"""
    code = normalize_structure_type(story_type)
    if code not in GOLD_STORY_INJECTABLE_CODES:
        return None
    rows = repo_gold_story.pick(
        theme=theme,
        story_type=code,
        theme_family=theme_family,
        limit=5,
    )
    for row in rows:
        st = str(row.get("structure_type") or "").upper()
        if not is_injectable_structure_type(st):
            continue
        if _gold_near_duplicate_of_daily_story(row):
            continue
        return row
    return None


def resolve_gold_story_block(
    *,
    theme: str,
    story_type: str | None,
    theme_family: str | None = None,
    config: Config | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """H7 入口：开关关闭、无匹配或全部雷同时返回空块。"""
    cfg = config or Config()
    if not cfg.gold_story_enabled or not story_type:
        return "", None
    row = pick_for_injection(
        theme=theme,
        story_type=story_type,
        theme_family=theme_family,
    )
    if not row:
        return "", None
    return build_gold_story_block(row), row
