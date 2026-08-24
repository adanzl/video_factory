"""gold_chat：金故事 → 日常对白（独立流程，不入 H0–H4 采集流水线）。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.collect import fetch_video_meta
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.gold_story.llm_steps import (
    GOLD_CHAT_LINES_SNIPPET,
)
from app.services.daily_story.gold_story.scene_contract import (
    format_scene_contract_block,
    sanitize_banned_literals,
    validate_chat_hard,
)
from app.services.daily_story.gold_story.types import structure_type_label
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_KEY_CHARS_MAX,
    DAILY_STORY_KEY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.llm.llm_mgr import llm_mgr

logger = logging.getLogger(__name__)

# 润色：暴力语义软化提示（具体改法交给 LLM，不在代码里写死替换句）
_VIOLENCE_WORD_HINTS: tuple[tuple[str, str], ...] = (
    ("动手", "跟人闹了"),
    ("挂彩", "弄成这样"),
    ("揍", "欺负"),
)

_ZHAOZHAO_WA_PREFIX = re.compile(r"^我……+")

_SYSTEM = (
    "你是日常故事编剧。输入为金故事 scene_contract（可拍场景契约）"
    "与 dialogue_seed intent，扩写成昭昭(7岁弟)/灿灿(10岁姐)可拍对白剧本。\n"
    "站外口播/科普/第三人称论述须 **还原成第一人称现场对白**："
    "角色当场说、当场吵、当场做，禁止转述「妈妈说/教过/曾经」。\n"
    "站外爸爸/父亲/宝爸须写为妈妈（少出场）；speaker 只允许昭昭/灿灿/妈妈。\n"
    "输出 JSON 须与站内 daily_story 字段一致；只输出 JSON。"
)

_USER = """金故事标题：{title}
机制/结构：{mechanism} / {structure_type}（{structure_label}）
冲突核：{conflict_core}

{scene_contract_block}

dialogue_seed（intent 骨架，须扩写为口语对白，禁止照抄）：
{dialogue_seed}

收束意图：{closing_intent}
映射说明：{speaker_map_note}
story_raw（背景，勿照抄；口播/论述须转现场对白）：{story_raw}
禁词（对白中禁止出现）：{banned_literals}
funny_why：{funny_why}
source_type：{source_type}（tutorial 时禁保留教程口吻/第几招）
{structure_hint}

{gold_chat_snippet}

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
- **第一人称现场对白**：每句是角色对另一角色当场说的话；禁第三人称论述、禁转述（「妈妈说/教过/说过」）
- 口播/育儿科普/「第几招」：选一个具体场面演出来，勿保留教程口吻
- 严格按 scene_contract.beat_chain 顺序推进；妈妈台词 ≤ scene_contract.mom_lines_max
- **须覆盖 story_raw / beat 关键拍**（伤情/碘伏、妈妈问谁先动手、齐声不打了等）；
  closing_intent 原意优先，**禁止**用无关暖梗（交换礼物/彩虹/酒窝等）替换金稿收束
- **正例只允许上方金稿对白**；语气/句长可参考，剧情须来自本稿 scene_contract + seed
- 昭昭/灿灿 交替为主，妈妈少出场；口语化、可拍
- line 禁止括号舞台说明（如「（从厨房走出来）」「（语塞）」）
- 站外爸爸/父亲/宝爸一律写妈妈，勿用爸爸作 speaker
- 站外陌生小孩/对方家长→映射为灿灿/妈妈，**禁止**「小男孩」「对方」等第三 speaker
- 按 beat 顺序推进，末段落实收束意图
- 正文 dialogue 总字数 {chars_min}–{chars_max} 字（硬卡）
- **首稿须一次写到 ≥{chars_min} 字**，建议 18–24 句、均句 ≤16 字；勿写短稿
- 禁止直接使用禁词列表里的词
- punchline_explain 须含「{structure_type}类」前缀
- 不要输出 discovery_opening / quality 等额外字段
"""


_FIX_SYSTEM = (
    "你是日常故事编辑。根据校验错误修正 JSON。\n"
    "须改成第一人称现场对白：角色当场说，禁止转述/旁白/括号说明。\n"
    "speaker 只允许昭昭/灿灿/妈妈（爸爸/父亲须改为妈妈）。\n"
    "只输出完整 JSON。"
)

_FIX_USER = """校验错误：
{errors}

