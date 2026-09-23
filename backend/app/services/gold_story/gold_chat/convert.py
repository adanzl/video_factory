"""gold_chat：金故事 → 日常对白（独立流程，不入 H0–H4 采集流水线）。

重转入口 ``convert_gold_chat`` 会先重跑 H3a/H3b 刷新 scene_contract，
再扩写对白（不必从 BV 重新导入）。

三阶段编排：
- **扩写**（expand）：契约 + seed → LLM 初稿
- **精修**（refine）：保真 checklist 对齐精修
- **终稿**（finalize）：垫字 / seal / 结构分 → ``finalize.py``

本文件负责编排与 normalize；扩写见 ``expand.py``，精修见 ``refine.py``，
终稿见 ``finalize.py``；截短/垫字原语在 ``length.py``；
机制补丁在 ``patch.py``；类型不变量经 story_types 公开桥。

本地 patch_* 分流（Batch1 盘点，Batch2 继续删并）：
- gold_length：截短/垫字/扩写/终稿硬补已抽至 length.py
- type_invariant：J/C 金稿结构补丁已迁 story_types 公开桥；convert 只编排
- delete_or_prompt：过拟合补丁（优先删/改提示词，勿整包搬家）
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
    _K_NATURAL_MID_PAIRS,
    _O_NATURAL_MID_PAIRS,
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
    patch_strip_all_natural_expands,
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
    format_align_refine_system,
    format_align_refine_user,
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
from app.services.gold_story.gold_chat.export import (
    _backfill_gold_story_after_export,
    export_gold_chat_files,
    gold_chat_export_dir,
    gold_chat_summary,
    load_gold_chat,
    load_gold_chat_for_row,
)
from app.services.gold_story.gold_chat.import_story import (
    import_gold_chat_daily_story,
)
from app.services.gold_story.gold_chat.polish import (
    _apply_gold_chat_polish_fixes,
    collect_gold_chat_polish_issues,
    polish_gold_chat_export,
    polish_gold_chat_wording,
)

logger = logging.getLogger(__name__)

# 对外仍从 convert 导入；实现已迁 expand / refine
from app.services.gold_story.gold_chat.expand import (  # noqa: E402
    CLOSING_PROMPT_MAX_CHARS,
    EXPAND_CANDIDATE_COUNT,
    EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN,
    EXPAND_LARGE_GAP_CHAR_DEFICIT_MIN_M8J,
    EXPAND_NEAR_MISS_CHAR_DEFICIT_MAX,
    EXPAND_NEAR_MISS_FIX_MAX_ROUNDS,
    EXPAND_REGENERATE_MAX,
    EXPAND_SHORT_LINE_DEFICIT_MAX,
    EXPAND_SHORT_REGENERATE_MAX,
    GOLD_CHAT_LLM_MAX_TOKENS,
    _apply_expand_setting_normalize,
    _apply_gold_chat_local_hard_repairs,
    _bump_short_regen_or_reject,
    _char_deficit_from_error,
    _chat_json,
    _closing_for_prompt,
    _fix_chat_with_llm,
    _format_dialogue_seed,
    _gate_forced_m14_p_or_raise,
    _generate_expand_candidate,
    _has_non_short_hard_errors,
    _is_large_gap_short_error,
    _is_near_miss_short_error,
    _is_regenerable_line_short_error,
    _is_regenerable_short_error,
    _is_short_content_error,
    _is_truncation_error,
    _normalize_chat_speakers,
    _persist_structure_correction,
    _pick_expand_candidate,
    _prepare_chat_for_validate,
    _resolve_closing_intent,
    _resolve_structure_row,
    _short_content_reject_message,
    _shorten_overlong_lines_with_llm,
    _validate_expand_chat,
    gold_story_to_gold_chat,
)
from app.services.gold_story.gold_chat.refine import (  # noqa: E402
    REFINE_MAX_ROUNDS,
    _align_refine_with_llm,
    refine_gold_chat_align,
)



# 2 候选够比选；4 会把短稿 FIX×重抽拖到数十分钟无反馈
# M8+J 大缺口阈值更激进：缺 ≥40 字立即中段重写，不走轻量 FIX
# 对白 JSON 正常约数百～1.5k tokens；再大视为跑飞


def patch_seed_speaker_align(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """seed 专属短语出现在错 speaker 时，改回 seed 标注角色（抽象，不写死单篇）。"""
    from app.services.gold_story.gold_chat.validate import (
        apply_seed_phrase_speaker_align,
    )

    return apply_seed_phrase_speaker_align(
        story, dialogue_seed=dialogue_seed
    )


_RE_PROPAGANDA_CLAIM = re.compile(
    r"我宣传|我宣扬|宣传高分|宣传低分|到处说她|到处说他|"
    r"低分被怪|低分怪分|高分.{0,8}谢|不是我考的|跟我有啥关系|"
    r"我.{0,4}门口喊|去门口喊|门口喊给|满楼|让.{0,4}都听见|"
    r"全班都知道|全楼都该听|全班都听见|"
    r"我要让|我再去.{0,6}喊|我举着卷子|没瞎编|明明白白|"
    r"宣传出去|事实又不是我|我.{0,4}楼下.{0,6}喊|又喊了一遍"
)
_RE_PROPAGANDA_VICTIM = re.compile(
    r"同学都笑我|你到处说我|说我考|拿我.{0,8}分|笑我|"
    r"你到处说|把卷子还我|你太过分|也太过分|当笑话讲|"
    r"放下卷子|满屋子嚷嚷|告状去|别到处说|"
    r"你.{0,4}门口喊|我同学全知道|同学会笑我|你别再嚷|别再嚷"
)


def patch_score_propaganda_speakers(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """分数宣传稿：宣传腔/受害腔 speaker 与 conflict 分工对齐。"""
    import copy

    from app.services.gold_story.gold_chat.validate import (
        _parse_conflict_propaganda_roles,
    )

    roles = _parse_conflict_propaganda_roles(
        conflict_text or str(story.get("conflict_core") or "")
    )
    if not roles:
        return story, False
    propagandist, victim = roles
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        # 家长只允许拷问/制敌/管教腔；误说第一人称宣传/受害腔则归位
        if sp in ("妈妈", "爸爸") and line:
            if re.search(
                r"换你|乐意吗|还得会|照你|评论.{0,8}吗|嘴硬|别跟我吵|"
                r"不乐意|别乱说|把卷子给我|轮不到你",
                line,
            ):
                continue
            if re.search(
                r"我宣传|我宣扬|我.{0,6}喊|我举着|跟我有啥关系|我又没瞎编",
                line,
            ):
                item["speaker"] = propagandist
                changed = True
            elif _RE_PROPAGANDA_VICTIM.search(line):
                item["speaker"] = victim
                changed = True
            continue
        if sp not in {"昭昭", "灿灿"} or not line:
            continue
        if _RE_PROPAGANDA_CLAIM.search(line) and sp != propagandist:
            item["speaker"] = propagandist
            changed = True
        elif _RE_PROPAGANDA_VICTIM.search(line) and sp != victim:
            item["speaker"] = victim
            changed = True
    return out, changed


def patch_collapse_empty_sibling_repeats(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """姐弟连说同一空转短句（如「别说了」）时只留首句，后续改写抗议。"""
    import copy

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return story, False
    changed = False
    prev_sp = ""
    prev_line = ""
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            prev_sp, prev_line = sp, line
            continue
        compact = re.sub(r"[！!。.?？…\s]", "", line)
        prev_compact = re.sub(r"[！!。.?？…\s]", "", prev_line)
        if (
            sp == prev_sp
            and compact
            and compact == prev_compact
            and len(compact) <= 4
        ):
            # 空转复读 → 换成一句有信息的短抗议
            item["line"] = "你别再说我分数了！"
            changed = True
            prev_line = item["line"]
            continue
        prev_sp, prev_line = sp, line
    return out, changed


def _realign_j_role_speakers(
    chat: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None,
    structure_type: str = "",
) -> dict[str, Any]:
    """normalize/连说后：seed + 求否句式归位，再插桥打散连说。"""
    st = str(structure_type or chat.get("story_type") or "").strip().upper()
    out, _ = patch_seed_speaker_align(chat, dialogue_seed=dialogue_seed)
    if st == "J":
        out, _ = patch_j_fix_lose_speaker(out)
        out, _ = patch_j_plea_veto_speakers(out)
        out, _ = patch_j_dedupe_plea_rounds(out)
        out, _ = patch_break_consecutive_keep_seed(out, dialogue_seed=dialogue_seed)
        out, _ = patch_seed_speaker_align(out, dialogue_seed=dialogue_seed)
        out, _ = patch_j_plea_veto_speakers(out)
        out, _ = patch_sanitize_natural_expand_stack(out)
        out, _ = patch_sanitize_pad_particles(out)
    return out


_MERGE_CONTINUATION = re.compile(
    r"^(所以|而且|那|然后|就是|还|再|可|但|不过|我|你)"
)


def _can_merge_consecutive_sibling_lines(line_a: str, line_b: str) -> bool:
    la = str(line_a or "").strip()
    lb = str(line_b or "").strip()
    if not la or not lb:
        return False
    merged = la.rstrip("。！？…!?") + "，" + lb
    if len(merged) > CHAT_MAX_LINE_CHARS:
        return False
    if _MERGE_CONTINUATION.search(lb):
        return True
    return la[-1] not in "。！？!?."


def patch_gold_chat_consecutive_siblings(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """金稿连说：先合并同人续句，再插接话；禁止仅 flip speaker 保交替。"""
    import copy

    from app.services.daily_story.prompts import _patch_q_break_consecutive_insert
    from app.services.daily_story.story_types import resolve_story_type_code

    notes: list[str] = []
    out = copy.deepcopy(story)
    code = resolve_story_type_code(out)
    if code == "B":
        return out, notes
    if code == "Q":
        notes.extend(_patch_q_break_consecutive_insert(out))
        return out, notes

    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return out, notes

    protect_tail = 4 if code in ("C", "D") else 0

    i = 1
    while i < len(dialogue):
        if protect_tail and i >= len(dialogue) - protect_tail:
            break
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in {"昭昭", "灿灿"} or sa != sb:
            i += 1
            continue
        la = str(a.get("line") or "").strip()
        lb = str(b.get("line") or "").strip()
        if _can_merge_consecutive_sibling_lines(la, lb):
            a["line"] = la.rstrip("。！？…!?") + "，" + lb
            dialogue.pop(i)
            notes.append(f"连说合并[{i}]")
            continue
        i += 1

    return out, notes


def patch_break_consecutive_keep_seed(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
    bridge_cap: int = 2,
    protect_tail: int = 0,
) -> tuple[dict[str, Any], bool]:
    """保留 API；不再插入固定接话（连说由 merge + 扩写/终检修稿处理）。"""
    del dialogue_seed, bridge_cap, protect_tail
    return story, False


def _gold_chat_j_pre_score_polish(
    chat: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None,
    mechanism: str = "",
) -> dict[str, Any]:
    """结构分门控前：J 删认输后拉锯、打散连说、归位 seed。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_m5_break_sibling_consecutive,
    )

    out = dict(chat)
    out["story_type"] = "J"
    out, _ = patch_j_fix_lose_speaker(out)
    out, _ = patch_j_fix_strongest_form_wording(out)
    out, _ = patch_j_drop_post_lose_rematch(out)
    out, _ = patch_j_dedupe_plea_rounds(out)
    out, _ = patch_j_drop_post_lose_plea(out)
    out, _ = patch_j_drop_post_lose_bridge(out)
    out, _ = patch_seed_speaker_align(out, dialogue_seed=dialogue_seed)
    for _ in range(2):
        out, br = patch_m5_break_sibling_consecutive(out)
        if not br:
            break
    out, _ = patch_j_ensure_post_lose_alternate(out)
    out, _ = patch_j_fix_post_lose_consecutive_can(out)
    out, _ = patch_j_drop_post_lose_bridge(out)
    out, _ = _ensure_gold_chat_min_chars(
        out,
        mechanism=mechanism,
        structure_type="J",
    )
    return out


