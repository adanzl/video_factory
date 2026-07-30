from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.segment.image.image_agnes import AgnesImageVerifyFailed
from app.services.segment.image.image_mgr import ImageMgr, ImageProvider


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


def _batch_provider(max_workers: int | None, peak: list[int]) -> ImageProvider:
    """出图时记录并发峰值的假 provider。"""
    import gevent

    class _Provider(ImageProvider):
        def describe_params(self, *, size: str | None = None) -> str:
            return "provider=fake"

        def generate(self, prompt, output_path, **kwargs):  # noqa: ANN001, ANN003
            peak[0] += 1
            peak[1] = max(peak[1], peak[0])
            gevent.sleep(0.05)
            peak[0] -= 1
            output_path.write_bytes(b"png")
            return output_path

    _Provider.max_workers = max_workers
    return _Provider()


def _run_batch(provider: ImageProvider, images_dir: Path, workers: int) -> tuple[list, list[int]]:
    from app.config import get_settings

    mgr = ImageMgr()
    segments = [
        {
            "id": 100 + i,
            "segment_index": i,
            "text": f"第{i}段",
            "image_prompt": "提示词内容 " * 20,
        }
        for i in range(1, 5)
    ]
    done_ids: list[int] = []
    settings = get_settings()
    with (
        patch.object(mgr, "_get_image_provider", return_value=provider),
        patch.object(settings, "mock_mode", False),
        patch.object(settings, "image_max_workers", workers),
    ):
        results = mgr.generate_segment_images(
            segments,
            images_dir,
            on_image_done=lambda seg_id, *_: done_ids.append(seg_id),
        )
    return results, done_ids


def test_cloud_provider_runs_concurrently_with_callback(tmp_path: Path) -> None:
    """传了落库回调也要按 IMAGE_MAX_WORKERS 并发，不能退化成串行。"""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    peak = [0, 0]
    results, done_ids = _run_batch(_batch_provider(None, peak), images_dir, 4)

    assert peak[1] == 4
    assert sorted(seg_id for seg_id, _ in results) == [101, 102, 103, 104]
    assert sorted(done_ids) == [101, 102, 103, 104]


def test_local_provider_stays_serial(tmp_path: Path) -> None:
    """SD15 独占本地显存，调大 IMAGE_MAX_WORKERS 也必须串行。"""
    from app.services.segment.image.image_sd15 import Sd15ImageProvider

    assert Sd15ImageProvider.max_workers == 1

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    peak = [0, 0]
    results, done_ids = _run_batch(_batch_provider(1, peak), images_dir, 4)

    assert peak[1] == 1
    assert len(results) == 4
    assert sorted(done_ids) == [101, 102, 103, 104]


def test_concurrent_prompt_persist_is_safe(app_ctx) -> None:
    """greenlet 不继承 app context，出图内的提示词落库须自行推入才写得进库。"""
    import gevent

    from app.repositories import repo_segment
    from app.repositories.sql_exec import atomic, execute
    from app.services.segment.image.image_mgr import _greenlet_app_context

    with atomic():
        execute("INSERT INTO video_job (id, title) VALUES (1, '并发写库')")
        repo_segment.insert_segments(
            1,
            [{"segment_index": i, "text": f"第{i}段", "image_prompt": "旧"} for i in range(1, 5)],
        )

    mgr = ImageMgr()
    rows = {int(r["segment_index"]): dict(r) for r in repo_segment.list_segments(1)}

    def persist(index: int) -> None:
        with _greenlet_app_context():
            gevent.sleep(0.01)
            seg = rows[index]
            seg["image_prompt"] = f"新提示词{index}"
            mgr._persist_segment_prompt(seg)

    gevent.joinall([gevent.spawn(persist, i) for i in range(1, 5)], raise_error=True)

    saved = {
        int(r["segment_index"]): r["image_prompt"] for r in repo_segment.list_segments(1)
    }
    assert saved == {i: f"新提示词{i}" for i in range(1, 5)}


