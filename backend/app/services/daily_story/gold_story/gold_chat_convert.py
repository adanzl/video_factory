"""gold_chat：金故事 → 日常对白（独立流程，不入 H0–H4 采集流水线）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config
from app.services.daily_story.gold_story.types import structure_type_label
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_KEY_CHARS_MAX,
    DAILY_STORY_KEY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES
from app.services.llm.llm_mgr import llm_mgr

_SYSTEM = (
    "你是日常故事编剧。输入为金故事结构化结果（beat + dialogue_seed intent），"
    "扩写成昭昭(7岁弟)/灿灿(10岁姐)可拍对白剧本。\n"
    "输出 JSON 须与站内 daily_story 字段一致；只输出 JSON。"
)

_USER = """金故事标题：{title}
机制/结构：{mechanism} / {structure_type}（{structure_label}）
冲突核：{conflict_core}
现场：{setting}

beat：
{beat}

dialogue_seed（intent 骨架，须扩写为口语对白，禁止照抄）：
{dialogue_seed}

收束意图：{closing_intent}
禁词（对白中禁止出现）：{banned_literals}
funny_why：{funny_why}

输出 JSON：
{{
  "scene_title": "短标题",
  "setting": "可拍现场一句",
  "key": "2-8字内容标签",
  "conflict_core": "一句话冲突核",
  "dialogue": [
    {{"speaker": "昭昭|灿灿|妈妈", "line": "…"}}
  ],
  "punchline_explain": "{structure_type}类…"
}}

