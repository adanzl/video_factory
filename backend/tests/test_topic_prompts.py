"""选题 prompt 拼装测试。"""

from app.services.topic.catalog import CATEGORY_CURRENT, CATEGORY_HISTORY, CATEGORY_SCIENCE
from app.services.topic.prompts.builder import (
    build_topic_optimize_system_prompt,
    build_topic_optimize_user_prompt,
    build_topic_system_prompt,
)
from app.services.topic.prompts.common import CONVERSATIONAL_TITLE_RULE, FORBIDDEN_FAQ_TITLE_RULE, HOOK_MOTIVATION_RULE
from app.services.topic.text import conversational_rewrite_example


def test_general_topic_prompt_forbids_indirect_reasoning_chain():
    system = build_topic_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
        count=3,
    )
    assert "西班牙人怕热" in CONVERSATIONAL_TITLE_RULE
    assert "链条太长" in system
    assert "地震云能预报地震？就这" in CONVERSATIONAL_TITLE_RULE
    assert "仅有语气词" in system
    assert "够你跑路" in CONVERSATIONAL_TITLE_RULE
    assert "足够你躲桌下" in CONVERSATIONAL_TITLE_RULE
    assert "百科式中性提问" in system


def test_optimize_system_prompt_history_track():
    system = build_topic_optimize_system_prompt(
        max_title_len=24,
        category=CATEGORY_HISTORY,
    )
    assert "历史悬案" in system
    assert "代号" in system
    assert "禁止换成" in system


def test_optimize_system_prompt_general_includes_coherence_rule():
    system = build_topic_optimize_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
    )
    assert CONVERSATIONAL_TITLE_RULE[:20] in system


def test_optimize_user_prompt_history_constraints():
    user = build_topic_optimize_user_prompt(
        title="烛影斧声：宋太祖半夜暴毙",
        category=CATEGORY_HISTORY,
        template="悬念钩子式",
    )
    assert "代号：悬念" in user


def test_optimize_user_prompt_conversational_requires_direct_link():
    user = build_topic_optimize_user_prompt(
        title="日本断供光刻胶？明明仓库都堆成山了",
        category=CATEGORY_SCIENCE,
    )
    assert "一步直达" in user
    assert "多跳推理链" in user


def test_optimize_user_prompt_faq_title_requires_conversational_rewrite():
    title = "地震预警能提前多久"
    user = build_topic_optimize_user_prompt(
        title=title,
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert "必须含中文问号" in user
    assert conversational_rewrite_example(title) in user


def test_optimize_user_prompt_statement_without_question_mark():
    title = "动物真能预报地震"
    user = build_topic_optimize_user_prompt(
        title=title,
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert conversational_rewrite_example(title) in user


def test_optimize_user_prompt_statement_without_template_still_rewrites():
    title = "动物真能预报地震"
    user = build_topic_optimize_user_prompt(
        title=title,
        category=CATEGORY_SCIENCE,
    )
    assert "硬性格式" in user
    assert conversational_rewrite_example(title) in user


def test_optimize_system_prompt_requires_question_mark():
    system = build_topic_optimize_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
    )
    assert "必须含中文问号" in system
    assert "监测数据压根对不上" in system


def test_optimize_user_prompt_incomplete_conversational_requires_rebuttal():
    title = "日本地震预警靠钱堆？"
    user = build_topic_optimize_user_prompt(
        title=title,
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert "必须含中文问号" in user
    example = conversational_rewrite_example(title)
    assert example in user
    assert "够你跑路" not in example
    assert "地震波" in example or "砸钱" in example


def test_optimize_user_prompt_weak_hook_requires_rewrite():
    user = build_topic_optimize_user_prompt(
        title="地震预警只有几十秒？明明够你跑出楼",
        category=CATEGORY_SCIENCE,
        hook="委内瑞拉地震时预警只有几十秒，别小看它够你冲出楼外",
    )
    assert "原钩子" in user
    assert "别小看" in user
    assert HOOK_MOTIVATION_RULE[:8] in build_topic_optimize_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
    ) or "hook 规则" in user


def test_hook_curiosity_adjustment_penalizes_preachy_hook():
    from app.services.topic.scorers.base import hook_curiosity_adjustment

    bland = hook_curiosity_adjustment("委内瑞拉地震时别小看它，足够你冲出楼外")
    curious = hook_curiosity_adjustment("委内瑞拉 7 级强震前，告警响起时震波还在半路")
    assert bland < curious


def test_conversational_rewrite_example_money_vs_duration():
    money = conversational_rewrite_example("日本地震预警靠钱堆？")
    duration = conversational_rewrite_example("地震预警只有几十秒")
    assert "够你跑路" not in money
    assert "地震波" in money or "砸钱" in money
    assert "够你跑路" in duration or "够躲" in duration


def test_conversational_rewrite_example_uses_varied_rebuttal_openers():
    samples = [
        conversational_rewrite_example("地震预警能提前多久"),
        conversational_rewrite_example("动物真能预报地震"),
        conversational_rewrite_example("看云能预报地震"),
        conversational_rewrite_example("日本断供光刻胶"),
    ]
    assert all("？" in s for s in samples)
    responses = [s.split("？", 1)[1] for s in samples]
    assert not all(response.startswith("明明") for response in responses)
