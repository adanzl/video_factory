"""H0b 多源逐字稿融合与质量评分。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_OVERLAY_RES = (
    re.compile(r"近日"),
    re.compile(r"素材来源"),
    re.compile(r"应来自"),
    re.compile(r"陶泥|小猴子|bilibili", re.IGNORECASE),
)
_EMAIL_URL_RE = re.compile(
    r"@|[.](?:com|cn|net|org)\b|https?://|qq\.com",
    re.IGNORECASE,
)
_LATIN_NOISE_RE = re.compile(r"^[A-Za-z0-9._%+\-]{2,}$")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GARBLED_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9，。！？、；：\"\"''（）…\\s]")
_REPEAT_RE = re.compile(r"(.{2,8})\1{2,}")
# 描边字幕 mobile OCR 常见形近误字（背→育、来→米、什→竹 等）
_OCR_CONFUSION_CHARS = frozenset("育竹工姿卜适言诉取扇")


def normalize_transcript_line(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def _transcript_lines(text: str) -> list[str]:
    return [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]


def _overlay_line_ratio(text: str) -> float:
    lines = _transcript_lines(text)
    if not lines:
        return 0.0
    bad = 0
    for ln in lines:
        if any(pat.search(ln) for pat in _OVERLAY_RES):
            bad += 1
        elif len(ln) > 36 and "：" not in ln:
            bad += 1
    return bad / len(lines)


def _noise_line_ratio(text: str) -> float:
    """邮箱/链接/纯拉丁噪声行占比（常见于无烧录字幕的水印误 OCR）。"""
    lines = _transcript_lines(text)
    if not lines:
        return 0.0
    bad = 0
    for ln in lines:
        if _EMAIL_URL_RE.search(ln) or _LATIN_NOISE_RE.fullmatch(ln):
            bad += 1
    return bad / len(lines)


def _near_variant_line_ratio(text: str) -> float:
    """近重复但未并成同一句的行占比。

    无稳定烧录字幕时，OCR 常对同一花字输出「逗乐介多/个多/谷多」
    一类变体簇；真字幕合并后该比例应很低。
    """
    lines = [normalize_transcript_line(ln) for ln in _transcript_lines(text)]
    lines = [ln for ln in lines if len(ln) >= 4]
    n = len(lines)
    if n < 4:
        return 0.0
    variant = 0
    for i, a in enumerate(lines):
        for j, b in enumerate(lines):
            if i == j:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if 0.5 <= ratio < 0.92:
                variant += 1
                break
    return variant / n


def _ocr_confusion_char_ratio(text: str) -> float:
    """形近误字占比；真对白里「育/竹/工米」类组合应极少。"""
    compact = normalize_transcript_line(text)
    cjk = _CJK_RE.findall(compact)
    if len(cjk) < 8:
        return 0.0
    bad = sum(1 for ch in cjk if ch in _OCR_CONFUSION_CHARS)
    return bad / len(cjk)


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

    lines = _transcript_lines(raw)
    line_count = len(lines)
    duration_bonus = 0.0
    if duration_sec > 0:
        lines_per_min = line_count / max(duration_sec / 60.0, 0.1)
        if 4 <= lines_per_min <= 40:
            duration_bonus = 0.08

    conf_bonus = 0.0
    if avg_confidence is not None:
        conf_bonus = max(0.0, min(float(avg_confidence), 1.0)) * 0.15

    overlay_penalty = _overlay_line_ratio(raw) * 0.25
    noise_penalty = _noise_line_ratio(raw) * 0.45
    variant_ratio = _near_variant_line_ratio(raw)
    # 变体簇 ≥35%：典型无字幕误 OCR，重罚到跳过 ASR 阈值以下
    variant_penalty = 0.0
    if variant_ratio >= 0.35:
        variant_penalty = 0.25 + min(variant_ratio, 1.0) * 0.35
    elif variant_ratio >= 0.2:
        variant_penalty = variant_ratio * 0.35

    confusion_ratio = _ocr_confusion_char_ratio(raw)
    confusion_penalty = 0.0
    if confusion_ratio >= 0.12:
        confusion_penalty = 0.18 + min(confusion_ratio, 0.35) * 0.55
    elif confusion_ratio >= 0.06:
        confusion_penalty = confusion_ratio * 0.65

    score = (
        0.45 * cjk_ratio
        + 0.20 * keyword_ratio
        + 0.12 * min(line_count / 8.0, 1.0)
        + duration_bonus
        + conf_bonus
        - garbled_ratio * 0.35
        - repeat_penalty
        - overlay_penalty
        - noise_penalty
        - variant_penalty
        - confusion_penalty
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
