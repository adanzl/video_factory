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
    assert "单冲突" in story_sys
    assert "conflict_core" in story_sys
    assert "18" in story_sys
    assert "有娃的大人" in story_sys
    assert "权威翻车" in story_sys
    assert "谁先洗澡" in story_user
    assert "前 2 句" in story_user
    assert "conflict_core" in story_user
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
    # 前 2 句露出冲突锚点（凑满 ≤18 字，避免总字数掉线）
    openers = ("这个橡皮是我的你别抢", "新橡皮明明先是我拿到的")
    for i, opener in enumerate(openers):
        pad = max(0, DAILY_STORY_LINE_CHARS_MAX - len(opener))
        dialogue[i]["line"] = opener + ("呀" * pad)
    return {
        "scene_title": "新橡皮",
        "setting": "客厅，姐弟抢新橡皮",
        "conflict_core": "姐弟抢新橡皮",
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


def test_validate_daily_story_json_allows_soft_ending():
    story = _valid_story()
    story["dialogue"][-1]["line"] = "算了听姐姐的一二三四五六七八"
    validate_daily_story_json(story)


def test_daily_story_prompts_require_stance_coherence():
    story_sys, story_user = build_daily_story_prompts("抱枕大战")
    assert "立场连贯" in story_sys
    assert "自相矛盾" in story_sys
    assert "软收" in story_sys
    assert "好吧" in story_user or "自相矛盾" in story_user


def test_validate_daily_story_json_rejects_vague_punchline():
    story = _valid_story()
    story["punchline_explain"] = "姐弟斗嘴很好笑"
    with pytest.raises(ValueError, match="类型标签"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_missing_conflict_core():
    story = _valid_story()
    del story["conflict_core"]
    with pytest.raises(ValueError, match="conflict_core"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_offtopic_latter():
    story = _valid_story()
    # 后 1/3 岔开体育课，且前文未出现
    story["dialogue"][-1]["line"] = "体育课你还敢告老师吗"
    with pytest.raises(ValueError, match="跑题"):
        validate_daily_story_json(story)


def test_build_daily_story_retry_user_asks_to_expand_short_draft():
    from app.services.daily_story.prompts import build_daily_story_retry_user

    prev = _valid_story(n=10)
    user = build_daily_story_retry_user(
        "把姐姐的鞋带系一起",
        prev_story=prev,
        errors="对白总字数须≥300，当前180（还差120字）",
    )
    assert "还差" in user
    assert "上一稿" in user
    assert "鞋带" in user
    assert "增补" in user or "扩到" in user
    assert "禁止换 conflict_core" in user