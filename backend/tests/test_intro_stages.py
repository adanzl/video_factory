from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.intro.generator import _normalize_title, central_43_bounds
from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_SCIENCE_CHILD,
    intro_generate_category,
)
from worker.stages.intro import IntroStage
from worker.stages.intro.base import resolve_intro_title


def test_central_43_bounds_landscape() -> None:
    left, top, right, bottom = central_43_bounds(1280, 720)
    assert left == 160
    assert top == 0
    assert right == 1120
    assert bottom == 720


def test_central_43_bounds_portrait() -> None:
    left, top, right, bottom = central_43_bounds(720, 1280)
    assert left == 0
    assert right == 720
    assert bottom - top == 540


def test_intro_title_normalize_keeps_colon() -> None:
    assert _normalize_title("秦陵：未解之谜") == "秦陵：未解之谜"
    assert _normalize_title("秦陵:未解之谜") == "秦陵：未解之谜"
    assert _normalize_title("秦陵﹕未解之谜") == "秦陵：未解之谜"
    assert _normalize_title("秦陵︰未解之谜") == "秦陵：未解之谜"


def test_intro_title_normalize_keeps_other_punctuation() -> None:
    assert _normalize_title("《秦陵》·未解") == "《秦陵》·未解"
    assert _normalize_title("秦陵,未解?") == "秦陵，未解？"


def test_resolve_intro_title_uses_draft_when_only_punct_diff() -> None:
    job = {
        "title": "秦陵未解之谜",
        "script_json": {
            "title": "秦陵未解之谜",
            "draft_title": "秦陵：未解之谜",
        },
    }
    assert resolve_intro_title(job) == "秦陵：未解之谜"


def test_intro_generate_category_from_job() -> None:
    history_job = {
        "info": {
            "intro_category": "历史悬案",
            "content_style": CONTENT_STYLE_SCIENCE_CHILD,
        }
    }
    science_job = {
        "info": {
            "intro_category": "百科",
            "content_style": CONTENT_STYLE_HISTORICAL_MYSTERY,
        }
    }
    fallback_job = {"info": {"content_style": CONTENT_STYLE_HISTORICAL_MYSTERY}}
    assert intro_generate_category(history_job) == "历史悬案"
    assert intro_generate_category(science_job) is None
    assert intro_generate_category(fallback_job) == "历史悬案"


def test_intro_stage_uses_history_theme_from_job() -> None:
    stage = IntroStage()
    ctx = MagicMock()
    ctx.job = {"id": 1}
    job = {"id": 1, "info": {"intro_category": "历史悬案"}}

    with (
        patch("worker.stages.intro.connection") as mock_conn,
        patch("worker.stages.intro.repo_job.get_job", return_value=job),
        patch("worker.stages.intro.run_intro_for_category") as mock_run,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stage.run(ctx)

    mock_run.assert_called_once_with(ctx, job, stage=stage)


def test_intro_stage_uses_science_theme_when_intro_category_百科() -> None:
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
        patch("worker.stages.intro.repo_job.get_job", return_value=job),
        patch("worker.stages.intro.run_intro_for_category") as mock_run,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stage.run(ctx)

    mock_run.assert_called_once_with(ctx, job, stage=stage)
