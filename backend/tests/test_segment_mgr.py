from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.segment.segment_mgr import segment_mgr
from app.services.visual import visual_mgr


def test_produce_images_partial_includes_missing_unselected(tmp_path: Path) -> None:
    """部分重跑静图时，未选中且尚未出图的段落应自动加入出图队列。"""
    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "1.png").write_bytes(b"png")

    segments = [
        {"id": 101, "segment_index": 1, "image_prompt": "prompt one " * 40},
        {"id": 102, "segment_index": 2, "image_prompt": "prompt two " * 40},
    ]

    def _fake_generate(targets: list[dict], out_dir: Path) -> list[tuple[int, Path]]:
        return [
            (seg["id"], out_dir / f"{seg['segment_index']}.png")
            for seg in targets
        ]

    with patch.object(visual_mgr, "generate_segment_images", side_effect=_fake_generate):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            only_segment_indices={3},
            scope="images",
        )

    generated_ids = {seg_id for seg_id, _ in result.image_paths}
    assert generated_ids == {102}