def test_regen_daily_rewrites_visual_brief_not_append_feedback() -> None:
    """daily 质检重写应改 visual_brief 再拼装，禁止把改写说明塞进 T2I。"""
    mgr = ImageMgr()
    seg = {
        "id": 6,
        "segment_index": 6,
        "text": "脏衣篮",
        "visual_brief": "客厅沙发旁地上放着藤编脏衣篮。",
        "shot_type": "中景",
        "image_prompt": "旧提示",
        "dialogue": [
            {"speaker": "灿灿", "text": "你看！"},
            {"speaker": "昭昭", "text": "哼。"},
        ],
    }
    job = {
        "id": 99,
        "script_json": {
            "title": "t",
            "visual_style": "儿童情绪涂鸦",
            "setting": "客厅",
            "content_style": "daily_story",
            "segments": [dict(seg)],
        },
    }

    def _fake_vb(script, **kwargs):
        fb = kwargs.get("feedback") or ""
        assert "出图质检" in fb
        assert "昭昭" in fb and "灿灿" in fb
        assert "同场粘性角色不可漏画" in fb
        assert "禁止新增未授权角色" in fb
        # 本段无妈妈，反馈不得写妈妈外貌约束
        assert "米色上衣" not in fb
        assert kwargs.get("segment_indices") == [6]
        for s in script["segments"]:
            if int(s["segment_index"]) == 6:
                s["visual_brief"] = (
                    "客厅沙发旁地上放着藤编脏衣篮，里面零散衣物更醒目；"
                    "画面左边是灿灿，右边是昭昭；"
                    "灿灿叉腰指着脏衣篮，昭昭双手抱臂撇嘴。"
                )
        return script

    def _fake_fill(script, **kwargs):
        # daily 路径不应再带质检 feedback 去拼 T2I
        assert kwargs.get("feedback") is None
        return script

    with (
        patch(
            "app.services.llm.llm_mgr.llm_mgr.fill_visual_briefs",
            side_effect=_fake_vb,
        ) as mock_vb,
        patch(
            "app.services.llm.llm_mgr.llm_mgr.fill_image_prompts",
            side_effect=_fake_fill,
        ) as mock_fill,
        patch(
            "app.utils.job_info.resolve_include_sd15_prompt",
            return_value=False,
        ),
    ):
        new_prompt = mgr._regen_segment_image_prompt(
            seg,
            job=job,
            content_style="daily_story",
        )

    mock_vb.assert_called_once()
    mock_fill.assert_called_once()
    assert "出图质检连续未通过" not in new_prompt
    assert "请改写本段" not in new_prompt
    assert "脏衣篮" in new_prompt
    assert "灿灿" in (seg.get("visual_brief") or "")
    assert "妈妈" not in new_prompt
    assert seg["image_prompt"] == new_prompt


def test_regen_segment_reinjects_speaking_times_into_motion() -> None:
    """质检重生 motion 后须按对白估时写入说话时间轴，避免落库无秒数原文。"""
    mgr = ImageMgr()
    seg = {
        "id": 99,
        "job_id": 54,
        "segment_index": 1,
        "text": "a。b。",
        "visual_brief": "画面左边是昭昭，右边是灿灿；昭昭指妈妈，灿灿叉腰。",
        "dialogue": [
            {"speaker": "昭昭", "text": "客厅挂钟都九点了。"},
            {"speaker": "灿灿", "text": "对啊她还不睡。"},
        ],
        "image_prompt": "旧图",
        "motion_prompt": "旧运动",
        "shot_type": "特写",
    }
    job = {
        "id": 54,
        "info": {"content_style": "daily_story"},
        "script_json": {
            "title": "t",
            "visual_style": "儿童情绪涂鸦",
            "setting": "客厅",
            "content_style": "daily_story",
            "segments": [dict(seg)],
        },
    }

    def _fake_vb(script, **kwargs):
        return script

    def _fake_fill(script, **kwargs):
        for s in script["segments"]:
            if int(s["segment_index"]) == 1:
                s["image_prompt"] = (
                    "儿童情绪涂鸦风格。客厅。画面左边是昭昭，右边是灿灿。"
                )
                s["motion_prompt"] = (
                    "画面左边是昭昭，右边是灿灿。"
                    "昭昭说话，同时右手食指微微向下点动约2厘米后停止；"
                    "灿灿说话，同时右手食指微微点动约1厘米后停止。"
                    "两人说话后面部表情恢复与静图一致：昭昭瞪眼，灿灿撇嘴。"
                    "服装发型稳定。镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
                )
        return script

    with (
        patch(
            "app.services.llm.llm_mgr.llm_mgr.fill_visual_briefs",
            side_effect=_fake_vb,
        ),
        patch(
            "app.services.llm.llm_mgr.llm_mgr.fill_image_prompts",
            side_effect=_fake_fill,
        ),
        patch(
            "app.utils.job_info.resolve_include_sd15_prompt",
            return_value=False,
        ),
        patch(
            "app.services.tts.tts_mgr.tts_mgr.subtitle_cues_path_for",
            return_value=Path("/tmp/missing_cues.json"),
        ),
    ):
        mgr._regen_segment_image_prompt(
            seg,
            job=job,
            content_style="daily_story",
        )

    mp = seg.get("motion_prompt") or ""
    assert re.search(r"\d+\.\d+-\d+\.\d+秒", mp)
    assert "左侧男孩张嘴说话，同时" in mp
    assert "右侧女孩张嘴说话，同时" in mp


def test_verify_regen_feedback_cast_aware() -> None:
    from app.services.segment.image.image_mgr import (
        _verify_prompt_regen_feedback,
        _verify_visual_brief_regen_feedback,
    )

    no_mom = _verify_prompt_regen_feedback(["昭昭", "灿灿"])
    assert "妈妈" not in no_mom
    assert "米色上衣" not in no_mom
    assert "昭昭男孩超短发" in no_mom
    assert "昭昭、灿灿" in no_mom

    with_mom = _verify_prompt_regen_feedback(["妈妈", "灿灿"])
    assert "米色上衣" in with_mom
    assert "妈妈" in with_mom

    vb = _verify_visual_brief_regen_feedback(["昭昭", "灿灿"])
    assert "昭昭、灿灿" in vb
    assert "同场粘性角色不可漏画" in vb
    assert "米色上衣" not in vb
