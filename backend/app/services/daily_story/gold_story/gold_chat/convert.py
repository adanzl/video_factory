"""gold_chat：金故事 → 日常对白（独立流程，不入 H0–H4 采集流水线）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
    patch_m5_break_sibling_consecutive,
    patch_remap_sibling_terms,
)
from app.services.daily_story.gold_story.gold_chat.prompts import (
    CHAT_MAX_LINE_CHARS,
    _ALIGN_REFINE_SYSTEM,
    _ALIGN_REFINE_USER,
    _FIX_SYSTEM,
    _FIX_USER,
    _SHORTEN_SYSTEM,
    _SHORTEN_USER,
    _SYSTEM,
    _USER,
    format_beat_sequence_block,
    format_align_block,
    format_align_issues_block,
    format_m5_h_pass1_beat_block,
    format_pass1_regen_feedback,
    format_role_binding_block,
)
from app.services.daily_story.gold_story.gold_chat.validate import (
    collect_align_issues,
    is_structural_align_kind,
    pass1_align_score,
    repair_m5_h_conflict_core,
    repair_m5_h_scene_contract,
    should_regenerate_pass1,
    split_align_issues,
    validate_chat_hard,
    validate_contract_role_consistency,
)
from app.services.daily_story.gold_story.collect.llm import resolve_gold_chat_snippet
from app.services.daily_story.gold_story.scene import (
    format_scene_block,
    sanitize_banned_literals,
)
from app.services.daily_story.gold_story.gold_chat.setting import (
    normalize_gold_chat_setting,
    setting_location_violations,
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
from app.services.daily_story.gold_story.gold_chat.export import (
    _backfill_gold_story_after_export,
    export_gold_chat_files,
    gold_chat_export_dir,
    gold_chat_summary,
    load_gold_chat,
    load_gold_chat_for_row,
)
from app.services.daily_story.gold_story.gold_chat.import_story import (
    import_gold_chat_daily_story,
)
from app.services.daily_story.gold_story.gold_chat.polish import (
    _apply_gold_chat_polish_fixes,
    collect_gold_chat_polish_issues,
    polish_gold_chat_export,
    polish_gold_chat_wording,
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
    """读取 closing；I 类与 seed 制敌 speaker 冲突时以 seed 为准。"""
    closing = str(
        payload.get("closing_intent") or scene_contract.get("closing_intent") or ""
    )
    st = str(structure_type or "").strip().upper()
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
    """I：Pass2 前本地收束裁尾；裁短则抛错打回 Pass1 加长争锋。"""
    from app.services.daily_story.gold_story.gold_chat.patch import (
        patch_gold_chat_post_close_tail,
        patch_m5_break_sibling_consecutive,
    )
    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN
    from app.services.daily_story.story_types.i.patch import patch_i_body

    data = dict(story)
    data["story_type"] = "I"
    patch_i_body(data)
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
        # 打回 Pass1：服软过早、争锋不够
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
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    sc = payload.get("scene_contract") if isinstance(payload.get("scene_contract"), dict) else {}
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


PASS1_CANDIDATE_COUNT = 4
PASS1_REGENERATE_MAX = 5
PASS2_MAX_ROUNDS = 2
GOLD_CHAT_NEAR_MISS_DEFICIT_MAX = 3
_RE_PAD_SUFFIX_STACK = re.compile(
    r"呢呢|啊呢|吧呢|嘛呢|呀呢|你呀呢|行了吧呢|不懂你呢|听听不懂|你真是呢|你真是的呢|"
    r"了呢了呀|了呢呀|了呀呢|好不好了呀|着呢了呀",
)
_B_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧", "真的呀")
_F_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧")


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
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        max_line=CHAT_MAX_LINE_CHARS,
    )
    return _chat_json(_FIX_SYSTEM, user)


_LINE_TRIM_SUFFIXES = ("！", "。", "!", "？", "?", "啊", "呢", "吧", "嘛", "呀", "哦")


def _overlong_line_indices(story: dict[str, Any], max_chars: int = CHAT_MAX_LINE_CHARS) -> list[int]:
    out: list[int] = []
    for i, item in enumerate(story.get("dialogue") or [], 1):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if len(line) > max_chars:
            out.append(i)
    return out


def _trim_line_det(line: str, max_chars: int = CHAT_MAX_LINE_CHARS) -> str:
    """超长不多时去尾语气/标点，避免整稿重抽。"""
    s = str(line or "").strip()
    guard = 0
    while len(s) > max_chars and guard < 8:
        guard += 1
        trimmed = False
        for suf in _LINE_TRIM_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)].strip()
                trimmed = True
                break
        if not trimmed:
            break
    return s


def _apply_deterministic_shorten(
    story: dict[str, Any],
    *,
    max_chars: int = CHAT_MAX_LINE_CHARS,
) -> tuple[dict[str, Any], bool]:
    """逐句微 trim；有改动则返回新 story。"""
    import copy

    indices = _overlong_line_indices(story, max_chars)
    if not indices:
        return story, False
    out = copy.deepcopy(story)
    rows = out.get("dialogue") or []
    changed = False
    for no in indices:
        idx = no - 1
        if not (0 <= idx < len(rows) and isinstance(rows[idx], dict)):
            continue
        old = str(rows[idx].get("line") or "").strip()
        new = _trim_line_det(old, max_chars)
        if new != old and len(new) <= max_chars:
            rows[idx]["line"] = new
            changed = True
    return out, changed


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


def _sanitize_pad_suffix_line(line: str) -> str:
    """机械去叠语气词（呢呢/啊呢/你呀呢等），不改剧情。"""
    out = line
    for old, new in (
        ("呢呢", "呢"),
        ("啊呢", "啊"),
        ("吧呢", "吧"),
        ("嘛呢", "嘛"),
        ("呀呢", "呀"),
        ("你呀呢", "你呀"),
        ("行了吧呢", "行了吧"),
        ("不懂你呢", "听不懂你"),
        ("听听不懂", "听不懂"),
        ("你真是呢", "你真是的"),
        ("你真是的呢", "你真是的"),
        ("着呢了呀", "着呢"),
        ("你听着了呀", ""),
        ("你听着呀", ""),
        ("好呢了呀", "呢"),
        ("好不好了呀", ""),
        ("了呢了呀", ""),
        ("了呢呀", ""),
        ("了呀呢", ""),
    ):
        if old in out:
            out = out.replace(old, new)
    return out


def patch_sanitize_pad_suffix(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """垫字后收口：去掉呢呢/啊呢等叠字。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old or not _RE_PAD_SUFFIX_STACK.search(old):
            continue
        new = _sanitize_pad_suffix_line(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def _pad_gold_chat_line(
    line: str,
    need: int,
    *,
    used: set[str] | None = None,
    story_type: str = "",
) -> tuple[str, int]:
    """near-miss 本地垫字：走日常故事同一套句尾垫字。"""
    from app.services.daily_story.prompts import _pad_dialogue_line

    st = str(story_type or "").strip().upper()
    if st == "B":
        tails = _B_GOLD_CHAT_PAD_TAILS
    elif st == "F":
        tails = _F_GOLD_CHAT_PAD_TAILS
    else:
        tails = None
    return _pad_dialogue_line(line, need, used, tails=tails)


def _gold_chat_pad_indices(
    dialogue: list[Any],
    *,
    story_type: str,
) -> list[int]:
    """可垫字行号；I 类排除收束段（首次制敌/服软后）与末 2 句。"""
    indices = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
    ] or list(range(len(dialogue)))
    st = str(story_type or "").strip().upper()
    if st != "I":
        return indices
    from app.services.daily_story.story_types.i.validate import (
        RE_WIN_STUBBORN,
        find_i_close_index,
    )

    lines = [
        str(item.get("line") or "")
        for item in dialogue
        if isinstance(item, dict)
    ]
    close_idx = find_i_close_index(lines)
    protected: set[int] = set()
    for i, item in enumerate(dialogue):
        if isinstance(item, dict) and RE_WIN_STUBBORN.search(
            str(item.get("line") or "")
        ):
            protected.add(i)
    if close_idx >= 0:
        protected.update(range(close_idx, len(dialogue)))
    if len(dialogue) > 2:
        protected.add(len(dialogue) - 1)
        protected.add(len(dialogue) - 2)
    kept = [i for i in indices if i not in protected]
    return kept or indices


