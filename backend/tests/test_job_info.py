from app.utils.job_info import merge_job_script_params, script_params_from_info


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
