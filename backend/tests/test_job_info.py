from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    merge_job_script_params,
    resolve_estimated_duration_min,
    resolve_narration_target_words,
    resolve_speech_chars_per_sec,
    script_params_from_info,
)
from app.utils.media import (
    DEFAULT_HISTORY_VIDEO_MINUTES,
    DEFAULT_SPEECH_CHARS_PER_SEC,
    narration_target_for_minutes,
)


def test_resolve_narration_target_words_from_estimated_duration():
    script = {"estimated_duration_min": 6.0}
    assert resolve_narration_target_words(script) == narration_target_for_minutes(6.0)


def test_resolve_speech_chars_per_sec_default():
    assert resolve_speech_chars_per_sec(None) == DEFAULT_SPEECH_CHARS_PER_SEC
    assert resolve_speech_chars_per_sec({}) == DEFAULT_SPEECH_CHARS_PER_SEC


def test_resolve_speech_chars_per_sec_daily_default():
    from app.utils.job_info import (
        CONTENT_STYLE_DAILY_STORY,
        DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
    )

    assert (
        resolve_speech_chars_per_sec(None, content_style=CONTENT_STYLE_DAILY_STORY)
        == DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC
    )
    assert (
        resolve_speech_chars_per_sec(
            {"speech_chars_per_sec": 4.0},
            content_style=CONTENT_STYLE_DAILY_STORY,
        )
        == 4.0
    )


def test_script_params_from_info_migrates_flat_speech_chars_per_sec():
    params = script_params_from_info(
        {"speech_chars_per_sec": 3.5, "daily_story_id": 1}
    )
    assert params["speech_chars_per_sec"] == 3.5


def test_resolve_narration_target_words_uses_custom_speech_rate():
    script = {"estimated_duration_min": 6.0, "speech_chars_per_sec": 5.0}
    assert resolve_narration_target_words(script) == narration_target_for_minutes(6.0, chars_per_sec=5.0)


def test_merge_job_script_params_stores_speech_chars_per_sec():
    merged = merge_job_script_params(None, speech_chars_per_sec=4.5)
    assert merged["script"]["speech_chars_per_sec"] == 4.5


def test_resolve_narration_target_words_prefers_estimated_duration():
    script = {
        "estimated_duration_min": 6.0,
        "narration_target_words": 400,
    }
    assert resolve_narration_target_words(script) == narration_target_for_minutes(6.0)


def test_resolve_estimated_duration_min_from_legacy_words():
    script = {"narration_target_words": 1800}
    assert resolve_estimated_duration_min(script) == DEFAULT_HISTORY_VIDEO_MINUTES


def test_merge_job_script_params_stores_explicit_estimated_duration():
    merged = merge_job_script_params(None, estimated_duration_min=5.5)
    assert merged["script"]["estimated_duration_min"] == 5.5


def test_merge_job_script_params_history_default_estimated_duration():
    merged = merge_job_script_params(
        None,
        content_style=CONTENT_STYLE_HISTORICAL_MYSTERY,
    )
    assert merged["script"]["estimated_duration_min"] == DEFAULT_HISTORY_VIDEO_MINUTES


def test_merge_job_script_params_nests_under_script():
    merged = merge_job_script_params(
        {"orientation": "portrait"},
        segment_target_sec=28.0,
        max_title_length=24,
        narration_target_words=1200,
        skip_title_optimize=True,
        generate_image_prompts=True,
        supplementary_info=" 背景要点 ",
        video_timeline='{"segments":[]}',
        orientation="landscape",
        content_style="life_experience",
    )

    assert merged["orientation"] == "landscape"
    assert merged["content_style"] == "life_experience"
    assert merged["script"]["segment_target_sec"] == 28.0
    assert merged["script"]["max_title_length"] == 24
    assert merged["script"]["narration_target_words"] == 1200
    assert merged["script"]["skip_title_optimize"] is True
    assert merged["script"]["generate_image_prompts"] is True
    assert merged["script"]["supplementary_info"] == "背景要点"
    assert merged["script"]["video_timeline"] == '{"segments":[]}'


def test_merge_job_script_params_clears_empty_text_fields():
    existing = {
        "script": {
            "supplementary_info": "old",
            "video_timeline": "old timeline",
        }
    }
    merged = merge_job_script_params(
        existing,
        supplementary_info="   ",
        video_timeline="",
    )

    assert "supplementary_info" not in merged["script"]
    assert "video_timeline" not in merged["script"]


def test_script_params_from_info_migrates_flat_legacy_keys():
    params = script_params_from_info(
        {
            "segment_target_sec": 30.0,
            "orientation": "portrait",
        }
    )

    assert params["segment_target_sec"] == 30.0
    assert "orientation" not in params


