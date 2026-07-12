from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.segment.segment_mgr import segment_mgr
from app.services.segment.image import image_mgr


def test_produce_images_partial_only_selected(tmp_path: Path) -> None:
    """部分重跑静图时，仅生成选中的分镜。"""
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
        image_provider: str | None = None,
        on_image_done=None,
        job_id: int | None = None,
    ) -> list[tuple[int, Path]]:
        assert size is not None
        return [
            (seg["id"], out_dir / f"{seg['segment_index']}.png")
            for seg in targets
        ]

    with patch.object(image_mgr, "generate_segment_images", side_effect=_fake_generate):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            only_segment_indices={2},
            scope="images",
            job={"info": {"orientation": "landscape"}},
        )

    generated_ids = {seg_id for seg_id, _ in result.image_paths}
    assert generated_ids == {102}


def test_produce_images_persists_each_image_via_callback(tmp_path: Path) -> None:
    """出图时每张完成后立即回调，不必等整批结束。"""
    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)

    segments = [
        {"id": 101, "segment_index": 1, "image_prompt": "prompt one " * 40},
        {"id": 102, "segment_index": 2, "image_prompt": "prompt two " * 40},
    ]
    persisted: list[tuple[int, Path]] = []

    def _fake_generate(
        targets: list[dict],
        out_dir: Path,
        *,
        size: str | None = None,
        image_provider: str | None = None,
        on_image_done=None,
        job_id: int | None = None,
    ) -> list[tuple[int, Path]]:
        assert on_image_done is not None
        results = []
        for seg in targets:
            path = out_dir / f"{seg['segment_index']}.png"
            path.write_bytes(b"png")
            on_image_done(seg["id"], path)
            results.append((seg["id"], path))
        return results

    with patch.object(image_mgr, "generate_segment_images", side_effect=_fake_generate):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            scope="images",
            job={"info": {"orientation": "landscape"}},
            on_image_done=lambda seg_id, path: persisted.append((seg_id, path)),
        )

    assert persisted == [(101, images_dir / "1.png"), (102, images_dir / "2.png")]
    assert result.image_paths == persisted


def test_produce_clips_partial_skips_unselected_without_image(tmp_path: Path) -> None:
    """部分图生视频时，未选中分镜缺少静图不应阻断。"""
    from app.services.media.media_mgr import SegmentClipsResult, media_mgr

    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "1.png"
    image_path.write_bytes(b"png")

    segments = [
        {
            "id": 101,
            "segment_index": 1,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 5.0,
            "text": "测试口播",
        },
        {"id": 103, "segment_index": 3, "visual_mode": "wan_i2v"},
    ]
    fake_clips = SegmentClipsResult(segment_clip_paths=[(101, media_dir / "segments" / "1.mp4")])

    with patch.object(media_mgr, "build_segment_clips", return_value=fake_clips) as mock_build:
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            audio_path=None,
            only_segment_indices={1},
            scope="clips",
        )

    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["only_segment_indices"] == {1}
    assert result.clips.segment_clip_paths == fake_clips.segment_clip_paths


def test_produce_clips_persists_each_clip_via_callback(tmp_path: Path) -> None:
    """图生视频时每段完成后立即回调，不必等整批结束。"""
    from app.services.media.media_mgr import media_mgr

    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "1.png"
    image_path.write_bytes(b"png")
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True)

    segments = [
        {
            "id": 101,
            "segment_index": 1,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 5.0,
            "text": "测试口播一",
        },
        {
            "id": 102,
            "segment_index": 2,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 4.0,
            "text": "测试口播二",
        },
    ]
    persisted: list[tuple[int, Path]] = []

    def _fake_build(
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path=None,
        only_segment_indices=None,
        job=None,
        on_clip_done=None,
    ):
        assert on_clip_done is not None
        results = []
        for seg in segments:
            path = media_dir / "segments" / f"{seg['segment_index']}.mp4"
            path.write_bytes(b"mp4")
            on_clip_done(seg["id"], path)
            results.append((seg["id"], path))
        from app.services.media.media_mgr import SegmentClipsResult

        return SegmentClipsResult(segment_clip_paths=results)

    with patch.object(media_mgr, "build_segment_clips", side_effect=_fake_build):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            audio_path=None,
            scope="clips",
            on_clip_done=lambda seg_id, path: persisted.append((seg_id, path)),
        )

    assert persisted == [
        (101, clips_dir / "1.mp4"),
        (102, clips_dir / "2.mp4"),
    ]
    assert result.clips.segment_clip_paths == persisted


