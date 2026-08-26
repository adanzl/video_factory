from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.segment.clip.video_agnes import (
    AgnesClipProvider,
    _backoff_seconds,
    _encode_image_data_uri,
    _extract_speak_windows,
    _normalize_submit_ids,
    _parse_speaking_sides,
    _pick_num_frames,
    _read_agnes_source_url,
    _resolve_i2v_image,
    _stabilize_motion_prompt,
)
from app.services.llm.llm_agnes import AgnesApiKey, AgnesQuotaExceeded
from app.utils.job_info import normalize_video_provider, resolve_video_provider
from app.utils.media_path import resolve_media_public_base_url


def test_backoff_seconds_timeout() -> None:
    assert _backoff_seconds(0, is_timeout=True) >= 45.0


def test_extract_speak_windows_new_and_legacy_formats() -> None:
    prompt = (
        "画面左边是昭昭，右边是灿灿。"
        "0.0-3.4秒右侧女孩开口说话，口型自然开合，说完即闭嘴，同时右手点动后停止，"
        "此时左侧男孩嘴巴闭合不动；"
        "3.4-8.4秒左侧男孩开口说话，口型自然开合，说完即闭嘴，同时拇指摩挲后定格。"
    )
    windows = _extract_speak_windows(prompt)
    assert windows == [(0.0, 3.4, "右侧女孩"), (3.4, 8.4, "左侧男孩")]

    legacy = "0.0-1.4秒左侧女孩张嘴说话，同时点头；1.4-2.5秒右侧男孩张嘴说话，同时耸肩。"
    assert _extract_speak_windows(legacy) == [
        (0.0, 1.4, "左侧女孩"),
        (1.4, 2.5, "右侧男孩"),
    ]
    # 三人站位：角色名按站位映射到侧边身份
    trio = (
        "画面左边是昭昭，中间是妈妈，右边是灿灿。"
        "0.0-5.3秒昭昭开口说话，口型自然开合，说完即闭嘴，同时摊手后停止；"
        "5.3-8.7秒灿灿开口说话，口型自然开合，说完即闭嘴，同时点指后定格。"
    )
    assert _extract_speak_windows(trio) == [
        (0.0, 5.3, "左侧男孩"),
        (5.3, 8.7, "右侧女孩"),
    ]
    # ambient 无说话窗口
    assert _extract_speak_windows("窗帘轻轻飘动，人物姿势保持不变。") == []


def test_parse_speaking_sides() -> None:
    assert _parse_speaking_sides("左侧") == {"左侧"}
    assert _parse_speaking_sides("右侧。") == {"右侧"}
    assert _parse_speaking_sides("中间") == {"中间"}
    assert _parse_speaking_sides("两者") == {"左侧", "右侧"}
    assert _parse_speaking_sides("多人") == {"左侧", "右侧"}
    assert _parse_speaking_sides("左侧和右侧都在说") == {"左侧", "右侧"}
    assert _parse_speaking_sides("无人") == set()
    assert _parse_speaking_sides("都没有说话") == set()
    assert _parse_speaking_sides("") is None
    assert _parse_speaking_sides("无法判断画面内容") is None


def test_parse_subtitle_hit() -> None:
    from app.services.segment.clip.video_agnes import _parse_subtitle_hit

    assert _parse_subtitle_hit("有字幕") is True
    assert _parse_subtitle_hit("有字幕。") is True
    assert _parse_subtitle_hit("无字幕") is False
    assert _parse_subtitle_hit("没有字幕") is False
    assert _parse_subtitle_hit("未见字幕") is False
    assert _parse_subtitle_hit("") is None
    assert _parse_subtitle_hit("看不清") is None


