"""gold_chat 跨阶段共享修稿预算与候选稿反馈。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldChatRepairBudget:
    """扩写 / 精修 / 终检共用修稿次数，不在各层重新计数。"""

    max_repairs: int = 2
    used: int = 0
    last_failure: str = ""

    def consume(self) -> bool:
        if self.used >= max(0, int(self.max_repairs)):
            return False
        self.used += 1
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
    val_txt = "；".join(validation_errors) if validation_errors else "（无）"
    parts = [
        "【精修候选·整体修订】",
        metrics,
        f"hard 校验：{val_txt}",
        "类型/事件要求：",
        align_block,
        "保留开场触发与角色归属；压缩重复收场或重复含义；"
        "禁止换 speaker 凑额度、禁止语气词凑字。",
    ]
    return "\n".join(parts)
