"""选题 prompt 拼装测试。"""

from app.services.topic.catalog import CATEGORY_HISTORY, CATEGORY_SCIENCE
from app.services.topic.prompts.builder import (
    build_topic_optimize_system_prompt,
    build_topic_optimize_user_prompt,
    build_topic_system_prompt,
)
from app.services.topic.prompts.common import CONVERSATIONAL_TITLE_RULE


def test_general_topic_prompt_forbids_indirect_reasoning_chain():
    system = build_topic_system_prompt(
        max_title_len=24,
        category=CATEGORY_SCIENCE,
        count=3,
    )
    assert "西班牙人怕热" in CONVERSATIONAL_TITLE_RULE
    assert "链条太长" in system


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
