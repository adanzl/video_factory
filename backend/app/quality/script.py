"""script 阶段质检：口播文案、分镜剧本。"""

from __future__ import annotations

import re

from app.config import get_settings
from app.quality.models import QualityReport
from app.utils.job_info import resolve_narration_target_words
from app.utils.media import (
    NARRATION_ABS_MIN_CHARS,
    narration_accept_max_chars,
    narration_accept_min_chars,
    segment_text_char_cap,
)

__all__ = [
    "check_board",
    "check_narration",
    "detect_memoir_narration",
    "skip_board_check",
    "skip_narration_check",
]


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def _resolve_narration_target(script: dict) -> int:
    return resolve_narration_target_words(script)


_MEMOIR_BANNED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"我当.{0,10}(时|的时候)"), "伪亲历开场「我当…时」"),
    (re.compile(r"我在.{0,12}(干活|工作|下井|上班|采掘|值班)"), "编造一线从业场景"),
    (re.compile(r"老.{0,4}教(我|过)"), "老XX教我类传闻亲历"),
    (re.compile(r"我(条件反射|还不理解|后来才知道|后来查资料才知道|一生都忘不了)"), "第一人称亲历叙事"),
    (re.compile(r"班长(却|大声|拉|喊)"), "编造班长/同事现场故事"),
    (re.compile(r"评论区聊聊"), "抖音式评论区互动话术"),
)


def detect_memoir_narration(narration: str) -> str | None:
    """检测口播是否含伪亲历/角色扮演表述，命中则返回原因。"""
    for pattern, label in _MEMOIR_BANNED_PATTERNS:
        if pattern.search(narration):
            return label
    return None


def check_narration(script: dict) -> QualityReport:
    """口播稿长度、违禁表述。"""
    narration = script.get("narration", "")
    memoir_issue = detect_memoir_narration(narration)
    if memoir_issue:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={"reason": f"memoir style narration: {memoir_issue}"},
        )
    word_count = _narration_chars(narration)
    target = _resolve_narration_target(script)
    min_chars = max(
        NARRATION_ABS_MIN_CHARS,
        narration_accept_min_chars(target),
    )
    max_chars = narration_accept_max_chars(target)
    if word_count > max_chars:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={
                "reason": "narration too long",
                "word_count": word_count,
                "max_expected": max_chars,
            },
        )
    if word_count < min_chars:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={
                "reason": "narration too short",
                "word_count": word_count,
                "min_expected": min_chars,
            },
        )
    banned = ["包治百病", "稳赚不赔"]
    for word in banned:
        if word in narration:
            return QualityReport(
                level="major",
                step="copy",
                fail_stage="script",
                details={"reason": f"banned phrase: {word}"},
            )
    return QualityReport(level="pass", step="copy", details={"word_count": word_count})


def skip_narration_check() -> QualityReport:
    return QualityReport(
        level="pass",
        step="copy",
        details={"reason": "skipped"},
    )


def check_board(
    script: dict,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
) -> QualityReport:
    """标题、分镜数量与字段完整性。"""
    settings = get_settings()
    if segment_target_sec is None:
        saved_seg = script.get("segment_target_sec")
        seg_target = (
            float(saved_seg) if saved_seg is not None else settings.segment_target_sec
        )
    else:
        seg_target = segment_target_sec

    if max_title_length is None:
        saved_max = script.get("max_title_length")
        max_len = int(saved_max) if saved_max is not None else settings.max_title_length
    else:
        max_len = max_title_length

    title = re.sub(r"\s+", "", (script.get("title") or "").strip())
    if not title:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={"reason": "title is empty"},
        )
    if len(title) > max_len:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={
                "reason": "title too long",
                "title_length": len(title),
                "max_length": max_len,
            },
        )

    segments = script.get("segments") or []
    if seg_target > 0:
        cap = segment_text_char_cap(seg_target)
        target_words = script.get("narration_target_words")
        if isinstance(target_words, float) and target_words.is_integer():
            target_words = int(target_words)
        if not isinstance(target_words, int):
            target_words = None
        hard_cap = int(cap * 1.15)
        long_segments: list[dict] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                long_segments.append(
                    {
                        "segment_index": seg.get("segment_index"),
                        "chars": seg_chars,
                        "max_chars": cap,
                    }
                )
        if long_segments:
            return QualityReport(
                level="major",
                step="storyboard",
                fail_stage="script",
                details={
                    "reason": "segment text too long",
                    "segments": long_segments,
                    "segment_target_sec": seg_target,
                },
            )

    bad: list[int] = []
    for idx, seg in enumerate(segments):
        if not (seg.get("text") or "").strip():
            bad.append(idx)
    if bad:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={"reason": "empty segment text", "bad_segment_indexes": bad},
        )
    return QualityReport(
        level="pass",
        step="storyboard",
        details={"segment_count": len(segments), "title_length": len(title)},
    )


def skip_board_check() -> QualityReport:
    return QualityReport(
        level="pass",
        step="storyboard",
        details={"reason": "skipped"},
    )
