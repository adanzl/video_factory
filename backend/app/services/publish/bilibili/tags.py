"""B 站投稿标签与活动话题。"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.services.publish.bilibili.tid import CHAT_PIPELINE

logger = logging.getLogger(__name__)

TOPIC_SEARCH_URL = "https://member.bilibili.com/x/vupre/web/topic/search"

CHAT_FIXED_TAGS = (
    "姐弟日常",
    "生活记录",
    "亲子日常",
    "搞笑对话",
    "育儿",
    "家庭搞笑",
    "儿童对话",
)

DEFAULT_ACTIVITY_TAG = "闪闪发光的家庭日"


def normalize_tags(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip().lstrip("#").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        tags.append(text[:20])
        if len(tags) >= 10:
            break
    return tags


def _clean_tag(text: str, *, max_len: int = 20) -> str:
    return str(text or "").strip().lstrip("#").strip()[:max_len]


def resolve_theme_tag(job: dict[str, Any]) -> str:
    """chat 优先取日常故事 key，否则回退标题短词。"""
    from app.repositories import repo_daily_story
    from app.utils.job_info import parse_job_info

    info = parse_job_info(job.get("info"))
    daily_story_id = info.get("daily_story_id")
    if daily_story_id:
        story = repo_daily_story.get_story(int(daily_story_id))
        story_content = story.get("story") if isinstance(story.get("story"), dict) else {}
        key = _clean_tag(str(story_content.get("key") or ""))
        if key:
            return key
    title = _clean_tag(str(job.get("title") or ""))
    if title:
        return title[:8]
    return "日常"


def resolve_activity_tag(*, settings: Any | None = None) -> str:
    from app.config import get_settings

    cfg = settings or get_settings()
    tag = _clean_tag(getattr(cfg, "bili_activity_tag", DEFAULT_ACTIVITY_TAG))
    return tag or DEFAULT_ACTIVITY_TAG


def resolve_activity_topic(
    http: requests.Session,
    keywords: str,
    *,
    timeout: float = 20,
) -> dict[str, Any] | None:
    """按活动名搜索 B 站话题，返回 topic_id / mission_id。"""
    name = _clean_tag(keywords)
    if not name:
        return None
    try:
        resp = http.get(
            TOPIC_SEARCH_URL,
            params={"page_size": 10, "offset": 0, "keywords": name},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("bili topic search failed keywords=%r: %s", name, exc)
        return None
    if payload.get("code") not in (0, None):
        logger.warning("bili topic search error keywords=%r: %s", name, payload.get("message"))
        return None
    topics = (((payload.get("data") or {}).get("result") or {}).get("topics") or [])
    if not isinstance(topics, list):
        return None
    chosen: dict[str, Any] | None = None
    for item in topics:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip() == name:
            chosen = item
            break
    if chosen is None and topics and isinstance(topics[0], dict):
        chosen = topics[0]
    if not chosen:
        logger.warning("bili topic not found keywords=%r", name)
        return None
    topic_id = int(chosen.get("id") or 0)
    if topic_id <= 0:
        return None
    mission_id = int(chosen.get("mission_id") or 0)
    topic_name = str(chosen.get("name") or name).strip()
    return {
        "topic_id": topic_id,
        "mission_id": mission_id,
        "topic_name": topic_name,
    }


def build_chat_tags(job: dict[str, Any], *, settings: Any | None = None) -> list[str]:
    """7 固定 + 1 主题；活动话题单独走 topic_id，不进 tag。"""
    theme = resolve_theme_tag(job)
    tags: list[str] = []
    seen: set[str] = set()
    for raw in (*CHAT_FIXED_TAGS, theme):
        tag = _clean_tag(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= 10:
            break
    return tags


def build_publish_tags(job: dict[str, Any], *, settings: Any | None = None) -> list[str]:
    pipeline = str(job.get("pipeline") or "").strip()
    if pipeline == CHAT_PIPELINE:
        return build_chat_tags(job, settings=settings)
    script = job.get("script_json") if isinstance(job.get("script_json"), dict) else {}
    return normalize_tags(script.get("tags"))