def test_subtitle_verify_hard_fails_after_retries(tmp_path: Path) -> None:
    from app.services.llm.llm_agnes import AgnesI2VError

    provider = AgnesClipProvider()
    image_path = tmp_path / "1.png"
    image_path.write_bytes(b"png")
    settings = SimpleNamespace(
        video_width=720,
        video_height=1280,
        agnes_video_mouth_verify=False,
        agnes_video_mouth_verify_attempts=2,
    )
    with (
        patch(
            "app.services.segment.clip.video_agnes.get_settings",
            return_value=settings,
        ),
        patch.object(provider, "_generate_raw") as mock_gen,
        patch(
            "app.services.segment.clip.video_agnes._sample_verify_windows",
            return_value=[(0.0, 3.0, "", ["data:image/jpeg;base64,xx"])],
        ),
        patch.object(provider, "_verify_no_burned_subtitles", return_value=False),
        patch(
            "app.services.segment.clip.video_agnes.clip_mgr.cue_total_duration",
            return_value=3.0,
        ),
        pytest.raises(AgnesI2VError, match="烧录字幕"),
    ):
        provider.build_segment_clip(
            image_path=image_path,
            subtitle_cues=[("x", 3.0)],
            output_path=tmp_path / "clip.mp4",
            motion_preset="ken_burns_slow",
            work_dir=tmp_path / "work",
            segment_index=11,
            motion_prompt="镜头固定不推近不拉远",
        )
    assert mock_gen.call_count == 2


def test_normalize_submit_ids_drops_task_prefixed_video_id() -> None:
    video_id, task_id = _normalize_submit_ids(
        video_id="task_hmLXl8ALGUeArDTsu7xBZHBaqgZYVNji",
        task_id="task_hmLXl8ALGUeArDTsu7xBZHBaqgZYVNji",
    )
    assert video_id is None
    assert task_id == "task_hmLXl8ALGUeArDTsu7xBZHBaqgZYVNji"


def test_normalize_submit_ids_keeps_distinct_video_id() -> None:
    video_id, task_id = _normalize_submit_ids(
        video_id="video_real",
        task_id="task_test",
    )
    assert video_id == "video_real"
    assert task_id == "task_test"


def test_extract_video_url_from_metadata() -> None:
    """completed 返回体的地址可能嵌在 metadata.url（线上实测）。"""
    body = {
        "id": "task_x",
        "video_id": "task_x",
        "status": "completed",
        "metadata": {
            "size_mapping": {"adjusted": True},
            "url": "https://platform-outputs.agnes-ai.space/videos/task_x.mp4",
        },
    }
    url = AgnesClipProvider._extract_video_url(body)  # noqa: SLF001
    assert url == "https://platform-outputs.agnes-ai.space/videos/task_x.mp4"


def test_agnes_poll_url_prefers_task_id() -> None:
    provider = AgnesClipProvider()
    url = provider._poll_url(  # noqa: SLF001
        video_id="video_real",
        task_id="task_test",
    )
    assert url.endswith("/videos/task_test")
    assert "agnesapi" not in url


def test_pick_num_frames() -> None:
    assert _pick_num_frames(2.5, 24) == 81
    assert _pick_num_frames(5.0, 24) == 121
    assert _pick_num_frames(20.0, 24) == 409
    assert _pick_num_frames(17.1, 24) == 409


def test_normalize_video_provider_agnes() -> None:
    assert normalize_video_provider("agnes_i2v") == "agnes_i2v"


def test_resolve_video_provider_agnes_override() -> None:
    settings = SimpleNamespace(clip_provider="ffmpeg")
    job = {"info": {"video_provider": "agnes_i2v"}}
    assert resolve_video_provider(job, visual_mode="static_motion", settings=settings) == "agnes_i2v"


def test_resolve_media_public_base_url_from_cors() -> None:
    settings = SimpleNamespace(
        media_public_base_url=None,
        get_cors_origins=lambda: ["http://localhost:5173", "https://example.com"],
    )
    assert resolve_media_public_base_url(settings) == "https://example.com"


