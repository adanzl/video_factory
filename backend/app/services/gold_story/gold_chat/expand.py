"""gold_chat 扩写：契约 + seed → LLM 初稿。

阶段一（expand）。入口 ``gold_story_to_gold_chat``；
精修见 ``refine.py``，终稿见 ``finalize.py``。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
    patch_m5_break_sibling_consecutive,
    patch_remap_sibling_terms,
)
from app.services.gold_story.gold_chat.length import (
    GOLD_CHAT_NEAR_MISS_DEFICIT_MAX,
    _apply_deterministic_shorten,
    _boost_short_with_mid_lines,
    _ensure_gold_chat_min_chars,
    _expand_short_gold_chat_lines,
    _gold_chat_force_min_chars,
    _j_lose_line_index,
    _overlong_line_indices,
    _pad_gold_chat_to_min_chars,
    patch_sanitize_bridge_lines,
    patch_sanitize_c_tone_stack,
    patch_sanitize_expand_clutter,
    patch_sanitize_natural_expand_stack,
    patch_sanitize_pad_particles,
    patch_sanitize_pad_suffix,
)
from app.services.daily_story.story_types import (
    patch_c_force_sibling_alternate,
    patch_c_possession_criterion,
    patch_j_cap_trailing_particles,
    patch_j_cap_ya_particles,
    patch_j_dedupe_cross_line_phrases,
    patch_j_dedupe_plea_rounds,
    patch_j_drop_post_lose_bridge,
    patch_j_drop_post_lose_plea,
    patch_j_drop_post_lose_rematch,
    patch_j_ensure_post_lose_alternate,
    patch_j_ensure_post_lose_can_press,
    patch_j_fix_can_closing_after_grumble,
    patch_j_fix_lose_speaker,
    patch_j_fix_post_lose_consecutive_can,
    patch_j_fix_strongest_form_wording,
    patch_j_plea_veto_speakers,
    patch_j_soften_closing_grumble,
    patch_j_strip_post_lose_defiant,
    patch_j_strip_role_mismatch_expands,
)
from app.services.gold_story.gold_chat.prompts import (
    CHARS_SOFT_HI,
    CHARS_SOFT_LO,
    CHAT_MAX_LINE_CHARS,
    DIALOGUE_ROUNDS_HARD_MAX,
    DIALOGUE_ROUNDS_SOFT_HI,
    DIALOGUE_ROUNDS_SOFT_LO,
    _FIX_SYSTEM,
    _FIX_USER,
    _M8_J_MID_REWRITE_SYSTEM,
    _M8_J_MID_REWRITE_USER,
    _SHORTEN_SYSTEM,
    _SHORTEN_USER,
    _SYSTEM,
    _USER,
    format_beat_sequence_block,
    format_align_block,
    format_align_issues_block,
    format_m5_h_expand_beat_block,
    format_authority_punchline_expand_block,
    format_scenario_rules_block,
    format_expand_regen_feedback,
    format_role_binding_block,
    format_seed_span_block,
    format_structure_score_feedback,
)
from app.services.gold_story.gold_chat.type_bridge import (
    is_m8_j_domination,
)
from app.services.gold_story.gold_chat.validate import (
    collect_align_issues,
    is_structural_align_kind,
    expand_align_score,
    repair_m5_h_conflict_core,
    repair_m5_h_scene_contract,
    should_reexpand,
    split_align_issues,
    validate_chat_hard,
    validate_contract_role_consistency,
)
from app.services.gold_story.collect.llm import resolve_gold_chat_snippet
from app.services.gold_story.scene import (
    format_scene_block,
    sanitize_banned_literals,
)
from app.services.gold_story.gold_chat.setting import (
    normalize_gold_chat_setting,
    setting_location_violations,
)
from app.services.gold_story.types import structure_type_label
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_KEY_CHARS_MAX,
    DAILY_STORY_KEY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.llm.llm_mgr import llm_mgr
from app.services.gold_story.gold_chat.polish import (
    _apply_gold_chat_polish_fixes,
    collect_gold_chat_polish_issues,
)

logger = logging.getLogger(__name__)

_FATHER_SPEAKER_ALIASES = frozenset(
    {"爸爸", "父亲", "爸", "老爸", "宝爸", "爸爸角色", "父亲角色"}
)

_KID_RIVAL_ALIASES = frozenset(
    {"小男孩", "小女孩", "对方", "对方小朋友", "陌生小孩", "小朋友", "对方孩子"}
)

_THIRD_PARTY_PARENT_ALIASES = frozenset({"对方家长", "对方妈妈", "对方爸爸"})

def _resolve_closing_intent(
    payload: dict[str, Any],
    scene_contract: dict[str, Any],
    *,
    structure_type: str = "",
) -> str:
    """读取 closing；I 对齐 seed 赢家；K 纠偏 H 式和好/缺僵持。"""
    closing = str(
        payload.get("closing_intent") or scene_contract.get("closing_intent") or ""
    )
    st = str(structure_type or "").strip().upper()
    if st == "K":
        from app.services.daily_story.story_types.k.validate import (
            repair_closing_intent_for_k,
        )

        return repair_closing_intent_for_k(closing)
    if st != "I":
        return closing
    from app.services.daily_story.story_types.i.validate import (
        repair_closing_intent_from_seed_win,
    )

    seed = payload.get("dialogue_seed")
    if not isinstance(seed, list):
        seed = scene_contract.get("dialogue_seed")
    return repair_closing_intent_from_seed_win(closing, seed)

def _apply_i_close_local_patches(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    dialogue_seed: list[Any] | None = None,
) -> dict[str, Any]:
    """I：精修前本地收束裁尾；裁短则抛错打回扩写加长争锋。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_gold_chat_post_close_tail,
        patch_m5_break_sibling_consecutive,
    )
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    data, _ = apply_gold_chat_type_patch(dict(story), structure_type="I")
    data, _ = patch_m5_break_sibling_consecutive(data)
    payload: dict[str, Any] = {}
    if isinstance(dialogue_seed, list):
        payload["dialogue_seed"] = dialogue_seed
    data, _ = patch_gold_chat_post_close_tail(
        data,
        payload=payload,
        structure_type="I",
        mechanism=mechanism,
    )
    data, _ = _ensure_gold_chat_min_chars(data)
    n = len(
        [
            x
            for x in (data.get("dialogue") or [])
            if isinstance(x, dict) and str(x.get("line") or "").strip()
        ]
    )
    chars = dialogue_total_chars(data)
    if n < CHAT_LINE_COUNT_MIN or chars < DAILY_STORY_BODY_CHARS_MIN:
        # 打回扩写：服软过早、争锋不够
        raise ValueError(
            f"align_refine_failed:I篇幅前置(句{n}/字{chars}，"
            f"须≥{CHAT_LINE_COUNT_MIN}句且≥{DAILY_STORY_BODY_CHARS_MIN}字；"
            "请在灵魂拷问前加长争锋，服软后立即停)"
        )
    return data

def _repair_i_row_contract(row: dict[str, Any]) -> dict[str, Any]:
    """I：closing/conflict 与 seed 赢家对齐（不写回 DB，仅本轮生成口径）。"""
    st = str(row.get("structure_type") or "").strip().upper()
    if st != "I":
        return row
    payload = cast(dict[str, Any], row.get("payload") or {})
    sc = cast(dict[str, Any], payload.get("scene_contract")) if isinstance(
        payload.get("scene_contract"), dict
    ) else {}
    seed = payload.get("dialogue_seed")
    if not isinstance(seed, list):
        seed = sc.get("dialogue_seed") if isinstance(sc, dict) else None
    from app.services.daily_story.story_types.i.validate import (
        repair_closing_intent_from_seed_win,
        repair_conflict_core_from_seed_win,
    )

    closing = repair_closing_intent_from_seed_win(
        str(payload.get("closing_intent") or sc.get("closing_intent") or ""),
        seed,
    )
    conflict = repair_conflict_core_from_seed_win(
        str(row.get("conflict_core") or ""),
        seed,
    )
    out = dict(row)
    out["conflict_core"] = conflict
    new_payload = dict(payload)
    new_payload["closing_intent"] = closing
    if isinstance(sc, dict):
        new_sc = dict(sc)
        new_sc["closing_intent"] = closing
        if conflict and str(sc.get("conflict") or "").strip():
            # scene conflict 若也写错赢家，一并纠偏
            new_sc["conflict"] = repair_conflict_core_from_seed_win(
                str(sc.get("conflict") or ""),
                seed,
            )
        new_payload["scene_contract"] = new_sc
    out["payload"] = new_payload
    return out

