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
from app.services.daily_story.gold_story.gold_chat_fidelity import (
    apply_m5_h_local_patches,
    collect_fidelity_issues,
    format_beat_sequence_block,
    format_fidelity_block,
    format_fidelity_issues_block,
    format_pass1_regen_feedback,
    format_role_binding_block,
    is_structural_fidelity_kind,
    pass1_fidelity_score,
    should_regenerate_pass1,
    split_fidelity_issues,
    validate_contract_role_consistency,
)
from app.services.daily_story.gold_story.llm_steps import resolve_gold_chat_snippet
from app.services.daily_story.gold_story.scene_contract import (
    CHAT_MAX_LINE_CHARS,
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

{role_binding_block}

{beat_sequence_block}

{pass1_feedback_block}

dialogue_seed（intent 骨架，须扩写为口语对白，禁止照抄）：
{dialogue_seed}

收束意图：{closing_intent}
映射说明：{speaker_map_note}
story_raw（背景，勿照抄；口播/论述须转现场对白）：{story_raw}
禁词（对白中禁止出现）：{banned_literals}
funny_why：{funny_why}
source_type：{source_type}（tutorial 时禁保留教程口吻/第几招）
{structure_hint}
{fidelity_block}

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
- 严格按 scene_contract.beat_chain **与上方事件顺序硬约束、金稿保真 checklist** 顺序推进；妈妈台词 ≤ mom_lines_max
- **互毁段**：「也/还+撕/弄坏+你的」须由受害方说，且先毁方已实质破坏；speaker 不得调序
- 若有上方金稿对白正例：语气/句长可参考；剧情须来自本稿 scene_contract + seed
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
    "修复不得减少正文总字数、不得删句；不足则扩写补齐。\n"
    "只输出完整 JSON。"
)

_FIX_USER = """校验错误：
{errors}

当前 JSON：
{story_json}

规则：
- 正文 dialogue 总字数 {chars_min}–{chars_max}（不足则 **扩写** 到 ≥{chars_min}，建议 18–24 句）
- **修复只增不删**：不得减少总字数、不得删 dialogue 行
- 对白句数须 ≥12；每句 ≤30 字，口语化、可拍
- 妈妈台词须 ≤{mom_lines_max} 句；末句宜姐弟对白（非 hard）
- 若违反金稿保真 checklist（跳步/自编暖收/互毁缺「也」的依据/M5 无加码），须按 checklist 补拍
- 禁词须同义改写：{banned_literals}
- 转述/旁白/括号说明须改为当场对白
- speaker 非法须改为昭昭/灿灿/妈妈
只输出 JSON。"""

_FIDELITY_REFINE_SYSTEM = (
    "你是 gold_chat 保真精修编辑。只改被点到的对白行，其余字段与行数不动。\n"
    "须落实金稿保真 checklist；M5 立规用「家规/规矩/规定」，勿写「妈妈说过」类转述。\n"
    "互毁：报复句之前须 establish 双方物/作品；改机审标定行，"
    "禁止把前文合并进「也/还弄坏」同一句。\n"
    "M5 立规/拒和/加码各占一句，禁止一句三连；"
    "拆句时须保留拒和与加码各一句且在妈妈前（与是否道歉无关）。\n"
    "修复不得减少正文总字数、不得删句；不足则在句内扩写。\n"
    "收场严格按 closing_intent，不发明帮拿/搀扶等新动作；"
    "碘伏/涂药后禁止续写新剧情；「还打不打架」speaker 须与 closing_intent 一致。\n"
    "末 4 句须有拉手或齐声「不打了」。\n"
    "只输出 JSON：{\"fixes\":[{\"no\":行号,\"line\":\"改好后的一句\"}]}"
)

