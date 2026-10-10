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
    _pick_seconds,
    _read_agnes_source_url,
    _remap_prompt_timeline,
    _resolve_aspect_ratio,
    _resolve_i2v_image,
    _stabilize_motion_prompt,
)
from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesI2VError,
    AgnesQuotaExceeded,
    AgnesUpstreamUnavailable,
)
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


def test_agnes_poll_url_prefers_video_id_with_model() -> None:
    provider = AgnesClipProvider()
    provider._model = "agnes-video-2.5-flash"  # noqa: SLF001
    url = provider._poll_url(  # noqa: SLF001
        video_id="video_real",
        task_id="task_test",
    )
    assert "agnesapi" in url
    assert "video_id=video_real" in url
    assert "model_name=agnes-video-2.5-flash" in url


def test_pick_seconds_rounds_half_up() -> None:
    assert _pick_seconds(2.5) == "4"  # 钳制下限
    assert _pick_seconds(4.4) == "4"
    assert _pick_seconds(4.5) == "5"  # 四舍五入
    assert _pick_seconds(5.0) == "5"
    assert _pick_seconds(11.5) == "12"
    assert _pick_seconds(20.0) == "12"  # 钳制上限


def test_resolve_aspect_ratio() -> None:
    assert _resolve_aspect_ratio(1280, 720) == "16:9"
    assert _resolve_aspect_ratio(720, 1280) == "9:16"
    assert _resolve_aspect_ratio(720, 720) == "1:1"
    assert _resolve_aspect_ratio(1680, 720) == "21:9"
    assert _resolve_aspect_ratio(960, 720) == "4:3"
    assert _resolve_aspect_ratio(720, 960) == "3:4"
    # 非标准尺寸取最近预设
    assert _resolve_aspect_ratio(1000, 700) == "4:3"


def test_remap_prompt_timeline() -> None:
    src = "0.0-3.4秒右侧女孩开口说话；3.4-5.3秒左侧男孩开口说话。"
    out = _remap_prompt_timeline(src, 5.3, 5.0)
    assert "0.0-3.2秒" in out
    assert "3.2-5.0秒" in out
    assert _remap_prompt_timeline(src, 5.0, 5.0) == src


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
    assert "颜色与首帧完全一致" in out
    assert "不补色不改色" in out
    # 旧稿推近用语提交前剔除，并补镜头锁定
    locked = _stabilize_motion_prompt("炉口青烟缓缓上升，镜头极缓推进")
    assert locked.startswith("纯视觉画面")
    assert locked.index("颜色与首帧完全一致") < locked.index("炉口青烟")
    assert "炉口青烟缓缓上升" in locked
    assert "面部表情与静图一致" in locked
    assert "不推近" in locked or "镜头固定" in locked
    # 已写表情锁定与固定机位则仍补无字 Style 前缀（无 clean 标记时）
    already = "妈妈举手停，面部表情与静图一致不微笑，镜头固定不推近不拉远"
    stabilized = _stabilize_motion_prompt(already)
    assert stabilized.startswith("纯视觉画面")
    assert already in stabilized
    assert "不补色不改色" in stabilized
    # 已写色彩锁则不重复补
    colored = _stabilize_motion_prompt(
        "所有区域颜色与首帧完全一致，不补色不改色，"
        "纱帘轻动，镜头固定不推近不拉远，面部表情与静图一致不微笑"
    )
    assert colored.count("不补色不改色") == 1
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
        seconds="5",
        aspect_ratio="9:16",
    )
    assert two["mode"] == "keyframe"
    assert two["first_frame"] == "https://example.com/a.png"
    assert "negative_prompt" not in two
    assert "多余小孩" not in two["prompt"]
    assert "第三个小孩" not in two["prompt"]


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
        seconds="5",
        aspect_ratio="9:16",
    )
    assert "negative_prompt" not in two
    assert "多余小孩" not in two["prompt"]


def test_build_i2v_payload_flash_keyframe() -> None:
    provider = AgnesClipProvider()
    payload = provider._build_i2v_payload(
        prompt="微动",
        image_ref="https://example.com/a.png",
        seconds="5",
        aspect_ratio="16:9",
    )
    assert payload["mode"] == "keyframe"
    assert payload["seconds"] == "5"
    assert payload["size"] == "720P"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["first_frame"] == "https://example.com/a.png"
    assert payload["n"] == 1
    assert "image" not in payload
    assert "num_frames" not in payload
    assert "frame_rate" not in payload
    assert "width" not in payload
    assert "height" not in payload
    assert "negative_prompt" not in payload
    assert payload["prompt"] == "微动"


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


