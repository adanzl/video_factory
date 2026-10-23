"""gold_chat 终稿：类型垫字 / 钉收束 / 结构分门控。

三阶段末环（扩写 → 精修 → **终稿**）。从 ``convert.convert_gold_chat``
抽出；convert 只负责编排到此步再导出。

K 收口原则：走 ``story_types.k.patch`` 的 seal/pin，中段通用补字；
不在本文件手写收束五句或固定 filler 插句。
"""

from __future__ import annotations

from app.services.gold_story.gold_chat.status import gold_chat_source_text

import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path
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
    _pad_line_is_duplicate,
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
    closing_accept_marker,
    collect_align_issues,
    gold_chat_effective_min_chars,
    is_sulk_closing,
    split_align_issues,
)
from app.services.gold_story.scene import sanitize_banned_literals

logger = logging.getLogger(__name__)

_GOLD_CHAT_STRUCTURE_LIFT_MAX = 2
_GOLD_CHAT_EXPORT_REPAIR_MAX = 2
_GOLD_CHAT_DUPLICATE_RESCUE_MAX = 1

# 可定点修的硬卡口径由 validate.chat_hard_error_is_local 单点定义，这里不再
# 自列一份字符串表——两处口径各写一份正是此前「同一份稿两个判定」的来源。


class GoldChatAcceptanceBlocked(ValueError):
    """终检高置信度硬伤，禁止导出。"""


class GoldChatLocalDuplicateBlocked(GoldChatAcceptanceBlocked):
    """仅本地重复硬伤，可进入有限次定点修稿。"""

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None) -> None:
        self.issues = [dict(item) for item in (issues or []) if isinstance(item, dict)]
        super().__init__(message)


class GoldChatSemanticBlocked(GoldChatAcceptanceBlocked):
    """终检 LLM 语义硬伤；保留结构化 issues 供定点修稿冻结范围。"""

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None) -> None:
        self.issues = [dict(item) for item in (issues or []) if isinstance(item, dict)]
        super().__init__(message)


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
    """语义审核未完成（超时/解析失败）或阻断证据不可核验，非稿子过错。

    ``candidate``：失败时的稳定候选稿。带上它才能落库供人工复核——此前该类异常
    不带候选，失败稿只剩日志，无法复算（专家裁决 2026-10）。
    """

    # 落库口径：failed 走 gold_chat_failed_candidate（不与「待审核」候选混用）
    candidate_review_status = "failed"

    def __init__(
        self,
        message: str,
        *,
        candidate: dict[str, Any] | None = None,
    ) -> None:
        self.candidate = dict(candidate) if isinstance(candidate, dict) else None
        super().__init__(message)


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


_VERBATIM_SOURCE_QUIRK_KINDS = ("语病",)
_VERBATIM_SOURCE_QUIRK_MAX = 2
_VERBATIM_SOURCE_QUIRK_MIN_CHARS = 8


def _demote_verbatim_source_quirks(
    review: Any,
    chat: dict[str, Any],
    *,
    source_raw: str = "",
) -> Any:
    """终检把「源故事里的原句」判成语病时降级留档。

    同一句「老虎一吼，公主也得现出原形」在不同轮次里时过时不过（20:21 放行、
    15:04 判「公主不是老虎变的，谈不上现出原形」）——这是终检对非字面表达的
    随机误读，不是稿子的问题。判据只用一条：被点名的引文在源故事里逐字存在，
    则它是作者原句，机器无权判它语病。降级条目仍写进 review_downgraded_issues
    供人工抽检，不静默吞掉。
    """
    # 逐拍路径把源文写进成稿，整篇扩写路径没有 → 两条路都要能取到源文。
    source = re.sub(
        r"[^\u4e00-\u9fff]",
        "",
        str(chat.get("source_raw") or source_raw or ""),
    )
    issues = getattr(review, "issues", None)
    if not source or not issues:
        return review
    kept: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    for it in issues:
        kind = str(it.get("kind") or "")
        evidence = it.get("evidence") or []
        quotes = [
            re.sub(r"[^\u4e00-\u9fff]", "", str(ev.get("quote") or ""))
            for ev in evidence
            if isinstance(ev, dict)
        ]
        # 引文太短（<8 字）时「是源文子串」几乎必然成立，不能当豁免证据；
        # 总数也只放 2 条，避免整稿语病被一次降级放行。
        long_enough = all(len(q) >= _VERBATIM_SOURCE_QUIRK_MIN_CHARS for q in quotes)
        if (
            kind in _VERBATIM_SOURCE_QUIRK_KINDS
            and quotes
            and long_enough
            and all(q and q in source for q in quotes)
            and len(demoted) < _VERBATIM_SOURCE_QUIRK_MAX
        ):
            demoted.append(it)
            continue
        kept.append(it)
    if not demoted:
        return review
    logger.info(
        "[GOLD_CHAT] 终检误杀源故事原句 %s 条，降级留档：%s",
        len(demoted),
        [str(it.get("desc") or "")[:40] for it in demoted[:3]],
    )
    from app.services.daily_story.review import format_downgraded_issue_record

    review.issues = kept
    review.downgraded = list(getattr(review, "downgraded", None) or []) + [
        format_downgraded_issue_record(it, reason="source_verbatim") for it in demoted
    ]
    return review


# 「明确归因」标记：只有这些说法才算「引用别人说过的话」。
_CITATION_MARKER_RE = re.compile(
    r"你说|你说的|你说过|你刚|你刚才|你明明|你之前|你先前|你曾|"
    r"你讲过|你提过|还夸|说过的|讲过的"
)
# 只有明确归因类的「引用无据」需要前文真有出处；单纯用评价词（眉清目秀、
# 嘴变快）是角色自己的判断，不构成引用。
_CITATION_KIND = "引用无据"


def _demote_nonattributed_citation_issues(
    review: Any,
    chat: dict[str, Any],
) -> Any:
    """把「引用无据」里没有归因标记的条目降级。

    审读模型看到「眉清目秀也压不住吼声」会判「全篇没人说过眉清目秀」——但这是
    角色自己的评价，不是引用。判据只看被点名的那几行里有没有「你说/你刚还夸」
    这类归因标记：没有就不是引用，不该用「引用无据」拦稿。
    """
    issues = getattr(review, "issues", None)
    if not issues:
        return review
    dialogue = chat.get("dialogue") or []
    kept: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    for it in issues:
        if str(it.get("kind") or "") != _CITATION_KIND:
            kept.append(it)
            continue
        nos = it.get("lines") if isinstance(it.get("lines"), list) else []
        texts = [
            str(dialogue[i - 1].get("line") or "")
            for i in nos
            if isinstance(i, int) and 1 <= i <= len(dialogue)
            and isinstance(dialogue[i - 1], dict)
        ]
        if texts and not any(_CITATION_MARKER_RE.search(t) for t in texts):
            demoted.append(it)
            continue
        kept.append(it)
    if not demoted:
        return review
    from app.services.daily_story.review import format_downgraded_issue_record

    logger.info(
        "[GOLD_CHAT] 无归因的「引用无据」降级 %s 条：%s",
        len(demoted),
        [str(it.get("desc") or "")[:40] for it in demoted[:3]],
    )
    review.issues = kept
    review.downgraded = list(getattr(review, "downgraded", None) or []) + [
        format_downgraded_issue_record(it, reason="no_attribution")
        for it in demoted
    ]
    return review


def _validate_chat_or_repairable(
    validate_chat: Any,
    chat: dict[str, Any],
) -> None:
    try:
        validate_chat(chat)
    except ValueError as exc:
        msg = str(exc).strip()
        parts = [p.strip() for p in msg.split(";") if p.strip()]
        from app.services.gold_story.gold_chat.validate import (
            chat_hard_error_is_local,
        )

        if parts and all(chat_hard_error_is_local(part) for part in parts):
            raise GoldChatValidationRepairableError(msg) from exc
        raise


