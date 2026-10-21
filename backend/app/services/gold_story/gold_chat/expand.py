"""gold_chat 扩写：契约 + seed → LLM 初稿。

阶段一（expand）。入口 ``gold_story_to_gold_chat``；
精修见 ``refine.py``，终稿见 ``finalize.py``。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
    patch_m5_break_sibling_consecutive,
    patch_remap_sibling_terms,
    remap_source_kinship,
)
from app.services.gold_story.gold_chat.validate import (
    _line_fulfills_beat,
    closing_accept_marker,
    is_sulk_closing,
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
    _stabilize_local_length_candidate,
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
    PERBEAT_STAGE_DIRECTION_RE,
    format_beat_sequence_block,
    format_align_block,
    format_align_issues_block,
    SAFE_LINE_CHARS_HI,
    SAFE_LINE_CHARS_LO,
    format_cast_block,
    format_m5_h_expand_beat_block,
    format_authority_punchline_expand_block,
    format_scenario_rules_block,
    format_expand_regen_feedback,
    format_retry_missing_events_block,
    format_role_binding_block,
    format_seed_span_block,
    format_seed_skeleton_block,
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
    ensure_request_premise_dialogue,
    format_scene_block,
    looks_like_narration_line,
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
from app.services.gold_story.gold_chat.repair import (
    AlignRepairFailure,
    build_short_only_spot_fix_feedback,
    evaluate_repair_candidate_acceptance,
    is_expand_short_only_repair,
    list_short_spot_editable_line_nos,
)
from app.services.gold_story.gold_chat.validate import opening_causality_passes

logger = logging.getLogger(__name__)

_FATHER_SPEAKER_ALIASES = frozenset(
    {"爸爸", "父亲", "爸", "老爸", "宝爸", "爸爸角色", "父亲角色"}
)

_KID_RIVAL_ALIASES = frozenset(
    {"小男孩", "小女孩", "对方", "对方小朋友", "陌生小孩", "小朋友", "对方孩子"}
)

_THIRD_PARTY_PARENT_ALIASES = frozenset({"对方家长", "对方妈妈", "对方爸爸"})


def _debug_dump_expand(chat: dict[str, Any], source_id: str) -> None:
    """GOLD_CHAT_DEBUG_DUMP=1 时把扩写原始稿落盘（补丁前的基线）。"""
    if not os.environ.get("GOLD_CHAT_DEBUG_DUMP"):
        return
    path = Path("/tmp") / f"gold_chat_expand_{source_id or 'unknown'}.json"
    try:
        path.write_text(
            json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logger.warning("[GOLD_CHAT] expand debug dump failed %s", path)


def _resolve_closing_intent(
    payload: dict[str, Any],
    scene_contract: dict[str, Any],
    *,
    structure_type: str = "",
    k_close_mode: str = "",
) -> str:
    """读取 closing；I 对齐 seed 赢家；K-A 才纠偏僵持 closing。"""
    closing = str(
        payload.get("closing_intent") or scene_contract.get("closing_intent") or ""
    )
    st = str(structure_type or "").strip().upper()
    if st == "K":
        from app.services.daily_story.story_types.k.close_mode import (
            k_close_mode_from_story,
        )
        from app.services.daily_story.story_types.k.validate import (
            repair_closing_intent_for_k,
        )

        mode = str(k_close_mode or "").strip() or k_close_mode_from_story(
            {
                "k_close_mode": payload.get("k_close_mode")
                or scene_contract.get("k_close_mode"),
            }
        )
        return repair_closing_intent_for_k(closing, k_close_mode=mode)
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
    from app.services.gold_story.gold_chat.validate import (
        gold_chat_effective_min_chars,
    )

    data, _premise_notes = ensure_request_premise_dialogue(
        dict(story),
        dialogue_seed=dialogue_seed,
    )
    data, _ = apply_gold_chat_type_patch(data, structure_type="I")
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
    char_floor = gold_chat_effective_min_chars(data.get("dialogue"))
    if n < CHAT_LINE_COUNT_MIN or chars < char_floor:
        # 打回扩写：服软过早、争锋不够
        raise ValueError(
            f"align_refine_failed:I篇幅前置(句{n}/字{chars}，"
            f"须≥{CHAT_LINE_COUNT_MIN}句且≥{char_floor}字；"
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


def _repair_k_row_contract(row: dict[str, Any]) -> dict[str, Any]:
    """K：生成前解析 k_close_mode 并落盘；不根据正文反改。"""
    st = str(row.get("structure_type") or "").strip().upper()
    if st != "K":
        return row
    payload = cast(dict[str, Any], row.get("payload") or {})
    sc = cast(dict[str, Any], payload.get("scene_contract")) if isinstance(
        payload.get("scene_contract"), dict
    ) else {}
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_DISQUALIFIED,
        K_UNKNOWN,
        k_b_disqualification_reason,
        stamp_k_close_mode_on_payload,
    )

    chain = sc.get("beat_chain") if isinstance(sc.get("beat_chain"), list) else []
    closing = str(payload.get("closing_intent") or sc.get("closing_intent") or "")
    reason = k_b_disqualification_reason(beat_chain=chain, closing_intent=closing)
    if reason:
        # 契约期 fail-fast：K-B 的不变量是家长非介入、孩子自行收场；拍链把家长
        # 当成孩子的攻击/迁怒目标时，K-B 稿子形态与拍链结构性冲突，生成出来必挂终检。
        # 不静默改判（K-A 要求劝失败僵持、其它类型契约不同），带结构化原因拒绝。
        raise ValueError(f"K_B_DISQUALIFIED：{reason}；须先重建拍链/收束意图")
    new_payload = dict(payload)
    mode, changed = stamp_k_close_mode_on_payload(
        new_payload,
        beat_chain=chain,
        closing_intent=closing,
        mechanism_text=str(
            sc.get("mechanism") or row.get("mechanism") or ""
        ),
    )
    if mode == K_UNKNOWN or mode == K_B_DISQUALIFIED:
        # 契约期 fail-fast：解析器跑过却判不出轨，勿进正文生成。
        # 否则 K-A/K-B 两条硬卡都不生效（且正文已烧完 16 句才在终检失败）。
        # 在落盘之前抛：勿把历史空值行写成显式 K_UNKNOWN（重算只作诊断）。
        raise ValueError(
            "K_CLOSE_MODE_UNRESOLVED：beat_chain/closing 无法归入 K-A/K-B，"
            "须先重建收束意图（家长劝失败僵持 或 旁观+孩子自行停场），勿直接生成"
        )
    out = dict(row)
    out["payload"] = new_payload
    gid = int(row.get("id") or 0)
    if changed and gid > 0:
        from app.repositories import repo_gold_story

        repo_gold_story.patch_story_payload(
            gid,
            {
                "k_close_mode": mode,
                "scene_contract": new_payload.get("scene_contract"),
            },
        )
        refreshed = repo_gold_story.get_story(gid)
        if refreshed:
            # 重掷反馈是内存态（不入库），刷新行时须留下，否则甲的缺拍提示丢失
            from app.services.gold_story.gold_chat.convert import (
                carry_retry_feedback,
            )

            out = carry_retry_feedback(refreshed, out)
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
    if payload.get("k_close_mode"):
        patch["k_close_mode"] = payload.get("k_close_mode")
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
    from app.services.gold_story.gold_chat.convert import carry_retry_feedback

    return carry_retry_feedback(repo_gold_story.get_story(gid), row)

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

# 整篇生成的墙钟截止点（monotonic）。convert 起草前设置：任何一次填词/重写
# 调用前都先看还剩多少时间，不然 180s 预算只会在两次重掷之间检查，
# 单稿能一路跑到 4 分钟（#138 实测）。
_GOLD_CHAT_DEADLINE: float = 0.0


def set_gold_chat_deadline(deadline: float) -> None:
    global _GOLD_CHAT_DEADLINE
    _GOLD_CHAT_DEADLINE = float(deadline or 0.0)


def _check_gold_chat_deadline(reserve: float = 0.0) -> None:
    if _GOLD_CHAT_DEADLINE and time.monotonic() > _GOLD_CHAT_DEADLINE - reserve:
        raise ValueError("gold_chat 时间预算已用尽")


def _chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    _check_gold_chat_deadline(reserve=8.0)
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
    scene_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user = _FIX_USER.format(
        errors=errors,
        cast_block=format_cast_block(scene_contract),
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        **_prompt_budget_kwargs(),
    )
    return _chat_json(_FIX_SYSTEM, user, temperature=0.55)


_SHORT_SPOT_FIX_SYSTEM = (
    "你是 gold_chat 定点补字编辑。只输出 JSON："
    '{"fixes":[{"no":行号,"line":"改好后的一句台词"}]}。\n'
    "只允许改指定行号；行数、speaker 不变；首尾句冻结。\n"
    "line 必须是角色当场说出口的对白，禁止旁白/动作说明/括号。"
)

_SHORT_SPOT_FIX_USER = """{feedback}

当前 dialogue（节选）：
{story_json}

只输出 fixes JSON。"""


def _short_spot_fix_chat_with_llm(
    story: dict[str, Any],
    feedback: str,
    *,
    editable_line_nos: list[int],
    banned_literals: list[str],
    mom_lines_max: int,
) -> dict[str, Any]:
    if not editable_line_nos:
        raise ValueError("short_spot_fix: 无可扩写的中段姐弟句")
    user = _SHORT_SPOT_FIX_USER.format(
        feedback=feedback,
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
    )
    raw = _chat_json(_SHORT_SPOT_FIX_SYSTEM, user, temperature=0.45)
    polish_result = _apply_gold_chat_polish_fixes(
        story,
        raw,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )
    merged = polish_result.candidate
    base_rows = story.get("dialogue") or []
    new_rows = merged.get("dialogue") or []
    if len(new_rows) != len(base_rows):
        raise ValueError("short_spot_fix: 改变了句数")
    allowed = set(editable_line_nos)
    for index, (old, new) in enumerate(zip(base_rows, new_rows, strict=False), 1):
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        if str(old.get("speaker") or "").strip() != str(new.get("speaker") or "").strip():
            raise ValueError("short_spot_fix: 改变了 speaker")
        if index not in allowed and str(old.get("line") or "") != str(new.get("line") or ""):
            raise ValueError(f"short_spot_fix: 冻结行 {index} 被改动")
    out = dict(story)
    out["dialogue"] = new_rows
    return out


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
    """只接受超长行的缩句结果；行数/speaker/其它对白全部冻结。"""
    indices = _overlong_line_indices(story, max_chars)
    if not indices:
        return story
    rows = story.get("dialogue") or []
    if not isinstance(rows, list):
        return story
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
    raw = _normalize_chat_speakers(_chat_json(_SHORTEN_SYSTEM, user))
    new_rows = raw.get("dialogue") or []
    if not isinstance(new_rows, list) or len(new_rows) != len(rows):
        return story

    out = copy.deepcopy(story)
    out_rows = out.get("dialogue") or []
    for no in indices:
        idx = no - 1
        if not (
            0 <= idx < len(rows)
            and idx < len(new_rows)
            and idx < len(out_rows)
            and isinstance(rows[idx], dict)
            and isinstance(new_rows[idx], dict)
            and isinstance(out_rows[idx], dict)
        ):
            continue
        old_speaker = str(rows[idx].get("speaker") or "").strip()
        new_speaker = str(new_rows[idx].get("speaker") or "").strip()
        old_line = str(rows[idx].get("line") or "").strip()
        new_line = str(new_rows[idx].get("line") or "").strip()
        if new_speaker != old_speaker or not new_line:
            continue
        if len(new_line) > max_chars or len(new_line) >= len(old_line):
            continue
        out_rows[idx]["line"] = new_line
    return out

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

def _prepare_chat_local_repairs(
    data: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    conflict_text: str = "",
    mom_lines_max: int = 1,
    row: dict[str, Any] | None = None,
    scene_contract_location: str = "",
    activity_context: str = "",
) -> dict[str, Any]:
    """校验前只做会改变正文的本地修复；不补字、不 validate。"""
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
    return _apply_gold_chat_local_hard_repairs(
        data,
        structure_type=st,
        mom_lines_max=mom_lines_max,
    )


def _validate_prepared_chat(
    data: dict[str, Any],
    *,
    banned_literals: list[str] | None,
    mom_lines_max: int,
) -> dict[str, Any]:
    from app.services.gold_story.gold_chat.convert import validate_gold_chat

    validate_gold_chat(
        data,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )
    return data


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
    """普通校验入口：本地修复后按真实正文 hard 校验，不机械补字。"""
    data = _prepare_chat_local_repairs(
        data,
        structure_type=structure_type,
        mechanism=mechanism,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
        mom_lines_max=mom_lines_max,
        row=row,
        scene_contract_location=scene_contract_location,
        activity_context=activity_context,
    )
    return _validate_prepared_chat(
        data,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )


def _prepare_chat_for_validate_after_local_length_close(
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
    """已授权机械收口：先完成会削字的本地修复，再补 near-miss，最后 validate。"""
    data = _prepare_chat_local_repairs(
        data,
        structure_type=structure_type,
        mechanism=mechanism,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
        mom_lines_max=mom_lines_max,
        row=row,
        scene_contract_location=scene_contract_location,
        activity_context=activity_context,
    )
    payload = cast(dict[str, Any], (row or {}).get("payload") or {})
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    beat_chain = scene_contract.get("beat_chain") or []
    if not isinstance(beat_chain, list):
        beat_chain = []
    dialogue_seed = payload.get("dialogue_seed") or []
    if not isinstance(dialogue_seed, list):
        dialogue_seed = []
    if str(structure_type or "").strip().upper() == "N":
        from app.services.gold_story.gold_chat.patch import (
            apply_n_contract_local_patches,
        )

        data, n_ask_notes = apply_n_contract_local_patches(
            data,
            beat_chain=beat_chain,
            dialogue_seed=dialogue_seed,
            mom_lines_max=mom_lines_max,
        )
        if n_ask_notes:
            logger.info(
                "gold_chat N contract local patch before validate: %s",
                "；".join(n_ask_notes),
            )
    data, _ = _stabilize_local_length_candidate(
        data,
        structure_type=structure_type,
        mechanism=mechanism,
        beat_chain=beat_chain,
        dialogue_seed=dialogue_seed,
    )
    return _validate_prepared_chat(
        data,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )

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
    # LLM 修稿/重写只被提示词告知「key 2–8 字」，实际会写出 9 字。本地先收口
    # 再校验，别为长度问题白烧一轮修稿预算（#144 实测：9 字 key 让已拼好的
    # 12 句稿被结构分直接驳回）。
    _key = str(data.get("key") or "").strip()
    if len(_key) > DAILY_STORY_KEY_CHARS_MAX:
        data["key"] = _key[:DAILY_STORY_KEY_CHARS_MAX].strip()
    st = str(structure_type or data.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    payload = cast(dict[str, Any], (row or {}).get("payload") or {})
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    beat_chain = scene_contract.get("beat_chain") or []
    if not isinstance(beat_chain, list):
        beat_chain = []
    dialogue_seed = payload.get("dialogue_seed") or []
    if not isinstance(dialogue_seed, list):
        dialogue_seed = []
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
        if not _perbeat_enabled():
            # 逐拍骨架已保证句数与字数（target≥14 句 / ≥300 字），再垫字只会
            # 插进 _N_VIEWER_ECHO_TEMPLATES 池子对（「反正我就这么说，你信不信
            # 都行」+「哈哈，妈你记下来没…」），#138 实测 14 句被灌成 18 句，
            # 结构分掉到 68–72，且终检判「接不上」。
            data, _ = _ensure_gold_chat_min_chars(
                data,
                mechanism=mech,
                structure_type=st,
                beat_chain=beat_chain,
                dialogue_seed=dialogue_seed,
            )
            if st == "K" and dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
                data, _ = _gold_chat_force_min_chars(data)
                data, _ = _ensure_gold_chat_min_chars(
                    data,
                    mechanism=mech,
                    structure_type=st,
                    beat_chain=beat_chain,
                    dialogue_seed=dialogue_seed,
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
            if _perbeat_enabled():
                # 逐拍模式：`_fix_chat_with_llm` 会**整篇重写**，把锁死的说话人
                # 与拍序一起冲掉（#138 实测：14 句 309 字 → 16 句 254 字，混进
                # 「你还真是照这个道理认真想的？」这类池子句，随后被判错位）。
                # 只做本地机械修补，剩下的交给外层**重新逐拍生成**整篇。
                data = _apply_gold_chat_local_hard_repairs(
                    data,
                    structure_type=st,
                    mom_lines_max=mom_lines_max,
                )
                try:
                    validate_gold_chat(
                        data,
                        banned_literals=banned_literals,
                        source_type=source_type,
                        mom_lines_max=mom_lines_max,
                    )
                    return data
                except ValueError as exc2:
                    raise ValueError(f"perbeat validate: {exc2}") from exc2
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

def _perbeat_enabled() -> bool:
    """逐拍填词已是主干路径，默认启用。

    仅保留 `GOLD_CHAT_PERBEAT=0/off/legacy` 作为故障时回退整篇扩写的应急开关，
    常规流程不需要设置。
    """
    return str(os.getenv("GOLD_CHAT_PERBEAT") or "").strip().lower() not in {
        "0",
        "off",
        "false",
        "no",
        "legacy",
    }


def _perbeat_legacy() -> bool:
    """GOLD_CHAT_PERBEAT=legacy 时走旧的 `_perbeat_slots` 死规则（回滚用）。"""
    return str(os.getenv("GOLD_CHAT_PERBEAT") or "").strip().lower() == "legacy"


# ---------------------------------------------------------------------------
# 逐句线路计划（line plan）
#
# 旧路线 `_perbeat_slots` 用死规则决定「第几句由谁说」「多出来的句子说什么」：
# 每拍先出一槽；家长拍不再补槽，孩子拍补一条「另一个孩子」的插话槽；
# 槽数超 12 就从中段摘插话槽。于是「拍数少、家长占拍多」的契约
# （#138：8 拍里妈妈占 4 拍、灿灿只 1 拍）只能靠插话槽凑满 12 句，
# 而插话槽没有具体意图可填，填词器只能写空表态，终检再按
# 「重复 / 接不上 / 旁白」打回——之前的补丁全在给这套死规则打补丁。
#
# 现在把「12 句怎么分、每句干什么」分成两段：谁在第几句说话由本地骨架确定性
# 排出（拍主各一句 + 多出来的按拍轮转补孩子反应），模型只给每行写 intent；
# 结构由骨架保证，intent 不合格只重写 intent，既不动契约，也不碰已写的台词。
# ---------------------------------------------------------------------------

LINE_PLAN_ATTEMPTS = 2
# 计划目标 12 句：孩子拍各拆一句刚好够（8 拍 = 8 主句 + 4 拆句），不再往
# 家长拍里硬插反应——多一句就会引出「妈妈问饺子、灿灿冒出一句不服」这类无头台词。
LINE_PLAN_TARGET_LINES = 12
# 孩子拍最多排几句：契约里一拍常写「先动手、还手、喊疼、指责」这类
# 多回合 intent（库里大量 4 拍契约就靠这种拍撑满 12 句），
# 所以孩子拍的容量不能按「一拍一句」算。
LINE_PLAN_KID_LINES_PER_BEAT = 5

# 静场拍：intent 本身是动作/停顿（愣住、接不上、没落下…），
# 不能把动作当台词写，只排一句当场接话。
_LINE_PLAN_STATIC_RE = re.compile(
    r"愣|接不上|没落下|认栽|认怂|服了|不响|沉默|卡壳|噎住|僵住"
)

_LINE_PLAN_PARENT_SPEAKERS = ("妈妈", "爸爸")

_LINE_PLAN_STAGE_WORDS = (
    "气笑",
    "不慌不忙",
    "愣住",
    "没落下",
    "举着筷子",
    "看妈妈",
    "看昭昭",
    "看着",
    "转头",
    "点头",
    "摇头",
    "叹气",
    "皱眉",
    "脸色",
)


def _line_plan_static_beat(beat: dict[str, Any] | str) -> bool:
    """拍/意图是否是「静场型」（愣住、接不上、没落下…）。接受 dict 或纯文本。"""
    intent = (
        str(beat.get("intent") or beat.get("beat") or "")
        if isinstance(beat, dict)
        else str(beat or "")
    )
    return bool(_LINE_PLAN_STATIC_RE.search(intent))


def _line_plan_speakers(beat_chain: list[Any]) -> list[str]:
    out: list[str] = []
    for beat in beat_chain or []:
        if not isinstance(beat, dict):
            continue
        speaker = str(beat.get("speaker") or "").strip()
        if speaker and speaker not in out:
            out.append(speaker)
    return out


def _line_plan_capacity(
    scene_contract: dict[str, Any],
    beat_chain: list[Any],
    *,
    target_lines: int,
) -> list[str]:
    """契约能不能排满 target_lines 句（纯本地判断，不调 LLM）。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    if not beats:
        return ["契约没有 beat_chain"]
    _mom, _dad, parent_max = resolve_parent_lines_budget(
        scene_contract, default_mom_lines_max=1
    )
    parent_beats = 0
    capacity = 0
    for beat in beats:
        speaker = str(beat.get("speaker") or "").strip()
        is_parent = speaker in _LINE_PLAN_PARENT_SPEAKERS
        if is_parent:
            parent_beats += 1
        if _line_plan_static_beat(beat):
            capacity += 1
        elif is_parent:
            # 家长拍里可以夹一句孩子的反应（家长问、孩子答），
            # 否则「家长占 5 拍」的契约连 12 句都分不出来。
            capacity += 2
        else:
            capacity += LINE_PLAN_KID_LINES_PER_BEAT
    errors: list[str] = []
    if parent_beats > parent_max:
        errors.append(
            f"契约里家长占 {parent_beats} 拍，家长额度只有 {parent_max} 句"
        )
    if len(beats) > target_lines:
        errors.append(f"契约 {len(beats)} 拍，比目标 {target_lines} 句还多")
    if capacity < target_lines:
        errors.append(
            f"契约最多排 {capacity} 句，排不满目标 {target_lines} 句"
        )
    return errors


_LINE_PLAN_SPLIT_MARKER_RE = re.compile(r"又|再|还|并且|同时|接着|顺带|另外")


def _beat_is_splittable(beat: dict[str, Any]) -> bool:
    """这一拍的内容能不能拆给两个孩子说。

    只有拍意图里真有两块内容（「嫌饺子难吃，**又**夸妈妈眉清目秀」）才拆；
    单块内容硬拆，第二个孩子只能复述拍主刚说的话——审读判「帮腔式重复」
    （#138 实测：灿灿把「眉清目秀」原样再说一遍）。
    """
    if _line_plan_static_beat(beat):
        # 静场拍（「愣住看妈妈」「举着筷子半天没落下」）本身没有两块内容，
        # 拆出来只能让另一个孩子复述现场，不能拆。
        return False
    intent = str(beat.get("intent") or beat.get("beat") or "").strip()
    if _LINE_PLAN_SPLIT_MARKER_RE.search(intent):
        return True
    parts = [x for x in re.split(r"[，,；;]", intent) if len(x.strip()) >= 4]
    return len(parts) >= 2


def _split_beat_halves(intent: str) -> tuple[str, str]:
    """把一拍内容拆成「拍主说的那半 / 拆句说的那半」。

    只在真有两个并列块时切（「嫌饺子难吃，**又**夸妈眉清目秀」）；
    切不出来返回空串，调用方就不标拆句。
    """
    text = str(intent or "").strip()
    m = _LINE_PLAN_SPLIT_MARKER_RE.search(text)
    if m and m.start() > 0:
        return text[: m.start()].strip(" ，,；;"), text[m.end() :].strip(" ，,；;")
    parts = [x.strip() for x in re.split(r"[，,；;]", text) if x.strip()]
    if len(parts) >= 2:
        return "，".join(parts[:1]), "，".join(parts[1:])
    return "", ""