def test_stabilize_motion_prompt() -> None:
    out = _stabilize_motion_prompt("slow zoom")
    assert "slow zoom" not in out.lower()
    assert "镜头固定" in out or "不推近" in out
    assert "面部表情与静图一致" in out
    # 旧稿推近用语提交前剔除，并补镜头锁定
    locked = _stabilize_motion_prompt("炉口青烟缓缓上升，镜头极缓推进")
    assert locked.startswith("纯视觉画面")
    assert "炉口青烟缓缓上升" in locked
    assert "面部表情与静图一致" in locked
    assert "不推近" in locked or "镜头固定" in locked
    # 已写表情锁定与固定机位则仍补无字 Style 前缀（无 clean 标记时）
    already = "妈妈举手停，面部表情与静图一致不微笑，镜头固定不推近不拉远"
    stabilized = _stabilize_motion_prompt(already)
    assert stabilized.startswith("纯视觉画面")
    assert already in stabilized
    # 站位句触发人数锁定（Style + 正面人数锁前置）
    casted = _stabilize_motion_prompt(
        "画面左边是灿灿，右边是昭昭。灿灿说话，同时点头。镜头固定不推近不拉远，"
        "面部表情与静图一致不微笑"
    )
    assert casted.startswith("纯视觉画面")
    assert "2人同框全程可见，灿灿、昭昭" in casted
    assert "无路人无额外人物" in casted
    assert "禁止路人" not in casted
    with_mom = _stabilize_motion_prompt(
        "画面左边是灿灿，右边是昭昭。妈妈说话，同时点头。镜头固定不推近不拉远，"
        "面部表情与静图一致不微笑"
    )
    assert "3人同框全程可见" in with_mom and "妈妈" in with_mom
    assert "从左到右是灿灿、昭昭、妈妈" in with_mom
    assert "禁止妈妈入画" not in with_mom
    assert "不被裁切" in with_mom


def test_stabilize_keyframe_tail_clean_hint_still_prefixes_visual_style() -> None:
    """尾部「无字幕」不能替代前置 Style；否则 I2V 仍易画出字幕。"""
    motion = (
        "画面左边是昭昭，右边是灿灿。"
        "0.0-3.3秒右侧女孩开口说话，口型自然开合，说完即闭嘴，同时双手叉腰时肩膀轻轻耸动后停止，"
        "此时左侧男孩嘴巴闭合不动；"
        "3.3-5.0秒左侧男孩开口说话，口型自然开合，说完即闭嘴，同时举起的右手手掌微微张开后定格，"
        "此时右侧女孩嘴巴闭合不动。"
        "说话时只动嘴唇和下巴，头部姿态与五官其余部分保持稳定。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，两人全程在画面内，画面干净无字幕无文字。"
    )
    out = _stabilize_motion_prompt(motion)
    assert out.startswith("纯视觉画面")
    assert "无任何字幕、水印、对话框或文字叠加" in out


def test_stabilize_uses_three_person_still_when_motion_is_two() -> None:
    """静图三人、运动写成左右两人时，不得锁成共2人把边上人吃掉。"""
    motion = (
        "画面左边是昭昭，右边是灿灿。"
        "0.0-5.7秒左侧男孩开口说话，口型自然开合，说完即闭嘴，同时点头后停止，"
        "此时右侧女孩嘴巴闭合不动。"
        "镜头固定，不推近不拉远，面部表情与静图一致不微笑"
    )
    still = (
        "画面从左到右是昭昭、妈妈、灿灿。"
        "中近景三人特写，严格左蓝T恤男孩昭昭、中妈妈、右粉卫衣女孩灿灿。"
    )
    out = _stabilize_motion_prompt(motion, image_prompt=still)
    assert out.startswith("纯视觉画面")
    assert "从左到右是昭昭、妈妈、灿灿" in out.split("画面左边是")[0]
    assert "不被裁切" in out
    assert "禁止妈妈入画" not in out
    assert "额外小孩" not in out.split("画面左边是")[0]

    two = AgnesClipProvider()._build_i2v_payload(  # noqa: SLF001
        prompt=out,
        image_ref="https://example.com/a.png",
        num_frames=81,
    )
    assert "多余小孩" not in two["negative_prompt"]
    assert "第三个小孩" not in two["negative_prompt"]


def test_cast_names_from_mom_in_middle() -> None:
    from app.services.segment.clip.video_agnes import _cast_names_from_text

    names = _cast_names_from_text(
        "画面左边是昭昭，右边是灿灿，妈妈在中间。"
    )
    assert names == ["昭昭", "妈妈", "灿灿"]