def test_agnes_i2v_submit_interval_by_pool() -> None:
    """限制池计时：付费池（TokenPlan 5 RPM）与免费池（1 RPM）各算各的。"""
    provider = AgnesClipProvider()
    provider._submit_interval = 12.0  # noqa: SLF001
    provider._free_submit_interval = 60.0  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_pool.clear()
    AgnesClipProvider._cooldown_until_by_pool.clear()

    assert provider._pool_for_key("primary") == "paid_intl"  # noqa: SLF001
    assert provider._pool_for_key("cn_paid") == "paid_cn"  # noqa: SLF001
    assert provider._pool_for_key("free") == "free_intl"  # noqa: SLF001
    # 跨站点恒分池：国内免费与国际免费不再共用池
    assert provider._pool_for_key("cn_free") == "free_cn"  # noqa: SLF001
    assert provider._interval_for_pool("paid_intl") == 12.0  # noqa: SLF001
    assert provider._interval_for_pool("paid_cn") == 12.0  # noqa: SLF001
    assert provider._interval_for_pool("free_intl") == 60.0  # noqa: SLF001
    assert provider._interval_for_pool("free_cn") == 60.0  # noqa: SLF001

    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    with (
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=[100.0, 100.0, 100.0, 100.0],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        provider._throttle_submit("primary")  # noqa: SLF001
        provider._throttle_submit("free")  # noqa: SLF001

    # 两个池首次都不 sleep
    assert sleeps == []

    with (
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=[115.0, 115.0, 115.0, 115.0],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        # 付费池上次在 100，间隔 12 → 115 已够，不等
        provider._throttle_submit("primary")  # noqa: SLF001
        # 免费池上次在 100，间隔 60 → 还需等 45s
        provider._throttle_submit("free")  # noqa: SLF001

    assert len(sleeps) == 1
    assert abs(sleeps[0] - 45.0) < 0.01


def test_agnes_i2v_free_pools_split_across_sites() -> None:
    """跨站点两把免费 key 恒为两池（仅同站点多把才看 AGNES_FREE_POOL_SHARED）。"""
    provider = AgnesClipProvider()
    for shared in (False, True):
        provider._free_pool_shared = shared  # noqa: SLF001
        assert provider._pool_for_key("free") == "free_intl"  # noqa: SLF001
        assert provider._pool_for_key("cn_free") == "free_cn"  # noqa: SLF001


def test_agnes_i2v_submit_retries_http_429() -> None:
    """提交 429 应立刻冻结该池抛配额错误（交给 key 链换 key），不再原地睡窗口。"""
    provider = AgnesClipProvider()
    provider._submit_max_retries = 4  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_pool.clear()
    AgnesClipProvider._cooldown_until_by_pool.clear()

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

    sleeps: list[float] = []

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            side_effect=[limited, limited, limited, limited],
        ) as mock_req,
        patch(
            "app.services.segment.clip.video_agnes.time.sleep",
            side_effect=lambda sec: sleeps.append(sec),
        ),
        pytest.raises(AgnesQuotaExceeded),
    ):
        provider._request(  # noqa: SLF001
            "POST",
            "https://example.com/videos",
            label="submit",
            key_label="free",
        )

    assert mock_req.call_count == 1, "429 不该在原地重试整轮"
    assert not [s for s in sleeps if s >= 60.0]
    assert provider._pool_cooldown_left("free") > 0  # noqa: SLF001


