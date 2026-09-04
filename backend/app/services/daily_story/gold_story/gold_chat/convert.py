"""gold_chat：金故事 → 日常对白（独立流程，不入 H0–H4 采集流水线）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.patch import (
    apply_m5_h_local_patches,
    patch_m5_break_sibling_consecutive,
    patch_remap_sibling_terms,
)
from app.services.daily_story.gold_story.gold_chat.prompts import (
    CHARS_SOFT_HI,
    CHARS_SOFT_LO,
    CHAT_MAX_LINE_CHARS,
    DIALOGUE_ROUNDS_HARD_MAX,
    DIALOGUE_ROUNDS_SOFT_HI,
    DIALOGUE_ROUNDS_SOFT_LO,
    _ALIGN_REFINE_SYSTEM,
    _ALIGN_REFINE_USER,
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
    format_m5_h_pass1_beat_block,
    format_pass1_regen_feedback,
    format_role_binding_block,
    format_seed_span_block,
    format_structure_score_feedback,
)
from app.services.daily_story.gold_story.gold_chat.type_bridge import (
    is_m8_j_domination,
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
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
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
    if patch:
        repo_gold_story.patch_story_payload(gid, patch)
    logger.info(
        "[GOLD_CHAT] structure auto_correct id=%s notes=%s",
        gid,
        "；".join(notes),
    )
    return repo_gold_story.get_story(gid) or row


# 2 候选够比选；4 会把短稿 FIX×重抽拖到数十分钟无反馈
PASS1_CANDIDATE_COUNT = 2
PASS1_REGENERATE_MAX = 5
PASS1_SHORT_REGENERATE_MAX = 3
PASS1_SHORT_LINE_DEFICIT_MAX = 3
PASS1_NEAR_MISS_CHAR_DEFICIT_MAX = 20
PASS1_LARGE_GAP_CHAR_DEFICIT_MIN = 60
# M8+J 大缺口阈值更激进：缺 ≥40 字立即中段重写，不走轻量 FIX
PASS1_LARGE_GAP_CHAR_DEFICIT_MIN_M8J = 40
PASS1_NEAR_MISS_FIX_MAX_ROUNDS = 2
PASS2_MAX_ROUNDS = 2
# 差 ≤60 字本地可读扩写/粒子收口（FIX 常停在 190–220）
GOLD_CHAT_NEAR_MISS_DEFICIT_MAX = 60
# 对白 JSON 正常约数百～1.5k tokens；再大视为跑飞
GOLD_CHAT_LLM_MAX_TOKENS = 2048
CLOSING_PROMPT_MAX_CHARS = 28
_RE_PAD_SUFFIX_STACK = re.compile(
    r"(?:不行吧|真的啊|你听着|你听着了呀|真的呀真的|真的嘛了呀|嘛了呀){2,}|"
    r"(?:真的(?:呀|呢|吧|啊)?){2,}|"
    r"(?:不行(?:真的|了?[啊吧呀呢嘛])?){2,}|"
    r"(?:了[啊吧呀呢]){2,}|"
    r"不行真的不行|真的了啊|真的呀不行|了吧不行|了啊不行|"
    r"活该了呢|活该嘛呀|不行嘛呀|嘛不行嘛|真的呀不行|"
    r"嘛呀[！。？…!?]|了呢呀|了呢了呀|"
    r"呢呢|啊呢|吧呢|嘛呢|呀呢|你呀呢|行了吧呢|不懂你呢|听听不懂|你真是呢|你真是的呢|"
    r"了呀呢|好不好了呀|着呢了呀",
)
_B_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧", "真的呀")
_F_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧")
# K：禁「真的呀/好不好/嘛」多轮升级成嘛呀/真的呀真的
_K_GOLD_CHAT_PAD_TAILS = ("啊", "吧", "呀")


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
    logger.info(
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
    logger.info(
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
        ("嘛不行嘛呀", ""),
        ("嘛不行嘛", ""),
        ("真的呀不行嘛", "真的不行"),
        ("不行嘛呀", "不行"),
        ("活该嘛呀", "活该"),
        ("活该了呢", "活该"),
    ):
        if old in out:
            out = out.replace(old, new)
    out = re.sub(r"(?:真的(?:呀|呢|吧|啊)?){2,}", "真的", out)
    out = re.sub(r"(?:不行(?:真的|了?[啊吧呀呢嘛])?){2,}", "不行", out)
    out = re.sub(r"(?:了[啊吧呀呢]){2,}", "", out)
    for junk in (
        "不行真的不行",
        "真的了啊",
        "真的呀不行",
        "了吧不行",
        "了啊不行",
    ):
        out = out.replace(junk, "")
    out = re.sub(
        r"(?:不行吧|真的啊|你听着|你听着了呀|真的呀|嘛了呀){2,}([！。！？…]?)$",
        r"\1",
        out,
    )
    out = re.sub(r"嘛呀([！。？…!?])$", r"\1", out)
    out = re.sub(r"真的(?:呀|呢|吧)?([！。？…!?])$", r"\1", out)
    out = re.sub(r"不行嘛([！。？…!?])$", r"不行\1", out)
    out = re.sub(r"[，,]{2,}", "，", out).strip("，, ")
    if out and out[-1] not in "！。？…!?" and line[-1:] in "！。？…!?":
        out = out + line[-1]
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


def _strip_extra_natural_expands(line: str) -> str:
    """句内最多保留 1 条可读扩写尾巴；剥软灌尾。"""
    s = str(line or "").strip()
    if not s:
        return s
    punct = s[-1] if s[-1] in "！。？…!" else ""
    body = s[:-1] if punct else s
    for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
        body = body.replace(f"，{soft}", "").replace(soft, "")
    bare_all = [c.lstrip("，,") for c in _GOLD_CHAT_NATURAL_EXPAND]
    hits = [(body.find(b), b) for b in bare_all if b in body]
    for bare in bare_all:
        while body.count(bare) > 1:
            body = body.replace(bare, "", 1)
    hits = [(body.find(b), b) for b in bare_all if b in body]
    if len(hits) <= 1:
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        return (body + punct) if body else s
    hits.sort(key=lambda x: x[0])
    keep = hits[0][1]
    for _, bare in hits[1:]:
        body = body.replace(f"，{bare}", "").replace(bare, "")
    body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
    if not body:
        return s
    return body + (punct or "！")


def patch_sanitize_natural_expand_stack(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """每句最多 1 条 near-miss 扩写尾巴，防垫字感堆叠。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        new = _strip_extra_natural_expands(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_sanitize_pad_particles(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """剥句尾「了呀/了吧/了啊」与软灌尾（听见没有/这回听清楚）。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        cleaned = re.sub(r"([！。？])[呀啊吧]+([！。？])$", r"\1", old)
        if cleaned != old:
            item["line"] = cleaned
            changed = True
            old = cleaned
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = re.sub(r"了[呀吧啊]{2,}$", "了", body)
        new_body = re.sub(r"啊{2,}$", "啊", new_body)
        new_body = re.sub(r"吧{2,}", "吧", new_body)
        new_body = re.sub(r"吗吧+", "吗", new_body)
        new_body = re.sub(r"呀呀+", "呀", new_body)
        new_body = re.sub(r"来呀来呀", "来呀", new_body)
        new_body = re.sub(r"呀吧$", "呀", new_body)
        new_body = re.sub(r"吗啊+", "吗", new_body)
        new_body = re.sub(r"了[呀吧啊]$", "", new_body)
        new_body = re.sub(r"了呢呀$", "了呢", new_body)
        new_body = re.sub(r"了啊呀$", "了啊", new_body)
        for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
            new_body = new_body.replace(f"，{soft}", "").replace(soft, "")
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if new_body != body and new_body:
            item["line"] = new_body + (punct or "！")
            changed = True
    return out, changed


def patch_j_cap_ya_particles(
    story: dict[str, Any],
    *,
    max_lines: int = 2,
) -> tuple[dict[str, Any], bool]:
    """J：全篇句尾「呀」最多保留 max_lines 处，其余剥掉防满篇垫字。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    ya_indices: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if re.search(r"呀[！。？…!]?$", line) or re.search(
            r"[来好啦了]呀[！。？…!]?$", line
        ):
            ya_indices.append(i)
    if len(ya_indices) <= max_lines:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for i in ya_indices[max_lines:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = re.sub(r"来呀来呀", "来", body)
        new_body = re.sub(r"([来啦了])呀$", r"\1", new_body)
        new_body = re.sub(r"呀$", "", new_body)
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_cap_trailing_particles(
    story: dict[str, Any],
    *,
    particles: tuple[str, ...] = ("啊", "呀"),
    max_lines: int = 3,
) -> tuple[dict[str, Any], bool]:
    """J：全篇句尾语气词（啊/呀）最多保留 max_lines 处。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    pat = re.compile(
        rf"(?:{'|'.join(re.escape(p) for p in particles)})[！。？…!]?$"
    )
    hit_indices: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if pat.search(line):
            hit_indices.append(i)
    if len(hit_indices) <= max_lines:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for i in hit_indices[max_lines:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = body
        for p in particles:
            new_body = re.sub(rf"{re.escape(p)}$", "", new_body)
        new_body = re.sub(r"([了啦呢])啊$", r"\1", new_body)
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_dedupe_cross_line_phrases(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：全篇扩写短语（你凭什么等）只保留首现，防叠灌重复。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    seen: set[str] = set()
    changed = False
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = body
        for phr in _J_CROSS_LINE_DEDUPE_PHRASES:
            if phr not in new_body:
                continue
            if phr in seen:
                for variant in (f"，{phr}呀", f"，{phr}啊", f"，{phr}", phr):
                    new_body = new_body.replace(variant, "")
            else:
                seen.add(phr)
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if not new_body:
            continue
        new = new_body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_strip_all_natural_expands(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """终稿：剥尽 near-miss 可读扩写尾巴，改由粒子补字。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        for bare in sorted(
            [c.lstrip("，,") for c in _GOLD_CHAT_NATURAL_EXPAND],
            key=len,
            reverse=True,
        ):
            body = body.replace(f"，{bare}", "").replace(bare, "")
        for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
            body = body.replace(f"，{soft}", "").replace(soft, "")
        body = re.sub(r"了[呀吧啊]$", "", body)
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        if not body:
            continue
        new = body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_fix_strongest_form_wording(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：「最强形态」须昭昭自述挑衅，禁灿灿错位或「那你拿出」口吻。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "最强形态" not in line:
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp == "灿灿":
            item["speaker"] = "昭昭"
            item["line"] = "我拿出最强形态来，你可别怂！"
            changed = True
            continue
        if sp != "昭昭":
            continue
        if not re.search(r"那你|你拿|你出", line):
            continue
        item["line"] = "我拿出最强形态来，我可不会输！"
        changed = True
    return out, changed


def patch_j_fix_lose_speaker(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输句必须归昭昭（防连说改 speaker 后错位）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    lose_pat = re.compile(r"我输了|我认输了")
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        sp = str(item.get("speaker") or "").strip()
        if lose_pat.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
    return out, changed


def patch_j_dedupe_plea_rounds(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后最多保留 1 轮「再求/不行」；删第二轮机械求拒。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False

    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False

    plea_pat = re.compile(
        r"再求你|再给.{0,2}机会|换个理由.{0,4}求|那我保证|就这一次|姐姐，再给"
    )
    veto_pat = re.compile(
        r"不行|规矩|输了就是输了|别想反悔|休想耍赖|继续压住|赢了就是赢了"
    )
    plea_idx = [
        i
        for i, x in enumerate(dialogue)
        if i > lose_idx
        and isinstance(x, dict)
        and str(x.get("speaker") or "") == "昭昭"
        and plea_pat.search(str(x.get("line") or ""))
    ]
    if len(plea_idx) < 2:
        return story, False

    drop: set[int] = set()
    for second in plea_idx[1:]:
        drop.add(second)
        if second + 1 < len(dialogue):
            nxt = dialogue[second + 1]
            if (
                isinstance(nxt, dict)
                and str(nxt.get("speaker") or "") == "灿灿"
                and veto_pat.search(str(nxt.get("line") or ""))
            ):
                drop.add(second + 1)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


_C_SAFE_PAD_TAILS = ("啊", "吧")  # 单语气词；禁叠成了呢了呀
# 禁「现在/立刻/马上/快点」——near-miss 多轮会叠成句尾垃圾
_C_SAFE_PAD_PHRASES = (
    "真的",
    "不行",
)
# 句数不足时中段插抽象反应（不写死主题物件，保 speaker 交替）
_GOLD_CHAT_REACT_LINES: tuple[tuple[str, str], ...] = (
    ("昭昭", "你少来这套！"),
    ("灿灿", "少废话听我的！"),
    ("昭昭", "我就不服！"),
    ("灿灿", "你再闹试试！"),
    ("昭昭", "凭什么听你的！"),
    ("灿灿", "我说怎样就怎样！"),
)
# 已停用灌尾巴（毁可读性）；保留常量供机审/剥除识别
_GOLD_CHAT_LINE_EXPAND: tuple[str, ...] = (
    "，你给我听好了",
    "，这回算清楚",
    "，别再装傻",
    "，我可记住了",
    "，说了就不改",
    "，再闹我可恼了",
)
_GOLD_CHAT_EXPAND_CLUTTER: tuple[str, ...] = tuple(
    c.lstrip("，,") for c in _GOLD_CHAT_LINE_EXPAND
) + (
    "少废话听我的",
    "你少来这套",
    "我就不服",
    "你再闹试试",
    "凭什么听你的",
    "我说怎样就怎样",
)
# 可读中段加句（FIX 停滞时插；J：昭求/灿否成对，禁角色对调）
_GOLD_CHAT_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "再求你一次，这回你就松口吧！"),
        ("灿灿", "不行，规矩就是这样定的！"),
    ),
    (
        ("昭昭", "那我保证，这次一定听你的！"),
        ("灿灿", "保证也没用，现在先听我的！"),
    ),
    (
        ("昭昭", "就这一次，下次再听你安排！"),
        ("灿灿", "少讨价还价，这回听我安排！"),
    ),
)
_M8_J_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "我才不服，再来一回合！"),
        ("灿灿", "来啊，看谁先认输！"),
    ),
    (
        ("昭昭", "你别得意，我还没发力呢！"),
        ("灿灿", "行了，谁赢谁说了算，别磨蹭！"),
    ),
    (
        ("昭昭", "你真敢跟我动手啊？"),
        ("灿灿", "规矩先讲好，输了别赖账！"),
    ),
)
# K：互顶升级/僵持向，禁套 J 求否；「越劝」须对劝架大人，勿对弟妹说
_K_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "你再拧耳朵试试！"),
        ("灿灿", "试试就试试，来啊！"),
    ),
    (
        ("昭昭", "你拧疼我了！松开！"),
        ("灿灿", "疼也得挨打！"),
    ),
    (
        ("昭昭", "哼，有你好看！"),
        ("灿灿", "谁怕你记仇！"),
    ),
    (
        ("昭昭", "我咬定了不松口！"),
        ("灿灿", "松不松都要打！"),
    ),
    (
        ("昭昭", "你还打！我不怕你！"),
        ("灿灿", "再闹我就更凶！"),
    ),
    (
        ("昭昭", "你给我等着瞧！"),
        ("灿灿", "等着瞧就等着瞧！"),
    ),
)
# K near-miss 可读扩写：按说话人分流，禁串角/禁粘护手句
_K_ZHAO_NATURAL_EXPAND: tuple[str, ...] = (
    "，我才不怕呢",
    "，你试试看啊",
)
_K_CAN_NATURAL_EXPAND: tuple[str, ...] = (
    "，再闹我恼了",
    "，轮不到你",
)
_K_GOLD_CHAT_NATURAL_EXPAND: tuple[str, ...] = (
    _K_ZHAO_NATURAL_EXPAND + _K_CAN_NATURAL_EXPAND
)
_RE_K_NO_EXPAND_LINE = re.compile(r"弄疼我手|打归打|手疼|护手")
# 可读句内扩写：禁「这回听清楚/听见没有」——审稿视同灌尾
_GOLD_CHAT_NATURAL_EXPAND: tuple[str, ...] = (
    "，我偏就不信",
    "，你试试看啊",
    "，我才不怕呢",
    "，少跟我吵啊",
    "，马上给我挪开",
    "，不许再耍赖了",
    "，别再乱动了",
    "，我可记住啦",
    "，说一不二",
    "，再闹我恼了",
    "，给我站住",
    "，轮不到你",
    "，我先说定",
)
# J 扩写尾巴 speaker 禁忌（防权威/挑衅语气错位）
_J_ZHAO_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {
        "少跟我吵",
        "轮不到你",
        "不许再耍赖",
        "马上给我挪开",
        "给我站住",
        "我先说定",
        "说一不二",
    }
)
_J_CAN_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {"你试试看", "少跟我吵", "我才不怕", "你凭什么"}
)
_GOLD_CHAT_EXPAND_SOFT_CLUTTER: tuple[str, ...] = (
    "听见没有呀",
    "这回听清楚",
    "听见没有",
    "这回听清楚",
    "你听着了呀",
    "你听着呀",
    "你听着",
)
_J_CROSS_LINE_DEDUPE_PHRASES: tuple[str, ...] = (
    "你凭什么",
    "你试试看",
    "少跟我吵",
    "我才不怕",
)
_J_YA_CAP_MAX_LINES = 2
_RE_C_TONE_STACK = re.compile(
    r"(?:[呢嘛的了着好]{2,}呀|呢了|呢呀)[！。！？…]?$"
)


