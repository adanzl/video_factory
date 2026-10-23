"""gold_chat JSON/MD 导出与回读。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.status import _GOLD_CHAT_ERROR_CLEAR_KEYS
from app.services.gold_story.export_story import export_story_files
from app.services.daily_story.prompts import dialogue_total_chars

logger = logging.getLogger(__name__)


def gold_chat_export_dir(config: Config | None = None) -> Path:
    cfg = config or Config()
    return cfg.gold_story_transcript_dir.parent / "gold_chat"


def _chat_md_lines(dialogue: list[Any]) -> list[str]:
    lines: list[str] = []
    for item in dialogue or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("line") or "").strip()
        if sp and text:
            lines.append(f"{sp}：{text}")
    return lines


def _backfill_gold_story_after_export(
    row: dict[str, Any],
    *,
    chat: dict[str, Any],
    paths: dict[str, str],
    config: Config,
    task_id: str | None = None,
) -> None:
    """单次 DB 提交发布完整版本。采集元数据不再占用成稿发布链路。"""
    gid = int(row.get("id") or 0)
    sid = str(row.get("source_id") or "").strip()
    if gid <= 0 or not sid:
        return
    payload_patch = {
        "gold_chat_exported_at": datetime.now(timezone.utc).isoformat(),
        "gold_chat_scene_title": chat.get("scene_title"),
        "gold_chat_lines": len(chat.get("dialogue") or []),
        "gold_chat_chars": dialogue_total_chars(chat),
        "gold_chat_json": paths.get("json"),
        "gold_chat_md": paths.get("markdown"),
    }
    quality = chat.get("quality") if isinstance(chat.get("quality"), dict) else None
    if quality:
        from app.services.daily_story.quality import structure_score_of

        payload_patch["gold_chat_structure_score"] = structure_score_of(quality)
        payload_patch["gold_chat_quality_summary"] = quality.get("summary")
        humor = quality.get("humor")
        if isinstance(humor, dict) and humor.get("funny_score") is not None:
            try:
                payload_patch["gold_chat_humor_score"] = int(humor["funny_score"])
            except (TypeError, ValueError):
                pass
        payload_patch["needs_manual_spotcheck"] = bool(
            quality.get("needs_manual_spotcheck")
        )
        downgraded = quality.get("review_downgraded_issues")
        payload_patch["gold_chat_review_downgraded"] = (
            [dict(it) for it in downgraded if isinstance(it, dict)]
            if isinstance(downgraded, list)
            else []
        )
    payload_patch.update({key: None for key in _GOLD_CHAT_ERROR_CLEAR_KEYS})
    payload_patch["gold_chat_last_error_stage"] = None
    from app.repositories import repo_daily_story
    from app.repositories.sql_exec import atomic
    from app.services.gold_story.gold_chat.import_story import gold_chat_production_eligibility

    with atomic():
        fresh = repo_gold_story.get_story(gid, include_payload_snapshot=True)
        own_id = int(fresh.get("gold_chat_daily_story_id") or 0) or None
        eligibility = gold_chat_production_eligibility(
            chat, fresh,
            candidates=repo_daily_story.list_all_stories(exclude_id=own_id),
            exclude_story_id=own_id,
        )
        if not eligibility["ok"]:
            error = ValueError("导出前制作检查未通过：" + "；".join(eligibility["reasons"]))
            setattr(error, "candidate", deepcopy(chat))
            raise error
        repo_gold_story.publish_chat_export(gid, payload_patch, task_id=task_id, expected_row=fresh)

    try:
        fresh = repo_gold_story.get_story(gid)
        export_story_files(source_id=sid, row=fresh, config=config)
    except Exception as exc:
        logger.warning("gold_chat story export failed id=%s: %s", gid, exc)


def _export_downgraded_issues(chat: dict[str, Any]) -> list[dict[str, Any]]:
    """降级（证据不可核验的观感类）条目：随导出稿留档供人工抽检。"""
    quality = chat.get("quality")
    if not isinstance(quality, dict):
        return []
    raw = quality.get("review_downgraded_issues")
    if not isinstance(raw, list):
        return []
    return [dict(it) for it in raw if isinstance(it, dict)]


def _export_needs_spotcheck(chat: dict[str, Any]) -> bool:
    quality = chat.get("quality")
    if not isinstance(quality, dict):
        return False
    if quality.get("needs_manual_spotcheck"):
        return True
    return bool(_export_downgraded_issues(chat))


def export_gold_chat_files(
    *,
    source_id: str,
    row: dict[str, Any],
    chat: dict[str, Any],
    config: Config | None = None,
    publish: bool = True,
) -> dict[str, str]:
    """导出 JSON + 可读 MD 到 data/gold_story/gold_chat/。"""
    sid = str(source_id or row.get("source_id") or "").strip()
    out_dir = gold_chat_export_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = cast(dict[str, Any], row.get("payload") or {})
    sc_export = payload.get("scene_contract")
    k_mode_export = chat.get("k_close_mode")
    if not k_mode_export and isinstance(sc_export, dict):
        k_mode_export = sc_export.get("k_close_mode")
    export = {
        "gold_story_id": row.get("id"),
        "source_id": sid,
        "url": row.get("url"),
        "title": row.get("title"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "status": row.get("status"),
        "conflict_core": chat.get("conflict_core") or row.get("conflict_core"),
        "chat_chars": dialogue_total_chars(chat),
        "chat_lines": len(chat.get("dialogue") or []),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "k_close_mode": k_mode_export,
        "needs_manual_spotcheck": _export_needs_spotcheck(chat),
        "review_downgraded_issues": _export_downgraded_issues(chat),
        "daily_story": chat,
        "gold_meta": {
            "source_type": payload.get("source_type"),
            "scene_contract": payload.get("scene_contract"),
            "beat": payload.get("beat"),
            "dialogue_seed": payload.get("dialogue_seed"),
            "banned_literals": payload.get("banned_literals"),
            "closing_intent": payload.get("closing_intent"),
        },
    }

    md_lines = [
        f"# {chat.get('scene_title') or row.get('title') or sid}",
        "",
        f"- BV: {sid}",
        f"- URL: {row.get('url') or ''}",
        f"- 金故事 status: {row.get('status') or ''}",
        f"- 机制: {row.get('mechanism')} / 结构: {row.get('structure_type')}",
        f"- 对白: {export['chat_lines']} 句 / {export['chat_chars']} 字",
    ]
    if payload.get("gold_chat_adaptation") is not None:
        from app.services.gold_story.gold_chat.status import gold_chat_source_text

        gold_chat_source_text(row)
        export["gold_meta"]["adaptation"] = deepcopy(payload["gold_chat_adaptation"])
        export["gold_meta"]["original_story_raw"] = str(row.get("story_raw") or payload.get("story_raw") or "")
        md_lines.append("- 创作方式：用户授权重构情节与笑点，非原视频逐句转写。")
    if export["needs_manual_spotcheck"]:
        md_lines.append(
            "- ⚠️ 需人工抽检：审读有 %s 条阻断问题证据不可核验（已降级）"
            % len(export["review_downgraded_issues"])
        )
    md_lines.extend([
        "",
        "## 元数据",
        f"- setting: {chat.get('setting') or ''}",
        f"- key: {chat.get('key') or ''}",
        f"- conflict_core: {chat.get('conflict_core') or ''}",
        f"- punchline_explain: {chat.get('punchline_explain') or ''}",
        "",
    ])
    if export["review_downgraded_issues"]:
        md_lines.append("## 待人工抽检（审读证据不可核验，已降级）")
        md_lines.append("")
        for item in export["review_downgraded_issues"]:
            md_lines.append(
                "- 第%s句·%s：%s"
                % (item.get("lines"), item.get("kind"), item.get("desc"))
            )
        md_lines.append("")
    md_lines.extend(["## 对白", ""])
    md_lines.extend(_chat_md_lines(chat.get("dialogue") or []))
    if payload.get("gold_chat_adaptation") is not None:
        md_lines.extend(["", "## 来源与重构", "", "### 原始素材", "",
                         export["gold_meta"]["original_story_raw"], "",
                         "### 用户授权的重构素材", "", gold_chat_source_text(row)])
    version_dir = out_dir / ".versions" / sid / uuid.uuid4().hex
    version_dir.mkdir(parents=True)
    json_path = version_dir / f"{sid}.json"
    md_path = version_dir / f"{sid}.md"
    try:
        for path, content in ((json_path, json.dumps(export, ensure_ascii=False, indent=2)),
                              (md_path, "\n".join(md_lines))):
            path.write_text(content, encoding="utf-8")
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    except BaseException:
        shutil.rmtree(version_dir)
        raise
    paths = {"json": str(json_path), "markdown": str(md_path)}
    if publish:
        publish_gold_chat_paths(sid, paths, config=config)
    return paths


def publish_gold_chat_paths(source_id: str, paths: dict[str, str], *, config: Config | None = None) -> None:
    """DB 是服务读取的权威；平铺文件只作兼容缓存，整对经一个指针切换。"""
    out_dir = gold_chat_export_dir(config)
    version_dir = Path(paths["json"]).parent
    if not Path(paths["json"]).is_file() or not Path(paths["markdown"]).is_file():
        raise FileNotFoundError("稿件版本不完整，禁止更新兼容入口")
    if Path(paths["markdown"]).parent != version_dir:
        raise ValueError("JSON 和 Markdown 必须来自同一稿件版本")
    current = out_dir / f".{source_id}.current"
    token = uuid.uuid4().hex
    temporary = out_dir / f".{source_id}.{token}.link"
    try:
        # 首次迁移旧的平铺文件时，先保留完整旧版，安装链接不改变旧稿内容。
        if not current.is_symlink() and (out_dir / f"{source_id}.json").is_file():
            legacy = out_dir / ".versions" / source_id / f"legacy-{token}"
            legacy.mkdir(parents=True)
            for suffix in ("json", "md"):
                path = out_dir / f"{source_id}.{suffix}"
                if path.is_file():
                    shutil.copyfile(path, legacy / path.name)
            temporary.symlink_to(legacy.relative_to(out_dir), target_is_directory=True)
            os.replace(temporary, current)
        for suffix in ("json", "md"):
            path = out_dir / f"{source_id}.{suffix}"
            temporary.symlink_to(Path(current.name) / path.name)
            os.replace(temporary, path)
        temporary.symlink_to(os.path.relpath(version_dir, out_dir), target_is_directory=True)
        os.replace(temporary, current)
        # 保留当前版、最近一版和一天内的新版本；不清理其他正在写入的暂存版本。
        versions = out_dir / ".versions" / source_id
        from flask import has_app_context

        if versions.is_dir() and has_app_context():
            row = repo_gold_story.get_by_source_id(source_id=source_id)
            committed = str(((row or {}).get("payload") or {}).get("gold_chat_json") or "")
            protected = Path(committed).parent if committed else version_dir
            directories = sorted((p for p in versions.iterdir() if p.is_dir()),
                                 key=lambda p: p.stat().st_mtime, reverse=True)
            cutoff = datetime.now(timezone.utc).timestamp() - 86400
            for directory in directories[2:]:
                if directory not in (version_dir, protected) and directory.stat().st_mtime < cutoff:
                    shutil.rmtree(directory)
    finally:
        temporary.unlink(missing_ok=True)


def discard_gold_chat_version(paths: dict[str, str]) -> None:
    directory = Path(paths["json"]).parent
    if directory.parent.parent.name == ".versions":
        shutil.rmtree(directory, ignore_errors=True)


def load_gold_chat(
    source_id: str,
    *,
    config: Config | None = None,
) -> dict[str, Any] | None:
    """读取已导出的 gold_chat JSON；不存在则 None。"""
    sid = str(source_id or "").strip()
    if not sid:
        return None
    json_path = gold_chat_export_dir(config) / f"{sid}.json"
    if not json_path.is_file():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_gold_chat_for_row(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any] | None:
    """读取金故事行对应的 gold_chat 导出（标准路径 + payload 记录的备用路径）。"""
    sid = str(row.get("source_id") or "").strip()
    if not sid:
        return None
    payload = cast(dict[str, Any], row.get("payload") or {})
    alt_json = str(payload.get("gold_chat_json") or "").strip()
    if not alt_json:
        return load_gold_chat(sid, config=config)
    alt_path = Path(alt_json)
    if not alt_path.is_file():
        if ".versions" in alt_path.parts:
            logger.error("DB 指向的正式稿版本缺失，拒绝回退旧缓存：%s", alt_path)
        return None if ".versions" in alt_path.parts else load_gold_chat(sid, config=config)
    try:
        raw = json.loads(alt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("正式稿 JSON 损坏，拒绝回退旧缓存：%s", alt_path)
        return None
    return raw if isinstance(raw, dict) else None



def _gold_chat_quality_scores(
    daily: dict[str, Any] | None,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, int | None]:
    """列表用：结构分 + 幽默分（funny_score）。"""
    from app.services.daily_story.quality import structure_score_of

    quality = (
        daily.get("quality")
        if isinstance(daily, dict) and isinstance(daily.get("quality"), dict)
        else None
    )
    structure_score: int | None = None
    humor_score: int | None = None
    if quality:
        raw_struct = structure_score_of(quality)
        structure_score = raw_struct if raw_struct else None
        humor = quality.get("humor")
        if isinstance(humor, dict) and humor.get("funny_score") is not None:
            try:
                humor_score = int(humor["funny_score"])
            except (TypeError, ValueError):
                pass
    if payload:
        if structure_score is None and payload.get("gold_chat_structure_score") is not None:
            try:
                structure_score = int(payload["gold_chat_structure_score"])
            except (TypeError, ValueError):
                pass
        if humor_score is None and payload.get("gold_chat_humor_score") is not None:
            try:
                humor_score = int(payload["gold_chat_humor_score"])
            except (TypeError, ValueError):
                pass
    return {
        "structure_score": structure_score,
        "humor_score": humor_score,
    }


def _summary_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload.get("gold_chat_exported_at"):
        return None
    return {
        "has_gold_chat": True,
        "chat_chars": payload.get("gold_chat_chars"),
        "chat_lines": payload.get("gold_chat_lines"),
        "scene_title": payload.get("gold_chat_scene_title"),
        "exported_at": payload.get("gold_chat_exported_at"),
        "bili_title": payload.get("bili_title"),
        **_gold_chat_quality_scores(None, payload=payload),
    }


def gold_chat_summary(
    source_id: str,
    *,
    config: Config | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """列表页用的导出摘要（优先读导出 JSON，其次读库内 payload）。"""
    data = load_gold_chat_for_row(row, config=config) if row is not None else load_gold_chat(source_id, config=config)
    if data:
        daily = data.get("daily_story") if isinstance(data.get("daily_story"), dict) else {}
        chat_chars = data.get("chat_chars")
        if chat_chars is None and daily:
            chat_chars = dialogue_total_chars(daily)
        chat_lines = data.get("chat_lines")
        if chat_lines is None and daily:
            chat_lines = len(daily.get("dialogue") or [])
        payload = (
            cast(dict[str, Any], row.get("payload") or {})
            if row is not None
            else None
        )
        return {
            "has_gold_chat": True,
            "chat_chars": chat_chars,
            "chat_lines": chat_lines,
            "scene_title": daily.get("scene_title") or data.get("scene_title"),  # type: ignore[union-attr]
            "exported_at": data.get("exported_at"),
            **_gold_chat_quality_scores(
                daily if isinstance(daily, dict) else None,
                payload=payload,
            ),
        }

    if row is None:
        row = repo_gold_story.get_by_source_id(source_id=str(source_id or "").strip())
    if row:
        payload = cast(dict[str, Any], row.get("payload") or {})
        cached = _summary_from_payload(payload)
        if cached:
            return cached
    return {"has_gold_chat": False}