def _o_polish_meet_min_chars(
    chat: dict[str, Any],
    *,
    mechanism: str,
    structure_type: str = "O",
    rounds: int = 4,
) -> tuple[dict[str, Any], list[str]]:
    """O 抛光：前置安全补字，末次 type patch 仅作兜底（不逐步强制 patch）。"""
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    del rounds  # 保留签名兼容；O 不靠多轮插对堆句数
    all_notes: list[str] = []
    st = str(structure_type or "O").strip().upper() or "O"
    mech = str(mechanism or "")
    chat, notes0 = apply_gold_chat_type_patch(chat, structure_type=st)
    if notes0:
        all_notes.extend(str(n) for n in notes0[:4])
    chat, _ = patch_sanitize_pad_suffix(chat)
    chat, _ = patch_sanitize_pad_particles(chat)
    if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
        # 最多两对中段实义（此处 1 + force 内再 1），其余 pad/expand
        chat, _ = _boost_short_with_mid_lines(
            chat, mechanism=mech, structure_type=st
        )
        chat, _ = _expand_short_gold_chat_lines(chat, ignore_deficit_cap=True)
        chat, _ = _pad_gold_chat_to_min_chars(chat, max_rounds=12)
        if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
            chat, _ = _gold_chat_force_min_chars(chat)
            chat, _ = _pad_gold_chat_to_min_chars(chat, max_rounds=12)
    # 兜底：清理点题说话人/第二轮抬杠/垫字
    chat, tail_notes = apply_gold_chat_type_patch(chat, structure_type=st)
    if tail_notes:
        all_notes.extend(str(n) for n in tail_notes[:2])
    if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
        chat, _ = _pad_gold_chat_to_min_chars(chat, max_rounds=24)
        chat, _ = _expand_short_gold_chat_lines(chat, ignore_deficit_cap=True)
        chat, tail2 = apply_gold_chat_type_patch(chat, structure_type=st)
        if tail2:
            all_notes.extend(str(n) for n in tail2[:2])
    return chat, all_notes


