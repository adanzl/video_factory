"""选题 LLM 响应解析测试。"""

import pytest

from app.services.topic.parsers import (
    format_topic_parse_feedback,
    parse_topics_payload,
)
from app.services.topic.text import open_faq_title_issue


def test_open_faq_title_issue_rejects_neutral_duration_question():
    assert open_faq_title_issue("地震预警能提前多久", category="科学原理") is not None


def test_open_faq_title_issue_allows_misconception_rebuttal():
    assert open_faq_title_issue(
        "地震预警能救命？明明只有几十秒窗口",
        category="科学原理",
    ) is None


def test_open_faq_title_issue_allows_faq_keyword_with_rebuttal():
    assert open_faq_title_issue(
        "地震预警能提前多久？明明只有几十秒窗口",
        category="科学原理",
    ) is None


def test_parse_topics_payload_filters_open_faq_titles():
    raw = {
        "topics": [
            {
                "title": "地震预警能提前多久",
                "category": "科学原理",
                "template": "误区反问式",
                "hook": "科普预警窗口",
            },
            {
                "title": "看云就能预报地震？明明气象局早就辟谣了",
                "category": "科学原理",
                "template": "误区反问式",
                "hook": "地震云是谣言",
            },
        ]
    }
    topics = parse_topics_payload(raw, max_title_len=24)
    assert len(topics) == 1
    assert topics[0]["title"] == "看云就能预报地震？明明气象局早就辟谣了"


def test_parse_topics_payload_raises_when_all_filtered():
    raw = {
        "topics": [
            {
                "title": "地震预警能提前多久",
                "category": "科学原理",
                "template": "误区反问式",
            }
        ]
    }
    with pytest.raises(ValueError, match="均未通过"):
        parse_topics_payload(raw, max_title_len=24)


def test_parse_topics_payload_filters_attitude_only_response():
    raw = {
        "topics": [
            {
                "title": "地震云能预报地震？就这",
                "category": "科学原理",
                "template": "误区反问式",
            },
            {
                "title": "看云就能预报地震？明明气象局早就辟谣了",
                "category": "科学原理",
                "template": "误区反问式",
            },
        ]
    }
    topics = parse_topics_payload(raw, max_title_len=24)
    assert len(topics) == 1
    assert "气象局" in topics[0]["title"]


def test_format_topic_parse_feedback_lists_rejection_reasons():
    raw = {
        "topics": [
            {
                "title": "地震预警能提前多久",
                "category": "科学原理",
                "template": "误区反问式",
            }
        ]
    }
    feedback = format_topic_parse_feedback(raw, max_title_len=24)
    assert "地震预警能提前多久" in feedback
    assert "百科式" in feedback


def test_scorer_rejects_open_faq_title():
    from app.services.topic.topic_mgr import score_title, status_from_score

    result = score_title(
        "地震预警能提前多久",
        category="科学原理",
        template="误区反问式",
    )
    assert result.total == 0
    assert result.rejected_reason is not None
    assert "百科式" in result.rejected_reason
    assert status_from_score(result) == "rejected"


def test_scorer_rejects_plain_statement_for_misconception_template():
    from app.services.topic.topic_mgr import score_title, status_from_score

    result = score_title(
        "地震预警只有几十秒",
        category="科学原理",
        template="误区反问式",
    )
    assert result.total == 0
    assert result.rejected_reason is not None
    assert "问号对话体" in result.rejected_reason
    assert status_from_score(result) == "rejected"


def test_scorer_rejects_incomplete_conversational_title():
    from app.services.topic.topic_mgr import score_title, status_from_score

    result = score_title(
        "日本预警快只因为有钱？",
        category="科学原理",
        template="误区反问式",
    )
    assert result.total == 0
    assert result.rejected_reason is not None
    assert "问号后缺少回应" in result.rejected_reason
    assert status_from_score(result) == "rejected"


def test_parse_topics_payload_filters_incomplete_conversational():
    raw = {
        "topics": [
            {
                "title": "日本地震预警靠钱堆？",
                "category": "科学原理",
                "template": "误区反问式",
            },
            {
                "title": "日本预警快只靠砸钱？明明秒级靠的是地震波",
                "category": "科学原理",
                "template": "误区反问式",
            },
        ]
    }
    topics = parse_topics_payload(raw, max_title_len=24)
    assert len(topics) == 1
    assert "明明秒级靠的是地震波" in topics[0]["title"]
