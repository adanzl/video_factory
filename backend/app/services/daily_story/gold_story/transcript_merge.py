"""H0b 多源逐字稿融合与质量评分。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_OVERLAY_RES = (
    re.compile(r"近日"),
    re.compile(r"素材来源"),
    re.compile(r"应来自"),
)


def _overlay_line_ratio(text: str) -> float:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        return 0.0
    bad = 0
    for ln in lines:
        if any(pat.search(ln) for pat in _OVERLAY_RES):
            bad += 1
        elif len(ln) > 36 and "：" not in ln:
            bad += 1
    return bad / len(lines)


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GARBLED_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9，。！？、；：\"\"''（）…\\s]")
_REPEAT_RE = re.compile(r"(.{2,8})\1{2,}")


def normalize_transcript_line(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def score_transcript_text(
    text: str,
    *,
    title: str = "",
    duration_sec: float = 0.0,
    avg_confidence: float | None = None,
) -> float:
    """机读质量分 0–1，用于 OCR / ASR 选主稿。"""
    raw = str(text or "").strip()
    compact = normalize_transcript_line(raw)
    if not compact:
        return 0.0

    total = len(compact)
    cjk_count = len(_CJK_RE.findall(compact))
    cjk_ratio = cjk_count / total
    garbled_ratio = len(_GARBLED_RE.findall(compact)) / total
    repeat_penalty = 0.15 if _REPEAT_RE.search(compact) else 0.0

    title_chars = [c for c in str(title or "") if _CJK_RE.match(c)]
    keyword_hits = sum(1 for c in set(title_chars) if c in compact)
    keyword_ratio = keyword_hits / max(len(set(title_chars)), 1)

    line_count = len([ln for ln in raw.splitlines() if ln.strip()])
    duration_bonus = 0.0
    if duration_sec > 0:
        lines_per_min = line_count / max(duration_sec / 60.0, 0.1)
        if 4 <= lines_per_min <= 40:
            duration_bonus = 0.08

    conf_bonus = 0.0
    if avg_confidence is not None:
        conf_bonus = max(0.0, min(float(avg_confidence), 1.0)) * 0.15

    overlay_penalty = _overlay_line_ratio(raw) * 0.25

    score = (
        0.45 * cjk_ratio
        + 0.20 * keyword_ratio
        + 0.12 * min(line_count / 8.0, 1.0)
        + duration_bonus
        + conf_bonus
        - garbled_ratio * 0.35
        - repeat_penalty
        - overlay_penalty
    )
    return max(0.0, min(round(score, 4), 1.0))


def texts_similar(a: str, b: str, *, threshold: float = 0.92) -> bool:
    na = normalize_transcript_line(a)
    nb = normalize_transcript_line(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def pick_transcript_candidate(
    candidates: list[dict[str, Any]],
    *,
    title: str = "",
    duration_sec: float = 0.0,
    min_quality: float = 0.35,
) -> dict[str, Any]:
    """在 OCR / ASR 等候选中选主稿。"""
    scored: list[dict[str, Any]] = []
    for row in candidates:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        quality = score_transcript_text(
            text,
            title=title,
            duration_sec=duration_sec,
            avg_confidence=row.get("avg_confidence"),
        )
        scored.append({**row, "quality_score": quality})

    if not scored:
        raise RuntimeError("no transcript candidate produced text")

    priority = {"ocr": 3, "cc": 3, "asr": 1}
    scored.sort(
        key=lambda r: (
            r.get("quality_score", 0.0),
            priority.get(str(r.get("source") or ""), 0),
        ),
        reverse=True,
    )
    best = scored[0]
    if float(best.get("quality_score") or 0.0) < min_quality:
        # 仍返回最高分，但打 warn 标记
        best = {**best, "quality_warn": True}
    return best