def _strip_c_tone_stack_line(line: str) -> str:
    """C 类硬卡：句尾语气词堆砌 → 剥成无叠尾。"""
    s = str(line or "").strip()
    if not s or not _RE_C_TONE_STACK.search(s):
        return s
    punct = s[-1] if s[-1] in "！。？…!" else ""
    body = s[:-1] if punct else s
    body = re.sub(r"[呢嘛呀啊吧了着的好]+$", "", body)
    return (body + punct) if body else s


def patch_sanitize_c_tone_stack(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """剥 C 类句尾叠语气词（垫字副作用）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "C":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        new = _strip_c_tone_stack_line(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_c_force_sibling_alternate(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """C：全篇姐弟严格交替（含末四拍）。日常 try_local_patch 会保护末 4 句。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "C":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return story, False
    changed = False
    for i in range(1, len(dialogue)):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa in {"昭昭", "灿灿"} and sa == sb:
            b["speaker"] = "灿灿" if sa == "昭昭" else "昭昭"
            changed = True
    return out, changed


def patch_seed_speaker_align(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """seed 专属短语出现在错 speaker 时，改回 seed 标注角色（抽象，不写死单篇）。"""
    import copy

    from app.services.daily_story.gold_story.gold_chat.validate import (
        _seed_unique_phrase_owners,
    )

    owners = _seed_unique_phrase_owners(dialogue_seed)
    if not owners:
        return story, False

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
        if not line or sp not in {"昭昭", "灿灿", "妈妈"}:
            continue
        line_han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
        for phr, want in owners.items():
            if phr not in line and phr not in line_han:
                continue
            if sp == want:
                break
            item["speaker"] = want
            changed = True
            break
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


def patch_j_plea_veto_speakers(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：本地加的求放行/否决句若被连说翻转，按句式归位（抽象模板，非单篇）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    plea = re.compile(r"再求你一次|那我保证|就这一次|再给一次机会")
    veto = re.compile(r"规矩就是这样|保证也没用|少讨价还价|这回听我安排")
    toy = re.compile(r"玩具.{0,6}归我|归我.{0,4}玩具")
    grow = re.compile(r"长大.{0,8}算")
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        sp = str(item.get("speaker") or "").strip()
        if plea.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
        elif veto.search(line) and sp != "灿灿":
            item["speaker"] = "灿灿"
            changed = True
        elif toy.search(line) and sp != "灿灿":
            item["speaker"] = "灿灿"
            changed = True
        elif grow.search(line) and sp != "昭昭":
            item["speaker"] = "昭昭"
            changed = True
        # seed 扩句 intent 泄漏进对白：改成口语
        if re.match(r"^换个理由再求", line):
            item["line"] = "再求你一次，刚才那下不算！"
            item["speaker"] = "昭昭"
            changed = True
        elif re.match(r"^换个说法继续压", line):
            item["line"] = "不行，输了就是输了！"
            item["speaker"] = "灿灿"
            changed = True
        elif re.match(r"^再保证一次", line):
            item["line"] = "我保证，这次听你的！"
            item["speaker"] = "昭昭"
            changed = True
        elif re.match(r"^再否决一次", line):
            item["line"] = "不行，我说了算！"
            item["speaker"] = "灿灿"
            changed = True
    return out, changed


def patch_break_consecutive_keep_seed(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
    bridge_cap: int = 2,
) -> tuple[dict[str, Any], bool]:
    """打散同人连说：只插对方短接话，不改已有句 speaker（保 seed/求否方向）。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MAX

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return story, False

    changed = False
    i = 1
    guard = 0
    while i < len(dialogue) and guard < 12:
        guard += 1
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in {"昭昭", "灿灿"} or sa != sb:
            i += 1
            continue
        if len(dialogue) >= CHAT_LINE_COUNT_MAX:
            break
        other = "灿灿" if sa == "昭昭" else "昭昭"
        bridges = (
            "等等，先听我说完！",
            "你别插嘴，轮到我了！",
            "先别吵，听清楚！",
        )
        used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
        bridge_n = sum(1 for br in bridges if br in used)
        if bridge_n >= bridge_cap:
            i += 1
            continue
        text = next((br for br in bridges if br not in used), None)
        if not text:
            i += 1
            continue
        dialogue.insert(i, {"speaker": other, "line": text})
        changed = True
        i += 2
    return out, changed


def patch_sanitize_bridge_lines(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """桥接句保持短句，勿叠 near-miss 扩写尾巴。"""
    import copy

    bridges = (
        "等等，先听我说完",
        "你别插嘴，轮到我了",
        "你别插嘴，轮到我",
        "先别吵，听清楚",
    )
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        for br in bridges:
            if br in line and line != f"{br}！":
                item["line"] = f"{br}！"
                changed = True
                break
    return out, changed


def patch_j_drop_post_lose_bridge(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：一锤分出胜负后删无意义桥句（别插嘴/轮到我），保收场节奏。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    bridges = (
        "等等，先听我说完",
        "你别插嘴，轮到我了",
        "你别插嘴，轮到我",
        "先别吵，听清楚",
    )
    drop: set[int] = set()
    for i in range(max(0, lose_idx - 2), lose_idx):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if any(br in line for br in bridges):
            drop.add(i)
    for i in range(lose_idx + 1, len(dialogue)):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if any(br in line for br in bridges):
            drop.add(i)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


def patch_j_drop_post_lose_plea(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后删求情-拒绝对，直进嘀咕+镇住（防审稿判拉锯）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    plea_pat = re.compile(
        r"再给.{0,2}机会|再.{0,2}给.{0,2}一次|再求你|换个理由.{0,4}求|"
        r"求一次|那我保证|姐姐，再|还没准备好|我保证不闹"
    )
    veto_pat = re.compile(
        r"不行|规矩|输了就是输了|别想反悔|休想耍赖|继续压住|赢了就是赢了|换个说法"
    )
    drop: set[int] = set()
    for i in range(lose_idx + 1, len(dialogue)):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        line = str(item.get("line") or "")
        if not plea_pat.search(line):
            continue
        drop.add(i)
        if i + 1 < len(dialogue):
            nxt = dialogue[i + 1]
            if (
                isinstance(nxt, dict)
                and str(nxt.get("speaker") or "") == "灿灿"
                and veto_pat.search(str(nxt.get("line") or ""))
            ):
                drop.add(i + 1)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


def _j_lose_line_index(dialogue: list[Any]) -> int:
    for i, x in enumerate(dialogue):
        if not isinstance(x, dict):
            continue
        if (
            str(x.get("speaker") or "").strip() == "昭昭"
            and re.search(r"我输了|认输", str(x.get("line") or ""))
        ):
            return i
    return -1


_RE_J_POST_LOSE_REMATCH = re.compile(
    r"不服|再来一回合|我还没用全力|看谁先认输|别磨蹭|"
    r"我还没发力|奉陪到底|你记住了|你真敢",
)
_RE_J_POST_LOSE_KEEP = re.compile(r"长大.{0,8}算|都归我|玩具都归")


def patch_j_drop_post_lose_rematch(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J/M8+J：认输后删本地互顶加码句，保收场节奏。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = _j_lose_line_index(dialogue)
    if lose_idx < 0:
        return story, False
    tail_guard = set(range(max(lose_idx + 1, len(dialogue) - 2), len(dialogue)))
    drop: set[int] = set()
    for i in range(lose_idx + 1, len(dialogue)):
        if i in tail_guard:
            continue
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if _RE_J_POST_LOSE_KEEP.search(line):
            continue
        if _RE_J_POST_LOSE_REMATCH.search(line):
            drop.add(i)
    if not drop:
        return story, False
    out["dialogue"] = [x for i, x in enumerate(dialogue) if i not in drop]
    return out, True


def _gold_chat_j_pre_score_polish(
    chat: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None,
    mechanism: str = "",
) -> dict[str, Any]:
    """结构分门控前：J 删认输后拉锯、打散连说、归位 seed。"""
    from app.services.daily_story.gold_story.gold_chat.patch import (
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


def _j_expand_bare_allowed(bare: str, speaker: str) -> bool:
    """near-miss 扩写按 speaker 过滤，防权威/挑衅错位。"""
    sp = str(speaker or "").strip()
    b = str(bare or "").strip()
    if not b:
        return False
    if sp == "昭昭" and any(x in b or b in x for x in _J_ZHAO_FORBIDDEN_EXPAND):
        return False
    if sp == "灿灿" and any(x in b or b in x for x in _J_CAN_FORBIDDEN_EXPAND):
        return False
    return True


def patch_j_strip_role_mismatch_expands(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：剥 speaker 禁忌扩写尾巴（如昭昭说「少跟我吵」）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        forbidden = (
            _J_ZHAO_FORBIDDEN_EXPAND
            if sp == "昭昭"
            else (_J_CAN_FORBIDDEN_EXPAND if sp == "灿灿" else frozenset())
        )
        for bare in sorted(forbidden, key=len, reverse=True):
            for suffix in ("", "啊", "呀", "吧"):
                token = bare + suffix
                body = body.replace(f"，{token}", "").replace(token, "")
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        if not body:
            continue
        new = body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_ensure_post_lose_alternate(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后若连说，插灿灿短否决，保交替与收场节奏。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 1 >= len(dialogue):
        return story, False
    nxt = dialogue[lose_idx + 1]
    if not isinstance(nxt, dict) or str(nxt.get("speaker") or "") != "昭昭":
        return story, False
    nxt_line = str(nxt.get("line") or "")
    if re.search(r"长大.{0,8}算", nxt_line):
        return story, False
    if re.search(
        r"再给|再求|换个理由.{0,4}求|求一次|那我保证|还没准备好",
        nxt_line,
    ):
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "你少废话，输了就是输了！",
        "别讨价还价，规矩定了！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 1, {"speaker": "灿灿", "line": text})
    return out, True


def patch_j_ensure_post_lose_can_press(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：删求拒后若认输直跳嘀咕，补灿灿短镇住句。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 1 >= len(dialogue):
        return story, False
    nxt = dialogue[lose_idx + 1]
    if not isinstance(nxt, dict):
        return story, False
    if str(nxt.get("speaker") or "") != "昭昭":
        return story, False
    if not re.search(r"长大.{0,8}算", str(nxt.get("line") or "")):
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "你少废话，输了就是输了！",
        "别讨价还价，这局我说了算！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 1, {"speaker": "灿灿", "line": text})
    return out, True


_RE_C_WEAK_CRITERION_REWRITE = (
    (re.compile(r"我先(?:碰|摸|搭|够|伸|探|吃|喝|咬|舔|尝)(?:到|着|了|的|完|光)?"), "我先拿到的"),
    (re.compile(r"谁先(?:碰|摸|搭|够|伸|探|吃|喝|咬|舔|尝)(?:到|着|了|完|光)?"), "谁先拿到"),
    (
        re.compile(
            r"(?:碰|摸|搭|够)(?:到|着|了|的|一下)?(?=[^。！？]{0,8}(?:该|归|算|赢|谁))"
        ),
        "拿到",
    ),
    (
        re.compile(
            r"(?:吃|喝|咬|舔|吞|尝|擦)(?:到|着|了|一下|完|光)?"
            r"(?=[^。！？]{0,6}(?:该|归|算|赢|谁))"
        ),
        "拿到",
    ),
    (
        re.compile(
            r"(?:拧|撕|掰|揭)(?:开|掉|下来|完)?(?=[^。！？]{0,8}(?:该|归|算|赢|谁))"
        ),
        "拿到",
    ),
)


def patch_c_possession_criterion(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """C：弱接触/消耗系判据翻成占有系（拿到），避免判据漂移硬卡。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "C":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "")
        new = old
        for pat, repl in _RE_C_WEAK_CRITERION_REWRITE:
            new2 = pat.sub(repl, new)
            if new2 != new:
                new = new2
                changed = True
        if new != old:
            item["line"] = new
    return out, changed


def _pad_gold_chat_line(
    line: str,
    need: int,
    *,
    used: set[str] | None = None,
    story_type: str = "",
    speaker: str = "",
) -> tuple[str, int]:
    """near-miss 本地垫字：走日常故事同一套句尾垫字。"""
    from app.services.daily_story.prompts import _pad_dialogue_line

    st = str(story_type or "").strip().upper()
    if st == "C":
        s = str(line or "").strip()
        if need <= 0:
            return s, 0
        from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX

        core = s.rstrip("！。？…!")
        punct = s[len(core) :]
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - len(s))
        if room <= 0:
            return s, 0
        if not re.search(r"[呢嘛呀啊吧了]$", core):
            for tail in _C_SAFE_PAD_TAILS:
                if used is not None and tail in used:
                    continue
                if len(tail) > need or len(tail) > room:
                    continue
                if used is not None:
                    used.add(tail)
                return core + tail + punct, len(tail)
        for phr in _C_SAFE_PAD_PHRASES:
            if used is not None and phr in used:
                continue
            if core.endswith(phr):
                continue
            if len(phr) > need or len(phr) > room:
                continue
            if used is not None:
                used.add(phr)
            return core + phr + punct, len(phr)
        return s, 0
    if st == "J":
        line_out, added = _pad_dialogue_line(
            line, need, used, tails=("啊", "吧")
        )
        if added > 0:
            return line_out, added
        return line, 0
    if st == "B":
        tails = _B_GOLD_CHAT_PAD_TAILS
    elif st == "F":
        tails = _F_GOLD_CHAT_PAD_TAILS
    elif st == "K":
        # K：只在句尾无语气词时补一个呀/啊/吧；禁止 particle_upgrade 叠成了呀
        from app.services.daily_story.dialogue_text import (
            DAILY_STORY_LINE_CHARS_MAX,
            dialogue_char_count,
        )

        text = str(line or "").strip()
        if need <= 0 or not text or _RE_K_NO_EXPAND_LINE.search(text):
            return line, 0
        trail = ""
        core = text
        if core[-1] in "。！？…":
            trail = core[-1]
            core = core[:-1]
        if not core or re.search(r"[呢嘛呀啊吧了呗]$", core):
            return line, 0
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(text))
        for tail in _K_GOLD_CHAT_PAD_TAILS:
            if used is not None and tail in used:
                continue
            if len(tail) > need or len(tail) > room:
                continue
            if used is not None:
                used.add(tail)
            return f"{core}{tail}{trail}", len(tail)
        return line, 0
    else:
        tails = None
    line_out, added = _pad_dialogue_line(line, need, used, tails=tails)
    if added > 0:
        return line_out, added
    if need <= 0:
        return line, 0
    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
    )

    text = str(line or "").strip()
    if not text:
        return line, 0
    trail = ""
    core = text
    if core[-1] in "。！？…":
        trail = core[-1]
        core = core[:-1]
    room = max(0, DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(text))
    for phr in _C_SAFE_PAD_PHRASES:
        if used is not None and phr in used:
            continue
        if core.endswith(phr):
            continue
        if len(phr) > room or len(phr) > need:
            continue
        if used is not None:
            used.add(phr)
        return f"{core}{phr}{trail}", len(phr)
    return line, 0


