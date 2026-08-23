"""B 站观众反应 → funny_signal（替代 LLM 自评「好笑」）。"""

from __future__ import annotations

import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Config

logger = logging.getLogger(__name__)

STRONG_LAUGH: tuple[str, ...] = (
    "笑死",
    "xswl",
    "绷不住",
    "笑不活了",
    "救命笑死",
    "肚子疼",
    "笑裂开",
    "哈哈哈哈",
    "哈哈哈哈哈",
    "笑yue",
    "笑吐",
)
WEAK_LAUGH: tuple[str, ...] = ("哈哈", "嘿嘿", "233", "草", "乐", "hh")
CUTE_WORDS: tuple[str, ...] = (
    "好可爱",
    "可爱死了",
    "awsl",
    "心化",
    "萌化",
    "太可爱",
    "萌娃",
    "好萌",
)

L1_FUNNY_MIN = 0.20
L2_FUNNY_MIN = 0.40
L2_COMMENT_LAUGH_MIN = 0.15
DEFAULT_FUNNY_SIGNAL = 0.15
MAX_DANMAKU = 1000
DM_MIN_FOR_HARD = 20
DM_LAUGH_RATIO_MIN = 0.08


@dataclass(frozen=True, slots=True)
class AudienceFunnyMetrics:
    danmaku_total: int
    danmaku_laugh_score: float
    danmaku_laugh_ratio: float
    comment_laugh_ratio: float
    view_reply_ratio_norm: float
    funny_signal: float
    cute_not_funny: bool
    danmaku_fetch_ok: bool


def view_reply_ratio_norm(view_count: int, reply_count: int) -> float:
    view = max(1, int(view_count))
    reply = max(0, int(reply_count))
    raw = math.log1p(reply) / math.log1p(view)
    return round(min(1.0, raw / 0.5), 4)


def _laugh_cute_score(text: str) -> tuple[float, float]:
    t = str(text or "").strip().lower()
    if not t:
        return 0.0, 0.0
    laugh = 0.0
    for word in STRONG_LAUGH:
        if word.lower() in t:
            laugh += 2.0
    for word in WEAK_LAUGH:
        if word.lower() in t:
            laugh += 1.0
    cute = sum(1.0 for word in CUTE_WORDS if word.lower() in t)
    return laugh, cute


def danmaku_laugh_ratio(texts: list[str]) -> tuple[int, float]:
    total = len(texts)
    if total <= 0:
        return 0, 0.0
    score = 0.0
    for text in texts:
        laugh, _ = _laugh_cute_score(text)
        score += laugh
    ratio = min(1.0, score / max(2 * total, 1))
    return total, round(ratio, 4)


def comment_laugh_ratio(replies: list[str]) -> float:
    texts = [str(x).strip() for x in replies if str(x).strip()]
    if not texts:
        return 0.0
    hits = 0
    for text in texts:
        laugh, _ = _laugh_cute_score(text)
        if laugh > 0:
            hits += 1
    return round(hits / len(texts), 4)


def compute_funny_signal(
    *,
    dm_laugh_ratio: float,
    comment_laugh: float,
    view_reply_norm: float,
) -> float:
    signal = (
        0.50 * float(dm_laugh_ratio)
        + 0.30 * float(comment_laugh)
        + 0.20 * float(view_reply_norm)
    )
    return round(min(1.0, max(0.0, signal)), 4)


def cute_not_funny_flag(
    danmaku_texts: list[str],
    replies: list[str],
) -> bool:
    laugh_total = 0.0
    cute_total = 0.0
    for text in list(danmaku_texts) + list(replies):
        laugh, cute = _laugh_cute_score(text)
        laugh_total += laugh
        cute_total += cute
    if laugh_total <= 0 and cute_total <= 0:
        return False
    return cute_total > laugh_total


def passes_funny_gate(
    metrics: AudienceFunnyMetrics | None,
    *,
    level: str = "l1",
    config: Config | None = None,
) -> tuple[bool, str]:
    """L1 预筛 / L2 入库门槛。"""
    _ = config
    if metrics is None:
        return True, "no_metrics"
    return _passes_funny_values(
        funny_signal=metrics.funny_signal,
        danmaku_laugh_ratio=metrics.danmaku_laugh_ratio,
        comment_laugh_ratio=metrics.comment_laugh_ratio,
        danmaku_total=metrics.danmaku_total,
        danmaku_laugh_score=metrics.danmaku_laugh_score,
        danmaku_fetch_ok=metrics.danmaku_fetch_ok,
        cute_not_funny=metrics.cute_not_funny,
        level=level,
    )


def passes_funny_gate_from_payload(
    payload: dict[str, Any] | None,
    *,
    level: str = "l2",
) -> tuple[bool, str]:
    if not isinstance(payload, dict) or payload.get("funny_signal") is None:
        return True, "no_metrics"
    return _passes_funny_values(
        funny_signal=float(payload.get("funny_signal") or 0),
        danmaku_laugh_ratio=float(payload.get("danmaku_laugh_ratio") or 0),
        comment_laugh_ratio=float(payload.get("comment_laugh_ratio") or 0),
        danmaku_total=int(payload.get("danmaku_total") or 0),
        danmaku_laugh_score=float(payload.get("danmaku_laugh_score") or 0),
        danmaku_fetch_ok=bool(payload.get("danmaku_fetch_ok")),
        cute_not_funny=bool(payload.get("cute_not_funny")),
        level=level,
    )


