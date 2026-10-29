"""H0/H1：B 站搜索 + 规则初筛。"""

from __future__ import annotations

import logging
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.collect.sign import fetch_bili_sign_keys, sign_bili_params
from app.services.gold_story.transcript.download import normalize_bv
from app.services.gold_story.collect.funny import (
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
    r"育儿课|教程|minecraft|MC恐怖|王者荣耀|原神|和平精英|"
    r"星穹铁道|崩坏|助眠|催眠|游戏实况|角色PV|恐怖地图",
    re.I,
)
# 孕产/分娩题材：站外是「产房实录」「待产包」「坐月子」这类成人纪实，
# 站内要的是 7–10 岁孩子日常对手戏，没有可拍的双孩冲突。
# 靠「二胎」进 _INCLUDE_TITLE 是漏点（#152「可妈二胎产房实录」就是这样进来的）。
# LLM 审核最终也会判「成人生产纪实」并驳回（#86），但那时已白下载+转写整条视频。
# 泛称「英语」「我的世界」「怀孕」「生孩子」也可能是家庭对白主题，交内容审核。
# 此处只拦明确的生产纪实或护理题材，不凭一个话题词否决素材。
_EXCLUDE_BIRTH_TITLE = re.compile(
    r"产房|待产包|坐月子|月子中心|月嫂|分娩|剖腹产|顺产|催产|产科|接生|"
    r"(?:新生儿|怀孕|孕期|孕晚期|生孩子|生娃|生产|陪产).{0,8}(?:实录|日记|记录|vlog|全过程)",
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
    duration_sec: int = 0


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


def title_reject_reason(title: str) -> str | None:
    """只看标题就能判死的题材，返回 reject reason；不拦则 None。

    抽取成公共函数，H1 初筛与单条 pipeline 共用：
    已入队/手工重导的 BV 也要挡，避免旧队列里的孕产片继续下载转写。
    """
    text = str(title or "").strip()
    if not text:
        return "empty_title"
    if _EXCLUDE_TITLE.search(text):
        return "exclude_title"
    if _EXCLUDE_BIRTH_TITLE.search(text):
        # 孕产/分娩纪实：标题就能判死，别浪费一次下载 + 转写
        return "exclude_birth"
    return None


def passes_h1_filter(
    *,
    title: str,
    view_count: int,
    reply_count: int,
    duration_sec: int | None = None,
    config: Config | None = None,
) -> tuple[bool, str]:
    cfg = config or Config()
    title_text = str(title or "").strip()
    title_reason = title_reject_reason(title_text)
    if title_reason:
        return False, title_reason
    max_duration = int(getattr(cfg, "gold_story_max_duration_sec", 0) or 0)
    if (
        duration_sec is not None
        and max_duration > 0
        and int(duration_sec) > max_duration
    ):
        # 合集/直播回放：转写要几小时，且往往抽不出单条微型故事
        return False, "too_long"
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
        # 合集/多 P 视频这里给的是总时长，正好用于「太长不要」门控
        "duration": int(data.get("duration") or 0),
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
    page: int = 1,
    config: Config | None = None,
    session: requests.Session | None = None,
) -> list[str]:
    """WBI 搜索 API 发现 BV 列表。"""
    cfg = config or Config()
    limit = max(1, min(limit, 50))
    http = session or _bili_http(cfg)
    img_key, sub_key = fetch_bili_sign_keys(http)
    params = sign_bili_params(
        {
            "keyword": keyword,
            "search_type": "video",
            "page": max(1, int(page)),
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
    advance_cursor: bool = True,
) -> list[VideoCandidate]:
    """H0 + H1：搜索并初筛，去重 BV。"""
    cfg = config or Config()
    cap = max_candidates if max_candidates is not None else cfg.gold_story_cron_max
    cap = max(1, min(cap, 50))
    words = keywords or search_keywords(cfg)
    cursor_key = hashlib.sha256(json.dumps(words, ensure_ascii=False).encode()).hexdigest()
    cursor = repo_gold_story.search_cursor(cursor_key)
    offset = cursor % len(words)
    words = words[offset:] + words[:offset]
    max_page = cfg.gold_story_search_max_page
    first_page = (cursor // len(words)) % max_page
    session = _bili_http(cfg)
    seen: set[str] = set()
    results: list[VideoCandidate] = []

    searched = False
    search_failed = False
    candidate_failure: Exception | None = None
    # 每页轮过所有关键词，最多三页/词，避免前面的词垄断整次搜索。
    searches = ((word, (first_page + depth) % max_page + 1)
                for depth in range(min(3, max_page)) for word in words)
    for keyword, page in searches:
        if len(results) >= cap:
            break
        try:
            bv_list = search_bilibili(
                keyword,
                page=page,
                limit=min(20, max(cap * 5, 10)),
                config=cfg,
                session=session,
            )
            searched = True
        except Exception as exc:
            search_failed = True
            logger.warning("gold_story search failed keyword=%r: %s", keyword, exc)
            continue
        for bvid in bv_list:
            if bvid in seen or len(results) >= cap:
                continue
            seen.add(bvid)
            if repo_gold_story.has_source(source="bili", source_id=bvid):
                logger.info(
                    "gold_story h0 skip bvid=%s reason=already_in_db",
                    bvid,
                )
                continue
            try:
                meta = fetch_video_meta(bvid, config=cfg, session=session)
            except Exception as exc:
                candidate_failure = exc
                logger.warning("gold_story view failed bvid=%s: %s", bvid, exc)
                continue
            duration_sec = int(meta.get("duration") or 0)
            ok, reason = passes_h1_filter(
                title=meta["title"],
                view_count=meta["view_count"],
                reply_count=meta["reply_count"],
                duration_sec=duration_sec,
                config=cfg,
            )
            if not ok:
                logger.info(
                    "gold_story h1 skip bvid=%s reason=%s duration=%ss title=%r",
                    bvid,
                    reason,
                    duration_sec,
                    meta["title"][:40],
                )
                continue
            try:
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
                    strict=True,
                )
            except Exception as exc:
                candidate_failure = exc
                logger.warning("gold_story audience fetch failed bvid=%s: %s", bvid, exc)
                continue
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
                    duration_sec=duration_sec,
                )
            )
    if not searched:
        raise RuntimeError("B 站搜索均失败，请稍后重试")
    if candidate_failure is not None and not results:
        raise RuntimeError("B 站候选信息获取失败，请稍后重试") from candidate_failure
    # 保留成功候选；局部故障时保留位置，下次跳过已入库项并补采遗漏项。
    if advance_cursor and not search_failed and candidate_failure is None:
        repo_gold_story.search_cursor(cursor_key, advance_from=cursor)
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
