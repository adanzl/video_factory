"""gold_chat 终稿：类型垫字 / 钉收束 / 结构分门控。

三阶段末环（扩写 → 精修 → **终稿**）。从 ``convert.convert_gold_chat``
抽出；convert 只负责编排到此步再导出。

K 收口原则：走 ``story_types.k.patch`` 的 seal/pin，中段通用补字；
不在本文件手写收束五句或固定 filler 插句。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.daily_story.story_types import (
    patch_j_soften_closing_grumble,
    patch_j_strip_role_mismatch_expands,
)
from app.services.gold_story.gold_chat.length import (
    _boost_short_with_mid_lines,
    _ensure_gold_chat_min_chars,
    _expand_short_gold_chat_lines,
    _gold_chat_force_min_chars,
    _pad_gold_chat_to_min_chars,
    patch_sanitize_bridge_lines,
    patch_sanitize_c_tone_stack,
    patch_sanitize_pad_particles,
    patch_sanitize_pad_suffix,
)
from app.services.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
    patch_m5_break_sibling_consecutive,
)
from app.services.gold_story.gold_chat.prompts import format_structure_score_feedback
from app.services.gold_story.gold_chat.validate import (
    collect_align_issues,
    split_align_issues,
)
from app.services.gold_story.scene import sanitize_banned_literals

logger = logging.getLogger(__name__)

_GOLD_CHAT_STRUCTURE_LIFT_MAX = 2
_GOLD_CHAT_EXPORT_REPAIR_MAX = 2
_GOLD_CHAT_DUPLICATE_RESCUE_MAX = 1

_REPAIRABLE_VALIDATE_MARKERS = (
    "正文总字数须≥",
    "正文总字数须≤",
    "妈妈台词须≤",
    "爸爸台词须≤",
    "opening_causality:",
)


class GoldChatAcceptanceBlocked(ValueError):
    """终检高置信度硬伤，禁止导出。"""


class GoldChatLocalDuplicateBlocked(GoldChatAcceptanceBlocked):
    """仅本地重复硬伤，可进入有限次定点修稿。"""


class GoldChatRepairableError(ValueError):
    """终检硬卡失败且可进入统一点定修稿。"""


class GoldChatStructureScoreError(GoldChatRepairableError):
    """结构分未过发布线。"""

    def __init__(self, score: int) -> None:
        self.score = int(score)
        super().__init__(f"structure_score:{self.score}")


class GoldChatValidationRepairableError(GoldChatRepairableError):
    """字数/家长句数等可由 LLM 定点修订的 hard 校验失败。"""


class GoldChatAcceptanceIncomplete(Exception):
    """语义审核未完成（超时/解析失败），非稿子过错。"""


def _gate_structure_or_raise(
    gate_score: Any,
    chat: dict[str, Any],
) -> int:
    try:
        return int(gate_score(chat))
    except ValueError as exc:
        msg = str(exc).strip()
        if msg.startswith("structure_score:"):
            tail = msg.split(":", 1)[-1].strip()
            try:
                score = int(tail)
            except ValueError:
                score = 0
            raise GoldChatStructureScoreError(score) from exc
        raise


def _validate_chat_or_repairable(
    validate_chat: Any,
    chat: dict[str, Any],
) -> None:
    try:
        validate_chat(chat)
    except ValueError as exc:
        msg = str(exc).strip()
        parts = [p.strip() for p in msg.split(";") if p.strip()]
        if parts and all(
            any(marker in part for marker in _REPAIRABLE_VALIDATE_MARKERS)
            for part in parts
        ):
            raise GoldChatValidationRepairableError(msg) from exc
        raise


def _is_export_repairable(exc: BaseException) -> bool:
    if isinstance(exc, GoldChatAcceptanceIncomplete):
        return False
    if isinstance(exc, (GoldChatRepairableError, GoldChatLocalDuplicateBlocked)):
        return True
    if isinstance(exc, GoldChatAcceptanceBlocked):
        return str(exc).strip().startswith("终检语义硬伤")
    return False


def _export_repair_budget_hint() -> str:
    return (
        "补足冲突触发，再保留辩解与解围；允许压缩后面重复收场，"
        "为必要角色台词腾出额度。禁止换角色凑额度或加语气词凑字。"
    )


def _build_export_repair_feedback(
    exc: BaseException,
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    st_final: str,
    mom_max: int,
) -> str:
    from app.services.gold_story.gold_chat.prompts import (
        format_semantic_acceptance_feedback,
        format_structure_score_feedback,
    )
    from app.services.gold_story.gold_chat.repair import build_candidate_repair_feedback

    dialogue = chat.get("dialogue") or []
    mom_count = sum(
        1
        for item in dialogue
        if isinstance(item, dict) and str(item.get("speaker") or "").strip() == "妈妈"
    )
    total = dialogue_total_chars(chat)
    metrics = (
        f"当前正文 {total} 字（至少 {DAILY_STORY_BODY_CHARS_MIN}）；"
        f"妈妈 {mom_count} 句（上限 {int(mom_max)}）。"
    )
    hint = _export_repair_budget_hint() + "\n" + build_candidate_repair_feedback(
        chat, validation_errors=[str(exc)], align_issues=[], mom_lines_max=mom_max,
    )

    if isinstance(exc, GoldChatStructureScoreError):
        body = format_structure_score_feedback(str(exc), chat)
        return f"{body}\n{metrics}\n{hint}"

    if isinstance(exc, GoldChatValidationRepairableError):
        return "\n".join([
            "【终检硬卡·定点修稿】",
            metrics,
            f"机审：{exc}",
            hint,
        ])

    if isinstance(exc, GoldChatLocalDuplicateBlocked):
        return (
            f"{format_semantic_acceptance_feedback(str(exc))}\n{metrics}\n{hint}"
        )

    msg = str(exc).strip()
    if msg.startswith("终检语义硬伤"):
        return f"{format_semantic_acceptance_feedback(msg)}\n{metrics}\n{hint}"

    del row, st_final
    return f"【终检修稿】\n{metrics}\n机审：{msg}\n{hint}"


def _sanitize_repaired_chat(
    lifted: dict[str, Any],
    *,
    st_final: str,
    normalize_chat: Any,
    dialogue_seed: list[Any] | None,
) -> dict[str, Any]:
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )

    out = normalize_chat(lifted)
    if st_final:
        out["story_type"] = st_final
    out, _ = patch_sanitize_pad_suffix(out)
    out, _ = patch_sanitize_pad_particles(out)
    out, _ = patch_gold_chat_consecutive_siblings(
        out,
        dialogue_seed=dialogue_seed,
    )
    return out


def run_gold_chat_final_acceptance(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    sid: str,
) -> dict[str, Any]:
    """补字/改 speaker 完成后统一终验；未过则抛错，不写导出文件。"""
    from app.services.daily_story.quality import stamp_gold_chat_acceptance_quality
    from app.services.daily_story.review import (
        collect_escalation_chatter_signals,
        collect_export_blocking_local_issues,
        format_export_blocking_issue_summary,
        partition_llm_export_blocking_issues,
        run_export_semantic_review,
    )

    theme = str(
        row.get("title") or chat.get("scene_title") or chat.get("key") or sid
    ).strip()
    payload_raw = row.get("payload")
    payload: dict[str, Any] = (
        payload_raw if isinstance(payload_raw, dict) else {}
    )
    scene_contract: dict[str, Any] = {}
    sc_raw = payload.get("scene_contract")
    if isinstance(sc_raw, dict):
        scene_contract = sc_raw
    beat_chain_raw = scene_contract.get("beat_chain")
    beat_chain = beat_chain_raw if isinstance(beat_chain_raw, list) else None
    mom_max = 1
    mom_contract = scene_contract.get("mom_lines_max")
    if mom_contract is not None:
        try:
            mom_max = max(0, int(mom_contract))
        except (TypeError, ValueError):
            mom_max = 1
    else:
        cached = chat.get("_gold_chat_mom_lines_max")
        if cached is not None:
            try:
                mom_max = max(0, int(cached))
            except (TypeError, ValueError):
                pass

    from app.services.gold_story.gold_chat.patch import (
        apply_opening_causality_local_patch,
    )
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        format_opening_causality_hard_error,
    )

    chat, opening_patched = apply_opening_causality_local_patch(
        chat,
        beat_chain=beat_chain,
        mom_lines_max=mom_max,
    )
    if opening_patched:
        logger.info("[GOLD_CHAT] final acceptance opening causality local patch")

    opening_block = collect_opening_causality_issues(
        chat,
        beat_chain,
        mom_lines_max=mom_max,
    )
    if opening_block:
        parts = [
            format_opening_causality_hard_error(item)
            for item in opening_block[:3]
        ]
        raise GoldChatValidationRepairableError("; ".join(parts))

    local_block = collect_export_blocking_local_issues(chat)
    if local_block:
        parts = [
            f"第{it['lines']}句·{it['kind']}：{it['desc']}"
            for it in local_block[:5]
        ]
        error_type = (
            GoldChatLocalDuplicateBlocked
            if all(it["kind"] == "重复" for it in local_block)
            else GoldChatAcceptanceBlocked
        )
        raise error_type("终检本地硬伤：" + "；".join(parts))

    review = run_export_semantic_review(theme, chat, beat_chain=beat_chain)
    if not review.completed:
        raise GoldChatAcceptanceIncomplete(
            review.error
            or "语义审核未完成（LLM 超时或解析失败），已保留上次导出稿",
        )

    llm_block, bad_evidence = partition_llm_export_blocking_issues(
        review.issues,
        chat,
        beat_chain=beat_chain,
    )
    if bad_evidence:
        parts = [
            format_export_blocking_issue_summary(it)
            for it in bad_evidence[:5]
        ]
        raise GoldChatAcceptanceIncomplete(
            "审核证据无效（"
            + "；".join(parts)
            + "），已保留上次导出稿",
        )
    if llm_block:
        parts = [
            format_export_blocking_issue_summary(it)
            for it in llm_block[:5]
        ]
        raise GoldChatAcceptanceBlocked(
            "终检语义硬伤：" + "；".join(parts),
        )

    signals = collect_escalation_chatter_signals(chat)
    stamp_gold_chat_acceptance_quality(
        chat,
        review_issues=review.issues,
        humor=review.humor,
        chatter_signals=signals,
        semantic_pass=True,
    )
    logger.info(
        "[GOLD_CHAT] final acceptance ok %s issues=%s humor=%s",
        sid,
        len(review.issues),
        bool(review.humor),
    )
    return chat


def run_gold_chat_final_acceptance_with_semantic_repair(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    sid: str,
    st_final: str,
    banned: list[str],
    mom_max: int,
    source_type: str,
    attach_score,
    gate_score,
    normalize_chat,
    fix_llm,
    validate_chat,
    dialogue_seed: list[Any] | None = None,
    max_repairs: int = _GOLD_CHAT_EXPORT_REPAIR_MAX,
    repair_budget: Any | None = None,
) -> tuple[dict[str, Any], int]:
    """导出前统一修稿；共享预算耗尽后，纯重复终检仅额外救援一次。"""
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    del source_type  # 校验由 validate_chat 闭包注入

    budget: GoldChatRepairBudget | None = (
        repair_budget
        if isinstance(repair_budget, GoldChatRepairBudget)
        else None
    )
    local_max = max(0, int(max_repairs))

    current = dict(chat)
    last_err: str | None = None
    attempt = 0
    duplicate_rescue_used = 0
    while True:
        try:
            _validate_chat_or_repairable(validate_chat, current)
            scored = attach_score(current, row)
            struct = _gate_structure_or_raise(gate_score, scored)
            current = scored
            accepted = run_gold_chat_final_acceptance(current, row, sid=sid)
            return accepted, int(struct)
        except GoldChatAcceptanceIncomplete:
            raise
        except BaseException as exc:
            if not _is_export_repairable(exc):
                raise
            if budget is not None:
                consumed = budget.consume(stage="final_acceptance", reason=str(exc))
                if not consumed:
                    if (
                        isinstance(exc, GoldChatLocalDuplicateBlocked)
                        and duplicate_rescue_used < _GOLD_CHAT_DUPLICATE_RESCUE_MAX
                    ):
                        duplicate_rescue_used += 1
                        logger.info(
                            "gold_chat final duplicate rescue used=%s/%s reason=%s",
                            duplicate_rescue_used,
                            _GOLD_CHAT_DUPLICATE_RESCUE_MAX,
                            str(exc),
                        )
                    else:
                        budget.note_failure(str(exc))
                        raise
            elif attempt >= local_max:
                raise
            attempt += 1
            last_err = str(exc).strip()
            prompt = _build_export_repair_feedback(
                exc,
                current,
                row,
                st_final=st_final,
                mom_max=int(mom_max),
            )
            if attempt > 0 and last_err:
                prompt = f"{prompt}\n【上一轮未过】{last_err}"
            lifted = fix_llm(
                current,
                prompt,
                banned_literals=[str(x) for x in banned],
                mom_lines_max=int(mom_max),
            )
            current = _sanitize_repaired_chat(
                lifted,
                st_final=st_final,
                normalize_chat=normalize_chat,
                dialogue_seed=dialogue_seed,
            )
            continue
    raise GoldChatAcceptanceBlocked(last_err or "终检修稿未通过")


def _k_fix_scene_title(chat: dict[str, Any], row: dict[str, Any]) -> None:
    """点题句污染标题时收回。"""
    title = str(chat.get("scene_title") or "").strip()
    if (
        title in {"还不哭？", "还不哭", "哭了还嘴硬？"}
        or title.startswith("还不哭")
        or title.startswith("哭了还")
        or len(title) < 4
    ):
        chat["scene_title"] = str(row.get("title") or "姐弟吵翻天")


def _k_bind_press_roles(chat: dict[str, Any]) -> list[str]:
    from app.services.daily_story.story_types.k.patch import (
        patch_k_bind_press_roles,
        patch_k_fix_consecutive_keep_press,
    )

    notes = patch_k_bind_press_roles(chat)
    notes.extend(patch_k_fix_consecutive_keep_press(chat))
    return notes


def _k_seal_and_pin(chat: dict[str, Any]) -> list[str]:
    """劝失败封口 + 冲突续行钉死（走 k.patch，不手写五句）。"""
    from app.services.daily_story.story_types.k.close_mode import (
        K_A_PARENT_FAIL_STALEMATE,
        k_close_mode_from_story,
    )
    from app.services.daily_story.story_types.k.patch import (
        patch_k_ensure_press_climax,
        patch_k_force_climax_before_parent,
        patch_k_pin_advise_fail_close,
        patch_k_seal_after_parent_fail,
        patch_k_strip_hard_win_close,
        patch_k_strip_meta_and_action_narr,
    )

    if k_close_mode_from_story(chat) != K_A_PARENT_FAIL_STALEMATE:
        return []
    notes: list[str] = []
    notes.extend(patch_k_ensure_press_climax(chat))
    notes.extend(patch_k_strip_meta_and_action_narr(chat))
    notes.extend(patch_k_strip_hard_win_close(chat))
    notes.extend(patch_k_seal_after_parent_fail(chat))
    notes.extend(patch_k_force_climax_before_parent(chat))
    notes.extend(patch_k_pin_advise_fail_close(chat))
    return notes


def _k_pin_close(chat: dict[str, Any]) -> list[str]:
    """只钉收束，不跑 seal 砍句（垫字后用）；仅 K-A。"""
    from app.services.daily_story.story_types.k.close_mode import (
        K_A_PARENT_FAIL_STALEMATE,
        k_close_mode_from_story,
    )
    from app.services.daily_story.story_types.k.patch import (
        patch_k_force_climax_before_parent,
        patch_k_pin_advise_fail_close,
    )

    if k_close_mode_from_story(chat) != K_A_PARENT_FAIL_STALEMATE:
        return []
    notes: list[str] = []
    notes.extend(patch_k_force_climax_before_parent(chat))
    notes.extend(patch_k_pin_advise_fail_close(chat))
    return notes


def _k_under_hard_floor(chat: dict[str, Any]) -> bool:
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    dialogue = chat.get("dialogue")
    lines = len(dialogue) if isinstance(dialogue, list) else 0
    return (
        dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN
        or lines < CHAT_LINE_COUNT_MIN
    )


def _k_meet_min_chars(
    chat: dict[str, Any],
    *,
    mechanism: str,
    rounds: int = 8,
) -> dict[str, Any]:
    """中段补到 hard min：剥粒子 → boost/force/expand/pad。

    不跑 type_patch/seal（避免垫完又被封口砍掉）。
    """
    from app.services.daily_story.story_types import (
        apply_gold_chat_k_fix_truncations,
    )
    from app.services.gold_story.gold_chat.length import _K_NATURAL_MID_PAIRS

    chat = dict(chat)
    chat["story_type"] = "K"
    for _ in range(rounds):
        if not _k_under_hard_floor(chat):
            break
        before_chars = dialogue_total_chars(chat)
        before_lines = len(chat.get("dialogue") or [])
        chat, _ = patch_sanitize_pad_suffix(chat)
        chat, _ = patch_sanitize_pad_particles(chat)
        chat, c1 = _boost_short_with_mid_lines(
            chat, mechanism=mechanism, structure_type="K"
        )
        chat, c2 = _gold_chat_force_min_chars(chat)
        apply_gold_chat_k_fix_truncations(chat)
        if not _k_under_hard_floor(chat):
            break
        chat, c3 = _expand_short_gold_chat_lines(
            chat, ignore_deficit_cap=True
        )
        chat, c4 = _pad_gold_chat_to_min_chars(chat, max_rounds=32)
        apply_gold_chat_k_fix_truncations(chat)
        after_chars = dialogue_total_chars(chat)
        after_lines = len(chat.get("dialogue") or [])
        if (
            after_chars <= before_chars
            and after_lines <= before_lines
            and not (c1 or c2 or c3 or c4)
        ):
            break
    # boost 可能因与收束句归一化撞车插不进：家长前硬插可读互顶对
    if _k_under_hard_floor(chat):
        dialogue = chat.get("dialogue")
        if isinstance(dialogue, list):
            parent_i = next(
                (
                    i
                    for i, x in enumerate(dialogue)
                    if isinstance(x, dict)
                    and str(x.get("speaker") or "").strip()
                    in ("妈妈", "爸爸")
                ),
                len(dialogue),
            )
            insert_at = max(1, parent_i)
            existing = {
                str(x.get("line") or "").strip()
                for x in dialogue
                if isinstance(x, dict)
            }
            inserted = 0
            for pair in _K_NATURAL_MID_PAIRS:
                if not _k_under_hard_floor(chat) or inserted >= 4:
                    break
                rows = [
                    {"speaker": sp, "line": line}
                    for sp, line in pair
                ]
                if any(r["line"] in existing for r in rows):
                    continue
                # 避免同人连说
                prev_sp = (
                    str(dialogue[insert_at - 1].get("speaker") or "")
                    if insert_at > 0
                    and insert_at <= len(dialogue)
                    and isinstance(dialogue[insert_at - 1], dict)
                    else ""
                )
                if prev_sp == rows[0]["speaker"]:
                    rows = list(reversed(rows))
                dialogue[insert_at:insert_at] = rows
                insert_at += len(rows)
                existing.update(r["line"] for r in rows)
                inserted += 1
                chat["dialogue"] = dialogue
            if inserted and _k_under_hard_floor(chat):
                chat, _ = _expand_short_gold_chat_lines(
                    chat, ignore_deficit_cap=True
                )
                chat, _ = _pad_gold_chat_to_min_chars(chat, max_rounds=32)
                chat, _ = _gold_chat_force_min_chars(chat)
    chat, _ = patch_sanitize_pad_suffix(chat)
    chat, _ = patch_sanitize_pad_particles(chat)
    apply_gold_chat_k_fix_truncations(chat)
    return chat


def _k_pad_keeping_seal_tail(
    chat: dict[str, Any], *, mechanism: str, rounds: int = 8
) -> dict[str, Any]:
    """封口后只垫中段：保末五句，勿再 pin（pin 会按首个家长重切冲掉垫字）。"""
    if not _k_under_hard_floor(chat):
        return chat
    dialogue = chat.get("dialogue")
    if isinstance(dialogue, list) and len(dialogue) >= 5:
        seal_tail = [dict(x) for x in dialogue[-5:] if isinstance(x, dict)]
        head = [dict(x) for x in dialogue[:-5] if isinstance(x, dict)]
        tmp = _k_meet_min_chars(
            {"dialogue": head, "story_type": "K"},
            mechanism=mechanism,
            rounds=rounds,
        )
        chat = dict(chat)
        chat["dialogue"] = list(tmp.get("dialogue") or []) + seal_tail
        chat["story_type"] = "K"
        return chat
    return _k_meet_min_chars(chat, mechanism=mechanism, rounds=rounds)


def _finalize_k_pre_validate(
    chat: dict[str, Any], *, mechanism: str
) -> dict[str, Any]:
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    chat, _ = apply_gold_chat_type_patch(chat, structure_type="K")
    chat = _k_meet_min_chars(chat, mechanism=mechanism)
    notes = _k_seal_and_pin(chat)
    if notes:
        logger.info(
            "gold_chat K pre-validate seal: %s",
            "；".join(notes[:4]),
        )
    # 封口只一次；之后只保尾垫头，禁止再 pin/seal 砍句
    if _k_under_hard_floor(chat):
        chat = _k_pad_keeping_seal_tail(chat, mechanism=mechanism, rounds=8)
    return chat


def _finalize_k_pre_score(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    mechanism: str,
) -> dict[str, Any]:
    role_notes = _k_bind_press_roles(chat)
    if role_notes:
        logger.info(
            "gold_chat pre-score K role bind: %s",
            "；".join(role_notes[:6]),
        )
    chat, boost_changed = _ensure_gold_chat_min_chars(
        chat, mechanism=mechanism, structure_type="K"
    )
    if boost_changed:
        logger.info("gold_chat pre-score K reboost")
        chat, _ = patch_sanitize_pad_particles(chat)
        _k_bind_press_roles(chat)
    if _k_under_hard_floor(chat):
        chat = _k_meet_min_chars(chat, mechanism=mechanism, rounds=6)
        _k_bind_press_roles(chat)
    seal_notes = _k_seal_and_pin(chat)
    if seal_notes:
        logger.info(
            "gold_chat pre-score K seal: %s",
            "；".join(seal_notes[:4]),
        )
    if _k_under_hard_floor(chat):
        chat = _k_pad_keeping_seal_tail(chat, mechanism=mechanism, rounds=8)
    _k_fix_scene_title(chat, row)
    return chat


def _default_structure_lift_hint(st_final: str) -> str:
    st = str(st_final or "").strip().upper()
    if st == "O":
        return (
            "抬结构：两轮死磕见底后由赢赛方自述点题，"
            "勿垫字碎片、勿对手代点题、勿点题后抬杠"
        )
    return (
        "抬结构：按本类型收束契约修订末段（保留主线冲突与人物），"
        "勿另起第二轮；收束落位后即停。"
    )


def _lift_gold_chat_structure_with_llm(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    st_final: str,
    mech: str,
    banned: list[str],
    mom_max: int,
    attach_score,
    gate_score,
    normalize_chat,
    fix_llm,
    validate_chat,
    max_attempts: int = _GOLD_CHAT_STRUCTURE_LIFT_MAX,
) -> tuple[dict[str, Any], int]:
    """结构分未过线：定点 LLM 修稿，最多 max_attempts 次。"""
    from app.services.daily_story.quality import structure_score_of
    from app.services.daily_story.story_types import apply_gold_chat_type_patch
    from app.services.gold_story.gold_chat.convert import (
        log_gold_chat_structure_score_fail,
    )
    from app.services.gold_story.gold_chat.length import (
        _ensure_gold_chat_min_chars,
    )

    current = dict(chat)
    last_err: str | None = None
    st_patch = str(st_final or "").strip().upper()
    for _ in range(max(1, int(max_attempts))):
        quality0 = cast(dict[str, Any], current.get("quality")) if isinstance(
            current.get("quality"), dict
        ) else {}
        fb = format_structure_score_feedback(
            f"structure_score:{structure_score_of(quality0)}",
            current,
        )
        hint = _default_structure_lift_hint(st_final)
        prompt = (fb or hint).strip()
        if last_err:
            prompt = f"{prompt}\n【上一轮未过】{last_err}"
        try:
            lifted = fix_llm(
                current,
                prompt,
                banned_literals=[str(x) for x in banned],
                mom_lines_max=int(mom_max),
            )
            lifted = normalize_chat(lifted)
            if st_final:
                lifted["story_type"] = st_final
            lifted, _ = patch_sanitize_pad_suffix(lifted)
            lifted, _ = patch_sanitize_pad_particles(lifted)
            if st_patch:
                lifted, _ = apply_gold_chat_type_patch(
                    lifted, structure_type=st_patch,
                )
            lifted, _ = _ensure_gold_chat_min_chars(
                lifted,
                mechanism=mech,
                structure_type=st_final,
            )
            if st_patch:
                lifted, _ = apply_gold_chat_type_patch(
                    lifted, structure_type=st_patch,
                )
            validate_chat(lifted)
            lifted = attach_score(lifted, row)
            struct = gate_score(lifted)
            return lifted, int(struct)
        except ValueError as exc:
            last_err = str(exc)
            if isinstance(locals().get("lifted"), dict):
                current = cast(dict[str, Any], locals()["lifted"])
    log_gold_chat_structure_score_fail(
        current,
        cast(dict[str, Any], current.get("quality"))
        if isinstance(current.get("quality"), dict)
        else {},
        structure_type=st_final,
    )
    raise ValueError(last_err or "structure_score:0")


def _finalize_k_lift_structure(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    mechanism: str,
    attach_score,
    gate_score,
) -> tuple[dict[str, Any], int]:
    """结构分不过：type_patch + 中段补字后再过门。"""
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    lifted = dict(chat)
    lifted["story_type"] = "K"
    lifted, _ = apply_gold_chat_type_patch(lifted, structure_type="K")
    lifted = _k_meet_min_chars(lifted, mechanism=mechanism, rounds=6)
    _k_seal_and_pin(lifted)
    if _k_under_hard_floor(lifted):
        lifted = _k_pad_keeping_seal_tail(
            lifted, mechanism=mechanism, rounds=6
        )
    lifted = attach_score(lifted, row)
    struct = gate_score(lifted)  # may raise
    return lifted, int(struct)


def _finalize_k_pre_export(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    mechanism: str,
    attach_score,
    gate_score,
) -> tuple[dict[str, Any], int]:
    from app.services.daily_story.story_types.k.patch import (
        patch_k_break_same_speaker_run,
        patch_k_loser_monotonic,
    )

    patch_k_loser_monotonic(chat)
    # 导出前只 pin 一次；若掉字则保尾垫头，不再 pin
    _k_pin_close(chat)
    if _k_under_hard_floor(chat):
        chat = _k_pad_keeping_seal_tail(chat, mechanism=mechanism, rounds=8)
        patch_k_loser_monotonic(chat)
    _k_fix_scene_title(chat, row)
    chat = attach_score(chat, row)
    try:
        struct = gate_score(chat)
    except ValueError:
        patch_k_break_same_speaker_run(chat)
        chat = attach_score(chat, row)
        struct = gate_score(chat)
    return chat, int(struct)


def run_gold_chat_finalize(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    sid: str,
    norm_notes: list[str] | None,
    payload0: dict[str, Any],
    st0: str,
    mech0: str,
    repair_budget: Any | None = None,
) -> tuple[dict[str, Any], int]:
    """归一化之后的终稿链路；返回 (chat, structure_score)。"""
    from app.services.gold_story.gold_chat.convert import (
        _attach_gold_chat_structure_score,
        _fix_chat_with_llm,
        _gate_gold_chat_structure_score,
        _gold_chat_j_final_polish,
        _normalize_chat_speakers,
        _o_polish_meet_min_chars,
        log_gold_chat_structure_score_fail,
        patch_break_consecutive_keep_seed,
        patch_score_propaganda_speakers,
        validate_gold_chat,
    )

    _st0 = st0
    _mech0 = mech0

    # 垫字后再跑一轮 M2+C 收口，然后若被削短再垫回 hard min
    if str(row.get("structure_type") or chat.get("story_type") or "").upper() == "C":
        chat, _ = patch_sanitize_c_tone_stack(chat)
        from app.services.gold_story.gold_chat.patch import (
            patch_m2_c_structure,
        )

        payload = cast(dict[str, Any], row.get("payload") or {})
        chat, strip_notes = patch_m2_c_structure(
            chat,
            structure_type=str(row.get("structure_type") or ""),
            mechanism=str(row.get("mechanism") or ""),
            theme=str(row.get("title") or chat.get("scene_title") or ""),
            payload=payload,
        )
        if strip_notes:
            norm_notes = list(norm_notes or []) + list(strip_notes)
        chat, pad_notes = _ensure_gold_chat_min_chars(
            chat,
            mechanism=_mech0,
            structure_type=_st0,
        )
        if pad_notes:
            norm_notes = list(norm_notes or []) + ["垫字达标"]
        chat, _ = patch_sanitize_c_tone_stack(chat)
    if norm_notes:
        logger.info(
            "gold_chat normalize %s: %s",
            sid,
            "；".join(norm_notes[:4]),
        )
    payload = cast(dict[str, Any], row.get("payload") or {})
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    source_type = str(payload.get("source_type") or scene_contract.get("source_type") or "field")
    mom_max = scene_contract.get("mom_lines_max")
    if mom_max is None:
        mom_max = 1
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    chat, _ = _ensure_gold_chat_min_chars(
        chat,
        mechanism=_mech0,
        structure_type=_st0,
    )
    chat, _ = _gold_chat_j_final_polish(
        chat,
        dialogue_seed=payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None,
        structure_type=str(row.get("structure_type") or ""),
    )
    if str(_st0 or "").upper() == "O":
        chat, o_notes = _o_polish_meet_min_chars(
            chat, mechanism=_mech0, structure_type="O", rounds=3
        )
        if o_notes:
            logger.info(
                "gold_chat O final polish: %s",
                "；".join(str(n) for n in o_notes[:4]),
            )
    if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
        for _ in range(3):
            if dialogue_total_chars(chat) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(chat)
            chat, _ = _gold_chat_force_min_chars(chat)
            chat, _ = patch_j_strip_role_mismatch_expands(chat)
            chat, _ = patch_j_soften_closing_grumble(chat)
            chat, _ = patch_sanitize_bridge_lines(chat)
            if dialogue_total_chars(chat) <= before:
                chat, _ = _pad_gold_chat_to_min_chars(
                    chat, particle_only=True, max_rounds=12
                )
                if dialogue_total_chars(chat) <= before:
                    break
    if str(_st0 or "").upper() == "K":
        chat = _finalize_k_pre_validate(chat, mechanism=_mech0)
    seed = (
        payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None
    )
    if str(row.get("structure_type") or chat.get("story_type") or "").upper() == "J":
        for _ in range(3):
            chat, br = patch_break_consecutive_keep_seed(
                chat, dialogue_seed=seed, bridge_cap=4
            )
            if not br:
                break
            chat, _ = patch_sanitize_bridge_lines(chat)
        if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
            chat, _ = _pad_gold_chat_to_min_chars(
                chat, particle_only=True, max_rounds=12
            )
    if str(_st0 or "").upper() == "O":
        chat, o_notes3 = _o_polish_meet_min_chars(
            chat, mechanism=_mech0, structure_type="O", rounds=4
        )
        if o_notes3:
            logger.info(
                "gold_chat O pre-validate trim: %s",
                "；".join(str(n) for n in o_notes3[:4]),
            )
    validate_gold_chat(
        chat,
        banned_literals=[str(x) for x in banned],
        source_type=source_type,
        mom_lines_max=int(mom_max),
    )
    logger.info(
        "[GOLD_CHAT] convert %s passed validation lines=%s chars=%s",
        sid,
        len(chat.get("dialogue") or []),
        dialogue_total_chars(chat),
    )
    mech = str(row.get("mechanism") or "").upper()
    st = str(row.get("structure_type") or "").strip().upper()
    if mech == "M5" and st == "H":
        payload = cast(dict[str, Any], row.get("payload") or {})
        scene_contract = payload.get("scene_contract") or {}
        closing = str(
            payload.get("closing_intent")
            or scene_contract.get("closing_intent")
            or ""
        )
        conflict_text = str(
            scene_contract.get("conflict") or row.get("conflict_core") or ""
        )
        chat, _ = apply_m5_h_local_patches(
            chat,
            closing_intent=closing,
            conflict_text=conflict_text,
        )
        chat, _ = patch_m5_break_sibling_consecutive(chat)
        blocking, _warn = split_align_issues(
            collect_align_issues(
                chat,
                structure_type=st,
                mechanism=mech,
                closing_intent=closing,
                conflict_text=conflict_text,
                beat_chain=scene_contract.get("beat_chain"),
                dialogue_seed=payload.get("dialogue_seed"),
                beat=payload.get("beat"),
                object_text=str(scene_contract.get("object") or ""),
                mechanism_text=str(scene_contract.get("mechanism") or ""),
            )
        )
        if blocking:
            kinds = "、".join(str(x.get("kind") or "") for x in blocking[:3])
            raise ValueError(f"align_export:{kinds}")
    # authority_punchline：导出前再兜底开场，防后处理冲掉立规
    payload_ex = cast(dict[str, Any], row.get("payload") or {})
    scene_ex = payload_ex.get("scene_contract") or {}
    closing_mode_ex = str(
        chat.get("closing_mode") or payload_ex.get("closing_mode") or ""
    ).strip()
    k_mode_ex = str(
        chat.get("k_close_mode")
        or payload_ex.get("k_close_mode")
        or (
            scene_ex.get("k_close_mode")
            if isinstance(scene_ex, dict)
            else ""
        )
        or ""
    ).strip()
    if k_mode_ex:
        chat = dict(chat)
        chat["k_close_mode"] = k_mode_ex
    if closing_mode_ex == "authority_punchline":
        from app.services.gold_story.gold_chat.patch import (
            apply_authority_punchline_local_patches,
        )

        beat_ex = scene_ex.get("beat_chain") or chat.get("gold_beat_chain")
        chat = dict(chat)
        chat["closing_mode"] = closing_mode_ex
        chat, auth_ex = apply_authority_punchline_local_patches(
            chat,
            beat_chain=beat_ex if isinstance(beat_ex, list) else None,
            dialogue_seed=payload_ex.get("dialogue_seed"),
        )
        if auth_ex:
            logger.info("gold_chat export-time authority opening patch")
        blocking_ex, _warn_ex = split_align_issues(
            collect_align_issues(
                chat,
                structure_type=str(row.get("structure_type") or "G"),
                mechanism=str(row.get("mechanism") or "M4"),
                closing_intent=str(
                    payload_ex.get("closing_intent")
                    or scene_ex.get("closing_intent")
                    or ""
                ),
                conflict_text=str(
                    scene_ex.get("conflict") or row.get("conflict_core") or ""
                ),
                beat_chain=beat_ex if isinstance(beat_ex, list) else None,
                dialogue_seed=payload_ex.get("dialogue_seed"),
                beat=payload_ex.get("beat"),
                object_text=str(scene_ex.get("object") or ""),
                mechanism_text=str(scene_ex.get("mechanism") or ""),
            )
        )
        if blocking_ex:
            kinds = "、".join(str(x.get("kind") or "") for x in blocking_ex[:3])
            raise ValueError(f"align_export:{kinds}")
    # 终检前再清一次姐弟连说（垫字/精修可能重新制造）
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )

    chat = dict(chat)
    st_final = str(row.get("structure_type") or chat.get("story_type") or "").strip().upper()
    if st_final:
        chat["story_type"] = st_final
    seed_for_consecutive = (
        payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None
    )
    chat, consecutive_notes = patch_gold_chat_consecutive_siblings(
        chat,
        dialogue_seed=seed_for_consecutive,
    )
    if consecutive_notes:
        logger.info(
            "gold_chat pre-score consecutive patch: %s",
            "；".join(consecutive_notes[:8]),
        )
    if st_final == "K":
        chat = _finalize_k_pre_score(
            chat, row, mechanism=str(row.get("mechanism") or ""),
        )
    # 连说改 speaker 可能打乱宣传/受害腔；I 类终检前必再锁
    chat, prop_final = patch_score_propaganda_speakers(
        chat, conflict_text=str(row.get("conflict_core") or "")
    )
    if prop_final or st_final == "I":
        if prop_final:
            logger.info("gold_chat pre-score propaganda rebind")
        if st_final == "I":
            from app.services.daily_story.story_types.i.patch import (
                patch_i_dedupe_sibling_lines,
                patch_i_enforce_line_max,
                patch_i_fix_parent_sibling_voice,
                patch_i_seal_after_parent_soul,
                patch_i_strip_mid_pad,
                patch_i_strip_premature_speechless,
            )

            voice_notes = patch_i_fix_parent_sibling_voice(chat)
            premature_notes = patch_i_strip_premature_speechless(chat)
            seal_notes = patch_i_seal_after_parent_soul(chat)
            sibling_repeat_notes = patch_i_dedupe_sibling_lines(chat)
            # 去重不得打穿语塞位：再封一次
            seal_notes2 = patch_i_seal_after_parent_soul(chat)
            pad_notes = patch_i_strip_mid_pad(chat)
            chat, _ = patch_sanitize_pad_suffix(chat)
            chat, _ = patch_sanitize_pad_particles(chat)
            max_notes = patch_i_enforce_line_max(chat)
            if (
                voice_notes
                or premature_notes
                or seal_notes
                or seal_notes2
                or sibling_repeat_notes
                or pad_notes
                or max_notes
            ):
                logger.info(
                    "gold_chat pre-score I voice/seal: %s",
                    "；".join(
                        (
                            voice_notes
                            + premature_notes
                            + seal_notes
                            + sibling_repeat_notes
                            + seal_notes2
                            + pad_notes
                            + max_notes
                        )[:8]
                    ),
                )
    if st_final == "O":
        chat, o_pre_score = _o_polish_meet_min_chars(
            chat,
            mechanism=str(row.get("mechanism") or ""),
            structure_type="O",
            rounds=3,
        )
        if o_pre_score:
            logger.info(
                "gold_chat O pre-score polish: %s",
                "；".join(str(n) for n in o_pre_score[:4]),
            )
    chat = _attach_gold_chat_structure_score(chat, row)
    try:
        struct = _gate_gold_chat_structure_score(chat)
    except ValueError:
        # 终检分不够：K 仍先本地抬结构；其余类型交给统一修稿环
        if st_final == "K":
            try:
                chat, struct = _finalize_k_lift_structure(
                    chat,
                    row,
                    mechanism=_mech0,
                    attach_score=_attach_gold_chat_structure_score,
                    gate_score=_gate_gold_chat_structure_score,
                )
            except ValueError:
                log_gold_chat_structure_score_fail(
                    chat,
                    cast(dict[str, Any], chat.get("quality"))
                    if isinstance(chat.get("quality"), dict)
                    else {},
                    structure_type=st_final,
                )
                raise
        else:
            from app.services.daily_story.quality import structure_score_of

            q_pre = chat.get("quality")
            struct = (
                structure_score_of(q_pre)
                if isinstance(q_pre, dict)
                else 0
            )
    if st_final == "K":
        chat, struct = _finalize_k_pre_export(
            chat,
            row,
            mechanism=str(row.get("mechanism") or _mech0),
            attach_score=_attach_gold_chat_structure_score,
            gate_score=_gate_gold_chat_structure_score,
        )

    def _validate_for_acceptance(c: dict[str, Any]) -> None:
        validate_gold_chat(
            c,
            banned_literals=[str(x) for x in banned],
            source_type=source_type,
            mom_lines_max=int(mom_max),
        )

    chat, struct = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        row,
        sid=sid,
        st_final=st_final,
        banned=[str(x) for x in banned],
        mom_max=int(mom_max),
        source_type=source_type,
        attach_score=_attach_gold_chat_structure_score,
        gate_score=_gate_gold_chat_structure_score,
        normalize_chat=_normalize_chat_speakers,
        fix_llm=_fix_chat_with_llm,
        validate_chat=_validate_for_acceptance,
        dialogue_seed=seed_for_consecutive,
        repair_budget=repair_budget,
        max_repairs=_GOLD_CHAT_EXPORT_REPAIR_MAX,
    )
    logger.info(
        "[GOLD_CHAT] convert %s structure_score=%s lines=%s chars=%s",
        sid,
        struct,
        len(chat.get("dialogue") or []),
        dialogue_total_chars(chat),
    )
    return chat, int(struct)
