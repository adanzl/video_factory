from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.intro.generator import _normalize_title, central_43_bounds
from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_SCIENCE_CHILD,
    intro_generate_category,
)
from worker.stages.intro import IntroStage
from worker.stages.intro.base import pick_cover_image, resolve_intro_title


def test_pick_cover_image_chat_prefers_closeup(tmp_path) -> None:
    closeup = tmp_path / "3.png"
    opening = tmp_path / "1.png"
    closeup.write_bytes(b"x")
    opening.write_bytes(b"x")
    job = {
        "pipeline": "chat",
        "script_json": {
            "segments": [
                {"segment_index": 1, "shot_type": "全景"},
                {"segment_index": 2, "shot_type": "中景"},
                {"segment_index": 3, "shot_type": "特写"},
            ]
        },
    }
    segs = [
        {"segment_index": 1, "image_path": str(opening)},
        {"segment_index": 2, "image_path": str(tmp_path / "missing.png")},
        {"segment_index": 3, "image_path": str(closeup)},
    ]
    path, reason = pick_cover_image(job, segs)
    assert path == closeup
    assert reason == "closeup seg3"


def test_pick_cover_image_chat_falls_back_to_seg1(tmp_path) -> None:
    opening = tmp_path / "1.png"
    opening.write_bytes(b"x")
    job = {
        "pipeline": "chat",
        "script_json": {
            "segments": [
                {"segment_index": 1, "shot_type": "全景"},
                {"segment_index": 2, "shot_type": "中景"},
            ]
        },
    }
    segs = [
        {"segment_index": 1, "image_path": str(opening)},
        {"segment_index": 2, "image_path": str(tmp_path / "2.png")},
    ]
    path, reason = pick_cover_image(job, segs)
    assert path == opening
    assert reason == "seg1"


def test_pick_cover_image_standard_uses_seg1(tmp_path) -> None:
    opening = tmp_path / "1.png"
    closeup = tmp_path / "3.png"
    opening.write_bytes(b"x")
    closeup.write_bytes(b"x")
    job = {
        "pipeline": "standard",
        "script_json": {
            "segments": [
                {"segment_index": 1, "shot_type": "全景"},
                {"segment_index": 3, "shot_type": "特写"},
            ]
        },
    }
    segs = [
        {"segment_index": 1, "image_path": str(opening)},
        {"segment_index": 3, "image_path": str(closeup)},
    ]
    path, reason = pick_cover_image(job, segs)
    assert path == opening
    assert reason == "seg1"


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


def test_intro_stage_uses_history_theme_from_job(noop_atomic) -> None:
    stage = IntroStage()
    ctx = MagicMock()
    ctx.job = {"id": 1}
    job = {"id": 1, "info": {"intro_category": "历史悬案"}}

    with (
        patch("worker.stages.intro.repo_job.get_job", return_value=job),
        patch("worker.stages.intro.run_intro_for_category") as mock_run,
    ):
        stage.run(ctx)

    mock_run.assert_called_once_with(ctx, job, stage=stage)


def test_intro_stage_uses_science_theme_when_intro_category_百科(noop_atomic) -> None:
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
        patch("worker.stages.intro.repo_job.get_job", return_value=job),
        patch("worker.stages.intro.run_intro_for_category") as mock_run,
    ):
        stage.run(ctx)

    mock_run.assert_called_once_with(ctx, job, stage=stage)