def test_stabilize_e_speakers_keep_mom_despite_two_person_motion() -> None:
    """E 粘性三人：运动写成左右两人时仍按 speakers 锁妈妈，禁止共2人。"""
    motion = (
        "画面左边是昭昭，右边是灿灿。"
        "0.0-5.7秒左侧男孩开口说话，口型自然开合，说完即闭嘴。"
        "镜头固定，不推近不拉远，面部表情与静图一致不微笑"
    )
    out = _stabilize_motion_prompt(
        motion,
        speakers=["昭昭", "灿灿", "妈妈"],
    )
    assert "3人同框全程可见，从左到右是昭昭、妈妈、灿灿" in out
    assert "禁止妈妈入画" not in out
    two = AgnesClipProvider()._build_i2v_payload(  # noqa: SLF001
        prompt=out,
        image_ref="https://example.com/a.png",
        num_frames=81,
    )
    assert "多余小孩" not in two["negative_prompt"]


def test_build_i2v_payload_includes_negative_prompt() -> None:
    provider = AgnesClipProvider()
    payload = provider._build_i2v_payload(
        prompt="微动",
        image_ref="https://example.com/a.png",
        num_frames=81,
        width=1280,
        height=720,
    )
    assert payload["mode"] == "ti2vid"
    assert payload["negative_prompt"].startswith("text overlay, speech bubble")
    assert "微笑" in payload["negative_prompt"]
    assert "快速推进" in payload["negative_prompt"]
    assert "第三人" not in payload["negative_prompt"]
    assert "third person" not in payload["negative_prompt"]
    assert "duplicate character" in payload["negative_prompt"]
    assert payload["prompt"] == "微动"

    two = provider._build_i2v_payload(
        prompt="画面左边是灿灿，右边是昭昭。灿灿说话，同时点头。",
        image_ref="https://example.com/a.png",
        num_frames=81,
        width=1280,
        height=720,
    )
    assert "成年男性" in two["negative_prompt"]
    assert "third person" in two["negative_prompt"]

    three = provider._build_i2v_payload(
        prompt="画面左边是灿灿，右边是昭昭。妈妈说话，同时点头。",
        image_ref="https://example.com/a.png",
        num_frames=81,
        width=1280,
        height=720,
    )
    assert "成年男性" not in three["negative_prompt"]
    assert "third person" not in three["negative_prompt"]


def test_encode_image_data_uri(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"png-bytes")
    uri = _encode_image_data_uri(image)
    assert uri.startswith("data:image/png;base64,")