def test_agnes_i2v_retry_gate_respects_pool_interval() -> None:
    """503 重试也要过闸门：付费池两次请求之间至少隔一个间隔。"""
    provider = AgnesClipProvider()
    provider._submit_interval = 12.0  # noqa: SLF001
    provider._submit_max_retries = 3  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_pool.clear()
    AgnesClipProvider._cooldown_until_by_pool.clear()

    bad = MagicMock()
    bad.status_code = 503
    bad.ok = False
    bad.json.return_value = {}

    ok = MagicMock()
    ok.status_code = 200
    ok.ok = True
    ok.raise_for_status = MagicMock()

    clock = {"now": 1000.0}
    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        clock["now"] += sec

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            side_effect=[bad, ok],
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        resp = provider._request(  # noqa: SLF001
            "POST",
            "https://example.com/videos",
            label="submit",
            key_label="primary",
        )

    assert resp is ok
    # 第一次请求无等待；503 退避 2s 后，第二次请求前闸门补到 12s
    assert sleeps[0] == 2.0
    assert abs(sleeps[1] - 10.0) < 0.01


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
        patch(
            "app.services.segment.clip.video_agnes.get_settings",
            return_value=SimpleNamespace(
                video_width=720,
                video_height=1280,
                ffmpeg_crf=23,
                agnes_video_mouth_verify=False,
                agnes_video_mouth_verify_attempts=1,
            ),
        ),
        patch(
            "app.services.segment.clip.video_agnes._scale_video_to_duration",
            side_effect=lambda src, dst, target: dst.write_bytes(b"scaled") or dst,
        ) as mock_scale,
        patch("app.services.segment.clip.video_agnes.fit_video_duration") as mock_fit,
    ):
        mock_fit.side_effect = lambda src, dst, *_args, **_kwargs: dst.write_bytes(b"fit")
        provider.build_segment_clip(
            image_path=image_path,
            subtitle_cues=[("hello", 5.3)],
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
    assert payload["mode"] == "keyframe"
    assert payload["seconds"] == "5"  # 5.3 四舍五入
    assert payload["size"] == "720P"
    assert payload["aspect_ratio"] == "9:16"  # 720x1280 约分
    assert payload["first_frame"].startswith("data:image/png;base64,")
    assert "num_frames" not in payload
    assert "slow zoom" not in payload["prompt"].lower()
    assert "不推近" in payload["prompt"] or "镜头固定" in payload["prompt"]
    assert "宇宙飞船" not in payload["prompt"]

    poll_call = mock_request.call_args_list[1]
    assert poll_call.args[0] == "GET"
    assert "agnesapi" in poll_call.args[1]
    assert "video_id=video_test" in poll_call.args[1]
    assert f"model_name={provider._model}" in poll_call.args[1]  # noqa: SLF001
    assert mock_scale.called
    assert mock_scale.call_args.args[2] == 5.3


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


def test_agnes_key_chain_switches_on_429_without_waiting() -> None:
    """429（含免费档报文）应立刻换下一把 key，不在被限的池上等满窗口。"""
    provider = AgnesClipProvider()
    provider._rate_limit_cooldown_sec = 60.0  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_pool.clear()
    AgnesClipProvider._cooldown_until_by_pool.clear()
    keys = [
        AgnesApiKey("primary", "k-paid", "https://apihub.agnes-ai.com/v1"),
        AgnesApiKey("free", "k-free", "https://apihub.agnes-ai.com/v1"),
    ]
    calls: list[str] = []
    sleeps: list[float] = []

    def operation(key: AgnesApiKey) -> str:
        calls.append(key.label)
        if key.label == "primary":
            provider._mark_pool_cooldown("primary", seconds=60.0)  # noqa: SLF001
            raise AgnesQuotaExceeded("429 rate_limit_exceeded")
        return "ok"

    with (
        patch(
            "app.services.segment.clip.video_agnes.agnes_api_keys",
            return_value=keys,
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: 1000.0,
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.sleep",
            side_effect=lambda sec: sleeps.append(sec),
        ),
    ):
        assert provider._with_api_key_fallback(operation) == "ok"  # noqa: SLF001

    assert calls == ["primary", "free"]
    assert sleeps == [], "换 key 前不该先睡一个 RPM 窗口"


def test_agnes_key_chain_waits_when_all_pools_cooling() -> None:
    """所有池都在冷却时整批等待最早恢复，而不是把 stage 判失败。"""
    provider = AgnesClipProvider()
    provider._key_wait_budget_sec = 300.0  # noqa: SLF001
    AgnesClipProvider._cooldown_until_by_pool.clear()
    AgnesClipProvider._last_submit_at_by_pool.clear()
    keys = [AgnesApiKey("primary", "k-paid", "https://apihub.agnes-ai.com/v1")]
    clock = {"now": 1000.0}
    sleeps: list[float] = []
    attempts = {"n": 0}

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        clock["now"] += sec

    def operation(_key: AgnesApiKey) -> str:
        attempts["n"] += 1
        return "ok"

    with (
        patch(
            "app.services.segment.clip.video_agnes.agnes_api_keys",
            return_value=keys,
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
    ):
        provider._mark_pool_cooldown("primary", seconds=30.0)  # noqa: SLF001
        assert provider._with_api_key_fallback(operation) == "ok"  # noqa: SLF001

    assert sleeps == [30.0]
    assert attempts["n"] == 1


def test_agnes_key_chain_gives_up_after_wait_budget() -> None:
    """冷却窗口超过等待预算时放弃（有界等待，避免无限挂住 worker）。"""
    provider = AgnesClipProvider()
    provider._key_wait_budget_sec = 5.0  # noqa: SLF001
    AgnesClipProvider._cooldown_until_by_pool.clear()
    keys = [AgnesApiKey("primary", "k-paid", "https://apihub.agnes-ai.com/v1")]

    with (
        patch(
            "app.services.segment.clip.video_agnes.agnes_api_keys",
            return_value=keys,
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: 1000.0,
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep") as mock_sleep,
        pytest.raises(AgnesI2VError),
    ):
        provider._mark_pool_cooldown("primary", seconds=60.0)  # noqa: SLF001
        provider._with_api_key_fallback(lambda key: "ok")  # noqa: SLF001

    mock_sleep.assert_not_called()


def test_agnes_poll_request_not_gated_by_submit_throttle() -> None:
    """轮询请求不带 key_label，不应触发提交闸门。"""
    provider = AgnesClipProvider()
    ok = MagicMock()
    ok.status_code = 200
    ok.ok = True
    ok.raise_for_status = MagicMock()

    with (
        patch("app.services.segment.clip.video_agnes.requests.request", return_value=ok),
        patch.object(provider, "_throttle_submit") as mock_gate,
    ):
        provider._request("GET", "https://example.com/poll", label="poll")  # noqa: SLF001

    mock_gate.assert_not_called()


def _upstream_reset() -> None:
    AgnesClipProvider._upstream_retry_at = 0.0  # noqa: SLF001
    AgnesClipProvider._upstream_fail_streak = 0  # noqa: SLF001
    AgnesClipProvider._upstream_queue_full = False  # noqa: SLF001
    AgnesClipProvider._last_submit_at_by_pool.clear()
    AgnesClipProvider._cooldown_until_by_pool.clear()
    AgnesClipProvider._pool_cooldown_reason.clear()


def test_submit_two_5xx_raises_upstream_unavailable() -> None:
    """提交遇到两个域名都 5xx：立刻判为上游不可用，不再连打 4 次。"""
    provider = AgnesClipProvider()
    provider._submit_max_retries = 4  # noqa: SLF001
    _upstream_reset()

    first = MagicMock()
    first.status_code = 503
    first.ok = False
    first.json.return_value = {}
    second = MagicMock()
    second.status_code = 503
    second.ok = False
    second.json.return_value = {}
    ok = MagicMock()
    ok.status_code = 200
    ok.ok = True
    ok.raise_for_status = MagicMock()

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            side_effect=[first, second, ok],
        ) as mock_req,
        patch("app.services.segment.clip.video_agnes.time.sleep"),
        pytest.raises(AgnesUpstreamUnavailable),
    ):
        provider._request(  # noqa: SLF001
            "POST",
            "https://apihub.agnes-ai.com/v1/videos",
            label="submit",
            key_label="primary",
        )

    # 第一次 503 换域名，第二次 503 即停：只打 2 次
    assert mock_req.call_count == 2


def test_upstream_unavailable_does_not_burn_keys() -> None:
    """503 不该被当成「这把 key 坏了」：不换 key，冷却后原 key 重试。"""
    provider = AgnesClipProvider()
    provider._upstream_cooldown_base_sec = 20.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    provider._upstream_wait_budget_sec = 3600.0  # noqa: SLF001
    _upstream_reset()
    keys = [
        AgnesApiKey("primary", "k-paid", "https://apihub.agnes-ai.com/v1"),
        AgnesApiKey("free", "k-free", "https://apihub.agnes-ai.com/v1"),
    ]
    calls: list[str] = []
    sleeps: list[float] = []
    clock = {"now": 1000.0}

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        clock["now"] += sec

    def operation(key: AgnesApiKey) -> str:
        calls.append(key.label)
        if len(calls) == 1:
            raise AgnesUpstreamUnavailable("agnes upstream unavailable: HTTP 503")
        return "ok"

    with (
        patch("app.services.segment.clip.video_agnes.agnes_api_keys", return_value=keys),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
        patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0),
    ):
        assert provider._with_api_key_fallback(operation) == "ok"  # noqa: SLF001

    # 只用回 key 链第一把（没被烧掉），且中途等过一次冷却
    assert calls == ["primary", "primary"]
    assert len(sleeps) == 1
    assert sleeps[0] >= 20.0
    assert provider._upstream_cooldown_left() == 0.0  # noqa: SLF001  # 成功后清零


