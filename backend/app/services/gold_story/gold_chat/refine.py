"""gold_chat 精修：保真 checklist 对齐精修。

阶段二（refine）。扩写见 ``expand.py``，终稿见 ``finalize.py``。
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.daily_story.story_types import (
    patch_c_force_sibling_alternate,
    patch_c_possession_criterion,
)
from app.services.gold_story.gold_chat.expand import (
    _apply_i_close_local_patches,
    _is_truncation_error,
    _normalize_chat_speakers,
    _prepare_chat_for_validate,
)
from app.services.gold_story.gold_chat.length import (
    patch_sanitize_c_tone_stack,
    patch_sanitize_pad_suffix,
)
from app.services.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
)
from app.services.gold_story.gold_chat.polish import (
    _apply_gold_chat_polish_fixes,
)
from app.services.gold_story.gold_chat.prompts import (
    CHAT_MAX_LINE_CHARS,
    format_align_issues_block,
    format_align_refine_system,
    format_align_refine_user,
)
from app.services.gold_story.gold_chat.validate import (
    collect_align_issues,
    is_structural_align_kind,
    should_reexpand,
    split_align_issues,
)

logger = logging.getLogger(__name__)

REFINE_MAX_ROUNDS = 2

def _align_refine_with_llm(
    story: dict[str, Any],
    issues: list[dict[str, Any]],
    *,
    align_block: str,
    banned_literals: list[str],
    mom_lines_max: int = 1,
    structure_type: str = "",
    mechanism: str = "",
    closing_intent: str = "",
    conflict_text: str = "",
) -> dict[str, Any]:
    system = format_align_refine_system(
        mechanism=mechanism,
        structure_type=structure_type,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    )
    user = format_align_refine_user(
        issues_block=format_align_issues_block(issues),
        align_block=align_block,
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        max_line=CHAT_MAX_LINE_CHARS,
        mechanism=mechanism,
        structure_type=structure_type,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    )
    # 经 expand 模块属性取用，便于测试 monkeypatch gex._chat_json
    from app.services.gold_story.gold_chat import expand as _expand

    return _expand._chat_json(system, user, max_tokens=1024)

def refine_gold_chat_align(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    align_block: str,
    banned_literals: list[str] | None = None,
    mom_lines_max: int = 1,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    dialogue_seed: list[Any] | None = None,
    beat: list[Any] | None = None,
    object_text: str = "",
    mechanism_text: str = "",
    max_rounds: int = REFINE_MAX_ROUNDS,
    bail_on_structural: bool = True,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """保真 checklist → LLM 定点精修 → 再 hard 校验。"""
    banned = [str(x) for x in (banned_literals or []) if str(x).strip()]
    mom_max = max(0, int(mom_lines_max))
    closing = str(closing_intent or "").strip()
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if row:
        payload = cast(dict[str, Any], row.get("payload") or {})
        mode = str(payload.get("closing_mode") or "").strip()
        if mode:
            data["closing_mode"] = mode

    for _round in range(max(1, int(max_rounds))):
        if mech == "M5" and st == "H":
            data, _ = apply_m5_h_local_patches(
                data,
                closing_intent=closing,
                conflict_text=conflict_text,
            )
        if str(data.get("closing_mode") or "").strip() == "authority_punchline":
            from app.services.gold_story.gold_chat.patch import (
                apply_authority_punchline_local_patches,
            )

            data, patched = apply_authority_punchline_local_patches(
                data,
                beat_chain=beat_chain,
                dialogue_seed=dialogue_seed,
            )
            if patched:
                logger.info("gold_chat authority opening local patch applied")
        if st == "I":
            data = _apply_i_close_local_patches(
                data,
                mechanism=mech,
                dialogue_seed=dialogue_seed,
            )
        if st == "K":
            from app.services.daily_story.story_types import apply_gold_chat_type_patch

            data, _ = apply_gold_chat_type_patch(data, structure_type="K")
        from app.services.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        patch_dialogue_narration_to_speech(data)

        issues = collect_align_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
            dialogue_seed=dialogue_seed,
            beat=beat,
            object_text=object_text,
            mechanism_text=mechanism_text,
        )
        blocking, warn = split_align_issues(issues)
        # authority 开场：再兜底一次（不占扩写重生名额）
        if any(
            str(x.get("kind") or "") in {"保真-权威开场", "保真-权威角色"}
            for x in blocking
        ):
            from app.services.gold_story.gold_chat.patch import (
                apply_authority_punchline_local_patches,
            )

            data, auth2 = apply_authority_punchline_local_patches(
                data,
                beat_chain=beat_chain,
                dialogue_seed=dialogue_seed,
            )
            if auth2:
                logger.info(
                    "gold_chat authority_retry_after_collect patch"
                )
                issues = collect_align_issues(
                    data,
                    structure_type=st,
                    mechanism=mech,
                    closing_intent=closing,
                    beat_chain=beat_chain,
                    conflict_text=conflict_text,
                    dialogue_seed=dialogue_seed,
                    beat=beat,
                    object_text=object_text,
                    mechanism_text=mechanism_text,
                )
                blocking, warn = split_align_issues(issues)
        if not blocking and not warn:
            return _prepare_chat_for_validate(
                data,
                structure_type=st,
                mechanism=mech,
                closing_intent=closing,
                conflict_text=conflict_text,
                banned_literals=banned,
                mom_lines_max=mom_max,
                row=row,
            )
        if not blocking:
            if warn:
                logger.info(
                    "gold_chat align warn only: %s",
                    "、".join(str(x.get("kind") or "") for x in warn[:3]),
                )
            return _prepare_chat_for_validate(
                data,
                structure_type=st,
                mechanism=mech,
                closing_intent=closing,
                conflict_text=conflict_text,
                banned_literals=banned,
                mom_lines_max=mom_max,
                row=row,
            )
        if bail_on_structural and should_reexpand(blocking):
            struct_kinds = [
                str(x.get("kind") or "")
                for x in blocking
                if is_structural_align_kind(str(x.get("kind") or ""))
            ]
            kinds = "、".join(struct_kinds[:3]) or "、".join(
                str(x.get("kind") or "") for x in blocking[:3]
            )
            raise ValueError(f"align_structural:{kinds}")

        try:
            raw = _align_refine_with_llm(
                data,
                blocking + warn,
                align_block=align_block,
                banned_literals=banned,
                mom_lines_max=mom_max,
                structure_type=st,
                mechanism=mech,
                closing_intent=closing,
                conflict_text=conflict_text,
            )
        except ValueError as refine_exc:
            if _is_truncation_error(str(refine_exc)):
                raise ValueError(
                    f"align_refine_failed:LLM截断:{refine_exc}"
                ) from refine_exc
            raise
        fixed, accepted = _apply_gold_chat_polish_fixes(
            data,
            raw,
            banned_literals=banned,
            mom_lines_max=mom_max,
        )
        if not accepted:
            break
        data = _normalize_chat_speakers(fixed)
        try:
            data = _prepare_chat_for_validate(
                data,
                structure_type=st,
                mechanism=mech,
                closing_intent=closing,
                conflict_text=conflict_text,
                banned_literals=banned,
                mom_lines_max=mom_max,
                row=row,
            )
        except ValueError:
            continue

    remain = collect_align_issues(
        data,
        structure_type=st,
        mechanism=mech,
        closing_intent=closing,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
    )
    # 末轮：C/K 本地收口后再机审，避免弱判据/连说卡死
    if st == "C":
        data, _ = patch_c_force_sibling_alternate(data)
        data, _ = patch_c_possession_criterion(data)
        data, _ = patch_sanitize_c_tone_stack(data)
        remain = collect_align_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        )
    if st == "K":
        from app.services.daily_story.story_types import apply_gold_chat_type_patch

        data, _ = apply_gold_chat_type_patch(data, structure_type="K")
        remain = collect_align_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        )
    if st == "O":
        from app.services.gold_story.gold_chat.convert import (
            _o_polish_meet_min_chars,
        )
        data, o_align_notes = _o_polish_meet_min_chars(
            data, mechanism=str(mech or ""), structure_type="O", rounds=3
        )
        if o_align_notes:
            logger.info(
                "gold_chat O align-end polish: %s",
                "；".join(str(n) for n in o_align_notes[:4]),
            )
        remain = collect_align_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        )
    blocking_remain, warn_remain = split_align_issues(remain)
    if any(
        str(x.get("kind") or "") in {"保真-权威开场", "保真-权威角色"}
        for x in blocking_remain
    ):
        from app.services.gold_story.gold_chat.patch import (
            apply_authority_punchline_local_patches,
        )

        data["closing_mode"] = str(
            data.get("closing_mode") or "authority_punchline"
        ).strip()
        if not isinstance(data.get("gold_beat_chain"), list) and beat_chain:
            data["gold_beat_chain"] = beat_chain
        data, auth_end = apply_authority_punchline_local_patches(
            data,
            beat_chain=beat_chain,
            dialogue_seed=data.get("dialogue_seed"),
        )
        logger.info(
            "gold_chat authority patch before refine_failed changed=%s",
            auth_end,
        )
        remain = collect_align_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
            dialogue_seed=dialogue_seed,
            beat=beat,
            object_text=object_text,
            mechanism_text=mechanism_text,
        )
        blocking_remain, warn_remain = split_align_issues(remain)
    if blocking_remain:
        parts: list[str] = []
        for x in blocking_remain[:3]:
            kind = str(x.get("kind") or "")
            desc = str(x.get("desc") or "").strip()
            parts.append(f"{kind}:{desc}" if desc else kind)
        raise ValueError(f"align_refine_failed:{'；'.join(parts)}")
    if warn_remain:
        logger.info(
            "gold_chat align warn remain: %s",
            "、".join(str(x.get("kind") or "") for x in warn_remain[:3]),
        )
    data = _prepare_chat_for_validate(
        data,
        structure_type=st,
        mechanism=mech,
        closing_intent=closing,
        conflict_text=conflict_text,
        banned_literals=banned,
        mom_lines_max=mom_max,
        row=row,
    )
    return data