def _line_plan_skeleton(
    scene_contract: dict[str, Any],
    beat_chain: list[Any],
    *,
    target_lines: int,
    no_material_speakers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """确定性排「第几句由谁说」：拍主各一句，多出来的按拍轮转补反应。

    谁在第几句说话不让模型决定——它的额度/拍覆盖/相邻同人约束学不会，
    实测两次重试都排不出合格结构。模型只负责给每行写 intent。

    补句规则（保证与 `_validate_line_plan` 同口径）：
    - 一拍补两句 = 「反应 + 拍主收尾」，所以补完仍以拍主收尾，
      要求下一拍拍主不是同一人（否则相邻同人）；
    - 余一句时插在拍首，要求与上一拍末句不同人；
    - 孩子拍容量 5、家长拍 2、静场拍 2，家长句数不超预算。
    """
    from app.services.gold_story.scene import resolve_parent_lines_budget

    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    mom_max, dad_max, _parent_max = resolve_parent_lines_budget(
        scene_contract, default_mom_lines_max=1
    )
    cast = [
        str(x).strip()
        for x in (scene_contract.get("characters") or [])
        if str(x).strip()
    ]
    present = set(cast)
    owners = [
        str(b.get("speaker") or "").strip()
        or (cast[0] if cast else "妈妈")
        for b in beats
    ]
    present.update(owners)
    parents = [p for p in _LINE_PLAN_PARENT_SPEAKERS if p in present]
    kids = [k for k in _KID_NAMES if k in present] or [
        c for c in cast if c not in parents
    ]
    budget = {"妈妈": mom_max, "爸爸": dad_max}
    counts: dict[str, int] = {}
    for owner in owners:
        counts[owner] = counts.get(owner, 0) + 1
    groups: list[list[dict[str, Any]]] = [
        [
            {
                "beat": no,
                "speaker": owners[no - 1],
                "role": "main",
                # 拍主那句要交代什么，拍意图已经写清楚了：直接取用，
                # 既省一次规划误差，也让 plan 只补「拍主之外」的行。
                "intent": str(beats[no - 1].get("intent") or "").strip(),
                "from_beat": True,
            }
        ]
        for no in range(1, len(beats) + 1)
    ]

    def cap_of(no: int) -> int:
        beat = beats[no - 1]
        if _line_plan_static_beat(beat):
            return 2
        return (
            2
            if str(beat.get("speaker") or "").strip() in parents
            else LINE_PLAN_KID_LINES_PER_BEAT
        )

    def other_speaker(
        no: int, owner: str, banned: tuple[str, ...] = ()
    ) -> str:
        pool = [k for k in kids if k != owner]
        for parent in parents:
            if parent == owner or counts.get(parent, 0) >= budget.get(parent, 0):
                continue
            # 该家长在后面还有自己的主句：插话排在这里，一开口就会把后面那拍
            # 的话说掉，逐拍判「插话不得顶替契约拍的台词」、终检判「核心反应
            # 被换人」（#144 实测：妈妈在 beat2 的反应连续三轮被判顶替）。
            if any(
                owners[j] == parent for j in range(no, len(owners))
            ):
                continue
            pool.append(parent)
        pool = [c for c in pool if c not in banned]
        if not pool:
            return ""
        return min(pool, key=lambda c: (c in parents, counts.get(c, 0)))

    def next_owner(no: int) -> str:
        return owners[no] if no < len(beats) else ""

    order = sorted(
        range(1, len(beats) + 1),
        key=lambda no: (
            no == len(beats),
            str(beats[no - 1].get("speaker") or "").strip() in parents,
            no,
        ),
    )
    remaining = target_lines - sum(len(group) for group in groups)
    # 多出来的句子**优先只在孩子拍里补**，并且是「拆句」：原稿里孩子那一回合
    # 拆成两个孩子各说一半（用户 2026-10 定的口径：源故事 8 回合撑 12 句的正解）。
    # 家长拍/静场拍不补——在妈妈问句后面硬插孩子反应，审读必判「没头没脑、
    # 答非所问」（#138 实测：灿灿在妈妈问饺子时冒出「你这么说我可不服」）。
    guard = 0
    while remaining > 0 and guard < 4 * target_lines:
        guard += 1
        progress = False
        for kid_pass in (True, False):
            for no in order:
                if remaining <= 0:
                    break
                owner = owners[no - 1]
                is_kid_beat = owner in kids
                if kid_pass and not is_kid_beat:
                    continue
                if not kid_pass and is_kid_beat:
                    continue
                group = groups[no - 1]
                if len(group) >= cap_of(no):
                    continue
                nxt = owners[no] if no < len(beats) else ""
                speaker = other_speaker(no, owner, (group[-1]["speaker"], nxt))
                if not speaker:
                    continue
                # 源故事里根本没出声的角色（#144 的旁人「灿灿」）不接拆句：拆句
                # 要求它说出本拍另一半内容，而它没有素材，只能转述别人的话
                # （实测三轮都是「她认了衣服是自己弄脏，还说疼你不想让你操心」
                # 这种旁白）。这类行只当在场者接话（旁观/递话），交机检的
                # 「零素材插话」口径处理。
                _split = (
                    is_kid_beat
                    and speaker in kids
                    and _beat_is_splittable(beats[no - 1])
                    and speaker not in (no_material_speakers or set())
                    # 旁观拍不拆：拍主只是「在旁边听着、你慢慢说」，拆给另一个
                    # 孩子就变成当事人去演旁观者的台词（#144 每轮第 4 句实测：
                    # 昭昭复述灿灿的安慰话，终检判「说话主体对调」）。
                    and owner not in (no_material_speakers or set())
                )
                group.append(
                    {
                        "beat": no,
                        "speaker": speaker,
                        "role": "reaction",
                        # 能拆的拍才标拆句；拆不动的拍只作在场者接话。
                        "split": _split,
                        "split_half": _split_beat_halves(
                            str(beats[no - 1].get("intent") or "")
                        )[1]
                        if _split
                        else "",
                    }
                )
                counts[speaker] = counts.get(speaker, 0) + 1
                remaining -= 1
                progress = True
            if remaining <= 0 or progress:
                break
        if not progress:
            break
    # 收尾修复：相邻两拍同人时，在后一拍拍首插一句反应（句数允许涨到 13/14）。
    for _ in range(len(groups) + 1):
        fixed = True
        for no in range(2, len(groups) + 1):
            group = groups[no - 1]
            prev_last = groups[no - 2][-1]["speaker"]
            if not group or group[0]["speaker"] != prev_last:
                continue
            # 不在下一拍拍首插反应（那会让插话先于拍主开口），改成给上一拍
            # 末尾补一句别人的反应：同样断开相邻同人，但不抢拍主的话头。
            prev_group = groups[no - 2]
            if len(prev_group) >= cap_of(no - 1):
                return []
            speaker = other_speaker(
                no - 1, owners[no - 2], (prev_last,)
            )
            if not speaker:
                return []
            prev_group.append(
                {"beat": no - 1, "speaker": speaker, "role": "reaction"}
            )
            counts[speaker] = counts.get(speaker, 0) + 1
            fixed = False
        if fixed:
            break
    if any(
        groups[no - 1] and groups[no - 2][-1]["speaker"]
        == groups[no - 1][0]["speaker"]
        for no in range(2, len(groups) + 1)
    ):
        return []
    return [row for group in groups for row in group]


def _merge_line_plan_intents(
    rows: list[dict[str, Any]],
    data: Any,
) -> list[dict[str, Any]]:
    """把模型返回的 intent 按行号贴回骨架。"""
    intents: dict[int, str] = {}
    raw = data.get("lines") if isinstance(data, dict) else None
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(str(item.get("i")).strip())
            except (TypeError, ValueError):
                continue
            text = str(item.get("intent") or "").strip()
            if text:
                intents[idx] = text
    return [
        {
            **row,
            # 拍主行（from_beat）的 intent 由骨架直接取拍意图，模型不必再填；
            # 这样 plan 的调用量减半、也不会再把「气笑要求…」写成动作词。
            "intent": intents.get(idx) or str(row.get("intent") or ""),
            "addressee": "",
        }
        for idx, row in enumerate(rows, 1)
    ]


def _validate_line_plan(
    plan: list[dict[str, Any]],
    *,
    scene_contract: dict[str, Any],
    beat_chain: list[Any],
    target_lines: int,
) -> list[str]:
    """计划的结构校验：句数/说话人/额度/拍序/覆盖/intent，全部确定性。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    if not plan:
        return ["计划为空"]
    errors: list[str] = []
    if len(plan) != target_lines:
        errors.append(f"句数 {len(plan)} ≠ {target_lines}")
    allowed = set(_line_plan_speakers(beats))
    allowed.update(
        str(x).strip()
        for x in (scene_contract.get("characters") or [])
        if str(x).strip()
    )
    mom_max, dad_max, parent_max = resolve_parent_lines_budget(
        scene_contract, default_mom_lines_max=1
    )
    counts: dict[str, int] = {}
    prev_speaker = ""
    prev_beat = 0
    for idx, row in enumerate(plan, 1):
        speaker = row["speaker"]
        if speaker not in allowed:
            errors.append(f"第{idx}句说话人「{speaker}」不在场")
        if speaker == prev_speaker:
            errors.append(f"第{idx}句与第{idx - 1}句同一说话人")
        prev_speaker = speaker
        counts[speaker] = counts.get(speaker, 0) + 1
        beat_no = int(row["beat"] or 0)
        if beat_no < 1 or beat_no > len(beats):
            errors.append(f"第{idx}句拍号 {beat_no} 越界（1..{len(beats)}）")
        elif beat_no < prev_beat:
            errors.append(f"第{idx}句拍号 {beat_no} 早于上一句")
        prev_beat = max(prev_beat, beat_no)
        intent = str(row.get("intent") or "")
        if len(intent) < 4:
            errors.append(f"第{idx}句缺 intent 或太短")
        if row.get("from_beat"):
            # 拍主行的 intent 就是拍意图原文，动作/神态本来就在里面
            pass
        elif any(word in intent for word in _LINE_PLAN_STAGE_WORDS):
            # 例外：静场/收束拍本身就是动作（「举着筷子半天没落下」），拍主
            # 这句的 intent 就是拍意图原文——照搬是对的，不重写（见
            # `_line_plan_settle_stage_intents`）。
            beat_intent = ""
            if 0 < beat_no <= len(beats):
                beat_intent = str(beats[beat_no - 1].get("intent") or "").strip()
            settled = bool(beat_intent and _line_plan_static_beat(intent))
            if not settled:
                errors.append(f"第{idx}句 intent 写了动作/神态")
    mom = counts.get("妈妈", 0)
    dad = counts.get("爸爸", 0)
    if mom > mom_max:
        errors.append(f"妈妈 {mom} 句 > 上限 {mom_max}")
    if dad > dad_max:
        errors.append(f"爸爸 {dad} 句 > 上限 {dad_max}")
    if mom + dad > parent_max:
        errors.append(f"家长合计 {mom + dad} 句 > 上限 {parent_max}")
    if plan[0]["beat"] != 1:
        errors.append("第1句不在第1拍")
    if plan[-1]["beat"] != len(beats):
        errors.append("最后一句不在最后一拍")
    last_speaker = str(beats[-1].get("speaker") or "").strip()
    if last_speaker and plan[-1]["speaker"] != last_speaker:
        errors.append(f"最后一句不是收束拍说话人「{last_speaker}」")
    rows_by_beat: dict[int, list[int]] = {}
    for idx, row in enumerate(plan, 1):
        rows_by_beat.setdefault(int(row["beat"] or 0), []).append(idx)
    for no, beat in enumerate(beats, 1):
        rows = rows_by_beat.get(no) or []
        if not rows:
            errors.append(f"第{no}拍没有一句台词")
            continue
        beat_speaker = str(beat.get("speaker") or "").strip()
        if beat_speaker and all(
            plan[idx - 1]["speaker"] != beat_speaker for idx in rows
        ):
            errors.append(f"第{no}拍说话人「{beat_speaker}」没有出声")
    # 拆句行必须写「本拍另一半」：拍意图能被切成两半时，拆句 intent 要含
    # 后半那块里的实词；切不出两半（骨架不会标 split）时不做这项校验。
    for idx, row in enumerate(plan, 1):
        if not row.get("split"):
            continue
        half = str(row.get("split_half") or "").strip()
        if not half:
            continue
        mine = _perbeat_terms(str(row.get("intent") or ""))
        if not (mine & _perbeat_terms(half)):
            errors.append(
                f"第{idx}句是拆句，但没补出本拍另一半内容（只说「{half}」那半）",
            )

    normalized = [
        re.sub(r"[^\u4e00-\u9fff]", "", str(row.get("intent") or ""))
        for row in plan
        if not row.get("from_beat")
        and not _line_plan_static_beat(str(row.get("intent") or ""))
    ]
    duplicated = {
        text for text in normalized if text and normalized.count(text) > 1
    }
    if duplicated:
        errors.append("intent 有重复：" + "、".join(sorted(duplicated)[:2]))
    return errors


_LINE_PLAN_STAGE_STRIP = (
    "气笑要求", "气笑", "不慌不忙", "狐疑追问", "狐疑", "认栽说", "认栽",
    "愣住", "愣", "苦笑", "无奈", "正色说", "正色", "板着脸", "挑眉",
    "撇嘴", "转头", "摇头", "叹气", "皱眉", "端来", "端着", "举着",
    "放下", "坐下", "站起来", "看着", "看妈妈", "看爸爸",
)


def _line_plan_sanitize_intents(
    plan: list[dict[str, Any]],
    beats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把 intent 里的舞台提示语剥掉，而不是整份计划报废。

    模型写 intent 时爱带「气笑」「端来」这类动作词；判废重试两轮仍改不掉，
    于是整份计划被丢掉、退回硬编码旧槽（#138 实测，退回那稿才出现重复）。
    这里做确定性兜口：剥掉动作词，剥空了就落成拍意图。
    """
    for row in plan:
        intent = str(row.get("intent") or "").strip()
        for word in _LINE_PLAN_STAGE_STRIP:
            intent = intent.replace(word, "")
        intent = re.sub(r"^[，,、\s]+", "", intent).strip("，。；、 ")
        if len(intent) < 4:
            beat_no = int(row.get("beat") or 0)
            beat = beats[beat_no - 1] if 0 < beat_no <= len(beats) else {}
            intent = str(beat.get("intent") or "").strip()
        row["intent"] = intent
    return plan


def _line_plan_settle_stage_intents(
    plan: list[dict[str, Any]],
    beats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """静态拍的 intent 若写成动作/神态，直接落成拍意图，不返工重写。

    收束拍本身是「举着筷子半天没落下，认栽说…」，模型照抄动作是正常理解，
    提示词里禁动作却改不掉（#138 实测连续两轮因第 11/12 句动作词整份 plan
    报废、退回硬编码旧槽）。这里改成确定性收口：这类行直接用拍意图当 intent。
    """
    for row in plan:
        intent = str(row.get("intent") or "")
        if not any(word in intent for word in _LINE_PLAN_STAGE_WORDS):
            continue
        beat_no = int(row.get("beat") or 0)
        beat = beats[beat_no - 1] if 0 < beat_no <= len(beats) else {}
        beat_intent = str(beat.get("intent") or "").strip()
        if beat_intent and _line_plan_static_beat(beat_intent):
            row["intent"] = beat_intent
    return plan


def _build_line_plan(
    *,
    scene_contract: dict[str, Any],
    beat_chain: list[Any],
    story_raw: str,
    target_lines: int,
    temperature: float,
    no_material_speakers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """确定性骨架 + 一次 intent 规划：结构不过关只重写 intent，不动骨架。"""
    from app.services.gold_story.gold_chat.prompts import (
        LINE_PLAN_SYSTEM,
        format_line_plan_user,
    )

    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    capacity_errors = _line_plan_capacity(
        scene_contract, beats, target_lines=target_lines
    )
    if capacity_errors:
        raise ValueError(
            "perbeat: line_plan 契约容量不足：" + "；".join(capacity_errors)
        )
    rows = _line_plan_skeleton(
        scene_contract,
        beats,
        target_lines=target_lines,
        no_material_speakers=no_material_speakers,
    )
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN as _LP_MIN

    if len(rows) < _LP_MIN:
        raise ValueError(
            f"perbeat: line_plan 骨架只排出 {len(rows)} 句"
            f"（至少 {_LP_MIN} 句），契约拍不够用"
        )
    # 骨架可能因「相邻拍同人」多补一对，落到 13 句：以骨架实际句数为准。
    target_lines = len(rows)
    feedback = ""
    last_errors: list[str] = []
    for attempt in range(1, LINE_PLAN_ATTEMPTS + 1):
        user = format_line_plan_user(
            scene_contract=scene_contract,
            story_raw=story_raw,
            rows=rows,
            feedback=feedback,
            no_material_speakers=no_material_speakers,
        )
        data = _chat_json(
            LINE_PLAN_SYSTEM,
            user,
            temperature=temperature,
            max_tokens=2400,
        )
        plan = _line_plan_settle_stage_intents(
            _merge_line_plan_intents(rows, data), beats
        )
        last_errors = _validate_line_plan(
            plan,
            scene_contract=scene_contract,
            beat_chain=beats,
            target_lines=target_lines,
        )
        if not last_errors:
            logger.info(
                "[GOLD_CHAT] line_plan ok attempt=%s lines=%s beats=%s",
                attempt,
                len(plan),
                len(beats),
            )
            return plan
        logger.info(
            "[GOLD_CHAT] line_plan retry %s/%s: %s",
            attempt,
            LINE_PLAN_ATTEMPTS,
            "；".join(last_errors[:4]),
        )
        feedback = (
            "\n【上一版 intent 不合格，按条改掉后重出完整 JSON】\n"
            + "\n".join(f"- {item}" for item in last_errors)
        )
    # 最后一招：把剩下的动作词剥掉再验一次，别因为一个「气笑」丢掉整份计划。
    settled = _line_plan_sanitize_intents(
        [dict(row) for row in plan], beats
    )
    settled_errors = _validate_line_plan(
        settled,
        scene_contract=scene_contract,
        beat_chain=beats,
        target_lines=target_lines,
    )
    if not settled_errors:
        logger.info(
            "[GOLD_CHAT] line_plan ok after sanitize lines=%s beats=%s",
            len(settled),
            len(beats),
        )
        return settled
    raise ValueError(
        "perbeat: line_plan 不合格：" + "；".join(settled_errors[:4])
    )


def _line_plan_slots(
    plan: list[dict[str, Any]],
    beat_chain: list[Any],
    *,
    no_material_speakers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """计划 → 填词槽（字段与 `_perbeat_slots` 一致，供 `_perbeat_fill_slots` 复用）。"""
    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    owner_seen: set[int] = set()
    slots: list[dict[str, Any]] = []
    # 哪些拍被拆成两人说：拍主说前半、另一个孩子说后半。
    split_beats = {
        int(row.get("beat") or 0)
        for row in plan
        if row.get("split") and int(row.get("beat") or 0) > 0
    }
    for row in plan:
        beat_no = int(row.get("beat") or 0)
        beat = beats[beat_no - 1] if 0 < beat_no <= len(beats) else {}
        owner = str(beat.get("speaker") or "").strip()
        _speaker = str(row.get("speaker") or "").strip()
        # 本拍主句 = 拍主在这一拍里的第一句。不能按「这一拍的第一句」判：
        # 骨架会在拍首插一句反应（余一句 / 修相邻同人），那时拍主的句子排在
        # 第二位，按位置判就变成「这一拍没人负责交代 intent」，整拍内容全交给
        # 可丢的插话槽（#138 第 4 拍实测）。
        is_owner = row.get("speaker") == owner
        main = is_owner and beat_no not in owner_seen
        if is_owner:
            owner_seen.add(beat_no)
        slots.append(
            {
                "beat_id": beat_no,
                "speaker": str(row.get("speaker") or "").strip(),
                "intent": str(row.get("intent") or "").strip(),
                "function": (
                    "本拍主句"
                    if main
                    else (
                        "本拍拆句（说本拍的另一半）"
                        if row.get("split")
                        else "接住上一句"
                    )
                ),
                "is_filler": not main,
                "is_split": bool(row.get("split")),
                # 有素材的槽照旧按内容槽判；源故事里没出声的角色（#144 的旁观
                # 角色灿灿）标 False，机检走「零素材插话」的放宽口径。
                "has_content": bool(
                    _speaker and _speaker not in (no_material_speakers or set())
                ),
                "beat_intent": str(beat.get("intent") or "").strip(),
                # 拆句拍的主句只说前半，拆句行只说后半；后文引用这半句时
                # 必须按实际说话人称呼（妈妈问的是「谁夸的」，不是固定问昭昭）。
                "split_role": (
                    "second_half"
                    if row.get("split")
                    else ("first_half" if beat_no in split_beats else "")
                ),
                "addressee": str(row.get("addressee") or "").strip(),
            }
        )
    return slots


_KID_NAMES = ("昭昭", "灿灿")


_N_SLOT_WORD_REQS: dict[str, tuple[str, ...]] = {
    "why": ("为啥", "为什么", "凭什么", "什么意思", "啥意思"),
    "reason": ("因为", "所以", "就能", "这样就能"),
    "stun": ("行吧", "服了", "那……", "接不住"),
}


_INTENT_SPLIT_RE = re.compile(r"[，,；;]\s*(?:又|并|再|且|还|另外|同时|然后)")


_INTENT_LEAD_NOISE = (
    "又", "并", "再", "且", "还", "另外", "同时", "然后", "补一句", "补上",
    "说一句", "加一句", "接一句", "来一句", "一句", "一句的",
)


def _intent_second_part_terms(intent: str) -> list[str]:
    """契约拍里「又/并/再」后面那半句的**三字**特征片段。

    #138 实测：第 2 拍 intent 是「嫌黑面芯子难吃无比，又补一句妈妈眉清目秀」，
    模型只写了前半（「这黑面饺子芯子苦得我直咧嘴」），于是第 3 拍妈妈追问
    「今天咋舍得夸妈眉眼清秀」变成「引用无据」整稿退回。这类「一拍两件事」
    的拍必须让后半句也有落点。

    用三字片段（「眉清目」）而不是二字词（「妈妈」「清目」）：二字词太容易
    被高频词命中，三字基本只有真的说了那件事才会出现。
    """
    parts = _INTENT_SPLIT_RE.split(str(intent or ""))
    if len(parts) < 2:
        return []
    tail = parts[1]
    for noise in _INTENT_LEAD_NOISE:
        if tail.startswith(noise):
            tail = tail[len(noise) :]
    head_terms = _perbeat_terms(parts[0])
    grams: list[str] = []
    for i in range(len(tail) - 2):
        gram = tail[i : i + 3]
        if not re.fullmatch(r"[\u4e00-\u9fff]{3}", gram):
            continue
        if _perbeat_terms(gram) & head_terms:
            continue  # 前半句已经覆盖的词组不算新要求
        if gram not in grams:
            grams.append(gram)
    return grams[:6]


def _perbeat_apply_intent_cover(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """复合拍的每个补充要求各占一组，不能被追问等机制词替代。"""
    for slot in slots:
        if slot.get("is_filler"):
            continue
        parts = _INTENT_SPLIT_RE.split(str(slot.get("intent") or ""))
        groups = _perbeat_required_word_groups(slot)
        for part in parts[1:]:
            more = _intent_second_part_terms(f"{parts[0]}，并{part}")
            if not more:
                continue
            groups.append(more)
            slot["function"] = (
                f"{slot.get('function') or ''}；本句必须同时交代「{part}」这件事"
            ).strip("；")
        slot["required_word_groups"] = groups
    return slots


def _perbeat_required_word_groups(slot: dict[str, Any]) -> list[list[str]]:
    """组间全部满足、组内任选一个；兼容原有单组 must_words。"""
    groups = [list(group) for group in slot.get("required_word_groups") or []]
    words = list(slot.get("must_words") or [])
    if words and words not in groups:
        groups.insert(0, words)
    return groups


def _perbeat_words_ok(line: str, groups: list[list[str]]) -> bool:
    return all(any(word in line for word in group) for group in groups)


def _apply_required_semantic_points(
    slots: list[dict[str, Any]],
    beat_chain: list[Any] | None,
) -> list[dict[str, Any]]:
    """把契约拍的必现语义点挂到槽上（批提示词里要显式写出来）。

    单句只有 24 字，模型会按「哪句读着顺」砍内容：契约把语义点声明成
    ``required_semantic_points`` 后，机检能拦住，但拦在生成之后等于白烧一轮。
    先在分配表里写明「必现（缺一不可）」，模型才知道该砍别的地方
    （#144 run26 实测：beat5 连续三轮都砍掉句尾的「疼妈妈」）。
    """
    beats = {
        int(item.get("beat") or 0): item
        for item in (beat_chain or [])
        if isinstance(item, dict)
    }
    for slot in slots:
        if slot.get("is_filler"):
            continue
        points = _perbeat_required_points(
            beats.get(int(slot.get("beat_id") or 0))
        )
        if points:
            slot["required_semantic_terms"] = [p["terms"] for p in points]
    return slots


def _apply_n_word_slots(
    slots: list[dict[str, Any]],
    *,
    structure_type: str,
) -> list[dict[str, Any]]:
    """给 N 类的三个硬词槽（追问/自洽/愣住）分配「必须出现某个词」的硬要求。

    这三条是 N 类正文契约的机检项（``story_types/n/validate.py``：RE_WHY /
    RE_SOLEMN_REASON / stun_close_hit）。整篇扩写靠模型自然覆盖；逐拍填词每个槽
    只看一句上下文，容易整篇漏掉某一个词（#138 实测：成稿写得很顺，却因缺
    「为啥」和收束语被机检整稿退回）。所以这里在**骨架层**把词槽钉死：
    追问给第二个家长槽、自洽给收束前的最后一个孩子槽、愣住给收束槽。
    """
    if str(structure_type or "").strip().upper() != "N" or len(slots) < 4:
        return slots
    # 只管契约拍（非插话槽）：插话槽在填词阶段允许整句丢弃，词钉在它上面
    # 等于「丢一句 → 词没落地 → 整稿判废」。#138 实测：第 11 句（插话槽）
    # 被判「必须出现指定词」，一句不合直接废掉整稿。
    contract_idx = [
        i for i, s in enumerate(slots) if not s.get("is_filler")
    ]
    if not contract_idx:
        return slots
    parent_idx = [
        i for i in contract_idx if slots[i]["speaker"] not in _KID_NAMES
    ]
    kid_idx = [i for i in contract_idx if slots[i]["speaker"] in _KID_NAMES]
    if not parent_idx or not kid_idx:
        return slots
    reqs: dict[int, str] = {}
    reqs[contract_idx[-1]] = "stun"
    if len(parent_idx) >= 2:
        reqs[parent_idx[1]] = "why"
    elif parent_idx:
        reqs[parent_idx[0]] = "why"
    # 自洽槽：收束前**最后一个承担剧情**的孩子槽（跳过插话槽与停顿拍——
    # 愣住拍里塞「因为」会把静场写成解释，插话槽里塞「所以」是空转）
    pause_re = re.compile(r"愣|接不上|没落下|认栽|服了|不响|沉默")
    before_close = [
        i
        for i in kid_idx
        if i < contract_idx[-1]
        and not pause_re.search(str(slots[i].get("intent") or ""))
    ]
    if before_close:
        reqs[before_close[-1]] = "reason"
    for i, key in reqs.items():
        words = _N_SLOT_WORD_REQS[key]
        slots[i] = dict(slots[i])
        slots[i]["must_words"] = list(words)
        slots[i]["function"] = (
            str(slots[i].get("function") or "")
            + f"；本句必须原样出现其中一个词：{'/'.join(words)}"
        )
    return slots


def _perbeat_lcs_len(a: str, b: str) -> int:
    """最长公共子串长度（只要长度，DP 一遍）。"""
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _perbeat_seed_is_new(
    text: str,
    beats: list[dict[str, Any]],
    punchline: str,
) -> bool:
    """seed 行是否带来**新内容**（不与任何契约拍/包袱重合 ≥5 字）。

    不过滤就会把包袱提前说一遍：seed 里「我妈妈像一个暴躁的老虎」和
    beat4 的 intent 几乎逐字相同，被当插话槽内容用掉后，第 4 拍再说一次，
    终检立刻判「重复」+「包袱说了两遍」。
    """
    clean = re.sub(r"[^\u4e00-\u9fff]", "", str(text or ""))
    if len(clean) < 6:
        return False
    refs = [re.sub(r"[^\u4e00-\u9fff]", "", str(b.get("intent") or "")) for b in beats]
    refs.append(re.sub(r"[^\u4e00-\u9fff]", "", str(punchline or "")))
    for ref in refs:
        if not ref:
            continue
        if _perbeat_lcs_len(clean, ref) >= 5:
            return False
    return True


_PERBEAT_STOP_TERMS = frozenset(
    """
    我们 你们 他们 这个 那个 什么 怎么 就是 还是 可是 但是 因为 所以
    如果 已经 一样 一个 一句 一下 不是 没有 可以 觉得 知道 时候 现在
    这样 那样 出来 起来 上来 下来 一点 有点 真是 什么 这儿 那儿
    """.split()
)


def _perbeat_terms(text: str) -> set[str]:
    """二字词集合（去标点，去掉高频虚词组合）。"""
    clean = re.sub(r"[^\u4e00-\u9fff]", "", str(text or ""))
    out: set[str] = set()
    for i in range(len(clean) - 1):
        term = clean[i : i + 2]
        if term in _PERBEAT_STOP_TERMS:
            continue
        out.add(term)
    return out


def _perbeat_seed_premise_ok(
    text: str,
    beats: list[dict[str, Any]],
    beat_id: int,
) -> bool:
    """seed 行提到的概念，必须在**已发生的拍**里出现过。

    否则前文还没铺垫就先说了（#138 实测：插话槽用了 seed 的
    「所以还是老虎更贴切，公主是装的」，而妈妈要到第 5 拍才提出公主，
    终检立刻判「缺前提」）。
    """
    heard: set[str] = set()
    for i, b in enumerate(beats, 1):
        if i <= beat_id:
            heard |= _perbeat_terms(str(b.get("intent") or ""))
    future: set[str] = set()
    for i, b in enumerate(beats, 1):
        if i > beat_id:
            future |= _perbeat_terms(str(b.get("intent") or ""))
    terms = _perbeat_terms(text)
    # 只在「后续拍独有」的概念上判定：前文已提过的不算提前泄露
    return not (terms & (future - heard))


def _perbeat_seed_queues(
    seed: list[Any] | None,
    *,
    beats: list[dict[str, Any]] | None = None,
    punchline: str = "",
) -> dict[str, list[str]]:
    """按说话人把 dialogue_seed 摊成素材队列（插话槽的正经内容来源）。

    早期实现让插话槽「照搬上一句的一个词」来证明咬合，结果生成器把咬合
    当成本职工作，写出「你替我吃这盘饺子/老虎爪子别烫着」四连乒乓
    （#138 实测：14 句里 4 句是互相复读，终检判换词重复，重抽到 16 句
    又判接不上）。seed 里的每一行都是真实素材（「真有那么邪乎？我可不敢
    下嘴」「妈你先别气，他这比喻我接不住」），拿它当插话槽的 intent，
    既保住咬合，又带进新内容。
    """
    out: dict[str, list[str]] = {}
    for item in seed or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("intent") or item.get("line") or "").strip()
        if not sp or not text:
            continue
        if len(text) > 40:
            text = text[:40]
        # seed 与契约拍常是同一段素材的不同摘录：已经被某条契约拍覆盖的，
        # 不能再拿来当插话，否则插话会「顶替契约拍」被机检判废（#138 实测：
        # 「不过我妈妈倒是眉清目秀的」反复占插话槽，三轮都过不了）。
        if any(
            str(b.get("speaker") or "").strip() == sp
            and _line_fulfills_beat(sp, text, b)
            for b in (beats or [])
            if isinstance(b, dict)
        ):
            continue
        if not _perbeat_seed_is_new(text, list(beats or []), punchline):
            continue
        out.setdefault(sp, []).append(text)
    return out


# 零素材插话槽的「功能」池（#144 专家评审）：
#   旁观角色（如只有一句旁白的姐姐）本来没有素材，默认那句「接住上一句里最具体
#   的那半句 + 给理由」会被模型解成**复述上一句**——实测三轮整表重掷都在换词照抄
#   （「说想自己弄干净，不让妈妈操心」→「她想自己弄干净，不让妈妈操心」）。
#   改成封闭的交互功能：只做旁观/递话/助威，不陈述事实、不给理由，也不许用「我」
#   认领别人的事。有素材的插话槽仍走 seed，不受影响。
_PERBEAT_FILLER_FUNCTIONS = (
    (
        "旁观（安抚当事人）",
        "只做旁观安抚：让上一句的说话人先别急、慢慢说、把话说完；"
        "你是旁边看着的人，不许把上一句讲的事再说一遍，"
        "也不许用「我」说别人做过/想过/委屈的事",
    ),
    (
        "递话（把话交回当事人）",
        "只做递话：把话交回上一句的说话人，让他把话说明白、说下去；"
        "不许重复上一句的内容，也不许用「我」说别人做过/想过/委屈的事",
    ),
    (
        "助威（明说自己站谁这边）",
        "只给当场一句助威/帮腔：明说你站在谁那边、让他慢慢说；"
        "不许重复上一句的内容，也不许用「我」说别人做过/想过/委屈的事",
    ),
)


def _filler_function_pair(ordinal: int) -> tuple[str, str]:
    """按槽序取一对（本句功能标签，功能 intent）。"""
    return _PERBEAT_FILLER_FUNCTIONS[ordinal % len(_PERBEAT_FILLER_FUNCTIONS)]


def _perbeat_slots(
    beat_chain: list[Any],
    scene_contract: dict[str, Any],
    *,
    target_lines: int,
    seed: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """把 beat_chain 摊成「一句一个槽」的填词骨架。

    句数来源按优先级：

    1. 每拍至少一槽，说话人 = 契约里的 speaker（说话人从结构上锁死）；
    2. 契约 ``min_turns≥2`` 的拍再补一槽给**另一个孩子**（家长额度封顶，
       第二槽不能给家长），这类槽只做「接住上一句」的反应，不推进剧情；
    3. 仍不足 ``target_lines`` 时，在「不相邻同人、不在停顿/收束拍之后」的位置
       给句数最少的那个孩子补插话槽（N 类正文 ≥12 句是硬卡）。

    停顿拍（愣住/接不上/举着筷子没落下）本身就是静场，后面不加塞。
    """
    beats = [b for b in (beat_chain or []) if isinstance(b, dict)]
    if not beats:
        return []
    kids = [k for k in _KID_NAMES if k in (scene_contract.get("characters") or [])]
    pause_re = re.compile(r"愣|接不上|没落下|认栽|服了|不响|沉默")
    # 核心孩子（契约拍多的那个）可以多说几句，搭档按专家口径封在 5 句内：
    # 两个人都按 5 句封死时，骨架刚够 13 句，凑不到「每句 21 字 × 14 句」的
    # 字数下限，只能靠垫字池子句补——那比少一句更糟。
    # 现场关键词：插话槽必须提到其中一个（饺子/老虎/餐桌…）。
    # 早期是「照搬上一句一个词」，结果生成器把照搬当任务，写出
    # 「你替我吃/老虎爪子别烫着」四连乒乓（#138 实测）。改成「提到现场
    # 某个东西」即可，复读由 _perbeat_is_dup 挡。
    topic_terms: set[str] = set()
    for _src in (
        str(scene_contract.get("object") or ""),
        str(scene_contract.get("location") or ""),
        " ".join(str(b.get("intent") or "") for b in beats),
    ):
        topic_terms |= {t for t in _perbeat_terms(_src) if len(t) == 2}

    seed_queue = _perbeat_seed_queues(
        seed,
        beats=beats,
        punchline=str(scene_contract.get("punchline") or ""),
    )
    seed_used: set[str] = set()

    def _filler_intent(
        beat: dict[str, Any],
        ordinal: int,
        default: str,
        speaker: str,
    ) -> str:
        """同一拍后的两条插话分工：第一条接批评/比喻，第二条接夸奖/换依据。"""
        intent = str(beat.get("intent") or "")
        beat_speaker = str(beat.get("speaker") or "").strip()
        has_negative = bool(re.search(r"难吃|难喝|太苦|太咸|太贵|太吵", intent))
        has_positive = bool(re.search(r"眉清目秀|好看|漂亮|俊|清秀", intent))
        if has_negative and has_positive:
            if ordinal == 1:
                return (
                    "直接对上一句的孩子说话：你一边嫌饺子难吃、一边夸妈妈，"
                    "这嘴变得也太快了；用陈述句表达你的态度，不要提问，"
                    "不要另补外貌或身体细节"
                )
            if ordinal == 2 and speaker == beat_speaker:
                return (
                    "上一句在挑你「嫌难吃还夸妈妈」的矛盾；先回应对方的挑刺，"
                    "再说自己夸妈妈是真心的，别把难吃和高兴扯成一件事；"
                    "用陈述句，不复述夸奖原话，不要提问"
                )
            if ordinal == 2:
                return (
                    "上一句已经接过批评；这一句不要再夸外貌，"
                    "改说这两个孩子一个嫌饺子、一个替妈妈高兴，听着就不像同一桌话；"
                    "用陈述句，不要提问"
                )
        if re.search(r"老虎|狮子|豹子", intent) and re.search(r"暴躁|凶", intent):
            if ordinal == 2 and speaker == beat_speaker:
                return (
                    "上一句在挑你「这不是夸」；直接回应对方，坚持自己的老虎判断，"
                    "补一个当场、能听懂的理由；用陈述句，"
                    "不许自述筷子/表情等动作旁白，不要重复上一句"
                )
            if ordinal == 1:
                return (
                    "直接对上一句的孩子说话：这不是夸，是拐着弯说妈妈凶；"
                    "用陈述句，不要拿问饺子/包饺子作反证，不要提问"
                )
            if ordinal == 2:
                return (
                    "上一句已经点出这是在拐弯说妈妈凶；换一个当场理由，"
                    "说明你为什么不同意这个比喻；用陈述句，不要提问"
                )
        return default

    def _seed_intent(speaker: str, beat_id: int) -> str:
        for text in seed_queue.get(speaker) or []:
            if text in seed_used:
                continue
            if not _perbeat_seed_premise_ok(text, beats, beat_id):
                continue  # 留给更靠后的槽，别在这里提前说
            seed_used.add(text)
            return text
        return ""

    _beat_spk = [str(b.get("speaker") or "").strip() for b in beats]
    # 逐拍开关对所有类型生效（A–N），角色表里不一定有「昭昭/灿灿」这两个名字；
    # 没有孩子角色时只按契约拍铺槽、不做插话补槽，max([]) 会直接抛 ValueError。
    core = (
        max(kids, key=lambda k: (_beat_spk.count(k), -kids.index(k)))
        if kids
        else ""
    )
    total_cap = {k: (7 if k == core else 5) for k in kids}
    # 每个孩子最多 4 条插话：契约拍 + 插话不超过 total_cap，
    # 同时给「坏句被机检丢掉」留出一槽缓冲（#138 实测：partner 只给 3 槽时
    # 只要有一条被判废就掉到 11 句，整条 draft 直接篇幅驳回）。
    filler_cap = {k: 4 for k in kids}
    count: dict[str, int] = {sp: 0 for sp in kids}
    filler_count: dict[str, int] = {sp: 0 for sp in kids}
    filler_round: dict[int, int] = {}
    filler_total = 0
    slots: list[dict[str, Any]] = []
    last = ""
    for i, b in enumerate(beats, 1):
        speaker = str(b.get("speaker") or "").strip()
        slots.append(
            {
                "beat_id": i,
                "speaker": speaker,
                "intent": str(b.get("intent") or "").strip(),
                "function": "推进",
                "is_filler": False,
            }
        )
        if speaker in count:
            count[speaker] += 1
        last = speaker
        try:
            turns = int(b.get("min_turns") or 1)
        except (TypeError, ValueError):
            turns = 1
        if len(kids) < 2 or turns < 2 or pause_re.search(str(b.get("intent") or "")):
            continue
        # 家长问句拍后面紧跟的必须是孩子的回答（问答相邻）：往中间塞插话槽，
        # 回答就被推到两三句之后，终检必判「答非所问」（#138 实测第 9 句）。
        if speaker not in _KID_NAMES:
            continue
        nxt = ""
        if i < len(beats):
            nxt = str(beats[i].get("speaker") or "").strip()
        cands = [
            k
            for k in kids
            if k != last
            and k != nxt
            and count.get(k, 0) < total_cap[k]
            and filler_count.get(k, 0) < min(2, filler_cap[k])
        ]
        if not cands:
            continue
        pick = min(cands, key=lambda k: (count.get(k, 0), kids.index(k)))
        _seed_txt = _seed_intent(pick, i)
        _ordinal = filler_round.get(i, 0) + 1
        filler_round[i] = _ordinal
        # 无素材的插话槽走「功能」而不是「内容」（#144 专家评审）。
        _default_function, _default_intent = _filler_function_pair(filler_total)
        slots.append(
            {
                "beat_id": i,
                "speaker": pick,
                "intent": _seed_txt
                or _filler_intent(b, _ordinal, _default_intent, pick),
                "function": (
                    "把这条素材改写成一句现场口语（18–24 字），"
                    "保留其中的具体物件与说法，不要换话题"
                    if _seed_txt
                    else _default_function
                ),
                "is_filler": True,
                "has_content": bool(_seed_txt),
                "topic_terms": sorted(topic_terms) if not _seed_txt else [],
            }
        )
        filler_total += 1
        filler_count[pick] = filler_count.get(pick, 0) + 1
        count[pick] = count.get(pick, 0) + 1
        last = pick
    if len(slots) > target_lines:
        # 超长时先摘中段的插话槽（结构拍和收束拍一个都不能少）
        idx = 1
        while len(slots) > target_lines and idx < len(slots) - 1:
            if slots[idx].get("is_filler"):
                slots.pop(idx)
                continue
            idx += 1
    if len(slots) >= target_lines or len(kids) < 2:
        return slots

    # 契约是否带 speech_act 标注：只有标注过的链才分得清「旁观拍」与「冲突拍」，
    # 没标注的旧契约不能按这条拦（否则一句补位都插不进去）。
    _annotated_chain = any(
        str(b.get("speech_act") or "").strip() for b in beats
    )

    def _gap_ok(i: int) -> bool:
        """能否在第 i 槽与第 i+1 槽之间加插话槽。"""
        if i < 0 or i + 1 >= len(slots):
            return False
        prev_sp = slots[i]["speaker"]
        nxt_sp = slots[i + 1]["speaker"]
        if prev_sp not in _KID_NAMES and nxt_sp in _KID_NAMES:
            return False  # 家长问 → 孩子答，不许拆
        if pause_re.search(str(slots[i].get("intent") or "")):
            return False  # 停顿拍是静场，后面不加塞
        # 旁观拍（契约里没有 speech_act 的纯围观句）后面不再加塞：旁观者刚
        # 说完，紧跟的补位只能复述上一句或把话轮拧反（#144 run28/29 实测：
        # 灿灿劝「你慢慢说」，下一句昭昭却「姐姐，你慢慢说，我在旁边听着」，
        # 终检判说话主体对调）。
        _b_idx = int(slots[i].get("beat_id") or 0) - 1
        if (
            _annotated_chain
            and 0 <= _b_idx < len(beats)
            and not str(beats[_b_idx].get("speech_act") or "").strip()
        ):
            return False
        # 连续插话最多两句（再多就是同一段里连甩反应，读着像卡带）。
        # 不能只数右边的 run：在两条插话之间插入会绕过上限，
        # #138 实测曾堆出 4 连插话，随后被判「同一反驳反复说」。
        left_run = 0
        j = i
        while j >= 0 and slots[j].get("is_filler"):
            left_run += 1
            j -= 1
        right_run = 0
        j = i + 1
        while j < len(slots) and slots[j].get("is_filler"):
            right_run += 1
            j += 1
        return left_run + 1 + right_run <= 3

    # 轮流往每个可用的空档里各加一句（不把插话全堆在一个空档）
    _guard = 0
    while len(slots) < target_lines and _guard < 40:
        _guard += 1
        placed = False
        for idx in range(len(slots) - 2, -1, -1):
            if len(slots) >= target_lines:
                break
            if not _gap_ok(idx):
                continue
            cands = [
                k
                for k in kids
                if k != slots[idx]["speaker"]
                and k != slots[idx + 1]["speaker"]
                and count.get(k, 0) < total_cap[k]
                and filler_count.get(k, 0) < filler_cap[k]
            ]
            if not cands:
                continue
            pick = min(cands, key=lambda k: (filler_count.get(k, 0), count.get(k, 0)))
            _seed_txt2 = _seed_intent(pick, slots[idx]["beat_id"])
            _b_id = int(slots[idx]["beat_id"])
            _ordinal2 = filler_round.get(_b_id, 0) + 1
            filler_round[_b_id] = _ordinal2
            _beat = beats[_b_id - 1] if 1 <= _b_id <= len(beats) else {}
            _default_function2, _default_intent2 = _filler_function_pair(
                filler_total
            )
            slots.insert(
                idx + 1,
                {
                    "beat_id": slots[idx]["beat_id"],
                    "speaker": pick,
                    "intent": _seed_txt2
                    or _filler_intent(_beat, _ordinal2, _default_intent2, pick),
                    "function": (
                        "把这条素材改写成一句现场口语（18–24 字），"
                        "保留其中的具体物件与说法，不要换话题"
                        if _seed_txt2
                        else _default_function2
                    ),
                    "is_filler": True,
                    "has_content": bool(_seed_txt2),
                    "topic_terms": sorted(topic_terms) if not _seed_txt2 else [],
                },
            )
            filler_total += 1
            filler_count[pick] = filler_count.get(pick, 0) + 1
            count[pick] = count.get(pick, 0) + 1
            placed = True
        if not placed:
            break
    return slots


def _perbeat_anchor_ok(line: str, prev_line: str, *, required: bool) -> bool:
    """插话槽必须照搬上一句里的一个具体词（接住话头的最小机械证据）。

    终检「接不上」几乎都长这样：插话者另起一件事（书包、彩笔、排骨汤），
    和上一句毫无字面交集。要求共享一个二字词不是语言理解，只是把
    「另起一件事」挡在生成这一步，省掉后面两轮语义返工。
    """
    if not required or not prev_line:
        return True
    prev = str(prev_line or "")
    text = str(line or "")
    for i in range(len(prev) - 1):
        frag = prev[i : i + 2]
        if not re.fullmatch(r"[\u4e00-\u9fff]{2}", frag):
            continue
        if frag in text and not _ANCHOR_STOP_RE.match(frag):
            return True
    return False


_ANCHOR_STOP_RE = re.compile(
    r"^(?:我是|你|我|的|了|吧|吗|呢|啊|就|还|不|说|这|那|也|都|要|会|能|把|被|和|跟|给|在)"
)


_NARRATION_HEAD_RE = re.compile(
    r"^我(?:夹起|夹了|咬开|咬了|汤勺|筷子|把|端|推|放下|愣|看|闻|尝)"
)


def _perbeat_norm(text: str) -> str:
    """去标点/称呼，用于判「换个人称把上一句再说一遍」。"""
    out = re.sub(r"[^\u4e00-\u9fff]", "", str(text or ""))
    for name in (*_KID_NAMES, "妈妈", "爸爸"):
        out = out.replace(name, "")
    return out


def _perbeat_term_ratio(a: str, b: str) -> float:
    """两句的二字词重合率（交集 / 较小集合）。"""
    ta, tb = _perbeat_terms(a), _perbeat_terms(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _perbeat_story_terms(
    lines: list[tuple[str, str]],
    *,
    df_cap: int = 3,
) -> set[str]:
    """全篇反复出现的词（饺子/黑面/芯子/眉清目秀…）不算「复述」证据。

    整篇都在说同一盘东西时，任何两句的二字词重合率都很高（实测 0.44–0.79），
    用原始重合率判「换词重复」会把每一句都判死，生成器只能退兜底句，
    结果句句答非所问。只保留「少数句才提到」的词做重合判定，
    这样「老虎」这种全篇反复讲的比喻仍能挡，而「苦得发涩」这类新细节不算重复。
    """
    df: dict[str, int] = {}
    for _sp, ln in lines:
        for term in _perbeat_terms(ln):
            df[term] = df.get(term, 0) + 1
    return {t for t, n in df.items() if n >= df_cap}


def _perbeat_carries_prev(
    line: str,
    earlier: list[tuple[str, str]],
) -> bool:
    """反应/插话句必须接住上一句的**独有**说法（不是全篇都在说的东西）。

    只要求「提到现场某个词」时，模型会用「饺子/妈妈」这类全篇高频词糊过去，
    写出一句结构上咬合、语义上答非所问的话（#138 实测：终检反复判
    「第3句·接不上：只是把上一句复述一遍/另起一件事」）。这里要求
    共用至少一个「少数句才提到」的具体词（那个味道、那个动作、那个判断）。
    """
    if not earlier:
        return True
    common = _perbeat_story_terms(earlier)
    prev_terms = _perbeat_terms(earlier[-1][1]) - common
    if not prev_terms:
        return True
    return bool(_perbeat_terms(line) & prev_terms)


def _perbeat_restates(
    line: str,
    earlier: list[tuple[str, str]],
    *,
    limit: float = 0.62,
) -> bool:
    """是否把前面某句「换个说法再说一遍」。

    `_perbeat_is_dup` 只抓字面重合；模型换个词重述同一件事时（「你一发火
    就像只暴躁老虎」/「可你一发火像暴躁老虎，平时倒还算眉清目秀」）字面
    只有六成相似，但二字词几乎全重合。终检会判「换词重复」并扣结构分，
    所以生成端就要挡。
    """
    if _perbeat_is_dup(line, earlier):
        return True
    if len(earlier) < 2:
        return False
    common = _perbeat_story_terms(earlier)
    cur_terms = _perbeat_terms(line) - common
    if len(cur_terms) < 3:
        # 这一句只有「全篇高频词」（又是一个说老虎/饺子的句子）
        return True
    for _sp, prev in earlier[-4:]:
        prev_terms = _perbeat_terms(prev) - common
        if len(prev_terms) < 2:
            continue
        ratio = len(cur_terms & prev_terms) / min(len(cur_terms), len(prev_terms))
        if ratio >= limit:
            return True
    return False


def _perbeat_repeats_long_phrase(
    line: str,
    earlier: list[tuple[str, str]],
    *,
    min_len: int = 5,
) -> bool:
    """插话是否把前文一个五字以上的具体说法原样再说一遍。

    二字词重合率会被句长和分词稀释：#138 实测第 2/4 句都在反复说
    「眉清目秀」，重合率只有 0.33，没被 ``_perbeat_restates`` 拦住，
    终检却判「同一夸赞换词重复两遍」。插话是可选句，原样复读具体短语
    没有新增信息，直接在生成端挡掉。
    """
    cur = re.sub(r"[^\u4e00-\u9fff]", "", str(line or ""))
    if len(cur) < min_len:
        return False
    for _speaker, prev in earlier:
        base = re.sub(r"[^\u4e00-\u9fff]", "", str(prev or ""))
        if len(base) < min_len:
            continue
        if _perbeat_lcs_len(cur, base) >= min_len:
            return True
    return False


# 插话句里表示「旁观/帮助」的框架词：带这些框架时，第一人称是在做旁观者的事
# （看/听/劝/帮/替/递话），不是把拍主的经历说成自己的（#144 专家评审）。
_PERBEAT_FILLER_HELPER_FRAME_RE = re.compile(
    r"帮|替|陪|给|为|听|看|见|说|问|劝|提醒|作证|保密|递"
)

# 第一人称认领「经历/委屈/动机」的说法：旁观者说这些就是把拍主的事认到自己身上。
# 「我」和认领词之间不许夹旁观框架词，否则「我帮你弄干净」这种帮忙句会被误杀。
_PERBEAT_FILLER_SELF_CLAIM_RE = re.compile(
    r"(?:我|咱)(?:(?![帮替陪给为听见说问劝递])[^，。！？；]){0,4}"
    r"(?:被骂|挨骂|挨说|被说|委屈|没错|做错|不该|冤枉|受气|弄脏|弄了|弄干净|去弄|来弄)"
)

# 否定/转指他人的写法不算认领：「我没说你委屈」「我不觉得你错了」要放过。
_PERBEAT_FILLER_SELF_DENY_RE = re.compile(
    r"(?:我|咱)[^，。！？；]{0,3}(?:没|不)(?:觉得|认为|说|怪|怨|觉)"
)


# 零素材插话槽的「松版咬合」（#144 专家评审）：这类槽没有素材，不要求它与
# 上一句共享实词，只要求它确实在做旁观/递话/助威（带旁观、递话、安抚词）。
_PERBEAT_FILLER_SOFT_LINK_RE = re.compile(
    r"别急|别气|别难过|别往心里|慢慢|听着|我在|我在这儿|旁边|看着|帮你|陪你|"
    r"听你|说吧|接着说|说下去|说清楚|说完|先听|喘口气|消消气|别忙|我来|你先"
)


def _perbeat_adjacent_repeat(
    line: str,
    prev_line: str,
    *,
    min_len: int = 5,
    min_cover: float = 0.35,
) -> bool:
    """插话是否照抄**紧邻上一句**（整句或长片段）。

    插话必须接住上一句的具体说法（共享一两个词是要求），但照抄一整段不是「接住」。
    #144 实测：第 10 句与第 9 句逐字相同、第 7 句照抄第 6 句 14 字，终检只判得出
    「错位」，重掷六轮仍复现。判据只比紧邻上一句，避免和「必须接住上一句」叠加成
    互斥规则（专家评审：共享一两词是要求，抄一整段不是）。
    """
    cur = re.sub(r"[^\u4e00-\u9fff]", "", str(line or ""))
    base = re.sub(r"[^\u4e00-\u9fff]", "", str(prev_line or ""))
    if len(cur) < min_len or len(base) < min_len:
        return False
    lcs = _perbeat_lcs_len(cur, base)
    return lcs >= min_len and lcs / min(len(cur), len(base)) >= min_cover


def _perbeat_filler_claims_owner_event(
    line: str,
    slot: dict[str, Any],
    prev_lines: list[tuple[str, str]],
) -> bool:
    """插话是否用第一人称认领本拍拍主的事实/动机/委屈/动作。

    专家评审把「第一人称立场标记 + 拍主不同」改写成「第一人称 + 本拍事件归属」：
    旁观者说「反正我没错，你不该那样说我」是把拍主的委屈认到自己身上；而
    「我帮你拿抹布」「我没说你委屈」是在帮忙/安抚，必须放过。
    """
    text = str(line or "")
    if not text or not re.search(r"我|咱", text):
        return False
    beat_id = int(slot.get("beat_id") or 0)
    owner = next(
        (e for no, e in (slot.get("_beat_entries") or []) if no == beat_id),
        None,
    )
    if not isinstance(owner, dict):
        return False
    if str(owner.get("speaker") or "").strip() == str(
        slot.get("speaker") or ""
    ).strip():
        # 拍主自己说自己的事，不算认领。
        return False
    if _PERBEAT_FILLER_SELF_CLAIM_RE.search(text):
        # 明说「我被骂/我委屈/我没错/我弄脏了」就是认领；带否定或转指他人的放过。
        return not _PERBEAT_FILLER_SELF_DENY_RE.search(text)
    if _PERBEAT_FILLER_HELPER_FRAME_RE.search(text):
        # 帮忙/旁观框架（我帮你拿、我看着、我说你听）不是认领。
        return False
    owner_terms: set[str] = set()
    for src in (
        slot.get("intent"),
        owner.get("intent"),
        prev_lines[-1][1] if prev_lines else "",
    ):
        owner_terms |= _perbeat_terms(str(src or ""))
    return len(_perbeat_terms(text) & owner_terms) >= 2


# 封闭功能模板池（#144 专家评审的「安全模板补位」）：旁观角色写不出内容时的
# 兜底句。要求：14–24 字、只做旁观/递话、不含上一句的事实谓宾、不含新物件、
# 与上一句连续相同字 <5；用之前一律过 `_perbeat_check`，不过就不用。
_PERBEAT_FILLER_TEMPLATES = (
    # 安抚（当事人说这句最安全：不认领别人的事，也不改话轮）
    "{to}，你先别急，我就在旁边听着，你慢慢说。",
    "{to}，你慢慢说，我不插嘴，就在旁边听着。",
    "你先别急，我就在旁边听着，慢慢说。",
)

# 纯围观者的补位句：只说自己看见的现场，不递话、不评理。
# 「你先说」「谁也别让我评理」这类会改话轮/凭空加前提（#144 run28 实测：
# 前者被判「灿灿已经说完了，昭昭却让她先说」，后者被判「没人让她评理」）。
_PERBEAT_WITNESS_FILLER_TEMPLATES = (
    "{to}，我在旁边看着呢，你俩谁也没让过谁。",
    "我在旁边看着都替你们累，先歇会儿再吵。",
    "{to}，我在旁边听着，这嗓门可不小。",
    "{to}，我在旁边看着，你俩这火气可不小。",
)


def _perbeat_rewrite_filler_slot(
    slot: dict[str, Any],
    *,
    scene_contract: dict[str, Any],
    prev_lines: list[tuple[str, str]],
    reason: str,
    temperature: float,
) -> str:
    """定向重写一个插话槽（只写这一句，不整表重掷）。"""
    from app.services.gold_story.gold_chat.prompts import (
        PERBEAT_FILLER_REWRITE_SYSTEM,
        format_perbeat_filler_rewrite_user,
    )

    user = format_perbeat_filler_rewrite_user(
        speaker=str(slot.get("speaker") or ""),
        intent=str(slot.get("intent") or ""),
        function=str(slot.get("function") or "反应/插话"),
        prev_lines=prev_lines,
        reason=reason,
        scene_contract=scene_contract,
        party=not _perbeat_filler_is_witness(slot),
    )
    data = _chat_json(
        PERBEAT_FILLER_REWRITE_SYSTEM,
        user,
        temperature=temperature,
        max_tokens=200,
    )
    return _perbeat_strip_stage_direction(str(data.get("line") or "")).strip()


def _perbeat_parties(slot: dict[str, Any]) -> set[str]:
    """契约拍里的**冲突当事人**（有 speech_act 的拍主）。

    只按「说过话」算会把纯围观角色（#144 的灿灿，只有一句「你慢慢说」、
    没有 speech_act）也算成当事人，于是当事人补位句劝她「别急」就不再被拦
    （#144 run34 第 4 句实测）。链上一条 speech_act 都没有的老契约退回旧口径。
    """
    entries = [
        entry
        for _no, entry in (slot.get("_beat_entries") or [])
        if isinstance(entry, dict)
    ]
    annotated = [
        entry
        for entry in entries
        if str(entry.get("speech_act") or "").strip()
    ]
    parties = {
        str(entry.get("speaker") or "").strip()
        for entry in (annotated or entries)
    }
    parties.discard("")
    return parties


def _perbeat_filler_is_witness(slot: dict[str, Any]) -> bool:
    """补位句说话人是不是纯围观者（不在任何契约拍里说话）。

    昭昭/妈妈是当事人：让当事人说「我在旁边看着」是错位（#144 run28 实测：
    昭昭的补位句被判「说话人和被劝对象整体对调」、立场自相矛盾）。
    """
    speaker = str(slot.get("speaker") or "").strip()
    if not speaker:
        return False
    parties = _perbeat_parties(slot)
    if not parties:
        return True
    return speaker not in parties


_PARTY_FILLER_INTENT = (
    "当事人在场反应：只回一句态度/情绪或顶一句，接着把冲突往下推；"
    "不许劝对方别急/慢慢说，也不许提前交代后面自己那拍的事实"
)


def _perbeat_party_filler_intent(intent: str) -> str:
    """当事人补位句的意图：把「旁观/安抚/递话」那套换成当事人反应。"""
    text = str(intent or "").strip()
    if re.search(r"旁观|安抚|递话|助威|和事佬", text):
        return _PARTY_FILLER_INTENT
    if "当事人" in text:
        return text
    return f"{text}（说话人是当事人：只回一句态度或顶一句，不许劝对方别急，也不许提前说掉后面自己那拍的事实）"


def _perbeat_filler_template(
    slot: dict[str, Any],
    prev_lines: list[tuple[str, str]],
) -> str:
    """从封闭功能模板池里取补位句：过机检，且与其它已写台词重复最少。

    以前取「池子里第一条过检的」，于是同一个池子里全是「你先别急/慢慢说」，
    三句补位长成一个样（#144 run27 第 3/7 句实测：换词复述，终检判重复）。
    现在按「叫上对方 → 咬住上一句 → 与已写台词重复最少」挑；纯围观者优先
    用见证句，当事人只用安抚句。
    """
    speaker = str(slot.get("speaker") or "").strip()
    prev_speaker = str(prev_lines[-1][0]).strip() if prev_lines else ""
    to = prev_speaker if prev_speaker and prev_speaker != speaker else ""
    seen = {str(ln or "").strip() for _sp, ln in prev_lines}
    pool = list(_PERBEAT_FILLER_TEMPLATES)
    if _perbeat_filler_is_witness(slot):
        pool = list(_PERBEAT_WITNESS_FILLER_TEMPLATES) + pool
    prev_terms = _perbeat_terms(prev_lines[-1][1]) if prev_lines else set()
    earlier_terms = [_perbeat_terms(txt) for _sp, txt in prev_lines[:-1]]
    best = ""
    best_key: tuple[int, int, int] | None = None
    for tpl in pool:
        if "{to}" in tpl and not to:
            continue
        line = tpl.format(to=to).strip()
        if line in seen:
            continue
        if _perbeat_check(slot, line, prev_lines):
            continue
        terms = _perbeat_terms(line)
        # 先要能叫上对方（旁观者开口先指人最自然），再要咬住上一句的实词，
        # 最后比谁跟前面其它句子重复最少。
        addressed = 1 if to and line.startswith(to) else 0
        anchor = len(terms & prev_terms)
        overlap = max(
            (len(terms & earlier) for earlier in earlier_terms),
            default=0,
        )
        key = (addressed, anchor, -overlap)
        if best_key is None or key > best_key:
            best, best_key = line, key
    return best


def _perbeat_replace_bad_fillers(
    slots: list[dict[str, Any]],
    filled: dict[int, str],
    failures: list[tuple[int, str, str]],
    *,
    scene_contract: dict[str, Any],
    temperature: float,
) -> dict[int, tuple[str, str]]:
    """插话槽判废后的本地替换链（#144 专家评审第 5 条）。

    判废就丢句会让 12 句掉到 10 句、整稿直接「对白句数须≥12」篇幅驳回（实测
    三轮都卡在这里）；而整表重掷必然复现同一批插话缺陷（模型只是换词照抄）。
    所以先定向重写这一句（≤2 次），再退到封闭功能模板；都拿不到才丢句。
    返回 {槽号: (新句子, 来源)}，来源是 rewrite/template。
    """
    bad_idx = {i for i, _ln, _why in failures}
    fixed: dict[int, tuple[str, str]] = {}
    for i, _ln, why in failures:
        if not (1 <= i <= len(slots)) or not slots[i - 1].get("is_filler"):
            continue
        slot = slots[i - 1]
        prev_lines = [
            (
                str(slots[j - 1].get("speaker") or ""),
                str(fixed[j][0] if j in fixed else filled[j]),
            )
            for j in range(1, i)
            if j in fixed or (j in filled and j not in bad_idx)
        ]
        line = ""
        source = ""
        for attempt in range(2):
            try:
                cand = _perbeat_rewrite_filler_slot(
                    slot,
                    scene_contract=scene_contract,
                    prev_lines=prev_lines,
                    reason=why,
                    temperature=min(0.9, temperature + 0.3 * (attempt + 1)),
                )
            except Exception as exc:  # 网络/解析失败：直接退到模板池
                logger.info(
                    "[GOLD_CHAT] perbeat filler rewrite error slot=%s: %s",
                    i,
                    str(exc)[:80],
                )
                break
            if cand and not _perbeat_check(slot, cand, prev_lines):
                line, source = cand, "rewrite"
                break
        if not line:
            tpl = _perbeat_filler_template(slot, prev_lines)
            if tpl:
                line, source = tpl, "template"
        if line:
            fixed[i] = (line, source)
            logger.info(
                "[GOLD_CHAT] perbeat filler replaced slot=%s by=%s line=%s",
                i,
                source,
                line,
            )
    return fixed


def _perbeat_repair_repeated_filler(
    slot: dict[str, Any],
    line: str,
    earlier: list[tuple[str, str]],
) -> str:
    """把「换词复述夸奖」的插话改成有新立场的对比句。"""
    if not _perbeat_repeats_long_phrase(line, earlier):
        return line
    intent = str(slot.get("intent") or "")
    if not (
        "夸奖" in intent
        or "眉清目秀" in line
        or "好看" in line
        or "漂亮" in line
    ):
        return line
    prop = next(
        (
            term
            for term in _PERBEAT_PROP_TERMS
            if any(term in prev for _speaker, prev in earlier)
        ),
        "东西",
    )
    parent = "爸爸" if "爸爸" in intent else "妈妈"
    speaker = str(slot.get("speaker") or "").strip()
    if speaker in {"妈妈", "爸爸"}:
        return f"你嫌{prop}难吃，又把{parent}夸上天，我可不敢当真。"
    return f"我夸{parent}是真心的，不是嘴变快，你别冤枉我。"


def _perbeat_is_dup(line: str, earlier: list[tuple[str, str]]) -> bool:
    """与已写过的任何一句高度重合即判重复（含「换个称呼复述」）。"""
    from difflib import SequenceMatcher

    cur = _perbeat_norm(line)
    if len(cur) < 6:
        return False
    for _sp, prev in earlier:
        base = _perbeat_norm(prev)
        if not base:
            continue
        if cur in base or base in cur:
            return True
        if SequenceMatcher(None, cur, base).ratio() > 0.62:
            return True
    return False


# 半句检测：真正「没说完」的收尾是连词/介词/量词。**不收「的/了」**——
# 「…妈妈眉清目秀倒是真的。」「…我认了。」都是完整口语，
# 把它们判废会让模型反复重写仍不过（#138 实测：beat 2 三连 draft 全废）。
_PERBEAT_DANGLING_TAIL = (
    "把", "被", "和", "跟", "就", "还", "也", "都",
    "要是", "如果", "因为", "所以", "但是", "可是", "而且", "然后",
    "像", "这", "那", "个", "只", "张", "盘", "碗",
)


def _perbeat_sentence_ok(line: str) -> bool:
    """句子必须说完整：以句末标点收尾，且不落在虚词/量词上。

    生成器被长度限制逼急了会交半句（「你说妈妈像暴躁的老虎。」11 字、
    「暴躁的老虎要是真来抢这盘黑面饺子。」没有下文），读起来像串词。
    """
    text = str(line or "").strip()
    if not text:
        return False
    if not re.search(r"[。！？…!?]$", text):
        return False
    core = text.rstrip("。！？…!?")
    if len(core) < 10:
        return False
    return not core.endswith(_PERBEAT_DANGLING_TAIL)


# 「昭昭说老虎一吼……」= 替别人转述（第三人称报告腔），不是对话。
# 下游 `patch_dialogue_narration_to_speech` 会把它改成莫名其妙的短句
# （#138 实测：「昭昭说老虎一吼，妈妈你筷子举着半天都没落下」→「你别过来！」）。
_PERBEAT_LINK_INTENT_RE = re.compile(
    r"追问|狐疑|反诘|改口|认栽|接不住|愣住|质问|确认|不服"
)


_PERBEAT_QUESTION_RE = re.compile(
    r"[？?]|吗|呢|咋|怎么|为什么|为啥|啥|谁|多少|啥意思"
)

# 自述动作/道具（「我筷子倒先停在半空」）= 舞台说明，不是对白。
# 锚定在句首：句中出现的「苦得我舌根发麻」「我嘴都麻了」是正常口语，
# 一并拒掉会让模型反复重写仍判废（#138 实测：beat 2 三连 draft 都因此被
# 打成「长度须14–22字且是完整口语」，而真因是这条正则误伤了句中「我舌根」）。
_PERBEAT_SELF_NARRATION_RE = re.compile(
    r"^(?:我|我的|俺)(?:的)?(?:筷子|碗|勺|汤勺|手|舌头|舌根|脸|嗓子|嘴|眼睛)"
    # 「我举着筷子，实在接不上话」「我筷子都停在半空」：自述动作即舞台说明。
    r"|^(?:我|俺)[^，。；]{0,8}(?:筷子|碗|勺子|汤勺)"
)

# 「这盘饺子我夹着」「我举着……」：以物件起句也不能掩盖自述动作。
_PERBEAT_SELF_STATE_RE = re.compile(
    r"(?:我|俺)[^，。；]{0,10}(?:夹着|端着|拿着|举着|捧着|咬着|嚼着|咽着|盯着|停在|僵在)"
    r"|(?:筷子|碗|勺子|汤勺|杯子)[^，。；]{0,10}"
    r"(?:举着|停着|停在|僵着|僵在|悬着|没落下|不放|落不落|举不举)"
    # 「我看看妈妈手里的筷子落不落」= 把反应写成镜头说明。
    r"|(?:我|俺)[^，。；]{0,6}(?:看看|瞧瞧|望望)[^，。；]{0,10}"
    r"(?:妈妈|筷子|碗|手|脸)"
    # 「只能愣着看妈妈怎么回」= 把反应写成镜头说明。
    r"|(?:愣|呆|傻)着[^，。；]{0,6}(?:看|瞧|望|盯)"
)

# 「灿灿你问这黑面饺子皮。」= 把对方的问题复述一遍就算回答，实际没内容。
_PERBEAT_KID_NAMES = {"昭昭", "灿灿"}

# 「灿灿夹起…」「昭昭推了推…」= 用自己的名字给自己做旁白。
_PERBEAT_THIRD_PERSON_ACTION_RE = re.compile(
    r"^[，,]?(?:又|就|却|便|倒|也|还)?"
    r"(?:夹|咬|推|放|端|拿|站|坐|笑|瞪|皱|停|伸|转|低|抬|愣|看|闻|尝|喝|吃|"
    r"摇|点|叹|咽|把|跟|冲|扭|缩|撇|绷|盯)"
)

_PERBEAT_STUB_RE = re.compile(r"你(?:问|说)(?:的)?[^，。]{0,16}[。！？…]$")


_PERBEAT_REPORT_RE = re.compile(r"^(?:昭昭|灿灿|妈妈|爸爸)(?:说|讲|问|答|接|喊|嘀咕|小声说)")

# 「是我弄脏的，说想自己弄干净」：在分句里用「说想/说要」转述自己的话，
# 等于把心理说明念成台词（#144 run28/29 终检连续判旁白）。
_PERBEAT_SELF_REPORT_RE = re.compile(
    r"[，,；;](?:我|俺|自己)?(?:说|讲)(?:想|要|觉得|自己)"
)

# 解说「满桌人/全场/没人接话」= 替镜头描述现场反应，不是角色说的话（#138 实测
# 「所以满桌人半天没人接话，全被这句镇住了」被终检判旁白）。
_PERBEAT_CROWD_NARRATION_RE = re.compile(
    r"满桌人|满屋子人|全场|众人|大家(?:都|全)?(?:没|愣|安静)|"
    r"(?:半天|一时)?没人接话|没人吭声|没人说话|一片安静|鸦雀无声"
)


# 「我不同意。」只有立场、没有理由，推进靠硬插一句（#138 实测终检判
# 「凭空表态，没给任何理由」）。只拦「表态词后面再没有实义分句」这一种。
_PERBEAT_STANCE_RE = re.compile(r"(?:我|俺)?(?:同意|不同意|赞成|不赞成|信|不信)")

# 「你刚才也瞧见了吧」= 引用前文没有发生过的共同经历。
_PERBEAT_RECALL_RE = re.compile(
    r"(?:刚才|刚刚|上次|那天)[^，。；]{0,8}"
    r"(?:瞧见|看见|见到|听见|听到|见过)"
)

# 包袱里写了「公主…现出原形」，但公主不是老虎变的；改成「装公主也露馅」。
_PERBEAT_PRINCESS_FORM_RE = re.compile(r"公主[^，。；]{0,6}现出原形")

# 「这夸得挺对」「把好话收下」= 只附和/收下夸奖，没有新增理由或冲突。
_PERBEAT_EMPTY_AGREEMENT_RE = re.compile(
    r"(?:好话|夸奖|这话|夸得)[^，。；]{0,6}(?:收下|收着|认了|挺对|不错)"
    r"|(?:觉得|认为)?(?:这|那)?(?:夸|说)?(?:得|的)?(?:挺|太)?"
    r"(?:对|不错|有道理)(?:[。！？…!?]|$)"
)

# 「你说老虎发威吓人」= 给上一句编了一句没说过的话。引语必须真有出处。
_PERBEAT_QUOTE_RE = re.compile(r"^你(?:刚才|刚)?说([^，。；]{1,16})")

_PERBEAT_WHY_QUESTION_RE = re.compile(r"为什么|为啥|凭什么|怎么")


def _perbeat_stance_has_reason(line: str) -> bool:
    """表态句不能只写「我同意/不同意」，后面必须有理由分句。"""
    match = _PERBEAT_STANCE_RE.search(str(line or ""))
    if not match:
        return True
    tail = str(line or "")[match.end():].strip("。！？…!?，,；; ")
    return len(re.findall(r"[\u4e00-\u9fff]", tail)) >= 4


def _perbeat_recall_ok(line: str, prev_lines: list[tuple[str, str]]) -> bool:
    """插话引用「刚才」时，前文必须真发生过可被看见/听见的事件。"""
    if not _PERBEAT_RECALL_RE.search(str(line or "")):
        return True
    seen = "".join(ln for _sp, ln in prev_lines)
    return bool(
        re.search(
            r"发威|吼|吵|摔|哭|喊|打|骂|瞧见|看见|见到|听见|听到",
            seen,
        )
    )


def _perbeat_filler_move_ok(line: str, prev_lines: list[tuple[str, str]]) -> bool:
    """同一个表态动作（我同意/我不同意/我不信）全篇只做一次。"""
    text = str(line or "")
    if "不同意" in text:
        marker = "不同意"
    elif re.search(r"(?<!不)我同意", text):
        marker = "我同意"
    elif "我不信" in text:
        marker = "我不信"
    else:
        return True
    return not any(marker in prev for _sp, prev in prev_lines)


def _perbeat_quote_ok(line: str, prev_line: str) -> bool:
    """插话用「你说…」引述上一句时，引语必须能在上一句里找到。"""
    match = _PERBEAT_QUOTE_RE.match(str(line or ""))
    if not match or not prev_line:
        return True
    quote = match.group(1).strip()
    if len(quote) < 3:
        return True
    return _perbeat_lcs_len(quote, prev_line) >= min(4, len(quote))


def _perbeat_clip(line: str, limit: int = 22) -> str:
    """把超长句截到 limit 以内，优先在逗号处断，别把话截成半句。"""
    text = str(line or "").strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind("，"), head.rfind("；"), head.rfind("、"))
    if cut >= 8:
        head = head[:cut]
    head = head.rstrip("，；、 ")
    if not re.search(r"[。！？…!?]$", head):
        head += "。"
    return head


def _perbeat_line_shape_ok(line: str) -> bool:
    """长度与完整句门槛。"""
    text = str(line or "").strip()
    # 真硬卡是「单句 ≤24 字、均句 ≤22 字」（CHAT_MAX_LINE_CHARS /
    # CHAT_AVG_LINE_CHARS_MAX）。生成端把单句卡到 22 时模型几乎永远写不出
    # （#138 实测：三连 draft 全部只差长度、「…苦得我舌根发麻，妈妈眉清目秀
    # 倒是真的。」24 字），于是整条重掷耗尽。这里放到真硬卡 24，均句由
    # `_generate_perbeat_candidate` 里的均值收口保证（在验收前就截好，
    # 不会等到验过后再截掉剧情条件）。
    if not (14 <= len(text) <= 24):
        return False
    if not _perbeat_sentence_ok(text):
        return False
    return True


def _perbeat_speech_form_ok(line: str, speaker: str) -> bool:
    """必须是角色当场说出口的话，不能是旁白/动作说明/自我转述。"""
    text = str(line or "").strip()
    if _NARRATION_HEAD_RE.search(text):
        return False
    if _PERBEAT_REPORT_RE.search(text):
        return False
    if _PERBEAT_SELF_REPORT_RE.search(text):
        return False
    if _PERBEAT_SELF_NARRATION_RE.search(text):
        return False
    if _PERBEAT_SELF_STATE_RE.search(text):
        return False
    if _PERBEAT_STUB_RE.search(text):
        return False
    if PERBEAT_STAGE_DIRECTION_RE.search(text):
        return False
    if _PERBEAT_CROWD_NARRATION_RE.search(text):
        return False
    # 只禁「用自己的名字自称 + 说自己动作」（灿灿开头说「灿灿夹起饺子…」= 旁白腔）；
    # 名字出现在别处是正常口语：「昭昭，你尝尝」是称呼对方，「可妈妈你眉清目秀」
    # 是把妈妈当对象。早期版本一律 `speaker not in text`，结果「你今天为啥舍得夸
    # 妈妈眉清目秀，平时可没这待遇。」这种完全正常的句子被判废（#138 实测）。
    if speaker in _PERBEAT_KID_NAMES:
        # 孩子的名字只可能出现在自己的台词里当自我旁白（「灿灿看着都觉得不对劲」），
        # 别人要称呼他会用「昭昭/灿灿」开头（已被句首分支处理）。
        if speaker in text:
            return False
    if speaker and text.startswith(speaker):
        tail = text[len(speaker):]
        return not _PERBEAT_THIRD_PERSON_ACTION_RE.match(tail)
    return True


def _perbeat_line_ok(line: str, speaker: str) -> bool:
    return _perbeat_line_shape_ok(line) and _perbeat_speech_form_ok(line, speaker)


def _perbeat_strip_stage_direction(line: str) -> str:
    """模型偶尔仍把 intent 里的表演提示抄进台词；能无损剔除就先本地剔除。

    「我不是想讨好处，我一本正经说妈妈像只暴躁老虎。」去掉「我一本正经说」
    后仍是完整口语。若剔除后不足 14 字，后面的长度硬卡会正常判废。
    """
    text = str(line or "").strip()
    cleaned = PERBEAT_STAGE_DIRECTION_RE.sub("", text)
    if cleaned == text:
        return text
    cleaned = re.sub(r"[，,；;]\s*[，,；;]+", "，", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip("，,；; ")
    return cleaned


def _perbeat_parse_batch(data: Any) -> dict[int, str]:
    """解析整篇填词结果 → {序号: 台词}；容忍 dict/数组两种形状。"""
    out: dict[int, str] = {}
    rows = data.get("lines") if isinstance(data, dict) else data
    if isinstance(rows, dict):
        rows = [{"i": k, "line": v} for k, v in rows.items()]
    if not isinstance(rows, list):
        return out
    for pos, row in enumerate(rows, 1):
        if isinstance(row, str):
            idx, line = pos, row
        elif isinstance(row, dict):
            # 不能用 `row.get("i") or ...`：模型若给 0 基序号，`0 or pos` 会退回
            # 位置序号，把这一行错挂到第 pos 槽上并顶掉真正的第 pos 句
            # （实测：i=0 的多余句抢走第 1 句，整篇说话人整体错位一位）。
            raw_idx = row.get("i")
            if raw_idx is None:
                raw_idx = row.get("index")
            try:
                idx = int(raw_idx) if raw_idx is not None else pos
            except (TypeError, ValueError):
                idx = pos
            line = str(row.get("line") or row.get("text") or "")
        else:
            continue
        line = line.strip().strip('"「」')
        if line and idx not in out:
            out[idx] = line
    return out


# 现场动作词：台词里出现这些词就等于在「演」动作（「筷子一落下」「你别过来」），
# 而现场做没做这件事，观众只能靠台词反推——审读会判旁白/凭空。
# 只有本拍 intent（或原故事）真的写了这个动作，才允许在台词里提。
_PERBEAT_ACTION_WORDS: tuple[str, ...] = (
    "筷子", "落下", "放下", "过来", "凑近", "递", "推了", "站起来", "坐下",
    "转头", "抬头", "低头", "伸手", "拍", "盯着", "瞪", "夹起", "端起",
)


def _perbeat_allowed_actions(scene_contract: dict[str, Any], source_text: str = "") -> set[str]:
    """本片允许被台词提到的动作词：拍意图与原故事里出现过的。"""
    corpus = str(source_text or "")
    for beat in scene_contract.get("beat_chain") or []:
        if isinstance(beat, dict):
            corpus += str(beat.get("intent") or "") + str(beat.get("beat") or "")
    return {w for w in _PERBEAT_ACTION_WORDS if w in corpus}


# 「不是嘴变快」「你别冤枉我」——反驳的必须是前文真出现过的事。
# #138 实测第 6 句「我夸妈妈是真心的，不是嘴变快」，全篇没人提过「嘴变快」，
# 这句在反驳一个不存在的指控，审读判「答非所问」。
_PERBEAT_REBUTTAL_RE = re.compile(
    # (?<!是)：避开「是不是又想讨好处」这种反问，那里没有反驳
    r"(?:(?<!是)不是|别冤枉|谁跟你说|谁说的|你才)([\u4e00-\u9fff]{2,10})"
)


# 「你问怎么当公主」「你刚才说……」——把话塞进别人嘴里，比反驳稻草人更隐蔽。
_PERBEAT_ATTRIBUTION_RE = re.compile(
    r"(?:你|您)(?:刚|刚才|刚刚)?(?:问|说)了?(?:过)?([\u4e00-\u9fff]{2,10})"
)


def _perbeat_attribution_ok(line: str, prev_text: str, beat_text: str = "") -> bool:
    """指认对方说过什么，那件事必须真在前文出现过。

    例外：本拍契约就要求「抓住对方那句解释追问」时，被引用的说法写在拍
    意图里（#144 beat7「抓住妈妈‘不小心’的解释」），前文没逐字出现不算
    编造——模型是在照契约写，出处是契约本身。
    """
    haystack = _perbeat_terms(prev_text) | _perbeat_terms(beat_text)
    for match in _PERBEAT_ATTRIBUTION_RE.finditer(line):
        terms = {
            term
            for term in _perbeat_terms(match.group(1))
            if term not in {"什么", "怎么", "自己", "一句"}
        }
        if terms and not (terms & haystack):
            return False
    return True


def _perbeat_rebuttal_ok(line: str, prev_text: str, beat_text: str) -> bool:
    """反驳句的宾语必须在前文或拍意图里出现过，否则是在打稻草人。"""
    haystack = _perbeat_terms(prev_text) | _perbeat_terms(beat_text)
    for match in _PERBEAT_REBUTTAL_RE.finditer(line):
        target = match.group(1)
        terms = {
            term
            for term in _perbeat_terms(target)
            if term not in {"不是", "冤枉", "什么", "自己"}
        }
        if terms and not (terms & haystack):
            return False
    return True


_PERBEAT_REQUIRED_POINT_NEG_RE = re.compile(r"(?:不|没|别|甭|非)$|不是?$|没有$")


def _perbeat_required_points(entry: Any) -> list[dict[str, Any]]:
    """契约拍声明的「必现语义点」：``required_semantic_points``。

    写法：``[{"surface": "疼", "synonyms": ["疼你", "心疼"]}]``。只收 1–4 字
    的动词/名词/形容词短语，每拍至多 2 个——超过 2 个说明这一拍语义过载，
    该拆拍，而不是把机检阈值越抬越高（#144 DeepSeek 评审口径）。
    """
    if not isinstance(entry, dict):
        return []
    raw = entry.get("required_semantic_points")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        surface = ""
        synonyms: list[str] = []
        if isinstance(item, str):
            surface = item.strip()
        elif isinstance(item, dict):
            surface = str(item.get("surface") or "").strip()
            synonyms = [
                str(x).strip()
                for x in (item.get("synonyms") or [])
                if str(x).strip()
            ]
        if not surface:
            continue
        out.append({"surface": surface, "terms": [surface, *synonyms]})
    return out[:2]


def _perbeat_point_hit(line: str, term: str) -> bool:
    """字面命中且不是否定/劝阻式提及（「不是不小心」不算落地「不小心」）。"""
    if not term:
        return False
    start = 0
    while True:
        idx = line.find(term, start)
        if idx < 0:
            return False
        if not _PERBEAT_REQUIRED_POINT_NEG_RE.search(line[max(0, idx - 3) : idx]):
            return True
        start = idx + 1


def _perbeat_missing_required_points(line: str, entry: Any) -> list[str]:
    """返回没落地的必现语义点（空列表=全部落地）。"""
    return [
        point["surface"]
        for point in _perbeat_required_points(entry)
        if not any(_perbeat_point_hit(line, term) for term in point["terms"])
    ]


_PERBEAT_COLLECTIVE_ADDRESSEES = ("大家", "咱们", "你们", "我们", "咱")
_PERBEAT_ADDRESSEE_ALIASES: dict[str, tuple[str, ...]] = {
    "妈妈": ("妈妈", "妈"),
    "爸爸": ("爸爸", "爸"),
}


def _perbeat_addressee_names(raw: Any) -> list[str]:
    """契约里的 addressee（字符串/列表，可能用「/、，和」并列）摊成名字。"""
    if isinstance(raw, str):
        parts = re.split(r"[/、,，和与]", raw)
    elif isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        return []
    return [str(x).strip() for x in parts if str(x).strip()]


def _perbeat_slot_own_entry(slot: dict[str, Any]) -> Any:
    """本拍契约：契约拍直接用 ``_own_entry``，插话槽从 ``_beat_entries`` 反查。"""
    own = slot.get("_own_entry")
    if isinstance(own, dict):
        return own
    beat_id = int(slot.get("beat_id") or 0)
    for no, entry in slot.get("_beat_entries") or []:
        if no == beat_id and isinstance(entry, dict):
            return entry
    return None


def _perbeat_line_addressee(line: str, names: set[str]) -> str:
    """句首显式呼语（「妈，你先别急」「妈你先别急」→ 妈妈）；没有返回空串。"""
    text = str(line or "").strip()
    for name in sorted(names, key=len, reverse=True):
        for form in _PERBEAT_ADDRESSEE_ALIASES.get(name, (name,)):
            if not text.startswith(form):
                continue
            tail = text[len(form) :]
            if (
                not tail
                or tail[:1] in "，,：:、 "
                or tail.startswith(("你", "您"))
            ):
                return name
    return ""


def _perbeat_filler_addressee_ok(
    line: str,
    slot: dict[str, Any],
    prev_lines: list[tuple[str, str]],
) -> bool:
    """零素材插话句的呼语必须落在「上一句的人 + 本拍当事人」里。

    #144 run25 第 4 句实测：上一句是灿灿劝昭昭「你慢慢说」，补位句却写
    「妈你先别急…」——功能是旁观/递话，机检全过，终检判「错位」。这里只看
    **句首显式呼语**，不看句中提及（「昭昭，慢慢说，妈妈会听懂的」是正常
    递话，提到妈妈不算错位）；没有呼语就一律放行，避免误伤。
    """
    if not prev_lines:
        return True
    speaker = str(slot.get("speaker") or "").strip()
    allowed = {
        str(prev_lines[-1][0]).strip(),
        *_PERBEAT_COLLECTIVE_ADDRESSEES,
    }
    names: set[str] = {*allowed, *_KID_NAMES, "妈妈", "爸爸"}
    own = _perbeat_slot_own_entry(slot)
    if isinstance(own, dict):
        own_speaker = str(own.get("speaker") or "").strip()
        if own_speaker:
            allowed.add(own_speaker)
            names.add(own_speaker)
        for name in _perbeat_addressee_names(own.get("addressee")):
            allowed.add(name)
            names.add(name)
    for _no, entry in slot.get("_beat_entries") or []:
        if isinstance(entry, dict):
            sp = str(entry.get("speaker") or "").strip()
            if sp:
                names.add(sp)
    names.discard(speaker)
    addr = _perbeat_line_addressee(line, names)
    if not addr:
        return True
    return addr in allowed


_PERBEAT_NONVERBAL_TEMPLATES = (
    "哼，我还没消气呢，先不跟你说话了。",
    "嗯……我先不说了，心里这口气还没顺。",
    "反正我还有点不服，先这么着吧。",
)

# 「赢了但没消气」的收束模板池（契约 closing_polarity=unresolved_resentment）。
# 每条都留着「没消气/没领这份道歉」的反差；前两条带锚词（对不起/妈妈/道歉），
# 后两条不带锚词兜底。终检判「接不上」的硬判据是回句与上一句一个双字词都
# 不共享，所以选句时先挑与上一句有实词交集的那条（#144 run27 实测：无锚词的
# 收束句被判答非所问，修稿又把反差改平）。
_PERBEAT_SULK_CLOSING_TEMPLATES = (
    "对不起我听见了，可那声傻我还记着呢。",
    "你说对不起，可那声傻我还记着呢。",
    "道歉我听见了，可我还没打算原谅。",
    "妈妈道歉归道歉，我这小脾气还没过去。",
    "我还气着呢，这会儿先不跟你搭话。",
)

# 补位句里「零增量安抚」的说法：全篇只用一次。三句旁观补位全是
# 「你先别急/慢慢说/我就在旁边听着」时，12 句里有 25% 是同义复述，
# 笑点密度被摊薄，终检也会判重复（#144 run27 第 3/7/10 句实测）。
_PERBEAT_FILLER_PACIFY_MARKERS: tuple[str, ...] = (
    "别急",
    "慢慢说",
    "慢慢讲",
    "听着",
    "旁边",
    "你没错",
    "不该这样",
)


def _perbeat_is_nonverbal_beat(entry: Any) -> bool:
    """非言语收束拍（静场/嘟囔）：契约标 ``beat_type: nonverbal``。"""
    if not isinstance(entry, dict):
        return False
    return bool(
        str(entry.get("beat_type") or "").strip().lower() == "nonverbal"
        or entry.get("coherence_exempt") is True
    )


def _perbeat_sulk_closing_slot(slot: dict[str, Any]) -> bool:
    """本槽是不是「赢了但没消气」的收束拍（契约极性/收束意图）。"""
    return is_sulk_closing(slot.get("_own_entry"))


def _perbeat_nonverbal_line(
    slot: dict[str, Any],
    prev_lines: list[tuple[str, str]],
) -> str:
    """非言语拍的收束句只从封闭模板池取（自由生成会写出带前提的清晰表态）。"""
    seen = {str(ln or "").strip() for _sp, ln in prev_lines}
    pool = (
        _PERBEAT_SULK_CLOSING_TEMPLATES
        if _perbeat_sulk_closing_slot(slot)
        else _PERBEAT_NONVERBAL_TEMPLATES
    )
    prev_terms = _perbeat_terms(prev_lines[-1][1]) if prev_lines else set()
    best = ""
    best_anchor = -1
    for template in pool:
        line = template.strip()
        if line in seen:
            continue
        if _perbeat_check(slot, line, prev_lines):
            continue
        # 同池里优先取与上一句有实词交集的那条：既不像答非所问，
        # 也不会把上一句整段复述回来。
        anchor = len(_perbeat_terms(line) & prev_terms)
        if anchor > best_anchor:
            best, best_anchor = line, anchor
    return best


def _perbeat_check(
    slot: dict[str, Any],
    line: str,
    prev_lines: list[tuple[str, str]],
) -> list[str]:
    """单句机检，返回未通过的条目（空列表=通过）。"""
    speaker = str(slot.get("speaker") or "")
    # 零素材插话槽（has_content=False）：旁观角色手上没有素材，却必须凑句数。
    # 这类槽不要求「给理由/独立新内容」，咬合也从「共享实词」放宽成「做旁观/
    # 递话」，但照抄、认领、抢拍主、新物件这些硬拦一条不减（#144 专家评审）。
    # 拆句槽不算：拆句行要补本拍的另一半内容，必须按内容槽判。
    zero_material_filler = bool(
        slot.get("is_filler")
        and not slot.get("is_split")
        and not str(slot.get("split_role") or "")
        and slot.get("has_content") is False
    )
    groups = _perbeat_required_word_groups(slot)
    shape_ok = _perbeat_line_shape_ok(line)
    speech_ok = _perbeat_speech_form_ok(line, speaker)
    # 契约拍必须真的说出本拍声明的必现语义点：#144 run25 第 6 句只落了「承认
    # 弄脏 + 想自己弄干净」，丢了契约里的「因为疼妈妈」，连带第 8 句妈妈的
    # 「你疼妈妈」失去前提，终检判缺前提、修稿预算耗尽。
    missing_points = (
        []
        if slot.get("is_filler")
        else _perbeat_missing_required_points(line, slot.get("_own_entry"))
    )
    # 零素材插话句的呼语错了人：#144 run25 第 4 句，上一句是灿灿劝昭昭慢慢说，
    # 补位句却喊「妈你先别急」，机检全过、终检判错位。
    addressee_ok = not zero_material_filler or _perbeat_filler_addressee_ok(
        line, slot, prev_lines
    )
    # 上一句是问句时，回句必须咬住问句里的词（#138 实测：昭昭问「你确定要听？」，
    # 妈妈答「老虎一吼我确实会吼」，审读判问句悬空、答非所问）。
    question_ok = True
    if (
        prev_lines
        and not slot.get("_is_closing")
        and not zero_material_filler
        and _perbeat_is_question(prev_lines[-1][1])
    ):
        # intent 是「连声道歉」这类不可字面核对的言语行为时，答句本来就不
        # 必复述问句里的词（「对不起，是妈妈不对」就是正解），不拿咬词判它。
        question_ok = bool(
            _perbeat_terms(line) & _perbeat_terms(prev_lines[-1][1])
        ) or not _perbeat_intent_has_literal_anchor(str(slot.get("intent") or ""))
    allowed = slot.get("_allowed_actions")
    action_ok = True
    if isinstance(allowed, set):
        action_ok = all(w in allowed for w in _PERBEAT_ACTION_WORDS if w in line)
    dup_ok = not _perbeat_restates(line, prev_lines)
    # 追问句允许复述前文的说法：契约拍本来就要求「抓住对方的话反问」
    # （#144：第9句「疼我为什么大声骂我、说我傻？」被判复述，但它是在
    # 追问，不是把同一条信息换个说法再说一遍）。判据只看「问句 + 追问词
    # + 与前文共享两个实词」，不绑具体剧情词。
    previous_terms: set[str] = set()
    for _spk, _prev in prev_lines:
        previous_terms |= _perbeat_terms(_prev)
    # 只豁免契约里真是「回声/反问」的拍（孩子追问），不是所有问句：
    # 家长照抄孩子的问句（#144 run15 第8句「疼我为什么大声骂我…」）会被
    # 这条误放，终检仍判「第2句与第8句换词重复」。
    _own_entry = slot.get("_own_entry")
    _speech_act = (
        str(_own_entry.get("speech_act") or "").strip().lower()
        if isinstance(_own_entry, dict)
        else ""
    )
    echo_followup = (
        _speech_act in {"echo", "retort", "question"}
        and _perbeat_is_question(line)
        and bool(
            re.search(r"为什么|为啥|凭什么|怎么|难道|不是.{0,6}吗", line)
        )
        and len(_perbeat_terms(line) & previous_terms) >= 2
    )
    if echo_followup:
        dup_ok = True
    long_dup_ok = not (
        slot.get("is_filler") and _perbeat_repeats_long_phrase(line, prev_lines)
    )
    # 插话槽不再禁提问（2026-10 清理）：承上启下的追问本来就是这个位置最自然的
    # 写法（「妈，你这是要昭昭改口啊？」），而空问句已由「插话须有具体内容」
    # 「不得只附和」两条拦住。禁提问直接导致 12 句里少 3 句、整稿重掷（#138 实测）。
    no_question = True
    # 只有「插话槽」和「追问型契约拍」需要咬住上一句的具体词。
    # 契约拍里「改口祝妈妈像公主」「认栽说以后打草稿」本身就是新话头，
    # 要求它照搬上一句会逼模型写出别扭的复读句（#138 实测：第 11/12 句
    # 「那改口祝妈妈像一个公主，总该满意了吧。」被判「没接住上一句」）。
    # 只有插话槽要求咬住上一句的具体词。
    # 契约拍的台词来自契约 intent（「今天为啥舍得夸妈妈」「改口祝我像公主」），
    # 本来就是独立话头；再叠加「必须共用上一句的词」，会把正确答案判废
    # （#138 实测：「今天为啥舍得夸妈妈，平时你可不这么说。」被判
    # 「必须接住上一句的具体说法」，连续两轮后整篇只出 10 句）。
    # 契约拍的话头衔接交给批提示词与终检，机检只管形状。
    need_anchor = bool(slot.get("is_filler")) and not zero_material_filler
    abstract_ok = not (
        slot.get("is_filler")
        and re.search(
            r"比喻|道理|这话|这句|这句话|意思|玄乎|离谱|说法|逻辑|"
            r"接不上|接不住|接不了",
            line,
        )
    )
    prev_line = prev_lines[-1][1] if prev_lines else ""
    quote_ok = not slot.get("is_filler") or _perbeat_quote_ok(line, prev_line)
    if slot.get("is_filler"):
        # 规则互斥消解：插话槽的职责是「接住上一句的具体说法」（anchor_ok），
        # 而「不得复述前文」「引述必须有出处」又禁止它照搬上一句的词。同一句话
        # 被两套互相抵消的规则同时判，交集写法必然判废（#138 实测：第 3/7/11
        # 句在两套规则之间反复死，一轮里同一批槽连废 6 次）。
        # 机检对插话只保留「接住上一句」这一条；是否算复述、引述有没有出处，
        # 交终检看上下文——终检有全文，机检只有一行。
        dup_ok = True
        long_dup_ok = True
        quote_ok = True
    # 插话槽只放行「共享一两词」的接话，不放行「照抄一整段」和「认领别人的事」：
    # 这两条不属于上面那对互斥规则，是硬缺陷（#144 实测：第 7/10 句照抄上一句、
    # 第 11 句灿灿用第一人称认领昭昭的委屈），交终检只会整稿重掷。
    filler_copy_ok = not (
        slot.get("is_filler") and _perbeat_adjacent_repeat(line, prev_line)
    )
    filler_claim_ok = not (
        slot.get("is_filler")
        and _perbeat_filler_claims_owner_event(line, slot, prev_lines)
    )
    # 零素材插话槽的「松版咬合」：不共享实词也行，但必须真在做旁观/递话/助威。
    filler_link_ok = not zero_material_filler or bool(
        _PERBEAT_FILLER_SOFT_LINK_RE.search(line)
        or (prev_line and _perbeat_terms(line) & _perbeat_terms(prev_line))
    )
    # 「新物件」指全篇从未出现过的物件，而不是「上一句没提」。
    # 只比对上一句会把桌上那盘饺子、手里的筷子都判成新物件，
    # 逼模型只能写空话（#138 实测：8 个插话槽有 6 个因这条被判废）。
    seen_props = "".join(ln for _sp, ln in prev_lines)
    new_props = {
        term
        for term in _PERBEAT_PROP_TERMS
        if term in line and term not in seen_props
    }
    new_prop_detail = bool(
        {
            term
            for term in _PERBEAT_PROP_TERMS
            if term in line and term not in prev_line
        }
    ) and bool(_PERBEAT_PROP_DETAIL_RE.search(line))
    new_body_detail = bool(_PERBEAT_BODY_DETAIL_RE.search(line)) and not bool(
        _PERBEAT_BODY_DETAIL_RE.search(prev_line)
    )
    props_ok = not (
        slot.get("is_filler") and (new_props or new_prop_detail or new_body_detail)
    )
    # 零素材插话槽不要求「给理由」：旁观者本就没有事实可依据（#144 专家评审）。
    stance_ok = (
        not slot.get("is_filler")
        or zero_material_filler
        or _perbeat_stance_has_reason(line)
    )
    recall_ok = not slot.get("is_filler") or _perbeat_recall_ok(line, prev_lines)
    agreement_ok = not (
        slot.get("is_filler") and _PERBEAT_EMPTY_AGREEMENT_RE.search(line)
    )
    move_ok = not slot.get("is_filler") or _perbeat_filler_move_ok(line, prev_lines)
    speaker = str(slot.get("speaker") or "").strip()
    intent = str(slot.get("intent") or "")
    # 已删两条 #138 时代加的成品句规则（2026-10 清理）：
    #   * 「家长要求改口时不得写成自己改口」——按「改口/祝妈妈」这类剧情词写死，
    #     换一篇戏就是纯噪声；
    #   * 「不得写公主现出原形」——它把原稿金句「老虎一吼，公主也得现出原形」
    #     要求写成**逐字固定形式**才放行，等于让机检背一篇稿子的答案。
    # 两句的实际风险（话头对着谁说错、比对方错）由终检的「错位」类判定覆盖。
    premise_ok = True
    future = slot.get("_future_terms") or set()
    if future:
        premise_ok = not (_perbeat_terms(line) & set(future))
    # 插话槽不许抢契约拍的活：一旦插话句也「落地」了某条契约拍，
    # 拍序检测就会把后面真正的契约拍判成「晚于后面的拍」，
    # 报 `opening_causality: … beat=3 在第4句，不晚于 beat=2（第7句）`
    # （#138 实测：插话槽写了一句「不过我妈妈倒是眉清目秀的」，
    # 正是 beat=2 的内容，把 beat=2 顶到第 7 句）。
    # 契约拍必须**真的说到那一拍要交代的内容**。判据分三层：
    # 1) 「连声道歉」「小嘴一撇，嘟囔一句…」这类 intent 只能演出来、不能
    #    念出来，字面交集恒为 0，跳过字面检查（#144 实测：11 号位连续四轮
    #    判废，返修理由全是「必须落地本拍要交代的内容」）；
    # 2) 本句与 intent 共享 ≥2 个实词；
    # 3) 或者下游 `_line_fulfills_beat` 已经认这句落地了本拍——逐拍机检
    #    不该比终检还严（#144 第 1 句「你把衣服弄这么脏，真是个傻孩子！」
    #    终检认 blame，逐拍只共享「衣服」一个词）。
    # 其余交给 opening_causality 与终检。
    own_beat_ok = True
    own_beat_act_ok = True
    if slot.get("is_filler"):
        # 只拦**后面**的契约拍；插话本来就要回应刚说完的那一拍，
        # 用全部契约拍比对会把「芯子难吃我也吃出来了」这种正常接话
        # 误判成「顶替契约拍」，导致插话槽反复判废（#138 实测）。
        beat_id = int(slot.get("beat_id") or 0)
        own_entry = [
            (no, entry)
            for no, entry in (slot.get("_beat_entries") or [])
            if no > beat_id
        ]
        if own_entry:
            own_beat_ok = not any(
                _line_fulfills_beat(speaker, line, entry)
                for _no, entry in own_entry
            )
        # 本拍也不许替拍主办事：`_line_fulfills_beat` 第一条就要求说话人等于
        # 本拍 speaker，插话替本拍办事时它永远判 False，等于没拦。于是出现
        # 「妈妈该说的『改口祝我像公主』被灿灿说了，妈妈只剩半句」——终检判
        # 「错位：核心反应被换人」，人看着就是人物串戏（#138 实测第 5/8 拍）。
        # 这里改用不看说话人的口径：插话句与**本拍** intent 的锚点/实词重合
        # 到 3 个，就是在替拍主说话。
        own_now = next(
            (e for no, e in (slot.get("_beat_entries") or []) if no == beat_id),
            None,
        )
        # 只在「插话排在拍主之前」时判：这时插话一开口就把本拍的话说了，拍主
        # 只能接半句，终检才判「核心反应被换人」。拍主已经说完之后的回应句
        # 复述本拍内容是正常接话，不拦。
        if own_now is not None and slot.get("_precedes_owner"):
            own_beat_act_ok = not _filler_takes_over_beat(line, own_now)
    else:
        intent = str(slot.get("intent") or "")
        if _perbeat_intent_has_literal_anchor(intent):
            cover = _perbeat_terms(intent) & _perbeat_terms(line)
            cover -= {"妈妈", "爸爸", "昭昭", "灿灿", "自己", "一句", "什么"}
            own_beat_ok = len(cover) >= 2
            if not own_beat_ok:
                own_entry = slot.get("_own_entry")
                own_beat_ok = isinstance(
                    own_entry, dict
                ) and _line_fulfills_beat(speaker, line, own_entry)
        elif _perbeat_intent_is_performative(intent):
            own_beat_ok = _perbeat_performative_line_ok(intent, line)
    # 插话槽要求「与上一句共用至少一个具体二字词」。曾经用更严的
    # 「独有词」口径（`_perbeat_carries_prev`，把全篇高频词排掉），
    # 结果 6 个插话槽两轮全废、整篇只剩 8 句（#138 实测：
    # 「对白句数须≥12，当前8」）；而模型现在已被告知要照搬上一句的具体词，
    # 用普通口径就够，剩下的交给审读。
    anchor_ok = (not need_anchor) or _perbeat_anchor_ok(
        line, prev_lines[-1][1] if prev_lines else "", required=True
    )
    words_ok = _perbeat_words_ok(line, groups)
    prev = prev_line
    prev_is_q = _perbeat_is_question(prev)
    # 上一句是问句时本句必须正面回答：机检只能管住「不许再反问回去」，
    # 「答得对不对」交给审读。曾经叠加「必须共用上一句的词」，
    # 结果「因为你像一只暴躁的老虎，夸完就翻脸。」（正解）被判废。
    # 反问回去也要看是不是在「接」：把上一句里的话原样拎回来再问，是家人
    # 对话里最自然的追问（「你嫌难吃，那为啥又夸我眉清目秀？」），不算躲问题。
    from app.services.gold_story.gold_chat.validate import _intent_line_overlap

    attribution_ok = _perbeat_attribution_ok(
        line,
        "".join(text for _spk, text in prev_lines),
        str(slot.get("intent") or slot.get("beat_intent") or ""),
    )
    rebuttal_ok = _perbeat_rebuttal_ok(
        line,
        "".join(text for _spk, text in prev_lines),
        "".join(str(entry.get("intent") or "") for _no, entry in (slot.get("_beat_entries") or [])),
    )
    echo_question = (
        bool(prev_is_q)
        and _perbeat_is_question(line)
        and bool(prev_lines)
        and bool(re.search(r"为啥|为什么|凭什么|怎么又|怎么还|哪来的|哪儿来的", line))
        and _intent_line_overlap(prev_lines[-1][1], line, need=2)
    )
    answers_prev = (
        (not prev_is_q) or (not _perbeat_is_question(line)) or echo_question
    )
    # 收束拍标了「赢了但没消气」：末句不能写成完全满意/收下道歉，
    # 那是把反差收平，笑点余味全丢。
    closing_ok = not (
        _perbeat_sulk_closing_slot(slot) and bool(closing_accept_marker(line))
    )
    # 纯围观者的补位句不许把同一套安抚话再说一遍：三句旁观补位全是
    # 「你先别急/慢慢说/我就在旁边听着」等于 25% 的零增量台词。只共用
    # **一个**词不算重复；当事人（昭昭/妈妈）补位说安抚话是正常接话，不拦。
    filler_pacify_ok = True
    if slot.get("is_filler") and _perbeat_filler_is_witness(slot):
        earlier_text = "".join(txt for _sp, txt in prev_lines)
        shared = sum(
            1
            for marker in _PERBEAT_FILLER_PACIFY_MARKERS
            if marker in line and marker in earlier_text
        )
        filler_pacify_ok = shared < 2
    # 当事人在场反应：不当和事佬（不许劝对方「别急/慢慢说」——#144 run30
    # 第 4 句「你别急」把安抚对象错成了上一句的灿灿），也不许把后面自己那
    # 拍要交代的事实提前说掉（第 4 句先说「衣服是我弄脏的」，第 5 句妈妈
    # 只能重复追问、第 6 句昭昭只能重复回答）。
    # 当事人在场反应：只拦「提前说掉后面自己那拍的事实」。劝「别急」只由
    # 提示词引导、不做硬判——实测（服务器 #144）模型会连着三轮写「你先别急」，
    # 每轮又触发两次定向重写，把 180s 生成预算耗光，整稿直接失败；
    # 而这条只是终检的「观感」项，不阻断发布。
    filler_party_fact_ok = True
    if slot.get("is_filler") and not _perbeat_filler_is_witness(slot):
        _next_terms = set(slot.get("_next_party_terms") or ())
        if _next_terms:
            filler_party_fact_ok = len(_perbeat_terms(line) & _next_terms) < 3
    return [
        label
        for label, passed in (
            ("须 14–24 字且是完整句", shape_ok),
            ("不得自述动作/旁白或转述别人的话", speech_ok),
            ("不得提现场没发生的动作", action_ok),
            ("上一句是问句，回句须咬住问句", question_ok),
            ("不得复述前文", dup_ok),
            ("不得复述前文的具体说法", long_dup_ok),
            ("插话不得提问", no_question),
            ("必须先正面回答上一句的问题", answers_prev),
            ("插话须有具体内容（不许抽象词）", abstract_ok),
            # 上一句是问句时，「正面回答」必然要提到问句里没有的东西，
            # 与「不得另起新物件」互斥（#144 实测：3/12 号位每轮两罪并罚）。
            ("插话不得另起上一句没提的新物件细节", props_ok or prev_is_q),
            ("插话表态须给出理由", stance_ok),
            ("插话不得只附和或收下夸奖", agreement_ok),
            ("同一表态动作不得反复用", move_ok),
            ("不得引用前文没发生的事件", recall_ok),
            ("辩驳的事前文须提过", rebuttal_ok),
            ("指认对方说过的话须真有出处", attribution_ok),
            ("引述上一句时必须真有出处", quote_ok),
            ("必须接住上一句的具体说法", anchor_ok),
            ("必须出现指定词", words_ok),
            (
                "必须落地本拍的必现语义点："
                + "、".join(missing_points),
                not missing_points,
            ),
            ("零素材插话的呼语须落在上一句的人身上", addressee_ok),
            ("不得提前说后面才发生的说法", premise_ok),
            (
                "插话不得顶替契约拍的台词" if slot.get("is_filler")
                else "必须落地本拍要交代的内容（原样含本拍 intent 至少一个实词）",
                own_beat_ok,
            ),
            ("插话不得替本拍说话人办事", own_beat_act_ok),
            ("插话不得照抄上一句", filler_copy_ok),
            ("插话不得认领拍主的事实/动机", filler_claim_ok),
            ("零素材插话须做旁观/递话/助威", filler_link_ok),
            ("补位句不得重复同一套安抚说法", filler_pacify_ok),
            ("当事人补位句不许提前说掉本拍的事实", filler_party_fact_ok),
            ("未消气的收束不得写成完全满意", closing_ok),
        )
        if not passed
    ]


_FILLER_TAKEOVER_NEED = 3


def _filler_takes_over_beat(line: str, entry: dict[str, Any]) -> bool:
    """插话句是否替**本拍拍主**把话说完了（不看说话人）。

    判据与落地判定同一套锚点：本拍 intent 的锚点在本句出现，或与 intent 共享
    3 个以上双字实词，就算替拍主办事。只用于插话槽，命中即丢该句（不进任何
    整稿否决），所以宁可判得稍严。
    """
    from app.services.gold_story.gold_chat.validate import (
        _anchor_matches_line,
        _intent_anchor_tokens,
        _intent_line_overlap,
    )

    intent = str(entry.get("intent") or entry.get("beat") or "")
    text = str(line or "").strip()
    if not intent or not text:
        return False
    anchors = _intent_anchor_tokens(intent)
    if anchors and any(_anchor_matches_line(tok, text) for tok in anchors):
        return True
    return _intent_line_overlap(intent, text, need=_FILLER_TAKEOVER_NEED)


def _perbeat_future_terms(
    slots: list[dict[str, Any]],
    idx: int,
    *,
    punchline: str = "",
) -> set[str]:
    """本句还没资格提的**包袱词**（公主/老虎/原形…）。

    提前说出来会被终检判「引用无据：前面没有任何人提过公主或现出原形」——
    #138 反复踩这条（第 10 句先说「公主也得现出原形」，
    妈妈要到第 11 句才要求改口祝她像公主）。

    只取包袱里的词，不取各拍 intent 的词：intent 是自然语言，
    二字切片全是「这盘/妈妈/句就」这类噪声，一律拿来判会把正常句子全判废
    （实测：第 1 句「昭昭，这盘黑面饺子刚端上桌，你尝尝好不好吃。」
    因「这盘」被判「提前说后面才发生的说法」）。
    本拍 intent 里出现的包袱词视为「本拍就负责说它」，直接放行。
    """
    target = _perbeat_terms(punchline or "")
    if not target:
        return set()
    own = str(slots[idx].get("intent") or "") if idx < len(slots) else ""
    heard = " ".join(
        str(s.get("intent") or "") for s in slots[: idx + 1] if isinstance(s, dict)
    )
    return target - _perbeat_terms(heard) - _perbeat_terms(own)


def _perbeat_next_party_terms(slots: list[dict[str, Any]], idx: int) -> set[str]:
    """后面第一个「同一说话人的契约拍」要交代的实词。

    当事人补位句不许抢在这拍前面把它的话说掉（#144 run30 第 4 句：
    昭昭的补位句先说「衣服是我弄脏的」，第 5 句妈妈再问、第 6 句昭昭再答，
    同一事实被念了三遍，终检判「重复追问 + 重复交代」）。
    """
    speaker = str(slots[idx].get("speaker") or "").strip() if idx < len(slots) else ""
    if not speaker:
        return set()
    for j in range(idx + 1, len(slots)):
        nxt = slots[j]
        if not isinstance(nxt, dict) or nxt.get("is_filler"):
            continue
        if str(nxt.get("speaker") or "").strip() != speaker:
            return set()
        return _perbeat_terms(str(nxt.get("intent") or ""))
    return set()


# 纯动作/停顿型契约拍（没有可核对的实词内容）
_PERBEAT_PAUSE_INTENT_RE = re.compile(
    r"愣住|接不上话|举着筷子|没落下|认栽|噎住|不吭声|沉默"
)


def _perbeat_intent_has_literal_anchor(intent: str) -> bool:
    """主句 intent 是否含可被台词字面核对的内容。

    契约拍有两种写法：写清「这拍要交代什么」（骂了什么、认了什么、夸了
    什么），台词能复述，实词交集检查有效；只写「这拍要做什么」（连声道歉、
    占物、劝架、吐槽），或写成舞台提示（「小嘴一撇，嘟囔一句听不清的
    话」），这些只能演出来、不能念出来，字面交集恒为 0，每轮返修都修
    不掉（#144 实测：11 号位连续四轮判废，理由全是「必须落地本拍要交代
    的内容」；12 号位也反复中同一类）。这类拍交给言语行为标记或终检的
    语义审读，逐拍机检只保留形状与衔接。
    """
    text = str(intent or "").strip()
    if not text:
        return False
    if _PERBEAT_PAUSE_INTENT_RE.search(text):
        return False
    if _perbeat_intent_is_performative(text):
        return False
    if looks_like_narration_line(text):
        # 舞台提示里的动作描写不能字面核；但「追问为什么…」「说『…』」
        # 这种仍带着要念的内容，按实词核，避免把有内容的拍一起放掉。
        return bool(
            re.search(r"[‘’“”\"「」『』]", text)
            or _PERBEAT_ASK_WORD_RE.search(text)
        )
    # 引语或冒号后是可念出来的具体话。
    if re.search(r"[“”\"「」『』：:]", text):
        return True
    # 2–3 字动作标签（「占物」「劝架」「吐槽」）没有可核对的实词；
    # 4 字以上（「追问原因」）已经能说明要交代什么，仍按实词核。
    if (
        not re.search(r"[，,；;]", text)
        and len(re.findall(r"[\u4e00-\u9fff]", text)) <= 3
    ):
        return False
    return True


# 「连声道歉」这类只写言语行为、不写内容的拍：台词不会复述「道歉」二字，
# 但必须真的在道歉。用通用言语行为标记核，不绑剧情词。
_PERBEAT_PERFORMATIVE_HEAD_RE = re.compile(
    r"^(?:连声|连连|连忙|赶紧|急忙|主动|率先|再次|小声|哭着|哭腔|无奈|勉强|只好|当场)?"
    r"(?:道歉|认错|服软|道谢|感谢|告别|道别)"
    r"(?:[，,。：:]?.{0,6})?$"
)
_PERBEAT_PERFORMATIVE_RULES: tuple[
    tuple[re.Pattern[str], re.Pattern[str]], ...
] = (
    (
        re.compile(r"道歉|认错|服软"),
        re.compile(r"对不起|抱歉|是我不对|是我不好|不该|原谅|认错|道歉|服了|我认输|行吧|好吧"),
    ),
    (re.compile(r"道谢|感谢"), re.compile(r"谢谢|多谢|感谢|谢")),
    (re.compile(r"告别|道别"), re.compile(r"再见|回头见|拜拜|我先走")),
)


def _perbeat_intent_is_performative(intent: str) -> bool:
    """intent 是否以「做这个言语行为」为主，而不是顺带提到它。

    「连声道歉」「认错：下次不这样」是纯言语行为拍，台词只需真的在道歉/
    认错；「道歉后提议讲道理，问昭昭…」这类多分句拍只是把道歉当前置动作，
    后面还有要交代的内容，仍按实词核（#144 实测：这条被误分到道歉分支，
    每轮判「必须落地本拍要交代的内容」）。
    """
    return bool(_PERBEAT_PERFORMATIVE_HEAD_RE.match(str(intent or "").strip()))


def _perbeat_performative_line_ok(intent: str, line: str) -> bool:
    text = str(intent or "").strip()
    for intent_re, line_re in _PERBEAT_PERFORMATIVE_RULES:
        if intent_re.search(text):
            return bool(line_re.search(str(line or "")))
    return True


_PERBEAT_ASK_RE = re.compile(r"[？?]\s*$|吗[。！…]?$")
_PERBEAT_ASK_NE_RE = re.compile(r"呢[。！…]?$")
_PERBEAT_ASK_WORD_RE = re.compile(
    r"什么|怎么|为什么|为啥|凭什么|哪|谁|几|多少|是不是|要不要|能不能|可不可以|会不会"
)

# 插话必须接着上一句的判断说。模型最常见的偷懒是「我同意，可这盘饺子皮…」
# 用全篇都在场的东西开新挑刺；这些具体物件若上一句没提，就不许插话另起。
_PERBEAT_PROP_TERMS = (
    "饺子", "黑面", "皮", "芯子", "馅", "筷子", "碗", "盘子", "勺子", "汤勺",
)

# 给上一句没提的物件**另加**感官/动作细节（「这盘饺子黑得我下不去嘴」
# 「妈妈端饺子手都没抖」）会把反应写成旁白式挑刺，终检会判接不上。
_PERBEAT_PROP_DETAIL_RE = re.compile(
    r"黑得|厚|薄|苦|咸|淡|硬|软|冷|热|烫|抖|捏|擀|包|煮|端|咬|尝|闻"
)

# 「她今天脸色确实白净」= 接着上一句的夸奖，另补一个外貌/身体细节。
# 这种句子看似有具体内容，实际只是把夸奖展开，既不接批评，也没有新立场。
_PERBEAT_BODY_DETAIL_RE = re.compile(
    r"脸色|白净|眉眼|眼睛|眼神|五官|皮肤|脸蛋|长相|身段|嗓子|"
    r"头发|梳头|梳了头|发型|打扮|口红|衣服|衣裳"
)


def _perbeat_is_question(line: str) -> bool:
    """「是不是在提问」：只看句末语气，不看句中疑问词。

    句中带疑问词的陈述句很常见（「凶起来谁都不敢吭声」「这盘饺子什么味都没有」
    都含「谁/什么」），用疑问词全集判定会把正常回答当成「又反问回去」
    （#138 实测：第 6 句「因为你像一只暴躁的老虎，凶起来谁都不敢吭声。」
    被判「必须先正面回答上一句的问题」）。

    「呢」有两种用法：作疑问语气（「我晚上吃什么呢」）和作陈述收尾
    （「我还没消气呢」）。后者曾被当成问句，把 12 号位的正解判成
    「必须先正面回答上一句的问题」（#144 实测）。句中无疑问词且不是
    短问句（「那你呢」）时按陈述处理。
    """
    text = str(line or "").strip()
    if _PERBEAT_ASK_RE.search(text):
        return True
    if _PERBEAT_ASK_NE_RE.search(text):
        return bool(_PERBEAT_ASK_WORD_RE.search(text)) or len(text) <= 6
    return False


def _perbeat_choose_filler_order(
    items: list[tuple[int, str, str]],
    *,
    prev_speaker: str,
    prev_line: str,
    next_speaker: str,
) -> list[tuple[int, str, str]]:
    """在两条契约拍之间给有效插话排一个「不相邻同人」的顺序。

    插话是可选行：判废后删掉会造成两侧同人相邻（A B A 去掉中间的 B）。
    这些插话本来就同属一个拍位、可以互换先后，所以优先重排而不是再让 LLM
    整篇重写。重排同时尽量保住每句对上一句的承接；实在排不开才少留一句。
    """
    if not items:
        return []

    def _ordered(seq: list[tuple[int, str, str]], *, require_anchor: bool) -> bool:
        last_speaker = prev_speaker
        last_line = prev_line
        for _idx, speaker, line in seq:
            if speaker and speaker == last_speaker:
                return False
            if (
                require_anchor
                and last_line
                and not _perbeat_anchor_ok(line, last_line, required=True)
            ):
                return False
            # 重排后「你说…」的引语仍必须有出处，否则会把后一句才说的话
            # 换到前一句去引述（#138 实测：灿灿「你说老虎发威吓人」被换到
            # 昭昭还没说这句之前，终检判引用无据）。
            if last_line and not _perbeat_quote_ok(line, last_line):
                return False
            last_speaker = speaker
            last_line = line
        return not next_speaker or last_speaker != next_speaker

    if _ordered(items, require_anchor=True):
        return items
    # 先按「仍能接住上一句」搜索完整顺序；找不到再退到纯结构顺序。
    for require_anchor in (True, False):
        # 一个拍位最多几张插话，穷举成本可忽略；异常长时改用贪心，避免卡住。
        if len(items) > 7:
            seq: list[tuple[int, str, str]] = []
            remaining = list(items)
            last_speaker = prev_speaker
            last_line = prev_line
            while remaining:
                pick_i = next(
                    (
                        i
                        for i, (_no, speaker, line) in enumerate(remaining)
                        if speaker != last_speaker
                        and (
                            not require_anchor
                            or not last_line
                            or _perbeat_anchor_ok(line, last_line, required=True)
                        )
                    ),
                    None,
                )
                if pick_i is None:
                    break
                item = remaining.pop(pick_i)
                seq.append(item)
                last_speaker = item[1]
                last_line = item[2]
            if _ordered(seq, require_anchor=require_anchor):
                return seq
            continue

        from itertools import combinations, permutations

        # 从保留最多句开始找，保证只在该丢时才丢插话。
        for size in range(len(items), 0, -1):
            for subset in combinations(range(len(items)), size):
                for order in permutations(subset):
                    seq = [items[i] for i in order]
                    if _ordered(seq, require_anchor=require_anchor):
                        return seq
    return []


def _perbeat_order_kept_slots(
    slots: list[dict[str, Any]],
    kept: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """契约拍顺序不动，只重排每个拍位内的有效插话。"""
    kept_map = dict(kept)
    ordered: list[tuple[int, str]] = []
    pending: list[tuple[int, str, str]] = []
    for idx, slot in enumerate(slots, 1):
        line = kept_map.get(idx)
        if line is None:
            continue
        speaker = str(slot.get("speaker") or "")
        if slot.get("is_filler"):
            pending.append((idx, speaker, line))
            continue
        if pending:
            prev_idx, prev_line = ordered[-1] if ordered else (0, "")
            prev_speaker = (
                str(slots[prev_idx - 1].get("speaker") or "") if prev_idx else ""
            )
            chosen = _perbeat_choose_filler_order(
                pending,
                prev_speaker=prev_speaker,
                prev_line=prev_line,
                next_speaker=speaker,
            )
            ordered.extend((i, ln) for i, _sp, ln in chosen)
            pending = []
        ordered.append((idx, line))
    if pending:
        prev_idx, prev_line = ordered[-1] if ordered else (0, "")
        prev_speaker = (
            str(slots[prev_idx - 1].get("speaker") or "") if prev_idx else ""
        )
        chosen = _perbeat_choose_filler_order(
            pending,
            prev_speaker=prev_speaker,
            prev_line=prev_line,
            next_speaker="",
        )
        ordered.extend((i, ln) for i, _sp, ln in chosen)
    return ordered


# 插话句判废后**不允许**靠「补到 12 句」回填的失败类型：留着只会把问题句
# 交给终检（终检照样拦，还多烧一轮修稿预算）。
_PERBEAT_NEVER_KEEP = (
    "须 14–24",
    "不得自述动作",
    "必须接住上一句",
    "不得提前说",
    "插话不得顶替",
    "插话不得替本拍说话人办事",
    # 照抄上一句/认领别人的事是硬缺陷，留着只是把问题句交给终检（#144）。
    "插话不得照抄上一句",
    "插话不得认领",
)


def _fill_fail_sig(failures: list[tuple[int, str, str]]) -> tuple[int, ...]:
    """返修轮失败签名：只比槽号，判断「这轮改不动了」。"""
    return tuple(sorted(i for i, _ln, _why in failures))


def _perbeat_fill_slots(
    slots: list[dict[str, Any]],
    *,
    scene_contract: dict[str, Any],
    punchline: str,
    temperature: float,
    retry_feedback: str = "",
    source_text: str = "",
) -> tuple[list[tuple[str, str]], list[tuple[int, str, str]]]:
    """整篇填词：一次调用填完所有槽，最多再一次返修。

    一句一调实测要 40+ 分钟（14 槽 × 4–6 次重写 × draft 重掷），因为每槽都要
    凑齐「14–24 字/不复述/接住上一句/必含词」四五个条件，模型几乎每槽都要重写。
    整篇一次性填词把调用降到 1–2 次，而说话人与拍序由骨架锁死（模型只填词），
    所以不会回到「张冠李戴」的老问题。
    """
    from app.services.gold_story.gold_chat.prompts import (
        PERBEAT_BATCH_SYSTEM,
        format_perbeat_batch_user,
    )

    allowed_actions = _perbeat_allowed_actions(scene_contract, source_text)
    last_beat = max((int(s.get("beat") or 0) for s in slots), default=0)
    for slot in slots:
        slot["_allowed_actions"] = allowed_actions
        # 收束拍的台词是收尾，不受「回句必须咬住上一句问句」约束
        slot["_is_closing"] = int(slot.get("beat") or 0) == last_beat

    filled: dict[int, str] = {}
    lines: list[tuple[str, str]] = []
    failures: list[tuple[int, str, str]] = []
    keep_idx: set[int] = set()
    base_feedback = str(retry_feedback or "").strip()
    feedback = base_feedback
    # 每槽带上「后面才出现的概念」清单，机检时用来挡「提前说」；
    # 插话槽再带上全部契约拍，机检时用来挡「插话顶替契约拍的台词」。
    from app.services.gold_story.gold_chat.validate import _beat_chain_entries

    _entries = _beat_chain_entries(
        (scene_contract.get("beat_chain") or [])
        if isinstance(scene_contract, dict)
        else []
    )
    _owner_first: dict[int, int] = {}
    for _i, _slot in enumerate(slots):
        if not isinstance(_slot, dict) or _slot.get("is_filler"):
            continue
        _bid = int(_slot.get("beat_id") or 0)
        _owner_first.setdefault(_bid, _i)
    for _i, _slot in enumerate(slots):
        if isinstance(_slot, dict):
            _bid = int(_slot.get("beat_id") or 0)
            _slot["_precedes_owner"] = bool(
                _slot.get("is_filler")
                and _bid in _owner_first
                and _i < _owner_first[_bid]
            )
            _slot["_future_terms"] = sorted(
                _perbeat_future_terms(slots, _i, punchline=punchline)
            )
            if _slot.get("is_filler"):
                _slot["_next_party_terms"] = sorted(
                    _perbeat_next_party_terms(slots, _i)
                )
                if not _perbeat_filler_is_witness(_slot):
                    _slot["intent"] = _perbeat_party_filler_intent(
                        str(_slot.get("intent") or "")
                    )
            if _slot.get("is_filler") and _entries:
                _slot["_beat_entries"] = list(_entries)
            elif not _slot.get("is_filler"):
                _bid = _slot.get("beat_id")
                _slot["_own_entry"] = next(
                    (e for no, e in _entries if no == _bid), None
                )
    prev_fail_sig: tuple[int, ...] | None = None
    for round_i in range(3):
        user = format_perbeat_batch_user(
            scene_contract=scene_contract,
            punchline=punchline,
            slots=slots,
            feedback=feedback,
        )
        data: Any = {}
        for _net in range(4):
            try:
                data = _chat_json(
                    PERBEAT_BATCH_SYSTEM,
                    user,
                    temperature=temperature + 0.1 * round_i,
                    max_tokens=1600,
                )
                break
            except ValueError:
                raise
            except Exception as exc:  # 网络抖动：整篇调用失败要能退避重试
                if _net >= 3:
                    raise
                logger.debug(
                    "[GOLD_CHAT] perbeat batch net retry %s: %s",
                    _net + 1,
                    str(exc)[:120],
                )
                time.sleep(3 * (_net + 1))
        got = _perbeat_parse_batch(data)
        if not got:
            feedback = "\n".join(
                x
                for x in (
                    base_feedback,
                    "上一轮没有按要求输出 JSON，请严格按 {\"lines\": [...]} 输出。",
                )
                if x
            )
            continue
        # 返修轮：**整表重填**，只覆盖上一轮判废的槽（合格的句子保持不动，
        # 免得改坏）。曾经让返修轮只输出判废的那几句，模型常常顺带少给几行，
        # 结果整篇只剩 8 句（#138 实测：「对白句数须≥12，当前8」）。
        if round_i == 0:
            filled = dict(got)
        else:
            for idx, line in got.items():
                if 1 <= idx <= len(slots) and idx not in keep_idx:
                    filled[idx] = line
        lines, failures = _perbeat_validate_fill(slots, filled)
        if not failures:
            return lines, []
        keep_idx = {i for i in range(1, len(slots) + 1)} - {
            i for i, _ln, _why in failures
        }
        local_feedback = "\n".join(
            f"- 第{i}句「{ln}」未通过：{why}" for i, ln, why in failures[:8]
        )
        feedback = "\n".join(x for x in (base_feedback, local_feedback) if x)
        logger.info(
            "[GOLD_CHAT] perbeat batch round=%s got=%s filled=%s invalid=%s/%s "
            "idx=%s reasons=%s",
            round_i + 1,
            len(got),
            len(filled),
            len(failures),
            len(slots),
            [i for i, _ln, _w in failures],
            [(i, why[:60]) for i, _ln, why in failures[:8]],
        )
        # 只剩插话槽不合格时不再重填：下面 `_perbeat_soft_fillers` 那条路会把
        # 它们按「够 12 句就保留」兜住，交给终检定点修。每轮整表重填要多烧一次
        # 12 行调用（约 3s），而这类软失败几乎每次都剩 1–2 条，三轮必然跑满。
        soft_only = all(
            i <= len(slots) and slots[i - 1].get("is_filler")
            for i, _ln, _why in failures
        )
        if soft_only and len(slots) - len(failures) >= 12:
            logger.info(
                "[GOLD_CHAT] perbeat soft-only failures left=%s, stop refill",
                len(failures),
            )
            break
        # 返修轮若判废的还是同一批槽，下一轮几乎必然同样判废（模型只是换词，
        # 触发的还是同一条规则）：#138 实测三轮 idx=[3,7,10] 原样重复，纯烧
        # 两次 12 行调用。同一批失败出现第二次就收手，交下游兜。
        if (
            failures
            and len(slots) >= 12
            and _fill_fail_sig(failures) == prev_fail_sig
        ):
            logger.info(
                "[GOLD_CHAT] perbeat fill stalled round=%s idx=%s",
                round_i + 1,
                [i for i, _ln, _w in failures],
            )
            break
        prev_fail_sig = _fill_fail_sig(failures)
        if round_i == 2:
            break
        filled = dict(filled)
        for i, _ln, _why in failures:
            filled.pop(i, None)
    if not filled:
        # 三轮都没拿到可解析的 {"lines": [...]}：这里必须显式失败。早先直接
        # 返回 ([], [])，日志只剩「assembled lines=0 chars=0」，下游 validate
        # 报的是「句数/字数不足」，真因（模型没给 JSON）被完全掩盖。
        raise ValueError("perbeat: batch fill returned no parsable lines")
    # 非言语收束拍（契约标 beat_type=nonverbal 的静场/嘟囔拍）不交给模型自由
    # 命题：它写出来的是「你道歉我听见了，可我心里这口气还没顺过来」这种带
    # 前提的清晰表态，终检会判缺前提/接不上（#144 run25 第 12 句实测）。这类拍
    # 只从封闭模板池取含糊收束句，模板一律先过机检；换句后撤掉旧判废记录。
    for _i, _slot in enumerate(slots, 1):
        if not _perbeat_is_nonverbal_beat(_slot.get("_own_entry")):
            continue
        _prev = [
            (str(slots[_j - 1].get("speaker") or ""), str(filled[_j]))
            for _j in range(1, _i)
            if _j in filled
        ]
        _line = _perbeat_nonverbal_line(_slot, _prev)
        if not _line or _line == filled.get(_i):
            continue
        filled[_i] = _line
        failures = [f for f in failures if f[0] != _i]
        logger.info("[GOLD_CHAT] perbeat nonverbal slot=%s line=%s", _i, _line)
    # 剩余的插话槽直接丢掉（凑句数的槽，塞坏句比少一句更糟）；
    # 契约拍交回上一级重掷。
    # 只有**判废的**插话槽才丢；合格的插话句当然要留下。
    # （早先这里写成「不是插话槽就留下」，把合格的 6 条插话句一起筛掉了，
    # 8 拍永远只剩 8 句，稳定报「对白句数须≥12，当前8」。#138 实测。）
    # 失败分两级（2026-10 清理）：
    #   * 契约拍的句子不合格 = 这一拍没交代清楚，整稿没意义 → 整稿重掷；
    #   * 插话槽（凑句数的补位句）不合格 = 单句瑕疵，本地修得掉 → 丢掉该句，
    #     不够 12 句时再把它留着交终检定点修。
    # 之前这里还有一张 `hard_markers` 子串表，把「必须出现指定词」「必须接住
    # 上一句」等 13 条也算整稿级否决——插话槽一句不合就废掉整稿，#138 实测
    # 一次重掷白烧 15–30 秒，连废 6 次。表已删：插话槽不再有任何整稿级否决。
    hard_fail: list[tuple[int, str, str]] = []
    soft_fillers: list[tuple[int, str, str]] = []
    for i, ln, why in failures:
        if i <= len(slots) and not slots[i - 1].get("is_filler"):
            hard_fail.append((i, ln, why))
        else:
            soft_fillers.append((i, ln, why))
    # 插话槽缺陷先走本地替换链（#144 专家评审第 5 条）：判废就丢句会让 12 句
    # 掉到 10 句、整稿直接篇幅驳回；整表重掷又必然复现同一批插话缺陷（模型只是
    # 换词照抄）。所以先定向重写该槽（≤2 次），再退到封闭功能模板，都拿不到才丢。
    # 只在凑句数的整篇稿上做（槽数够 12）：链子的用途就是保住句数下限，
    # 短稿里没有这条下限要保，废句照旧丢弃。
    min_lines = 12
    fixed: dict[int, tuple[str, str]] = {}
    if soft_fillers and len(slots) >= min_lines:
        fixed = _perbeat_replace_bad_fillers(
            slots,
            filled,
            soft_fillers,
            scene_contract=scene_contract,
            temperature=temperature + 0.1 * round_i,
        )
        for i, (ln, _how) in fixed.items():
            filled[i] = ln
        soft_fillers = [f for f in soft_fillers if f[0] not in fixed]
    bad_idx = {i for i, _ln, _why in failures} - set(fixed)
    for i, _ln, why in soft_fillers:
        logger.info(
            "[GOLD_CHAT] perbeat filler dropped slot=%s sp=%s why=%s",
            i,
            slots[i - 1].get("speaker") if i <= len(slots) else "?",
            why,
        )
    kept = [
        (i, l) for i, l in sorted(filled.items())
        # 1 <= i：i=0 会命中 slots[-1]，把这一句错挂到最后一句的说话人名下。
        if 1 <= i <= len(slots) and i not in bad_idx
    ]
    # 软问题（表态/理由/物件细节）不再无限丢句：句数掉到 12 以下时，
    # 把这类插话保留下来交给终检定点修。否则本地规则会把稿子删成 8 句，
    # 连进入语义审读的机会都没有（#138 实测）。
    if len(kept) < min_lines and soft_fillers:
        have = {i for i, _ln in kept}
        for i, ln, why in sorted(soft_fillers):
            if i in have or not str(ln or "").strip():
                continue
            # 「补到 12 句」只补**内容对、措辞有小毛病**的插话句。形状不对
            # （不是 14–24 字的完整句）、写成旁白、没接住上一句、抢了契约拍的
            # 台词——这几类留着也只是把问题句交给终检，补进来等于自欺。
            if any(marker in why for marker in _PERBEAT_NEVER_KEEP):
                continue
            kept.append((i, ln))
            have.add(i)
            if len(kept) >= min_lines:
                break
        kept.sort()
        logger.info(
            "[GOLD_CHAT] perbeat soft filler kept to meet min lines=%s/%s",
            len(kept),
            min_lines,
        )
    ordered = _perbeat_order_kept_slots(slots, kept)
    if [i for i, _ln in ordered] != [i for i, _ln in kept]:
        logger.info(
            "[GOLD_CHAT] perbeat filler reorder before=%s after=%s dropped=%s",
            [i for i, _ln in kept],
            [i for i, _ln in ordered],
            len(kept) - len(ordered),
        )
    lines = [(str(slots[i - 1]["speaker"]), ln) for i, ln in ordered]
    return lines, hard_fail


def _perbeat_validate_fill(
    slots: list[dict[str, Any]],
    filled: dict[int, str],
) -> tuple[list[tuple[str, str]], list[tuple[int, str, str]]]:
    """按槽序逐句机检：返回（合格句子序列, 不合格项）。"""
    lines: list[tuple[str, str]] = []
    line_idx: list[int] = []
    failures: list[tuple[int, str, str]] = []
    trigger_speaker = ""
    for idx, slot in enumerate(slots, 1):
        line = str(filled.get(idx) or "").strip()
        if not line:
            failures.append((idx, "（空）", "没有给出这一句"))
            continue
        line = _perbeat_strip_stage_direction(line)
        if slot.get("is_filler"):
            line = _perbeat_repair_repeated_filler(slot, line, lines)
        # 先截到 24 字再检：模型多写两三个字（「…所以你还是当老虎吧。」25 字）
        # 不该判废——截断在逗号处就是一句合法台词，重写反而更远离原意。
        # （#138 实测：run 里只差 2 条「须 14–24 字」，整条 draft 就此重掷。）
        if len(line) > 24:
            clipped = _perbeat_clip(line, limit=24)
            if len(clipped) >= 14:
                line = clipped
        # 装稿阶段直接取 filled；清理/截短后的结果必须写回，否则验收过了、
        # 最终台词仍然带着原始舞台提示或超长尾巴（#138 实测）。
        filled[idx] = line
        why = _perbeat_check(slot, line, lines)
        if why:
            failures.append((idx, line, "、".join(why)))
            continue
        speaker = str(slot.get("speaker") or "")
        lines.append((speaker, line))
        line_idx.append(idx)
        if (
            not slot.get("is_filler")
            and speaker in _PERBEAT_KID_NAMES
            and not _PERBEAT_PAUSE_INTENT_RE.search(str(slot.get("intent") or ""))
        ):
            trigger_speaker = speaker
    # 拆句行不得只是把拍主刚说的内容换个说法重说（#138 实测：昭昭说「芯子难吃
    # 我认、妈确实眉清目秀」，灿灿紧跟着又把这句复述一遍，终检判「抢台词重说」）。
    # 拆句的职责是补本拍**另外一半**内容，与拍主那句共享 3 个以上实词就算越界。
    from app.services.gold_story.gold_chat.validate import _intent_line_overlap

    owner_line: dict[int, str] = {}
    for slot in slots:
        beat_no = int(slot.get("beat") or 0)
        idx = int(slot.get("i") or 0)
        if not slot.get("split_role") and beat_no and beat_no not in owner_line:
            owner_line[beat_no] = str(filled.get(idx) or "")
    kept: list[tuple[str, str]] = [(sp, ln) for sp, ln in lines]
    for slot in slots:
        if slot.get("split_role") != "second_half":
            continue
        beat_no = int(slot.get("beat") or 0)
        mine = str(filled.get(int(slot.get("i") or 0)) or "")
        prev = owner_line.get(beat_no) or ""
        if (
            mine
            and prev
            and _intent_line_overlap(prev, mine, need=3)
            and any(mine == ln for _sp, ln in kept)
        ):
            kept = [(sp, ln) for sp, ln in kept if ln != mine]
            failures.append(
                (int(slot.get("i") or 0), mine, "拆句不得复述拍主刚说的内容"),
            )
    lines = kept
    # 句数达标后的总字数下限（联合判据 240-24=216）。单句 14 字合法，但整篇
    # 偏短时本地垫字补不出来（#144 实测：12 句 207 字，垫到 212 就停），
    # 与其硬塞语气词，不如把最短的几句退回让模型写长。
    from app.services.gold_story.scene import (
        CHAT_LINE_COUNT_MIN as _CHAT_MIN_FOR_LENGTH,
    )

    if not failures and len(lines) >= _CHAT_MIN_FOR_LENGTH:
        from app.services.gold_story.gold_chat.validate import (
            gold_chat_effective_min_chars,
        )

        floor = gold_chat_effective_min_chars(
            [{"line": ln} for _sp, ln in lines]
        )
        total = sum(len(ln) for _sp, ln in lines)
        # 留 12 字余量：finalize 的类型补丁（如 I 的 strip_mid_pad）会再删
        # 语气词，卡在下限整好 216 的稿子会被删到 208（#144 run14 实测）。
        target = floor + 12
        if total < target:
            need = target - total
            for i in sorted(range(len(lines)), key=lambda i: len(lines[i][1])):
                if need <= 0:
                    break
                room = 24 - len(lines[i][1])
                if room <= 0:
                    continue
                failures.append(
                    (
                        line_idx[i],
                        lines[i][1],
                        f"全文还差{need}字，本句写到{min(24, len(lines[i][1]) + need)}字左右",
                    )
                )
                need -= room
    return lines, failures


def _perbeat_key_from_object(raw: str) -> str:
    """逐拍路径的 key：从契约 object 取一个完整短语，别硬切 8 字。

    旧实现 ``object[:8]``：#138 的 object 写成「妈妈像什么（黑面饺子）」，硬切
    得到 ``妈妈像什么（黑面``——括号没闭合、意思半截，导出稿里直接可见。
    这里优先在该短语的第一个标点/括号前收口，再按 8 字上限截断，最后去掉
    残留的悬空标点。
    """
    text = str(raw or "").strip()
    if not text:
        return "像什么"
    for sep in ("（", "(", "【", "[", "：", ":", "，", ",", "。", ".", "！", "!", "？", "?", "；", ";"):
        if sep not in text:
            continue
        head = text.split(sep, 1)[0].strip()
        if len(head) >= 2:
            return head[:8].strip("（(【[）)】]：:，,。.！!？?；;、 ")
    return (
        text[:8].strip("（(【[）)】]：:，,。.！!？?；;、 ") or "像什么"
    )


def _generate_perbeat_candidate(
    *,
    scene_contract: dict[str, Any],
    beat_chain: list[Any],
    seed: list[Any] | None = None,
    structure_type: str = "",
    mechanism: str = "",
    mom_lines_max: int = 3,
    banned_literals: list[str] | None = None,
    source_type: str = "",
    temperature: float = 0.5,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """逐拍填词：按骨架整篇填一次，最多返修两轮，再交回统一硬校验。"""
    _beats = [b for b in beat_chain if isinstance(b, dict)]
    # 多铺候选槽供不合格插话丢弃；实际句数/总字数仍由统一硬校验决定。
    # 每句至多22字，在生成时守住均句长度，避免验过后再截掉剧情条件。
    # 多铺一槽是坏句缓冲：插话判废后仍要保住 ≥12 句，不能一删就掉到 11。
    # 12 句是硬下限；多铺一槽会往同一拍后塞第三条反应，
    # 终检常把它们判成同一理由换词重复（#138 实测：老虎比喻后三条
    # 都在用「端饺子/问饺子」开脱）。先填满 12 句，再按硬校验决定去留。
    from app.services.gold_story.scene import chat_line_cap

    # 拍比 12 还多时按拍数排（每拍至少一句）；超过句数上限说明契约拍拆太碎。
    beats = [b for b in beat_chain or [] if isinstance(b, dict)]
    line_cap = chat_line_cap(structure_type)
    if len(beats) > line_cap:
        raise ValueError(
            f"perbeat: 契约 {len(beats)} 拍 > 句数上限 {line_cap}"
        )
    target = max(LINE_PLAN_TARGET_LINES, len(beats))
    logger.debug(
        "[GOLD_CHAT] perbeat target=%s beats=%s legacy=%s",
        target,
        len(beats),
        _perbeat_legacy(),
    )
    def _legacy_slots() -> list[dict[str, Any]]:
        return _perbeat_apply_intent_cover(
            _apply_n_word_slots(
                _perbeat_slots(
                    beat_chain, scene_contract, target_lines=target, seed=seed
                ),
                structure_type=structure_type,
            )
        )

    # 没有契约拍就无从规划（历史调用/单测只造槽）：退回旧规则。
    has_beats = any(isinstance(b, dict) for b in beat_chain or [])
    payload = (row or {}).get("payload")
    if not isinstance(payload, dict):
        payload = {}
    # 两种路径都要带上源故事（line_plan 写 intent 要用；成稿落 source_raw 供终检）。
    story_raw = str(
        (row or {}).get("story_raw") or payload.get("story_raw") or ""
    )
    slots: list[dict[str, Any]] = []
    if not (_perbeat_legacy() or not has_beats):
        # 哪些角色「源素材里根本没出声」（#144 的旁观角色灿灿）：这些角色的补位
        # 行没有内容可依，规划与机检都走「零素材插话」的口径（旁观/递话/助威），
        # 否则模型只能转述/复述上一句（实测三轮都是旁白式转述）。
        _seed_queue = _perbeat_seed_queues(
            seed,
            beats=[b for b in beat_chain or [] if isinstance(b, dict)],
            punchline=str(scene_contract.get("punchline") or ""),
        )
        _material = {sp for sp, items in _seed_queue.items() if items}
        _cast = {
            str(x).strip()
            for x in (scene_contract.get("characters") or [])
            if str(x).strip()
        }
        _cast.update(_line_plan_speakers(beat_chain))
        no_material_speakers = {sp for sp in _cast if sp not in _material}
        try:
            plan = _build_line_plan(
                scene_contract=scene_contract,
                beat_chain=beat_chain,
                story_raw=story_raw,
                target_lines=target,
                temperature=temperature,
                no_material_speakers=no_material_speakers,
            )
        except ValueError as exc:
            # 骨架排不出 / intent 两轮不合格：退回旧槽，但要让日志能看见。
            logger.warning("[GOLD_CHAT] line_plan 未采用，回退旧槽: %s", exc)
        else:
            slots = _perbeat_apply_intent_cover(
                _apply_n_word_slots(
                    _line_plan_slots(
                        plan,
                        beat_chain,
                        no_material_speakers=no_material_speakers,
                    ),
                    structure_type=structure_type,
                )
            )
    if not slots:
        slots = _legacy_slots()
    if not slots:
        raise ValueError("perbeat: empty skeleton")
    # 契约拍声明的必现语义点挂到槽上：批提示词里要写出来，否则模型不知道
    # 哪些词不能砍（#144 run26 实测：beat5 每轮都砍掉句尾的「疼妈妈」）。
    slots = _apply_required_semantic_points(slots, beat_chain)
    punchline = str(scene_contract.get("punchline") or "").strip()
    retry_feedback = format_retry_missing_events_block(row or {})
    lines, failures = _perbeat_fill_slots(
        slots,
        scene_contract=scene_contract,
        punchline=punchline,
        temperature=temperature,
        retry_feedback=retry_feedback,
        source_text=str(story_raw or ""),
    )
    if failures:
        # 契约拍没填出合格句：整条 draft 重掷（外层 draft retry），
        # 交上去只会让后文变成「引用无据」。
        detail = "；".join(f"第{i}句「{ln}」{why}" for i, ln, why in failures[:3])
        raise ValueError(f"perbeat: {len(failures)} line(s) invalid; {detail}")
    # 单句上限是硬卡（24 字）：生成端已按 14–24 判过，但返修轮拼进来的句子
    # 仍可能超（#138 实测：`单句过长(max=26>24)` 让整轮修稿预算白烧）。
    lines = [
        (sp, _perbeat_clip(ln, limit=24) if len(ln) > 24 else ln)
        for sp, ln in lines
    ]
    # 均句长度不再设限（2026-10 清理）：验收端的「均句过长」硬卡已删，
    # 拼装前还按均值截句只会把本来合格的长句截掉剧情条件——被删的那张卡
    # 说均句均值反映不了稿子好坏，这里也就不该为它截句子。
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN as _CHAT_MIN

    if len(slots) >= _CHAT_MIN and len(lines) < _CHAT_MIN:
        # 逐拍填词按槽质检，不合格的槽会被丢掉；某次抽到丢句多就只剩 8–9 句。
        # 以前这种半成品仍被当候选交下去，终检再判「对白句数须≥12，当前8」，
        # 白烧最后那轮修稿预算（#138 实测 12:21 那条 failure）。缺口大到本地
        # 补位（软插话保留到 12 句）也救不回来时，按「短稿」抛错，让候选循环
        # 直接换一稿重抽。
        raise ValueError(f"对白句数须≥{_CHAT_MIN}，当前{len(lines)}")

    data = {
        "scene_title": str((row or {}).get("title") or ""),
        # validate 的必填字段：逐拍生成只管对白，其余字段从契约原地补齐，
        # 否则缺字段会让 validate 直接失败并把整篇丢给 LLM 重写。
        "setting": str(scene_contract.get("location") or "").strip() or "餐桌",
        "key": _perbeat_key_from_object(str(scene_contract.get("object") or "")),
        "conflict_core": str(scene_contract.get("conflict") or ""),
        "story_type": str(structure_type or "").strip().upper(),
        "dialogue": [{"speaker": sp, "line": ln} for sp, ln in lines],
        "punchline_explain": str(scene_contract.get("punchline") or "").strip()
        or str(scene_contract.get("closing_intent") or "").strip()
        or str(scene_contract.get("conflict") or ""),
        "gold_beat_chain": beat_chain,
        # 源故事原文带上：终检判「语病」时要用它区分「作者原句」与「模型硬编」。
        "source_raw": story_raw,
    }
    logger.info(
        "[GOLD_CHAT] perbeat assembled lines=%s chars=%s",
        len(lines),
        len("".join(ln for _sp, ln in lines)),
    )
    if str(os.environ.get("GOLD_CHAT_DEBUG_DUMP") or "") == "1":
        # 逐拍原稿落盘：和 _debug_dump_expand 的产物对比，就能看出是哪个
        # 后处理环节把好句子改坏的（垫字、插池子对、换说话人）。
        try:
            Path(
                f"/tmp/gold_chat_raw_{row.get('source_id') if row else 'x'}.json"
            ).write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001 调试落盘失败不影响主流程
            pass
    return _validate_expand_chat(
        _normalize_chat_speakers(data),
        banned_literals=list(banned_literals or []),
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

def _snippet_for_contract(
    scene_contract: dict[str, Any],
    source_id: str,
) -> str:
    """金稿正例注入：两人手契约下不注入。

    金稿正例是另一部片子（《画作争夺战》），人物固定为灿灿/昭昭 双孩交替。
    两人手契约（家长 × 单孩）下把这段摆给模型，等于同时教它「加一个孩子」
    和「两人交替」——实测成稿会反复冒出契约外的灿灿，随后被角色表闸门拦死。
    两人手不需要学双孩节奏，直接不注入。
    """
    cast = [
        str(c).strip()
        for c in (scene_contract.get("characters") or [])
        if str(c).strip()
    ]
    beat_speakers = {
        str(row.get("speaker") or "").strip()
        for row in (scene_contract.get("beat_chain") or [])
        if isinstance(row, dict) and str(row.get("speaker") or "").strip()
    }
    if cast and beat_speakers:
        cast = [c for c in cast if c in beat_speakers] or cast
    parents = {"妈妈", "爸爸"}
    kids = [c for c in cast if c not in parents]
    if len(kids) == 1 and any(c in parents for c in cast):
        return ""
    return resolve_gold_chat_snippet(source_id)


# 正文 240 字的两个杠杆：句数与每句长度。儿童口语的自然长度是 15–17 字，
# 12 句就必须每句均 20 字——口语化与字数下限互相打架，本地补字上限只有
# 几十字，缺口稍大就必然补不满（#87 实测：12 句稿反复停在 200–230 字）。
# 句数上限是 24，句数是零成本的杠杆，故 N 类按「儿童自然句长」反推目标句数。
_N_CHAIN_KEY_LINE_RE = re.compile(
    r"只说出这个词|解释这个词|苹果|怪词|蹦出|冒出"
)
_N_NATURAL_LINE_CHARS = 15
_N_TARGET_LINE_COUNT = 12


# 补位 intent 里出现这些形态，等于要求模型凭空造一个新实体（人/地点/道具/
# 时间），而终检对此的判词是「缺前提 / 引用无据」。补位只允许对已出口的
# 内容做深化（坚持/反问/复述/推进一格），不允许新开事实。
_N_PAD_NEW_ENTITY_RE = re.compile(
    r"具体是谁|那个人|什么人|叫什么名|称呼即可|谁那儿|听来的|"
    r"什么地方|在哪儿|哪个地方|地点|"
    r"什么时候|哪天|几点|"
    r"手里|身上|什么样子|模样|穿着|"
    r"新的人|新的词|新的细节|另一个人|另一个人名"
)


def _pad_intent_requires_new_entity(intent: str) -> bool:
    """补位 intent 是否在要求一个对白里还不存在的新实体。

    这是防复发的机读不变量：往 seed 里塞「让他说出那个人是谁 / 在哪儿看见的」
    这类要点，模型只能编，编完必被终检判「缺前提/引用无据」，
    几轮下来修稿预算全部烧在解释自己编的东西上（#87 实测 19 轮仅 2 通过）。
    补字只能靠深化，不能靠加人加物。
    """
    text = str(intent or "")
    return bool(_N_PAD_NEW_ENTITY_RE.search(text))


def _filter_pad_extras(
    extras: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """滤掉会逼模型造新实体的补位要点，并回报被滤掉的条目。"""
    kept: list[dict[str, str]] = []
    dropped: list[str] = []
    for item in extras:
        intent = str(item.get("intent") or "")
        if _pad_intent_requires_new_entity(intent):
            dropped.append(intent)
            continue
        kept.append(item)
    return kept, dropped


def _expand_seed_for_line_floor(
    seed: list[Any] | None,
    *,
    structure_type: str = "",
    mechanism: str = "",
    characters: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> list[Any]:
    """seed 条数 <12 时，在收束前插入抽象加码拍，迫使扩写写满句数。

    只改 prompt 用 seed，不写回 DB；intent 抽象，不按单篇物件造句。

    补位说话人**只能用契约 `characters` 里的角色**，且家长条数不超
    ``mom_lines_max``：先前的兜底分支写死「昭昭/灿灿 交替」，在两人手
    契约（家长 × 单孩）里等于让提示词教模型去写一个契约外角色，
    成稿随后被角色表闸门拦死，修稿预算来回空转（#87 实测）。
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
    st = str(structure_type or "").strip().upper()
    # seed 只负责「把要点说全」，不负责凑对白句数：把 seed 硬补到目标句数
    # 会在「出词→解释」「追问→回答」这些必须紧邻的行对之间插话，反而打断
    # 机制链（#87 实测：补到 16 条时成稿句序与契约错位）。
    # 对白句数交给提示词（明确要求 16–18 句、每句 15–20 字）。
    # 目标：把 seed 补到 16 条（= 契约 6 拍 × 每拍 2–3 句），这样扩写有足够
    # 句数落点，正文字数才凑得满 240。关键行对（出词/解释、追问/回答）由下方
    # 的跳过规则保护，不会被插话打断。
    line_target = _N_TARGET_LINE_COUNT if st == "N" else CHAT_LINE_COUNT_MIN
    if n >= line_target:
        return out
    if st != "N":
        # 非 N 的句数不足交给“话轮对”扩写（请求/追问 + 回答/反应）。
        # 过去在主孩子台词后硬插自我表态，模型只能换词重复同一态度，
        # 终检必报重复；seed 条数应由独立事件/话轮决定，不由句数配额决定。
        return out


    # ── 可用说话人：只认契约角色；契约缺失时退回 seed 已有说话人 ──
    cast = [
        str(c).strip() for c in (characters or []) if str(c).strip()
    ]
    if not cast:
        cast = list(
            dict.fromkeys(
                str(x.get("speaker") or "").strip()
                for x in out
                if isinstance(x, dict) and str(x.get("speaker") or "").strip()
            )
        )
    parent_names = {"妈妈", "爸爸"}
    kids = [c for c in cast if c not in parent_names]
    parents = [c for c in cast if c in parent_names]
    # 主孩子 = seed 里台词最多的那个孩子（机制主体），其余孩子不参与补位
    kid_lines: dict[str, int] = {}
    for x in out:
        if not isinstance(x, dict):
            continue
        sp = str(x.get("speaker") or "").strip()
        if sp in kids:
            kid_lines[sp] = kid_lines.get(sp, 0) + 1
    main_kid = max(kid_lines, key=lambda k: kid_lines[k]) if kid_lines else (
        kids[0] if kids else ""
    )
    # 家长额度：已用条数 ≥ 额度时不再插家长拍
    parent_used = sum(
        1
        for x in out
        if isinstance(x, dict)
        and str(x.get("speaker") or "").strip() in parent_names
        and str(x.get("intent") or x.get("line") or "").strip()
    )
    try:
        parent_cap = (
            int(mom_lines_max) if mom_lines_max is not None else parent_used
        )
    except (TypeError, ValueError):
        parent_cap = parent_used
    parent_room = max(0, parent_cap - parent_used)
    main_parent = parents[0] if parents else ""

    if is_m8_j_domination(mechanism=mechanism, structure_type=st):
        extras = [
            {"speaker": main_kid, "intent": "不服继续顶撞/扭打升级"},
            {"speaker": main_kid, "intent": "嘴硬应战要对方出招"},
        ]
    elif st == "J":
        extras = [
            {"speaker": main_kid, "intent": "换个理由再求一次"},
            {"speaker": main_kid, "intent": "再保证一次求放行"},
        ]
    elif st == "N":
        # N 字数缺口只能靠**把同一个荒诞点往深处挖**来补，不能靠「往宽处铺」。
        # 往宽处铺（新的人名/地点/道具/关系）会立刻触发终检的
        # 「缺前提 / 引用无据」——新实体在对白里没有依据（#87 实测十余次）。
        # 深度动作的共同点：不引入任何新实体，只是对已说出口的内容
        # 坚持、反问、复述、推进一格。
        # 只允许「对已发生的事实做自我表态」：不描述外形（会写成旁白）、
        # 不假设对方态度（会写成替对方安想法）、不要求对方动作（会写成指挥）。
        extras = [
            {"speaker": main_kid, "intent": "重申自己刚才那句是真的，不改口"},
            {"speaker": main_kid, "intent": "说明自己是认真讲的，不是随口说"},
            {"speaker": main_kid, "intent": "表示这些名字都记得住，一个都不会忘"},
            {"speaker": main_kid, "intent": "强调自己没有乱说，也没有骗人"},
            {"speaker": main_kid, "intent": "说明自己讲这件事的时候很确定"},
            {"speaker": main_kid, "intent": "表示随便怎么问，答案还是这个"},
        ]
    else:
        extras = [
            {"speaker": main_kid, "intent": "换个理由再顶一句"},
            {"speaker": main_kid, "intent": "加码争一次"},
        ]
    extras = [e for e in extras if e["speaker"]]
    # 机读不变量：补位一律不得要求新实体（否则模型只能编，随后被终检判无据）
    extras, _dropped_extras = _filter_pad_extras(extras)
    if _dropped_extras:
        logger.info(
            "seed floor pad: 剔除造实体补位 %s", _dropped_extras[:3],
        )
    if not extras:
        return out

    # ── 补位规则（唯一一套，不再叠加重叠守卫）────────────────────────────
    # 只做一件事：在**每句孩子台词之后**补一句自我表态，把该拍扩成两句。
    # 允许的位置必须同时满足：
    #   1) 该句是孩子说的，且不是怪词/解释/补词这类机制关键行；
    #   2) 该句不在怪词行之前（先说怪词再表态，否则答非所问）；
    #   3) 该句在收束行之前（收束之后不再接话）；
    #   4) 该句后面还没补过（每句最多扩成两句）。
    # 不满足就跳过，补不满就交给提示词——绝不为了凑数把补位塞到错位置。
    token_at = next(
        (
            k
            for k, r in enumerate(out)
            if isinstance(r, dict) and _N_CHAIN_KEY_LINE_RE.search(str(r.get("intent") or ""))
        ),
        -1,
    )
    close_at = next(
        (
            k
            for k, r in enumerate(out)
            if isinstance(r, dict)
            and str(r.get("speaker") or "").strip() in {"妈妈", "爸爸"}
            and re.search(
                r"收束|认栽|服了|打草稿|决定以后|接不住",
                str(r.get("intent") or ""),
            )
        ),
        len(out),
    )
    ei = 0
    insert_at = 1
    while n < line_target and ei < len(extras) and insert_at < len(out):
        idx = insert_at
        row = out[idx]
        ok = (
            isinstance(row, dict)
            and str(row.get("speaker") or "").strip() == main_kid
            and not _N_CHAIN_KEY_LINE_RE.search(str(row.get("intent") or ""))
            and (token_at < 0 or idx > token_at)
            and idx < close_at
            and not str(row.get("_n_pad") or "")
            and not (
                idx + 1 < len(out)
                and isinstance(out[idx + 1], dict)
                and str(out[idx + 1].get("_n_pad") or "")
            )
        )
        if not ok:
            insert_at += 1
            continue
        extra = dict(extras[ei])
        ei += 1
        extra["_n_pad"] = "1"
        out.insert(idx + 1, extra)
        n += 1
        # 插完跳过刚插入的补位行，避免在同一处继续堆
        insert_at = idx + 2

    # 清理内部标记，不污染提示词
    for row in out:
        if isinstance(row, dict):
            row.pop("_n_pad", None)
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

def _retry_missing_events_block(row: dict[str, Any]) -> str:
    """甲重掷时的「上一轮缺拍」提示块；无重掷反馈时返回空串。"""
    from app.services.gold_story.gold_chat.prompts import (
        format_retry_missing_events_block,
    )

    try:
        return format_retry_missing_events_block(row)
    except Exception as exc:  # pragma: no cover - 提示词辅助不得阻断出稿
        logger.debug("[GOLD_CHAT] retry missing-events block skipped: %s", exc)
        return ""


def _has_non_short_hard_errors(msg: str) -> bool:
    """缺字段/家长句/精修失败等硬错：勿只走短篇幅 FIX。"""
    text = str(msg or "")
    return (
        "缺少字段" in text
        or "punchline_explain" in text
        or "妈妈台词须" in text
        or "爸爸台词须" in text
        or "家长台词须" in text
        or "key 须" in text
        or "align_refine_failed:" in text
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

def _restore_extra_parent_speakers_from_baseline(
    draft: dict[str, Any],
    baseline: dict[str, Any],
    *,
    parent_lines_max: int,
) -> tuple[dict[str, Any], bool]:
    """结构修稿只把原姐弟槽改成家长时，按 baseline 还原 speaker，避免删正文。"""
    import copy

    rows = draft.get("dialogue")
    base_rows = baseline.get("dialogue")
    if not isinstance(rows, list) or not isinstance(base_rows, list):
        return draft, False
    if len(rows) != len(base_rows):
        return draft, False

    parents = {"妈妈", "爸爸"}
    siblings = {"昭昭", "灿灿"}
    base_parent_n = sum(
        1
        for item in base_rows
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() in parents
    )
    draft_parent_n = sum(
        1
        for item in rows
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() in parents
    )
    target = min(max(0, int(parent_lines_max)), base_parent_n)
    if draft_parent_n <= target:
        return draft, False

    out = copy.deepcopy(draft)
    out_rows = out.get("dialogue")
    if not isinstance(out_rows, list):
        return draft, False
    changed = False
    current = draft_parent_n
    for base_item, item in zip(base_rows, out_rows, strict=False):
        if current <= target:
            break
        if not isinstance(base_item, dict) or not isinstance(item, dict):
            continue
        base_speaker = str(base_item.get("speaker") or "").strip()
        draft_speaker = str(item.get("speaker") or "").strip()
        if draft_speaker not in parents or base_speaker not in siblings:
            continue
        item["speaker"] = base_speaker
        current -= 1
        changed = True
    return (out, True) if changed else (draft, False)


def _trim_gold_chat_mom_lines(
    story: dict[str, Any],
    *,
    mom_lines_max: int = 1,
    structure_type: str = "",
    parent_lines_max: int | None = None,
    dad_lines_max: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """家长句超限：先合并连续句；N 类保护关键追问，其余优先保留末段。

    口径与 validate.validate_chat_hard 共用 resolve_parent_lines_budget：
    妈妈≤mom_max、爸爸≤dad_max、家长合计≤parent_max。
    """
    import copy

    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom_max, dad_max, parent_max = resolve_parent_lines_budget(
        story,
        mom_lines_max=mom_lines_max,
        dad_lines_max=dad_lines_max,
        parent_lines_max=parent_lines_max,
    )
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    if mom_max <= 0 and dad_max <= 0 and parent_max <= 0:
        kept = [
            item
            for item in dialogue
            if not (
                isinstance(item, dict)
                and str(item.get("speaker") or "").strip() in {"妈妈", "爸爸"}
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

    def _count(dlg: list[Any], speaker: str) -> int:
        return len(
            [
                item
                for item in dlg
                if isinstance(item, dict)
                and str(item.get("speaker") or "").strip() == speaker
            ]
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

    parent_idxs = [
        idx
        for idx, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() in {"妈妈", "爸爸"}
    ]
    if (
        _count(dialogue, "妈妈") <= mom_max
        and _count(dialogue, "爸爸") <= dad_max
        and len(parent_idxs) <= parent_max
    ):
        return (out, changed) if changed else (story, False)

    # 超限：按 speaker 各自上限与合计上限一起裁。优先保末段收束与开场触发，再保 N 追问。
    protected: list[int] = []
    if str(structure_type or "").strip().upper() == "N":
        from app.services.daily_story.story_types.n.validate import RE_WHY

        protected = [
            idx
            for idx in parent_idxs
            if isinstance(dialogue[idx], dict)
            and str(dialogue[idx].get("speaker") or "").strip() == "妈妈"
            and RE_WHY.search(str(dialogue[idx].get("line") or ""))
        ][:1]

    keep_order: list[int] = []
    if parent_idxs:
        keep_order.append(parent_idxs[-1])
        keep_order.append(parent_idxs[0])
    for idx in [*protected, *reversed(parent_idxs)]:
        if idx not in keep_order:
            keep_order.append(idx)

    def _speaker_of(idx: int) -> str:
        item = dialogue[idx]
        return str(item.get("speaker") or "").strip() if isinstance(item, dict) else ""

    keep_set: set[int] = set()
    speaker_cap = {"妈妈": mom_max, "爸爸": dad_max}
    used = {"妈妈": 0, "爸爸": 0}
    for idx in keep_order:
        if len(keep_set) >= parent_max:
            break
        sp = _speaker_of(idx)
        if sp not in speaker_cap:
            continue
        if used[sp] >= speaker_cap[sp]:
            continue
        keep_set.add(idx)
        used[sp] += 1

    drop = set(parent_idxs) - keep_set
    if not drop:
        return (out, changed) if changed else (story, False)
    out["dialogue"] = [
        item for idx, item in enumerate(dialogue) if idx not in drop
    ]
    return out, True

def _apply_gold_chat_local_hard_repairs(
    story: dict[str, Any],
    *,
    structure_type: str = "",
    mom_lines_max: int = 1,
    parent_lines_max: int | None = None,
    dad_lines_max: int | None = None,
) -> dict[str, Any]:
    """校验前本地硬修复：补 punchline、裁家长句。"""
    data = _ensure_gold_chat_punchline_explain(
        story, structure_type=structure_type
    )
    data, _ = _trim_gold_chat_mom_lines(
        data,
        mom_lines_max=mom_lines_max,
        structure_type=structure_type,
        parent_lines_max=parent_lines_max,
        dad_lines_max=dad_lines_max,
    )
    # 站外称谓（哥哥/弟弟）改站内名：硬卡 collect_voice_errors 见到即拦，
    # 而改写是无损的（只换称谓词），必须在**校验前**做，否则每轮都白拦
    # （#135 实测：refine 循环里 5 处命中反复驳回，到 finalize 才修已来不及）。
    from app.services.gold_story.gold_chat.patch import (
        apply_kinship_label_patch,
    )

    data, _kin_notes = apply_kinship_label_patch(data)
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
    k_close_mode: str = "",
    *,
    contract: dict[str, Any] | None = None,
) -> str:
    from app.services.gold_story.gold_chat.type_bridge import (
        structure_type_hint,
    )
    from app.services.gold_story.scene import fact_role_pair

    challenger, authority = fact_role_pair(contract)
    return structure_type_hint(
        structure_type=structure_type,
        mechanism=mechanism,
        closing_mode=closing_mode,
        k_close_mode=k_close_mode,
        challenger=challenger,
        authority=authority,
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

def gold_story_to_gold_chat(
    row: dict[str, Any],
    *,
    repair_budget: Any | None = None,
) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    from app.services.gold_story.gold_chat.repair import (
        GoldChatRepairBudget,
        GoldChatRepairExhausted,
        build_candidate_repair_feedback,
        prepare_candidate_for_acceptance,
        prepare_candidate_for_acceptance_after_local_length_close,
    )

    budget: GoldChatRepairBudget = (
        repair_budget
        if isinstance(repair_budget, GoldChatRepairBudget)
        else GoldChatRepairBudget(max_repairs=2, reserve_final=1)
    )
    row = _repair_i_row_contract(row)
    row = _repair_k_row_contract(row)
    row, _structure_notes = _resolve_structure_row(row)
    _gate_forced_m14_p_or_raise(row)
    payload = cast(dict[str, Any], row.get("payload") or {})
    structure_type = str(row.get("structure_type") or "A").strip().upper()
    st_label = structure_type_label(structure_type)
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    # 每拍补 min_turns（可落地最小回合数），保证契约能撑起正文最少句数；
    # 旧存量契约没有该字段，读出来时统一补齐，生成侧才有明确回合额度。
    from app.services.gold_story.scene import normalize_beat_min_turns

    scene_contract, _turns_notes = normalize_beat_min_turns(scene_contract)
    if _turns_notes:
        logger.info("gold_chat beat min_turns: %s", "；".join(_turns_notes))
        if isinstance(payload.get("scene_contract"), dict):
            payload["scene_contract"] = scene_contract
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
    k_close_mode = str(
        payload.get("k_close_mode")
        or scene_contract.get("k_close_mode")
        or ""
    ).strip()
    if structure_type == "K" and isinstance(seed, list):
        from app.services.daily_story.story_types import (
            sanitize_gold_chat_dialogue_seed,
        )

        seed = sanitize_gold_chat_dialogue_seed(
            seed,
            structure_type="K",
            k_close_mode=k_close_mode,
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
    # 家长额度必须走 resolve_parent_lines_budget，不能照抄契约原值：
    # 该函数含「按 beat 拍数抬额」与「只到一位家长时另一位让出额度」两层。
    # 直接读契约值会让扩写/精修阶段按比实际更紧的额度裁句，合规稿被判超限
    # （#138 实测：契约 3、实际可用 4，妈妈第 4 句被裁 → 终检报缺前提）。
    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom_max, _dad_budget, _parent_budget = resolve_parent_lines_budget(
        scene_contract,
        mom_lines_max=scene_contract.get("mom_lines_max"),
    )
    beat = payload.get("beat") if isinstance(payload.get("beat"), list) else []
    closing = _resolve_closing_intent(
        payload,
        scene_contract,
        structure_type=structure_type,
        k_close_mode=k_close_mode,
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
        k_close_mode=k_close_mode,
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
            characters=scene_contract.get("characters") or [],
            mom_lines_max=mom_int,
        )
        user = _USER.format(
            title=str(row.get("title") or ""),
            mechanism=mechanism,
            structure_type=structure_type,
            structure_label=st_label,
            conflict_core=conflict_core[:500],
            cast_block=format_cast_block(scene_contract),
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
            retry_missing_events_block=_retry_missing_events_block(row),
            dialogue_seed=_format_dialogue_seed(prompt_seed)[:4000],
            seed_span_block=format_seed_span_block(
                prompt_seed,
                structure_type=structure_type,
                mechanism=mechanism,
            ),
            seed_skeleton_block=format_seed_skeleton_block(prompt_seed),
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
                k_close_mode,
                contract=scene_contract,
            ),
            align_block=align_block,
            gold_chat_snippet=_snippet_for_contract(scene_contract, str(row.get("source_id") or "")),
            safe_lo=SAFE_LINE_CHARS_LO,
            safe_hi=SAFE_LINE_CHARS_HI,
            **_prompt_budget_kwargs(),
        )
        candidates: list[dict[str, Any]] = []
        hit_truncation = False
        hit_short = False
        # 逐拍路径固定 1 稿：一稿要 1 次 line_plan + 1~3 次整表填词，再做
        # best-of-2 就是翻倍等待（#138 实测单次跑进 2–3 分钟）。措辞不好由
        # 外层 draft retry 带反馈重抽，不在这里并行烧两份。
        candidate_count = 1 if _perbeat_enabled() else EXPAND_CANDIDATE_COUNT
        for attempt_no in range(candidate_count):
            logger.debug(
                "[GOLD_CHAT] expand candidate %s/%s …",
                attempt_no + 1,
                EXPAND_CANDIDATE_COUNT,
            )
            try:
                if _perbeat_enabled():
                    # 逐拍填词：一拍一次调用，说话人由骨架锁死，根治张冠李戴
                    candidates.append(
                        _generate_perbeat_candidate(
                            scene_contract=scene_contract,
                            beat_chain=beat_chain,
                            seed=seed,
                            structure_type=structure_type,
                            mechanism=mechanism,
                            mom_lines_max=mom_int,
                            banned_literals=banned_list,
                            source_type=source_type,
                            temperature=expand_temperature,
                            row=row,
                        )
                    )
                else:
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
            except Exception as exc:  # noqa: BLE001 逐拍调用次数多，网络抖动不该炸整条
                last_err = f"network:{exc}"
                logger.warning(
                    "[GOLD_CHAT] expand candidate network fail: %s",
                    str(exc)[:160],
                    exc_info=not isinstance(exc, (TimeoutError, ConnectionError)),
                )
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
        from app.services.gold_story.gold_chat.convert import (
            _attach_gold_chat_structure_score,
            _gate_gold_chat_structure_score,
            _gold_chat_j_pre_score_polish,
            _post_align_j_closing_touchup,
            _realign_j_role_speakers,
            patch_break_consecutive_keep_seed,
            patch_collapse_empty_sibling_repeats,
            patch_score_propaganda_speakers,
            patch_seed_order_align,
            patch_seed_premise_align,
            patch_seed_speaker_align,
        )

        # 旁路收束模式随稿走入 align/G 硬卡（不改 structure_type）。必须写在
        # if/else 之外：逐拍分支也要落盘，否则 validate 里按 closing_mode 分支的
        # 硬卡（authority 开场立规、G 收束）读不到模式会**静默跳过**。
        closing_mode = str(payload.get("closing_mode") or "").strip()
        if closing_mode:
            data = dict(data)
            data["closing_mode"] = closing_mode
        if k_close_mode:
            data = dict(data)
            data["k_close_mode"] = k_close_mode

        if _perbeat_enabled():
            # 逐拍模式：骨架已按契约拍序锁死说话人，每句都是按拍写出来的，
            # 下面整条补丁链是给「整篇自由扩写」善后用的（换池子句、按 seed
            # 重排、补垫字对、LLM 精修重写）。套在逐拍稿上只会把好句子换成
            # 池子话（#138 实测：12 次复跑全部卡在这一段，接不上/错位/缺前提）。
            from app.services.gold_story.scene import (
                patch_dialogue_narration_to_speech,
            )

            _pb_notes = patch_dialogue_narration_to_speech(data)
            if _pb_notes:
                logger.info(
                    "gold_chat perbeat narration fix: %s", len(_pb_notes)
                )
            if closing_mode == "authority_punchline":
                # 权威开场兜底是「换说话人 + 插立规句」的整段改写，与逐拍锁死
                # 拍序冲突。这里不静默跳过：留日志，便于回查硬卡到底是谁报的。
                logger.info(
                    "gold_chat perbeat skip authority opening patch (closing_mode=%s)",
                    closing_mode,
                )
        else:
            # 类型本地补丁先于精修（align），避免 C 回旋镖等只能靠 LLM 精修
            from app.services.daily_story.story_types import (
                apply_gold_chat_body_pipeline,
            )

            data["gold_beat_chain"] = beat_chain
            data, type_notes = apply_gold_chat_body_pipeline(
                data,
                structure_type=structure_type,
                dialogue_seed=seed,
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
            # 导入放在 if/else 之外（见下方 chat = data 之后的精修收口）：
            # 逐拍分支也要用到这些函数，放在 else 里会 UnboundLocalError。

            # 逐拍模式：seed 补拍/拍序归位会把 seed 原句再插一遍（#138 实测
            # 14 句被补到 18 句、灿灿五句同一句式追问，判「重复」整稿退回）。
            if not _perbeat_enabled():
                data, seed_changed = patch_seed_speaker_align(data, dialogue_seed=seed)
                if seed_changed:
                    type_notes = list(type_notes) + ["seed角色归位"]
                data, premise_changed = patch_seed_premise_align(
                    data, dialogue_seed=seed
                )
                if premise_changed:
                    type_notes = list(type_notes) + ["seed前提补回"]
                data, order_changed = patch_seed_order_align(data, dialogue_seed=seed)
                if order_changed:
                    type_notes = list(type_notes) + ["seed拍序归位"]
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
            if not _perbeat_enabled():
                # 逐拍模式已在骨架层保证句数/字数；再垫字只会灌池子句（见上）
                data, _ = _ensure_gold_chat_min_chars(
                    data,
                    mechanism=mechanism,
                    structure_type=structure_type,
                    beat_chain=beat_chain,
                    dialogue_seed=seed if isinstance(seed, list) else None,
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
            data, request_premise_notes = ensure_request_premise_dialogue(
                data,
                dialogue_seed=seed if isinstance(seed, list) else None,
            )
            if request_premise_notes:
                type_notes = list(type_notes) + request_premise_notes
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
                    data,
                    structure_type="Q",
                    dialogue_seed=seed,
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
        _debug_dump_expand(chat, str(row.get("source_id") or ""))
        try:
            from app.services.gold_story.gold_chat.refine import (
                refine_gold_chat_align,
                REFINE_MAX_ROUNDS,
            )
            # 逐拍模式不再走 LLM 精修：稿子是一句一句按拍写出来的，align 精修
            # 会把整篇重写一遍，重新引入张冠李戴（#138 实测：精修后第 5 句把
            # 比喻当实体、第 9 句换成池子话「你这话我可接不住」、第 10 句答非所问）。
            # 逐拍模式下契约的追问/自洽/愣住三个词槽已在骨架层钉死，结构分由
            # 下方 _gate_gold_chat_structure_score 把关，不合格就重掷。
            chat = data if _perbeat_enabled() else refine_gold_chat_align(
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
                repair_budget=budget,
            )
            # align 精修可能又写回弱判据/连说；收口再垫一次
            chat, _ = patch_c_force_sibling_alternate(chat)
            chat, _ = patch_c_possession_criterion(chat)
            chat, _ = patch_sanitize_c_tone_stack(chat)
            chat, _ = patch_sanitize_pad_suffix(chat)
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
                theme=remap_source_kinship(
                    str(row.get("title") or chat.get("scene_title") or "")
                ),
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
            if (
                str(structure_type or "").upper() == "G"
                and str(mechanism or "").upper() == "M4"
            ):
                from app.services.gold_story.gold_chat.convert import (
                    patch_gold_chat_consecutive_siblings,
                )

                before_g_chars = dialogue_total_chars(chat)
                chat, g_consecutive_notes = patch_gold_chat_consecutive_siblings(
                    chat,
                    dialogue_seed=seed if isinstance(seed, list) else None,
                )
                if g_consecutive_notes:
                    if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
                        chat, _ = _boost_short_with_mid_lines(
                            chat,
                            mechanism=mechanism,
                            structure_type="G",
                            beat_chain=beat_chain,
                            dialogue_seed=seed if isinstance(seed, list) else None,
                        )
                    logger.info(
                        "gold_chat pre-score G behavior consecutive close chars=%s->%s notes=%s",
                        before_g_chars,
                        dialogue_total_chars(chat),
                        "；".join(g_consecutive_notes[:6]),
                    )
            # 留在当前候选上修复；预算耗尽才退出，不丢稿重抽。
            repair_error = ""
            while True:
                # 评分前先过一遍 N 契约补丁：同人连说/换词重复/句数额度都会被
                # 结构分直接扣分，补丁是确定性的，先清再评分（幂等）。
                if str(structure_type or "").strip().upper() == "N":
                    from app.services.gold_story.gold_chat.patch import (
                        apply_n_contract_local_patches,
                    )

                    chat, n_pre_notes = apply_n_contract_local_patches(
                        chat,
                        beat_chain=beat_chain,
                        dialogue_seed=seed if isinstance(seed, list) else None,
                        mom_lines_max=mom_int,
                    )
                    if n_pre_notes:
                        logger.info(
                            "gold_chat pre-score N contract patch: %s",
                            "；".join(n_pre_notes),
                        )
                chat, candidate_errors = prepare_candidate_for_acceptance(
                    chat, mom_lines_max=mom_int, banned_literals=banned_list,
                )
                chat = _attach_gold_chat_structure_score(chat, row)
                structure_gate_ok = True
                try:
                    _gate_gold_chat_structure_score(chat)
                except ValueError as gate_exc:
                    structure_gate_ok = False
                    candidate_errors.append(str(gate_exc))
                if not candidate_errors:
                    return chat

                # post-align / type patch 可能把已达标正文重新压短；机械门槛先本地收口，
                # 再完整复验。只有剩余真实结构问题才允许消耗共享 repair budget。
                before_local_chars = dialogue_total_chars(chat)
                local_closed, local_length_changed = _stabilize_local_length_candidate(
                    chat,
                    structure_type=structure_type,
                    mechanism=mechanism,
                    beat_chain=beat_chain,
                    dialogue_seed=seed if isinstance(seed, list) else None,
                )
                if local_length_changed:
                    chat, candidate_errors = prepare_candidate_for_acceptance_after_local_length_close(
                        local_closed,
                        mom_lines_max=mom_int,
                        banned_literals=banned_list,
                        structure_type=structure_type,
                        mechanism=mechanism,
                    )
                    chat = _attach_gold_chat_structure_score(chat, row)
                    structure_gate_ok = True
                    try:
                        _gate_gold_chat_structure_score(chat)
                    except ValueError as gate_exc:
                        structure_gate_ok = False
                        candidate_errors.append(str(gate_exc))
                    logger.info(
                        "gold_chat expand_structure local length close chars=%s->%s "
                        "score=%s remaining_errors=%s",
                        before_local_chars,
                        dialogue_total_chars(chat),
                        (chat.get("quality") or {}).get("structure_score"),
                        "；".join(candidate_errors[:4]) or "none",
                    )
                    if not candidate_errors:
                        return chat

                mode_errors = list(candidate_errors)
                feedback_errors = list(candidate_errors)
                if repair_error:
                    feedback_errors.append(repair_error)
                last_err = "；".join(feedback_errors)
                quality = chat.get("quality") or {}
                logger.info(
                    "gold_chat candidate rejected stage=expand_structure "
                    "score=%s used=%s remaining=%s errors=%s",
                    quality.get("structure_score"), budget.used, budget.remaining, last_err,
                )
                if not budget.consume(stage="expand_structure", reason=last_err):
                    raise GoldChatRepairExhausted(
                        stage="expand_structure", reason=last_err, candidate=chat,
                    )
                baseline = copy.deepcopy(chat)
                short_only = is_expand_short_only_repair(
                    mode_errors, structure_gate_ok=structure_gate_ok,
                )
                beat_chain_raw = scene_contract.get("beat_chain")
                beat_chain_for_open = (
                    beat_chain_raw if isinstance(beat_chain_raw, list) else None
                )
                opening_ok = opening_causality_passes(
                    chat,
                    beat_chain_for_open,
                    mom_lines_max=mom_int,
                )
                if short_only and not opening_ok:
                    short_only = False
                try:
                    if short_only:
                        editable = list_short_spot_editable_line_nos(
                            chat, freeze_opening=opening_ok,
                        )
                        spot_fb = build_short_only_spot_fix_feedback(
                            chat,
                            validation_errors=feedback_errors,
                            mom_lines_max=mom_int,
                            editable_line_nos=editable,
                        )
                        draft = _short_spot_fix_chat_with_llm(
                            chat,
                            spot_fb,
                            editable_line_nos=editable,
                            banned_literals=banned_list,
                            mom_lines_max=mom_int,
                        )
                    else:
                        fb = build_candidate_repair_feedback(
                            chat, validation_errors=feedback_errors, align_issues=[],
                            mom_lines_max=mom_int,
                        ) + "\n" + format_structure_score_feedback(last_err, chat)
                        if gaps:
                            fb += "\n" + "\n".join(
                                f"- {g}：请在对白中补全，勿另起无关剧情" for g in gaps[:3]
                            )
                        draft = _fix_chat_with_llm(
                            chat, fb, banned_literals=banned_list, mom_lines_max=mom_int,
                        )
                        draft = _normalize_chat_speakers(draft)
                        if structure_type:
                            draft["story_type"] = structure_type
                        draft, _ = patch_c_force_sibling_alternate(draft)
                        draft, _ = patch_c_possession_criterion(draft)
                        draft, _ = patch_sanitize_c_tone_stack(draft)
                        draft, _ = patch_sanitize_pad_suffix(draft)
                        draft, _ = patch_m2_c_structure(
                            draft,
                            structure_type=structure_type,
                            mechanism=mechanism,
                            theme=remap_source_kinship(
                                str(row.get("title") or draft.get("scene_title") or "")
                            ),
                            payload=payload,
                        )
                        draft, _ = _post_align_j_closing_touchup(
                            draft, structure_type=structure_type
                        )
                        if conflict_core:
                            draft["conflict_core"] = conflict_core
                        # 整稿结构修订同样必须先恢复本地硬约束再验收。
                        # 否则 LLM 为补结构新增第 4 句妈妈时，会先被 acceptance 拒稿，
                        # 回滚到原 65 分候选后再烧一次共享 repair budget。
                        # 若整稿修订只是把原有姐弟槽误改成家长 speaker，优先按 baseline
                        # 还原角色，不删台词；只有真实新增/重排的家长句才交给 hard trim。
                        before_parent = sum(
                            1
                            for item in (draft.get("dialogue") or [])
                            if isinstance(item, dict)
                            and str(item.get("speaker") or "").strip() in {"妈妈", "爸爸"}
                        )
                        draft, parent_restored = _restore_extra_parent_speakers_from_baseline(
                            draft,
                            baseline,
                            parent_lines_max=mom_int,
                        )
                        if parent_restored:
                            after_parent = sum(
                                1
                                for item in (draft.get("dialogue") or [])
                                if isinstance(item, dict)
                                and str(item.get("speaker") or "").strip() in {"妈妈", "爸爸"}
                            )
                            logger.info(
                                "gold_chat expand_structure repair restore parent speaker=%s->%s max=%s",
                                before_parent,
                                after_parent,
                                mom_int,
                            )

                        before_mom = sum(
                            1
                            for item in (draft.get("dialogue") or [])
                            if isinstance(item, dict)
                            and str(item.get("speaker") or "").strip() == "妈妈"
                        )
                        draft = _apply_gold_chat_local_hard_repairs(
                            draft,
                            structure_type=structure_type,
                            mom_lines_max=mom_int,
                        )
                        after_mom = sum(
                            1
                            for item in (draft.get("dialogue") or [])
                            if isinstance(item, dict)
                            and str(item.get("speaker") or "").strip() == "妈妈"
                        )
                        if after_mom != before_mom:
                            logger.info(
                                "gold_chat expand_structure repair local hard close mom=%s->%s max=%s",
                                before_mom,
                                after_mom,
                                mom_int,
                            )

                        # hard repair（尤其妈妈 4→3）可能顺手删掉十几字；这个副作用属于
                        # 同一次结构修稿，必须在 acceptance 前本地恢复，不能再占下一次预算。
                        before_reclose_chars = dialogue_total_chars(draft)
                        draft, reclosed = _stabilize_local_length_candidate(
                            draft,
                            structure_type=structure_type,
                            mechanism=mechanism,
                            beat_chain=beat_chain,
                            dialogue_seed=seed if isinstance(seed, list) else None,
                        )
                        if reclosed:
                            logger.info(
                                "gold_chat expand_structure repair post-hard length close chars=%s->%s",
                                before_reclose_chars,
                                dialogue_total_chars(draft),
                            )
                except ValueError as exc:
                    repair_error = str(exc)
                    chat = baseline
                    continue
                accepted, reject_reason = evaluate_repair_candidate_acceptance(
                    baseline,
                    draft,
                    row=row,
                    mom_lines_max=mom_int,
                    banned_literals=banned_list,
                    strict_dialogue_shape=short_only,
                )
                if accepted is None:
                    repair_error = reject_reason or "修稿验收未通过"
                    chat = baseline
                    continue
                repair_error = ""
                chat = accepted
        except GoldChatRepairExhausted:
            raise
        except AlignRepairFailure as exc:
            last_err = exc.to_message()
            budget.note_failure(last_err)
            if budget.exhausted:
                raise GoldChatRepairExhausted(
                    stage=exc.stage, reason=last_err, candidate=exc.candidate,
                ) from exc
            expand_feedback_block = format_expand_regen_feedback(
                last_err,
                exc.candidate,
                structure_type=structure_type,
                mechanism=mechanism,
                closing_intent=closing,
                beat_chain=beat_chain,
                conflict_text=conflict_text,
                short_regen_count=short_regen_count,
            )
            continue
        except ValueError as exc:
            last_err = str(exc)
            if budget.exhausted:
                raise GoldChatRepairExhausted(
                    stage="expand", reason=last_err, candidate=chat,
                ) from exc
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
            "scene_title": remap_source_kinship(str(row.get("title") or "")),
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
