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
    format_structure_score_feedback,
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
    st = str(row.get("structure_type") or "").strip().upper()
    if not st:
        return row
    try:
        repo_gold_story.update_structure_type(gid, st)
    except ValueError as exc:
        logger.warning("[GOLD_CHAT] structure persist skipped id=%s: %s", gid, exc)
        return row
    payload = cast(dict[str, Any], row.get("payload") or {})
    sc = cast(dict[str, Any], payload.get("scene_contract")) if isinstance(
        payload.get("scene_contract"), dict
    ) else None
    if isinstance(sc, dict) and str(sc.get("story_type") or "").strip().upper() == st:
        repo_gold_story.patch_story_payload(gid, {"scene_contract": sc})
    logger.info(
        "[GOLD_CHAT] structure auto_correct id=%s notes=%s",
        gid,
        "；".join(notes),
    )
    return repo_gold_story.get_story(gid) or row


PASS1_CANDIDATE_COUNT = 4
PASS1_REGENERATE_MAX = 5
PASS1_SHORT_REGENERATE_MAX = 3
PASS1_SHORT_LINE_DEFICIT_MAX = 3
PASS2_MAX_ROUNDS = 2
# 差 ≤40 字本地垫字（215 等 near-miss 须能收口）
GOLD_CHAT_NEAR_MISS_DEFICIT_MAX = 40
# 对白 JSON 正常约数百～1.5k tokens；再大视为跑飞
GOLD_CHAT_LLM_MAX_TOKENS = 2048
CLOSING_PROMPT_MAX_CHARS = 28
_RE_PAD_SUFFIX_STACK = re.compile(
    r"(?:不行吧|真的啊|你听着|你听着了呀|真的呀真的|真的嘛了呀|嘛了呀){2,}|"
    r"呢呢|啊呢|吧呢|嘛呢|呀呢|你呀呢|行了吧呢|不懂你呢|听听不懂|你真是呢|你真是的呢|"
    r"了呢了呀|了呢呀|了呀呢|好不好了呀|着呢了呀",
)
_B_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧", "真的呀")
_F_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧")


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
    content, finish = _client()._chat(  # type: ignore[attr-defined]
        system,
        user,
        thinking_enabled=False,
        temperature=float(temperature),
        max_tokens=budget,
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
    out = re.sub(
        r"(?:不行吧|真的啊|你听着|你听着了呀|真的呀|嘛了呀){2,}([！。！？…]?)$",
        r"\1",
        out,
    )
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
# 偏短句句内加可拍尾巴（姐弟通用；可复用到不同句）
_GOLD_CHAT_LINE_EXPAND: tuple[str, ...] = (
    "，你给我听好了",
    "，这回算清楚",
    "，别再装傻",
    "，我可记住了",
    "，说了就不改",
    "，再闹我可恼了",
)
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
            line, need, used, tails=("呀", "啊", "吧")
        )
        if added > 0:
            return line_out, added
        return line, 0
    if st == "B":
        tails = _B_GOLD_CHAT_PAD_TAILS
    elif st == "F":
        tails = _F_GOLD_CHAT_PAD_TAILS
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
    pad_rounds = 24 if need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX else 12
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
            new_line, added = _pad_gold_chat_line(
                line, need, used=used_pads, story_type=story_type,
            )
            if added <= 0:
                continue
            item["line"] = new_line
            changed = True
            progressed = True
        if not progressed:
            # 垫词用尽时清空复用，优先把 near-miss 垫满
            if used_pads:
                used_pads.clear()
                continue
            break
    return out, changed


