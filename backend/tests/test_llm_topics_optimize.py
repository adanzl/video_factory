"""选题优化 Prompt 测试。"""

from app.services.llm.llm_topics import (
    _CONVERSATIONAL_TITLE_RULE,
    build_topic_optimize_system_prompt,
    build_topic_optimize_user_prompt,
    build_topic_system_prompt,
)


def test_general_topic_prompt_forbids_indirect_reasoning_chain():
    system = build_topic_system_prompt(max_title_len=24)
    assert "西班牙人怕热" in system
    assert "链条太长太绕" in system


def test_optimize_system_prompt_history_track():
    system = build_topic_optimize_system_prompt(max_title_len=24, track="历史悬案")
    assert "历史悬案" in system
    assert "代号" in system
    assert "禁止换成" in system


def test_optimize_system_prompt_general_includes_coherence_rule():
    system = build_topic_optimize_system_prompt(max_title_len=24, track="日常科学原理")
    assert _CONVERSATIONAL_TITLE_RULE[:20] in system


def test_optimize_user_prompt_history_constraints():
    user = build_topic_optimize_user_prompt(
        title="烛影斧声：宋太祖半夜暴毙",
        track="历史悬案",
        template="悬念钩子式",
    )
    assert "同一历史人物" in user
    assert "代号：悬念" in user


def test_optimize_user_prompt_conversational_requires_direct_link():
    user = build_topic_optimize_user_prompt(
        title="日本断供光刻胶？明明仓库都堆成山了",
        track="日常科学原理",
    )
    assert "一步直达" in user
    assert "多跳推理链" in user
