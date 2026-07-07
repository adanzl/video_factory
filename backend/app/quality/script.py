"""script 阶段质检：口播文案、分镜剧本。"""

from __future__ import annotations

import re
from collections import Counter

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
    "detect_json_in_narration",
    "detect_memoir_narration",
    "detect_narration_repetition",
    "skip_board_check",
    "skip_narration_check",
]

_REPEAT_PHRASE_MIN_LEN = 10
_REPEAT_PHRASE_MIN_COUNT = 3
_ADJACENT_OVERLAP_MIN_LEN = 10
_NIKAN_MAX_COUNT = 4

# narration 中不应出现 JSON 结构片段
_JSON_FRAGMENT_RE = re.compile(r'\{\s*"[\w]+"\s*:')


def detect_json_in_narration(narration: str) -> str | None:
    """检测 narration 中是否混入了 JSON 结构片段。"""
    m = _JSON_FRAGMENT_RE.search(narration)
    if m:
        start = max(0, m.start() - 10)
        end = min(len(narration), m.end() + 30)
        preview = narration[start:end]
        return f"narration 含 JSON 片段: …{preview}…"
    return None


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


def _normalize_narration_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _adjacent_shared_fragment(left: str, right: str, *, min_len: int) -> str | None:
    a = _normalize_narration_text(left)
    b = _normalize_narration_text(right)
    if not a or not b:
        return None
    upper = min(len(a), len(b))
    for size in range(upper, min_len - 1, -1):
        for start in range(len(a) - size + 1):
            frag = a[start : start + size]
            if frag in b:
                return frag
    return None


def detect_narration_repetition(
    narration: str,
    segments: list[dict] | None = None,
) -> str | None:
    """检测口播复读（重复短语、相邻段复述、完全相同分镜）。"""
    normalized = _normalize_narration_text(narration)
    if not normalized:
        return None

    if normalized.count("你看") > _NIKAN_MAX_COUNT:
        return "「你看」出现过多（全文最多 3～4 次）"

    grams: Counter[str] = Counter()
    for size in range(_REPEAT_PHRASE_MIN_LEN, _REPEAT_PHRASE_MIN_LEN + 5):
        if len(normalized) < size:
            continue
        for start in range(len(normalized) - size + 1):
            frag = normalized[start : start + size]
            if len(set(frag)) < 3:
                continue
            grams[frag] += 1
    repeated = [(frag, count) for frag, count in grams.items() if count >= _REPEAT_PHRASE_MIN_COUNT]
    if repeated:
        frag, count = max(repeated, key=lambda item: (len(item[0]), item[1]))
        preview = frag if len(frag) <= 20 else f"{frag[:20]}…"
        return f"短语「{preview}」重复 {count} 次"

    if not segments:
        return None

    ordered = sorted(
        segments,
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    texts = [str(seg.get("text") or "") for seg in ordered]
    dup = Counter(_normalize_narration_text(text) for text in texts if text.strip())
    for text, count in dup.items():
        if count > 1 and len(text) >= 15:
            return f"有 {count} 段口播文案完全相同"

    for index in range(len(texts) - 1):
        frag = _adjacent_shared_fragment(
            texts[index],
            texts[index + 1],
            min_len=_ADJACENT_OVERLAP_MIN_LEN,
        )
        if frag:
            seg_idx = ordered[index].get("segment_index", index + 1)
            preview = frag if len(frag) <= 24 else f"{frag[:24]}…"
            return f"分镜 {seg_idx} 与下一段复述「{preview}」"
    return None


def check_narration(script: dict) -> QualityReport:
    """口播稿长度、违禁表述。"""
    narration = script.get("narration", "")
    json_issue = detect_json_in_narration(narration)
    if json_issue:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={"reason": json_issue},
        )
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
    repeat_issue = detect_narration_repetition(
        narration,
        script.get("segments") if isinstance(script.get("segments"), list) else None,
    )
    if repeat_issue:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={"reason": f"narration repetition: {repeat_issue}"},
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

    title = (script.get("title") or "").strip()
    title_clean = re.sub(r"[^\w]", "", re.sub(r"\s+", "", title))
    if not title_clean:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={"reason": "title is empty"},
        )
    if len(title_clean) > max_len:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={
                "reason": "title too long",
                "title_length": len(title_clean),
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
