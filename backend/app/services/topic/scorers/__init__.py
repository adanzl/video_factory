"""按大分类调度选题打分。"""

from __future__ import annotations

from app.services.topic.catalog import (
    CATEGORY_CURRENT,
    CATEGORY_HISTORY,
    resolve_category,
)
from app.services.topic.scorers.base import SCORE_THRESHOLD, ScoreResult
from app.services.topic.scorers.current_affairs import score_current_affairs
from app.services.topic.scorers.history_mystery import score_history
from app.services.topic.scorers.science import score_science


def score_title(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
    hook: str | None = None,
) -> ScoreResult:
    resolved = resolve_category(category)
    if resolved == CATEGORY_HISTORY:
        return score_history(title, template=template, hook=hook)
    if resolved == CATEGORY_CURRENT:
        return score_current_affairs(
            title, category=resolved, template=template, hook=hook
        )
    return score_science(title, category=resolved, template=template, hook=hook)


def status_from_score(result: ScoreResult) -> str:
    if result.rejected_reason and result.total < SCORE_THRESHOLD:
        return "rejected"
    return "queued"


__all__ = ["SCORE_THRESHOLD", "ScoreResult", "score_title", "status_from_score"]
