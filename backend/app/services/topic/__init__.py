"""选题域：配置、业务、提示词与打分。"""

from app.services.topic.catalog import (
    CATEGORY_CURRENT,
    CATEGORY_HISTORY,
    CATEGORY_SCIENCE,
    TOPIC_CATEGORIES,
    catalog_for_api,
    normalize_category,
    resolve_category,
)
from app.services.topic.topic_mgr import (
    SCORE_THRESHOLD,
    ScoreResult,
    score_title,
    status_from_score,
    topic_mgr,
)

__all__ = [
    "CATEGORY_CURRENT",
    "CATEGORY_HISTORY",
    "CATEGORY_SCIENCE",
    "SCORE_THRESHOLD",
    "ScoreResult",
    "TOPIC_CATEGORIES",
    "catalog_for_api",
    "normalize_category",
    "resolve_category",
    "score_title",
    "status_from_score",
    "topic_mgr",
]
