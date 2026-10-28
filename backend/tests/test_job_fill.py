"""补全成片：已有产物视为完成，缺的才算缺口。"""
from __future__ import annotations

from pathlib import Path

from app.services.job.job_fill import (
    clear_downstream_media,
    script_body_ready,
    script_prompt_gaps,
    stage_outputs_complete,
    tts_files_ready,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_script_body_ready_keeps_partial_dialogue():
    script = {
        "segments": [
            {"segment_index": 1, "text": "已经写好的一句"},
            {"segment_index": 2, "text": ""},
        ]
    }
    assert script_body_ready(script) is True
    assert script_body_ready({"segments": []}) is False
    assert script_body_ready({"segments": [{"segment_index": 1, "text": ""}]}) is False


def test_material_script_does_not_require_image_prompts():
    job = {"pipeline": "material"}
    script = {"segments": [{"segment_index": 1, "text": "口播"}]}
    assert script_prompt_gaps(job, script) == []
    assert stage_outputs_complete(job | {"script_json": script}, "script", media_dir=Path("."))


def test_standard_script_gap_is_missing_prompt_only():
    job = {"pipeline": "standard", "script_json": {
        "segments": [
            {"segment_index": 1, "text": "甲", "image_prompt": "已有"},
            {"segment_index": 2, "text": "乙"},
        ]
    }}
    assert script_prompt_gaps(job, job["script_json"]) == [2]
    assert stage_outputs_complete(job, "script", media_dir=Path(".")) is False
    job["script_json"]["segments"][1]["image_prompt"] = "补上"
    assert stage_outputs_complete(job, "script", media_dir=Path(".")) is True


def test_tts_and_segment_and_merge_completeness(tmp_path: Path):
    media = tmp_path
    segments = [
        {"segment_index": 1, "text": "甲", "image_path": str(media / "images" / "1.png"), "clip_path": str(media / "segments" / "1.mp4")},
        {"segment_index": 2, "text": "乙", "image_path": str(media / "images" / "2.png"), "clip_path": str(media / "segments" / "2.mp4")},
    ]
    job = {
        "id": 1,
        "pipeline": "standard",
        "audio_path": str(media / "audio" / "narration.mp3"),
        "subtitle_path": str(media / "audio" / "subtitles.srt"),
    }
    assert tts_files_ready(media, segments) is False
    _touch(media / "audio" / "narration.mp3")
    _touch(media / "audio" / "subtitles.srt")
    _touch(media / "audio" / "subtitle_cues.json")
    _touch(media / "audio" / "clips" / "1.mp3")
    assert tts_files_ready(media, segments) is False
    _touch(media / "audio" / "clips" / "2.mp3")
    assert tts_files_ready(media, segments) is True
    assert stage_outputs_complete(job, "tts", media_dir=media, segments=segments) is True

    assert stage_outputs_complete(job, "segment", media_dir=media, segments=segments) is False
    for seg in segments:
        _touch(Path(seg["image_path"]))
        _touch(Path(seg["clip_path"]))
    assert stage_outputs_complete(job, "segment", media_dir=media, segments=segments) is True

    assert stage_outputs_complete(job, "merge", media_dir=media) is False
    _touch(media / "final.mp4")
    assert stage_outputs_complete(job, "merge", media_dir=media) is True

    assert stage_outputs_complete(job, "intro", media_dir=media) is False
    _touch(media / "intro.mp4")
    _touch(media / "cover.jpg")
    assert stage_outputs_complete(job, "intro", media_dir=media) is True


def test_clear_downstream_keeps_base_video(tmp_path: Path):
    _touch(tmp_path / "base.mp4")
    _touch(tmp_path / "audio" / "narration.mp3")
    _touch(tmp_path / "images" / "1.png")
    _touch(tmp_path / "final.mp4")
    clear_downstream_media(tmp_path)
    assert (tmp_path / "base.mp4").is_file()
    assert not (tmp_path / "audio" / "narration.mp3").exists()
    assert not (tmp_path / "images" / "1.png").exists()
    assert not (tmp_path / "final.mp4").exists()


def test_chat_intro_also_needs_end_card(tmp_path: Path):
    job = {"pipeline": "chat"}
    _touch(tmp_path / "intro.mp4")
    _touch(tmp_path / "cover.jpg")
    assert stage_outputs_complete(job, "intro", media_dir=tmp_path) is False
    _touch(tmp_path / "end.mp4")
    assert stage_outputs_complete(job, "intro", media_dir=tmp_path) is True
