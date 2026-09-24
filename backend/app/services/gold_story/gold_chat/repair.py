"""gold_chat 跨阶段共享修稿预算与候选稿反馈。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GoldChatRepairBudget:
    """扩写 / 精修 / 终检共用修稿次数，不在各层重新计数。"""

    max_repairs: int = 2
    used: int = 0
    last_failure: str = ""

    def consume(self, *, stage: str = "repair", reason: str = "") -> bool:
        if reason:
            self.note_failure(reason)
        if self.used >= max(0, int(self.max_repairs)):
            logger.info(
                "gold_chat repair exhausted stage=%s used=%s remaining=%s reason=%s",
                stage, self.used, self.remaining, self.last_failure,
            )
            return False
        self.used += 1
        logger.info(
            "gold_chat repair consume stage=%s used=%s remaining=%s reason=%s",
            stage, self.used, self.remaining, self.last_failure,
        )
        return True

    @property
    def exhausted(self) -> bool:
        return self.used >= max(0, int(self.max_repairs))

    @property
    def remaining(self) -> int:
        return max(0, int(self.max_repairs) - int(self.used))

    def note_failure(self, msg: str) -> None:
        text = str(msg or "").strip()
        if text:
            self.last_failure = text


class GoldChatRepairExhausted(ValueError):
    """当前候选修稿预算耗尽，不得由扩写重试吞掉。"""

    def __init__(self, *, stage: str, reason: str, candidate: dict[str, Any]) -> None:
        self.stage = stage
        self.candidate = candidate
        super().__init__(f"gold_chat修稿预算耗尽 stage={stage}；{reason}")


class AlignRepairFailure(ValueError):
    """精修阶段结构化失败（勿仅按篇幅归类）。"""

    __slots__ = (
        "stage",
        "validation_errors",
        "align_issues",
        "candidate",
    )

    def __init__(
        self,
        *,
        stage: str,
        validation_errors: list[str],
        align_issues: list[dict[str, Any]],
        candidate: dict[str, Any],
    ) -> None:
        self.stage = str(stage or "align_repair")
        self.validation_errors = list(validation_errors)
        self.align_issues = list(align_issues)
        self.candidate = dict(candidate)
        super().__init__(self.to_message())

    def to_message(self) -> str:
        parts: list[str] = []
        for x in self.align_issues[:4]:
            kind = str(x.get("kind") or "")
            desc = str(x.get("desc") or "").strip()
            parts.append(f"{kind}:{desc}" if desc else kind)
        head = f"align_refine_failed:{'；'.join(parts) if parts else '未对齐'}"
        if self.validation_errors:
            head = f"{head}；{'；'.join(self.validation_errors)}"
        return head

    def to_payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "validation_errors": self.validation_errors,
            "align_issues": self.align_issues,
        }


def collect_candidate_repair_errors(
    candidate: dict[str, Any],
    *,
    mom_lines_max: int,
    banned_literals: list[str] | None = None,
    skip_pad_sanitize: bool = False,
) -> list[str]:
    """基于当前正文收集硬校验与剩余垫字问题（可选先机械清明确垫字）。"""
    from app.services.gold_story.gold_chat.convert import validate_gold_chat
    from app.services.gold_story.gold_chat.pad_stack import apply_clear_pad_sanitize
    from app.services.daily_story.review import (
        collect_pad_stack_issues,
        format_export_blocking_issue_summary,
    )

    story = dict(candidate)
    if not skip_pad_sanitize:
        story, _ = apply_clear_pad_sanitize(story)
    errors: list[str] = []
    try:
        validate_gold_chat(
            story, mom_lines_max=mom_lines_max, banned_literals=banned_literals,
        )
    except ValueError as exc:
        errors.append(str(exc))
    errors.extend(
        format_export_blocking_issue_summary(issue)
        for issue in collect_pad_stack_issues(story)
    )
    return errors


def prepare_candidate_for_acceptance(
    candidate: dict[str, Any],
    *,
    mom_lines_max: int,
    banned_literals: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """先清明确垫字，再验收字数/结构/对齐相关硬错误。"""
    from app.services.gold_story.gold_chat.pad_stack import apply_clear_pad_sanitize

    cleaned, _ = apply_clear_pad_sanitize(dict(candidate))
    errors = collect_candidate_repair_errors(
        cleaned,
        mom_lines_max=mom_lines_max,
        banned_literals=banned_literals,
        skip_pad_sanitize=True,
    )
    return cleaned, errors


def collect_candidate_consecutive_notes(candidate: dict[str, Any]) -> list[str]:
    """连说行号只供修稿参考，是否扣分仍由原有结构评分决定。"""
    notes: list[str] = []
    dialogue = candidate.get("dialogue") or []
    for index in range(1, len(dialogue)):
        previous, current = dialogue[index - 1], dialogue[index]
        if not isinstance(previous, dict) or not isinstance(current, dict):
            continue
        speaker = str(current.get("speaker") or "").strip()
        if (
            speaker in {"灿灿", "昭昭"}
            and speaker == str(previous.get("speaker") or "").strip()
        ):
            notes.append(
                f"第{index}、{index + 1}句同人连说（{speaker}）；"
                "按事件重写衔接，不要直接换说话人"
            )
    return notes


def build_candidate_repair_feedback(
    candidate: dict[str, Any],
    *,
    validation_errors: list[str],
    align_issues: list[dict[str, Any]],
    mom_lines_max: int,
) -> str:
    """精修候选未过 hard 卡时的整体修订指令。"""
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )
    from app.services.gold_story.gold_chat.pad_stack import apply_clear_pad_sanitize
    from app.services.gold_story.gold_chat.prompts import format_align_issues_block

    candidate, _ = apply_clear_pad_sanitize(dict(candidate))
    dialogue = candidate.get("dialogue") or []
    mom_count = sum(
        1
        for item in dialogue
        if isinstance(item, dict) and str(item.get("speaker") or "").strip() == "妈妈"
    )
    total = dialogue_total_chars(candidate)
    metrics = (
        f"当前正文 {total} 字（允许 {DAILY_STORY_BODY_CHARS_MIN}–"
        f"{DAILY_STORY_BODY_CHARS_MAX}）；"
        f"妈妈 {mom_count} 句（上限 {max(0, int(mom_lines_max))}）。"
    )
    align_block = format_align_issues_block(align_issues) if align_issues else "（无）"
    errors = collect_candidate_repair_errors(
        candidate, mom_lines_max=mom_lines_max, skip_pad_sanitize=True,
    )
    previous_errors = [error for error in dict.fromkeys(validation_errors) if error not in errors]
    notes = collect_candidate_consecutive_notes(candidate)
    val_txt = "；".join(errors) if errors else "（无）"
    parts = [
        "【精修候选·整体修订】",
        metrics,
        f"本轮失败：{'；'.join(previous_errors) or '见当前校验'}",
        f"当前硬校验与垫字问题：{val_txt}",
        f"连说提示（按结构分门控）：{'；'.join(notes) or '（无）'}",
        f"结构扣分：{(candidate.get('quality') or {}).get('cons') or []}",
        "类型/事件要求：",
        align_block,
        "保留开场触发与角色归属；压缩重复收场或重复含义；"
        "禁止换 speaker 凑额度、禁止语气词凑字。",
    ]
    if total < DAILY_STORY_BODY_CHARS_MIN:
        deficit = int(DAILY_STORY_BODY_CHARS_MIN) - int(total)
        parts.append(
            f"缺 {deficit} 字：通过角色说出口的具体回应补充事件信息，"
            "禁止旁白、动作说明、括号描述；"
            "禁止追加呢呀吧或「好不好呀」等语气词凑字。"
        )
    return "\n".join(parts)


def _is_body_chars_shortage_only_text(msg: str) -> bool:
    """仅正文总字数不足（不含句数/单句超长等组合问题）。"""
    text = str(msg or "")
    if "正文总字数须≥" not in text:
        return False
    blocked = (
        "对白句数须≥",
        "dialogue 至少",
        "单句过长",
        "句数",
        "垫字",
        "structure_score:",
        "妈妈台词须",
        "narration_not_speech",
    )
    return not any(token in text for token in blocked)


def is_expand_short_only_repair(
    candidate_errors: list[str],
    *,
    structure_gate_ok: bool,
) -> bool:
    """结构已过线，且唯一问题是正文总字数不足。"""
    if not structure_gate_ok or not candidate_errors:
        return False
    return all(_is_body_chars_shortage_only_text(err) for err in candidate_errors)


def list_short_spot_editable_line_nos(chat: dict[str, Any]) -> list[int]:
    """仅补字：中段姐弟句可扩，首尾与妈妈句冻结。"""
    dialogue = chat.get("dialogue") or []
    if not isinstance(dialogue, list):
        return []
    n = len(dialogue)
    head_frozen = 2 if n > 4 else 1
    tail_frozen = 2 if n > 4 else 1
    editable: list[int] = []
    for index, row in enumerate(dialogue, 1):
        if index <= head_frozen or index > n - tail_frozen:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() in {"昭昭", "灿灿"}:
            editable.append(index)
    return editable


def build_short_only_spot_fix_feedback(
    candidate: dict[str, Any],
    *,
    validation_errors: list[str],
    mom_lines_max: int,
    editable_line_nos: list[int],
) -> str:
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    total = dialogue_total_chars(candidate)
    deficit = max(0, int(DAILY_STORY_BODY_CHARS_MIN) - int(total))
    lines_txt = "、".join(str(n) for n in editable_line_nos[:12]) or "（无）"
    err_txt = "；".join(dict.fromkeys(validation_errors)) or "（无）"
    return "\n".join(
        [
            "【仅补字·定点扩句】",
            f"当前 {total} 字，缺 {deficit} 字；硬下限 {DAILY_STORY_BODY_CHARS_MIN}。",
            f"本轮校验：{err_txt}",
            f"只允许改行号：{lines_txt}（昭昭/灿灿中段句）。",
            "句数、speaker、开场前两句与收束后两句台词冻结，不得改妈妈/爸爸句。",
            "在可改行内用角色当场说出口的互怼/回应补信息，",
            "禁止旁白、动作说明、括号描述、 narration 腔。",
            "禁止新增句、禁止换 speaker、禁止用语气词凑字。",
            f"妈妈句上限 {max(0, int(mom_lines_max))}，不得增加。",
        ],
    )


def _count_parent_lines(chat: dict[str, Any]) -> int:
    dialogue = chat.get("dialogue") or []
    return sum(
        1
        for item in dialogue
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() in {"妈妈", "爸爸"}
    )


def evaluate_repair_candidate_acceptance(
    baseline: dict[str, Any],
    draft: dict[str, Any],
    *,
    row: dict[str, Any],
    mom_lines_max: int,
    banned_literals: list[str] | None = None,
    strict_dialogue_shape: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    """修稿先验收：劣于 baseline 则拒稿并保留上一份候选。"""
    from app.services.daily_story.quality import structure_score_of
    from app.services.gold_story.gold_chat.convert import (
        _attach_gold_chat_structure_score,
        _gate_gold_chat_structure_score,
    )

    base_dialogue = baseline.get("dialogue") or []
    draft_dialogue = draft.get("dialogue") or []
    if strict_dialogue_shape:
        if len(draft_dialogue) != len(base_dialogue):
            return None, "修稿改变了对白句数"
        for old, new in zip(base_dialogue, draft_dialogue, strict=False):
            if not isinstance(old, dict) or not isinstance(new, dict):
                continue
            if str(old.get("speaker") or "").strip() != str(new.get("speaker") or "").strip():
                return None, "修稿改变了 speaker 归属"

    mom_max = max(0, int(mom_lines_max))
    base_mom = _count_parent_lines(baseline)
    draft_scored = _attach_gold_chat_structure_score(dict(draft), row)
    draft_mom = _count_parent_lines(draft_scored)
    if draft_mom > mom_max:
        return None, f"修稿后妈妈/家长句 {draft_mom} 句，超过上限 {mom_max}"
    if draft_mom > base_mom:
        return None, f"修稿增加了家长句（{base_mom}→{draft_mom}）"

    base_struct = int(structure_score_of(baseline.get("quality") or {}) or 0)
    try:
        _gate_gold_chat_structure_score(draft_scored)
    except ValueError as exc:
        return None, str(exc)
    draft_struct = int(structure_score_of(draft_scored.get("quality") or {}) or 0)
    if base_struct and draft_struct < base_struct:
        return None, f"修稿结构分退回（{base_struct}→{draft_struct}）"

    errors = collect_candidate_repair_errors(
        draft_scored,
        mom_lines_max=mom_max,
        banned_literals=banned_literals,
        skip_pad_sanitize=False,
    )
    hard = [
        e
        for e in errors
        if "narration_not_speech" in e
        or ("妈妈台词须" in e and "当前" in e)
    ]
    if hard:
        return None, "；".join(hard[:3])
    return draft_scored, ""