def _resolve_structure_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    from app.services.gold_story.gold_chat.type_bridge import (
        resolve_gold_chat_structure_row,
    )

    return resolve_gold_chat_structure_row(row)

def _persist_structure_correction(row: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """structure 纠偏后回写 DB（仅 gold_chat 入口触发）。"""
    if not notes:
        return row
    gid = int(row.get("id") or 0)
    if gid <= 0:
        return row
    mech = str(row.get("mechanism") or "").strip().upper()
    st = str(row.get("structure_type") or "").strip().upper()
    if not mech or not st:
        return row
    try:
        repo_gold_story.update_mechanism_and_structure(
            gid,
            mechanism=mech,
            structure_type=st,
        )
    except ValueError as exc:
        logger.warning("[GOLD_CHAT] structure persist skipped id=%s: %s", gid, exc)
        return row
    payload = cast(dict[str, Any], row.get("payload") or {})
    patch: dict[str, Any] = {}
    note = str(payload.get("structure_mapping_note") or "").strip()
    if note:
        patch["structure_mapping_note"] = note
    sc = payload.get("scene_contract")
    if isinstance(sc, dict):
        patch["scene_contract"] = sc
    if "closing_mode" in payload:
        patch["closing_mode"] = payload.get("closing_mode")
    if patch:
        repo_gold_story.patch_story_payload(gid, patch)
    # demote 置信写回 payload
    conf = payload.get("structure_confidence")
    if conf is not None and "demote:forced-m14p-not-prank" in "；".join(notes):
        repo_gold_story.patch_story_payload(
            gid, {"structure_confidence": float(conf)}
        )
    logger.info(
        "[GOLD_CHAT] structure auto_correct id=%s notes=%s",
        gid,
        "；".join(notes),
    )
    return repo_gold_story.get_story(gid) or row

EXPAND_CANDIDATE_COUNT = 2

EXPAND_REGENERATE_MAX = 5

EXPAND_SHORT_REGENERATE_MAX = 3

EXPAND_SHORT_LINE_DEFICIT_MAX = 3

EXPAND_NEAR_MISS_CHAR_DEFICIT_MAX = 20

EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN = 60

EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN_M8J = 40

EXPAND_NEAR_MISS_FIX_MAX_ROUNDS = 2

GOLD_CHAT_LLM_MAX_TOKENS = 2048

CLOSING_PROMPT_MAX_CHARS = 28

def _client():
    return llm_mgr._get_client()

def _is_truncation_error(msg: str) -> bool:
    err = str(msg or "")
    return "finish_reason=length" in err or "truncated" in err

def _chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """gold_chat 专用：紧预算；length 立刻失败，勿走全局 JSON 重试再烧一轮。"""
    from app.services.llm.llm_deepseek import _loads_llm_json

    budget = int(max_tokens or GOLD_CHAT_LLM_MAX_TOKENS)
    logger.debug(
        "[GOLD_CHAT] llm_chat start temp=%.2f max_tokens=%s user_chars=%s",
        float(temperature),
        budget,
        len(user or ""),
    )
    content, finish = _client()._chat(  # type: ignore[attr-defined]
        system,
        user,
        thinking_enabled=False,
        temperature=float(temperature),
        max_tokens=budget,
    )
    logger.debug(
        "[GOLD_CHAT] llm_chat done finish=%s out_chars=%s",
        finish,
        len(str(content or "")),
    )
    if not str(content or "").strip():
        raise ValueError("LLM returned empty response")
    if finish == "length":
        raise ValueError(
            "LLM output truncated (finish_reason=length)；"
            "对白 JSON 须短小，禁止超长/循环输出"
        )
    raw = _loads_llm_json(content)
    if not isinstance(raw, dict):
        raise ValueError("LLM JSON must be object")
    return raw

def _prompt_budget_kwargs() -> dict[str, Any]:
    return {
        "chars_min": DAILY_STORY_BODY_CHARS_MIN,
        "chars_max": DAILY_STORY_BODY_CHARS_MAX,
        "chars_soft_lo": CHARS_SOFT_LO,
        "chars_soft_hi": CHARS_SOFT_HI,
        "rounds_soft_lo": DIALOGUE_ROUNDS_SOFT_LO,
        "rounds_soft_hi": DIALOGUE_ROUNDS_SOFT_HI,
        "rounds_hard_max": DIALOGUE_ROUNDS_HARD_MAX,
        "key_min": DAILY_STORY_KEY_CHARS_MIN,
        "key_max": DAILY_STORY_KEY_CHARS_MAX,
        "max_line": CHAT_MAX_LINE_CHARS,
    }

def _closing_for_prompt(closing: str) -> str:
    """长 closing 压成要点，避免模型把说明整段写进对白。"""
    s = str(closing or "").strip()
    if len(s) <= CLOSING_PROMPT_MAX_CHARS:
        return s
    for sep in ("：", ":", "；", ";", "。"):
        if sep in s:
            head = s.split(sep, 1)[0].strip()
            if 4 <= len(head) <= CLOSING_PROMPT_MAX_CHARS:
                return f"{head}（按 beat 收束，勿照抄说明）"
    return s[:CLOSING_PROMPT_MAX_CHARS].rstrip("，。；、 ") + "…"

def _normalize_chat_speakers(story: dict[str, Any]) -> dict[str, Any]:
    """站外父亲别名 → 爸爸；第三方家长 → 妈妈；陌生小孩 → 灿灿。"""
    out = dict(story)
    dialogue: list[dict[str, Any]] = []
    for item in story.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        if sp in _FATHER_SPEAKER_ALIASES:
            row["speaker"] = "爸爸"
        elif sp in _THIRD_PARTY_PARENT_ALIASES:
            row["speaker"] = "妈妈"
        elif sp in _KID_RIVAL_ALIASES:
            row["speaker"] = "灿灿"
        dialogue.append(row)
    out["dialogue"] = dialogue
    out, _ = patch_remap_sibling_terms(out)
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
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        **_prompt_budget_kwargs(),
    )
    return _chat_json(_FIX_SYSTEM, user, temperature=0.55)

