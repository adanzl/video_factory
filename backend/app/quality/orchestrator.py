from __future__ import annotations

from pathlib import Path

from app.quality.models import QualityReport


def check_text(script: dict) -> QualityReport:
    narration = script.get("narration", "")
    word_count = len(narration.replace(" ", "").replace("\n", ""))
    if word_count < 200:
        return QualityReport(
            level="major",
            fail_stage="script",
            details={"reason": "narration too short", "word_count": word_count},
        )
    banned = ["包治百病", "稳赚不赔"]
    for word in banned:
        if word in narration:
            return QualityReport(
                level="major",
                fail_stage="script",
                details={"reason": f"banned phrase: {word}"},
            )
    return QualityReport(level="pass", details={"word_count": word_count})


def check_visual(segments: list[dict]) -> QualityReport:
    missing = [seg["id"] for seg in segments if not seg.get("image_path")]
    if missing:
        return QualityReport(
            level="minor",
            bad_segment_ids=missing,
            details={"reason": "missing images"},
        )
    return QualityReport(level="pass")


def check_audio(audio_path: Path | None, duration_sec: float) -> QualityReport:
    if audio_path is None or not audio_path.exists():
        return QualityReport(
            level="major",
            fail_stage="tts",
            details={"reason": "missing audio"},
        )
    min_duration = 30.0
    if duration_sec < min_duration:
        return QualityReport(
            level="major",
            fail_stage="tts",
            details={"reason": "audio too short", "duration_sec": duration_sec},
        )
    return QualityReport(level="pass", details={"duration_sec": duration_sec})


def run_quality_checks(
    *,
    script: dict,
    segments: list[dict],
    audio_path: Path | None,
    duration_sec: float,
) -> QualityReport:
    for checker in (
        lambda: check_text(script),
        lambda: check_visual(segments),
        lambda: check_audio(audio_path, duration_sec),
    ):
        report = checker()
        if report.level != "pass":
            return report
    return QualityReport(level="pass", details={"checks": ["text", "visual", "audio"]})
