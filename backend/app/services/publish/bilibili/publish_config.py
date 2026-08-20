"""B 站投稿页统一配置（分区、话题、标签、创作声明等）。"""

from __future__ import annotations

from typing import Any

import requests

from app.services.publish.bilibili.tags import (
    CHAT_FIXED_TAGS,
    resolve_activity_tag,
    resolve_activity_topic,
)
from app.services.publish.bilibili.tid import (
    CHAT_PIPELINE,
    describe_publish_partition,
    resolve_neutral_mark,
)


def describe_publish_config(
    pipeline: str | None,
    *,
    settings: Any | None = None,
    http: requests.Session | None = None,
) -> dict[str, Any]:
    """返回流水线投稿将使用的配置快照（供发布页展示与投稿对齐）。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    pipe = (pipeline or "").strip() or "standard"
    payload: dict[str, Any] = {
        "pipeline": pipe,
        "partition": describe_publish_partition(pipe, settings=cfg),
        "neutral_mark": resolve_neutral_mark(pipe),
        "copyright": 1,
        "topic": None,
        "fixed_tags": None,
    }
    if pipe != CHAT_PIPELINE:
        return payload

    activity_name = resolve_activity_tag(settings=cfg)
    topic: dict[str, Any] = {
        "name": activity_name,
        "topic_id": None,
        "mission_id": None,
    }
    if http is not None:
        resolved = resolve_activity_topic(http, activity_name)
        if resolved:
            topic["topic_id"] = resolved.get("topic_id")
            topic["mission_id"] = resolved.get("mission_id")
    payload["topic"] = topic
    payload["fixed_tags"] = list(CHAT_FIXED_TAGS)
    return payload
