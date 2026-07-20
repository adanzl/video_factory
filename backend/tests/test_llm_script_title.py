"""标题优化提示词测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.prompts import (
    DAILY_STORY_LINE_CHARS_MAX,
    build_daily_story_prompts,
    build_daily_story_theme_prompts,
    validate_daily_story_json,
)
from app.services.script.optimize_title import (
    CHAT_TITLE_MAX_LEN,
    build_chat_title_prompts,
    build_title_optimize_system_prompt,
    build_title_optimize_user_prompt,
    parse_title_optimize_payload,
)


def test_title_optimize_system_prompt_includes_hook_formulas():
    system = build_title_optimize_system_prompt(max_title_len=24)
    assert "误区反问" in system
    assert "反差好奇" in system
    assert "3 秒内" in system


def test_title_optimize_user_prompt_asks_for_hook():
    user = build_title_optimize_user_prompt(
        draft_title="雪崩瞬间",
        narration="哇，雪崩好快呀。",
        max_title_len=24,
    )
    assert "雪崩瞬间" in user
    assert "反常识" in user


def test_parse_title_optimize_payload():
    title = parse_title_optimize_payload({"title": "雪崩瞬间，为啥这么猛"}, max_title_len=24)
    assert title == "雪崩瞬间，为啥这么猛"


def test_chat_title_clamps_to_ten_and_includes_punchline():
    prompts = build_chat_title_prompts(
        "找橡皮",
        {
            "setting": "书桌前",
            "punchline_explain": "C类公平执念，姐姐权威被戳穿",
            "dialogue": [{"speaker": "昭昭", "line": "你藏了我的橡皮"}],
        },
        max_title_length=16,
    )
    assert f"≤{CHAT_TITLE_MAX_LEN} 字" in prompts["system"]
    assert "有娃的大人" in prompts["system"]
    assert "反差说明" in prompts["user"]
    assert "C类公平执念" in prompts["user"]
    assert "16" not in prompts["system"]


def test_daily_story_prompts_share_contract():
    theme_sys, theme_user = build_daily_story_theme_prompts(3)
    story_sys, story_user = build_daily_story_prompts("谁先洗澡")
    assert "10岁" in story_sys
    assert "10岁" in theme_user
    assert "360" in story_sys and "420" in story_sys
    assert "略超可接受" in story_sys
    assert "18" in story_sys
    assert "有娃的大人" in story_sys
    assert "权威翻车" in story_sys
    assert "谁先洗澡" in story_user
    assert "对付爸妈" not in theme_user
    assert "下雨只带了一把伞" not in theme_user


def _valid_story(*, line: str | None = None, n: int = 8) -> dict:
    if line is None:
        line = "一二三四五六七八九十一二三四五六七八"
    assert len(line) <= DAILY_STORY_LINE_CHARS_MAX
    speakers = ("昭昭", "灿灿")
    return {
        "scene_title": "谁先洗",
        "setting": "客厅，妈妈问谁先洗澡",
        "dialogue": [
            {"speaker": speakers[i % 2], "line": line} for i in range(n)
        ],
        "punchline_explain": "C类公平执念收束",
    }


def test_validate_daily_story_json_ok():
    validate_daily_story_json(_valid_story())


def test_validate_daily_story_json_allows_long_total_chars():
    # 总字数不再硬卡；598 这类略超不应失败
    validate_daily_story_json(_valid_story(n=34))


def test_validate_daily_story_json_rejects_long_line():
    story = _valid_story()
    story["dialogue"][0]["line"] = "一二三四五六七八九十一二三四五六七八九"
    assert len(story["dialogue"][0]["line"]) > DAILY_STORY_LINE_CHARS_MAX
    with pytest.raises(ValueError, match="超过18字"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_bad_speaker():
    story = _valid_story()
    story["dialogue"][0]["speaker"] = "爸爸"
    with pytest.raises(ValueError, match="爸爸"):
        validate_daily_story_json(story)