def _try_final_hard_floor_one_char_close(
    chat: dict[str, Any],
    exc: GoldChatValidationRepairableError,
) -> tuple[dict[str, Any], bool]:
    """终检仅差 1 字且无其它硬错时，本地补一个安全单粒子后再验。"""
    total = dialogue_total_chars(chat)
    if total != DAILY_STORY_BODY_CHARS_MIN - 1:
        return chat, False
    parts = [p.strip() for p in str(exc).split(";") if p.strip()]
    if not parts or not all("正文总字数须≥" in part for part in parts):
        return chat, False

    from app.services.gold_story.gold_chat.length import (
        _patch_gold_chat_near_miss_chars,
    )

    closed, changed = _patch_gold_chat_near_miss_chars(chat)
    if not changed or dialogue_total_chars(closed) < DAILY_STORY_BODY_CHARS_MIN:
        return chat, False
    return closed, True


def _try_terminal_sibling_adjacency_close(
    chat: dict[str, Any],
    *,
    validate_chat: Any,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
) -> dict[str, Any]:
    """结构评分之前的终态连说兜底：行序类问题机械修，不烧 LLM 修稿预算。

    连说判据只看「说话人 + 相邻位置」，修复动作与类型补丁同源（插短反应、不删句）。
    前面各层（类型补丁 / seed 补拍 / 契约重排）都可能把相邻同人重新排到一起，
    而结构评分只认最终行序，所以这一步必须发生在最终行序之后、``attach_score`` 之前。
    修完仍不合法（字数/句数/speaker 被撑破）就退回原稿，交回原有失败链路，
    不引入新的失败方式。
    """
    from app.services.gold_story.gold_chat.patch import (
        repair_sibling_adjacency_terminal,
    )

    repaired, notes = repair_sibling_adjacency_terminal(
        dict(chat),
        beat_chain=beat_chain,
        dialogue_seed=dialogue_seed,
    )
    if not notes:
        return chat
    try:
        _validate_chat_or_repairable(validate_chat, repaired)
    except Exception:
        logger.info(
            "gold_chat terminal adjacency repair rejected notes=%s",
            notes,
        )
        return chat
    logger.info("gold_chat terminal adjacency repaired notes=%s", notes)
    return repaired


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


def _semantic_repair_target_lines(exc: GoldChatSemanticBlocked) -> set[int]:
    """语义终检可改行；缺前提额外开放故障行前一行作为补拍位。"""
    targets: set[int] = set()
    for item in exc.issues:
        raw_lines = item.get("lines")
        if not isinstance(raw_lines, list):
            continue
        issue_lines: list[int] = []
        for no in raw_lines:
            if isinstance(no, int) and not isinstance(no, bool) and no > 0:
                normalized = int(no)
                targets.add(normalized)
                issue_lines.append(normalized)
        # 「缺前提」的故障通常落在依赖该前提的后一句。若仍只允许改故障行，
        # 修稿器无法把 missing_beat 放到它之前，只能硬改结果句绕过问题。
        # 因此只额外开放最早故障行的前一行，仍冻结行数、speaker 和其它行。
        if str(item.get("kind") or "").strip() == "缺前提" and issue_lines:
            first = min(issue_lines)
            if first > 1:
                targets.add(first - 1)
    return targets


def _semantic_repair_scope_block(
    exc: GoldChatSemanticBlocked,
    chat: dict[str, Any],
) -> str:
    """把结构化审核项、可改行与只读邻句明确写进修稿指令。"""
    targets = sorted(_semantic_repair_target_lines(exc))
    if not targets:
        return ""
    labels = "、".join(f"第{no}句" for no in targets)
    # 「缺前提」是结果句依赖的事件没被任何人说出来；只允许改写无法补出前提，
    # 故对缺拍类额外放行「插入至多一行」，其余行数/行序/speaker 仍冻结。
    missing_beat_rows = _semantic_missing_beat_entries(exc)
    parts = [
        f"【语义定点范围】只允许改{labels}的 line 文本；",
        "对白行数、行序、全部 speaker、其它行文本全部冻结"
        + ("（下述缺拍补行为唯一例外）。" if missing_beat_rows else "。"),
        "未点名的相邻句仅用于判断问答对象和我/你视角，不得修改。",
    ]
    if missing_beat_rows:
        earliest = _semantic_earliest_target_line(exc) or min(targets)
        parts.append(
            f"【缺拍补行】可在第{max(1, earliest)}句之前**新增至多一行**对白，"
            "用来把缺失事件说出来；只许新增这一行，不许删行、挪行、改他人台词。"
            "补行必须是角色说出口的话，不得写成旁白或动作说明，"
            "且不得引入新的道具或新事件。"
        )
        for beat in missing_beat_rows[:4]:
            beat_no = beat.get("beat")
            intent = str(beat.get("intent") or "").strip()
            speaker = str(beat.get("speaker") or "").strip()
            row_desc = f"- 缺失契约 beat={beat_no}"
            if speaker:
                row_desc += f" 说话人应为{speaker}"
            if intent:
                row_desc += f"：{intent}"
            parts.append(row_desc)
    for item in exc.issues[:8]:
        raw_lines = item.get("lines")
        line_txt = raw_lines if isinstance(raw_lines, list) else []
        kind = str(item.get("kind") or "").strip()
        desc = str(item.get("desc") or "").strip()
        fix = str(item.get("fix") or "").strip()
        detail = f"- 第{line_txt}句 {kind}：{desc}".rstrip("：")
        if fix:
            detail += f"；审核建议：{fix}"
        if kind == "缺前提":
            missing_beat = item.get("missing_beat")
            if isinstance(missing_beat, dict):
                beat = missing_beat.get("beat")
                intent = str(missing_beat.get("intent") or "").strip()
                if beat is not None or intent:
                    detail += f"；必须补回契约 beat={beat} {intent}".rstrip()
            detail += "；允许改最早故障行的前一行来补前提，且前提必须出现在依赖它的台词之前"
        if kind == "语病" and "指代" in desc:
            detail += (
                "；若是‘这个/那个/它/这’等指代不清，直接改成上下文已有的具体事物名，"
                "不要靠只读邻句新增解释"
            )
        parts.append(detail)

    dialogue = chat.get("dialogue")
    if isinstance(dialogue, list):
        target_set = set(targets)
        context_nos: set[int] = set()
        for no in targets:
            for ctx_no in (no - 1, no + 1):
                if 1 <= ctx_no <= len(dialogue) and ctx_no not in target_set:
                    context_nos.add(ctx_no)
        if context_nos:
            parts.append("【只读邻句】")
            for no in sorted(context_nos)[:12]:
                item = dialogue[no - 1]
                if not isinstance(item, dict):
                    continue
                speaker = str(item.get("speaker") or "").strip()
                line = str(item.get("line") or "").strip()
                parts.append(f"- 第{no}句 {speaker}：{line}")
    return "\n".join(parts)


def _protected_closing_line_index(chat: dict[str, Any]) -> int | None:
    """标了「赢了但没消气」的收束拍所在行号（1 基）；没有返回 None。

    修稿只许做表层改写：把「心里这口气还没顺」改成「这还差不多」等于把
    反差收平，笑点余味全丢（#144 run27 实测：两轮修稿后好笑分 8，结构 80）。
    """
    chain = chat.get("gold_beat_chain") or chat.get("beat_chain") or []
    if not isinstance(chain, list) or not chain:
        return None
    last = chain[-1]
    if not isinstance(last, dict):
        return None
    if not is_sulk_closing(last):
        return None
    rows = chat.get("dialogue")
    if not isinstance(rows, list) or not rows:
        return None
    tail = rows[-1]
    speaker = str(last.get("speaker") or "").strip()
    if (
        speaker
        and isinstance(tail, dict)
        and str(tail.get("speaker") or "").strip() != speaker
    ):
        return None
    return len(rows)


