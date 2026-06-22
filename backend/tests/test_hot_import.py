from unittest.mock import MagicMock, patch

from app.services.topic.hot_pipeline import HOT_SOURCE, persist_scored_hot_topics


def test_persist_scored_hot_topics_min_score():
    topics = [
        {
            "title": "测试标题A",
            "track": "日常科学原理",
            "template": "误区反问式",
            "hook": "钩子",
            "total": 80,
            "status": "queued",
            "score_detail": {"total": 80},
        },
        {
            "title": "测试标题B",
            "total": 68,
            "status": "queued",
            "score_detail": {"total": 68},
        },
    ]
    row = {
        "id": 1,
        "title": "测试标题A",
        "source": HOT_SOURCE,
        "status": "queued",
        "score": 80,
    }
    conn = MagicMock()
    mock_insert = MagicMock(return_value={"id": 1, "title": "测试标题A", "source": HOT_SOURCE})
    mock_update = MagicMock(return_value=row)

    with (
        patch("app.repositories.connection.connection") as mock_conn,
        patch("app.repositories.title_repo.insert_title", mock_insert),
        patch("app.repositories.title_repo.update_title", mock_update),
    ):
        mock_conn.return_value.__enter__.return_value = conn
        result = persist_scored_hot_topics(topics, min_score=70)

    assert result["source"] == HOT_SOURCE
    assert result["count"] == 1
    assert result["skipped"] == 1
    mock_insert.assert_called_once()