def _passes_funny_values(
    *,
    funny_signal: float,
    danmaku_laugh_ratio: float,
    comment_laugh_ratio: float,
    danmaku_total: int,
    danmaku_laugh_score: float,
    danmaku_fetch_ok: bool,
    cute_not_funny: bool,
    level: str,
) -> tuple[bool, str]:
    if cute_not_funny:
        return False, "cute_not_funny"
    if (
        danmaku_fetch_ok
        and danmaku_total >= DM_MIN_FOR_HARD
        and danmaku_laugh_ratio < DM_LAUGH_RATIO_MIN
    ):
        return False, (
            f"no_danmaku_laugh:{danmaku_laugh_ratio:.3f}<{DM_LAUGH_RATIO_MIN}"
        )
    min_signal = L2_FUNNY_MIN if level == "l2" else L1_FUNNY_MIN
    if funny_signal < min_signal:
        return False, f"low_funny_signal:{funny_signal:.2f}<{min_signal}"
    if level == "l2" and comment_laugh_ratio < L2_COMMENT_LAUGH_MIN:
        if danmaku_fetch_ok and danmaku_total >= 50:
            pass
        elif comment_laugh_ratio < L2_COMMENT_LAUGH_MIN:
            return False, (
                f"low_comment_laugh:{comment_laugh_ratio:.2f}"
                f"<{L2_COMMENT_LAUGH_MIN}"
            )
    if level == "l1" and danmaku_fetch_ok and danmaku_laugh_score <= 0:
        if comment_laugh_ratio <= 0:
            return False, "no_audience_laugh"
    return True, "ok"


def fetch_danmaku_texts(
    *,
    cid: int,
    source_id: str,
    session: requests.Session,
    max_items: int = MAX_DANMAKU,
) -> list[str]:
    """拉取弹幕 XML，返回文本列表。"""
    if cid <= 0:
        return []
    bvid = str(source_id or "").strip()
    referer = f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"
    url = f"https://comment.bilibili.com/{int(cid)}.xml"
    resp = session.get(
        url,
        headers={"Referer": referer},
        timeout=20,
    )
    resp.raise_for_status()
    raw = resp.content
    if raw[:2] == b"\x1f\x8b":
        import gzip

        raw = gzip.decompress(raw)
    root = ET.fromstring(raw)
    texts: list[str] = []
    for node in root.findall("d"):
        text = (node.text or "").strip()
        if text:
            texts.append(text)
        if len(texts) >= max_items:
            break
    return texts


def compute_audience_funny_metrics(
    *,
    source_id: str,
    cid: int,
    view_count: int,
    reply_count: int,
    replies: list[str],
    session: requests.Session | None = None,
) -> AudienceFunnyMetrics:
    """H0：整支视频观众好笑信号。"""
    danmaku_texts: list[str] = []
    fetch_ok = False
    if session is not None and cid > 0:
        try:
            danmaku_texts = fetch_danmaku_texts(
                cid=cid,
                source_id=source_id,
                session=session,
            )
            fetch_ok = True
        except Exception as exc:
            logger.warning(
                "danmaku fetch failed bvid=%s cid=%s: %s",
                source_id,
                cid,
                exc,
            )

    dm_total, dm_ratio = danmaku_laugh_ratio(danmaku_texts)
    dm_score = round(dm_ratio * max(2 * dm_total, 1), 2)
    cm_ratio = comment_laugh_ratio(replies)
    vr_norm = view_reply_ratio_norm(view_count, reply_count)
    signal = compute_funny_signal(
        dm_laugh_ratio=dm_ratio,
        comment_laugh=cm_ratio,
        view_reply_norm=vr_norm,
    )
    cute_flag = cute_not_funny_flag(danmaku_texts, replies)
    return AudienceFunnyMetrics(
        danmaku_total=dm_total,
        danmaku_laugh_score=dm_score,
        danmaku_laugh_ratio=dm_ratio,
        comment_laugh_ratio=cm_ratio,
        view_reply_ratio_norm=vr_norm,
        funny_signal=signal,
        cute_not_funny=cute_flag,
        danmaku_fetch_ok=fetch_ok,
    )


def metrics_to_payload(metrics: AudienceFunnyMetrics) -> dict[str, Any]:
    return {
        "danmaku_total": metrics.danmaku_total,
        "danmaku_laugh_score": metrics.danmaku_laugh_score,
        "danmaku_laugh_ratio": metrics.danmaku_laugh_ratio,
        "comment_laugh_ratio": metrics.comment_laugh_ratio,
        "view_reply_ratio_norm": metrics.view_reply_ratio_norm,
        "funny_signal": metrics.funny_signal,
        "cute_not_funny": metrics.cute_not_funny,
        "danmaku_fetch_ok": metrics.danmaku_fetch_ok,
    }
