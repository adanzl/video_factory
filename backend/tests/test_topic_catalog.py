"""选题 prompt 拼装测试。"""

from app.services.topic.catalog import (
    CATEGORY_CURRENT,
    CATEGORY_HISTORY,
    CATEGORY_SCIENCE,
    distribute_templates,
    normalize_category,
    resolve_category,
)
from app.services.topic.prompts.builder import build_topic_system_prompt, build_topic_user_prompt


def test_resolve_category_maps_legacy_track():
    assert resolve_category("日常科学原理") == CATEGORY_SCIENCE
    assert resolve_category("历史悬案") == CATEGORY_HISTORY


def test_normalize_category_matches_resolve():
    assert normalize_category("生活避坑实用常识") == CATEGORY_SCIENCE


def test_distribute_templates_respects_single_template():
    names = distribute_templates(CATEGORY_SCIENCE, 5, template="误区反问式")
    assert names == ["误区反问式"] * 5


def test_build_user_prompt_current_theme_requires_anchor():
    user = build_topic_user_prompt(
        category=CATEGORY_CURRENT,
        theme="委内瑞拉地震",
        count=1,
    )
    assert "委内瑞拉地震" in user
    assert "禁止换成无关泛科普" in user
    assert "hook 须点明时事锚点" in user
    assert "勿擅自换成其他话题" in user
    assert "自由发挥" not in user


def test_build_system_prompt_current_includes_theme_anchor_rule():
    from app.services.topic.prompts.common import CURRENT_THEME_ANCHOR_RULE, HOOK_MOTIVATION_RULE

    system = build_topic_system_prompt(
        max_title_len=24,
        category=CATEGORY_CURRENT,
        count=1,
    )
    assert CURRENT_THEME_ANCHOR_RULE[:12] in system
    assert HOOK_MOTIVATION_RULE[:8] in system
    assert "别小看" in system
    assert "evergreen" in system or "无关" in system


def test_build_user_prompt_includes_keywords():
    user = build_topic_user_prompt(
        category=CATEGORY_CURRENT,
        theme="地震科普",
        count=3,
        keywords="震级,烈度",
    )
    assert "震级" in user
    assert "烈度" in user


def test_build_system_prompt_includes_category_field():
    system = build_topic_system_prompt(
        max_title_len=20,
        category=CATEGORY_HISTORY,
        count=2,
    )
    assert "历史悬案" in system
    assert "category 固定" in system