def test_upstream_wait_budget_exceeded_raises() -> None:
    """上游长期不可用：等待超出预算后失败，不无限挂住 worker。"""
    provider = AgnesClipProvider()
    provider._upstream_cooldown_base_sec = 300.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    provider._upstream_wait_budget_sec = 60.0  # noqa: SLF001
    _upstream_reset()
    keys = [AgnesApiKey("primary", "k-paid", "https://apihub.agnes-ai.com/v1")]
    clock = {"now": 1000.0}

    def operation(_key: AgnesApiKey) -> str:
        raise AgnesUpstreamUnavailable("agnes upstream unavailable: HTTP 503")

    with (
        patch("app.services.segment.clip.video_agnes.agnes_api_keys", return_value=keys),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep") as mock_sleep,
        patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0),
        pytest.raises(AgnesUpstreamUnavailable),
    ):
        provider._with_api_key_fallback(operation)  # noqa: SLF001

    mock_sleep.assert_not_called()


def test_upstream_streak_backs_off_and_resets_on_success() -> None:
    """冷却指数退避（20→40→80…封顶），成功一次即清零。"""
    provider = AgnesClipProvider()
    provider._upstream_cooldown_base_sec = 20.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    _upstream_reset()

    with (
        patch("app.services.segment.clip.video_agnes.time.monotonic", return_value=1000.0),
        patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0),
    ):
        delays = [provider._note_upstream_failure() for _ in range(6)]  # noqa: SLF001

    assert delays == [20.0, 40.0, 80.0, 160.0, 300.0, 300.0]
    with patch("app.services.segment.clip.video_agnes.time.monotonic", return_value=1000.0):
        provider._note_upstream_success()  # noqa: SLF001
    assert AgnesClipProvider._upstream_fail_streak == 0  # noqa: SLF001
    assert provider._upstream_cooldown_left() >= 0.0  # noqa: SLF001