def test_produce_segments_skips_existing_clips(tmp_path: Path) -> None:
    """部分 clip 已存在时跳过已生成的，只重新生成缺失的 clip（服务重启恢复场景）。"""
    from app.services.media.media_mgr import SegmentClipsResult, media_mgr

    media_dir = tmp_path / "17"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True)

    (images_dir / "1.png").write_bytes(b"png")
    (images_dir / "2.png").write_bytes(b"png")
    (images_dir / "3.png").write_bytes(b"png")

    # 分镜1 已有 clip（模拟服务重启前已生成1个）
    (clips_dir / "1.mp4").write_bytes(b"mp4")

    segments = [
        {"id": 101, "segment_index": 1, "visual_mode": "wan_i2v", "image_path": str(images_dir / "1.png"), "duration_sec": 5.0, "text": "测试一"},
        {"id": 102, "segment_index": 2, "visual_mode": "wan_i2v", "image_path": str(images_dir / "2.png"), "duration_sec": 5.0, "text": "测试二"},
        {"id": 103, "segment_index": 3, "visual_mode": "wan_i2v", "image_path": str(images_dir / "3.png"), "duration_sec": 5.0, "text": "测试三"},
    ]

    built_indices: list[int] = []

    def _fake_build(*, media_dir, segments, audio_path=None, only_segment_indices=None, job=None, on_clip_done=None):
        for seg in segments:
            built_indices.append(seg["segment_index"])
            path = clips_dir / f"{seg['segment_index']}.mp4"
            path.write_bytes(b"mp4")
            if on_clip_done:
                on_clip_done(seg["id"], path)
        return SegmentClipsResult(
            segment_clip_paths=[(seg["id"], clips_dir / f"{seg['segment_index']}.mp4") for seg in segments]
        )

    with patch.object(media_mgr, "build_segment_clips", side_effect=_fake_build):
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            audio_path=None,
            scope="clips",
            job=None,
        )

    # 只有分镜2、3需要重新生成 clip
    assert built_indices == [2, 3], f"应只生成缺少 clip 的分镜, 实际={built_indices}"

    # 结果应包含所有3个分镜的 clip
    result_ids = {seg_id for seg_id, _ in result.clips.segment_clip_paths}
    assert result_ids == {101, 102, 103}, f"应包含所有分镜, 实际={result_ids}"


def test_produce_segments_all_clips_exist_skips_build(tmp_path: Path) -> None:
    """所有 clip 都已存在时完全跳过 clip 生成，不调用 build_segment_clips。"""
    from app.services.media.media_mgr import media_mgr

    media_dir = tmp_path / "18"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True)

    (images_dir / "1.png").write_bytes(b"png")
    (clips_dir / "1.mp4").write_bytes(b"mp4")

    segments = [
        {"id": 101, "segment_index": 1, "visual_mode": "wan_i2v", "image_path": str(images_dir / "1.png"), "duration_sec": 5.0, "text": "测试"},
    ]

    with patch.object(media_mgr, "build_segment_clips") as mock_build:
        result = segment_mgr.produce_segments(
            segments=segments,
            media_dir=media_dir,
            audio_path=None,
            scope="clips",
            job=None,
        )

    mock_build.assert_not_called()
    assert len(result.clips.segment_clip_paths) == 1
    assert result.clips.segment_clip_paths[0][0] == 101