当前 JSON：
{story_json}

规则：
- 正文 dialogue 总字数 {chars_min}–{chars_max}（不足则 **扩写** 到 ≥{chars_min}，建议 18–24 句）
- 对白句数须 ≥12；每句 ≤30 字，口语化、可拍
- 妈妈台词须 ≤{mom_lines_max} 句；末句不能是妈妈
- 禁词须同义改写：{banned_literals}
- 转述/旁白/括号说明须改为当场对白
- speaker 非法须改为昭昭/灿灿/妈妈
只输出 JSON。"""

_FATHER_SPEAKER_ALIASES = frozenset(
    {"爸爸", "父亲", "爸", "老爸", "宝爸", "爸爸角色", "父亲角色"}
)
_KID_RIVAL_ALIASES = frozenset(
    {"小男孩", "小女孩", "对方", "对方小朋友", "陌生小孩", "小朋友", "对方孩子"}
)
_THIRD_PARTY_PARENT_ALIASES = frozenset({"对方家长", "对方妈妈", "对方爸爸"})


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


def _normalize_chat_speakers(story: dict[str, Any]) -> dict[str, Any]:
    """站外爸爸/父亲 speaker → 妈妈。"""
    out = dict(story)
    dialogue: list[dict[str, Any]] = []
    for item in story.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        if sp in _FATHER_SPEAKER_ALIASES or sp in _THIRD_PARTY_PARENT_ALIASES:
            row["speaker"] = "妈妈"
        elif sp in _KID_RIVAL_ALIASES:
            row["speaker"] = "灿灿"
        dialogue.append(row)
    out["dialogue"] = dialogue
    return out


def _fix_chat_with_llm(
    story: dict[str, Any],
    errors: str,
    *,
    banned_literals: list[str],
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    user = _FIX_USER.format(
        errors=errors,
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
    )
    return _chat_json(_FIX_SYSTEM, user)


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
    source_type: str = "",
    mom_lines_max: int | None = None,
) -> None:
    """gold_chat 校验（字段 + scene_contract hard 规则）。"""
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

    key = str(story.get("key") or "").strip()
    if key and not (
        DAILY_STORY_KEY_CHARS_MIN <= len(key) <= DAILY_STORY_KEY_CHARS_MAX
    ):
        errors.append(
            f"key 须{DAILY_STORY_KEY_CHARS_MIN}–{DAILY_STORY_KEY_CHARS_MAX}字，"
            f"当前{len(key)}字"
        )

    explain = str(story.get("punchline_explain") or "").strip()
    if "punchline_explain" in story and not explain:
        errors.append("punchline_explain 为空")

    errors.extend(
        validate_chat_hard(
            story,
            banned_literals=banned_literals,
            source_type=source_type,
            mom_lines_max=mom_lines_max,
        )
    )

    if errors:
        raise ValueError("; ".join(errors))


def _is_short_content_error(msg: str) -> bool:
    """字数/句数不足 → 不重试，直接放弃。"""
    return (
        "正文总字数须≥" in msg
        or "dialogue 至少" in msg
        or "对白句数须≥" in msg
    )


def _structure_type_hint(structure_type: str) -> str:
    st = str(structure_type or "").strip().upper()
    if st == "H":
        return """【H 第三方化解 · 须贴近 story_raw / beat】
