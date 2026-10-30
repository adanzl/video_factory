"""OCR 合并：原样保留，仅相邻去重。"""

from app.services.gold_story.transcript.ocr import merge_ocr_rows
import pytest


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


@pytest.mark.parametrize("first,second", [
    ("今天晚上我同意把这本书借给你", "今天晚上我不同意把这本书借给你"),
    ("这次请你帮我拿过来十五本练习册", "这次请你帮我拿过来十六本练习册"),
    ("这次需要支付的价格是12.5元", "这次需要支付的价格是125元"),
])
def test_similar_subtitles_preserve_changed_facts(first, second):
    text, segments, _ = merge_ocr_rows([
        {"timestamp_sec": 0, "text": first, "confidence": .7},
        {"timestamp_sec": 1, "text": second, "confidence": .99},
    ])
    assert text.splitlines() == [first, second]
    assert [s["confidence"] for s in segments] == [.7, .99]


def test_identical_subtitle_confidence_matches_selected_observation():
    _, segments, confidence = merge_ocr_rows([
        {"timestamp_sec": 0, "text": "原样对白", "confidence": .6},
        {"timestamp_sec": 1, "text": "原样对白", "confidence": .9},
    ])
    assert segments[0]["end_sec"] == 1
    assert segments[0]["confidence"] == confidence == .9