_FIDELITY_REFINE_USER = """保真机审问题（只改标定行）：
{issues_block}

{fidelity_block}

当前 JSON（dialogue 节选）：
{story_json}

硬约束：
- 只改上方标定行号；行数、speaker 不变；每句 ≤30 字
- **不得减少正文总字数、不得删句**；改句后总字数仍须 ≥{chars_min}
- **保真-互毁**：在报复句**之前**的句 establish 破坏依据（抢坏/弄坏）与对方也有该物
  （如「我画…你的画呢」）；报复句可保留，勿合并成一句
- **保真-M5合并/保真-M5加码**：立规、拒和、加码须分句且在妈妈介入前各至少一句
- **保真-和好**：末 4 句补「拉手」或姐弟齐声「不打了」
- **保真-M5拒和speaker**：若已有服软/道歉，拒和/加码须另一方说
- **保真-对象持有补丁**：勿用「我也有你的X」单独补丁互毁对象
- **保真-收场Invent**：删 closing_intent 外的帮忙/搀扶/回来/不疼了等，收成短应答
- **保真-收场拖句**：碘伏/涂药后多余句**可删**；删后总字数仍须 ≥{chars_min}；残句改完整或删
- **保真-齐声问句**：「还打不打架」改 closing_intent 指定角色问；删重复问句
- **保真-H定责**：妈妈分层定责，禁「扯平/都有错」；先点先动手方再劝和
- 正文总字数 {chars_min}–{chars_max}；妈妈台词 ≤{mom_lines_max} 句；末句宜姐弟对白
- 禁词须同义改写：{banned_literals}
- line 只写台词，不带说话人前缀；禁括号说明
只输出 fixes JSON。"""

_FATHER_SPEAKER_ALIASES = frozenset(
    {"爸爸", "父亲", "爸", "老爸", "宝爸", "爸爸角色", "父亲角色"}
)
_KID_RIVAL_ALIASES = frozenset(
    {"小男孩", "小女孩", "对方", "对方小朋友", "陌生小孩", "小朋友", "对方孩子"}
)
_THIRD_PARTY_PARENT_ALIASES = frozenset({"对方家长", "对方妈妈", "对方爸爸"})

PASS1_CANDIDATE_COUNT = 4
PASS1_REGENERATE_MAX = 3
PASS2_MAX_ROUNDS = 2
GOLD_CHAT_NEAR_MISS_DEFICIT_MAX = 3
_GOLD_CHAT_PAD_TAILS = ("呢", "呀", "吧", "嘛", "啊", "哦")


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


_SHORTEN_SYSTEM = (
    "你是 gold_chat 缩句编辑。只缩短超长对白行，语义与 speaker 不变。\n"
    f"每句须 ≤{CHAT_MAX_LINE_CHARS} 字。只输出完整 JSON。"
)

_SHORTEN_USER = """以下对白有单句超过 {max_chars} 字，请**只改超长行**（删冗余词/语气词，勿改剧情）：
{long_lines}

当前 JSON：
{story_json}

规则：行数、speaker、字段不变；每句 ≤{max_chars} 字；禁括号说明。
只输出 JSON。"""

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


def _pad_gold_chat_line(line: str, need: int) -> tuple[str, int]:
    """near-miss 本地垫字：句尾补语气词，不增行。"""
    if need <= 0 or not line:
        return line, 0
    trail = ""
    core = line
    if core[-1] in "。！？…":
        trail = core[-1]
        core = core[:-1]
        if not core:
            return line, 0
    room = max(0, CHAT_MAX_LINE_CHARS - len(line))
    if room <= 0:
        return line, 0
    for suf in sorted(_GOLD_CHAT_PAD_TAILS, key=len, reverse=True):
        if len(suf) <= room and len(suf) <= need:
            return f"{core}{suf}{trail}", len(suf)
    return line, 0


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

    indices = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
    ] or list(range(len(dialogue)))

    changed = False
    for idx in reversed(indices):
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        new_line, added = _pad_gold_chat_line(line, need)
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

    indices = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
    ] or list(range(len(dialogue)))

    changed = False
    for idx in reversed(indices):
        if need <= 0:
            break
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        new_line, added = _pad_gold_chat_line(line, need)
        if added <= 0:
            continue
        item["line"] = new_line
        need -= added
        changed = True
    return out, changed


