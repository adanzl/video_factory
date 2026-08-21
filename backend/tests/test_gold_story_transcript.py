"""金故事 H0b 逐字稿工具测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story.download import parse_media_ref
from app.services.daily_story.gold_story.transcript import (
    format_dialogue_transcript,
    format_transcript_display,
    normalize_bv,
    read_source_list,
)


def test_normalize_bv_from_id():
    assert normalize_bv("BV1kfDTBXEfu") == "BV1kfDTBXEfu"


def test_normalize_bv_from_url():
    assert (
        normalize_bv("https://www.bilibili.com/video/BV1kfDTBXEfu")
        == "BV1kfDTBXEfu"
    )


def test_normalize_bv_invalid():
    with pytest.raises(ValueError, match="not a BV"):
        normalize_bv("not-a-bv")


def test_parse_douyin_ref():
    ref = parse_media_ref(
        "https://www.douyin.com/video/7123456789012345678",
        platform="douyin",
    )
    assert ref.source == "douyin"
    assert ref.source_id == "7123456789012345678"


def test_read_source_list(tmp_path):
    path = tmp_path / "bv.txt"
    path.write_text(
        "# comment\nBV1aaa111111\n\nhttps://www.bilibili.com/video/BV2bbb222222\n",
        encoding="utf-8",
    )
    assert read_source_list(path) == [
        "BV1aaa111111",
        "https://www.bilibili.com/video/BV2bbb222222",
    ]


def test_format_transcript_display_keeps_newlines():
    raw = "第一句\n第二句"
    assert format_transcript_display(raw) == raw


def test_format_transcript_display_splits_on_punctuation():
    raw = "已经睡了。你还醒着！别吵了？"
    assert format_transcript_display(raw) == "已经睡了。\n你还醒着！\n别吵了？"


def test_format_transcript_display_splits_on_comma():
    raw = "第一句,第二句,第三句"
    assert format_transcript_display(raw) == "第一句,\n第二句,\n第三句"
