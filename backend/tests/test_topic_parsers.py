"""选题 LLM 响应解析测试。"""

import pytest

from app.services.topic.parsers import parse_topics_payload
from app.services.topic.text import open_faq_title_issue
from app.services.topic.topic_mgr import score_title, status_from_score


def test_open_faq_title_issue_rejects_neutral_duration_question():
    assert open_faq_title_issue("地震预警能提前多久", category="科学原理") is not None


def test_open_faq_title_issue_allows_misconception_rebuttal():
    assert open_faq_title_issue(
        "地震预警能救命？明明只有几十秒窗口",
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
    with pytest.raises(ValueError, match="no valid entries"):
        parse_topics_payload(raw, max_title_len=24)


def test_scorer_rejects_open_faq_title():
    result = score_title(
        "地震预警能提前多久",
        category="科学原理",
        template="误区反问式",
    )
    assert result.total == 0
    assert result.rejected_reason is not None
    assert "百科式" in result.rejected_reason
    assert status_from_score(result) == "rejected"
