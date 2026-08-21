"""入库后导出可读 story 文件到 data/gold_story/stories/。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import Config
from app.services.daily_story.gold_story.transcript import format_transcript_display


def story_export_dir(config: Config | None = None) -> Path:
    cfg = config or Config()
    return cfg.gold_story_transcript_dir.parent / "stories"


def _read_transcript_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_transcript_text(
    *,
    source_id: str,
    row: dict[str, Any],
    config: Config | None = None,
) -> str:
    cfg = config or Config()
    raw_path = str(row.get("transcript_path") or "").strip()
    path = Path(raw_path) if raw_path else cfg.gold_story_transcript_dir / f"{source_id}.txt"
    return _read_transcript_file(path)


def _load_repaired_transcript_text(
    *,
    source_id: str,
    row: dict[str, Any],
    config: Config | None = None,
) -> str:
    cfg = config or Config()
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    raw_path = str(payload.get("transcript_repaired_path") or "").strip()
    path = (
        Path(raw_path)
        if raw_path
        else cfg.gold_story_transcript_dir / f"{source_id}.repaired.txt"
    )
    return _read_transcript_file(path)


def export_story_files(
    *,
    source_id: str,
    row: dict[str, Any],
    config: Config | None = None,
) -> dict[str, str]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    sid = str(source_id or row.get("source_id") or row.get("id"))
    transcript_raw = _load_transcript_text(source_id=sid, row=row, config=config)
    transcript_repaired = _load_repaired_transcript_text(
        source_id=sid,
        row=row,
        config=config,
    )
    transcript_main = transcript_repaired or transcript_raw
    transcript_raw_display = format_transcript_display(transcript_raw)
    transcript_main_display = format_transcript_display(transcript_main)
    export = {
        "id": row.get("id"),
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "url": row.get("url"),
        "title": row.get("title"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "theme_family": row.get("theme_family"),
        "conflict_core": row.get("conflict_core"),
        "auto_score": row.get("auto_score"),
        "story_raw": payload.get("story_raw") or "",
        "transcript": transcript_main,
        "transcript_raw": transcript_raw,
        "transcript_repaired": transcript_repaired,
        "transcript_backend": row.get("transcript_backend"),
        "transcript_path": row.get("transcript_path"),
        "transcript_repaired_path": payload.get("transcript_repaired_path"),
        "transcript_repair_confidence": payload.get("transcript_repair_confidence"),
        "transcript_speakers": payload.get("transcript_speakers"),
        "transcript_repair_notes": payload.get("transcript_repair_notes"),
        "beat": payload.get("beat"),
        "dialogue_seed": payload.get("dialogue_seed"),
        "closing_intent": payload.get("closing_intent"),
        "banned_literals": payload.get("banned_literals"),
        "funny_why": payload.get("funny_why"),
        "speaker_map_note": payload.get("speaker_map_note"),
        "extract_confidence": payload.get("extract_confidence"),
        "structure_confidence": payload.get("structure_confidence"),
        "dialogue_confidence": payload.get("dialogue_confidence"),
    }
    out_dir = story_export_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{sid}.json"
    md_path = out_dir / f"{sid}.md"
    json_path.write_text(
        json.dumps(export, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_lines = [
        f"# {export.get('title') or '金故事'}",
        "",
        f"- BV: {export.get('source_id')}",
        f"- URL: {export.get('url')}",
        f"- 机制: {export.get('mechanism')} / 结构: {export.get('structure_type')}",
        f"- auto_score: {export.get('auto_score')}",
        f"- story_raw 字数: {len(str(export.get('story_raw') or ''))}",
        f"- 逐字稿字数: {len(transcript_main.replace(chr(10), ''))}",
        "",
        "## 冲突核",
        str(export.get("conflict_core") or ""),
        "",
        "## 逐字稿（修复 + 说话人）",
        transcript_main_display or "（无）",
        "",
        "## ASR 原文",
        transcript_raw_display or "（无）",
        "",
        "## story_raw",
        str(export.get("story_raw") or "（空）"),
        "",
        "## beat",
    ]
    for i, beat in enumerate(export.get("beat") or [], 1):
        md_lines.append(f"{i}. {beat}")
    md_lines.extend(["", "## dialogue_seed"])
    for item in export.get("dialogue_seed") or []:
        md_lines.append(f"- {item.get('speaker')}: {item.get('intent')}")
    md_lines.extend(
        [
            "",
            "## 收束 / 禁词",
            f"收束: {export.get('closing_intent') or ''}",
            f"禁词: {'、'.join(export.get('banned_literals') or [])}",
            "",
            f"funny_why: {export.get('funny_why') or ''}",
            f"speaker_map_note: {export.get('speaker_map_note') or ''}",
        ]
    )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
