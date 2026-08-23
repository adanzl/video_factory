"""H0/H1：B 站搜索 + 规则初筛。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.config import Config
from app.services.daily_story.gold_story.bili_wbi import fetch_wbi_keys, sign_wbi_params
from app.services.daily_story.gold_story.download import normalize_bv
from app.services.daily_story.gold_story.funny_signal import (
    compute_audience_funny_metrics,
    metrics_to_payload,
    passes_funny_gate,
)
from app.services.publish.bilibili.session import BiliSession, USER_AGENT

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_KEYWORDS: tuple[str, ...] = (
    "姐弟吵架",
    "兄妹抢",
    "二胎抢东西",
    "童言无忌",
    "萌娃语录",
    "萌娃名场面",
    "萌娃讲道理",
    "二胎日常",
)

_INCLUDE_TITLE = re.compile(
    r"姐弟|兄妹|抢|吵架|名场面|日常|语录|萌娃|童言|二胎",
    re.I,
)
_EXCLUDE_TITLE = re.compile(
    r"育儿课|教程|英语|英文|minecraft|MC恐怖|我的世界|王者|原神|和平精英|"
    r"星穹|崩坏|铁道|助眠|催眠|游戏实况|角色PV|恐怖地图",
    re.I,
)


@dataclass(frozen=True, slots=True)
class VideoCandidate:
    source: str
    source_id: str
    url: str
    title: str
    description: str
    view_count: int
    reply_count: int
    keyword: str
    top_replies: tuple[str, ...] = ()
    cid: int = 0
    funny_metrics: dict[str, Any] | None = None


def search_keywords(config: Config | None = None) -> list[str]:
    cfg = config or Config()
    raw = str(getattr(cfg, "gold_story_search_keywords", "") or "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return parts
    return list(DEFAULT_SEARCH_KEYWORDS)


def engagement_norm(view_count: int, reply_count: int) -> float:
    view = max(0, int(view_count))
    reply = max(0, int(reply_count))
    v = min(1.0, view / 500_000)
    r = min(1.0, reply / 500)
    return round(0.6 * v + 0.4 * r, 4)


def passes_h1_filter(
    *,
    title: str,
    view_count: int,
    reply_count: int,
    config: Config | None = None,
) -> tuple[bool, str]:
    cfg = config or Config()
    title_text = str(title or "").strip()
    if not title_text:
        return False, "empty_title"
    if _EXCLUDE_TITLE.search(title_text):
        return False, "exclude_title"
    view_ok = int(view_count) >= cfg.gold_story_min_view
    reply_ok = int(reply_count) >= cfg.gold_story_min_reply
    if not view_ok and not reply_ok:
        return False, "low_engagement"
    if not _INCLUDE_TITLE.search(title_text) and not reply_ok:
        return False, "title_not_matched"
    return True, "ok"


def _bili_http(config: Config) -> requests.Session:
    session = BiliSession(path=config.bili_cookie_path).http()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
        }
    )
    return session


def fetch_video_meta(
    source_id: str,
    *,
    config: Config | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    cfg = config or Config()
    bvid = normalize_bv(source_id)
    http = session or _bili_http(cfg)
    resp = http.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, None):
        raise RuntimeError(f"bili view failed: {payload.get('message')}")
    data = payload.get("data") or {}
    stat = data.get("stat") or {}
    return {
        "source": "bili",
        "source_id": bvid,
        "url": f"https://www.bilibili.com/video/{bvid}",
        "title": str(data.get("title") or ""),
        "description": str(data.get("desc") or ""),
        "aid": int(data.get("aid") or 0),
        "view_count": int(stat.get("view") or 0),
        "reply_count": int(stat.get("reply") or 0),
        "cid": int(data.get("cid") or 0),
    }


def fetch_top_replies(
    aid: int,
    *,
    config: Config | None = None,
    session: requests.Session | None = None,
    limit: int = 5,
) -> list[str]:
    if aid <= 0:
        return []
    cfg = config or Config()
    http = session or _bili_http(cfg)
    resp = http.get(
        "https://api.bilibili.com/x/v2/reply",
        params={"type": 1, "oid": aid, "sort": 2, "ps": max(1, min(limit, 20))},
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, None):
        logger.warning("bili reply failed aid=%s: %s", aid, payload.get("message"))
        return []
    replies: list[str] = []
    for item in (payload.get("data") or {}).get("replies") or []:
        content = item.get("content") or {}
        text = str(content.get("message") or "").strip()
        if len(text) >= 20:
            replies.append(text)
    return replies[:limit]


def search_bilibili(
    keyword: str,
    *,
    limit: int = 20,
    config: Config | None = None,
    session: requests.Session | None = None,
) -> list[str]:
    """WBI 搜索 API 发现 BV 列表。"""
    cfg = config or Config()
    limit = max(1, min(limit, 50))
    http = session or _bili_http(cfg)
    img_key, sub_key = fetch_wbi_keys(http)
    params = sign_wbi_params(
        {
            "keyword": keyword,
            "search_type": "video",
            "page": 1,
            "page_size": limit,
            "order": "totalrank",
            "platform": "pc",
            "single_column": 0,
        },
        img_key=img_key,
        sub_key=sub_key,
    )
    resp = http.get(
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        params=params,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, None):
        raise RuntimeError(f"bili search failed: {payload.get('message')}")
    out: list[str] = []
    for item in (payload.get("data") or {}).get("result") or []:
        bvid = str(item.get("bvid") or "").strip()
        if bvid:
            out.append(bvid)
    return out[:limit]


def collect_candidates(
    *,
    config: Config | None = None,
    max_candidates: int | None = None,
    keywords: list[str] | None = None,
) -> list[VideoCandidate]:
    """H0 + H1：搜索并初筛，去重 BV。"""
    cfg = config or Config()
    cap = max_candidates if max_candidates is not None else cfg.gold_story_cron_max
    cap = max(1, min(cap, 50))
    words = keywords or search_keywords(cfg)
    session = _bili_http(cfg)
    seen: set[str] = set()
    results: list[VideoCandidate] = []

    for keyword in words:
        if len(results) >= cap:
            break
        try:
            bv_list = search_bilibili(
                keyword,
                limit=min(20, max(cap * 5, 10)),
                config=cfg,
                session=session,
            )
        except Exception as exc:
            logger.warning("gold_story search failed keyword=%r: %s", keyword, exc)
            continue
        for bvid in bv_list:
            if bvid in seen or len(results) >= cap:
                continue
            seen.add(bvid)
            try:
                meta = fetch_video_meta(bvid, config=cfg, session=session)
            except Exception as exc:
                logger.warning("gold_story view failed bvid=%s: %s", bvid, exc)
                continue
            ok, reason = passes_h1_filter(
                title=meta["title"],
                view_count=meta["view_count"],
                reply_count=meta["reply_count"],
                config=cfg,
            )
            if not ok:
                logger.info(
                    "gold_story h1 skip bvid=%s reason=%s title=%r",
                    bvid,
                    reason,
                    meta["title"][:40],
                )
                continue
            replies = fetch_top_replies(
                int(meta.get("aid") or 0),
                config=cfg,
                session=session,
                limit=8,
            )
            funny = compute_audience_funny_metrics(
                source_id=bvid,
                cid=int(meta.get("cid") or 0),
                view_count=int(meta["view_count"]),
                reply_count=int(meta["reply_count"]),
                replies=replies,
                session=session,
            )
            funny_ok, funny_reason = passes_funny_gate(funny, level="l1", config=cfg)
            if not funny_ok:
                logger.info(
                    "gold_story h1 skip bvid=%s reason=%s funny=%.2f",
                    bvid,
                    funny_reason,
                    funny.funny_signal,
                )
                continue
            results.append(
                VideoCandidate(
                    source="bili",
                    source_id=bvid,
                    url=str(meta["url"]),
                    title=str(meta["title"]),
                    description=str(meta["description"]),
                    view_count=int(meta["view_count"]),
                    reply_count=int(meta["reply_count"]),
                    keyword=keyword,
                    top_replies=tuple(replies),
                    cid=int(meta.get("cid") or 0),
                    funny_metrics=metrics_to_payload(funny),
                )
            )
    return results


def write_candidate_list(
    candidates: list[VideoCandidate],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# gold_story candidates generated"]
    for row in candidates:
        lines.append(row.source_id)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