def _post_align_j_closing_touchup(
    chat: dict[str, Any],
    *,
    structure_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """align 后只跑 J 末句镇住（勿全量 type pipeline，免把 H 连说改坏）。"""
    st = str(structure_type or chat.get("story_type") or "").strip().upper()
    if st != "J":
        return chat, []
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    out, notes = apply_gold_chat_type_patch(chat, structure_type="J")
    return out, list(notes or [])


def _gold_chat_j_final_polish(
    chat: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None,
    structure_type: str,
) -> tuple[dict[str, Any], bool]:
    """export 前 J 终稿：归位 → 每句最多 1 扩写 → 删重复求拒 → 桥句收口 → near-miss 补字。"""
    st = str(structure_type or chat.get("story_type") or "").strip().upper()
    out = _realign_j_role_speakers(
        chat,
        dialogue_seed=dialogue_seed,
        structure_type=structure_type,
    )
    changed = out is not chat
    if st != "J":
        return out, changed
    out, c0 = patch_j_fix_lose_speaker(out)
    changed = changed or c0
    out, c0b = patch_j_fix_strongest_form_wording(out)
    changed = changed or c0b
    out, c1 = patch_sanitize_natural_expand_stack(out)
    out, c2 = patch_sanitize_pad_particles(out)
    out, c3 = patch_sanitize_expand_clutter(out)
    out, c4b = patch_j_dedupe_plea_rounds(out)
    out, c5 = patch_j_drop_post_lose_bridge(out)
    out, c4c = patch_j_drop_post_lose_plea(out)
    out, c5c = patch_j_ensure_post_lose_can_press(out)
    out, c5b = patch_j_ensure_post_lose_alternate(out)
    changed = changed or c1 or c2 or c3 or c4b or c4c or c5 or c5c or c5b
    if c4c and dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        out, cr = patch_strip_all_natural_expands(out)
        out, cr2 = patch_sanitize_pad_particles(out)
        changed = changed or cr or cr2
    for _ in range(3):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        out, cx = _expand_short_gold_chat_lines(out)
        out, _ = patch_sanitize_natural_expand_stack(out)
        changed = changed or cx
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        sp = str(item.get("speaker") or "").strip()
        if sp == "昭昭" and "我输了" in line:
            cleaned_story, lose_changed = patch_strip_all_natural_expands(
                {"dialogue": [{"speaker": "昭昭", "line": line}]}
            )
            dlg = cleaned_story.get("dialogue") or []
            if dlg and isinstance(dlg[0], dict):
                item["line"] = dlg[0].get("line") or line
                changed = changed or lose_changed
        elif sp == "昭昭" and re.search(
            r"再给一次机会|再求你一次|那我保证", line
        ):
            cleaned_story, plea_changed = patch_strip_all_natural_expands(
                {"dialogue": [{"speaker": "昭昭", "line": line}]}
            )
            dlg = cleaned_story.get("dialogue") or []
            if dlg and isinstance(dlg[0], dict):
                item["line"] = dlg[0].get("line") or line
                changed = changed or plea_changed
    out, c5c = patch_j_strip_role_mismatch_expands(out)
    changed = changed or c5c
    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
    if 0 < need <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        out, cy = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=2
        )
        out, _ = patch_sanitize_pad_particles(out)
        changed = changed or cy
    out, c6 = patch_sanitize_bridge_lines(out)
    changed = changed or c6
    for _ in range(3):
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
        if need <= 0:
            break
        out, cz = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=4
        )
        out, _ = patch_sanitize_pad_particles(out)
        out, _ = patch_j_strip_role_mismatch_expands(out)
        changed = changed or cz
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        out, cm = _gold_chat_force_min_chars(out)
        out, _ = patch_sanitize_natural_expand_stack(out)
        out, _ = patch_j_strip_role_mismatch_expands(out)
        out, _ = patch_sanitize_bridge_lines(out)
        changed = changed or cm
    out, c6b = patch_j_soften_closing_grumble(out)
    changed = changed or c6b
    out, c6c = patch_j_strip_post_lose_defiant(out)
    out, c6d = patch_j_fix_can_closing_after_grumble(out)
    changed = changed or c6c or c6d
    for _ in range(5):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(out)
        out, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=4
        )
        changed = changed or cp
        if dialogue_total_chars(out) <= before:
            out, ce = _expand_short_gold_chat_lines(out)
            out, _ = patch_sanitize_natural_expand_stack(out)
            changed = changed or ce
        out, _ = patch_j_strip_role_mismatch_expands(out)
        out, _ = patch_j_soften_closing_grumble(out)
        out, _ = patch_sanitize_bridge_lines(out)
    out, cf = _gold_chat_force_min_chars(out)
    out, c4d = patch_j_drop_post_lose_plea(out)
    out, c5d = patch_j_ensure_post_lose_can_press(out)
    out, _ = patch_j_strip_role_mismatch_expands(out)
    out, _ = patch_j_dedupe_cross_line_phrases(out)
    out, _ = patch_j_cap_ya_particles(out)
    out, _ = patch_sanitize_pad_particles(out)
    for _ in range(4):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(out)
        out, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=12
        )
        changed = changed or cp
        if dialogue_total_chars(out) <= before:
            out, ce = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
            out, _ = patch_sanitize_natural_expand_stack(out)
            changed = changed or ce
            if dialogue_total_chars(out) <= before:
                break
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        out, cf2 = _gold_chat_force_min_chars(out)
        out, _ = patch_j_dedupe_cross_line_phrases(out)
        changed = changed or cf2
    for _ in range(3):
        out, cb = patch_break_consecutive_keep_seed(
            out, dialogue_seed=dialogue_seed, bridge_cap=4
        )
        changed = changed or cb
        if not cb:
            break
        out, _ = patch_sanitize_bridge_lines(out)
    out, c5e = patch_j_drop_post_lose_bridge(out)
    out, c5f = patch_j_fix_post_lose_consecutive_can(out)
    changed = changed or c5e or c5f
    for _ in range(3):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(out)
        out, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=8
        )
        changed = changed or cp
        if dialogue_total_chars(out) <= before:
            break
    for _ in range(4):
        out, ct = patch_j_cap_trailing_particles(out, max_lines=3)
        changed = changed or ct
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        out, ce = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
        out, _ = patch_sanitize_natural_expand_stack(out)
        changed = changed or ce
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            continue
        before = dialogue_total_chars(out)
        out, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=8
        )
        changed = changed or cp
        if dialogue_total_chars(out) <= before:
            break
    changed = changed or cf or c4d or c5d
    return out, changed


