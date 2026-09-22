"""gold_chat 导出导入 daily_story。"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.export import load_gold_chat_for_row
from app.services.gold_story.gold_chat.patch import (
    patch_m5_break_sibling_consecutive,
)

logger = logging.getLogger(__name__)


def _review_gold_chat_import_story(story: dict[str, Any], theme: str) -> dict[str, Any]:
    """gold_chat 导入 daily_story：单次 LLM 审读，注入 humor.funny_score。"""
    try:
        from app.services.daily_story.review import (
            apply_review_to_quality,
            collect_local_issues,
            merge_issues,
        )
        from app.services.llm import llm_mgr

        client = llm_mgr._get_client()
        review = getattr(client, "review_daily_story_issues", None)
        if not callable(review):
            return story
        issues_, humor_ = review(theme, story)  # type: ignore[union-attr]
        issues = merge_issues(collect_local_issues(story), issues_)
        return apply_review_to_quality(
            story,
            issues,
            humor=humor_,
            apply_penalty=False,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "gold_chat import review skipped: %s",
            exc,
        )
        return story


def validate_gold_chat_story_for_row(
    story: dict[str, Any],
    row: dict[str, Any],
) -> None:
    """按来源金故事契约复验，供导入、编辑、建任务统一复用。"""
    from app.services.gold_story.gold_chat.convert import (
        sanitize_banned_literals,
        validate_gold_chat,
    )

    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    scene_contract = (
        payload.get("scene_contract")
        if isinstance(payload.get("scene_contract"), dict)
        else {}
    )
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    mom_lines_max = scene_contract.get("mom_lines_max")
    if mom_lines_max is None:
        mom_lines_max = 1
    validate_gold_chat(
        story,
        banned_literals=banned,
        source_type=str(
            payload.get("source_type")
            or scene_contract.get("source_type")
            or "field"
        ),
        mom_lines_max=int(mom_lines_max),
    )


def import_gold_chat_daily_story(
    row: dict[str, Any],
    *,
    config: Config | None = None,
    force: bool = False,
    review: bool = True,
) -> dict[str, Any]:
    """gold_chat 导出 → daily_story；force 时覆盖已有导入。"""
    from app.repositories import repo_daily_story
    from app.services.daily_story.prompts import sync_discovery_opening_from_dialogue
    from app.services.daily_story.quality import attach_daily_story_quality

    gid = int(row.get("id") or 0)
    sid = str(row.get("source_id") or "").strip()
    if gid <= 0 or not sid:
        raise ValueError("gold_story 缺少 id 或 source_id")

    export = load_gold_chat_for_row(row, config=config)
    if export is None:
        raise FileNotFoundError(f"尚未导出 gold_chat: {sid}")

    chat = export.get("daily_story")
    if not isinstance(chat, dict):
        raise ValueError("gold_chat export missing daily_story")
    if not (chat.get("dialogue") or []):
        raise ValueError("gold_chat 对白为空")

    from app.services.gold_story.gold_chat.convert import (
        apply_gold_chat_normalizations,
    )

    chat, _ = apply_gold_chat_normalizations(dict(chat), row=row)
    story = dict(chat)
    theme = str(
        story.get("scene_title")
        or story.get("key")
        or row.get("title")
        or sid
    ).strip()
    story_type = str(row.get("structure_type") or "").strip().upper()[:1] or None
    mech = str(row.get("mechanism") or "").strip().upper()
    if story_type:
        story["story_type"] = story_type
    if mech == "M5" and story_type == "H":
        story, _ = patch_m5_break_sibling_consecutive(story)
    # 与 convert._attach_gold_chat_structure_score 一致：先按正文一体计分，
    # 再 sync discovery_opening，避免开场双句被二次扣分。
    story.pop("discovery_opening", None)
    attach_daily_story_quality(
        story, theme=theme, finalize=True, skip_relevancy=True
    )
    sync_discovery_opening_from_dialogue(story)
    if review:
        story = _review_gold_chat_import_story(story, theme)
    validate_gold_chat_story_for_row(story, row)
    story_key = str(story.get("key") or "").strip() or None

    existing_raw = row.get("gold_chat_daily_story_id")
    existing_id = int(existing_raw) if existing_raw else 0

    if existing_id > 0 and not force:
        return {
            "action": "skip",
            "reason": "already_imported",
            "gold_story_id": gid,
            "source_id": sid,
            "daily_story_id": existing_id,
        }

    if existing_id > 0:
        try:
            repo_daily_story.get_story(existing_id)
        except KeyError:
            existing_id = 0

    if existing_id > 0:
        updated = repo_daily_story.update_story(
            existing_id,
            story=story,
            story_type=story_type,
            key=story_key,
        )
        repo_gold_story.set_gold_chat_daily_story_id(gid, existing_id)
        return {
            "action": "update",
            "gold_story_id": gid,
            "source_id": sid,
            "daily_story_id": existing_id,
            "theme": updated.get("theme"),
            "story_type": updated.get("story_type"),
            "daily_story": story,
        }

    new_id = repo_daily_story.insert_story(
        theme=theme,
        story=story,
        story_type=story_type,
        key=story_key,
    )
    repo_gold_story.set_gold_chat_daily_story_id(gid, new_id)
    return {
        "action": "insert",
        "gold_story_id": gid,
        "source_id": sid,
        "daily_story_id": new_id,
        "theme": theme,
        "story_type": story_type,
        "daily_story": story,
    }