def _sanitize_semantic_scoped_repair(
    original: dict[str, Any],
    lifted: dict[str, Any],
    *,
    target_lines: set[int],
    st_final: str,
    normalize_chat: Any,
) -> tuple[dict[str, Any], bool]:
    """语义定点修只落目标行文本；shape/speaker/非目标行严格冻结。"""
    normalized = normalize_chat(lifted)
    original_rows = original.get("dialogue")
    repaired_rows = normalized.get("dialogue")
    if (
        not target_lines
        or not isinstance(original_rows, list)
        or not isinstance(repaired_rows, list)
        or len(repaired_rows) != len(original_rows)
    ):
        return dict(original), False

    closing_idx = _protected_closing_line_index(original)
    scoped_rows: list[Any] = [dict(x) if isinstance(x, dict) else x for x in original_rows]
    changed = False
    for idx in sorted(target_lines):
        if not (1 <= idx <= len(original_rows)):
            continue
        old_item = original_rows[idx - 1]
        new_item = repaired_rows[idx - 1]
        if not isinstance(old_item, dict) or not isinstance(new_item, dict):
            continue
        old_speaker = str(old_item.get("speaker") or "").strip()
        new_speaker = str(new_item.get("speaker") or "").strip()
        if old_speaker != new_speaker:
            continue
        new_line = str(new_item.get("line") or "").strip()
        old_line = str(old_item.get("line") or "").strip()
        if new_line and new_line != old_line:
            # 收束拍极性守卫：「没消气」被改成「这还差不多」时回退该行，
            # 不让修稿把设计好的反差余味抹平。
            if (
                closing_idx == idx
                and closing_accept_marker(new_line)
                and not closing_accept_marker(old_line)
            ):
                logger.info(
                    "gold_chat repair guard: line=%s 收束极性被改写，回退该行",
                    idx,
                )
                continue
            scoped_rows[idx - 1]["line"] = new_line
            changed = True

    out = dict(original)
    out["dialogue"] = scoped_rows
    if st_final:
        out["story_type"] = st_final
    out, _ = patch_sanitize_pad_suffix(out)
    out, _ = patch_sanitize_pad_particles(out)
    if str(st_final or "").strip().upper() == "I":
        from app.services.daily_story.story_types.i.patch import (
            patch_i_acknowledge_apology,
            patch_i_collapse_repeated_claim_questions,
            patch_i_ground_opening_quote_assertion,
            patch_i_parent_acknowledge_child_feeling,
            patch_i_parent_accept_child_pause,
            patch_i_strip_self_action_narration,
        )

        patch_i_strip_self_action_narration(out)
        patch_i_ground_opening_quote_assertion(out)
        patch_i_acknowledge_apology(out)
        patch_i_parent_acknowledge_child_feeling(out)
        patch_i_parent_accept_child_pause(out)
        patch_i_collapse_repeated_claim_questions(out)

    # sanitizer 只能影响目标行；非目标行逐字回滚，speaker 永远沿用 original。
    cleaned_rows = out.get("dialogue")
    if isinstance(cleaned_rows, list) and len(cleaned_rows) == len(original_rows):
        for idx, old_item in enumerate(original_rows, 1):
            if idx in target_lines or not isinstance(old_item, dict):
                continue
            cleaned_rows[idx - 1] = dict(old_item)
        for idx in target_lines:
            if not (1 <= idx <= len(original_rows)):
                continue
            old_item = original_rows[idx - 1]
            cur_item = cleaned_rows[idx - 1]
            if isinstance(old_item, dict) and isinstance(cur_item, dict):
                cur_item["speaker"] = old_item.get("speaker")
    if str(st_final or "").strip().upper() == "I":
        from app.services.daily_story.story_types.i.patch import (
            patch_i_rewrite_duplicate_question_groups,
        )

        patch_i_rewrite_duplicate_question_groups(
            out,
            preferred_indexes=target_lines,
        )
    return out, changed


def _semantic_missing_beat_entries(
    exc: GoldChatSemanticBlocked,
) -> list[dict[str, Any]]:
    """终检「缺前提」项里携带的缺失契约 beat（含期望 speaker）。"""
    out: list[dict[str, Any]] = []
    for item in exc.issues:
        if str(item.get("kind") or "").strip() != "缺前提":
            continue
        missing = item.get("missing_beat")
        if isinstance(missing, dict):
            out.append(missing)
    return out


def _semantic_missing_beat_speakers(exc: GoldChatSemanticBlocked) -> set[str]:
    """终检「缺前提」点名的缺拍说话人（确定性补拍的额度只花在他们身上）。"""
    return {
        str(entry.get("speaker") or "").strip()
        for entry in _semantic_missing_beat_entries(exc)
        if str(entry.get("speaker") or "").strip()
    }


def _semantic_earliest_target_line(exc: GoldChatSemanticBlocked) -> int:
    """最早故障行号；缺拍须插在它之前才有因果。"""
    earliest = 0
    for item in exc.issues:
        raw_lines = item.get("lines")
        if not isinstance(raw_lines, list):
            continue
        for no in raw_lines:
            if isinstance(no, int) and not isinstance(no, bool) and no > 0:
                earliest = int(no) if not earliest else min(earliest, int(no))
    return earliest


def _extract_single_inserted_row(
    original_rows: list[Any],
    repaired_rows: list[Any],
    *,
    editable_indexes: set[int] | None = None,
) -> tuple[int, dict[str, Any]] | None:
    """修复稿比原稿恰好多一行时，定位该行与其插入下标。

    ``editable_indexes`` 是允许改写 line 文本的原稿下标（故障行），其余行必须
    逐句未改；**所有**行（含故障行）的 speaker 都必须与原文一致。

    允许改写会让多个插入点都「说得通」（把某个原行误判成新插行），故这里按
    **逐行精确匹配数**取最高分，而不是取第一个能自圆其说的下标——否则会把
    原稿已有的台词当成补拍行插进去，同时丢掉真正的新行。
    """
    if len(repaired_rows) - len(original_rows) != 1:
        return None
    editable = editable_indexes or set()

    def _text(item: Any) -> str:
        return str(item.get("line") or "").strip() if isinstance(item, dict) else ""

    def _spk(item: Any) -> str:
        return (
            str(item.get("speaker") or "").strip() if isinstance(item, dict) else ""
        )

    best_rank: tuple[int, int] | None = None
    best_idx = -1
    for idx in range(len(repaired_rows)):
        inserted = repaired_rows[idx]
        if not isinstance(inserted, dict):
            continue
        score = 0
        valid = True
        for pos, old in enumerate(original_rows):
            if not isinstance(old, dict):
                valid = False
                break
            j = pos if pos < idx else pos + 1
            if not (0 <= j < len(repaired_rows)):
                valid = False
                break
            new = repaired_rows[j]
            if not isinstance(new, dict) or _spk(old) != _spk(new):
                valid = False
                break
            if _text(old) == _text(new):
                score += 1
            elif pos not in editable:
                valid = False
                break
        if not valid:
            continue
        # 优先「插入行确实不是任何原行原文」的解，避免把原行当补行。
        is_new_text = _text(inserted) not in {
            _text(x) for x in original_rows if isinstance(x, dict) and _text(x)
        }
        rank = (score, 1 if is_new_text else 0)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_idx = idx
    if best_rank is None or best_idx < 0:
        return None
    return best_idx, dict(repaired_rows[best_idx])


def _missing_beat_expected_speakers(
    beats: list[dict[str, Any]],
    *,
    chat: dict[str, Any] | None = None,
) -> set[str]:
    """缺失拍允许的补行说话人：beat 本人 + 该拍的对手方（addressee）。

    「被推趔趄」这类拍，契约 speaker 是**受动方**，但补前提的话通常由**施动方**
    说出（谁干了这事）。若只认 speaker，合法补行会被一律拒绝；故从契约 beat_chain
    读出 addressee（施动方）一并放行。全部取自数据字段，不写剧情词表。

    ``chat`` 只用于取契约 beat_chain（读 addressee）；不要用求交结果当作
    「是否需要校验」的判据——那会把「契约有 speaker、但名字对不上」这种该拒绝
    的情况变成静默放行。
    """
    chain_lookup = _missing_beat_contract_lookup(chat)
    speakers: set[str] = set()
    for beat in beats:
        speaker = str(beat.get("speaker") or "").strip()
        if speaker:
            speakers.add(speaker)
        source = beat
        beat_no = beat.get("beat")
        if isinstance(beat_no, int) and beat_no in chain_lookup:
            source = {**chain_lookup[beat_no], **beat}
        raw_addressee = source.get("addressee")
        candidates: list[str] = []
        if isinstance(raw_addressee, str):
            candidates = re.split(r"[/、,，和与]", raw_addressee)
        elif isinstance(raw_addressee, list):
            candidates = [str(x) for x in raw_addressee]
        for name in candidates:
            cleaned = str(name or "").strip()
            if cleaned:
                speakers.add(cleaned)
    speakers = {x for x in speakers if x}
    return speakers