def test_read_agnes_source_url_sidecar(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    sidecar = image.with_name(image.name + ".agnes_source_url")
    cdn = "https://storage.googleapis.com/agnes-aigc/test.png"
    sidecar.write_text(cdn, encoding="utf-8")
    assert _read_agnes_source_url(image) == cdn


def test_resolve_i2v_image_prefers_sidecar(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    sidecar = image.with_name(image.name + ".agnes_source_url")
    cdn = "https://storage.googleapis.com/agnes-aigc/aigc/images/test.png"
    sidecar.write_text(cdn, encoding="utf-8")
    assert _resolve_i2v_image(image) == cdn


def test_resolve_i2v_image_uses_data_uri(tmp_path: Path) -> None:
    image = tmp_path / "1.png"
    image.write_bytes(b"png")
    ref = _resolve_i2v_image(image)
    assert ref.startswith("data:image/png;base64,")


def test_agnes_i2v_poll_throttle_is_global() -> None:
    """多路并发共用全局 poll 间隔，避免状态查询 429。"""
    provider = AgnesClipProvider()
    provider._poll_interval_sec = 15.0  # noqa: SLF001
    AgnesClipProvider._last_poll_at = 0.0

    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    with (
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=[100.0, 100.0, 105.0, 115.0],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        provider._throttle_poll()  # noqa: SLF001  # 首次不 sleep
        provider._throttle_poll()  # noqa: SLF001  # 距上次 5s，还需等 10s

    assert len(sleeps) == 1
    assert abs(sleeps[0] - 10.0) < 0.01


def test_agnes_i2v_submit_interval_by_key() -> None:
    """付费 enterprise≈2 RPM(30s)，免费≈1 RPM(60s)；按 key 分开记时。"""
    provider = AgnesClipProvider()
    provider._submit_interval = 30.0  # noqa: SLF001
    provider._free_submit_interval = 60.0  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_key.clear()

    assert provider._submit_interval_for_key("primary") == 30.0  # noqa: SLF001
    assert provider._submit_interval_for_key("free") == 60.0  # noqa: SLF001

    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    with (
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=[100.0, 100.0, 130.0, 130.0],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        provider._throttle_submit("primary")  # noqa: SLF001
        provider._throttle_submit("free")  # noqa: SLF001

    # primary 首次、free 首次都不 sleep
    assert sleeps == []

    with (
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=[145.0, 145.0, 160.0, 160.0],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        # free 上次在 130，间隔 60 → 还需等 45s
        provider._throttle_submit("free")  # noqa: SLF001
        # primary 上次在 100，间隔 30 → 145 已够，不等
        provider._throttle_submit("primary")  # noqa: SLF001

    assert len(sleeps) == 1
    assert abs(sleeps[0] - 45.0) < 0.01


def test_agnes_i2v_submit_retries_http_429() -> None:
    """提交 429 是 RPM 窗口，应等满 1 分钟再试，不能当配额立刻失败。"""
    provider = AgnesClipProvider()
    provider._submit_max_retries = 2  # noqa: SLF001

    limited = MagicMock()
    limited.status_code = 429
    limited.ok = False
    limited.json.return_value = {
        "error": {
            "message": (
                "video generation rate limit exceeded: "
                "allows 1 requests per 1 minute(s)"
            ),
            "code": "rate_limit_exceeded",
        }
    }

    ok = MagicMock()
    ok.status_code = 200
    ok.ok = True
    ok.raise_for_status = MagicMock()

    sleeps: list[float] = []

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            side_effect=[limited, ok],
        ) as mock_req,
        patch(
            "app.services.segment.clip.video_agnes.time.sleep",
            side_effect=lambda sec: sleeps.append(sec),
        ),
    ):
        resp = provider._request(  # noqa: SLF001
            "POST", "https://example.com/videos", label="submit"
        )

    assert resp is ok
    assert mock_req.call_count == 2
    assert sleeps and sleeps[0] >= 60.0


def test_agnes_i2v_submit_429_exhausted_raises_quota() -> None:
    """提交 429 重试耗尽后再当配额，交给备用 Key。"""
    provider = AgnesClipProvider()
    provider._submit_max_retries = 2  # noqa: SLF001

    limited = MagicMock()
    limited.status_code = 429
    limited.ok = False
    limited.json.return_value = {
        "error": {"message": "rate limit", "code": "rate_limit_exceeded"}
    }

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            return_value=limited,
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep"),
        pytest.raises(AgnesQuotaExceeded),
    ):
        provider._request(  # noqa: SLF001
            "POST", "https://example.com/videos", label="submit"
        )


def test_agnes_clip_provider_submits_i2v_payload(tmp_path: Path) -> None:
    provider = AgnesClipProvider()
    image_path = tmp_path / "1.png"
    image_path.write_bytes(b"png")
    output_path = tmp_path / "clip.mp4"

    create_resp = MagicMock()
    create_resp.json.return_value = {
        "video_id": "video_test",
        "task_id": "task_test",
        "status": "queued",
    }
    create_resp.raise_for_status = MagicMock()

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "status": "completed",
        "remixed_from_video_id": "https://example.com/out.mp4",
    }
    poll_resp.raise_for_status = MagicMock()

    video_resp = MagicMock()
    video_resp.content = b"mp4-bytes"
    video_resp.raise_for_status = MagicMock()

    with (
        patch(
            "app.services.segment.clip.video_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "test-key")],
        ),
        patch.object(provider, "_request", side_effect=[create_resp, poll_resp]) as mock_request,
        patch("app.services.segment.clip.video_agnes.requests.get", return_value=video_resp),
        patch("app.services.segment.clip.video_agnes.probe_duration", return_value=5.0),
        patch("app.services.segment.clip.video_agnes.fit_video_duration") as mock_fit,
    ):
        mock_fit.side_effect = lambda src, dst, *_args, **_kwargs: dst.write_bytes(b"fit")
        provider.build_segment_clip(
            image_path=image_path,
            subtitle_cues=[("hello", 5.0)],
            output_path=output_path,
            motion_preset="ken_burns_slow",
            work_dir=tmp_path / "work",
            segment_index=1,
            motion_prompt="slow zoom",
            image_prompt="画面主体是宇宙飞船",
            width=720,
            height=1280,
        )

    create_call = mock_request.call_args_list[0]
    payload = create_call.kwargs["json"]
    assert payload["model"] == provider._model  # noqa: SLF001
    assert payload["mode"] == "ti2vid"
    assert payload["image"].startswith("data:image/png;base64,")
    assert payload["num_frames"] == 129
    assert "slow zoom" not in payload["prompt"].lower()
    assert "不推近" in payload["prompt"] or "镜头固定" in payload["prompt"]
    assert "宇宙飞船" not in payload["prompt"]

    poll_call = mock_request.call_args_list[1]
    assert poll_call.args[0] == "GET"
    assert poll_call.args[1].endswith("/videos/task_test")
    assert "agnesapi" not in poll_call.args[1]


def test_clip_batch_i2v_concurrency_respects_max_workers(tmp_path: Path) -> None:
    """单任务内 I2V 分镜应按 VIDEO_MAX_WORKERS 并行，且峰值不超过并发数。"""
    import gevent

    from app.config import get_settings
    from app.services.media import media_mgr as media_mgr_mod
    from app.services.media.media_mgr import media_mgr

    workers = 3
    media_mgr_mod._reset_i2v_semaphore_for_tests()
    settings = get_settings()

    media_dir = tmp_path / "job"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "1.png"
    image_path.write_bytes(b"png")

    segments = [
        {
            "id": 100 + i,
            "segment_index": i,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 3.0,
            "text": f"分镜{i}",
            "image_prompt": "test",
            "motion_prompt": "slow pan",
        }
        for i in range(1, 7)
    ]

    active = 0
    peak = 0

    def fake_build_segment_clip(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        gevent.sleep(0.12)
        active -= 1
        out = kwargs["output_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")

    persisted: list[int] = []

    with (
        patch.object(settings, "video_max_workers", workers),
        patch.object(settings, "mock_mode", False),
        patch.object(
            media_mgr_mod.clip_mgr,
            "build_segment_clip",
            side_effect=fake_build_segment_clip,
        ),
        patch.object(media_mgr, "_load_subtitle_cues", return_value=[]),
    ):
        result = media_mgr.build_segment_clips(
            media_dir=media_dir,
            segments=segments,
            on_clip_done=lambda seg_id, _path, *_unused: persisted.append(seg_id),
        )

    assert peak == workers
    assert len(result.segment_clip_paths) == 6
    assert sorted(persisted) == [101, 102, 103, 104, 105, 106]


def test_clip_batch_waits_for_all_workers_before_raise_on_partial_failure(
    tmp_path: Path,
) -> None:
    """有分镜失败时仍等其它路完成，成功的分镜应先 on_clip_done，最后再抛错。"""
    import gevent

    from app.config import get_settings
    from app.services.media import media_mgr as media_mgr_mod
    from app.services.media.media_mgr import media_mgr

    workers = 3
    media_mgr_mod._reset_i2v_semaphore_for_tests()
    settings = get_settings()

    media_dir = tmp_path / "job"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "1.png"
    image_path.write_bytes(b"png")

    segments = [
        {
            "id": 201,
            "segment_index": 1,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 3.0,
            "text": "a",
            "image_prompt": "test",
            "motion_prompt": "slow pan",
        },
        {
            "id": 202,
            "segment_index": 2,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 3.0,
            "text": "b",
            "image_prompt": "test",
            "motion_prompt": "slow pan",
        },
        {
            "id": 203,
            "segment_index": 3,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 3.0,
            "text": "c",
            "image_prompt": "test",
            "motion_prompt": "slow pan",
        },
    ]

    finished: list[int] = []

    def fake_build_segment_clip(**kwargs):
        index = kwargs["segment_index"]
        gevent.sleep(0.05 if index != 2 else 0.15)
        if index == 2:
            raise RuntimeError("segment 2 boom")
        out = kwargs["output_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        finished.append(index)

    persisted: list[int] = []

    with (
        patch.object(settings, "video_max_workers", workers),
        patch.object(settings, "mock_mode", False),
        patch.object(
            media_mgr_mod.clip_mgr,
            "build_segment_clip",
            side_effect=fake_build_segment_clip,
        ),
        patch.object(media_mgr, "_load_subtitle_cues", return_value=[]),
    ):
        with pytest.raises(RuntimeError, match="segment 2 boom"):
            media_mgr.build_segment_clips(
                media_dir=media_dir,
                segments=segments,
                on_clip_done=lambda seg_id, _path, *_unused: persisted.append(seg_id),
            )

    assert sorted(finished) == [1, 3]
    assert sorted(persisted) == [201, 203]


def test_on_clip_done_fires_before_all_spawns_finish(tmp_path: Path) -> None:
    """首个 clip 完成须立刻落库；不得等 Pool 列表推导把剩余任务都 spawn 完。"""
    import gevent
    from gevent.event import Event

    from app.config import get_settings
    from app.services.media import media_mgr as media_mgr_mod
    from app.services.media.media_mgr import media_mgr

    media_mgr_mod._reset_i2v_semaphore_for_tests()
    settings = get_settings()

    media_dir = tmp_path / "job"
    images_dir = media_dir / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "1.png"
    image_path.write_bytes(b"png")

    segments = [
        {
            "id": 300 + i,
            "segment_index": i,
            "visual_mode": "wan_i2v",
            "image_path": str(image_path),
            "duration_sec": 3.0,
            "text": f"分镜{i}",
            "image_prompt": "test",
            "motion_prompt": "slow pan",
        }
        for i in range(1, 7)
    ]

    first_callback = Event()
    allow_slow = Event()
    callbacks: list[int] = []

    def fake_build_segment_clip(**kwargs):
        index = int(kwargs["segment_index"])
        if index <= 2:
            gevent.sleep(0.05)
            out = kwargs["output_path"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"mp4")
            return
        assert first_callback.wait(timeout=2), "on_clip_done never fired"
        assert allow_slow.wait(timeout=2), "test did not release slow tasks"
        out = kwargs["output_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")

    def on_done(seg_id: int, *_args) -> None:
        callbacks.append(seg_id)
        if len(callbacks) == 1:
            first_callback.set()

    with (
        patch.object(settings, "video_max_workers", 2),
        patch.object(settings, "mock_mode", False),
        patch.object(
            media_mgr_mod.clip_mgr,
            "build_segment_clip",
            side_effect=fake_build_segment_clip,
        ),
        patch.object(media_mgr, "_load_subtitle_cues", return_value=[]),
    ):
        worker = gevent.spawn(
            media_mgr.build_segment_clips,
            media_dir=media_dir,
            segments=segments,
            on_clip_done=on_done,
        )
        assert first_callback.wait(timeout=2), "callback blocked by Pool.spawn"
        allow_slow.set()
        result = worker.get(timeout=5)

    assert len(callbacks) == 6
    assert sorted(seg_id for seg_id, _ in result.segment_clip_paths) == list(
        range(301, 307)
    )


def test_agnes_i2v_poll_stops_on_job_abort(tmp_path: Path) -> None:
    """abort 后轮询应立刻抛 JobCancelledError，不再继续拉状态。"""
    from app.utils.job_cancel import JobCancelledError, job_cancel

    job_id = 9001
    job_cancel.clear(job_id)
    provider = AgnesClipProvider()
    provider._poll_interval_sec = 0.0  # noqa: SLF001
    provider._active_job_id = job_id  # noqa: SLF001
    AgnesClipProvider._last_poll_at = 0.0

    poll_calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        _ = method, url, kwargs
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            job_cancel.request(job_id)
        resp = MagicMock()
        resp.json.return_value = {"status": "in_progress"}
        resp.raise_for_status = MagicMock()
        return resp

    with (
        patch.object(provider, "_request", side_effect=fake_request),
        patch("app.services.segment.clip.video_agnes.time.sleep"),
    ):
        try:
            with pytest.raises(JobCancelledError):
                provider._poll_task(  # noqa: SLF001
                    headers={"Authorization": "Bearer x"},
                    video_id="task_abort_test",
                    task_id=None,
                    output_path=tmp_path / "out.mp4",
                )
        finally:
            job_cancel.clear(job_id)
            provider._active_job_id = None  # noqa: SLF001

    # 第 1 次 poll 后设置 abort，下一轮循环开头应立刻退出
    assert poll_calls["n"] == 1