规则：
- 昭昭/灿灿 交替为主，妈妈少出场；口语化、可拍，不要旁白 narration
- 按 beat 顺序推进，末段落实收束意图
- 正文 dialogue 总字数 {chars_min}–{chars_max} 字（硬卡）
- 禁止直接使用禁词列表里的词
- punchline_explain 须含「{structure_type}类」前缀
- 不要输出 discovery_opening / quality 等额外字段
"""


def gold_chat_export_dir(config: Config | None = None) -> Path:
    cfg = config or Config()
    return cfg.gold_story_transcript_dir.parent / "gold_chat"


def _client():
    return llm_mgr._get_client()


def _chat_json(system: str, user: str) -> dict[str, Any]:
    raw, _finish = _client()._chat_json(
        system,
        user,
        thinking_enabled=False,
        temperature=0.4,
    )
    if not isinstance(raw, dict):
        raise ValueError("LLM JSON must be object")
    return raw


def _format_dialogue_seed(seed: list[Any]) -> str:
    lines: list[str] = []
    for item in seed or []:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if speaker and intent:
            lines.append(f"- {speaker}：{intent}")
    return "\n".join(lines) or "（无）"


def validate_gold_chat(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
) -> None:
    """gold_chat 轻量校验（不跑完整 daily_story validate）。"""
    errors: list[str] = []
    required = (
        "scene_title",
        "setting",
        "key",
        "conflict_core",
        "dialogue",
        "punchline_explain",
    )
    for field in required:
        if field not in story:
            errors.append(f"缺少字段: {field}")

    if errors:
        raise ValueError("; ".join(errors))

    key = str(story.get("key") or "").strip()
    if not (
        DAILY_STORY_KEY_CHARS_MIN <= len(key) <= DAILY_STORY_KEY_CHARS_MAX
    ):
        errors.append(
            f"key 须{DAILY_STORY_KEY_CHARS_MIN}–{DAILY_STORY_KEY_CHARS_MAX}字，"
            f"当前{len(key)}字"
        )

    dialogue = story.get("dialogue") or []
    allowed = set(DAILY_STORY_SPEAKER_NAMES)
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        errors.append("dialogue 至少 4 句")
    else:
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                errors.append(f"dialogue[{i}] 不是字典")
                continue
            sp = str(item.get("speaker") or "").strip()
            line = str(item.get("line") or "").strip()
            if sp not in allowed:
                errors.append(f"dialogue[{i}] speaker 非法: {sp!r}")
            if not line:
                errors.append(f"dialogue[{i}] line 为空")

    total = dialogue_total_chars(story)
    if total < DAILY_STORY_BODY_CHARS_MIN:
        errors.append(
            f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前{total}"
        )
    if total > DAILY_STORY_BODY_CHARS_MAX:
        errors.append(
            f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}"
        )

    explain = str(story.get("punchline_explain") or "").strip()
    if not explain:
        errors.append("punchline_explain 为空")

    banned = [str(x).strip() for x in (banned_literals or []) if str(x).strip()]
    if banned and isinstance(dialogue, list):
        body = "\n".join(
            str(item.get("line") or "")
            for item in dialogue
            if isinstance(item, dict)
        )
        hits = [w for w in banned if w and w in body]
        if hits:
            errors.append(f"对白含禁词: {'、'.join(hits[:5])}")

    if errors:
        raise ValueError("; ".join(errors))


def gold_story_to_gold_chat(row: dict[str, Any]) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    structure_type = str(row.get("structure_type") or "A").strip().upper()
    st_label = structure_type_label(structure_type)
    beat = payload.get("beat") or []
    seed = payload.get("dialogue_seed") or []
    banned = payload.get("banned_literals") or []

    user = _USER.format(
        title=str(row.get("title") or ""),
        mechanism=str(row.get("mechanism") or ""),
        structure_type=structure_type,
        structure_label=st_label,
        conflict_core=str(row.get("conflict_core") or "")[:500],
        setting=str(payload.get("setting") or "")[:300],
        beat=json.dumps(beat, ensure_ascii=False, indent=2)[:3000],
        dialogue_seed=_format_dialogue_seed(seed)[:4000],
        closing_intent=str(payload.get("closing_intent") or "")[:500],
        banned_literals="、".join(str(x) for x in banned) or "（无）",
        funny_why=str(payload.get("funny_why") or "")[:500],
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
    )
    data = _chat_json(_SYSTEM, user)
    validate_gold_chat(data, banned_literals=list(banned))
    return data


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


def export_gold_chat_files(
    *,
    source_id: str,
    row: dict[str, Any],
    chat: dict[str, Any],
    config: Config | None = None,
) -> dict[str, str]:
    """导出 JSON + 可读 MD 到 data/gold_story/gold_chat/。"""
    sid = str(source_id or row.get("source_id") or "").strip()
    out_dir = gold_chat_export_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    export = {
        "gold_story_id": row.get("id"),
        "source_id": sid,
        "url": row.get("url"),
        "title": row.get("title"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "status": row.get("status"),
        "conflict_core": row.get("conflict_core"),
        "chat_chars": dialogue_total_chars(chat),
        "chat_lines": len(chat.get("dialogue") or []),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "daily_story": chat,
        "gold_meta": {
            "beat": payload.get("beat"),
            "dialogue_seed": payload.get("dialogue_seed"),
            "banned_literals": payload.get("banned_literals"),
            "closing_intent": payload.get("closing_intent"),
        },
    }

    json_path = out_dir / f"{sid}.json"
    md_path = out_dir / f"{sid}.md"
    json_path.write_text(
        json.dumps(export, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        f"# {chat.get('scene_title') or row.get('title') or sid}",
        "",
        f"- BV: {sid}",
        f"- URL: {row.get('url') or ''}",
        f"- 金故事 status: {row.get('status') or ''}",
        f"- 机制: {row.get('mechanism')} / 结构: {row.get('structure_type')}",
        f"- 对白: {export['chat_lines']} 句 / {export['chat_chars']} 字",
        "",
        "## 元数据",
        f"- setting: {chat.get('setting') or ''}",
        f"- key: {chat.get('key') or ''}",
        f"- conflict_core: {chat.get('conflict_core') or ''}",
        f"- punchline_explain: {chat.get('punchline_explain') or ''}",
        "",
        "## 对白",
        "",
    ]
    md_lines.extend(_chat_md_lines(chat.get("dialogue") or []))
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def convert_gold_chat(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any]:
    """转换 + 落盘，返回摘要。"""
    sid = str(row.get("source_id") or "").strip()
    chat = gold_story_to_gold_chat(row)
    paths = export_gold_chat_files(
        source_id=sid,
        row=row,
        chat=chat,
        config=config,
    )
    return {
        "ok": True,
        "source_id": sid,
        "gold_story_id": row.get("id"),
        "chat_chars": dialogue_total_chars(chat),
        "chat_lines": len(chat.get("dialogue") or []),
        "scene_title": chat.get("scene_title"),
        "export": paths,
        "daily_story": chat,
    }


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


def gold_chat_summary(source_id: str, *, config: Config | None = None) -> dict[str, Any]:
    """列表页用的导出摘要。"""
    data = load_gold_chat(source_id, config=config)
    if not data:
        return {"has_gold_chat": False}
    daily = data.get("daily_story") if isinstance(data.get("daily_story"), dict) else {}
    chat_chars = data.get("chat_chars")
    if chat_chars is None and daily:
        chat_chars = dialogue_total_chars(daily)
    chat_lines = data.get("chat_lines")
    if chat_lines is None and daily:
        chat_lines = len(daily.get("dialogue") or [])
    return {
        "has_gold_chat": True,
        "chat_chars": chat_chars,
        "chat_lines": chat_lines,
        "scene_title": daily.get("scene_title") or data.get("scene_title"),
        "exported_at": data.get("exported_at"),
    }