def _missing_beat_contract_lookup(
    chat: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    """从候选稿携带的契约里按 beat 号索引整拍（读 addressee 等字段）。"""
    if not isinstance(chat, dict):
        return {}
    chain = chat.get("gold_beat_chain")
    if not isinstance(chain, list) or not chain:
        sc = chat.get("scene_contract")
        chain = sc.get("beat_chain") if isinstance(sc, dict) else None
    if not isinstance(chain, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(chain, 1):
        if not isinstance(item, dict):
            continue
        beat_no = item.get("beat")
        key = beat_no if isinstance(beat_no, int) and beat_no > 0 else index
        out[key] = item
    return out


def _dialogue_speaker_names(chat: dict[str, Any]) -> set[str]:
    dialogue = chat.get("dialogue")
    if not isinstance(dialogue, list):
        return set()
    return {
        str(x.get("speaker") or "").strip()
        for x in dialogue
        if isinstance(x, dict) and str(x.get("speaker") or "").strip()
    }


def _apply_semantic_missing_beat_insertion(
    original: dict[str, Any],
    lifted: dict[str, Any],
    exc: GoldChatSemanticBlocked,
    *,
    target_lines: set[int],
    st_final: str,
    normalize_chat: Any,
) -> tuple[dict[str, Any], bool]:
    """缺拍兜底：允许插入**至多一行**契约缺失拍，其余行严格冻结。

    缺前提的根因是「结果句依赖的事件没被任何人说出来」，只改写故障行必然
    改出无因之果。故在最早故障行之前放行一行补拍，仍受硬约束：
    行数上限、期望 speaker、禁旁白、禁近似重复。
    """
    from app.services.gold_story.scene import (
        CHAT_MAX_LINE_CHARS,
        chat_line_cap,
        looks_like_narration_line,
    )

    beats = _semantic_missing_beat_entries(exc)
    earliest = _semantic_earliest_target_line(exc)
    original_rows = original.get("dialogue")
    if (
        not beats
        or not earliest
        or not isinstance(original_rows, list)
        or not original_rows
    ):
        return dict(original), False

    normalized = normalize_chat(lifted)
    repaired_rows = normalized.get("dialogue")
    if not isinstance(repaired_rows, list):
        return dict(original), False

    cap = chat_line_cap(st_final)
    if len(original_rows) + 1 > cap:
        return dict(original), False

    located = _extract_single_inserted_row(
        original_rows,
        repaired_rows,
        editable_indexes={n - 1 for n in target_lines if 1 <= n <= len(original_rows)},
    )
    if located is None:
        return dict(original), False
    raw_idx, inserted = located
    inserted_line = str(inserted.get("line") or "").strip()
    inserted_speaker = str(inserted.get("speaker") or "").strip()
    if not inserted_line or not inserted_speaker:
        return dict(original), False
    if len(inserted_line) > CHAT_MAX_LINE_CHARS:
        return dict(original), False
    if looks_like_narration_line(inserted_line):
        return dict(original), False
    # 说话人校验：拿到契约期望 speaker 就必须严格匹配；求交为空说明契约里的
    # 说话人在本篇根本没开口，同样拒绝（不可静默放行）。契约给不出期望时，
    # 退化为「不得引入新角色」。
    dialogue_speakers = _dialogue_speaker_names(original)
    expected = _missing_beat_expected_speakers(beats, chat=original)
    if expected:
        allowed = expected & dialogue_speakers
        if not allowed or inserted_speaker not in allowed:
            return dict(original), False
    elif inserted_speaker not in dialogue_speakers:
        return dict(original), False
    # 必须落在最早故障行之前（0-based 下标 <= earliest-1）
    if raw_idx > earliest - 1:
        return dict(original), False
    existing_lines = [
        str(x.get("line") or "").strip()
        for x in original_rows
        if isinstance(x, dict)
    ]
    if _pad_line_is_duplicate(inserted_line, existing_lines):
        return dict(original), False

    scoped_rows: list[Any] = [
        dict(x) if isinstance(x, dict) else x for x in original_rows
    ]
    # 修复稿比原稿多了一行，故原稿下标 i 在修复稿里的位置要按插入点右移。
    def _original_index_to_new(i: int) -> int:
        return i + 1 if i >= raw_idx else i

    # 同批只允许目标行改写（故障行，非已通过行）；speaker 一律沿用原行。
    # 注意：改写必须取自**右移后**对应的那一行，否则会把补行的文本抄进目标行；
    # 但写入要用**原稿下标**（此时还没执行 insert，scoped_rows 仍是原长度）。
    allowed_text: dict[int, str] = {}
    for line_no in sorted(target_lines):
        i = line_no - 1
        if not (0 <= i < len(original_rows)):
            continue
        old_item = original_rows[i]
        if not isinstance(old_item, dict):
            continue
        pos = _original_index_to_new(i)
        if pos == raw_idx or not (0 <= pos < len(repaired_rows)):
            continue
        cand = repaired_rows[pos]
        if not isinstance(cand, dict):
            continue
        if str(cand.get("speaker") or "").strip() != str(
            old_item.get("speaker") or ""
        ).strip():
            continue
        old_line = str(old_item.get("line") or "").strip()
        new_line = str(cand.get("line") or "").strip()
        if new_line and new_line != old_line:
            allowed_text[i] = new_line
            scoped_rows[i]["line"] = new_line
    scoped_rows.insert(raw_idx, {"speaker": inserted_speaker, "line": inserted_line})

    out = dict(original)
    out["dialogue"] = scoped_rows
    if st_final:
        out["story_type"] = st_final
    out, _ = patch_sanitize_pad_suffix(out)
    out, _ = patch_sanitize_pad_particles(out)

    # sanitize 若动了行数，整条补拍不可信，直接放弃。
    cleaned_rows = out.get("dialogue")
    if not isinstance(cleaned_rows, list) or len(cleaned_rows) != len(scoped_rows):
        return dict(original), False

    # 逐行回滚：非目标行逐字还原；目标行只保留允许的 line 文本、沿用原 speaker。
    for i, old_item in enumerate(original_rows):
        if not isinstance(old_item, dict):
            continue
        if i in allowed_text:
            continue
        cleaned_rows[_original_index_to_new(i)] = dict(old_item)
    for i, new_line in allowed_text.items():
        old_item = original_rows[i]
        if not isinstance(old_item, dict):
            continue
        cur_item = cleaned_rows[_original_index_to_new(i)]
        if not isinstance(cur_item, dict):
            continue
        if not str(cur_item.get("line") or "").strip():
            cur_item["line"] = old_item.get("line")
        cur_item["speaker"] = old_item.get("speaker")
    return out, True


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


    if isinstance(exc, GoldChatSemanticBlocked):
        scope = _semantic_repair_scope_block(exc, chat)
        allow_insert = bool(_semantic_missing_beat_entries(exc))
        return "\n".join(
            part
            for part in (
                format_semantic_acceptance_feedback(
                    str(exc), allow_insert=allow_insert
                ),
                scope,
                metrics,
                "只在目标行内完成修复并维持现有字数/结构硬约束；不得靠改其它行补长度。",
            )
            if part
        )

    if isinstance(exc, GoldChatLocalDuplicateBlocked):
        targets = sorted(_duplicate_repair_target_lines(exc, chat))
        scope = ""
        if targets:
            labels = "、".join(f"第{no}句" for no in targets)
            scope = (
                f"\n【重复定点范围】只允许改{labels}的台词文本；"
                "其余句与全部 speaker 必须保持原样。"
                "目标句必须推进新信息，且不得与任何其它句同义复读。"
            )
        return (
            f"{format_semantic_acceptance_feedback(str(exc))}{scope}\n{metrics}\n{hint}"
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
    if str(st_final or "").strip().upper() == "I":
        from app.services.daily_story.story_types.i.patch import (
            patch_i_acknowledge_apology,
            patch_i_collapse_repeated_claim_questions,
            patch_i_ground_opening_quote_assertion,
            patch_i_parent_acknowledge_child_feeling,
            patch_i_parent_accept_child_pause,
            patch_i_repair_mirror_parent_question,
            patch_i_strip_self_action_narration,
            patch_i_soften_win_after_concession,
        )

        patch_i_repair_mirror_parent_question(out)
        patch_i_strip_self_action_narration(out)
        patch_i_ground_opening_quote_assertion(out)
        patch_i_acknowledge_apology(out)
        patch_i_parent_acknowledge_child_feeling(out)
        patch_i_parent_accept_child_pause(out)
        patch_i_collapse_repeated_claim_questions(out)
        patch_i_soften_win_after_concession(out)
    return out


def _duplicate_orphan_line(
    lines: list[int],
    chat: dict[str, Any] | None,
) -> int | None:
    """K-B：重复组里「删掉后末段不变量仍成立」的那句优先当改写目标。

    孤儿接住句（早于最后一次邀约的同义句）删掉不破坏「孩子自行恢复」，
    而承载句删掉会让硬卡失效。改写前者才能既消重又保住收束。
    """
    if not isinstance(chat, dict):
        return None
    rows = chat.get("dialogue")
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_CHILD_SELF_RESOLVE,
        k_close_mode_from_story,
    )
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    if k_close_mode_from_story(chat) != K_B_CHILD_SELF_RESOLVE:
        return None
    speakers: list[str] = []
    texts: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            return None
        speakers.append(str(item.get("speaker") or ""))
        texts.append(str(item.get("line") or ""))
    if not kid_self_resolve_in_tail(speakers, texts):
        # 不变量本来就没落位：不做特殊选择，交给默认策略。
        return None
    orphans: list[int] = []
    for no in lines:
        idx = no - 1
        if idx < 0 or idx >= len(rows):
            continue
        kept_speakers = [sp for i, sp in enumerate(speakers) if i != idx]
        kept_texts = [tx for i, tx in enumerate(texts) if i != idx]
        if kid_self_resolve_in_tail(kept_speakers, kept_texts):
            orphans.append(no)
    return orphans[0] if len(orphans) == 1 else None


def _duplicate_repair_target_lines(
    exc: GoldChatLocalDuplicateBlocked,
    chat: dict[str, Any] | None = None,
) -> set[int]:
    """每组重复只允许改一句：优先改不承载末段不变量的孤儿句；行号 1-based。"""
    targets: set[int] = set()
    for item in exc.issues:
        raw_lines = item.get("lines")
        if not isinstance(raw_lines, list):
            continue
        lines = [
            int(no)
            for no in raw_lines
            if isinstance(no, int) and not isinstance(no, bool) and int(no) > 0
        ]
        if len(lines) >= 2:
            targets.add(_duplicate_orphan_line(lines, chat) or max(lines))
    return targets


def _freeze_duplicate_repair_scope(
    original: dict[str, Any],
    repaired: dict[str, Any],
    *,
    target_lines: set[int],
) -> dict[str, Any]:
    """重复定点修只落目标行文本；冻结其它对白以及所有 speaker。"""
    original_rows = original.get("dialogue")
    repaired_rows = repaired.get("dialogue")
    if not isinstance(original_rows, list) or not isinstance(repaired_rows, list):
        return repaired

    frozen_rows: list[Any] = []
    for idx, old_item in enumerate(original_rows, 1):
        if not isinstance(old_item, dict):
            frozen_rows.append(old_item)
            continue
        row = dict(old_item)
        if idx in target_lines and idx <= len(repaired_rows):
            new_item = repaired_rows[idx - 1]
            if isinstance(new_item, dict):
                new_line = str(new_item.get("line") or "").strip()
                if new_line:
                    row["line"] = new_line
        frozen_rows.append(row)

    out = dict(repaired)
    out["dialogue"] = frozen_rows
    return out


def _final_acceptance_row_context(
    chat: dict[str, Any],
    row: dict[str, Any],
) -> tuple[list[Any] | None, list[Any] | None, int, str]:
    """终检共用的契约上下文：beat_chain、seed、妈妈句上限、类型。"""
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
    dialogue_seed_raw = payload.get("dialogue_seed")
    dialogue_seed = dialogue_seed_raw if isinstance(dialogue_seed_raw, list) else None
    # 妈妈额度走 resolve_parent_lines_budget：含「按拍数抬额」与「只到一位家长时
    # 另一位让额度」两层。直接读契约原值会让硬卡比实际可用额度更紧（#138：
    # 契约 3、实际应为 4），妈妈末拍被判超限裁掉，终检随即报缺前提。
    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom_max, _dad_max, _parent_max = resolve_parent_lines_budget(
        scene_contract,
        mom_lines_max=scene_contract.get("mom_lines_max"),
    )
    if not mom_max:
        cached = chat.get("_gold_chat_mom_lines_max")
        if cached is not None:
            try:
                mom_max = max(0, int(cached))
            except (TypeError, ValueError):
                pass
    contract_type = str(
        scene_contract.get("story_type")
        or row.get("structure_type")
        or chat.get("story_type")
        or ""
    ).strip()
    return beat_chain, dialogue_seed, mom_max, contract_type


def apply_final_acceptance_local_patches(
    chat: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """终检语义审核前本地 patch，与审核行号对齐的稿件基线。"""
    from app.services.gold_story.gold_chat.patch import (
        _perbeat_mode,
        apply_kinship_label_patch,
        apply_opening_causality_local_patch,
        trim_parent_quota_overflow,
    )
    from app.services.gold_story.gold_chat.validate import (
        apply_n_beat_role_speaker_align,
    )

    if _perbeat_mode():
        # 逐拍稿的角色与拍序由生成器负责。终检前插入 seed 或重挂角色会改变
        # 待验稿的因果关系；保留原稿给统一校验/语义审核，只规范称谓。
        patched, kin_patched = apply_kinship_label_patch(chat)
        if kin_patched:
            logger.info(
                "[GOLD_CHAT] final acceptance kinship patch: %s",
                "；".join(kin_patched),
            )
        return patched

    beat_chain, dialogue_seed, mom_max, contract_type = _final_acceptance_row_context(
        chat,
        row,
    )
    patched, n_role_patched = apply_n_beat_role_speaker_align(
        chat,
        beat_chain=beat_chain,
        structure_type=contract_type,
    )
    if n_role_patched:
        logger.info("[GOLD_CHAT] final acceptance N beat role speaker align")

    patched, kin_patched = apply_kinship_label_patch(patched)
    if kin_patched:
        logger.info(
            "[GOLD_CHAT] final acceptance kinship patch: %s",
            "；".join(kin_patched),
        )

    payload_raw = row.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    contract_raw = payload.get("scene_contract")
    contract: dict[str, Any] = (
        contract_raw if isinstance(contract_raw, dict) else {}
    )
    from app.services.gold_story.scene import trim_supplemental_kid_dialogue

    # 裁句之前记一份：这两步会整行删孩子/家长台词，删完若不重跑硬卡，
    # 首轮终检就通过的稿子可能被裁到「对白句数须≥12 / 正文总字数须≥」之下
    # 直接导出。这里只在裁完仍守住下限时才采纳裁句，否则整步回滚。
    _floor_snapshot = dict(patched)
    patched, witness_trimmed = trim_supplemental_kid_dialogue(
        patched,
        contract=contract,
    )
    if witness_trimmed:
        logger.info(
            "[GOLD_CHAT] final acceptance witness trim: %s",
            "；".join(witness_trimmed),
        )

    patched, quota_notes = trim_parent_quota_overflow(
        patched,
        beat_chain=beat_chain,
        mom_lines_max=mom_max,
    )
    if witness_trimmed or quota_notes:
        from app.services.gold_story.gold_chat.validate import (
            gold_chat_effective_min_chars,
        )
        from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

        _dialogue_now = patched.get("dialogue") or []
        _lines_now = len(_dialogue_now) if isinstance(_dialogue_now, list) else 0
        _chars_now = dialogue_total_chars(patched)
        if (
            _lines_now < CHAT_LINE_COUNT_MIN
            or _chars_now < gold_chat_effective_min_chars(_dialogue_now)
        ):
            logger.warning(
                "[GOLD_CHAT] 裁句后跌破下限（lines=%s chars=%s），回滚本次裁句",
                _lines_now,
                _chars_now,
            )
            patched = _floor_snapshot
            witness_trimmed = []
            quota_notes = []
    if quota_notes:
        logger.info(
            "[GOLD_CHAT] final acceptance parent quota: %s",
            "；".join(quota_notes),
        )

    patched, opening_patched = apply_opening_causality_local_patch(
        patched,
        beat_chain=beat_chain,
        mom_lines_max=mom_max,
        dialogue_seed=dialogue_seed,
    )
    if opening_patched:
        logger.info("[GOLD_CHAT] final acceptance opening causality local patch")
    return patched


def _export_repair_dialogue_base(
    current: dict[str, Any],
    row: dict[str, Any],
    exc: BaseException,
) -> dict[str, Any]:
    """定点修稿须与终检本地 patch 后送审稿对齐（语义/重复共用）。"""
    if isinstance(exc, (GoldChatSemanticBlocked, GoldChatLocalDuplicateBlocked)):
        return apply_final_acceptance_local_patches(current, row)
    return current


def run_gold_chat_final_acceptance(
    chat: dict[str, Any],
    row: dict[str, Any],
    *,
    sid: str,
    preserve_dialogue: bool = False,
) -> dict[str, Any]:
    """补字/改 speaker 完成后统一终验；未过则抛错，不写导出文件。"""
    if "_gold_link_review_raw" in row:
        chat = {**chat, "source_link_review": True, "source_raw": row["_gold_link_review_raw"]}
    if row.get("_gold_source_line_plan"):
        chat = {**chat, "gold_source_line_plan": deepcopy(row["_gold_source_line_plan"]),
                "gold_n_expression_contract": deepcopy(row.get("_gold_n_expression_contract")),
                "source_raw": str(row.get("_gold_source_raw") or "")}
    from app.services.daily_story.quality import (
        gold_story_review_contract,
        stamp_gold_chat_acceptance_quality,
    )
    from app.services.daily_story.review import (
        collect_escalation_chatter_signals,
        collect_export_blocking_local_issues,
        format_export_blocking_issue_summary,
        partition_llm_export_blocking_issues,
        run_export_semantic_review,
    )

    adaptation = (row.get("payload") or {}).get("gold_chat_adaptation")
    if adaptation is not None:
        chat = {**chat, "source_raw": gold_chat_source_text(row), "source_link_review": True,
                "source_adaptation": {**deepcopy(adaptation), "original_story_raw": str(
                    row.get("story_raw") or (row.get("payload") or {}).get("story_raw") or "")}}
    theme = str(
        row.get("title") or chat.get("scene_title") or chat.get("key") or sid
    ).strip()
    beat_chain, dialogue_seed, mom_max, _contract_type = _final_acceptance_row_context(
        chat,
        row,
    )

    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        format_opening_causality_hard_error,
    )

    if not preserve_dialogue:
        chat = apply_final_acceptance_local_patches(chat, row)
    from app.services.gold_story.gold_chat.patch import remap_chat_kinship_metadata

    chat, theme, _ = remap_chat_kinship_metadata(chat, theme=theme)

    # 终检前最后一道确定性契约补丁（幂等）：重掷/LLM 修稿可能把旁观角色、
    # 词槽或追问归属写回去，终检只审补丁后的文本（专家口径：自动管线补丁，
    # 不是手改导出稿）。
    # story_type 可能只存在于 row（chat 里没有这个字段），
    # 直接用 chat.get 会让这段前置补丁**永远不执行**（#87 实测：
    # 日志里 pre-final N contract patch 一次都没出现，旧对白原样进终检）。
    _st_for_patch = (
        str(chat.get("story_type") or row.get("story_type") or "")
        .strip()
        .upper()
    )
    from app.services.gold_story.gold_chat.patch import (
        _perbeat_mode,
        apply_n_contract_local_patches,
    )

    if _st_for_patch == "N" and not _perbeat_mode() and not preserve_dialogue:
        if not chat.get("story_type"):
            chat["story_type"] = "N"
        chat, pre_final_notes = apply_n_contract_local_patches(
            chat,
            beat_chain=beat_chain,
            dialogue_seed=dialogue_seed,
            mom_lines_max=mom_max,
        )
        if pre_final_notes:
            logger.info(
                "gold_chat pre-final N contract patch: %s",
                "；".join(pre_final_notes),
            )

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
        message = "终检本地硬伤：" + "；".join(parts)
        if error_type is GoldChatLocalDuplicateBlocked:
            raise GoldChatLocalDuplicateBlocked(message, issues=local_block)
        raise error_type(message)

    review = run_export_semantic_review(theme, chat, beat_chain=beat_chain)
    source_failures = [item for item in review.issues if item.get("source_audit_failed")]
    if review.completed and source_failures:
        raise GoldChatSemanticBlocked(
            "终检素材/接话不合格：" + "；".join(f"第{it['lines']}句：{it['desc']}" for it in source_failures),
            issues=source_failures,
        )
    first_review_error = review.error
    if not review.completed:
        # 审核执行失败只重审同一候选一次；不重新归一化、不耗用内容修稿额度。
        from app.services.llm.llm_mgr import remaining_llm_time

        remaining_llm_time(reserve=8.0)
        review = run_export_semantic_review(theme, chat, beat_chain=beat_chain)
        source_failures = [item for item in review.issues if item.get("source_audit_failed")]
        if review.completed and source_failures:
            raise GoldChatSemanticBlocked(
                "终检素材/接话不合格：" + "；".join(f"第{it['lines']}句：{it['desc']}" for it in source_failures),
                issues=source_failures,
            )
    review = _demote_verbatim_source_quirks(
        review, chat, source_raw=gold_chat_source_text(row)
    )
    review = _demote_nonattributed_citation_issues(review, chat)
    if not review.completed:
        raise GoldChatAcceptanceIncomplete(
            "；".join(dict.fromkeys(x for x in (first_review_error, review.error) if x))
            or "语义审核未完成（LLM 超时或解析失败），已保留上次导出稿",
            candidate=chat,
        )

    # 把契约链一并带上：语义豁免（怪词/补词）需要从 story 里读拍链，
    # chat 本身没有这个字段。
    _chat_for_review = dict(chat)
    _chat_for_review.setdefault("beat_chain", beat_chain)
    _chat_for_review.setdefault("story_type", _st_for_patch or "N")
    llm_block, bad_evidence = partition_llm_export_blocking_issues(
        review.issues,
        _chat_for_review,
        beat_chain=beat_chain,
    )
    if bad_evidence:
        # 残留兜底：观感类证据不可核验的条目已在审查侧降级并从 issues 剔除，
        # 这里只可能是高风险类（事实/称谓/价值观）或弱核验不通过的条目。
        parts = [
            format_export_blocking_issue_summary(it)
            for it in bad_evidence[:5]
        ]
        raise GoldChatAcceptanceIncomplete(
            "审核证据无效（"
            + "；".join(parts)
            + "），已保留上次导出稿",
            candidate=chat,
        )
    if llm_block:
        parts = [
            format_export_blocking_issue_summary(it)
            for it in llm_block[:5]
        ]
        _debug_dump_rejected_chat(chat, sid)
        raise GoldChatSemanticBlocked(
            "终检语义硬伤：" + "；".join(parts),
            issues=llm_block,
        )

    signals = collect_escalation_chatter_signals(chat)
    stamp_gold_chat_acceptance_quality(
        chat,
        review_issues=review.issues,
        humor=review.humor,
        chatter_signals=signals,
        semantic_pass=True,
        review_contract=gold_story_review_contract(row, chat),
        downgraded_issues=review.downgraded,
    )
    if review.downgraded:
        logger.warning(
            "[GOLD_CHAT] final acceptance ok with %s downgraded issue(s) "
            "needing manual spotcheck %s",
            len(review.downgraded),
            sid,
        )
    logger.info(
        "[GOLD_CHAT] final acceptance ok %s issues=%s humor=%s",
        sid,
        len(review.issues),
        bool(review.humor),
    )
    return chat


def _debug_dump_rejected_chat(chat: dict[str, Any], sid: str) -> None:
    """GOLD_CHAT_DEBUG_DUMP=1 时把被终检拒掉的稿子落盘，便于本地定位语义硬伤。

    生产不设该环境变量时是空操作。
    """
    if not os.environ.get("GOLD_CHAT_DEBUG_DUMP"):
        return
    path = Path("/tmp") / f"gold_chat_debug_{sid or 'unknown'}.json"
    try:
        path.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.warning("[GOLD_CHAT] debug dump failed %s", path)


def _try_local_premise_align(
    current: dict[str, Any],
    dialogue_seed: list[Any] | None,
    validate_chat,
    *,
    only_speakers: set[str] | None = None,
) -> dict[str, Any] | None:
    """终检缺前提时先试确定性 seed 补拍；不合法就不动。

    缺前提的根因常是 seed 里本就有的前提拍没落地（生成遗漏），属机械缺陷：
    交由 LLM 语义修稿既烧预算又常补不出（专家裁决：机械问题机械修，不占语义预算）。
    这里用与 expand 前置对齐同一套 ``patch_seed_premise_align``，只在补出的稿子
    仍通过硬校验时采用；否则返回 ``None``，保持原候选不动。
    ``only_speakers`` 是终检点名的缺拍说话人，用于把补拍额度锁在真正缺的角色上。
    """
    if not dialogue_seed:
        return None
    from app.services.gold_story.gold_chat.convert import patch_seed_premise_align

    patched, changed = patch_seed_premise_align(
        dict(current),
        dialogue_seed=dialogue_seed,
        only_speakers=only_speakers,
    )
    if not changed:
        return None
    try:
        _validate_chat_or_repairable(validate_chat, patched)
    except Exception:
        return None
    return patched


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
    from app.services.gold_story.gold_chat.patch import missing_seed_rows
    from app.services.gold_story.gold_chat.repair import (
        GoldChatRepairBudget,
        GoldChatRepairExhausted,
    )

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
    # 结构闸门那一刻的评分快照：失败落库必须用它，不能用 current 里上一次的旧
    # quality（#138：库里候选写着结构 80，报错却是 65，人工确认会被误导）。
    gate_scored: dict[str, Any] | None = None
    # 已**尝试**补过的缺拍（beat 号）：同一拍反复补说明是契约/生成根因，
    # 不是措辞问题，禁止反复插行（专家裁决）。按"尝试"记账而非"成功"，
    # 否则补行被拒（超上限/speaker 不符）时会每轮重试到天荒地老。
    attempted_beats: set[int] = set()
    # 确定性 seed 补拍只试一次：同一候选补过仍判缺前提，说明根因不在「没落地」，
    # 再补只是反复插行（专家裁决：同一拍不重复插行）。
    premise_align_tried = False
    # 拍落地覆盖检查（专家裁决层①）：收尾的旁观反应拍全稿无人引用，既不会触发
    # 「缺前提」，也没有后继锚点，会在终检静默丢失。这里不等引用，按 seed 覆盖
    # 确定性补回一次；补不动就不动（不占语义预算，也不插必挂的行）。
    if dialogue_seed:
        if missing_seed_rows(current.get("dialogue"), dialogue_seed):
            covered = _try_local_premise_align(current, dialogue_seed, validate_chat)
            if covered is not None:
                current = covered
                premise_align_tried = True
                logger.info("gold_chat final beat coverage close applied")
    while True:
        gate_scored = None
        try:
            try:
                _validate_chat_or_repairable(validate_chat, current)
            except GoldChatValidationRepairableError as validation_exc:
                current2, local_closed = _try_final_hard_floor_one_char_close(
                    current,
                    validation_exc,
                )
                if not local_closed:
                    raise
                current = current2
                logger.info(
                    "gold_chat final hard-floor local close chars=%s",
                    dialogue_total_chars(current),
                )
                _validate_chat_or_repairable(validate_chat, current)
            # 拍落地覆盖（专家裁决层①/②）：整场缺席的角色拍必须当硬伤处理，
            # 否则无人引用的收尾拍（家长反应）会在终检静默通过。缺口进结构化
            # 反馈走重掷，而不是无声丢掉。
            missing_coverage = missing_seed_rows(
                current.get("dialogue"), dialogue_seed
            ) if dialogue_seed else []
            if missing_coverage:
                raise GoldChatSemanticBlocked(
                    "终检语义硬伤：拍未落地："
                    + "；".join(f"{sp}（{text}）" for sp, text in missing_coverage),
                    issues=[
                        {
                            "kind": "缺前提",
                            "desc": f"整场未见{sp}的回合（{text}），该拍没落地",
                            "fix": (
                                f"由{sp}补一个有推进的台词回合（{text}）；"
                                "不许用旁白或空应答占行"
                            ),
                            "missing_beat": {"intent": text, "speaker": sp},
                        }
                        for sp, text in missing_coverage
                    ],
                )
            # 终态连说兜底：行序类缺陷机械可修，必须在评分对象定稿前拆开，
            # 否则会白烧一轮 LLM 修稿预算（#138 实测）。
            # 必须带上 seed：插句优先用 seed 里的真实素材，否则会退回态度词库，
            # 而词库句不含剧情、必被语义终检判「答非所问」。
            _tc_chain, _tc_seed, _tc_mom, _tc_type = _final_acceptance_row_context(
                current, row
            )
            current = _try_terminal_sibling_adjacency_close(
                current,
                validate_chat=validate_chat,
                beat_chain=_tc_chain,
                dialogue_seed=_tc_seed,
            )
            scored = attach_score(current, row)
            gate_scored = scored
            struct = _gate_structure_or_raise(gate_score, scored)
            current = scored
            accepted = run_gold_chat_final_acceptance(current, row, sid=sid)
            return accepted, int(struct)
        except GoldChatAcceptanceIncomplete:
            raise
        except BaseException as exc:
            if not _is_export_repairable(exc):
                raise
            # 逐拍填词模式：稿子是按拍写出来的，说话人与拍序由骨架锁死；
            # 这里的 LLM 整篇修稿会重写句子并插入池子对
            # （「你还真是照这个道理认真想的？」/「当然，我刚才就是这么认真回答的。」），
            # 反而把 12 句 232 字的合格稿改成 15 句 277 字的错位稿
            # （#138 实测：终检报引用无据/旁白/错位/重复六条）。
            # 逐拍模式宁可整条 draft 重掷，也不接受整篇 LLM 修稿。
            from app.services.gold_story.gold_chat.patch import _perbeat_mode

            if _perbeat_mode():
                raise
            if (
                not premise_align_tried
                and isinstance(exc, GoldChatSemanticBlocked)
                and _semantic_missing_beat_entries(exc)
            ):
                # 机械缺陷（seed 前提拍没落地）先做确定性补拍：不消耗语义预算，
                # 补出的稿子若仍不合法则放弃，落回原有预算修稿/重掷链路。
                premise_align_tried = True
                # 只补「整场缺席」的角色拍。说话人在正文里已经开过口、却仍缺某一拍，
                # 说明生成时读过整条 seed 却没写这一拍——即这条素材它判断不可用
                # （源稿损坏时，这条恰恰是 ASR/OCR 的乱码原文）。此时把 seed 原文
                # 硬塞回对白，等于用机械手段推翻那个判断，还必然被语义终检判语病
                # （#138 实测：乱码 seed 被本地补回 → 反复报语病 → 预算耗尽）。
                absent = (
                    {
                        sp
                        for sp, _text in missing_seed_rows(
                            current.get("dialogue"), dialogue_seed
                        )
                    }
                    if dialogue_seed
                    else set()
                )
                retry_speakers = _semantic_missing_beat_speakers(exc) & absent
                relocated: dict[str, Any] | None = None
                if retry_speakers:
                    relocated = _try_local_premise_align(
                        current,
                        dialogue_seed,
                        validate_chat,
                        only_speakers=retry_speakers,
                    )
                if relocated is not None:
                    current = relocated
                    logger.info(
                        "gold_chat final local premise align applied beats=%s",
                        _semantic_missing_beat_entries(exc),
                    )
                    continue
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
                        pending_base: dict[str, Any] = (
                            gate_scored if gate_scored is not None else current
                        )
                        if gate_scored is None:
                            # 还没走到结构闸门就失败（校验/覆盖/语义先挂）：临门补算一次，
                            # 落库必须是「导致失败的这一刻」的分，而不是上一次的旧快照。
                            try:
                                pending_base = attach_score(dict(current), row)
                            except BaseException:
                                pending_base = current
                        pending: dict[str, Any] = dict(pending_base)
                        raw_pending_quality = pending.get("quality")
                        pending_quality: dict[str, Any] = (
                            dict(raw_pending_quality)
                            if isinstance(raw_pending_quality, dict)
                            else {}
                        )
                        pending_quality["review_status"] = "review_pending"
                        pending_quality["review_failure_reason"] = str(exc)
                        if gate_scored is None:
                            # 分是失败后补算的，不是闸门判定值：显式标源，
                            # 免得人工把校验/语义失败误读成「结构挂了」。
                            pending_quality["structure_score_source"] = (
                                "recomputed_pre_gate"
                            )
                        pending["quality"] = pending_quality
                        raise GoldChatRepairExhausted(
                            stage="final_acceptance",
                            reason=str(exc),
                            candidate=pending,
                        ) from exc
            elif attempt >= local_max:
                raise
            attempt += 1
            last_err = str(exc).strip()
            repair_base = _export_repair_dialogue_base(current, row, exc)
            prompt = _build_export_repair_feedback(
                exc,
                repair_base,
                row,
                st_final=st_final,
                mom_max=int(mom_max),
            )
            if attempt > 0 and last_err:
                prompt = f"{prompt}\n【上一轮未过】{last_err}"
            lifted = fix_llm(
                repair_base,
                prompt,
                banned_literals=[str(x) for x in banned],
                mom_lines_max=int(mom_max),
            )
            if isinstance(exc, GoldChatSemanticBlocked):
                targets = _semantic_repair_target_lines(exc)
                repaired, scoped_changed = _sanitize_semantic_scoped_repair(
                    repair_base,
                    lifted,
                    target_lines=targets,
                    st_final=st_final,
                    normalize_chat=normalize_chat,
                )
                # 冻结域改不出缺拍时，放行「补拍一行」（仍受上限/speaker/禁旁白约束）
                if not scoped_changed:
                    beat_ids = {
                        int(x["beat"])
                        for x in _semantic_missing_beat_entries(exc)
                        if isinstance(x.get("beat"), int)
                    }
                    if beat_ids and beat_ids <= attempted_beats:
                        # 同一拍上一轮已尝试补过仍被判缺 → 根因在契约/生成，
                        # 再插只会反复缝补，直接放弃本轮补行。
                        logger.info(
                            "gold_chat missing-beat insertion skipped: "
                            "beat already attempted beats=%s",
                            sorted(beat_ids),
                        )
                    else:
                        attempted_beats |= beat_ids
                        inserted_chat, ins_changed = (
                            _apply_semantic_missing_beat_insertion(
                                repair_base,
                                lifted,
                                exc,
                                target_lines=targets,
                                st_final=st_final,
                                normalize_chat=normalize_chat,
                            )
                        )
                        if ins_changed:
                            repaired = inserted_chat
                            scoped_changed = True
                            logger.info(
                                "gold_chat semantic missing-beat insertion accepted "
                                "beats=%s target_lines=%s",
                                _semantic_missing_beat_entries(exc),
                                sorted(targets),
                            )
                logger.info(
                    "gold_chat semantic repair bounded scope target_lines=%s changed=%s",
                    sorted(targets),
                    scoped_changed,
                )
            else:
                repaired = _sanitize_repaired_chat(
                    lifted,
                    st_final=st_final,
                    normalize_chat=normalize_chat,
                    dialogue_seed=dialogue_seed,
                )
                if isinstance(exc, GoldChatLocalDuplicateBlocked):
                    targets = _duplicate_repair_target_lines(exc)
                    if targets:
                        repaired = _freeze_duplicate_repair_scope(
                            repair_base,
                            repaired,
                            target_lines=targets,
                        )
                        logger.info(
                            "gold_chat duplicate repair frozen scope target_lines=%s",
                            sorted(targets),
                        )
            # 只有正文实际变化才做额外回归门；模型原样返回时让主循环正常复验，
            # 避免重复跑同一套纯本地校验。正文一旦变化，若破坏已通过硬条件/结构，
            # 则保留修前候选，不让坏修稿成为下一轮基线。
            if repaired.get("dialogue") != repair_base.get("dialogue"):
                try:
                    _validate_chat_or_repairable(validate_chat, repaired)
                    regression_scored = attach_score(repaired, row)
                    _gate_structure_or_raise(gate_score, regression_scored)
                except BaseException as regression_exc:
                    last_err = f"终检修稿回归：{regression_exc}"
                    if budget is not None:
                        budget.note_failure(last_err)
                    logger.warning(
                        "gold_chat final repair regressed; keep previous candidate reason=%s",
                        regression_exc,
                    )
                    current = repair_base
                    continue
            current = repaired
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
    # 与 validate_chat_hard 同口径：句数达标时字数下限放宽一行（240-24=216）。
    # 写死 240 会把 12 句 233 字的合格稿判成「不够」，再灌 `_K_NATURAL_MID_PAIRS`
    # 池子对（#149 实测：12 句 233 字被垫成 15 句，末段三句全是「不认输/没完」复述）。
    return (
        dialogue_total_chars(chat) < gold_chat_effective_min_chars(dialogue)
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
    from app.services.gold_story.gold_chat.length import (
        _K_NATURAL_MID_PAIRS,
        _pad_line_is_duplicate,
        _pad_safe_insert_bounds,
    )

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
            # 插入点须落在安全区：太靠前会占掉开场因果的槽位，
            # 太靠后会把互顶灌进收束段，破坏已钉好的收场。
            lo, hi = _pad_safe_insert_bounds(len(dialogue))
            insert_at = max(lo, min(parent_i, hi))
            existing = [
                str(x.get("line") or "").strip()
                for x in dialogue
                if isinstance(x, dict)
            ]
            inserted = 0
            for pair in _K_NATURAL_MID_PAIRS:
                if not _k_under_hard_floor(chat) or inserted >= 4:
                    break
                rows = [
                    {"speaker": sp, "line": line}
                    for sp, line in pair
                ]
                # 逐字/归一化/近似三级判重，避免把只差语气词的同义句又灌一遍
                if any(
                    _pad_line_is_duplicate(r["line"], existing) for r in rows
                ):
                    continue
                lo, hi = _pad_safe_insert_bounds(len(dialogue))
                insert_at = max(lo, min(insert_at, hi))
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
                existing.extend(r["line"] for r in rows)
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
            remap_source_kinship,
        )

        payload = cast(dict[str, Any], row.get("payload") or {})
        chat, strip_notes = patch_m2_c_structure(
            chat,
            structure_type=str(row.get("structure_type") or ""),
            mechanism=str(row.get("mechanism") or ""),
            theme=remap_source_kinship(str(row.get("title") or chat.get("scene_title") or "")),
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
    # 同 `_final_acceptance_row_context`：家长额度走 resolve，别照抄契约原值，
    # 否则裁句阶段会比实际可用额度更紧、把合规的家长末句裁掉。
    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom_max, _mm_dad, _mm_parent = resolve_parent_lines_budget(
        scene_contract,
        mom_lines_max=scene_contract.get("mom_lines_max"),
    )
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