- 前段：抢看/互毁/扭打 escalating；story_raw 有伤情则须可拍（蹭破/涂碘伏等）
- 妈妈：先问「谁先动手」再定责劝和；台词 2–4 句，末句宜姐弟
- 收束：灿灿问「以后还打不打架？」+ 齐声「不打了！」；可补碘伏/涂药一拍
- 非 G 内部 pivot；勿自编交换画作/彩虹等站内暖梗替换金稿收束"""
    return ""


def gold_story_to_gold_chat(row: dict[str, Any]) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    structure_type = str(row.get("structure_type") or "A").strip().upper()
    st_label = structure_type_label(structure_type)
    scene_contract = payload.get("scene_contract") or {}
    seed = payload.get("dialogue_seed") or []
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    source_type = str(payload.get("source_type") or scene_contract.get("source_type") or "field")
    story_raw = str(row.get("story_raw") or payload.get("story_raw") or "")[:800]
    mom_max = scene_contract.get("mom_lines_max")
    if mom_max is None:
        mom_max = 1

    user = _USER.format(
        title=str(row.get("title") or ""),
        mechanism=str(row.get("mechanism") or ""),
        structure_type=structure_type,
        structure_label=st_label,
        conflict_core=str(row.get("conflict_core") or "")[:500],
        scene_contract_block=format_scene_contract_block(scene_contract),
        dialogue_seed=_format_dialogue_seed(seed)[:4000],
        closing_intent=str(payload.get("closing_intent") or scene_contract.get("closing_intent") or "")[:500],
        speaker_map_note=str(payload.get("speaker_map_note") or scene_contract.get("remap_note") or "")[:500],
        story_raw=story_raw or "（无）",
        banned_literals="、".join(str(x) for x in banned) or "（无）",
        funny_why=str(payload.get("funny_why") or "")[:500],
        source_type=source_type,
        structure_hint=_structure_type_hint(structure_type),
        gold_chat_snippet=GOLD_CHAT_LINES_SNIPPET,
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
    )
    data = _chat_json(_SYSTEM, user)
    banned_list = [str(x) for x in banned]
    data = _normalize_chat_speakers(data)
    last_err = ""
    for attempt in range(5):
        try:
            validate_gold_chat(
                data,
                banned_literals=banned_list,
                source_type=source_type,
                mom_lines_max=int(mom_max),
            )
            return data
        except ValueError as exc:
            last_err = str(exc)
            if attempt >= 4:
                raise ValueError(last_err) from exc
            data = _fix_chat_with_llm(
                data,
                last_err,
                banned_literals=banned_list,
                mom_lines_max=int(mom_max),
            )
            data = _normalize_chat_speakers(data)
    raise ValueError(last_err or "gold_chat validate failed")


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


def _bili_meta_patch(source_id: str, *, config: Config) -> dict[str, Any]:
    sid = str(source_id or "").strip()
    if not sid.startswith("BV"):
        return {}
    try:
        meta = fetch_video_meta(sid, config=config)
    except Exception as exc:
        logger.warning("gold_chat bili meta failed bvid=%s: %s", sid, exc)
        return {}
    url = str(meta.get("url") or "").strip() or f"https://www.bilibili.com/video/{sid}"
    patch: dict[str, Any] = {
        "bili_title": meta.get("title"),
        "bili_url": url,
        "bili_view_count": meta.get("view_count"),
        "bili_reply_count": meta.get("reply_count"),
    }
    return {k: v for k, v in patch.items() if v not in (None, "")}


def _backfill_gold_story_after_export(
    row: dict[str, Any],
    *,
    chat: dict[str, Any],
    paths: dict[str, str],
    config: Config,
) -> None:
    """gold_chat 导出后回写库内摘要与 B 站元数据。"""
    gid = int(row.get("id") or 0)
    sid = str(row.get("source_id") or "").strip()
    if gid <= 0 or not sid:
        return

    payload_patch = {
        **_bili_meta_patch(sid, config=config),
        "gold_chat_exported_at": datetime.now(timezone.utc).isoformat(),
        "gold_chat_scene_title": chat.get("scene_title"),
        "gold_chat_lines": len(chat.get("dialogue") or []),
        "gold_chat_chars": dialogue_total_chars(chat),
        "gold_chat_json": paths.get("json"),
        "gold_chat_md": paths.get("markdown"),
    }
    repo_gold_story.patch_story_payload(gid, payload_patch)

    bili_url = payload_patch.get("bili_url")
    if isinstance(bili_url, str) and bili_url.strip():
        repo_gold_story.update_story_source_fields(gid, url=bili_url.strip())

    try:
        fresh = repo_gold_story.get_story(gid)
        export_story_files(source_id=sid, row=fresh, config=config)
    except Exception as exc:
        logger.warning("gold_chat story export failed id=%s: %s", gid, exc)


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
            "source_type": payload.get("source_type"),
            "scene_contract": payload.get("scene_contract"),
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
    cfg = config or Config()
    paths = export_gold_chat_files(
        source_id=sid,
        row=row,
        chat=chat,
        config=cfg,
    )
    _backfill_gold_story_after_export(row, chat=chat, paths=paths, config=cfg)
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


def load_gold_chat_for_row(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any] | None:
    """读取金故事行对应的 gold_chat 导出（标准路径 + payload 记录的备用路径）。"""
    sid = str(row.get("source_id") or "").strip()
    if not sid:
        return None
    export = load_gold_chat(sid, config=config)
    if export is not None:
        return export
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    alt_json = str(payload.get("gold_chat_json") or "").strip()
    if not alt_json:
        return None
    alt_path = Path(alt_json)
    if not alt_path.is_file():
        return None
    try:
        raw = json.loads(alt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def import_gold_chat_daily_story(
    row: dict[str, Any],
    *,
    config: Config | None = None,
    force: bool = False,
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

    story = dict(chat)
    sync_discovery_opening_from_dialogue(story)
    attach_daily_story_quality(story)

    theme = str(
        story.get("scene_title")
        or story.get("key")
        or row.get("title")
        or sid
    ).strip()
    story_type = str(row.get("structure_type") or "").strip().upper()[:1] or None
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
    }


def gold_chat_summary(
    source_id: str,
    *,
    config: Config | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """列表页用的导出摘要（优先读导出 JSON，其次读库内 payload）。"""
    data = load_gold_chat(source_id, config=config)
    if data:
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

    if row is None:
        row = repo_gold_story.get_by_source_id(source_id=str(source_id or "").strip())
    if row:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        cached = _summary_from_payload(payload)
        if cached:
            return cached
    return {"has_gold_chat": False}


def collect_gold_chat_polish_issues(story: dict[str, Any]) -> list[dict[str, Any]]:
    """规则收集 gold_chat 润色点，交给 daily_story 童语化润色模块。"""
    issues: list[dict[str, Any]] = []
    rows = story.get("dialogue") or []
    wa_kept = 0
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if not line:
            continue
        if sp == "昭昭" and _ZHAOZHAO_WA_PREFIX.match(line):
            wa_kept += 1
            if wa_kept > 2:
                issues.append(
                    {
                        "lines": [i],
                        "kind": "复读结巴",
                        "desc": f"昭昭「我……」开头过多（第{wa_kept}处）：{line}",
                        "fix": "改成短句直接说（如「不是。」「我跑了。」），"
                        "勿再以「我……」开头；保留怂/委屈语气",
                    }
                )
        if "跟个娘们似的" in line or "跟个娘们" in line:
            issues.append(
                {
                    "lines": [i],
                    "kind": "措辞",
                    "desc": line,
                    "fix": "删除「跟个娘们似的」等性别贬义，保留「还充大侠呢」等数落",
                }
            )
        for word, hint in _VIOLENCE_WORD_HINTS:
            if word in line:
                issues.append(
                    {
                        "lines": [i],
                        "kind": "暴力词",
                        "desc": f"含「{word}」：{line}",
                        "fix": f"软化暴力语义，可改成更儿童化的说法（如「{hint}」），保持原意",
                    }
                )
        if sp == "昭昭" and line in {"嘿嘿。", "嘿嘿"}:
            issues.append(
                {
                    "lines": [i],
                    "kind": "收束",
                    "desc": line,
                    "fix": "改成更贴7岁的短反应，如「哦。」或「那你说话算数。」",
                }
            )
    return issues


def _apply_gold_chat_polish_fixes(
    chat: dict[str, Any],
    raw_fixes: Any,
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "field",
    mom_lines_max: int = 0,
) -> tuple[dict[str, Any], set[int]]:
    from app.services.daily_story.review import apply_spot_fixes, fix_line_numbers

    accepted: set[int] = set()
    for no in fix_line_numbers(raw_fixes):
        trial = accepted | {no}
        fixed, notes = apply_spot_fixes(chat, raw_fixes, only=trial)
        if not notes:
            continue
        try:
            validate_gold_chat(
                fixed,
                banned_literals=banned_literals,
                source_type=source_type,
                mom_lines_max=mom_lines_max,
            )
        except ValueError as exc:
            logger.info("gold_chat polish line %d dropped: %s", no, exc)
            continue
        accepted = trial
    if not accepted:
        return chat, accepted
    fixed, _ = apply_spot_fixes(chat, raw_fixes, only=accepted)
    validate_gold_chat(
        fixed,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
    )
    return fixed, accepted


def _repair_gold_chat_after_polish(chat: dict[str, Any]) -> dict[str, Any]:
    """润色模块会误删首句「昭昭，」，此处补回。"""
    out = dict(chat)
    rows: list[dict[str, Any]] = []
    first_cancan = True
    for item in chat.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if sp == "灿灿" and first_cancan:
            first_cancan = False
            if line.startswith("，") or line.startswith(","):
                row["line"] = "昭昭" + line
            elif line and not line.startswith("昭昭"):
                row["line"] = f"昭昭，{line}"
        rows.append(row)
    out["dialogue"] = rows
    return out


def polish_gold_chat_wording(
    chat: dict[str, Any],
    *,
    theme: str = "",
    banned_literals: list[str] | None = None,
    source_type: str = "field",
    mom_lines_max: int = 0,
) -> tuple[dict[str, Any], int]:
    """复用 daily_story 童语化润色，只改被点行。"""
    issues = collect_gold_chat_polish_issues(chat)
    if not issues:
        return chat, 0
    client = llm_mgr._get_client()
    polish = getattr(client, "polish_daily_story_wording", None)
    if not callable(polish):
        return chat, 0
    raw = polish(
        theme or str(chat.get("scene_title") or ""),
        chat,
        issues,
        type_code="C",
    )
    fixed, accepted = _apply_gold_chat_polish_fixes(
        chat,
        raw,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
    )
    fixed = _repair_gold_chat_after_polish(fixed)
    try:
        validate_gold_chat(
            fixed,
            banned_literals=banned_literals,
            source_type=source_type,
            mom_lines_max=mom_lines_max,
        )
    except ValueError:
        return chat, 0
    return fixed, len(accepted)


def polish_gold_chat_export(
    source_id: str,
    *,
    config: Config | None = None,
) -> dict[str, Any]:
    """对已导出 gold_chat 做润色并回写 JSON/MD。"""
    cfg = config or Config()
    sid = str(source_id or "").strip()
    export = load_gold_chat(sid, config=cfg)
    if not export:
        raise FileNotFoundError(f"尚未导出 gold_chat: {sid}")
    chat = export.get("daily_story")
    if not isinstance(chat, dict):
        raise ValueError("gold_chat export missing daily_story")

    row = repo_gold_story.get_by_source_id(source_id=sid, source="bili")
    if not row:
        row = {"source_id": sid, "id": export.get("gold_story_id")}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    scene_contract = payload.get("scene_contract") or {}
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    source_type = str(payload.get("source_type") or scene_contract.get("source_type") or "field")
    mom_max = scene_contract.get("mom_lines_max")
    if mom_max is None:
        mom_max = 0

    issues_before = collect_gold_chat_polish_issues(chat)
    polished, accepted_n = polish_gold_chat_wording(
        chat,
        theme=str(chat.get("scene_title") or row.get("title") or sid),
        banned_literals=banned,
        source_type=source_type,
        mom_lines_max=int(mom_max),
    )
    polished = _repair_gold_chat_after_polish(polished)
    paths = export_gold_chat_files(
        source_id=sid,
        row=row,
        chat=polished,
        config=cfg,
    )
    return {
        "ok": True,
        "source_id": sid,
        "issues_before": len(issues_before),
        "lines_polished": accepted_n,
        "chat_chars": dialogue_total_chars(polished),
        "chat_lines": len(polished.get("dialogue") or []),
        "export": paths,
        "daily_story": polished,
    }
