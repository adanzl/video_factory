"""标题优化提示词测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.prompts import (
    DAILY_STORY_LINE_CHARS_MAX,
    DAILY_STORY_TOTAL_CHARS_MAX,
    DAILY_STORY_TOTAL_CHARS_MIN,
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
    assert "300" in story_sys and "380" in story_sys
    assert "320" in story_sys and "360" in story_sys
    assert "开场钩子" in story_sys
    assert "18" in story_sys
    assert "有娃的大人" in story_sys
    assert "权威翻车" in story_sys
    assert "谁先洗澡" in story_user
    assert "前 2 句" in story_user
    assert "对付爸妈" not in theme_user
    assert "下雨只带了一把伞" not in theme_user
    assert "动作/实物" in theme_user


def _valid_story(*, line: str | None = None, n: int = 17) -> dict:
    # 默认 18*17=306，刚好过下限 300、未超上限 380
    if line is None:
        line = "一二三四五六七八九十一二三四五六七八"
    assert len(line) <= DAILY_STORY_LINE_CHARS_MAX
    speakers = ("昭昭", "灿灿")
    dialogue = [
        {"speaker": speakers[i % 2], "line": line} for i in range(n)
    ]
    # 开场须含冲突线索，且保持原字数不破坏上下限
    dialogue[0] = {"speaker": "昭昭", "line": "抢" + line[1:]}
    return {
        "scene_title": "谁先洗",
        "setting": "客厅，妈妈问谁先洗澡",
        "dialogue": dialogue,
        "punchline_explain": "C类公平执念，姐姐规则被字面戳穿",
    }


def test_validate_daily_story_json_ok():
    story = _valid_story()
    total = sum(len(d["line"]) for d in story["dialogue"])
    assert DAILY_STORY_TOTAL_CHARS_MIN <= total <= DAILY_STORY_TOTAL_CHARS_MAX
    validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_long_total_chars():
    with pytest.raises(ValueError, match="总字数须≤"):
        validate_daily_story_json(_valid_story(n=34))


def test_validate_daily_story_json_rejects_short_total_chars():
    with pytest.raises(ValueError, match="总字数须≥"):
        validate_daily_story_json(_valid_story(n=10))  # 远低于 300


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


def test_validate_daily_story_json_rejects_weak_opening():
    story = _valid_story()
    pad = "一二三四五六七八九十一二三四五六七八"
    story["dialogue"][0]["line"] = pad
    story["dialogue"][1]["line"] = pad
    story["dialogue"][2]["line"] = pad
    with pytest.raises(ValueError, match="开场前3句"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_soft_ending():
    story = _valid_story()
    story["dialogue"][-1]["line"] = "算了听姐姐的一二三四五六七八"
    with pytest.raises(ValueError, match="软收尾"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_vague_punchline():
    story = _valid_story()
    story["punchline_explain"] = "姐弟斗嘴很好笑"
    with pytest.raises(ValueError, match="类型标签"):
        validate_daily_story_json(story)