def test_queue_full_body_recognized() -> None:
    """503 body 是 video_queue_full 时要识别出来（此前完全没记 body）。"""
    from app.services.segment.clip.video_agnes import (
        _body_summary_for_log,
        _is_queue_full_body,
    )

    body = {
        "code": "video_queue_full",
        "message": "video queue is full, please retry later",
        "data": None,
    }
    assert _is_queue_full_body(body)
    assert "video_queue_full" in _body_summary_for_log(body)
    # 网关故障、配额类报文不应误判
    assert not _is_queue_full_body({"code": "invalid_request", "message": "prompt is required"})
    assert not _is_queue_full_body(None)
    assert not _is_queue_full_body("<html>520 unknown error</html>")


def test_submit_queue_full_stops_immediately_without_host_failover() -> None:
    """队列满：不换域名（同后端）、不在原地重试，直接进冷却。"""
    provider = AgnesClipProvider()
    provider._submit_max_retries = 4  # noqa: SLF001
    provider._queue_full_cooldown_base_sec = 120.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    _upstream_reset()

    limited = MagicMock()
    limited.status_code = 503
    limited.ok = False
    limited.json.return_value = {
        "code": "video_queue_full",
        "message": "video queue is full, please retry later",
    }

    with (
        patch(
            "app.services.segment.clip.video_agnes.requests.request",
            side_effect=[limited, limited, limited, limited],
        ) as mock_req,
        patch("app.services.segment.clip.video_agnes.time.sleep"),
        pytest.raises(AgnesUpstreamUnavailable) as excinfo,
    ):
        provider._request(  # noqa: SLF001
            "POST",
            "https://apihub.agnes-ai.com/v1/videos",
            label="submit",
            key_label="primary",
        )

    assert excinfo.value.queue_full is True
    assert "video_queue_full" in str(excinfo.value)
    assert mock_req.call_count == 1, "队列满不该再换域名重试"