def _patch_gold_chat_near_miss_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """240 hard 不变；差 ≤3 字时本地垫字收口。"""
    import copy

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, False

    story_type = str(story.get("story_type") or "").strip().upper()
    indices = _gold_chat_pad_indices(dialogue, story_type=story_type)

    changed = False
    used_pads: set[str] = set()
    story_type = str(story.get("story_type") or "").strip().upper()
    for idx in reversed(indices):
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        new_line, added = _pad_gold_chat_line(
            line, need, used=used_pads, story_type=story_type,
        )
        if added <= 0:
            continue
        item["line"] = new_line
        need -= added
        changed = True
        if need <= 0:
            break
    return out, changed


def _pad_gold_chat_to_min_chars(
    story: dict[str, Any],
    *,
    min_chars: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Pass2 改短/删尾后垫字至 hard min（不限 near_miss 3 字）。"""
    import copy

    floor = int(min_chars or DAILY_STORY_BODY_CHARS_MIN)
    total = dialogue_total_chars(story)
    need = floor - total
    if need <= 0:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, False

    indices = _gold_chat_pad_indices(
        dialogue, story_type=str(story.get("story_type") or "")
    )

    changed = False
    used_pads: set[str] = set()
    story_type = str(story.get("story_type") or "").strip().upper()
    # 多轮垫字：单轮每句最多补一尾巴，循环直到满或停步
    for _ in range(12):
        need = floor - dialogue_total_chars(out)
        if need <= 0:
            break
        progressed = False
        for idx in reversed(indices):
            need = floor - dialogue_total_chars(out)
            if need <= 0:
                break
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            new_line, added = _pad_gold_chat_line(
                line, need, used=used_pads, story_type=story_type,
            )
            if added <= 0:
                continue
            item["line"] = new_line
            changed = True
            progressed = True
        if not progressed:
            break
    return out, changed


def _ensure_gold_chat_min_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    data, changed = _patch_gold_chat_near_miss_chars(story)
    if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
        return data, changed
    data2, changed2 = _pad_gold_chat_to_min_chars(data)
    return data2, changed or changed2


def _gold_chat_post_pad_cleanup(story: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """垫字后：B 类剥句尾垫字 + 再补 min（禁回灌好不好）。"""
    from app.services.daily_story.story_types.b.patch import patch_b_strip_filler
    from app.services.daily_story.story_types.f.patch import patch_f_strip_filler

    notes: list[str] = []
    out = dict(story)
    st = str(out.get("story_type") or "").strip().upper()
    if st == "B":
        strip_notes = patch_b_strip_filler(out)
        if strip_notes:
            notes.extend(strip_notes[:6])
    elif st == "F":
        strip_notes = patch_f_strip_filler(out)
        if strip_notes:
            notes.extend(strip_notes[:6])
    out, pad_changed = _ensure_gold_chat_min_chars(out)
    if pad_changed:
        notes.append("gold_chat垫字补min")
        if st == "B":
            strip_notes = patch_b_strip_filler(out)
            if strip_notes:
                notes.extend(strip_notes[:6])
        elif st == "F":
            strip_notes = patch_f_strip_filler(out)
            if strip_notes:
                notes.extend(strip_notes[:6])
    return out, notes


def _refine_after_normalize(
    chat: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """normalize 垫字后若仍有非结构性对齐 issue，走一轮 Pass2 精修。"""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    structure_type = str(row.get("structure_type") or chat.get("story_type") or "B")
    structure_type = structure_type.strip().upper()
    mechanism = str(row.get("mechanism") or "").strip().upper()
    closing = _resolve_closing_intent(
        payload, scene_contract, structure_type=structure_type
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
    align_block = format_align_block(
        structure_type=structure_type,
        mechanism=mechanism,
        beat=beat,
        closing_intent=closing,
        story_raw=story_raw,
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
        )
    except ValueError:
        logger.info("gold_chat post-normalize refine skipped: %s", blocking[:2])
        return chat

    refined, _ = _gold_chat_post_pad_cleanup(refined)
    refined, _ = patch_sanitize_pad_suffix(refined)
    if str(refined.get("story_type") or "").strip().upper() == "I":
        from app.services.daily_story.story_types.i.patch import patch_i_body

        patch_i_body(refined)
    return refined


def _prepare_chat_for_validate(
    data: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    conflict_text: str = "",
    banned_literals: list[str] | None = None,
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    """M5+H 本地补丁 → 补字数 → hard 校验（LLM 精修后亦须先补丁再验）。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if mech == "M5" and st == "H":
        data, _ = apply_m5_h_local_patches(
            data,
            closing_intent=closing_intent,
            conflict_text=conflict_text,
        )
    data, _ = _ensure_gold_chat_min_chars(data)
    validate_gold_chat(
        data,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
    )
    return data


def _validate_pass1_chat(
    story: dict[str, Any],
    *,
    banned_literals: list[str],
    source_type: str,
    mom_lines_max: int,
) -> dict[str, Any]:
    """Pass1 硬校验 + 格式 fix，直至通过或耗尽 retry。"""
    data = _normalize_chat_speakers(dict(story))
    last_err = ""
    shorten_llm_used = False
    for attempt in range(5):
        data, _ = _ensure_gold_chat_min_chars(data)
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
    raise ValueError(last_err or "gold_chat validate failed")


def _generate_pass1_candidate(
    user: str,
    *,
    banned_literals: list[str],
    source_type: str,
    mom_lines_max: int,
) -> dict[str, Any]:
    data = _normalize_chat_speakers(_chat_json(_SYSTEM, user))
    return _validate_pass1_chat(
        data,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
    )


def _pick_pass1_candidate(
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
        raise ValueError("no pass1 candidates")
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
        return pass1_align_score(
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


def _align_refine_with_llm(
    story: dict[str, Any],
    issues: list[dict[str, Any]],
    *,
    align_block: str,
    banned_literals: list[str],
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    user = _ALIGN_REFINE_USER.format(
        issues_block=format_align_issues_block(issues),
        align_block=align_block,
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
        max_line=CHAT_MAX_LINE_CHARS,
    )
    return _chat_json(_ALIGN_REFINE_SYSTEM, user)


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
    max_rounds: int = PASS2_MAX_ROUNDS,
    bail_on_structural: bool = True,
) -> dict[str, Any]:
    """Pass 2：对齐机审 → LLM 定点精修 → 再 hard 校验。"""
    banned = [str(x) for x in (banned_literals or []) if str(x).strip()]
    mom_max = max(0, int(mom_lines_max))
    closing = str(closing_intent or "").strip()
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()

    for _round in range(max(1, int(max_rounds))):
        if mech == "M5" and st == "H":
            data, _ = apply_m5_h_local_patches(
                data,
                closing_intent=closing,
                conflict_text=conflict_text,
            )
        if st == "I":
            data = _apply_i_close_local_patches(
                data,
                mechanism=mech,
                dialogue_seed=dialogue_seed,
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
            )
        if bail_on_structural and should_regenerate_pass1(blocking):
            struct_kinds = [
                str(x.get("kind") or "")
                for x in blocking
                if is_structural_align_kind(str(x.get("kind") or ""))
            ]
            kinds = "、".join(struct_kinds[:3]) or "、".join(
                str(x.get("kind") or "") for x in blocking[:3]
            )
            raise ValueError(f"align_structural:{kinds}")

        raw = _align_refine_with_llm(
            data,
            blocking + warn,
            align_block=align_block,
            banned_literals=banned,
            mom_lines_max=mom_max,
        )
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
    blocking_remain, warn_remain = split_align_issues(remain)
    if blocking_remain:
        kinds = "、".join(str(x.get("kind") or "") for x in blocking_remain[:3])
        raise ValueError(f"align_refine_failed:{kinds}")
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
    )
    return data


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


def apply_gold_chat_normalizations(
    chat: dict[str, Any],
    *,
    row: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """setting 地点映射 + 类型 patch 链（桥接日常故事成熟流水线）。"""
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        apply_type_body_pipeline,
    )

    notes: list[str] = []
    payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
    sc = payload.get("scene_contract") if isinstance(payload.get("scene_contract"), dict) else {}
    st = str(
        (row or {}).get("structure_type") or chat.get("story_type") or ""
    ).strip().upper()
    raw_chars = sc.get("characters") if isinstance(sc.get("characters"), list) else []
    characters = tuple(str(c).strip() for c in raw_chars if str(c).strip())
    if len(characters) < 2:
        characters = ("灿灿", "昭昭")

    mech = str((row or {}).get("mechanism") or payload.get("mechanism") or "").strip()

    new_setting, sn = normalize_gold_chat_setting(
        str(chat.get("setting") or ""),
        scene_contract_location=str(sc.get("location") or ""),
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
            chat, type_notes = apply_type_body_pipeline(chat, structure_type=st)
            notes.extend(type_notes)
    from app.services.daily_story.gold_story.gold_chat.patch import (
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
    from app.services.daily_story.gold_story.gold_chat.patch import (
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


def _is_short_content_error(msg: str) -> bool:
    """字数/句数不足 → 不重试，直接放弃。"""
    return (
        "正文总字数须≥" in msg
        or "dialogue 至少" in msg
        or "对白句数须≥" in msg
    )


def _structure_type_hint(structure_type: str, mechanism: str = "") -> str:
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        structure_type_hint,
    )

    return structure_type_hint(structure_type=structure_type, mechanism=mechanism)


def gold_story_to_gold_chat(row: dict[str, Any]) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    row = _repair_i_row_contract(row)
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    structure_type = str(row.get("structure_type") or "A").strip().upper()
    st_label = structure_type_label(structure_type)
    scene_contract = payload.get("scene_contract") or {}
    if not isinstance(scene_contract, dict):
        scene_contract = {}
    conflict_core = str(row.get("conflict_core") or "")
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
        story_raw=story_raw,
    )
    m5_h_beat_block = ""
    if mechanism.upper() == "M5" and structure_type == "H":
        m5_h_beat_block = format_m5_h_pass1_beat_block(
            conflict_text=conflict_text,
            closing_intent=closing,
        )

    banned_list = [str(x) for x in banned]
    mom_int = int(mom_max)
    last_err = ""
    pass1_feedback_block = ""
    for _regen in range(PASS1_REGENERATE_MAX):
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
            pass1_feedback_block=pass1_feedback_block,
            dialogue_seed=_format_dialogue_seed(seed)[:4000],
            closing_intent=closing,
            speaker_map_note=str(
                payload.get("speaker_map_note")
                or scene_contract.get("remap_note")
                or ""
            )[:500],
            story_raw=story_raw or "（无）",
            banned_literals="、".join(str(x) for x in banned) or "（无）",
            funny_why=str(payload.get("funny_why") or "")[:500],
            source_type=source_type,
            structure_hint=_structure_type_hint(structure_type, mechanism),
            align_block=align_block,
            gold_chat_snippet=resolve_gold_chat_snippet(str(row.get("source_id") or "")),
            chars_min=DAILY_STORY_BODY_CHARS_MIN,
            chars_max=DAILY_STORY_BODY_CHARS_MAX,
        )
        candidates: list[dict[str, Any]] = []
        for _ in range(PASS1_CANDIDATE_COUNT):
            try:
                candidates.append(
                    _generate_pass1_candidate(
                        user,
                        banned_literals=banned_list,
                        source_type=source_type,
                        mom_lines_max=mom_int,
                    )
                )
            except ValueError as exc:
                last_err = str(exc)
        if not candidates:
            continue
        data = _pick_pass1_candidate(
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
        try:
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
                max_rounds=PASS2_MAX_ROUNDS,
                bail_on_structural=True,
            )
            if conflict_core:
                chat["conflict_core"] = conflict_core
            chat = _attach_gold_chat_structure_score(chat, row)
            try:
                _gate_gold_chat_structure_score(chat)
            except ValueError as score_exc:
                last_err = str(score_exc)
                pass1_feedback_block = format_pass1_regen_feedback(
                    last_err,
                    chat,
                    structure_type=structure_type,
                    mechanism=mechanism,
                    closing_intent=closing,
                    beat_chain=beat_chain,
                    conflict_text=conflict_text,
                )
                continue
            return chat
        except ValueError as exc:
            last_err = str(exc)
            if not str(exc).startswith(
                ("align_structural:", "align_refine_failed:", "structure_score:")
            ):
                raise
            pass1_feedback_block = format_pass1_regen_feedback(
                last_err,
                data,
                structure_type=structure_type,
                mechanism=mechanism,
                closing_intent=closing,
                beat_chain=beat_chain,
                conflict_text=conflict_text,
            )
    raise ValueError(last_err or "gold_chat generation failed")



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
        out.get("scene_title")
        or out.get("key")
        or row.get("title")
        or row.get("source_id")
        or ""
    ).strip()
    sync_discovery_opening_from_dialogue(out)
    attach_daily_story_quality(out, theme=theme, finalize=True)
    return out


def _gate_gold_chat_structure_score(chat: dict[str, Any]) -> int:
    """结构分未过线则抛 structure_score:{n}。"""
    from app.services.daily_story.quality import (
        STRUCTURE_PUBLISH_MIN,
        structure_score_of,
    )

    quality = chat.get("quality") if isinstance(chat.get("quality"), dict) else {}
    struct = structure_score_of(quality)
    if struct < STRUCTURE_PUBLISH_MIN:
        raise ValueError(f"structure_score:{struct}")
    return struct


def _persist_m5_h_contract_if_needed(row: dict[str, Any]) -> dict[str, Any]:
    """M5+H 契约修复回写 DB，返回刷新后的 row。"""
    gid = int(row.get("id") or 0)
    mechanism = str(row.get("mechanism") or "").upper()
    structure_type = str(row.get("structure_type") or "").strip().upper()
    if gid <= 0 or mechanism != "M5" or structure_type != "H":
        return row

    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
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


def convert_gold_chat(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any]:
    """转换 + 落盘，返回摘要。"""
    row = _persist_m5_h_contract_if_needed(row)
    sid = str(row.get("source_id") or "").strip()
    chat = gold_story_to_gold_chat(row)
    chat, norm_notes = apply_gold_chat_normalizations(chat, row=row)
    chat = _refine_after_normalize(chat, row)
    chat, _ = _ensure_gold_chat_min_chars(chat)
    if norm_notes:
        logger.info(
            "gold_chat normalize %s: %s",
            sid,
            "；".join(norm_notes[:4]),
        )
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
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
    validate_gold_chat(
        chat,
        banned_literals=[str(x) for x in banned],
        source_type=source_type,
        mom_lines_max=int(mom_max),
    )
    mech = str(row.get("mechanism") or "").upper()
    st = str(row.get("structure_type") or "").strip().upper()
    if mech == "M5" and st == "H":
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
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
    chat = _attach_gold_chat_structure_score(chat, row)
    struct = _gate_gold_chat_structure_score(chat)
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
        "structure_score": struct,
        "quality": chat.get("quality"),
        "export": paths,
        "daily_story": chat,
    }

