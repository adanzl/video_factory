"""选题 prompt 拼装测试。"""

from app.services.topic.catalog import CATEGORY_HISTORY, CATEGORY_SCIENCE
from app.services.topic.prompts.builder import (
    build_topic_optimize_system_prompt,
    build_topic_optimize_user_prompt,
    build_topic_system_prompt,
)
from app.services.topic.prompts.common import CONVERSATIONAL_TITLE_RULE, FORBIDDEN_FAQ_TITLE_RULE


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
    user = build_topic_optimize_user_prompt(
        title="地震预警能提前多久",
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert "必须含中文问号" in user
    assert "地震预警能提前多久？明明够你跑路的" in user


def test_optimize_user_prompt_statement_without_question_mark():
    user = build_topic_optimize_user_prompt(
        title="动物真能预报地震",
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert "动物真能预报地震？明明监测数据对不上" in user


def test_optimize_user_prompt_statement_without_template_still_rewrites():
    user = build_topic_optimize_user_prompt(
        title="动物真能预报地震",
        category=CATEGORY_SCIENCE,
    )
    assert "硬性格式" in user
    assert "动物真能预报地震？明明监测数据对不上" in user


def test_optimize_system_prompt_requires_question_mark():
    system = build_topic_optimize_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
    )
    assert "必须含中文问号" in system
    assert "动物真能预报地震？明明监测数据对不上" in system


def test_optimize_user_prompt_incomplete_conversational_requires_rebuttal():
    user = build_topic_optimize_user_prompt(
        title="日本地震预警靠钱堆？",
        category=CATEGORY_SCIENCE,
        template="误区反问式",
    )
    assert "硬性格式" in user
    assert "必须含中文问号" in user
    assert "日本地震预警靠钱堆？明明够你跑路的" in user
