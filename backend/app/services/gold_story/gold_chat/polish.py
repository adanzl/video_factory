"""gold_chat 独有润色 issue；通用走 daily_story.review。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.export import (
    export_gold_chat_files,
    load_gold_chat,
)
from app.services.daily_story.prompts import dialogue_total_chars
from app.services.gold_story.scene import sanitize_banned_literals
from app.services.llm.llm_mgr import llm_mgr

logger = logging.getLogger(__name__)


@dataclass
class PolishResult:
    """润色定点改结果；失败时 candidate 为被校验的稿，不可直接导出。"""

    candidate: dict[str, Any]
    accepted: set[int] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


# 润色：暴力语义软化提示（具体改法交给 LLM，不在代码里写死替换句）
_VIOLENCE_WORD_HINTS: tuple[tuple[str, str], ...] = (
    ("动手", "跟人闹了"),
    ("挂彩", "弄成这样"),
    ("揍", "欺负"),
)

_ZHAO_WA_PREFIX = re.compile(r"^我……+")
# 句内同短语重复（口语 fight 常用，抽象非单篇）
_INTRA_LINE_ORAL_PHRASE = re.compile(
    r"试试看|来试试|来啊|谁怕谁|还不服|不认输|你等着|别闹"
)


def _collect_intra_line_repeat_issues(
    line: str,
    line_no: int,
) -> list[dict[str, Any]]:
    """同一句内口头短语重复 ≥2 次 → 润色点（不走类型 patch）。"""
    text = str(line or "").strip()
    if not text or len(text) < 8:
        return []
    counts: dict[str, int] = {}
    for m in _INTRA_LINE_ORAL_PHRASE.finditer(text):
        key = m.group(0)
        counts[key] = counts.get(key, 0) + 1
    out: list[dict[str, Any]] = []
    for phrase, n in counts.items():
        if n < 2:
            continue
        out.append(
            {
                "lines": [line_no],
                "kind": "句内重复",
                "desc": f"第{line_no}句「{phrase}」在同句出现{n}次：{text}",
                "fix": f"合并为一次「{phrase}」，删同句内重复，语气保留",
            }
        )
    return out


def collect_gold_chat_polish_issues(story: dict[str, Any]) -> list[dict[str, Any]]:
    """规则收集 gold_chat 润色点，交给 daily_story 童语化润色模块。"""
    from app.services.daily_story.review import (
        collect_narration_meta_issues,
        collect_pad_stack_issues,
    )

    issues: list[dict[str, Any]] = list(collect_narration_meta_issues(story))
    issues.extend(collect_pad_stack_issues(story))
    rows = story.get("dialogue") or []
    wa_kept = 0
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if not line:
            continue
        if sp == "昭昭" and _ZHAO_WA_PREFIX.match(line):
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
        issues.extend(_collect_intra_line_repeat_issues(line, i))
    return issues


def _raw_polish_fixes_well_formed(raw_fixes: Any) -> bool:
    if not isinstance(raw_fixes, dict):
        return False
    fixes = raw_fixes.get("fixes")
    if fixes is None:
        return True
    if not isinstance(fixes, list):
        return False
    for item in fixes:
        if not isinstance(item, dict):
            return False
        if "no" not in item and "line" not in item and "lines" not in item:
            return False
    return True


def _apply_gold_chat_polish_fixes(
    chat: dict[str, Any],
    raw_fixes: Any,
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "field",
    mom_lines_max: int = 0,
    rejection_reasons: list[str] | None = None,
) -> PolishResult:
    from app.services.gold_story.gold_chat.convert import (
        _ensure_gold_chat_min_chars,
        patch_sanitize_pad_suffix,
        validate_gold_chat,
    )
    from app.services.daily_story.review import apply_spot_fixes, fix_line_numbers

    def _record_rejection(reason: str) -> None:
        if rejection_reasons is not None:
            rejection_reasons.append(reason)

    if not _raw_polish_fixes_well_formed(raw_fixes):
        err = "polish_fixes 格式无效"
        _record_rejection(err)
        return PolishResult(candidate=dict(chat), accepted=set(), errors=[err])

    all_nos = set(fix_line_numbers(raw_fixes))
    if not all_nos:
        return PolishResult(candidate=dict(chat), accepted=set(), errors=[])

    fixed, notes = apply_spot_fixes(chat, raw_fixes, only=all_nos)
    if not notes:
        err = "polish_fixes 未落地"
        _record_rejection(err)
        return PolishResult(candidate=dict(chat), accepted=set(), errors=[err])

    accepted = set(all_nos)
    fixed, _ = _ensure_gold_chat_min_chars(fixed)
    fixed, _ = patch_sanitize_pad_suffix(fixed)
    fixed, _ = _ensure_gold_chat_min_chars(fixed)
    fixed, _ = patch_sanitize_pad_suffix(fixed)
    try:
        validate_gold_chat(
            fixed,
            banned_literals=banned_literals,
            source_type=source_type,
            mom_lines_max=mom_lines_max,
        )
    except ValueError as exc:
        reason = str(exc)
        logger.info("gold_chat polish batch dropped: %s", reason)
        _record_rejection(reason)
        return PolishResult(
            candidate=fixed,
            accepted=set(),
            errors=[reason],
        )
    return PolishResult(candidate=fixed, accepted=accepted, errors=[])


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
    type_code = str(chat.get("story_type") or "").strip().upper()[:1] or None
    raw = polish(
        theme or str(chat.get("scene_title") or ""),
        chat,
        issues,
        type_code=type_code,
    )
    from app.services.gold_story.gold_chat.convert import (
        validate_gold_chat,
    )

    polish_result = _apply_gold_chat_polish_fixes(
        chat,
        raw,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
    )
    if polish_result.errors:
        return chat, 0
    fixed = _repair_gold_chat_after_polish(polish_result.candidate)
    try:
        validate_gold_chat(
            fixed,
            banned_literals=banned_literals,
            source_type=source_type,
            mom_lines_max=mom_lines_max,
        )
    except ValueError:
        return chat, 0
    return fixed, len(polish_result.accepted)


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
    payload = cast(dict[str, Any], row.get("payload") or {})
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
    from app.services.gold_story.gold_chat.convert import (
        _ensure_gold_chat_min_chars,
        patch_sanitize_pad_suffix,
    )

    polished = _repair_gold_chat_after_polish(polished)
    polished, _ = patch_sanitize_pad_suffix(polished)
    polished, _ = _ensure_gold_chat_min_chars(polished)
    polished, _ = patch_sanitize_pad_suffix(polished)
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