def test_queue_full_rotates_to_next_pool_instead_of_global_cooldown() -> None:
    """某池队列满只冻结该池，同轮轮换到下一池，不升级为全局冷却。"""
    provider = AgnesClipProvider()
    provider._queue_full_cooldown_base_sec = 120.0  # noqa: SLF001
    _upstream_reset()
    keys = [
        AgnesApiKey("primary", "k-paid-intl", "https://apihub.agnes-ai.com/v1"),
        AgnesApiKey("cn_paid", "k-paid-cn", "https://api.agnes-ai.cn/v1"),
        AgnesApiKey("free", "k-free-intl", "https://apihub.agnes-ai.com/v1"),
    ]
    calls: list[str] = []
    sleeps: list[float] = []

    def operation(key: AgnesApiKey) -> str:
        calls.append(key.label)
        if key.label != "free":
            raise AgnesUpstreamUnavailable(
                "agnes upstream unavailable: HTTP 503 (queue full)",
                queue_full=True,
            )
        return "ok"

    with (
        patch("app.services.segment.clip.video_agnes.agnes_api_keys", return_value=keys),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: 1000.0,
        ),
        patch(
            "app.services.segment.clip.video_agnes.time.sleep",
            side_effect=lambda sec: sleeps.append(sec),
        ),
    ):
        assert provider._with_api_key_fallback(operation) == "ok"  # noqa: SLF001

    assert calls == ["primary", "cn_paid", "free"], "两个满池应依次轮换到可用池"
    assert sleeps == [], "还有可用池时不该整体等待"
    assert provider.upstream_backpressure_active() is False  # noqa: SLF001
    assert (  # noqa: SLF001
        AgnesClipProvider._pool_cooldown_reason["paid_intl"] == "queue_full"
    )
    assert (  # noqa: SLF001
        AgnesClipProvider._pool_cooldown_reason["paid_cn"] == "queue_full"
    )


def test_all_pools_queue_full_escalates_to_global_cooldown() -> None:
    """四个限制池全满：升级为全局冷却，并在超预算时以队列满原因失败。"""
    provider = AgnesClipProvider()
    provider._queue_full_cooldown_base_sec = 120.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    provider._upstream_wait_budget_sec = 60.0  # noqa: SLF001
    _upstream_reset()
    keys = [
        AgnesApiKey("primary", "k-paid-intl", "https://apihub.agnes-ai.com/v1"),
        AgnesApiKey("cn_paid", "k-paid-cn", "https://api.agnes-ai.cn/v1"),
    ]
    clock = {"now": 1000.0}
    calls: list[str] = []

    def _fake_sleep(sec: float) -> None:
        clock["now"] += sec

    def operation(key: AgnesApiKey) -> str:
        calls.append(key.label)
        raise AgnesUpstreamUnavailable(
            "agnes upstream unavailable: HTTP 503 (queue full)",
            queue_full=True,
        )

    with (
        patch("app.services.segment.clip.video_agnes.agnes_api_keys", return_value=keys),
        patch(
            "app.services.segment.clip.video_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch("app.services.segment.clip.video_agnes.time.sleep", side_effect=_fake_sleep),
        patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0),
        pytest.raises(AgnesUpstreamUnavailable) as excinfo,
    ):
        provider._with_api_key_fallback(operation)  # noqa: SLF001

    assert excinfo.value.queue_full is True
    assert calls == ["primary", "cn_paid"] * (len(calls) // 2), "每轮都该轮换两池"


def test_queue_full_uses_longer_cooldown_base() -> None:
    """队列满冷却基准更长（默认 120s），排空是分钟级。"""
    provider = AgnesClipProvider()
    provider._upstream_cooldown_base_sec = 20.0  # noqa: SLF001
    provider._queue_full_cooldown_base_sec = 120.0  # noqa: SLF001
    provider._upstream_cooldown_max_sec = 300.0  # noqa: SLF001
    _upstream_reset()

    with (
        patch("app.services.segment.clip.video_agnes.time.monotonic", return_value=1000.0),
        patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0),
    ):
        first = provider._note_upstream_failure(queue_full=True)  # noqa: SLF001
        second = provider._note_upstream_failure(queue_full=True)  # noqa: SLF001
        assert provider.upstream_queue_full_active() is True
        provider._note_upstream_success()  # noqa: SLF001
        third = provider._note_upstream_failure(queue_full=False)  # noqa: SLF001

    assert first == 120.0
    assert second == 240.0
    assert third == 20.0, "普通 5xx 仍用 20s 基准"
    assert provider.upstream_queue_full_active() is False