def _gold_chat_post_pad_cleanup(story: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """垫字后：B/F/P 类剥句尾垫字 + 再补 min（禁回灌好不好）。"""
    from app.services.daily_story.story_types import apply_gold_chat_strip_filler

    notes: list[str] = []
    out = dict(story)
    st = str(out.get("story_type") or "").strip().upper()
    strip_notes = apply_gold_chat_strip_filler(out)
    if strip_notes:
        notes.extend(strip_notes[:6])
    out, pad_changed = _ensure_gold_chat_min_chars(out)
    if pad_changed:
        notes.append("gold_chat垫字补min")
        strip_notes = apply_gold_chat_strip_filler(out)
        if strip_notes:
            notes.extend(strip_notes[:6])
    # P：补字常加在末尾，认怂截断须在最后一次补字后重跑
    if st == "P":
        from app.services.daily_story.story_types.p.patch import (
            patch_p_fix_surrender_speaker,
            patch_p_strip_pad_tails,
            patch_p_trim_after_surrender,
        )

        for fn in (
            patch_p_strip_pad_tails,
            patch_p_fix_surrender_speaker,
            patch_p_trim_after_surrender,
        ):
            extra = fn(out) or []
            if extra:
                notes.extend(extra[:4])
    return out, notes


def _refine_after_normalize(
    chat: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """normalize 垫字后若仍有非结构性对齐 issue，走一轮精修。"""
    payload = cast(dict[str, Any], row.get("payload") or {})
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    structure_type = str(row.get("structure_type") or chat.get("story_type") or "B")
    structure_type = structure_type.strip().upper()
    mechanism = str(row.get("mechanism") or "").strip().upper()
    closing = _resolve_closing_intent(
        payload,
        scene_contract,
        structure_type=structure_type,
        k_close_mode=str(
            payload.get("k_close_mode")
            or scene_contract.get("k_close_mode")
            or ""
        ),
    )
    beat_chain = scene_contract.get("beat_chain") or []
    if not isinstance(beat_chain, list):
        beat_chain = []
    conflict_text = str(
        scene_contract.get("conflict") or row.get("conflict_core") or ""
    )
    dialogue_seed = payload.get("dialogue_seed") if isinstance(
        payload.get("dialogue_seed"), list
    ) else []
    object_text = str(scene_contract.get("object") or "")
    mechanism_text = str(scene_contract.get("mechanism") or "")
    beat = payload.get("beat") if isinstance(payload.get("beat"), list) else []
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=beat,
    )
    mom_max = scene_contract.get("mom_lines_max")
    if mom_max is None:
        mom_max = 1
    source_type = str(
        payload.get("source_type") or scene_contract.get("source_type") or "field"
    )
    story_raw = str(row.get("story_raw") or payload.get("story_raw") or "")[:800]
    k_close_mode = str(
        payload.get("k_close_mode") or scene_contract.get("k_close_mode") or ""
    ).strip()
    align_block = format_align_block(
        structure_type=structure_type,
        mechanism=mechanism,
        beat=beat,
        closing_intent=closing,
        story_raw=story_raw,
        closing_mode=str(payload.get("closing_mode") or ""),
        k_close_mode=k_close_mode,
    )
    banned_list = [str(x) for x in banned]

    issues = collect_align_issues(
        chat,
        structure_type=structure_type,
        mechanism=mechanism,
        closing_intent=closing,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
        dialogue_seed=dialogue_seed,
        beat=beat,
        object_text=object_text,
        mechanism_text=mechanism_text,
    )
    blocking, _warn = split_align_issues(issues)
    if not blocking:
        return chat
    if any(
        is_structural_align_kind(str(x.get("kind") or "")) for x in blocking
    ):
        return chat

    try:
        refined = refine_gold_chat_align(
            chat,
            structure_type=structure_type,
            mechanism=mechanism,
            align_block=align_block,
            banned_literals=banned_list,
            mom_lines_max=int(mom_max),
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
            dialogue_seed=dialogue_seed,
            beat=beat,
            object_text=object_text,
            mechanism_text=mechanism_text,
            max_rounds=1,
            bail_on_structural=False,
            row=row,
        )
    except ValueError:
        logger.info("gold_chat post-normalize refine skipped: %s", blocking[:2])
        return chat

    refined, _ = _gold_chat_post_pad_cleanup(refined)
    refined, _ = patch_sanitize_pad_suffix(refined)
    if str(refined.get("story_type") or "").strip().upper() == "I":
        from app.services.daily_story.story_types import apply_gold_chat_type_patch

        refined, _ = apply_gold_chat_type_patch(refined, structure_type="I")
    return refined


def apply_gold_chat_normalizations(
    chat: dict[str, Any],
    *,
    row: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """setting 地点映射 + 类型 patch 链（桥接日常故事成熟流水线）。"""
    from app.services.daily_story.story_types import (
        apply_gold_chat_body_pipeline,
    )

    notes: list[str] = []
    payload = cast(dict[str, Any], (row or {}).get("payload") or {})
    _sc_raw = payload.get("scene_contract")
    if isinstance(_sc_raw, dict):
        sc = _sc_raw
    else:
        sc = {}
    st = str(
        (row or {}).get("structure_type") or chat.get("story_type") or ""
    ).strip().upper()
    _chars_raw = sc.get("characters")
    raw_chars = _chars_raw if isinstance(_chars_raw, list) else []
    characters = tuple(str(c).strip() for c in raw_chars if str(c).strip())
    if len(characters) < 2:
        characters = ("灿灿", "昭昭")

    mech = str((row or {}).get("mechanism") or payload.get("mechanism") or "").strip()

    # I 类家长拷问补丁依赖 beat_chain
    if not isinstance(chat.get("gold_beat_chain"), list):
        chain = sc.get("beat_chain")
        if isinstance(chain, list):
            chat = dict(chat)
            chat["gold_beat_chain"] = chain

    new_setting, sn = normalize_gold_chat_setting(
        str(chat.get("setting") or ""),
        scene_contract_location=str(sc.get("location") or ""),
        activity_context=" ".join(
            x
            for x in (
                str(sc.get("object") or ""),
                str(sc.get("conflict") or ""),
                str((row or {}).get("conflict_core") or ""),
            )
            if x
        ),
        characters=characters,
    )
    if sn:
        notes.extend(sn)
        chat["setting"] = new_setting
    from app.services.script.visual_brief import enrich_setting_with_dialogue_props

    before_setting = str(chat.get("setting") or "")
    after_setting = enrich_setting_with_dialogue_props(
        before_setting,
        chat.get("dialogue") or [],
        contract_object=str(sc.get("object") or ""),
    )
    if after_setting != before_setting:
        chat["setting"] = after_setting
        notes.append("setting 补冲突物持有")
    if st:
        # M2+C 已有专用 patch 链；勿再走 daily_story 的连说改 speaker / 整件肉 filler
        if not (st == "C" and mech.upper() == "M2"):
            seed_raw = payload.get("dialogue_seed")
            chat, type_notes = apply_gold_chat_body_pipeline(
                chat,
                structure_type=st,
                dialogue_seed=seed_raw if isinstance(seed_raw, list) else None,
            )
            notes.extend(type_notes)
        from app.services.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        notes.extend(patch_dialogue_narration_to_speech(chat))
    from app.services.gold_story.gold_chat.patch import (
        patch_gold_chat_c_seed_bridge,
        patch_gold_chat_dedupe_dialogue_loop,
        patch_gold_chat_post_close_tail,
        patch_m2_c_ensure_seed_close,
        patch_m2_c_break_eating_consecutive,
        patch_m2_c_eating_roles,
        patch_m2_c_fix_opening,
        patch_m2_c_structure,
    )

    chat, loop_notes = patch_gold_chat_dedupe_dialogue_loop(chat)
    notes.extend(loop_notes)
    if st == "C" and mech.upper() == "M2":
        theme = str(
            chat.get("scene_title")
            or (row or {}).get("title")
            or payload.get("title")
            or ""
        ).strip()
        chat, open_notes = patch_m2_c_fix_opening(chat, payload=payload)
        notes.extend(open_notes)
        chat, eat_notes = patch_m2_c_eating_roles(
            chat, structure_type=st, mechanism=mech,
        )
        notes.extend(eat_notes)
        chat, br_notes = patch_m2_c_break_eating_consecutive(
            chat, structure_type=st, mechanism=mech,
        )
        notes.extend(br_notes)
        chat, bridge_notes = patch_gold_chat_c_seed_bridge(
            chat,
            structure_type=st,
            mechanism=mech,
            payload=payload,
        )
        notes.extend(bridge_notes)
        chat, struct_notes = patch_m2_c_structure(
            chat,
            structure_type=st,
            mechanism=mech,
            theme=theme,
            payload=payload,
        )
        notes.extend(struct_notes)
    chat, tail_notes = patch_gold_chat_post_close_tail(
        chat,
        payload=payload,
        structure_type=st,
        mechanism=mech,
    )
    notes.extend(tail_notes)
    if st == "C" and mech.upper() == "M2":
        chat, close_notes = patch_m2_c_ensure_seed_close(chat, payload=payload)
        notes.extend(close_notes)
    chat, pad_changed = _ensure_gold_chat_min_chars(chat)
    if pad_changed:
        notes.append("gold_chat垫字补min")
    chat, cleanup_notes = _gold_chat_post_pad_cleanup(chat)
    notes.extend(cleanup_notes)
    chat, san_changed = patch_sanitize_pad_suffix(chat)
    if san_changed:
        notes.append("gold_chat去叠语气词")
        chat, pad_changed2 = _ensure_gold_chat_min_chars(chat)
        if pad_changed2:
            notes.append("gold_chat垫字补min")
        chat, _ = patch_sanitize_pad_suffix(chat)
    from app.services.gold_story.gold_chat.patch import (
        patch_trim_redundant_ne_suffix,
    )

    chat, ne_notes = patch_trim_redundant_ne_suffix(chat)
    notes.extend(ne_notes)
    chat, trimmed = _apply_deterministic_shorten(chat)
    if trimmed:
        notes.append("gold_chat截长句")
    return chat, notes


def validate_gold_chat(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "",
    mom_lines_max: int | None = None,
) -> None:
    """gold_chat 校验：字段/字数/speaker 对齐日常故事常量，再追加金稿独有项。"""
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

    errors.extend(setting_location_violations(str(story.get("setting") or "")))

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


def _attach_gold_chat_structure_score(
    chat: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """导出前算结构分（不含 LLM 好笑）；写回 chat.quality。"""
    from app.services.daily_story.prompts import sync_discovery_opening_from_dialogue
    from app.services.daily_story.quality import attach_daily_story_quality

    out = dict(chat)
    st = str(row.get("structure_type") or out.get("story_type") or "").strip().upper()
    if st:
        out["story_type"] = st
    theme = str(
        row.get("title")
        or out.get("scene_title")
        or out.get("key")
        or row.get("source_id")
        or ""
    ).strip()
    payload_raw = row.get("payload")
    payload: dict[str, Any] = (
        payload_raw if isinstance(payload_raw, dict) else {}
    )
    scene_contract: dict[str, Any] = {}
    sc_raw = payload.get("scene_contract")
    if isinstance(sc_raw, dict):
        scene_contract = sc_raw
    mom_contract = scene_contract.get("mom_lines_max")
    if mom_contract is not None:
        try:
            out["_gold_chat_mom_lines_max"] = int(mom_contract)
        except (TypeError, ValueError):
            pass
    # 按正文一体计分：勿把前 2 句 sync 成 discovery_opening 再扣开场分
    out.pop("discovery_opening", None)
    attach_daily_story_quality(out, theme=theme, finalize=True, skip_relevancy=True)
    sync_discovery_opening_from_dialogue(out)
    return out


def _gate_gold_chat_structure_score(chat: dict[str, Any]) -> int:
    """结构分未过线则抛 structure_score:{n}。"""
    from app.services.daily_story.quality import (
        STRUCTURE_PUBLISH_MIN,
        structure_score_of,
    )

    quality = cast(dict[str, Any], chat.get("quality")) if isinstance(
        chat.get("quality"), dict
    ) else {}
    struct = structure_score_of(quality)
    if struct < STRUCTURE_PUBLISH_MIN:
        raise ValueError(f"structure_score:{struct}")
    return struct


def _format_gold_chat_dialogue_tail3(chat: dict[str, Any]) -> str:
    dialogue = chat.get("dialogue")
    if not isinstance(dialogue, list):
        return ""
    parts: list[str] = []
    for item in dialogue[-3:]:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp or line:
            parts.append(f"{sp}:{line}")
    return " | ".join(parts)


def log_gold_chat_structure_score_fail(
    chat: dict[str, Any],
    quality: dict[str, Any] | None,
    *,
    structure_type: str = "",
) -> None:
    """结构分终检失败：记录类型、扣分项与末三句，便于对照规则。"""
    from app.services.daily_story.quality import structure_cons_for_log

    q = quality if isinstance(quality, dict) else {}
    reasons = [str(r) for r in (q.get("reasons") or [])]
    cons = structure_cons_for_log(q)
    logger.info(
        "gold_chat structure_score fail type=%s score=%s summary=%s "
        "cons=%s reasons=%s tail3=%s",
        structure_type or chat.get("story_type") or "?",
        q.get("structure_score") or q.get("score"),
        q.get("summary"),
        cons[:12],
        reasons[:20],
        _format_gold_chat_dialogue_tail3(chat),
    )


def _persist_m5_h_contract_if_needed(row: dict[str, Any]) -> dict[str, Any]:
    """M5+H 契约修复回写 DB，返回刷新后的 row。"""
    gid = int(row.get("id") or 0)
    mechanism = str(row.get("mechanism") or "").upper()
    structure_type = str(row.get("structure_type") or "").strip().upper()
    if gid <= 0 or mechanism != "M5" or structure_type != "H":
        return row

    payload = cast(dict[str, Any], row.get("payload") or {})
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}

    conflict_core = str(row.get("conflict_core") or "")
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
    if not core_changed and not sc_changed:
        return row

    if sc_changed:
        repo_gold_story.patch_story_payload(gid, {"scene_contract": repaired_sc})
    if core_changed:
        repo_gold_story.update_conflict_core(gid, conflict_core)
    return repo_gold_story.get_story(gid) or row


def _rebuild_h3a_h3b_on_convert(row: dict[str, Any]) -> dict[str, Any]:
    """重转入口：用库内 story_raw + H3 字段重跑 H3a/H3b，刷新契约后再扩写。

    这是「重转对话稿」的切入点——不必从 BV 重新导入。
    H3a/H3b 失败则保留旧契约，避免整条重转中断。
    """
    from app.services.gold_story.collect.llm import (
        build_dialogue_seed,
        build_scene_contract,
    )
    from app.services.gold_story.scene import (
        remap_story_raw_scores_for_prompt,
        remap_story_raw_sibling_roles,
        sanitize_banned_literals,
        scrub_h3_beat_list,
        sync_contract_exam_scores,
    )

    payload = dict(cast(dict[str, Any], row.get("payload") or {}))
    raw0 = str(row.get("story_raw") or payload.get("story_raw") or "").strip()
    story_raw = remap_story_raw_sibling_roles(raw0)
    if len(story_raw) < 40:
        logger.warning(
            "[GOLD_CHAT] skip H3a/H3b rebuild id=%s: story_raw too short",
            row.get("id"),
        )
        return row

    beat_raw = payload.get("beat") if isinstance(payload.get("beat"), list) else []
    beat = scrub_h3_beat_list(beat_raw, story_raw=story_raw)
    # 源稿做了姐弟名归一时，旧 conflict_core 可能角色反了，勿灌进 H3a
    conflict_for_h3 = str(row.get("conflict_core") or "")
    if story_raw != raw0:
        conflict_for_h3 = ""
    h3: dict[str, Any] = {
        "title": row.get("title"),
        "conflict_core": conflict_for_h3,
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "theme_family": row.get("theme_family"),
        "beat": beat,
        "funny_why": payload.get("funny_why"),
        "banned_literals": payload.get("banned_literals") or [],
        "structure_mapping_note": payload.get("structure_mapping_note") or "",
        "structure_confidence": float(payload.get("structure_confidence") or 0.8),
    }
    source_type = str(payload.get("source_type") or "field")
    try:
        h3a = build_scene_contract(
            story_raw=story_raw,
            h3=h3,
            source_type=source_type,
        )
    except Exception as exc:
        logger.warning(
            "[GOLD_CHAT] H3a rebuild failed id=%s: %s; keep old contract",
            row.get("id"),
            exc,
        )
        return row

    # 库表 structure_type 覆盖 LLM 可能写偏的 story_type（如 K 稿被标 C）
    _row_st = str(row.get("structure_type") or "").strip().upper()
    if _row_st:
        h3a = dict(h3a)
        h3a["story_type"] = _row_st

    # H3b 也勿吃未迁龄 story_raw
    story_raw_for_seed = remap_story_raw_scores_for_prompt(
        story_raw,
        contract=h3a,
    )
    try:
        h3b = build_dialogue_seed(
            story_raw=story_raw_for_seed,
            h3=h3,
            scene_contract=h3a,
        )
    except Exception as exc:
        # H3a 已含迁龄/家长预算；H3b 失败时用 beat_chain 兜底 seed，勿整段回退
        from app.services.gold_story.scene import seed_from_beat_chain

        logger.warning(
            "[GOLD_CHAT] H3b rebuild failed id=%s: %s; keep H3a + beat_chain seed",
            row.get("id"),
            exc,
        )
        h3b = {
            "setting": h3a.get("location"),
            "dialogue_seed": seed_from_beat_chain(h3a.get("beat_chain") or []),
            "closing_intent": h3a.get("closing_intent"),
            "speaker_map_note": h3a.get("remap_note"),
            "dialogue_confidence": 0.5,
        }

    banned = sanitize_banned_literals(
        h3a.get("banned_literals") or payload.get("banned_literals"),
        scene_contract=h3a,
        beat=beat,
    )
    seed_list = h3b.get("dialogue_seed") or []
    remapped_core = str(h3a.get("conflict") or "").strip()
    h3a, remapped_core, _score_synced = sync_contract_exam_scores(
        h3a,
        dialogue_seed=seed_list if isinstance(seed_list, list) else [],
        conflict_core=remapped_core,
    )
    patch: dict[str, Any] = {
        "scene_contract": h3a,
        "contract_confidence": h3a.get("contract_confidence"),
        "dialogue_seed": seed_list,
        "closing_intent": (
            h3b.get("closing_intent") or h3a.get("closing_intent")
        ),
        "speaker_map_note": (
            h3b.get("speaker_map_note") or h3a.get("remap_note")
        ),
        "setting": h3b.get("setting") or h3a.get("location"),
        "dialogue_confidence": h3b.get("dialogue_confidence"),
        "banned_literals": banned,
    }
    payload.update(patch)
    out = dict(row)
    out["payload"] = payload
    # 迁龄/remap 后以 scene conflict 为准，勿沿用站外旧 conflict_core
    if remapped_core:
        out["conflict_core"] = remapped_core
    gid = int(row.get("id") or 0)
    if gid > 0:
        try:
            repo_gold_story.patch_story_payload(gid, patch)
            if remapped_core:
                repo_gold_story.update_conflict_core(gid, remapped_core)
        except Exception as exc:
            logger.warning(
                "[GOLD_CHAT] persist rebuilt contract failed id=%s: %s",
                gid,
                exc,
            )
    logger.info(
        "[GOLD_CHAT] rebuilt H3a/H3b id=%s mom_lines_max=%s chars=%s",
        row.get("id"),
        h3a.get("mom_lines_max"),
        ",".join(str(c) for c in (h3a.get("characters") or [])),
    )
    return out


def convert_gold_chat(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any]:
    """转换 + 落盘，返回摘要。

    会先重跑 H3a/H3b 刷新 scene_contract（重转的切入点），再扩写对白。
    """
    from app.services.gold_story.gold_chat.finalize import run_gold_chat_finalize

    row = _persist_m5_h_contract_if_needed(row)
    row, structure_notes = _resolve_structure_row(row)
    row = _persist_structure_correction(row, structure_notes)
    row = _rebuild_h3a_h3b_on_convert(row)
    sid = str(row.get("source_id") or "").strip()
    chat = gold_story_to_gold_chat(row)
    chat, norm_notes = apply_gold_chat_normalizations(chat, row=row)
    payload0 = cast(dict[str, Any], row.get("payload") or {})
    chat = _realign_j_role_speakers(
        chat,
        dialogue_seed=payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None,
        structure_type=str(row.get("structure_type") or ""),
    )
    chat = _refine_after_normalize(chat, row)
    _st0 = str(row.get("structure_type") or chat.get("story_type") or "")
    _mech0 = str(row.get("mechanism") or "")
    chat, _ = _ensure_gold_chat_min_chars(
        chat,
        mechanism=_mech0,
        structure_type=_st0,
    )
    chat = _realign_j_role_speakers(
        chat,
        dialogue_seed=payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None,
        structure_type=str(row.get("structure_type") or ""),
    )
    chat, struct = run_gold_chat_finalize(
        chat,
        row,
        sid=sid,
        norm_notes=list(norm_notes or []),
        payload0=payload0,
        st0=_st0,
        mech0=_mech0,
    )
    cfg = config or Config()
    paths = export_gold_chat_files(
        source_id=sid,
        row=row,
        chat=chat,
        config=cfg,
    )
    _backfill_gold_story_after_export(row, chat=chat, paths=paths, config=cfg)
    logger.info("[GOLD_CHAT] convert %s exported paths=%s", sid, list(paths.keys()))
    return {
        "ok": True,
        "generated": True,
        "exported": True,
        "backfilled": True,
        "source_id": sid,
        "gold_story_id": row.get("id"),
        "chat_chars": dialogue_total_chars(chat),
        "chat_lines": len(chat.get("dialogue") or []),
        "scene_title": chat.get("scene_title"),
        "structure_score": struct,
        "quality": chat.get("quality"),
        "export": paths,
        "daily_story": chat,
    }
