from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.job_info import CONTENT_STYLE_HISTORICAL_MYSTERY, CONTENT_STYLE_SCIENCE_CHILD
from worker.stages.intro import IntroStage


def test_intro_stage_routes_history_mystery() -> None:
    stage = IntroStage()
    ctx = MagicMock()
    ctx.job = {"id": 1}
    job = {"id": 1, "info": {"intro_category": "历史悬案"}}

    with (
        patch("worker.stages.intro.connection") as mock_conn,
        patch("worker.stages.intro.job_repo.get_job", return_value=job),
        patch("worker.stages.intro.HistoryMysteryIntroStage.run") as mock_history,
        patch("worker.stages.intro.ScienceIntroStage.run") as mock_science,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stage.run(ctx)

    mock_history.assert_called_once_with(ctx)
    mock_science.assert_not_called()


def test_intro_stage_routes_science_by_content_style_fallback() -> None:
    stage = IntroStage()
    ctx = MagicMock()
    ctx.job = {"id": 2}
    job = {"id": 2, "info": {"content_style": CONTENT_STYLE_SCIENCE_CHILD}}

    with (
        patch("worker.stages.intro.connection") as mock_conn,
        patch("worker.stages.intro.job_repo.get_job", return_value=job),
        patch("worker.stages.intro.HistoryMysteryIntroStage.run") as mock_history,
        patch("worker.stages.intro.ScienceIntroStage.run") as mock_science,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stage.run(ctx)

    mock_science.assert_called_once_with(ctx)
    mock_history.assert_not_called()


def test_intro_stage_intro_category_overrides_content_style() -> None:
    stage = IntroStage()
    ctx = MagicMock()
    ctx.job = {"id": 3}
    job = {
        "id": 3,
        "info": {
            "content_style": CONTENT_STYLE_HISTORICAL_MYSTERY,
            "intro_category": "百科",
        },
    }

    with (
        patch("worker.stages.intro.connection") as mock_conn,
        patch("worker.stages.intro.job_repo.get_job", return_value=job),
        patch("worker.stages.intro.HistoryMysteryIntroStage.run") as mock_history,
        patch("worker.stages.intro.ScienceIntroStage.run") as mock_science,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stage.run(ctx)

    mock_science.assert_called_once_with(ctx)
    mock_history.assert_not_called()