def _ensure_gold_chat_min_lines(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """句数 <12 时在收束前插抽象反应句（保交替，不改末 2 句）。"""
    import copy

    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    rows = [x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()]
    if len(rows) >= CHAT_LINE_COUNT_MIN:
        return story, False
    # 只补 near-miss（差 ≤3 句）；差太多交 Pass1 重生成，勿硬插成空壳
    if CHAT_LINE_COUNT_MIN - len(rows) > PASS1_SHORT_LINE_DEFICIT_MAX:
        return story, False

    out = copy.deepcopy(story)
    dlg = list(out.get("dialogue") or [])
    react_i = 0
    guard = 0
    while len(dlg) < CHAT_LINE_COUNT_MIN and guard < 8:
        guard += 1
        insert_at = max(2, len(dlg) - 2)
        prev = dlg[insert_at - 1] if insert_at >= 1 else {}
        prev_sp = str(prev.get("speaker") or "").strip()
        want_sp = "灿灿" if prev_sp == "昭昭" else "昭昭"
        # 选匹配 speaker 的反应句
        line = ""
        for _ in range(len(_GOLD_CHAT_REACT_LINES)):
            sp, ln = _GOLD_CHAT_REACT_LINES[react_i % len(_GOLD_CHAT_REACT_LINES)]
            react_i += 1
            if sp == want_sp:
                line = ln
                break
        if not line:
            line = "少来！" if want_sp == "昭昭" else "听我的！"
        # 避免与邻句完全相同
        neigh = {
            str(dlg[insert_at - 1].get("line") or "") if insert_at >= 1 else "",
            str(dlg[insert_at].get("line") or "") if insert_at < len(dlg) else "",
        }
        if line in neigh:
            continue
        dlg.insert(insert_at, {"speaker": want_sp, "line": line})
    out["dialogue"] = dlg
    return out, len(dlg) > len(rows)


def _expand_short_gold_chat_lines(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """偏短句加可拍尾巴，补到 hard min（每句最多一条尾巴，禁叠灌）。"""
    import copy

    from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    if need <= 0:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, False

    changed = False
    touched: set[int] = set()
    used_clauses: set[str] = set()
    for _ in range(8):
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
        if need <= 0:
            break
        candidates = [
            (i, item)
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and i not in touched
            and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
            and 4 <= len(str(item.get("line") or "").strip()) < 16
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
            if room < 4:
                touched.add(idx)
                continue
            for clause in (
                [c for c in _GOLD_CHAT_LINE_EXPAND if c.lstrip("，,") not in used_clauses]
                + [c for c in _GOLD_CHAT_LINE_EXPAND if c.lstrip("，,") in used_clauses]
            ):
                bare = clause.lstrip("，,")
                if bare in core:
                    continue
                if len(clause) > room or len(clause) > need:
                    continue
                item["line"] = (core + clause + punct)[:DAILY_STORY_LINE_CHARS_MAX]
                used_clauses.add(bare)
                touched.add(idx)
                changed = True
                progressed = True
                break
            if progressed:
                break
        if not progressed:
            break
    return out, changed


def _ensure_gold_chat_min_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """垫到 hard min；先补句数，再句内扩写/粒子垫；sanitize 剥叠后再垫。"""
    data, changed_lines = _ensure_gold_chat_min_lines(story)
    data, changed_exp = _expand_short_gold_chat_lines(data)
    changed = changed_lines or changed_exp

    data2, changed_pad = _patch_gold_chat_near_miss_chars(data)
    data, changed = data2, changed or changed_pad
    if dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
        data3, changed3 = _pad_gold_chat_to_min_chars(data)
        data, changed = data3, changed or changed3

    # 垫 ↔ 剥叠：最多几轮，直到 ≥min 或垫不动
    for _ in range(4):
        data, san = patch_sanitize_c_tone_stack(data)
        data, san2 = patch_sanitize_pad_suffix(data)
        changed = changed or san or san2
        if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
            return data, changed
        before = dialogue_total_chars(data)
        data, exp_again = _expand_short_gold_chat_lines(data)
        data, pad_again = _pad_gold_chat_to_min_chars(data)
        changed = changed or exp_again or pad_again
        if (not exp_again and not pad_again) or dialogue_total_chars(data) <= before:
            break
    return data, changed


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
    structure_type: str = "",
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass1 硬校验 + 格式 fix，直至通过或耗尽 retry。"""
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or data.get("story_type") or "").strip().upper()
    if st:
        data["story_type"] = st
    last_err = ""
    shorten_llm_used = False
    short_expand_llm_used = False
    for attempt in range(5):
        data = _apply_pass1_setting_normalize(data, row=row)
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
            # 偏短：粒子垫字补不动（如 12 短句≈150 字）→ 先 FIX 句内扩写一轮；
            # 仍不足再交外层 Pass1 重生成（勿空烧整稿重抽）
            if _is_short_content_error(last_err):
                if not short_expand_llm_used:
                    deficit = _char_deficit_from_error(last_err) or 0
                    expand_err = last_err
                    if deficit > 0:
                        expand_err = (
                            f"{last_err}；须句内扩写补满还差{deficit}字，"
                            f"偏短句各加到约18–{CHAT_MAX_LINE_CHARS}字，"
                            f"禁止只加语气词、禁止删句"
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
                    data, _ = _ensure_gold_chat_min_chars(data)
                    short_expand_llm_used = True
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
    # 末轮：C 本地收口后再机审，避免弱判据/连说卡死
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
        # 截断回灌后压低 story_raw，减少「照着长叙述扩写跑飞」
        story_raw_cap = 400 if pass1_temperature < 0.35 else 800
        story_raw = story_raw_full[:story_raw_cap]
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
        for _ in range(PASS1_CANDIDATE_COUNT):
            try:
                candidates.append(
                    _generate_pass1_candidate(
                        user,
                        banned_literals=banned_list,
                        source_type=source_type,
                        mom_lines_max=mom_int,
                        structure_type=structure_type,
                        temperature=pass1_temperature,
                        row=row,
                    )
                )
            except ValueError as exc:
                last_err = str(exc)
                # 同提示连打截断只会烧额度；立刻换反馈重抽
                if _is_truncation_error(last_err):
                    hit_truncation = True
                    break
        if not candidates:
            if last_err:
                pass1_feedback_block = format_pass1_regen_feedback(
                    last_err,
                    None,
                    structure_type=structure_type,
                    mechanism=mechanism,
                    closing_intent=closing,
                    beat_chain=beat_chain,
                    conflict_text=conflict_text,
                )
                if hit_truncation or _is_truncation_error(last_err):
                    pass1_temperature = 0.25
                elif _is_short_content_error(last_err):
                    short_regen_count = _bump_short_regen_or_reject(
                        last_err, short_regen_count
                    )
                    pass1_temperature = max(pass1_temperature, 0.35)
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
        data, alt_changed = patch_c_force_sibling_alternate(data)
        if alt_changed:
            type_notes = list(type_notes) + ["C全篇交替"]
        data, crit_changed = patch_c_possession_criterion(data)
        if crit_changed:
            type_notes = list(type_notes) + ["C判据→占有系"]
        data, _ = patch_sanitize_c_tone_stack(data)
        data, _ = patch_sanitize_pad_suffix(data)
        data, _ = _ensure_gold_chat_min_chars(data)
        if type_notes:
            logger.info(
                "gold_chat pre-align type patch: %s",
                "；".join(str(n) for n in type_notes[:4]),
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
            # align 可能写回昭昭「哼」软收末句；结构门控前再跑类型补丁
            chat, post_notes = apply_type_body_pipeline(
                chat, structure_type=structure_type
            )
            if post_notes:
                logger.info(
                    "gold_chat post-align type patch: %s",
                    "；".join(str(n) for n in post_notes[:4]),
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
                    lifted, _ = apply_type_body_pipeline(
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
                pass1_temperature = max(pass1_temperature, 0.35)
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
    sync_discovery_opening_from_dialogue(out)
    attach_daily_story_quality(out, theme=theme, finalize=True, skip_relevancy=True)
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
    chat = _refine_after_normalize(chat, row)
    chat, _ = _ensure_gold_chat_min_chars(chat)
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
        chat, pad_notes = _ensure_gold_chat_min_chars(chat)
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
    chat, _ = _ensure_gold_chat_min_chars(chat)
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