def test_clip_batch_workers_backs_off_on_backpressure() -> None:
    """i2v 上游背压时本批并发退回 1（队列满时提交越多越糟）。"""
    from app.services.media.media_mgr import _clip_batch_workers

    with (
        patch("app.services.media.media_mgr._agnes_i2v_backpressure_active", return_value=True),
        patch("app.services.media.media_mgr.get_settings") as mock_settings,
    ):
        mock_settings.return_value.video_max_workers = 2
        assert _clip_batch_workers(uses_i2v=True, mock=False) == 1

    with (
        patch("app.services.media.media_mgr._agnes_i2v_backpressure_active", return_value=False),
        patch("app.services.media.media_mgr.get_settings") as mock_settings,
    ):
        mock_settings.return_value.video_max_workers = 2
        assert _clip_batch_workers(uses_i2v=True, mock=False) == 2
        # 非 i2v / mock 恒为 1
        assert _clip_batch_workers(uses_i2v=False, mock=False) == 1
        assert _clip_batch_workers(uses_i2v=True, mock=True) == 1


def test_upstream_backpressure_flag_feeds_media_mgr() -> None:
    """真实 provider 的背压标志能传到并发层判定。"""
    from app.services.media.media_mgr import _agnes_i2v_backpressure_active

    _upstream_reset()
    with patch(
        "app.services.segment.clip.video_agnes.time.monotonic", return_value=1000.0
    ):
        assert _agnes_i2v_backpressure_active() is False
        with patch("app.services.segment.clip.video_agnes.random.uniform", return_value=1.0):
            AgnesClipProvider()._note_upstream_failure(queue_full=True)  # noqa: SLF001
        # 冷却期内（1000 < retry_at=1120）应报背压
        assert _agnes_i2v_backpressure_active() is True


def test_prioritize_non_i2v_keeps_ffmpeg_first() -> None:
    """i2v 会冷却等待，非 i2v 段应先建，免被占槽拖住。"""
    from app.services.media.media_mgr import MediaMgr

    mgr = MediaMgr.__new__(MediaMgr)  # 不跑 __init__，只测纯排序逻辑
    segs = [
        {"segment_index": 1, "visual_mode": "static_motion"},
        {"segment_index": 2, "visual_mode": "static_motion"},
        {"segment_index": 3, "visual_mode": "static_motion"},
        {"segment_index": 4, "visual_mode": "static_motion"},
    ]
    providers = {1: "agnes_i2v", 2: "ffmpeg", 3: "agnes_i2v", 4: "ffmpeg"}

    def _resolve(*, visual_mode, job=None, segment=None):
        return providers[segment["segment_index"]]

    mgr._resolve_clip_provider = _resolve  # type: ignore[method-assign]  # noqa: SLF001
    ordered = mgr._prioritize_non_i2v(segs, job=None)  # noqa: SLF001
    assert [s["segment_index"] for s in ordered] == [2, 4, 1, 3]

    # 全是 i2v 或全是 ffmpeg 时保持原序（不做无谓重排）
    providers.clear()
    providers.update({1: "agnes_i2v", 2: "agnes_i2v", 3: "agnes_i2v", 4: "agnes_i2v"})
    assert [s["segment_index"] for s in mgr._prioritize_non_i2v(segs, job=None)] == [  # noqa: SLF001
        1, 2, 3, 4
    ]
    providers.clear()
    providers.update({1: "ffmpeg", 2: "ffmpeg", 3: "ffmpeg", 4: "ffmpeg"})
    assert [s["segment_index"] for s in mgr._prioritize_non_i2v(segs, job=None)] == [  # noqa: SLF001
        1, 2, 3, 4
    ]


def test_resume_job_does_not_prepare() -> None:
    """续跑入口必须 prepare=False（否则会清空已完成产物）。"""
    from app.services.job.job_mgr import JobMgr

    calls: dict = {}

    def _fake_submit(self, job_id, action, run, **kwargs):  # noqa: ANN001
        calls["job_id"] = job_id
        calls["action"] = action
        calls.update(kwargs)
        return {"id": job_id, "stage": action, "status": "running"}

    with (
        patch.object(JobMgr, "get_job", return_value={"id": 7, "stage": "segment"}),
        patch.object(JobMgr, "submit_action", _fake_submit),
    ):
        JobMgr().resume_job(7)

    assert calls["job_id"] == 7
    assert calls["action"] == "segment"
    assert calls["prepare"] is False, "续跑不能清产物"
    assert calls["sync"] is False
    assert calls["resume_after_abort"] is False