def _ensure_gold_chat_min_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    data, changed = _patch_gold_chat_near_miss_chars(story)
    if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
        return data, changed
    data2, changed2 = _pad_gold_chat_to_min_chars(data)
    return data2, changed or changed2


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
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("no pass1 candidates")
    if len(candidates) == 1:
        return candidates[0]
    return min(
        candidates,
        key=lambda d: pass1_fidelity_score(
            d,
            structure_type=structure_type,
            mechanism=mechanism,
            closing_intent=closing_intent,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        ),
    )


def _fidelity_refine_with_llm(
    story: dict[str, Any],
    issues: list[dict[str, Any]],
    *,
    fidelity_block: str,
    banned_literals: list[str],
    mom_lines_max: int = 1,
) -> dict[str, Any]:
    user = _FIDELITY_REFINE_USER.format(
        issues_block=format_fidelity_issues_block(issues),
        fidelity_block=fidelity_block,
        story_json=json.dumps(story, ensure_ascii=False)[:8000],
        chars_min=DAILY_STORY_BODY_CHARS_MIN,
        chars_max=DAILY_STORY_BODY_CHARS_MAX,
        banned_literals="、".join(banned_literals) or "（无）",
        mom_lines_max=max(0, int(mom_lines_max)),
    )
    return _chat_json(_FIDELITY_REFINE_SYSTEM, user)