def _split_m8_j_head_mid_tail(
    dialogue: list[Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    """M8+J 中段重写：保留首尾，中段可替换。"""
    lose_idx = _j_lose_line_index(dialogue)
    n = len(dialogue)
    if n < 4:
        head_n = max(1, n // 3)
        tail_n = max(1, n - head_n - 1)
        return dialogue[:head_n], dialogue[head_n:n - tail_n], dialogue[n - tail_n:]
    if lose_idx < 0:
        head_n = min(3, max(2, n // 4))
        tail_n = min(3, max(2, n // 5))
        return dialogue[:head_n], dialogue[head_n:n - tail_n], dialogue[n - tail_n:]
    head_n = min(3, max(2, lose_idx // 2))
    head = dialogue[:head_n]
    tail = dialogue[lose_idx:]
    mid = dialogue[head_n:lose_idx]
    if not mid and head_n < lose_idx:
        mid = dialogue[head_n:lose_idx]
    return head, mid, tail

def _rewrite_m8_j_mid_section_with_llm(
    story: dict[str, Any],
    *,
    banned_literals: list[str],
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    """大缺口：保留首尾，只让 LLM 重写中段立规→应战→一锤。"""
    dialogue = story.get("dialogue") or []
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story
    head, mid, tail = _split_m8_j_head_mid_tail(dialogue)
    user = _M8_J_MID_REWRITE_USER.format(
        head_json=json.dumps(head, ensure_ascii=False),
        mid_json=json.dumps(mid, ensure_ascii=False),
        tail_json=json.dumps(tail, ensure_ascii=False),
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        **_prompt_budget_kwargs(),
    )
    out = _normalize_chat_speakers(
        _chat_json(_M8_J_MID_REWRITE_SYSTEM, user, temperature=0.55)
    )
    new_dialogue = out.get("dialogue") or []
    if not isinstance(new_dialogue, list) or len(new_dialogue) < len(head) + len(tail):
        return story
    merged = dict(story)
    merged["dialogue"] = new_dialogue
    return merged

def _shorten_overlong_lines_with_llm(
    story: dict[str, Any],
    *,
    max_chars: int = CHAT_MAX_LINE_CHARS,
) -> dict[str, Any]:
    indices = _overlong_line_indices(story, max_chars)
    if not indices:
        return story
    rows = story.get("dialogue") or []
    long_desc = []
    for no in indices:
        row = rows[no - 1]
        long_desc.append(
            f"- 第{no}句（{row.get('speaker')}）：{row.get('line')}（{len(str(row.get('line') or ''))}字）"
        )
    user = _SHORTEN_USER.format(
        max_chars=max_chars,
        long_lines="\n".join(long_desc),
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
    )
    return _normalize_chat_speakers(_chat_json(_SHORTEN_SYSTEM, user))

def _setting_normalize_kwargs_from_row(
    row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    payload = cast(dict[str, Any], row.get("payload") or {})
    sc_raw = payload.get("scene_contract")
    sc = sc_raw if isinstance(sc_raw, dict) else {}
    raw_chars = sc.get("characters")
    characters = tuple(
        str(c).strip()
        for c in (raw_chars if isinstance(raw_chars, list) else [])
        if str(c).strip()
    )
    if len(characters) < 2:
        characters = ("灿灿", "昭昭")
    activity_context = " ".join(
        x
        for x in (
            str(sc.get("object") or ""),
            str(sc.get("conflict") or ""),
            str(row.get("conflict_core") or ""),
        )
        if x
    )
    return {
        "scene_contract_location": str(sc.get("location") or ""),
        "activity_context": activity_context,
        "characters": characters,
    }

def _apply_expand_setting_normalize(
    chat: dict[str, Any],
    *,
    row: dict[str, Any] | None = None,
    scene_contract_location: str = "",
    activity_context: str = "",
    characters: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """扩写/精修 校验前：站外 setting → 允许地点表内锚点。"""
    out = dict(chat)
    kw = _setting_normalize_kwargs_from_row(row) if row else {}
    loc = str(scene_contract_location or kw.get("scene_contract_location") or "")
    ctx = str(activity_context or kw.get("activity_context") or "")
    chars = characters or kw.get("characters") or ("灿灿", "昭昭")
    new_setting, _notes = normalize_gold_chat_setting(
        str(out.get("setting") or ""),
        scene_contract_location=loc,
        activity_context=ctx,
        characters=chars,
    )
    out["setting"] = new_setting
    return out

def _prepare_chat_for_validate(
    data: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    conflict_text: str = "",
    banned_literals: list[str] | None = None,
    mom_lines_max: int = 1,
    row: dict[str, Any] | None = None,
    scene_contract_location: str = "",
    activity_context: str = "",
) -> dict[str, Any]:
    """M5+H 本地补丁 → setting 归类 → 补字数 → hard 校验。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if mech == "M5" and st == "H":
        data, _ = apply_m5_h_local_patches(
            data,
            closing_intent=closing_intent,
            conflict_text=conflict_text,
        )
    ctx = activity_context or conflict_text
    data = _apply_expand_setting_normalize(
        data,
        row=row,
        scene_contract_location=scene_contract_location,
        activity_context=ctx,
    )
    from app.services.gold_story.scene import (
        patch_dialogue_narration_to_speech,
    )

    patch_dialogue_narration_to_speech(data)
    if st == "K":
        from app.services.daily_story.story_types import apply_gold_chat_type_patch

        data, _ = apply_gold_chat_type_patch(data, structure_type="K")
    data = _apply_gold_chat_local_hard_repairs(
        data,
        structure_type=st,
        mom_lines_max=mom_lines_max,
    )
    data, _ = _ensure_gold_chat_min_chars(
        data,
        mechanism=mech,
        structure_type=st,
    )
    if st == "K" and dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
        data, _ = _gold_chat_force_min_chars(data)
        data, _ = _ensure_gold_chat_min_chars(
            data,
            mechanism=mech,
            structure_type=st,
        )
    from app.services.gold_story.gold_chat.convert import validate_gold_chat

    validate_gold_chat(
        data,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )
    return data

def _validate_expand_chat(
    story: dict[str, Any],
    *,
    banned_literals: list[str],
    source_type: str,
    mom_lines_max: int,
    structure_type: str = "",
    mechanism: str = "",
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """扩写 硬校验 + 格式 fix，直至通过或耗尽 retry。"""
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or data.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    if st:
        data["story_type"] = st
    last_err = ""
    shorten_llm_used = False
    short_expand_rounds = 0
    for attempt in range(5):
        data = _apply_expand_setting_normalize(data, row=row)
        from app.services.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        patch_dialogue_narration_to_speech(data)
        # validate_gold_chat 仍住在 convert，避免循环导入
        from app.services.gold_story.gold_chat.convert import (
            validate_gold_chat,
        )

        if st == "K":
            from app.services.daily_story.story_types import apply_gold_chat_type_patch

            data, _ = apply_gold_chat_type_patch(data, structure_type="K")
        data = _apply_gold_chat_local_hard_repairs(
            data,
            structure_type=st,
            mom_lines_max=mom_lines_max,
        )
        data, _ = _ensure_gold_chat_min_chars(
            data,
            mechanism=mech,
            structure_type=st,
        )
        if st == "K" and dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
            data, _ = _gold_chat_force_min_chars(data)
            data, _ = _ensure_gold_chat_min_chars(
                data,
                mechanism=mech,
                structure_type=st,
            )
        try:
            validate_gold_chat(
                data,
                banned_literals=banned_literals,
                source_type=source_type,
                mom_lines_max=mom_lines_max,
            )
            return data
        except ValueError as exc:
            last_err = str(exc)
            if attempt >= 4:
                raise ValueError(last_err) from exc
            # 缺字段/妈句：本地补丁 + 通用 FIX，勿只走短篇幅扩写
            if _has_non_short_hard_errors(last_err):
                data = _apply_gold_chat_local_hard_repairs(
                    data,
                    structure_type=st,
                    mom_lines_max=mom_lines_max,
                )
                data = _fix_chat_with_llm(
                    data,
                    last_err,
                    banned_literals=banned_literals,
                    mom_lines_max=mom_lines_max,
                )
                data = _normalize_chat_speakers(data)
                if st:
                    data["story_type"] = st
                data = _apply_gold_chat_local_hard_repairs(
                    data,
                    structure_type=st,
                    mom_lines_max=mom_lines_max,
                )
                continue
            # 偏短：near_miss 轻量 FIX；大缺口 M8+J 中段重写；仍不足交外层扩写重生成
            if _is_short_content_error(last_err):
                from app.services.gold_story.gold_chat.type_bridge import (
                    is_m8_j_domination,
                )

                m8_j = is_m8_j_domination(mechanism=mech, structure_type=st)
                large_gap = m8_j and _is_large_gap_short_error(
                    last_err, mechanism=mech, structure_type=st
                )
                near_miss = _is_near_miss_short_error(last_err)
                max_fix = (
                    EXPAND_NEAR_MISS_FIX_MAX_ROUNDS
                    if near_miss
                    else (2 if large_gap else 3)
                )
                if large_gap and short_expand_rounds == 0:
                    logger.debug(
                        "[GOLD_CHAT] expand M8+J mid rewrite err=%s",
                        last_err[:120],
                    )
                    data = _rewrite_m8_j_mid_section_with_llm(
                        data,
                        banned_literals=banned_literals,
                        mom_lines_max=mom_lines_max,
                    )
                    data = _normalize_chat_speakers(data)
                    if st:
                        data["story_type"] = st
                    data, _ = _ensure_gold_chat_min_chars(
                        data,
                        mechanism=mech,
                        structure_type=st,
                    )
                    short_expand_rounds += 1
                    continue
                if short_expand_rounds < max_fix:
                    deficit = _char_deficit_from_error(last_err) or 0
                    expand_err = last_err
                    extras: list[str] = []
                    if "句数" in last_err or "对白句数" in last_err:
                        if m8_j:
                            extras.append(
                                "中段插入互顶/立规/应战各 1–2 句，补到≥12句；"
                                "禁灌「你给我听好了/这回算清楚」尾巴"
                            )
                        else:
                            extras.append(
                                "中段插入哀求/加码+否决来回，补到≥12句；"
                                "禁灌「你给我听好了/这回算清楚」尾巴"
                            )
                    if deficit > 0:
                        if near_miss:
                            extras.append(
                                f"near_miss 差{deficit}字：只扩 1 个现有短句"
                                f"（动作/神态），不新增 beat、不尾部灌水"
                            )
                        else:
                            extras.append(
                                f"句内用 beat 实词扩写还差{deficit}字，"
                                f"偏短句加到约18–{CHAT_MAX_LINE_CHARS}字；"
                                "禁止只加语气词、禁止删句、"
                                "禁止「你给我听好了/这回算清楚/别再装傻」"
                            )
                    else:
                        extras.append(
                            "句内用 beat 实词写满；"
                            "禁止「你给我听好了/这回算清楚/别再装傻」灌尾"
                        )
                    if extras:
                        expand_err = f"{last_err}；" + "；".join(extras)
                    logger.debug(
                        "[GOLD_CHAT] expand FIX short round=%s err=%s",
                        short_expand_rounds + 1,
                        last_err[:120],
                    )
                    data = _fix_chat_with_llm(
                        data,
                        expand_err,
                        banned_literals=banned_literals,
                        mom_lines_max=mom_lines_max,
                    )
                    data = _normalize_chat_speakers(data)
                    if st:
                        data["story_type"] = st
                    data, _ = _ensure_gold_chat_min_chars(
                        data,
                        mechanism=mech,
                        structure_type=st,
                    )
                    short_expand_rounds += 1
                    continue
                raise ValueError(last_err) from exc
            if "单句过长" in last_err:
                trimmed, changed = _apply_deterministic_shorten(data)
                if changed:
                    data = _normalize_chat_speakers(trimmed)
                    continue
                if not shorten_llm_used:
                    data = _shorten_overlong_lines_with_llm(data)
                    data = _normalize_chat_speakers(data)
                    shorten_llm_used = True
                    continue
            data = _fix_chat_with_llm(
                data,
                last_err,
                banned_literals=banned_literals,
                mom_lines_max=mom_lines_max,
            )
            data = _normalize_chat_speakers(data)
            if st:
                data["story_type"] = st
    raise ValueError(last_err or "gold_chat validate failed")

def _generate_expand_candidate(
    user: str,
    *,
    banned_literals: list[str],
    source_type: str,
    mom_lines_max: int,
    structure_type: str = "",
    mechanism: str = "",
    temperature: float = 0.4,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = _normalize_chat_speakers(
        _chat_json(_SYSTEM, user, temperature=temperature)
    )
    if structure_type:
        data["story_type"] = str(structure_type).strip().upper()
    return _validate_expand_chat(
        data,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
        structure_type=structure_type,
        mechanism=mechanism,
        row=row,
    )

def _pick_expand_candidate(
    candidates: list[dict[str, Any]],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str,
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    dialogue_seed: list[Any] | None = None,
    beat: list[Any] | None = None,
    object_text: str = "",
    mechanism_text: str = "",
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("no expand candidates")
    if len(candidates) == 1:
        return candidates[0]

    def _score(d: dict[str, Any]) -> tuple[int, int]:
        scored = d
        mech = str(mechanism or "").strip().upper()
        st = str(structure_type or "").strip().upper()
        if mech == "M5" and st == "H":
            scored, _ = apply_m5_h_local_patches(
                d,
                closing_intent=closing_intent,
                conflict_text=conflict_text,
            )
        return expand_align_score(
            scored,
            structure_type=structure_type,
            mechanism=mechanism,
            closing_intent=closing_intent,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
            dialogue_seed=dialogue_seed,
            beat=beat,
            object_text=object_text,
            mechanism_text=mechanism_text,
        )

    zero_struct = [c for c in candidates if _score(c)[0] == 0]
    pool = zero_struct if zero_struct else candidates
    return min(pool, key=_score)

def _format_dialogue_seed(seed: list[Any]) -> str:
    """成句 seed 标成「要点须改写」，降低照抄/一条扩多版。"""
    lines: list[str] = []
    spoken_like = 0
    for item in seed or []:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if not (speaker and intent):
            continue
        if len(intent) >= 8 and any(ch in intent for ch in "？！。!?.…"):
            spoken_like += 1
            lines.append(
                f"- {speaker}｜要点：{intent}"
                "（须改写成口语，勿逐字照抄；本条最多 1–2 句）"
            )
        else:
            lines.append(f"- {speaker}｜intent：{intent}")
    body = "\n".join(lines) or "（无）"
    if spoken_like:
        return (
            "（下列 seed 已接近成句：只取语义改写，禁止一条扩成多版本）\n"
            + body
        )
    return body

def _expand_seed_for_line_floor(
    seed: list[Any] | None,
    *,
    structure_type: str = "",
    mechanism: str = "",
) -> list[Any]:
    """seed 条数 <12 时，在收束前插入抽象加码拍，迫使扩写写满句数。

    只改 prompt 用 seed，不写回 DB；intent 抽象，不按单篇物件造句。
    """
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    from app.services.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    out: list[Any] = [dict(x) if isinstance(x, dict) else x for x in (seed or [])]
    n = sum(
        1
        for x in out
        if isinstance(x, dict) and str(x.get("intent") or x.get("line") or "").strip()
    )
    if n >= CHAT_LINE_COUNT_MIN:
        return out

    st = str(structure_type or "").strip().upper()
    extras: list[dict[str, str]]
    if is_m8_j_domination(mechanism=mechanism, structure_type=st):
        extras = [
            {"speaker": "昭昭", "intent": "不服继续顶撞/扭打升级"},
            {"speaker": "灿灿", "intent": "重申谁赢谁说了算"},
            {"speaker": "昭昭", "intent": "嘴硬应战要对方出招"},
            {"speaker": "灿灿", "intent": "一锤前放狠话或气势铺垫"},
        ]
    elif st == "J":
        extras = [
            {"speaker": "昭昭", "intent": "换个理由再求一次"},
            {"speaker": "灿灿", "intent": "换个说法继续压住"},
            {"speaker": "昭昭", "intent": "再保证一次求放行"},
            {"speaker": "灿灿", "intent": "再否决一次不松口"},
        ]
    else:
        extras = [
            {"speaker": "昭昭", "intent": "换个理由再顶一句"},
            {"speaker": "灿灿", "intent": "换个说法再堵一句"},
            {"speaker": "昭昭", "intent": "加码争一次"},
            {"speaker": "灿灿", "intent": "加码守一次"},
        ]
    insert_at = max(2, len(out) - 2)
    ei = 0
    guard = 0
    while n < CHAT_LINE_COUNT_MIN and guard < 8:
        guard += 1
        extra = dict(extras[ei % len(extras)])
        ei += 1
        out.insert(insert_at, extra)
        insert_at += 1
        n += 1
    return out

def _is_short_content_error(msg: str) -> bool:
    """字数/句数不足。"""
    return (
        "正文总字数须≥" in msg
        or "dialogue 至少" in msg
        or "对白句数须≥" in msg
    )

def _is_near_miss_short_error(msg: str) -> bool:
    """差 ≤20 字或仅少 1 句：轻量 FIX，不动结构。"""
    char_def = _char_deficit_from_error(msg)
    line_def = _line_count_deficit_from_error(msg)
    if char_def is not None and 0 < char_def <= EXPAND_NEAR_MISS_CHAR_DEFICIT_MAX:
        return True
    return line_def is not None and line_def == 1

def _is_large_gap_short_error(
    msg: str,
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> bool:
    """差 ≥60 字或少 ≥3 句：须中段重写，勿同 prompt 空转。
    M8+J 用更激进阈值（≥40 字）早点进入中段重写。"""
    char_def = _char_deficit_from_error(msg)
    line_def = _line_count_deficit_from_error(msg)
    
    # M8+J 专用：缺 ≥40 字立即中段重写
    if is_m8_j_domination(mechanism=mechanism, structure_type=structure_type):
        threshold = EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN_M8J
    else:
        threshold = EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN
    
    if char_def is not None and char_def >= threshold:
        return True
    return line_def is not None and line_def >= 3

def _line_count_deficit_from_error(msg: str) -> int | None:
    m = re.search(r"对白句数须≥(\d+)，当前(\d+)", str(msg or ""))
    if not m:
        return None
    return max(0, int(m.group(1)) - int(m.group(2)))

def _char_deficit_from_error(msg: str) -> int | None:
    m = re.search(r"正文总字数须≥(\d+)，当前(\d+)", str(msg or ""))
    if not m:
        return None
    return max(0, int(m.group(1)) - int(m.group(2)))

def _is_regenerable_line_short_error(msg: str) -> bool:
    """句数差 ≤3（如 9–11/12）可走扩写重生成。"""
    deficit = _line_count_deficit_from_error(msg)
    if deficit is None:
        return False
    return 1 <= deficit <= EXPAND_SHORT_LINE_DEFICIT_MAX

def _is_regenerable_short_error(msg: str) -> bool:
    """句数差 ≤3，或仅字数不足（句数已够/未报句数）→ 可走扩写重生成。

    字数缺口大（如 117/240）也靠 FIX 扩写 + 重抽，勿立刻驳回。
    仅当句数差 >3（如 8/12）才视为不可靠重生成。
    """
    line_def = _line_count_deficit_from_error(msg)
    if line_def is not None and line_def > EXPAND_SHORT_LINE_DEFICIT_MAX:
        return False
    if line_def is not None and line_def >= 1:
        return True
    char_def = _char_deficit_from_error(msg)
    return char_def is not None and char_def > 0

def _has_non_short_hard_errors(msg: str) -> bool:
    """缺字段/妈句等硬错：勿只走短篇幅 FIX。"""
    text = str(msg or "")
    return (
        "缺少字段" in text
        or "punchline_explain" in text
        or "妈妈台词须" in text
        or "爸爸台词须" in text
        or "key 须" in text
    )

def _ensure_gold_chat_punchline_explain(
    story: dict[str, Any],
    *,
    structure_type: str = "",
) -> dict[str, Any]:
    """缺 punchline_explain 时按类型补前缀字段（不改对白）。"""
    out = dict(story)
    st = str(structure_type or out.get("story_type") or "").strip().upper()
    if not st:
        return out
    from app.services.daily_story.story_types import (
        STORY_TYPE_LABELS,
        normalize_punchline_explain,
    )

    if st not in STORY_TYPE_LABELS:
        return out
    raw = str(out.get("punchline_explain") or "").strip()
    if not raw:
        label = STORY_TYPE_LABELS.get(st, st)
        out["punchline_explain"] = f"{st}类{label}"
        return out
    out["punchline_explain"] = normalize_punchline_explain(raw, st)
    return out

def _trim_gold_chat_mom_lines(
    story: dict[str, Any],
    *,
    mom_lines_max: int = 1,
) -> tuple[dict[str, Any], bool]:
    """妈妈句超限：先合并连续妈妈句，再保留末尾相关句至上限。"""
    import copy

    mom_max = max(0, int(mom_lines_max))
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or mom_max <= 0:
        # mom_max=0：删全部妈妈句
        if not isinstance(dialogue, list):
            return story, False
        kept = [
            item
            for item in dialogue
            if not (
                isinstance(item, dict)
                and str(item.get("speaker") or "").strip() == "妈妈"
            )
        ]
        if len(kept) == len(dialogue):
            return story, False
        out["dialogue"] = kept
        return out, True

    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
    )

    changed = False
    # 合并连续妈妈句
    i = 1
    while i < len(dialogue):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        if str(a.get("speaker") or "").strip() != "妈妈":
            i += 1
            continue
        if str(b.get("speaker") or "").strip() != "妈妈":
            i += 1
            continue
        left = str(a.get("line") or "").rstrip("。！？…")
        right = str(b.get("line") or "").strip()
        sep = "，" if left and not left.endswith(("！", "!", "？")) else ""
        merged = f"{left}{sep}{right}"
        if dialogue_char_count(merged) > DAILY_STORY_LINE_CHARS_MAX:
            i += 1
            continue
        a["line"] = merged
        dialogue.pop(i)
        changed = True

    mom_idxs = [
        idx
        for idx, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() == "妈妈"
    ]
    if len(mom_idxs) <= mom_max:
        return (out, changed) if changed else (story, False)

    # 超限：保留最后 mom_max 句妈妈台词（收束常在末段）
    drop = set(mom_idxs[:-mom_max])
    out["dialogue"] = [
        item for idx, item in enumerate(dialogue) if idx not in drop
    ]
    return out, True

def _apply_gold_chat_local_hard_repairs(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    """校验前本地硬修复：补 punchline、裁妈妈句。"""
    data = _ensure_gold_chat_punchline_explain(
        story, structure_type=structure_type
    )
    data, _ = _trim_gold_chat_mom_lines(data, mom_lines_max=mom_lines_max)
    return data

def _short_content_reject_message(detail: str, *, regen_count: int = 0) -> str:
    text = str(detail or "").strip()
    if _has_non_short_hard_errors(text):
        if regen_count > 0:
            head = f"gold_chat校验驳回:重试{regen_count}次仍不达标"
        else:
            head = "gold_chat校验驳回"
    elif regen_count > 0:
        head = f"gold_chat篇幅驳回:重生成{regen_count}次仍不达标"
    else:
        head = "gold_chat篇幅驳回:本地垫字仍不足"
    return f"{head}; {text}" if text else head

def _bump_short_regen_or_reject(msg: str, short_regen_count: int) -> int:
    """句/字 near-miss → 扩写重生成（最多 3 次）；差距更大或次数用尽 → 驳回。"""
    if not _is_short_content_error(msg):
        return short_regen_count
    if not _is_regenerable_short_error(msg):
        raise ValueError(
            _short_content_reject_message(msg, regen_count=short_regen_count)
        )
    next_count = short_regen_count + 1
    if next_count > EXPAND_SHORT_REGENERATE_MAX:
        raise ValueError(
            _short_content_reject_message(msg, regen_count=EXPAND_SHORT_REGENERATE_MAX)
        )
    return next_count

def _structure_type_hint(
    structure_type: str,
    mechanism: str = "",
    closing_mode: str = "",
) -> str:
    from app.services.gold_story.gold_chat.type_bridge import (
        structure_type_hint,
    )

    return structure_type_hint(
        structure_type=structure_type,
        mechanism=mechanism,
        closing_mode=closing_mode,
    )

def _gate_forced_m14_p_or_raise(row: dict[str, Any]) -> None:
    """假 M14+P（亲子成人反将等）禁止硬转对白。"""
    from app.services.gold_story.structure_resolve import (
        p_structure_evidence_blob,
        should_demote_forced_m14_p,
    )

    payload = cast(dict[str, Any], row.get("payload") or {})
    blob = p_structure_evidence_blob(
        story_raw=str(payload.get("story_raw") or ""),
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
        conflict_core=str(row.get("conflict_core") or ""),
        closing_intent=str(payload.get("closing_intent") or ""),
        dialogue_seed=payload.get("dialogue_seed")
        if isinstance(payload.get("dialogue_seed"), list)
        else None,
    )
    if should_demote_forced_m14_p(
        mechanism=str(row.get("mechanism") or ""),
        structure_type=str(row.get("structure_type") or ""),
        blob=blob,
    ):
        raise ValueError(
            "gold_chat结构驳回:forced-m14p-not-prank; "
            "缺道具互整认怂链（亲子成人反将不可硬套 P）"
        )

def gold_story_to_gold_chat(row: dict[str, Any]) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    row = _repair_i_row_contract(row)
    row, _structure_notes = _resolve_structure_row(row)
    _gate_forced_m14_p_or_raise(row)
    payload = cast(dict[str, Any], row.get("payload") or {})
    structure_type = str(row.get("structure_type") or "A").strip().upper()
    st_label = structure_type_label(structure_type)
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    # 优先用契约 conflict（迁龄后），避免旧 conflict_core 把 383 等写回成稿
    conflict_core = str(
        scene_contract.get("conflict") or row.get("conflict_core") or ""
    ).strip()
    # 扩写口径：优先用已 remap/迁龄的 scene conflict，避免站外旧核污染标题与元数据
    sc_conflict = str(scene_contract.get("conflict") or "").strip()
    if sc_conflict:
        conflict_core = sc_conflict
    mechanism = str(row.get("mechanism") or "")
    if mechanism.upper() == "M5" and structure_type == "H":
        repaired_core, core_changed = repair_m5_h_conflict_core(
            conflict_core,
            scene_contract,
        )
        if core_changed:
            conflict_core = repaired_core
        repaired_sc, sc_changed = repair_m5_h_scene_contract(
            scene_contract,
            conflict_core=conflict_core,
        )
        if sc_changed:
            scene_contract = repaired_sc
    seed = payload.get("dialogue_seed") or []
    if isinstance(seed, list):
        from app.services.gold_story.scene import (
            sanitize_dialogue_seed_speech,
        )

        seed = sanitize_dialogue_seed_speech(seed)
    if structure_type == "K" and isinstance(seed, list):
        from app.services.daily_story.story_types import (
            sanitize_gold_chat_dialogue_seed,
        )

        seed = sanitize_gold_chat_dialogue_seed(
            seed, structure_type="K"
        )
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    source_type = str(payload.get("source_type") or scene_contract.get("source_type") or "field")
    story_raw_full = str(row.get("story_raw") or payload.get("story_raw") or "")
    from app.services.gold_story.scene import remap_story_raw_scores_for_prompt

    story_raw_full = remap_story_raw_scores_for_prompt(
        story_raw_full,
        contract=scene_contract,
    )
    mom_max = scene_contract.get("mom_lines_max")
    if mom_max is None:
        mom_max = 1
    beat = payload.get("beat") if isinstance(payload.get("beat"), list) else []
    closing = _resolve_closing_intent(
        payload, scene_contract, structure_type=structure_type
    )[:500]
    beat_chain = scene_contract.get("beat_chain") or []
    if not isinstance(beat_chain, list):
        beat_chain = []
    conflict_text = str(
        scene_contract.get("conflict") or conflict_core or ""
    )
    object_text = str(scene_contract.get("object") or "")
    mechanism_text = str(scene_contract.get("mechanism") or "")
    contract_role_errs = validate_contract_role_consistency(
        scene_contract,
        conflict_core=conflict_core,
    )
    if contract_role_errs:
        raise ValueError(f"contract_role:{'; '.join(contract_role_errs)}")
    role_binding_block = format_role_binding_block(conflict_text)
    beat_sequence_block = format_beat_sequence_block(
        conflict_text=conflict_text,
        beat_chain=beat_chain,
        mechanism=mechanism,
        structure_type=structure_type,
    )
    align_block = format_align_block(
        structure_type=structure_type,
        mechanism=mechanism,
        beat=beat,
        closing_intent=closing,
        story_raw=story_raw_full[:800],
        closing_mode=str(payload.get("closing_mode") or ""),
    )
    m5_h_beat_block = ""
    if mechanism.upper() == "M5" and structure_type == "H":
        m5_h_beat_block = format_m5_h_expand_beat_block(
            conflict_text=conflict_text,
            closing_intent=closing,
        )
    closing_mode_expand = str(payload.get("closing_mode") or "").strip()
    if (
        mechanism.upper() == "M4"
        and structure_type == "G"
        and closing_mode_expand == "authority_punchline"
    ):
        from app.services.gold_story.gold_chat.prompts import (
            format_authority_punchline_expand_block,
        )

        auth_block = format_authority_punchline_expand_block(
            beat_chain=beat_chain,
        )
        m5_h_beat_block = (
            f"{m5_h_beat_block}\n\n{auth_block}".strip()
            if m5_h_beat_block
            else auth_block
        )

    banned_list = [str(x) for x in banned]
    mom_int = int(mom_max)
    last_err = ""
    expand_feedback_block = ""
    expand_temperature = 0.4
    chat: dict[str, Any] = {}
    short_regen_count = 0
    for _regen in range(EXPAND_REGENERATE_MAX):
        logger.debug(
            "[GOLD_CHAT] expand regen=%s/%s temp=%.2f short_regen=%s feedback=%s",
            _regen + 1,
            EXPAND_REGENERATE_MAX,
            expand_temperature,
            short_regen_count,
            "yes" if expand_feedback_block else "no",
        )
        # 截断回灌后压低 story_raw，减少「照着长叙述扩写跑飞」
        story_raw_cap = 400 if expand_temperature < 0.35 else 800
        story_raw = story_raw_full[:story_raw_cap]
        prompt_seed = _expand_seed_for_line_floor(
            seed,
            structure_type=structure_type,
            mechanism=mechanism,
        )
        user = _USER.format(
            title=str(row.get("title") or ""),
            mechanism=mechanism,
            structure_type=structure_type,
            structure_label=st_label,
            conflict_core=conflict_core[:500],
            scene_contract_block=format_scene_block(scene_contract),
            role_binding_block=role_binding_block,
            beat_sequence_block=beat_sequence_block,
            m5_h_beat_block=m5_h_beat_block,
            scenario_rules_block=format_scenario_rules_block(
                mechanism=mechanism,
                structure_type=structure_type,
                conflict_text=conflict_text,
                closing_intent=closing,
                beat_chain=beat_chain,
            ),
            expand_feedback_block=expand_feedback_block,
            dialogue_seed=_format_dialogue_seed(prompt_seed)[:4000],
            seed_span_block=format_seed_span_block(
                prompt_seed,
                structure_type=structure_type,
                mechanism=mechanism,
            ),
            closing_intent=_closing_for_prompt(closing),
            speaker_map_note=str(
                payload.get("speaker_map_note")
                or scene_contract.get("remap_note")
                or ""
            )[:500],
            story_raw=story_raw or "（无）",
            banned_literals="、".join(str(x) for x in banned) or "（无）",
            funny_why=str(payload.get("funny_why") or "")[:500],
            source_type=source_type,
            structure_hint=_structure_type_hint(
                structure_type,
                mechanism,
                str(payload.get("closing_mode") or ""),
            ),
            align_block=align_block,
            gold_chat_snippet=resolve_gold_chat_snippet(str(row.get("source_id") or "")),
            **_prompt_budget_kwargs(),
        )
        candidates: list[dict[str, Any]] = []
        hit_truncation = False
        hit_short = False
        for attempt_no in range(EXPAND_CANDIDATE_COUNT):
            logger.debug(
                "[GOLD_CHAT] expand candidate %s/%s …",
                attempt_no + 1,
                EXPAND_CANDIDATE_COUNT,
            )
            try:
                candidates.append(
                    _generate_expand_candidate(
                        user,
                        banned_literals=banned_list,
                        source_type=source_type,
                        mom_lines_max=mom_int,
                        structure_type=structure_type,
                        mechanism=mechanism,
                        temperature=expand_temperature,
                        row=row,
                    )
                )
            except ValueError as exc:
                last_err = str(exc)
                logger.debug(
                    "[GOLD_CHAT] expand candidate fail: %s",
                    last_err[:160],
                )
                # 同提示连打截断/短稿只会烧额度；立刻换反馈重抽
                if _is_truncation_error(last_err):
                    hit_truncation = True
                    break
                if _is_short_content_error(last_err) and not candidates:
                    hit_short = True
                    break
        if not candidates:
            if last_err:
                if hit_short or _is_short_content_error(last_err):
                    short_regen_count = _bump_short_regen_or_reject(
                        last_err, short_regen_count
                    )
                    expand_temperature = max(expand_temperature, 0.55)
                expand_feedback_block = format_expand_regen_feedback(
                    last_err,
                    None,
                    structure_type=structure_type,
                    mechanism=mechanism,
                    closing_intent=closing,
                    beat_chain=beat_chain,
                    conflict_text=conflict_text,
                    short_regen_count=short_regen_count,
                )
                if hit_truncation or _is_truncation_error(last_err):
                    expand_temperature = 0.25
            continue
        data = _pick_expand_candidate(
            candidates,
            structure_type=structure_type,
            mechanism=mechanism,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
            dialogue_seed=seed,
            beat=beat,
            object_text=object_text,
            mechanism_text=mechanism_text,
        )
        # 类型本地补丁先于精修（align），避免 C 回旋镖等只能靠 LLM 精修
        from app.services.daily_story.story_types import (
            apply_gold_chat_body_pipeline,
        )

        data["gold_beat_chain"] = beat_chain
        data, type_notes = apply_gold_chat_body_pipeline(
            data, structure_type=structure_type
        )
        from app.services.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        narration_notes = patch_dialogue_narration_to_speech(data)
        if narration_notes:
            type_notes = list(type_notes) + narration_notes
        data, alt_changed = patch_c_force_sibling_alternate(data)
        if alt_changed:
            type_notes = list(type_notes) + ["C全篇交替"]
        data, crit_changed = patch_c_possession_criterion(data)
        if crit_changed:
            type_notes = list(type_notes) + ["C判据→占有系"]
        from app.services.gold_story.gold_chat.convert import (
            _attach_gold_chat_structure_score,
            _gate_gold_chat_structure_score,
            _gold_chat_j_pre_score_polish,
            _post_align_j_closing_touchup,
            _realign_j_role_speakers,
            patch_break_consecutive_keep_seed,
            patch_collapse_empty_sibling_repeats,
            patch_score_propaganda_speakers,
            patch_seed_speaker_align,
        )

        data, seed_changed = patch_seed_speaker_align(data, dialogue_seed=seed)
        if seed_changed:
            type_notes = list(type_notes) + ["seed角色归位"]
        data, prop_changed = patch_score_propaganda_speakers(
            data, conflict_text=conflict_text
        )
        if prop_changed:
            type_notes = list(type_notes) + ["宣传受害归位"]
        data, empty_changed = patch_collapse_empty_sibling_repeats(data)
        if empty_changed:
            type_notes = list(type_notes) + ["空转复读改写"]
        data, _ = patch_sanitize_c_tone_stack(data)
        data, _ = patch_sanitize_pad_suffix(data)
        data, _ = _ensure_gold_chat_min_chars(
            data,
            mechanism=mechanism,
            structure_type=structure_type,
        )
        # 连说/垫字后再：先宣传分工，再 seed 短语（seed 最后赢，避免结构卡死）
        data, prop_changed2 = patch_score_propaganda_speakers(
            data, conflict_text=conflict_text
        )
        if prop_changed2:
            type_notes = list(type_notes) + ["宣传受害再归位"]
        data, seed_changed2 = patch_seed_speaker_align(data, dialogue_seed=seed)
        if seed_changed2:
            type_notes = list(type_notes) + ["seed角色再归位"]
        # 垫字达标后可能又灌尾：I 类再封一次语塞后收束
        if str(structure_type or "").upper() == "I":
            from app.services.daily_story.story_types import apply_gold_chat_type_patch

            data, i_notes = apply_gold_chat_type_patch(
                data, structure_type="I"
            )
            if i_notes:
                type_notes = list(type_notes) + list(i_notes)[:3]
            data, _ = patch_sanitize_pad_suffix(data)
        if str(structure_type or "").upper() == "Q":
            data, q_notes = apply_gold_chat_body_pipeline(
                data, structure_type="Q"
            )
            if q_notes:
                type_notes = list(type_notes) + list(q_notes)[:4]
            data, _ = _ensure_gold_chat_min_chars(
                data,
                mechanism=mechanism,
                structure_type=structure_type,
            )
        if str(structure_type or "").upper() == "J":
            data, br_changed = patch_break_consecutive_keep_seed(
                data, dialogue_seed=seed
            )
            if br_changed:
                type_notes = list(type_notes) + ["连说保seed打散"]
                data, _ = patch_seed_speaker_align(data, dialogue_seed=seed)
        if type_notes:
            logger.info(
                "gold_chat pre-align type patch: %s",
                "；".join(str(n) for n in type_notes[:6]),
            )
        # 旁路收束模式随稿走入 align/G 硬卡（不改 structure_type）
        closing_mode = str(payload.get("closing_mode") or "").strip()
        if closing_mode:
            data = dict(data)
            data["closing_mode"] = closing_mode
        if closing_mode == "authority_punchline":
            from app.services.gold_story.gold_chat.patch import (
                apply_authority_punchline_local_patches,
            )

            data, auth_patched = apply_authority_punchline_local_patches(
                data,
                beat_chain=beat_chain,
                dialogue_seed=seed,
            )
            if auth_patched:
                type_notes = list(type_notes) + ["权威开场兜底"]
                logger.info("gold_chat pre-align authority opening patch")
        chat = data
        try:
            from app.services.gold_story.gold_chat.refine import (
                refine_gold_chat_align,
                REFINE_MAX_ROUNDS,
            )
            chat = refine_gold_chat_align(
                data,
                structure_type=structure_type,
                mechanism=mechanism,
                align_block=align_block,
                banned_literals=banned_list,
                mom_lines_max=mom_int,
                closing_intent=closing,
                beat_chain=beat_chain,
                conflict_text=conflict_text,
                dialogue_seed=seed,
                beat=beat,
                object_text=object_text,
                mechanism_text=mechanism_text,
                max_rounds=REFINE_MAX_ROUNDS,
                bail_on_structural=True,
                row=row,
            )
            # align 精修可能又写回弱判据/连说；收口再垫一次
            chat, _ = patch_c_force_sibling_alternate(chat)
            chat, _ = patch_c_possession_criterion(chat)
            chat, _ = patch_sanitize_c_tone_stack(chat)
            chat, _ = patch_sanitize_pad_suffix(chat)
            chat, _ = _ensure_gold_chat_min_chars(chat)
            chat, _ = patch_seed_speaker_align(chat, dialogue_seed=seed)
            if str(structure_type or "").upper() == "J":
                chat, _ = patch_j_plea_veto_speakers(chat)
                chat, _ = patch_break_consecutive_keep_seed(chat, dialogue_seed=seed)
                chat, _ = patch_seed_speaker_align(chat, dialogue_seed=seed)
                chat, _ = patch_j_plea_veto_speakers(chat)
            # align 可能写回昭昭「哼」软收末句；只跑 J 末句镇住，勿全量 type pipeline
            chat, post_notes = _post_align_j_closing_touchup(
                chat, structure_type=structure_type
            )
            if post_notes:
                logger.info(
                    "gold_chat post-align J touchup: %s",
                    "；".join(str(n) for n in post_notes[:4]),
                )
            chat = _realign_j_role_speakers(
                chat,
                dialogue_seed=seed,
                structure_type=structure_type,
            )
            if conflict_core:
                chat["conflict_core"] = conflict_core
            # 结构分门控前先跑 M2+C 机械 normalize（缺层只记 note，不编句）
            from app.services.gold_story.gold_chat.patch import (
                patch_m2_c_structure,
            )

            chat, m2_notes = patch_m2_c_structure(
                chat,
                structure_type=structure_type,
                mechanism=mechanism,
                theme=str(row.get("title") or chat.get("scene_title") or ""),
                payload=payload,
            )
            if m2_notes:
                logger.info(
                    "gold_chat pre-score M2+C: %s",
                    "；".join(str(n) for n in m2_notes[:4]),
                )
            gaps = [str(n) for n in m2_notes if "缺" in str(n)]
            if str(structure_type or "").upper() == "J":
                chat = _gold_chat_j_pre_score_polish(
                    chat,
                    dialogue_seed=seed,
                    mechanism=mechanism,
                )
            chat = _attach_gold_chat_structure_score(chat, row)
            try:
                _gate_gold_chat_structure_score(chat)
            except ValueError as score_exc:
                last_err = str(score_exc)
                # 已过 align 的稿：先定点抬结构，避免整开扩写空转
                try:
                    fb = format_structure_score_feedback(last_err, chat)
                    if gaps:
                        fb = fb + "\n" + "\n".join(
                            f"- {g}：请在对白中补全，勿另起无关剧情" for g in gaps[:3]
                        )
                    lifted = _fix_chat_with_llm(
                        chat,
                        fb or last_err,
                        banned_literals=banned_list,
                        mom_lines_max=mom_int,
                    )
                    lifted = _normalize_chat_speakers(lifted)
                    if structure_type:
                        lifted["story_type"] = structure_type
                    lifted, _ = patch_c_force_sibling_alternate(lifted)
                    lifted, _ = patch_c_possession_criterion(lifted)
                    lifted, _ = patch_sanitize_c_tone_stack(lifted)
                    lifted, _ = patch_sanitize_pad_suffix(lifted)
                    lifted, _ = _ensure_gold_chat_min_chars(lifted)
                    lifted, _ = patch_m2_c_structure(
                        lifted,
                        structure_type=structure_type,
                        mechanism=mechanism,
                        theme=str(row.get("title") or lifted.get("scene_title") or ""),
                        payload=payload,
                    )
                    lifted, _ = _post_align_j_closing_touchup(
                        lifted, structure_type=structure_type
                    )
                    if conflict_core:
                        lifted["conflict_core"] = conflict_core
                    lifted = _attach_gold_chat_structure_score(lifted, row)
                    _gate_gold_chat_structure_score(lifted)
                    return lifted
                except ValueError:
                    pass
                quality = cast(dict[str, Any], chat.get("quality")) if isinstance(
                    chat.get("quality"), dict
                ) else {}
                reasons = [str(r) for r in (quality.get("reasons") or [])]
                cons = [
                    r
                    for r in reasons
                    if any(
                        p in r
                        for p in (
                            "缺",
                            "未",
                            "拖",
                            "不足",
                            "软收",
                            "跑题",
                            "说人话",
                            "连说",
                            "-",
                        )
                    )
                ]
                logger.info(
                    "gold_chat structure_score fail score=%s summary=%s "
                    "cons=%s pros=%s",
                    quality.get("structure_score") or quality.get("score"),
                    quality.get("summary"),
                    cons[:8],
                    reasons[:6],
                )
                expand_feedback_block = format_expand_regen_feedback(
                    last_err,
                    chat,
                    structure_type=structure_type,
                    mechanism=mechanism,
                    closing_intent=closing,
                    beat_chain=beat_chain,
                    conflict_text=conflict_text,
                    short_regen_count=short_regen_count,
                )
                continue
            return chat
        except ValueError as exc:
            last_err = str(exc)
            # 精修/校验路径截断也回灌 扩写，勿直接打死整次 convert
            if _is_truncation_error(last_err):
                last_err = f"align_refine_failed:LLM截断:{last_err}"
                expand_temperature = 0.25
            elif _is_short_content_error(last_err):
                short_regen_count = _bump_short_regen_or_reject(
                    last_err, short_regen_count
                )
                expand_temperature = max(expand_temperature, 0.55)
            elif not last_err.startswith(
                ("align_structural:", "align_refine_failed:", "structure_score:")
            ):
                raise
            expand_feedback_block = format_expand_regen_feedback(
                last_err,
                data,
                structure_type=structure_type,
                mechanism=mechanism,
                closing_intent=closing,
                beat_chain=beat_chain,
                conflict_text=conflict_text,
                short_regen_count=short_regen_count,
            )
    # 零食+作业本战：仅扩写耗尽后的兜底；
    # patch_m2_c_structure 不再无条件整篇覆盖
    if str(structure_type or "").upper() == "C" and str(mechanism or "").upper() == "M2":
        from app.services.gold_story.gold_chat.patch import (
            _m2_c_is_snack_homework_ctx,
            m2_c_meat_whole_item_context,
            m2_c_snack_rebuild_fallback_eligible,
            patch_m2_c_snack_beat_rebuild,
        )

        ctx_story = {
            "story_type": "C",
            "scene_title": str(row.get("title") or ""),
            "setting": str((payload.get("scene_contract") or {}).get("location") or ""),
            "conflict_core": conflict_core
            or str(payload.get("conflict") or conflict_text or ""),
            "dialogue": [],
        }
        meat = m2_c_meat_whole_item_context(ctx_story, payload=payload)
        if _m2_c_is_snack_homework_ctx(
            ctx_story,
            meat_ctx=meat,
            payload=payload,
        ):
            seed_story = dict(ctx_story)
            seed_story["dialogue"] = list(chat.get("dialogue") or [])
            if not m2_c_snack_rebuild_fallback_eligible(
                seed_story,
                last_err=str(last_err or ""),
                payload=payload if isinstance(payload, dict) else None,
            ):
                logger.info(
                    "gold_chat snack rebuild skipped: draft already structured "
                    "or err=%s",
                    (last_err or "")[:80],
                )
            else:
                rebuilt, notes = patch_m2_c_snack_beat_rebuild(
                    seed_story,
                    payload=payload,
                    boom_sp="昭昭",
                    last_sp="灿灿",
                )
                if conflict_core:
                    rebuilt["conflict_core"] = conflict_core
                rebuilt["story_type"] = "C"
                rebuilt = _attach_gold_chat_structure_score(rebuilt, row)
                try:
                    _gate_gold_chat_structure_score(rebuilt)
                    logger.info(
                        "gold_chat snack beat rebuild fallback: %s",
                        "；".join(notes),
                    )
                    return rebuilt
                except ValueError:
                    pass
    raise ValueError(
        _short_content_reject_message(last_err)
        if last_err and _is_short_content_error(last_err)
        else (last_err or "gold_chat generation failed")
    )

