"""cover_layout.split_cover_title_lines 单元测试。"""

from __future__ import annotations

from app.services.intro.cover_layout import COVER_TITLE_MAX_CHARS, split_cover_title_lines


def test_split_cover_title_lines_at_max_chars() -> None:
    title = "大雪封存十三载桩基之下惊现战编钟群秘"
    assert len(title) == COVER_TITLE_MAX_CHARS
    lines = split_cover_title_lines(title)
    assert len(lines) == 2
    assert "".join(lines) == title


def test_split_cover_title_lines_truncates_over_limit() -> None:
    long_title = "大雪封存十三载桩基之下惊现战国青铜编钟群秘密档案"
    lines = split_cover_title_lines(long_title)
    assert len("".join(lines)) == COVER_TITLE_MAX_CHARS


def test_split_cover_title_lines_by_space() -> None:
    lines = split_cover_title_lines("秦陵未解 之谜")
    assert lines == ["秦陵未解", "之谜"]


def test_split_cover_title_lines_short() -> None:
    assert split_cover_title_lines("秦陵编钟谜") == ["秦陵编钟谜"]


def test_split_cover_title_lines_over_eight_even_split() -> None:
    title = "明明酸奶我先抢，白忙了"
    lines = split_cover_title_lines(title)
    assert lines == ["明明酸奶我先", "抢，白忙了"]


def test_title_font_range_matches_cover_and_scales_1080p() -> None:
    from app.services.intro.title_layout import title_font_range

    assert title_font_range(width=1280, height=720) == (135, 100)
    assert title_font_range(width=1920, height=1080) == (
        round(135 * 1080 / 720),
        round(100 * 1080 / 720),
    )
    max_size, min_size = title_font_range(width=1920, height=1080)
    assert max_size > 135
    assert min_size >= 100