def refine_gold_chat_fidelity(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    fidelity_block: str,
    banned_literals: list[str] | None = None,
    mom_lines_max: int = 1,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    max_rounds: int = PASS2_MAX_ROUNDS,
    bail_on_structural: bool = True,
) -> dict[str, Any]:
    """Pass 2：保真机审 → LLM 定点精修 → 再 hard 校验。"""
    banned = [str(x) for x in (banned_literals or []) if str(x).strip()]
    mom_max = max(0, int(mom_lines_max))
    closing = str(closing_intent or "").strip()
    data = _normalize_chat_speakers(dict(story))
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()

    for _round in range(max(1, int(max_rounds))):
        if mech == "M5" and st == "H":
            data, _ = apply_m5_h_local_patches(data)

        issues = collect_fidelity_issues(
            data,
            structure_type=st,
            mechanism=mech,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        )
        blocking, warn = split_fidelity_issues(issues)
        if not blocking and not warn:
            data, _ = _ensure_gold_chat_min_chars(data)
            validate_gold_chat(
                data,
                banned_literals=banned,
                mom_lines_max=mom_max,
            )
            return data
        if not blocking:
            if warn:
                logger.info(
                    "gold_chat fidelity warn only: %s",
                    "、".join(str(x.get("kind") or "") for x in warn[:3]),
                )
            data, _ = _ensure_gold_chat_min_chars(data)
            validate_gold_chat(
                data,
                banned_literals=banned,
                mom_lines_max=mom_max,
            )
            return data
        if bail_on_structural and should_regenerate_pass1(blocking):
            struct_kinds = [
                str(x.get("kind") or "")
                for x in blocking
                if is_structural_fidelity_kind(str(x.get("kind") or ""))
            ]
            kinds = "、".join(struct_kinds[:3]) or "、".join(
                str(x.get("kind") or "") for x in blocking[:3]
            )
            raise ValueError(f"fidelity_structural:{kinds}")

        raw = _fidelity_refine_with_llm(
            data,
            blocking + warn,
            fidelity_block=fidelity_block,
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
        data, _ = _ensure_gold_chat_min_chars(data)
        try:
            validate_gold_chat(
                data,
                banned_literals=banned,
                mom_lines_max=mom_max,
            )
        except ValueError:
            continue

    remain = collect_fidelity_issues(
        data,
        structure_type=st,
        mechanism=mech,
        closing_intent=closing,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
    )
    blocking_remain, warn_remain = split_fidelity_issues(remain)
    if blocking_remain:
        kinds = "、".join(str(x.get("kind") or "") for x in blocking_remain[:3])
        raise ValueError(f"fidelity_refine_failed:{kinds}")
    if warn_remain:
        logger.info(
            "gold_chat fidelity warn remain: %s",
            "、".join(str(x.get("kind") or "") for x in warn_remain[:3]),
        )
    data, _ = _ensure_gold_chat_min_chars(data)
    validate_gold_chat(
        data,
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


def _structure_type_hint(structure_type: str, mechanism: str = "") -> str:
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if st == "H":
        extra = ""
        if mech == "M5":
            extra = (
                "\n- **M5+H**：互毁须双向；妈妈前须拒和+加码两拍嘴硬再调解；"
                "先动手方与受害方分工：服软/道歉≠拒和/加码，禁止同一 speaker；"
                "scene conflict 受害方须在前 2 句 establish 持有/创作，先毁物者≠受害方；"
                "禁止「秘密画/抢看秘密」偏题，须写捣乱毁画→互毁→扭打"
            )
        return f"""【H 第三方化解 · 机制 {mech or "?"}】
- 详拍见下方「金稿保真 checklist」，逐步落实勿跳步{extra}"""
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
    mechanism = str(row.get("mechanism") or "")
    beat = payload.get("beat") if isinstance(payload.get("beat"), list) else []
    closing = str(
        payload.get("closing_intent") or scene_contract.get("closing_intent") or ""
    )
    beat_chain = scene_contract.get("beat_chain") or []
    if not isinstance(beat_chain, list):
        beat_chain = []
    conflict_text = str(
        scene_contract.get("conflict") or row.get("conflict_core") or ""
    )
    contract_role_errs = validate_contract_role_consistency(
        scene_contract,
        conflict_core=str(row.get("conflict_core") or ""),
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
    fidelity_block = format_fidelity_block(
        structure_type=structure_type,
        mechanism=mechanism,
        beat=beat,
        closing_intent=closing,
        story_raw=story_raw,
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
            conflict_core=str(row.get("conflict_core") or "")[:500],
            scene_contract_block=format_scene_contract_block(scene_contract),
            role_binding_block=role_binding_block,
            beat_sequence_block=beat_sequence_block,
            pass1_feedback_block=pass1_feedback_block,
            dialogue_seed=_format_dialogue_seed(seed)[:4000],
            closing_intent=str(
                payload.get("closing_intent")
                or scene_contract.get("closing_intent")
                or ""
            )[:500],
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
            fidelity_block=fidelity_block,
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
        )
        try:
            return refine_gold_chat_fidelity(
                data,
                structure_type=structure_type,
                mechanism=mechanism,
                fidelity_block=fidelity_block,
                banned_literals=banned_list,
                mom_lines_max=mom_int,
                closing_intent=closing,
                beat_chain=beat_chain,
                conflict_text=conflict_text,
                max_rounds=PASS2_MAX_ROUNDS,
                bail_on_structural=True,
            )
        except ValueError as exc:
            last_err = str(exc)
            if not str(exc).startswith(("fidelity_structural:", "fidelity_refine_failed:")):
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
            err = str(exc)
            if "正文总字数须≥" in err:
                padded, changed = _ensure_gold_chat_min_chars(fixed)
                if changed:
                    try:
                        validate_gold_chat(
                            padded,
                            banned_literals=banned_literals,
                            source_type=source_type,
                            mom_lines_max=mom_lines_max,
                        )
                        fixed = padded
                    except ValueError as exc2:
                        logger.info(
                            "gold_chat polish line %d dropped: %s",
                            no,
                            exc2,
                        )
                        continue
                else:
                    logger.info("gold_chat polish line %d dropped: %s", no, exc)
                    continue
            else:
                logger.info("gold_chat polish line %d dropped: %s", no, exc)
                continue
        accepted = trial
    if not accepted:
        return chat, accepted
    fixed, _ = apply_spot_fixes(chat, raw_fixes, only=accepted)
    fixed, _ = _ensure_gold_chat_min_chars(fixed)
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
