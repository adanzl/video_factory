"""gold_chat 导出导入 daily_story。"""

from __future__ import annotations

from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.export import load_gold_chat_for_row

def validate_gold_chat_story_for_row(
    story: dict[str, Any],
    row: dict[str, Any],
) -> None:
    """按来源金故事契约复验，供导入、编辑、建任务统一复用。"""
    from app.services.gold_story.gold_chat.convert import (
        sanitize_banned_literals,
        validate_gold_chat,
    )

    payload_raw = row.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    scene_contract_raw = payload.get("scene_contract")
    scene_contract: dict[str, Any] = (
        scene_contract_raw if isinstance(scene_contract_raw, dict) else {}
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


def _exported_quality_is_final(
    story: dict[str, Any],
    row: dict[str, Any],
) -> bool:
    """只有终验摘要仍绑定当前正文/来源契约时，导入才原样沿用。"""
    from app.services.daily_story.quality import (
        gold_story_review_contract,
        story_production_eligibility,
    )

    return bool(
        story_production_eligibility(
            story,
            review_contract=gold_story_review_contract(row, story),
        ).get("ok")
    )


def import_gold_chat_daily_story(
    row: dict[str, Any],
    *,
    config: Config | None = None,
    force: bool = False,
    review: bool = True,
) -> dict[str, Any]:
    """gold_chat 导出 → daily_story；force 时覆盖已有导入。

    导入只核对导出稿终验摘要并原样入库；摘要缺失/失效则保存为 review_pending，
    不在导入阶段归一化、改稿或重新打分。
    """
    del review  # 导入不触发改稿/重评；保留参数兼容既有调用方。
    from app.repositories import repo_daily_story
    from app.services.daily_story.quality import (
        find_story_duplicate_matches,
        gold_story_review_contract,
        story_production_eligibility,
    )

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

    story: dict[str, Any] = dict(chat)
    theme = str(
        story.get("scene_title")
        or story.get("key")
        or row.get("title")
        or sid
    ).strip()
    story_type = str(row.get("structure_type") or "").strip().upper()[:1] or None
    if story_type:
        story["story_type"] = story_type
    exported_final = _exported_quality_is_final(story, row)
    # 导入只消费导出事实，不在这里改稿、同步正文镜像或重评。已绑定当前正文/契约的
    # 终验稿可直接沿用；旧导出稿（无 hash / hash 失效）原样保存为 review_pending。
    hard_error: str | None = None
    try:
        validate_gold_chat_story_for_row(story, row)
    except Exception as exc:
        hard_error = str(exc).strip() or exc.__class__.__name__
    story_key = str(story.get("key") or "").strip() or None

    existing_raw = row.get("gold_chat_daily_story_id")
    existing_id = int(existing_raw) if existing_raw else 0

    existing_daily: dict[str, Any] | None = None
    if existing_id > 0:
        try:
            existing_daily = repo_daily_story.get_story(existing_id)
        except KeyError:
            existing_id = 0

    if existing_id > 0 and not force and existing_daily is not None:
        existing_story = existing_daily.get("story")
        existing_quality_raw = (
            existing_story.get("quality") if isinstance(existing_story, dict) else None
        )
        existing_quality: dict[str, Any] = (
            existing_quality_raw if isinstance(existing_quality_raw, dict) else {}
        )
        return {
            "action": "skip",
            "reason": "already_imported",
            "gold_story_id": gid,
            "source_id": sid,
            "daily_story_id": existing_id,
            "status": existing_daily.get("status"),
            "production_reasons": list(existing_quality.get("production_reasons") or []),
        }

    # 最终入库前查全库，不按类型排除；完全/高度重复阻断 active，但仍保存原因供确认。
    # 真正写库前在同一事务中重读一次最新候选，缩小并发生成/导入的漏查窗口。
    from app.repositories.sql_exec import atomic

    with atomic():
        candidates = repo_daily_story.list_all_stories(
            exclude_id=existing_id if existing_id > 0 else None,
        )
        duplicate_matches = find_story_duplicate_matches(
            story,
            candidates,
            exclude_story_id=existing_id if existing_id > 0 else None,
        )
        duplicate_block = [
            item for item in duplicate_matches if item.get("severity") == "block"
        ]
        raw_quality = story.get("quality")
        quality: dict[str, Any] = raw_quality if isinstance(raw_quality, dict) else {}
        if raw_quality is not quality:
            story["quality"] = quality
        if duplicate_matches:
            quality["dedupe_matches"] = duplicate_matches[:10]
        eligibility = story_production_eligibility(
            story,
            hard_error=hard_error,
            review_contract=gold_story_review_contract(row, story),
        )
        if not exported_final:
            eligibility["ok"] = False
            eligibility.setdefault("reasons", []).append("导出稿缺少当前正文终验摘要，需重新终验")
        if duplicate_block:
            eligibility["ok"] = False
            ids = ",".join(str(item.get("story_id")) for item in duplicate_block[:5])
            eligibility.setdefault("reasons", []).append(
                f"库内高度重复：story_id={ids}"
            )
        quality["production_reasons"] = list(eligibility.get("reasons") or [])
        status = "active" if eligibility.get("ok") else "review_pending"

        if existing_id > 0:
            updated = repo_daily_story.update_story(
                existing_id,
                story=story,
                status=status,
                story_type=story_type,
                key=story_key,
            )
            daily_story_id = existing_id
        else:
            daily_story_id = repo_daily_story.insert_story(
                theme=theme,
                story=story,
                status=status,
                story_type=story_type,
                key=story_key,
            )
        repo_gold_story.set_gold_chat_daily_story_id(gid, daily_story_id)

    if existing_id > 0:
        return {
            "action": "update",
            "gold_story_id": gid,
            "source_id": sid,
            "daily_story_id": daily_story_id,
            "theme": updated.get("theme"),
            "story_type": updated.get("story_type"),
            "status": status,
            "production_reasons": list(quality.get("production_reasons") or []),
            "daily_story": story,
        }

    new_id = daily_story_id
    return {
        "action": "insert",
        "gold_story_id": gid,
        "source_id": sid,
        "daily_story_id": new_id,
        "theme": theme,
        "story_type": story_type,
        "status": status,
        "production_reasons": list(quality.get("production_reasons") or []),
        "daily_story": story,
    }