def _gold_chat_pad_indices(
    dialogue: list[Any],
    *,
    story_type: str,
) -> list[int]:
    """可垫字行号；I 类排除收束段（首次语塞到结尾）与末 2 句。"""
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
        RE_SPEECHLESS,
        RE_WIN_STUBBORN,
    )

    lines = [
        str(item.get("line") or "")
        for item in dialogue
        if isinstance(item, dict)
    ]
    protected: set[int] = set()
    for i, ln in enumerate(lines):
        if RE_SPEECHLESS.search(ln):
            protected.update(range(i, len(dialogue)))
            break
    for i, item in enumerate(dialogue):
        if isinstance(item, dict) and RE_WIN_STUBBORN.search(
            str(item.get("line") or "")
        ):
            protected.add(i)
    if len(dialogue) > 2:
        protected.add(len(dialogue) - 1)
        protected.add(len(dialogue) - 2)
    kept = [i for i in indices if i not in protected]
    return kept or indices


def _patch_gold_chat_near_miss_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """240 hard 不变；差 ≤NEAR_MISS 字时本地垫字收口。"""
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
    natural_bares = {c.lstrip("，,") for c in _GOLD_CHAT_NATURAL_EXPAND}
    for idx in reversed(indices):
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        # 已有可读扩写尾巴的句子勿再叠粒子垫字
        if any(b in line for b in natural_bares):
            continue
        new_line, added = _pad_gold_chat_line(
            line,
            need,
            used=used_pads,
            story_type=story_type,
            speaker=str(item.get("speaker") or ""),
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
    particle_only: bool = False,
    max_rounds: int | None = None,
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
    used_pads: set[str] | None = None if particle_only else set()
    story_type = str(story.get("story_type") or "").strip().upper()
    # K：粒子叠垫必脏，改走可读尾巴/中段句
    if story_type == "K" and particle_only:
        particle_only = False
        used_pads = set()
    expand_src = (
        _K_GOLD_CHAT_NATURAL_EXPAND if story_type == "K" else _GOLD_CHAT_NATURAL_EXPAND
    )
    natural_bares = {c.lstrip("，,") for c in expand_src}
    pad_rounds = (
        max_rounds
        if max_rounds is not None
        else (48 if particle_only else (24 if need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX else 12))
    )
    # 多轮垫字：单轮每句最多补一尾巴，循环直到满或停步
    for _ in range(pad_rounds):
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
            if (not particle_only) and any(b in line for b in natural_bares):
                continue
            new_line, added = _pad_gold_chat_line(
                line,
                need,
                used=used_pads,
                story_type=story_type,
                speaker=str(item.get("speaker") or ""),
            )
            if added <= 0:
                continue
            item["line"] = new_line
            changed = True
            progressed = True
        if not progressed:
            # 垫词用尽时清空复用，优先把 near-miss 垫满
            if used_pads is not None and used_pads:
                used_pads.clear()
                continue
            break
    return out, changed


def _ensure_gold_chat_min_lines(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """已停用脏反应句灌句；改走 `_boost_short_with_mid_lines` 可读中段加句。"""
    return story, False


def _boost_short_with_mid_lines(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], bool]:
    """FIX/Pass1 写不满时：收束前插入成对句，保 J 权威方向。

    M8+J 插互顶/立规对；M5+J 等插昭求/灿否对。
    大缺口（>near_miss）时允许句数 <12 先插对补句数/字数。
    """
    import copy

    from app.services.daily_story.gold_story.scene import (
        CHAT_LINE_COUNT_MAX,
        CHAT_LINE_COUNT_MIN,
    )
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    if need <= 0:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False

    st = str(structure_type or story.get("story_type") or "").strip().upper()
    # K：顶满 24 句时仍可能差字，允许至 26 以便插实义中段对
    line_cap = CHAT_LINE_COUNT_MAX + (2 if st == "K" else 0)
    m8_j = is_m8_j_domination(mechanism=mechanism, structure_type=st)
    large_gap = need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    if total < 100 and not large_gap:
        return story, False
    if len(dialogue) < CHAT_LINE_COUNT_MIN and not large_gap:
        return story, False

    existing = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    blob = "".join(existing)
    if m8_j:
        if _j_lose_line_index(dialogue) >= 0:
            return story, False
        if len(dialogue) >= CHAT_LINE_COUNT_MIN:
            return story, False
    elif st == "J" and ("再求你一次" in blob or "那我保证" in blob):
        # 已有求否加码，勿再插第二对
        return story, False
    # K：僵持词已在不挡大缺口补句；小缺口且已有僵持点则不再插
    insert_at = max(2, len(dialogue) - 2)
    if m8_j:
        ko_idx = next(
            (
                i
                for i, x in enumerate(dialogue)
                if isinstance(x, dict)
                and re.search(r"草莓熊|肘击", str(x.get("line") or ""))
            ),
            -1,
        )
        if ko_idx >= 2:
            insert_at = min(insert_at, ko_idx)
    prev = dialogue[insert_at - 1] if insert_at > 0 else None
    if isinstance(prev, dict) and str(prev.get("speaker") or "").strip() == "昭昭":
        insert_at = min(insert_at + 1, len(dialogue))
    if m8_j:
        pair_pool = _M8_J_NATURAL_MID_PAIRS
    elif st == "J":
        pair_pool = _GOLD_CHAT_NATURAL_MID_PAIRS
    elif st == "K":
        pair_pool = _K_NATURAL_MID_PAIRS
    else:
        pair_pool = tuple(
            (_GOLD_CHAT_REACT_LINES[i], _GOLD_CHAT_REACT_LINES[i + 1])
            for i in range(0, len(_GOLD_CHAT_REACT_LINES) - 1, 2)
        )
    changed = False
    pairs_used = 0
    max_pairs = 1 if m8_j else (2 if large_gap else 1)
    if st == "K":
        # 小缺口只插 1 对，避免后段空喊堆叠
        max_pairs = 2 if need >= 20 else 1

    def _norm_pad_line(text: str) -> str:
        return re.sub(r"[呀啊吧呢嘛了呗！？。!?，,\s]", "", str(text or ""))

    existing_norm = {_norm_pad_line(x) for x in existing if x}
    for pair in pair_pool:
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        if pairs_used >= max_pairs:
            break
        if len(dialogue) + 2 > line_cap:
            break
        lines_ok = True
        for _sp, line in pair:
            text = str(line).strip()
            if not text or text in existing or _norm_pad_line(text) in existing_norm:
                lines_ok = False
                break
        if not lines_ok:
            continue
        # 避免插出同角色连说（上一句说话人 == 对首句）
        first_sp = str(pair[0][0]).strip()
        while insert_at > 0 and insert_at <= len(dialogue):
            prev_item = dialogue[insert_at - 1]
            if not isinstance(prev_item, dict):
                break
            if str(prev_item.get("speaker") or "").strip() != first_sp:
                break
            if insert_at >= len(dialogue):
                break
            insert_at += 1
        if insert_at > 0 and insert_at <= len(dialogue):
            prev_item = dialogue[insert_at - 1]
            if (
                isinstance(prev_item, dict)
                and str(prev_item.get("speaker") or "").strip() == first_sp
            ):
                continue
        for speaker, line in pair:
            text = str(line).strip()
            dialogue.insert(insert_at, {"speaker": speaker, "line": text})
            existing.add(text)
            existing_norm.add(_norm_pad_line(text))
            insert_at += 1
        pairs_used += 1
        changed = True
    return out, changed


def _expand_short_gold_chat_lines(
    story: dict[str, Any],
    *,
    ignore_deficit_cap: bool = False,
) -> tuple[dict[str, Any], bool]:
    """句数已满、字数 near-miss 时，句内加可读实词尾巴（禁旧灌尾）。

    每句最多一条、优先不重复；大缺口仍交 Pass1/FIX，勿靠本地硬灌过关。
    """
    import copy

    from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    rows = [x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()]
    if len(rows) < CHAT_LINE_COUNT_MIN:
        return story, False

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    # 只接手 near-miss；大缺口交 FIX（temp↑）写满，勿本地叠灌
    if need <= 0 or ((not ignore_deficit_cap) and need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX):
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False

    changed = False
    expand_count: dict[int, int] = {}
    used: set[str] = set()
    st = str(story.get("story_type") or "").strip().upper()
    expand_src = (
        _K_GOLD_CHAT_NATURAL_EXPAND if st == "K" else _GOLD_CHAT_NATURAL_EXPAND
    )
    bare_all = {c.lstrip("，,") for c in expand_src}
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        hits = [b for b in bare_all if b in line]
        if hits:
            expand_count[i] = min(1, len(hits))
            used.update(hits)
    for _ in range(24):
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
        if need <= 0:
            break
        candidates = [
            (i, item)
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and expand_count.get(i, 0) < 1
            and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
            and 4 <= len(str(item.get("line") or "").strip()) < 20
            and i >= 2
            and i < len(dialogue) - 2  # 首尾句不垫尾巴，保开场/收场干净
            and not any(
                br in str(item.get("line") or "")
                for br in (
                    "等等，先听我说完",
                    "你别插嘴，轮到我了",
                    "你别插嘴，轮到我",
                    "先别吵，听清楚",
                )
            )
            and "我输了" not in str(item.get("line") or "")
            and not _RE_K_NO_EXPAND_LINE.search(str(item.get("line") or ""))
        ]
        if not candidates:
            break
        candidates.sort(key=lambda x: len(str(x[1].get("line") or "")))
        progressed = False
        for idx, item in candidates:
            need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
            if need <= 0:
                break
            line = str(item.get("line") or "").strip()
            core = line.rstrip("！。？…!")
            punct = line[len(core) :] or "！"
            room = max(0, DAILY_STORY_LINE_CHARS_MAX - len(line))
            if room < 5:
                expand_count[idx] = 1
                continue
            sp = str(item.get("speaker") or "").strip()
            if st == "K":
                if sp == "昭昭":
                    src = _K_ZHAO_NATURAL_EXPAND
                elif sp == "灿灿":
                    src = _K_CAN_NATURAL_EXPAND
                else:
                    expand_count[idx] = 1
                    continue
            else:
                src = expand_src
            pool = [
                c
                for c in src
                if c.lstrip("，,") not in used
                and c.lstrip("，,") not in "".join(
                    str(x.get("line") or "")
                    for x in dialogue
                    if isinstance(x, dict)
                )
                and _j_expand_bare_allowed(
                    c.lstrip("，,"),
                    sp,
                )
            ]
            if not pool:
                break
            for clause in pool:
                bare = clause.lstrip("，,")
                if bare in core:
                    continue
                if len(clause) > room or len(clause) > need + 2:
                    continue
                item["line"] = (core + clause + punct)[:DAILY_STORY_LINE_CHARS_MAX]
                used.add(bare)
                expand_count[idx] = expand_count.get(idx, 0) + 1
                changed = True
                progressed = True
                break
            if progressed:
                break
        if not progressed:
            break
    return out, changed


def _strip_expand_clutter_line(line: str) -> str:
    """剥句内扩写灌尾巴（可读性硬伤）。"""
    s = str(line or "").strip()
    if not s:
        return s
    punct = s[-1] if s[-1] in "！。？…!" else ""
    body = s[:-1] if punct else s
    for clause in _GOLD_CHAT_EXPAND_CLUTTER:
        body = body.replace(f"，{clause}", "").replace(clause, "")
    body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
    if not body:
        return s
    return body + (punct or "！")


def patch_sanitize_expand_clutter(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """剥扩写灌尾巴；字数跌破 min 交上层重生成，勿再灌回去。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old or not any(c in old for c in _GOLD_CHAT_EXPAND_CLUTTER):
            continue
        new = _strip_expand_clutter_line(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def _ensure_gold_chat_min_chars(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], bool]:
    """near-miss 垫到 hard min；大缺口先可读中段加句，再交 Pass1/FIX。

    剥旧灌尾 → 可读句内扩写 → 中段加句 → 粒子 near-miss（差 ≤60）。
    """
    data, clutter_changed = patch_sanitize_expand_clutter(story)
    data, changed_lines = _ensure_gold_chat_min_lines(data)
    data, changed_exp = _expand_short_gold_chat_lines(data)
    changed = clutter_changed or changed_lines or changed_exp
    # 仅大缺口才插求否对；near-miss 交给句内扩写/粒子，避免一锤后拉锯灌尾
    need_now = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    changed_mid = False
    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    if need_now > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data, changed_mid = _boost_short_with_mid_lines(
            data,
            mechanism=mech,
            structure_type=st,
        )
    changed = changed or changed_mid

    data2, changed_pad = _patch_gold_chat_near_miss_chars(data)
    data, changed = data2, changed or changed_pad

    # 中段加句后再试 near-miss 粒子；大缺口仍留给 FIX/重抽
    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    if 0 < need <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data3, changed3 = _pad_gold_chat_to_min_chars(data)
        data, changed = data3, changed or changed3

    # 只剥叠；near-miss 再垫粒子。禁止二次 expand（尾巴叠灌）
    for _ in range(4):
        data, san = patch_sanitize_c_tone_stack(data)
        data, san2 = patch_sanitize_pad_suffix(data)
        data, san3 = patch_sanitize_expand_clutter(data)
        data, san4 = patch_sanitize_pad_particles(data)
        changed = changed or san or san2 or san3 or san4
        if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
            data, san_stack = patch_sanitize_natural_expand_stack(data)
            data, san_part = patch_sanitize_pad_particles(data)
            changed = changed or san_stack or san_part
            return data, changed
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
        if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
            # 仍差很多时再试一次中段加句
            if need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
                data, mid2 = _boost_short_with_mid_lines(
                    data,
                    mechanism=mech,
                    structure_type=st,
                )
                changed = changed or mid2
                need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
                if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
                    break
            else:
                break
        before = dialogue_total_chars(data)
        data, pad_again = _pad_gold_chat_to_min_chars(data)
        changed = changed or pad_again
        if (not pad_again) or dialogue_total_chars(data) <= before:
            break
    data, san_stack = patch_sanitize_natural_expand_stack(data)
    data, san_part = patch_sanitize_pad_particles(data)
    changed = changed or san_stack or san_part
    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    if 0 < need <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data, pad_final = _pad_gold_chat_to_min_chars(data)
        changed = changed or pad_final
    return data, changed


def _post_align_j_closing_touchup(
    chat: dict[str, Any],
    *,
    structure_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """align 后只跑 J 末句镇住（勿全量 type pipeline，免把 H 连说改坏）。"""
    st = str(structure_type or chat.get("story_type") or "").strip().upper()
    if st != "J":
        return chat, []
    from app.services.daily_story.story_types.j.patch import patch_j_body

    out = dict(chat)
    out["story_type"] = "J"
    notes = patch_j_body(out)
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


def _gold_chat_insert_body_lines_for_min(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删句后 pad/expand 顶格时：中段插 1–2 条抽象反应句补 min（非求拒）。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MAX

    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(story)
    if need <= 0:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    existing = {
        str(x.get("line") or "").strip()
        for x in dialogue
        if isinstance(x, dict)
    }
    insert_at = min(max(3, len(dialogue) // 3), len(dialogue) - 3)
    changed = False
    inserted = 0
    for sp, line in _GOLD_CHAT_REACT_LINES:
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        if len(dialogue) >= CHAT_LINE_COUNT_MAX:
            break
        if inserted >= 2:
            break
        text = str(line).strip()
        if not text or text in existing:
            continue
        dialogue.insert(insert_at, {"speaker": sp, "line": text})
        existing.add(text)
        insert_at += 1
        inserted += 1
        changed = True
    if changed:
        out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
        out = out2
        changed = True
    return out, changed


def _gold_chat_force_min_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """终稿仍差 min 时：句内扩写 → 粒子/可读垫满 → 中段插反应句（禁插求否对）。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN

    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(story)
    if need <= 0:
        return story, False
    st = str(story.get("story_type") or "").strip().upper()
    if st == "K":
        out = copy.deepcopy(story)
        out["story_type"] = "K"
        changed = False
        for _ in range(6):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            # K 禁口头禅扩写垫字（会与去重打架）；只插中段对 + 单语气词
            out2, c1 = _boost_short_with_mid_lines(out, structure_type="K")
            out = out2
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            changed = changed or c1
            if dialogue_total_chars(out) <= before:
                out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=24)
                out = out2
                out, _ = patch_sanitize_pad_suffix(out)
                out, _ = patch_sanitize_pad_particles(out)
                changed = changed or cp
                if dialogue_total_chars(out) <= before:
                    break
        return out, changed
    dialogue = story.get("dialogue")
    if isinstance(dialogue, list) and len(dialogue) >= CHAT_LINE_COUNT_MIN + 2:
        out = copy.deepcopy(story)
        changed = False
        for _ in range(8):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            out2, cx = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
            out = out2
            out, _ = patch_sanitize_natural_expand_stack(out)
            out, _ = patch_j_dedupe_cross_line_phrases(out)
            out, _ = patch_j_strip_role_mismatch_expands(out)
            changed = changed or cx
            if dialogue_total_chars(out) <= before:
                out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
                out = out2
                out, _ = patch_sanitize_pad_particles(out)
                out, _ = patch_j_cap_ya_particles(out)
                changed = changed or cp
                if dialogue_total_chars(out) <= before:
                    break
        return out, changed
    out = copy.deepcopy(story)
    changed = False
    for _ in range(4):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        out2, c5 = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
        out = out2
        out, _ = patch_sanitize_natural_expand_stack(out)
        changed = changed or c5
    for _ in range(8):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(out)
        out2, c4 = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=24
        )
        out = out2
        out, _ = patch_sanitize_pad_particles(out)
        changed = changed or c4
        if dialogue_total_chars(out) <= before:
            out2, c6 = _pad_gold_chat_to_min_chars(
                out, particle_only=False, max_rounds=12
            )
            out = out2
            changed = changed or c6
            if dialogue_total_chars(out) <= before:
                break
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        for _ in range(4):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            out2, ci = _gold_chat_insert_body_lines_for_min(out)
            out = out2
            changed = changed or ci
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
            out = out2
            changed = changed or cp
            if dialogue_total_chars(out) <= before:
                break
    out, _ = patch_sanitize_natural_expand_stack(out)
    out, _ = patch_j_dedupe_cross_line_phrases(out)
    out, _ = patch_j_cap_trailing_particles(out, max_lines=3)
    out, _ = patch_sanitize_pad_particles(out)
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        out2, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=24
        )
        out = out2
        out, _ = patch_j_cap_trailing_particles(out, max_lines=3)
        changed = changed or cp
    return out, changed


