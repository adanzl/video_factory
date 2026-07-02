from app.quality.models import QualityReport
from app.quality.quality_mgr import format_quality_log_message


def test_format_quality_log_message_pass_copy_includes_word_count():
    report = QualityReport(level="pass", step="copy", details={"word_count": 1350})
    assert format_quality_log_message("copy", report) == "quality[copy]=pass, word_count=1350"


def test_format_quality_log_message_major_includes_reason():
    report = QualityReport(
        level="major",
        step="copy",
        fail_stage="script",
        details={"reason": "narration repetition: 分镜 1 与下一段复述"},
    )
    line = format_quality_log_message("copy", report)
    assert line.startswith("quality[copy]=major, reason=narration repetition:")
