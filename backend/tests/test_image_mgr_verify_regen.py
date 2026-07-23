from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.segment.image.image_agnes import AgnesImageVerifyFailed
from app.services.segment.image.image_mgr import ImageMgr


def test_generate_segment_images_regens_prompt_after_verify_fail(tmp_path: Path) -> None:
    mgr = ImageMgr()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    seg = {
        "id": 4,
        "segment_index": 4,
        "text": "灿灿，把橡皮给我。",
        "image_prompt": "旧提示词 " * 20,
        "dialogue": [
            {"speaker": "妈妈", "text": "灿灿，把橡皮给我。"},
            {"speaker": "灿灿", "text": "不行！"},
        ],
    }
    job = {
        "id": 43,
        "script_json": {
            "title": "新橡皮归谁",
            "visual_style": "儿童情绪涂鸦",
            "setting": "客厅",
            "segments": [dict(seg)],
        },
    }

    provider = MagicMock()
    out = images_dir / "4.png"

    def _gen(prompt, output_path, **kwargs):
        output_path.write_bytes(b"png")
        calls = getattr(_gen, "calls", 0)
        _gen.calls = calls + 1
        if calls == 0:
            raise AgnesImageVerifyFailed(
                "fail", output_path=output_path, prompt=prompt
            )
        return output_path

    provider.generate.side_effect = _gen
    provider.describe_params.return_value = "provider=mock"

    def _fake_regen(seg_arg, **kwargs):
        seg_arg["image_prompt"] = "新提示词 " * 20
        return seg_arg["image_prompt"]

    with (
        patch.object(mgr, "_get_image_provider", return_value=provider),
        patch.object(mgr, "_regen_segment_image_prompt", side_effect=_fake_regen) as mock_regen,
        patch.object(mgr, "_persist_segment_prompt") as mock_persist,
        patch("app.config.get_settings") as mock_settings,
    ):
        mock_settings.return_value.mock_mode = True
        mock_settings.return_value.image_max_workers = 1
        results = mgr.generate_segment_images(
            [seg],
            images_dir,
            job=job,
            content_style="daily_story",
            on_image_done=lambda *_: None,
        )

    assert results == [(4, out)]
    assert provider.generate.call_count == 2
    mock_regen.assert_called_once()
    mock_persist.assert_called_once()
    assert "新提示词" in (seg.get("image_prompt") or "")


def test_generate_segment_images_skips_after_prompt_regen_fail(
    tmp_path: Path,
) -> None:
    mgr = ImageMgr()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    bad = {
        "id": 4,
        "segment_index": 4,
        "text": "行了",
        "image_prompt": "旧提示词 " * 20,
        "dialogue": [{"speaker": "妈妈", "text": "行了"}],
    }
    good = {
        "id": 5,
        "segment_index": 5,
        "text": "好",
        "image_prompt": "正常提示词 " * 20,
        "dialogue": [{"speaker": "昭昭", "text": "好"}],
    }
    job = {
        "id": 43,
        "script_json": {
            "title": "t",
            "visual_style": "v",
            "segments": [dict(bad), dict(good)],
        },
    }
    provider = MagicMock()
    done_ids: list[int] = []

    def _gen(prompt, output_path, **kwargs):
        output_path.write_bytes(b"png")
        if output_path.name == "4.png":
            raise AgnesImageVerifyFailed(
                "fail", output_path=output_path, prompt=prompt
            )
        return output_path

    provider.generate.side_effect = _gen
    provider.describe_params.return_value = "provider=mock"

    def _fake_regen(seg_arg, **kwargs):
        seg_arg["image_prompt"] = "新提示词 " * 20
        return seg_arg["image_prompt"]

    with (
        patch.object(mgr, "_get_image_provider", return_value=provider),
        patch.object(mgr, "_regen_segment_image_prompt", side_effect=_fake_regen),
        patch.object(mgr, "_persist_segment_prompt"),
        patch("app.config.get_settings") as mock_settings,
    ):
        mock_settings.return_value.mock_mode = True
        mock_settings.return_value.image_max_workers = 1
        results = mgr.generate_segment_images(
            [bad, good],
            images_dir,
            job=job,
            content_style="daily_story",
            on_image_done=lambda seg_id, _path, *_unused: done_ids.append(seg_id),
        )

    assert results == [(5, images_dir / "5.png")]
    assert done_ids == [5]
    assert not (images_dir / "4.png").exists()
    # bad: 3+3 attempts across two rounds → 2 generate calls that raise after
    # each round's internal retries are mocked as single raise per generate()
    assert provider.generate.call_count == 3  # 2 for bad rounds + 1 for good