def patch_j_strip_post_lose_defiant(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：认输后昭昭句剥「我才不怕/你试试看」等逆势尾巴，保怂态。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0:
        return story, False
    changed = False
    defiant_bits = (
        "，我才不怕呢",
        "，我才不怕",
        "我才不怕呢",
        "我才不怕",
        "，你试试看啊",
        "，你试试看",
        "你试试看",
        "，谁怕谁",
        "谁怕谁",
    )
    for item in dialogue[lose_idx + 1 :]:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        old = str(item.get("line") or "").strip()
        if not old or re.search(r"长大.{0,8}算", old):
            continue
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = body
        for bit in defiant_bits:
            new_body = new_body.replace(bit, "")
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if not new_body:
            continue
        new = new_body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_j_fix_can_closing_after_grumble(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：昭昭嘀咕长大算账后，灿灿末句禁「行啊我等着」接招，改镇住命令。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return story, False
    grumble_idx = next(
        (
            i
            for i in range(len(dialogue) - 1, -1, -1)
            if isinstance(dialogue[i], dict)
            and str(dialogue[i].get("speaker") or "") == "昭昭"
            and re.search(r"长大.{0,8}算", str(dialogue[i].get("line") or ""))
        ),
        -1,
    )
    if grumble_idx < 0 or grumble_idx + 1 >= len(dialogue):
        return story, False
    last = dialogue[-1]
    if not isinstance(last, dict) or str(last.get("speaker") or "") != "灿灿":
        return story, False
    old = str(last.get("line") or "").strip()
    if not re.search(r"行啊|我等着|等着.*算|算.*账", old):
        return story, False
    stubs = (
        "别废话，趴好了！我说了算！",
        "闭嘴，现在就得听我的！",
        "少顶嘴，乖乖趴好别动！",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    last["line"] = text
    return out, True


def patch_j_fix_post_lose_consecutive_can(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：删桥句后若灿灿连说，插昭昭短怂句保交替。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MAX

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    lose_idx = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "") == "昭昭"
            and "我输了" in str(x.get("line") or "")
        ),
        -1,
    )
    if lose_idx < 0 or lose_idx + 2 >= len(dialogue):
        return story, False
    a = dialogue[lose_idx + 1]
    b = dialogue[lose_idx + 2]
    if not isinstance(a, dict) or not isinstance(b, dict):
        return story, False
    if str(a.get("speaker") or "") != "灿灿" or str(b.get("speaker") or "") != "灿灿":
        return story, False
    if len(dialogue) >= CHAT_LINE_COUNT_MAX:
        return story, False
    stubs = (
        "姐，我知道了，别打了。",
        "好嘛，我听话还不行吗。",
        "哎呀，我服了，你说怎样就怎样。",
    )
    used = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    text = next((s for s in stubs if s not in used), stubs[0])
    dialogue.insert(lose_idx + 2, {"speaker": "昭昭", "line": text})
    return out, True


def patch_j_soften_closing_grumble(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """J：末段昭昭嘀咕去掉「你等着瞧」等强势尾缀，保怂态。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "J":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "") != "昭昭":
            continue
        old = str(item.get("line") or "").strip()
        if not re.search(r"长大.{0,8}算", old):
            continue
        punct = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if punct else old
        new_body = re.sub(r"[，,]?你等着瞧[！。]?$", "", body)
        new_body = re.sub(r"[，,]?你等着呀[！。]?$", "", new_body)
        new_body = re.sub(r"^哼[，,]", "那个，", new_body)
        new_body = re.sub(r"([。！？…!])?[啊呀]+([。！？…!])$", r"\2", new_body)
        if not new_body.startswith("那个"):
            new_body = "那个，" + new_body.lstrip("那个，")
        new_body = new_body.strip("，, ")
        if not new_body:
            continue
        new = new_body + (punct or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


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
    payload = cast(dict[str, Any], row.get("payload") or {})
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
            row=row,
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


def _apply_pass1_setting_normalize(
    chat: dict[str, Any],
    *,
    row: dict[str, Any] | None = None,
    scene_contract_location: str = "",
    activity_context: str = "",
    characters: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Pass1/Pass2 校验前：站外 setting → 允许地点表内锚点。"""
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
    data = _apply_pass1_setting_normalize(
        data,
        row=row,
        scene_contract_location=scene_contract_location,
        activity_context=ctx,
    )
    from app.services.daily_story.gold_story.scene import (
        patch_dialogue_narration_to_speech,
    )

    patch_dialogue_narration_to_speech(data)
    if st == "K":
        from app.services.daily_story.story_types.k.patch import patch_k_body

        data["story_type"] = "K"
        patch_k_body(data)
    data, _ = _ensure_gold_chat_min_chars(
        data,
        mechanism=mech,
        structure_type=st,
    )
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
    structure_type: str = "",
    mechanism: str = "",
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass1 硬校验 + 格式 fix，直至通过或耗尽 retry。"""
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or data.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    if st:
        data["story_type"] = st
    last_err = ""
    shorten_llm_used = False
    short_expand_rounds = 0
    for attempt in range(5):
        data = _apply_pass1_setting_normalize(data, row=row)
        from app.services.daily_story.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        patch_dialogue_narration_to_speech(data)
        if st == "K":
            from app.services.daily_story.story_types.k.patch import patch_k_body

            data["story_type"] = "K"
            patch_k_body(data)
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
            # 偏短：near_miss 轻量 FIX；大缺口 M8+J 中段重写；仍不足交外层 Pass1 重生成
            if _is_short_content_error(last_err):
                from app.services.daily_story.gold_story.gold_chat.type_bridge import (
                    is_m8_j_domination,
                )

                m8_j = is_m8_j_domination(mechanism=mech, structure_type=st)
                large_gap = m8_j and _is_large_gap_short_error(
                    last_err, mechanism=mech, structure_type=st
                )
                near_miss = _is_near_miss_short_error(last_err)
                max_fix = (
                    PASS1_NEAR_MISS_FIX_MAX_ROUNDS
                    if near_miss
                    else (2 if large_gap else 3)
                )
                if large_gap and short_expand_rounds == 0:
                    logger.info(
                        "[GOLD_CHAT] pass1 M8+J mid rewrite err=%s",
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
                    logger.info(
                        "[GOLD_CHAT] pass1 FIX short round=%s err=%s",
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


def _generate_pass1_candidate(
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
    return _validate_pass1_chat(
        data,
        banned_literals=banned_literals,
        source_type=source_type,
        mom_lines_max=mom_lines_max,
        structure_type=structure_type,
        mechanism=mechanism,
        row=row,
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
    return _chat_json(_ALIGN_REFINE_SYSTEM, user, max_tokens=1024)


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
    row: dict[str, Any] | None = None,
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
        if st == "K":
            from app.services.daily_story.story_types.k.patch import patch_k_body

            data = dict(data)
            data["story_type"] = "K"
            patch_k_body(data)
        from app.services.daily_story.gold_story.scene import (
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

        try:
            raw = _align_refine_with_llm(
                data,
                blocking + warn,
                align_block=align_block,
                banned_literals=banned,
                mom_lines_max=mom_max,
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
        from app.services.daily_story.story_types.k.patch import patch_k_body

        data = dict(data)
        data["story_type"] = "K"
        patch_k_body(data)
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
    """seed 条数 <12 时，在收束前插入抽象加码拍，迫使 Pass1 写满句数。

    只改 prompt 用 seed，不写回 DB；intent 抽象，不按单篇物件造句。
    """
    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN

    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
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
    if is_m8_j_domination(mechanism=mechanism, structure_type=st):
        extras: list[dict[str, str]] = [
            {"speaker": "昭昭", "intent": "不服继续顶撞/扭打升级"},
            {"speaker": "灿灿", "intent": "重申谁赢谁说了算"},
            {"speaker": "昭昭", "intent": "嘴硬应战要对方出招"},
            {"speaker": "灿灿", "intent": "一锤前放狠话或气势铺垫"},
        ]
    elif st == "J":
        extras: list[dict[str, str]] = [
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
            chat, type_notes = apply_type_body_pipeline(chat, structure_type=st)
            notes.extend(type_notes)
        from app.services.daily_story.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        notes.extend(patch_dialogue_narration_to_speech(chat))
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
    if char_def is not None and 0 < char_def <= PASS1_NEAR_MISS_CHAR_DEFICIT_MAX:
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
        threshold = PASS1_LARGE_GAP_CHAR_DEFICIT_MIN_M8J
    else:
        threshold = PASS1_LARGE_GAP_CHAR_DEFICIT_MIN
    
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
    """句数差 ≤3（如 9–11/12）可 Pass1 重生成。"""
    deficit = _line_count_deficit_from_error(msg)
    if deficit is None:
        return False
    return 1 <= deficit <= PASS1_SHORT_LINE_DEFICIT_MAX


def _is_regenerable_short_error(msg: str) -> bool:
    """句数差 ≤3，或仅字数不足（句数已够/未报句数）→ 可 Pass1 重生成。

    字数缺口大（如 117/240）也靠 FIX 扩写 + 重抽，勿立刻驳回。
    仅当句数差 >3（如 8/12）才视为不可靠重生成。
    """
    line_def = _line_count_deficit_from_error(msg)
    if line_def is not None and line_def > PASS1_SHORT_LINE_DEFICIT_MAX:
        return False
    if line_def is not None and line_def >= 1:
        return True
    char_def = _char_deficit_from_error(msg)
    return char_def is not None and char_def > 0


def _short_content_reject_message(detail: str, *, regen_count: int = 0) -> str:
    text = str(detail or "").strip()
    if regen_count > 0:
        head = f"gold_chat篇幅驳回:重生成{regen_count}次仍不达标"
    else:
        head = "gold_chat篇幅驳回:本地垫字仍不足"
    return f"{head}; {text}" if text else head


def _bump_short_regen_or_reject(msg: str, short_regen_count: int) -> int:
    """句/字 near-miss → Pass1 重生成（最多 3 次）；差距更大或次数用尽 → 驳回。"""
    if not _is_short_content_error(msg):
        return short_regen_count
    if not _is_regenerable_short_error(msg):
        raise ValueError(
            _short_content_reject_message(msg, regen_count=short_regen_count)
        )
    next_count = short_regen_count + 1
    if next_count > PASS1_SHORT_REGENERATE_MAX:
        raise ValueError(
            _short_content_reject_message(msg, regen_count=PASS1_SHORT_REGENERATE_MAX)
        )
    return next_count


def _structure_type_hint(structure_type: str, mechanism: str = "") -> str:
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        structure_type_hint,
    )

    return structure_type_hint(structure_type=structure_type, mechanism=mechanism)


def gold_story_to_gold_chat(row: dict[str, Any]) -> dict[str, Any]:
    """单条 gold_story 行 → daily_story 形 JSON。"""
    row = _repair_i_row_contract(row)
    row, _structure_notes = _resolve_structure_row(row)
    payload = cast(dict[str, Any], row.get("payload") or {})
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
    if isinstance(seed, list):
        from app.services.daily_story.gold_story.scene import (
            sanitize_dialogue_seed_speech,
        )

        seed = sanitize_dialogue_seed_speech(seed)
    if structure_type == "K" and isinstance(seed, list):
        from app.services.daily_story.story_types.k.patch import (
            sanitize_k_dialogue_seed,
        )

        seed = sanitize_k_dialogue_seed(seed)
    banned = sanitize_banned_literals(
        payload.get("banned_literals") or scene_contract.get("banned_literals"),
        scene_contract=scene_contract,
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
    )
    source_type = str(payload.get("source_type") or scene_contract.get("source_type") or "field")
    story_raw_full = str(row.get("story_raw") or payload.get("story_raw") or "")
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
    pass1_temperature = 0.4
    chat: dict[str, Any] = {}
    short_regen_count = 0
    for _regen in range(PASS1_REGENERATE_MAX):
        logger.info(
            "[GOLD_CHAT] pass1 regen=%s/%s temp=%.2f short_regen=%s feedback=%s",
            _regen + 1,
            PASS1_REGENERATE_MAX,
            pass1_temperature,
            short_regen_count,
            "yes" if pass1_feedback_block else "no",
        )
        # 截断回灌后压低 story_raw，减少「照着长叙述扩写跑飞」
        story_raw_cap = 400 if pass1_temperature < 0.35 else 800
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
            pass1_feedback_block=pass1_feedback_block,
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
            structure_hint=_structure_type_hint(structure_type, mechanism),
            align_block=align_block,
            gold_chat_snippet=resolve_gold_chat_snippet(str(row.get("source_id") or "")),
            **_prompt_budget_kwargs(),
        )
        candidates: list[dict[str, Any]] = []
        hit_truncation = False
        hit_short = False
        for _cand_i in range(PASS1_CANDIDATE_COUNT):
            logger.info(
                "[GOLD_CHAT] pass1 candidate %s/%s …",
                _cand_i + 1,
                PASS1_CANDIDATE_COUNT,
            )
            try:
                candidates.append(
                    _generate_pass1_candidate(
                        user,
                        banned_literals=banned_list,
                        source_type=source_type,
                        mom_lines_max=mom_int,
                        structure_type=structure_type,
                        mechanism=mechanism,
                        temperature=pass1_temperature,
                        row=row,
                    )
                )
            except ValueError as exc:
                last_err = str(exc)
                logger.info(
                    "[GOLD_CHAT] pass1 candidate fail: %s",
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
                    pass1_temperature = max(pass1_temperature, 0.55)
                pass1_feedback_block = format_pass1_regen_feedback(
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
                    pass1_temperature = 0.25
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
        # 类型本地补丁先于 Pass2 align，避免 C 回旋镖等只能靠 LLM 精修
        from app.services.daily_story.gold_story.gold_chat.type_bridge import (
            apply_type_body_pipeline,
        )

        data, type_notes = apply_type_body_pipeline(
            data, structure_type=structure_type
        )
        from app.services.daily_story.gold_story.scene import (
            patch_dialogue_narration_to_speech,
        )

        narr_notes = patch_dialogue_narration_to_speech(data)
        if narr_notes:
            type_notes = list(type_notes) + narr_notes
        data, alt_changed = patch_c_force_sibling_alternate(data)
        if alt_changed:
            type_notes = list(type_notes) + ["C全篇交替"]
        data, crit_changed = patch_c_possession_criterion(data)
        if crit_changed:
            type_notes = list(type_notes) + ["C判据→占有系"]
        data, seed_changed = patch_seed_speaker_align(data, dialogue_seed=seed)
        if seed_changed:
            type_notes = list(type_notes) + ["seed角色归位"]
        data, _ = patch_sanitize_c_tone_stack(data)
        data, _ = patch_sanitize_pad_suffix(data)
        data, _ = _ensure_gold_chat_min_chars(
            data,
            mechanism=mechanism,
            structure_type=structure_type,
        )
        # 连说/垫字后再归位一次，避免补丁把专属短语翻错
        data, seed_changed2 = patch_seed_speaker_align(data, dialogue_seed=seed)
        if seed_changed2:
            type_notes = list(type_notes) + ["seed角色再归位"]
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
        chat = data
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
            # 结构分门控前先跑 M2+C 回旋镖/触发词补丁（否则 40 分空转）
            from app.services.daily_story.gold_story.gold_chat.patch import (
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
                # 已过 align 的稿：先定点抬结构，避免整开 Pass1 空转
                try:
                    fb = format_structure_score_feedback(last_err, chat)
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
                pass1_feedback_block = format_pass1_regen_feedback(
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
            # Pass2/校验路径截断也回灌 Pass1，勿直接打死整次 convert
            if _is_truncation_error(last_err):
                last_err = f"align_refine_failed:LLM截断:{last_err}"
                pass1_temperature = 0.25
            elif _is_short_content_error(last_err):
                short_regen_count = _bump_short_regen_or_reject(
                    last_err, short_regen_count
                )
                pass1_temperature = max(pass1_temperature, 0.55)
            elif not last_err.startswith(
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
                short_regen_count=short_regen_count,
            )
    # 零食+作业本战：LLM 截断/结构分翻车时用 beat 重建兜底（禁再烧 flash）
    if str(structure_type or "").upper() == "C" and str(mechanism or "").upper() == "M2":
        from app.services.daily_story.gold_story.gold_chat.patch import (
            _m2_c_is_snack_homework_ctx,
            m2_c_meat_whole_item_context,
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


def convert_gold_chat(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any]:
    """转换 + 落盘，返回摘要。"""
    row = _persist_m5_h_contract_if_needed(row)
    row, structure_notes = _resolve_structure_row(row)
    row = _persist_structure_correction(row, structure_notes)
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
    # 垫字后再跑一轮 M2+C 收口，然后若被削短再垫回 hard min
    if str(row.get("structure_type") or chat.get("story_type") or "").upper() == "C":
        chat, _ = patch_sanitize_c_tone_stack(chat)
        from app.services.daily_story.gold_story.gold_chat.patch import (
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
    if str(_st0 or "").upper() == "K":
        from app.services.daily_story.story_types.k.patch import patch_k_body

        chat = dict(chat)
        chat["story_type"] = "K"
        patch_k_body(chat)
        chat, _ = _ensure_gold_chat_min_chars(
            chat,
            mechanism=_mech0,
            structure_type=_st0,
        )
        chat, _ = patch_sanitize_pad_suffix(chat)
        chat, _ = patch_sanitize_pad_particles(chat)
        patch_k_body(chat)
        chat, _ = patch_sanitize_pad_suffix(chat)
        chat, _ = patch_sanitize_pad_particles(chat)
    chat, _ = _gold_chat_j_final_polish(
        chat,
        dialogue_seed=payload0.get("dialogue_seed")
        if isinstance(payload0.get("dialogue_seed"), list)
        else None,
        structure_type=str(row.get("structure_type") or ""),
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
        from app.services.daily_story.story_types.k.patch import patch_k_body

        chat = dict(chat)
        chat["story_type"] = "K"
        # 末轮补字后再剥；不足则用中段句/可读扩写补，禁止粒子叠脏
        for _ in range(5):
            chat, _ = patch_sanitize_pad_suffix(chat)
            chat, _ = patch_sanitize_pad_particles(chat)
            patch_k_body(chat)
            if dialogue_total_chars(chat) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(chat)
            chat, _ = _boost_short_with_mid_lines(
                chat, mechanism=_mech0, structure_type="K"
            )
            chat, _ = _gold_chat_force_min_chars(chat)
            if dialogue_total_chars(chat) <= before:
                break
        chat, _ = patch_sanitize_pad_suffix(chat)
        chat, _ = patch_sanitize_pad_particles(chat)
        from app.services.daily_story.story_types.k.patch import (
            patch_k_fix_truncations,
            patch_k_body,
        )

        patch_k_fix_truncations(chat)
        if dialogue_total_chars(chat) < DAILY_STORY_BODY_CHARS_MIN:
            chat, _ = _boost_short_with_mid_lines(
                chat, mechanism=_mech0, structure_type="K"
            )
            chat, _ = _gold_chat_force_min_chars(chat)
            patch_k_fix_truncations(chat)
        # 出口完整 K patch 后只中段补字+截断修复，避免口头禅去重再砍字
        patch_k_body(chat)
        for _ in range(4):
            if dialogue_total_chars(chat) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(chat)
            chat, c1 = _boost_short_with_mid_lines(
                chat, mechanism=_mech0, structure_type="K"
            )
            chat, c2 = _gold_chat_force_min_chars(chat)
            patch_k_fix_truncations(chat)
            if dialogue_total_chars(chat) <= before and not c1 and not c2:
                break
        chat, _ = patch_sanitize_pad_suffix(chat)
        chat, _ = patch_sanitize_pad_particles(chat)
        patch_k_fix_truncations(chat)
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
    chat = _attach_gold_chat_structure_score(chat, row)
    struct = _gate_gold_chat_structure_score(chat)
    logger.info(
        "[GOLD_CHAT] convert %s structure_score=%s lines=%s chars=%s",
        sid,
        struct,
        len(chat.get("dialogue") or []),
        dialogue_total_chars(chat),
    )
    cfg = config or Config()
    try:
        paths = export_gold_chat_files(
            source_id=sid,
            row=row,
            chat=chat,
            config=cfg,
        )
        _backfill_gold_story_after_export(row, chat=chat, paths=paths, config=cfg)
        logger.info("[GOLD_CHAT] convert %s exported paths=%s", sid, list(paths.keys()))
    except Exception as exc:
        # 机审已过：导出/回写失败不丢稿，便于本地审读与重试落盘
        logger.exception(
            "[GOLD_CHAT] convert %s export/backfill failed: %s", sid, exc
        )
        paths = {}
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