def test_resolve_segment_image_size_landscape():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_segment_image_size

    settings = SimpleNamespace(
        image_provider="wan_t2i",
        wan_image_size="720*1280",
        z_image_size="720*1280",
    )
    job = {"info": {"orientation": "landscape"}}
    assert resolve_segment_image_size(job, settings=settings) == "1280*720"


def test_resolve_segment_image_size_portrait():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_segment_image_size

    settings = SimpleNamespace(
        image_provider="wan_t2i",
        wan_image_size="720*1280",
        z_image_size="720*1280",
    )
    job = {"info": {"orientation": "portrait"}}
    assert resolve_segment_image_size(job, settings=settings) == "720*1280"


def test_resolve_image_provider_job_override():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_image_provider

    settings = SimpleNamespace(image_provider="z_image_t2i")
    job = {"info": {"image_provider": "sd15_t2i"}}
    assert resolve_image_provider(job, settings=settings) == "sd15_t2i"


def test_resolve_image_provider_fallback():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_image_provider

    settings = SimpleNamespace(image_provider="wan_t2i")
    assert resolve_image_provider(None, settings=settings) == "wan_t2i"


def test_resolve_include_sd15_prompt():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_include_sd15_prompt

    settings = SimpleNamespace(image_provider="z_image_t2i")
    assert resolve_include_sd15_prompt({"info": {"image_provider": "sd15_t2i"}}, settings=settings)
    assert not resolve_include_sd15_prompt(None, settings=settings)


def test_resolve_segment_image_size_sd15_portrait():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_segment_image_size

    settings = SimpleNamespace(
        image_provider="sd15_t2i",
        sd_image_size="360*640",
        wan_image_size="720*1280",
        z_image_size="720*1280",
    )
    job = {"info": {"orientation": "portrait"}}
    assert resolve_segment_image_size(job, settings=settings) == "360*640"


def test_resolve_segment_image_size_sd15_landscape():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_segment_image_size

    settings = SimpleNamespace(
        image_provider="sd15_t2i",
        sd_image_size="360*640",
        wan_image_size="720*1280",
        z_image_size="720*1280",
    )
    job = {"info": {"orientation": "landscape"}}
    assert resolve_segment_image_size(job, settings=settings) == "640*360"


def test_resolve_segment_video_size_landscape():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_segment_video_size

    settings = SimpleNamespace(video_width=1080, video_height=1920)
    job = {"info": {"orientation": "landscape"}}
    assert resolve_segment_video_size(job, settings=settings) == (1920, 1080)


def test_resolve_video_provider_job_override():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_video_provider

    settings = SimpleNamespace(clip_provider="ffmpeg")
    job = {"info": {"video_provider": "wan_i2v"}}
    assert resolve_video_provider(job, visual_mode="static_motion", settings=settings) == "wan_i2v"


def test_resolve_video_provider_visual_mode_fallback():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_video_provider

    settings = SimpleNamespace(clip_provider="ffmpeg")
    assert resolve_video_provider(None, visual_mode="wan_i2v", settings=settings) == "wan_i2v"


def test_resolve_video_provider_clip_provider_fallback():
    from types import SimpleNamespace

    from app.utils.job_info import resolve_video_provider

    settings = SimpleNamespace(clip_provider="ffmpeg")
    assert resolve_video_provider(None, visual_mode="static_motion", settings=settings) == "ffmpeg"


def test_daily_story_create_job_info_stores_phrase_gap_in_tts():
    from app.utils.job_info import merge_job_info, merge_job_script_params
    from worker.stages.daily_story.tts import DEFAULT_DAILY_SPEAKER_CONFIGS

    info = merge_job_info(
        merge_job_script_params(None, speech_chars_per_sec=3.6),
        daily_story_id=18,
        orientation="landscape",
        video_provider="ffmpeg",
    )
    phrase_gap_sec = 0.2
    speaker_configs = {
        name: dict(cfg) for name, cfg in DEFAULT_DAILY_SPEAKER_CONFIGS.items()
    }
    speaker_configs["phrase_gap_sec"] = phrase_gap_sec
    info["tts"] = {"speaker_configs": speaker_configs}

    assert info["script"]["speech_chars_per_sec"] == 3.6
    assert info["tts"]["speaker_configs"]["phrase_gap_sec"] == 0.2
    assert info["tts"]["speaker_configs"]["昭昭"]["speech_rate"] == 0.81
    assert info["tts"]["speaker_configs"]["灿灿"]["speech_rate"] == 0.94
    assert info["tts"]["speaker_configs"]["妈妈"]["speech_rate"] == 1.0
    assert "phrase_gap_sec" not in info
