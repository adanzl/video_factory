"""OCR 合并：原样保留，仅相邻去重。"""

from app.services.daily_story.gold_story.transcript.ocr import merge_ocr_rows


def test_merge_keeps_all_lines_and_only_dedupes_adjacent():
    rows = [
        {
            "timestamp_sec": 0.0,
            "text": "我爱学习你爱吗",
            "confidence": 0.9,
            "lines": ["我爱学习你爱吗"],
        },
        {
            "timestamp_sec": 1.0,
            "text": "我爱学习你爱吗",
            "confidence": 0.9,
            "lines": ["我爱学习你爱吗"],
        },
        {
            "timestamp_sec": 2.0,
            "text": "舌头授直了再给我翻译一遍",
            "confidence": 0.9,
            "lines": ["舌头授直了再给我翻译一遍"],
        },
        {
            "timestamp_sec": 3.0,
            "text": "C",
            "confidence": 0.7,
            "lines": ["C"],
        },
    ]
    plain, merged, _ = merge_ocr_rows(rows)
    lines = plain.splitlines()
    assert lines == [
        "我爱学习你爱吗",
        "舌头授直了再给我翻译一遍",
        "C",
    ]
    assert len(merged) == 3
