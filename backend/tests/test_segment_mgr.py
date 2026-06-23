from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.segment.segment_mgr import segment_mgr
from app.services.visual import visual_mgr


def test_produce_images_partial_only_selected(tmp_path: Path) -> None:
    """部分重跑静图时，仅生成选中的分段。"""
    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "1.png").write_bytes(b"png")

    segments = [
        {"id": 101, "segment_index": 1, "image_prompt": "prompt one " * 40},
        {"id": 102, "segment_index": 2, "image_prompt": "prompt two " * 40},
        {"id": 103, "segment_index": 3, "image_prompt": "prompt three " * 40},
    ]

    def _fake_generate(
        targets: list[dict],
        out_dir: Path,
        *,
        size: str | None = None,
    ) -> list[tuple[int, Path]]:
        assert size is not None
        return [
            (seg["id"], out_dir / f"{seg['segment_index']}.png")
            for seg in targets
        ]

    with patch.object(visual_mgr, "generate_segment_images", side_effect=_fake_generate):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            only_segment_indices={2},
            scope="images",
            job={"info": {"orientation": "landscape"}},
        )

    generated_ids = {seg_id for seg_id, _ in result.image_paths}
    assert generated_ids == {102}
