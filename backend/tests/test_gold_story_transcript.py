"""金故事 H0b 逐字稿工具测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.transcript.download import parse_media_ref
from app.services.gold_story.transcript import (
    format_dialogue_transcript,
    format_transcript_display,
    normalize_bv,
    read_source_list,
)


def test_normalize_bv_from_id():
    assert normalize_bv("BV1kfDTBXEfu") == "BV1kfDTBXEfu"


def test_normalize_bv_from_url():
    assert (
        normalize_bv("https://www.bilibili.com/video/BV1kfDTBXEfu")
        == "BV1kfDTBXEfu"
    )


def test_normalize_bv_invalid():
    with pytest.raises(ValueError, match="not a BV"):
        normalize_bv("not-a-bv")


def test_parse_douyin_ref():
    ref = parse_media_ref(
        "https://www.douyin.com/video/7123456789012345678",
        platform="douyin",
    )
    assert ref.source == "douyin"
    assert ref.source_id == "7123456789012345678"


def test_read_source_list(tmp_path):
    path = tmp_path / "bv.txt"
    path.write_text(
        "# comment\nBV1aaa111111\n\nhttps://www.bilibili.com/video/BV2bbb222222\n",
        encoding="utf-8",
    )
    assert read_source_list(path) == [
        "BV1aaa111111",
        "https://www.bilibili.com/video/BV2bbb222222",
    ]


def test_format_transcript_display_keeps_newlines():
    raw = "第一句\n第二句"
    assert format_transcript_display(raw) == raw


def test_format_transcript_display_splits_on_punctuation():
    raw = "已经睡了。你还醒着！别吵了？"
    assert format_transcript_display(raw) == "已经睡了。\n你还醒着！\n别吵了？"


def test_format_transcript_display_splits_on_comma():
    raw = "第一句,第二句,第三句"
    assert format_transcript_display(raw) == "第一句,\n第二句,\n第三句"


def test_transcribe_preserves_cross_check_in_result_metadata_and_cache(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from app.config import Config
    from app.services.gold_story.transcript import transcript as tx

    cfg = Config()
    cfg.gold_story_transcript_dir = tmp_path / "transcripts"
    cfg.gold_story_media_workspace = tmp_path / "media"
    cross = {"available": True, "passed": False, "agreement": 0.043}
    candidates = [{"source": "ocr", "text": "评论文字拼接", "segments": [{"start": 0, "end": 1, "text": "评论文字拼接"}]},
                  {"source": "asr", "text": "音频对白", "segments": [{"start": 0, "end": 1, "text": "音频对白"}]}]
    monkeypatch.setattr(tx, "download_media", lambda *_a: SimpleNamespace(
        video_path=tmp_path / "video.mp4", metadata={"duration": 60, "title": "字幕测试"}))
    monkeypatch.setattr(tx, "extract_audio_wav", lambda *_a, **_kw: tmp_path / "audio.wav")
    monkeypatch.setattr(tx, "_resolve_transcription", lambda **_kw: {
        "text": "评论文字拼接", "engine": "rapidocr", "model": "test", "source": "ocr", "cross_check": cross,
        "candidates": candidates,
    })
    result = tx.transcribe_media("BV1pA4m1378V", config=cfg, skip_existing=False)
    assert result["cross_check"] == cross
    assert json.loads(Path(result["metadata_path"]).read_text())["cross_check"] == cross
    assert json.loads(Path(result["metadata_path"]).read_text())["transcript_candidates"] == candidates
    monkeypatch.setattr(tx, "download_media", lambda *_a: pytest.fail("缓存命中不得重下视频"))
    cached = tx.transcribe_media("BV1pA4m1378V", config=cfg)
    assert cached["action"] == "skip"
    assert cached["cross_check"] == cross
    assert cached["transcript_candidates"] == result["transcript_candidates"] == candidates


def test_resolve_transcription_retains_both_sources_and_segments(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.transcript import transcript as tx

    cfg = Config()
    cfg.gold_story_transcript_cross_check = True
    text = "姐姐让我洗碗，弟弟说他要写作业。"
    segments = [{"start": 0, "end": 3, "text": text}]
    monkeypatch.setattr(tx.gs_subtitle_ocr, "should_try_ocr", lambda *_a, **_kw: True)
    monkeypatch.setattr(tx.gs_subtitle_ocr, "transcribe_video_ocr_subprocess", lambda *_a, **_kw: {
        "source": "ocr", "text": text, "segments": segments, "avg_confidence": 0.9})
    monkeypatch.setattr(tx.gs_whisper, "transcribe_audio", lambda *_a, **_kw: {
        "text": text, "segments": segments, "engine": "faster-whisper", "model": "test"})
    result = tx._resolve_transcription(video_path=tmp_path / "video.mp4", audio_path=tmp_path / "audio.wav",
        ref=parse_media_ref("BV1pA4m1378V"), cfg=cfg, workspace=tmp_path, prompt=None)
    assert result["cross_check"]["b_source"] == "asr"
    assert result["cross_check"]["passed"] is True
    assert {row["source"] for row in result["candidates"]} == {"ocr", "asr"}
    assert all(row["text"] == text and row["segments"] == segments for row in result["candidates"])


def test_transcript_metadata_does_not_apply_to_different_output(tmp_path):
    import json
    from app.config import Config
    from app.services.gold_story.transcript.transcript import read_transcript_metadata

    cfg = Config()
    cfg.gold_story_media_workspace = tmp_path
    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "BV1pA4m1378V.json").write_text(json.dumps({
        "transcript_path": str(tmp_path / "old.txt"),
        "cross_check": {"available": True, "passed": True},
    }))
    assert read_transcript_metadata(cfg, "BV1pA4m1378V", tmp_path / "new.txt") == {}


@pytest.mark.parametrize("state", ["legacy", "cleared", "unusable"])
def test_export_respects_current_transcript_state_without_deleting_evidence(tmp_path, state):
    import json
    from pathlib import Path
    from app.config import Config
    from app.services.gold_story.export_story import export_story_files, load_transcript_for_row

    cfg = Config()
    cfg.gold_story_transcript_dir = tmp_path / "transcripts"
    cfg.gold_story_transcript_dir.mkdir()
    sid = "BV1pA4m1378V"
    raw = cfg.gold_story_transcript_dir / f"{sid}.txt"
    repaired = cfg.gold_story_transcript_dir / f"{sid}.repaired.txt"
    raw.write_text("本轮原始转写")
    repaired.write_text("上一轮修复稿")
    payload = {}
    if state == "cleared":
        payload = {"transcript_repaired_path": None, "transcript_status": "usable"}
    elif state == "unusable":
        payload = {"transcript_repaired_path": str(repaired), "transcript_status": "unusable",
                   "transcript_failure_reason": "交叉验证未通过", "source_inputs": ["replies"]}
    row = {"id": 160, "source_id": sid, "payload": payload}
    display = load_transcript_for_row(row, config=cfg)
    paths = export_story_files(source_id=sid, row=row, config=cfg)
    exported = json.loads(Path(paths["json"]).read_text())
    expected_main = {"legacy": "上一轮修复稿", "cleared": "本轮原始转写", "unusable": ""}[state]
    for result in [display, exported]:
        assert result["transcript"] == expected_main
        assert result["transcript_raw"] == "本轮原始转写"
        assert result["transcript_repaired"] == ("上一轮修复稿" if state == "legacy" else "")
        if state != "legacy":
            assert result["transcript_repaired_path"] is None
        if state == "unusable":
            assert result["source_inputs"] == ["replies"]
            assert result["transcript_failure_reason"] == "交叉验证未通过"
    assert repaired.read_text() == "上一轮修复稿"
