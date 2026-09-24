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
) -> list[str]:
    """基于当前正文同时收集硬校验与垫字问题，不修改稿子。"""
    from app.services.gold_story.gold_chat.convert import validate_gold_chat
    from app.services.daily_story.review import (
        collect_pad_stack_issues,
        format_export_blocking_issue_summary,
    )

    errors: list[str] = []
    try:
        validate_gold_chat(
            candidate, mom_lines_max=mom_lines_max, banned_literals=banned_literals,
        )
    except ValueError as exc:
        errors.append(str(exc))
    errors.extend(
        format_export_blocking_issue_summary(issue)
        for issue in collect_pad_stack_issues(candidate)
    )
    return errors


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
    from app.services.gold_story.gold_chat.prompts import format_align_issues_block

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
    errors = collect_candidate_repair_errors(candidate, mom_lines_max=mom_lines_max)
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
    return "\n".join(parts)
