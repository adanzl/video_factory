from __future__ import annotations

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_accepted,
    json_created,
    json_ok,
    parse_bool,
    parse_id,
    parse_int_list,
    parse_optional_float,
    parse_optional_int,
    parse_optional_str,
    parse_query_int,
    parse_str,
)
from app.services.intro.size import parse_intro_orientation
from app.services.job.job_mgr import JobBusyError, job_mgr
from app.utils.job_info import (
    merge_job_info,
    normalize_content_style,
    normalize_image_provider,
    normalize_intro_category,
    normalize_orientation,
    normalize_video_provider,
)

bp = Blueprint("api_jobs", __name__, url_prefix="/v_factory/api/jobs")

_UPDATABLE_FIELDS = frozenset({"title", "skip_publish", "status"})


def _parse_stage_body() -> tuple[int, bool]:
    data = get_json_body()
    return parse_id(data), parse_bool(data, "to_end", default=False)


def _accept_stage(job_id: int, submit) -> tuple:
    job_mgr.get_job(job_id)
    try:
        job = submit()
    except JobBusyError as exc:
        raise APIError(str(exc), status_code=409, code="job_busy") from exc
    return json_accepted(job)


def _parse_script_body() -> tuple[
    int,
    bool,
    str | None,
    float | None,
    int | None,
    int | None,
    bool,
    bool,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    data = get_json_body()
    supplementary = parse_optional_str(data, "supplementary_info")
    video_timeline = parse_optional_str(data, "video_timeline")
    orientation = None
    if "orientation" in data:
        orientation = normalize_orientation(parse_optional_str(data, "orientation"))
        if orientation not in {"portrait", "landscape"}:
            raise APIError(
                "orientation must be portrait or landscape",
                status_code=400,
            )
    content_style = None
    if "content_style" in data:
        content_style = normalize_content_style(parse_optional_str(data, "content_style"))
        if content_style is None:
            raise APIError(
                "content_style must be science_child, life_experience or history_mystery",
                status_code=400,
            )
    return (
        parse_id(data),
        parse_bool(data, "to_end", default=False),
        parse_optional_str(data, "title"),
        parse_optional_float(data, "segment_target_sec", minimum=0.0, maximum=60.0),
        parse_optional_int(data, "max_title_length", minimum=8, maximum=48),
        parse_optional_int(data, "narration_target_words", minimum=1, maximum=3000),
        parse_bool(data, "skip_title_optimize", default=False),
        parse_bool(data, "generate_image_prompts", default=False),
        supplementary,
        video_timeline,
        orientation,
        content_style,
    )


@bp.post("/script")
def run_script_route():
    (
        job_id,
        to_end,
        title,
        segment_target_sec,
        max_title_length,
        narration_target_words,
        skip_title_optimize,
        generate_image_prompts,
        supplementary_info,
        video_timeline,
        orientation,
        content_style,
    ) = _parse_script_body()
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_script(
            job_id,
            to_end=to_end,
            title=title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            skip_title_optimize=skip_title_optimize,
            generate_image_prompts=generate_image_prompts,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            orientation=orientation,
            content_style=content_style,
        ),
    )


@bp.post("/script/previewPrompts")
def preview_script_prompts_route():
    data = get_json_body()
    job_id = parse_id(data)
    title = parse_optional_str(data, "title")
    segment_target_sec = parse_optional_float(data, "segment_target_sec", minimum=0.0, maximum=60.0)
    max_title_length = parse_optional_int(data, "max_title_length", minimum=8, maximum=48)
    narration_target_words = parse_optional_int(data, "narration_target_words", minimum=1, maximum=3000)
    skip_title_optimize = parse_bool(data, "skip_title_optimize", default=False)
    supplementary_info = parse_optional_str(data, "supplementary_info")
    video_timeline = parse_optional_str(data, "video_timeline")
    orientation = None
    if "orientation" in data:
        orientation = normalize_orientation(parse_optional_str(data, "orientation"))
    content_style = normalize_content_style(parse_optional_str(data, "content_style"))
    try:
        prompts = job_mgr.preview_script_prompts(
            job_id,
            title=title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            skip_title_optimize=skip_title_optimize,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            orientation=orientation,
            content_style=content_style,
        )
    except ValueError as exc:
        raise APIError(str(exc)) from exc
    return json_ok({"prompts": prompts})


@bp.post("/script/imagePrompts")
def generate_image_prompts_route():
    data = get_json_body()
    job_id = parse_id(data)
    segment_indices = parse_int_list(data, "segments")
    return _accept_stage(
        job_id,
        lambda: job_mgr.generate_image_prompts(job_id, segment_indices=segment_indices),
    )


@bp.post("/script/description")
def regenerate_video_description_route():
    data = get_json_body()
    job_id = parse_id(data)
    try:
        result = job_mgr.generate_video_description(job_id)
    except ValueError as exc:
        raise APIError(str(exc)) from exc
    return json_ok(result)


def _parse_intro_body() -> tuple[int, bool, float | None, str | None, str | None, str | None]:
    data = get_json_body()
    raw_orientation = parse_optional_str(data, "orientation")
    orientation_preference = None
    if "orientation" in data:
        normalized = normalize_orientation(raw_orientation)
        if normalized is None:
            raise APIError(
                "orientation must be auto, portrait, or landscape",
                status_code=400,
            )
        orientation_preference = normalized
    intro_category = None
    if "intro_category" in data:
        intro_category = normalize_intro_category(parse_optional_str(data, "intro_category"))
        if intro_category is None:
            raise APIError("intro_category must be 百科 or 历史悬案", status_code=400)
    return (
        parse_id(data),
        parse_bool(data, "to_end", default=False),
        parse_optional_float(data, "hold_tail_sec", minimum=0.0, maximum=5.0),
        parse_intro_orientation(raw_orientation),
        orientation_preference,
        intro_category,
    )


@bp.post("/intro")
def run_intro_route():
    job_id, to_end, hold_tail_sec, orientation, orientation_preference, intro_category = (
        _parse_intro_body()
    )
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_intro(
            job_id,
            to_end=to_end,
            hold_tail_sec=hold_tail_sec,
            orientation=orientation,
            orientation_preference=orientation_preference,
            intro_category=intro_category,
        ),
    )


@bp.post("/cover")
def run_cover_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_cover(job_id, to_end=to_end))


@bp.post("/tts")
def run_tts_route():
    data = get_json_body()
    job_id = parse_id(data)
    to_end = parse_bool(data, "to_end", default=False)
    speech_rate = parse_optional_float(data, "speech_rate", minimum=0.5, maximum=2.0)
    voice_id = parse_optional_str(data, "voice_id")
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_tts(
            job_id,
            to_end=to_end,
            speech_rate=speech_rate,
            voice_id=voice_id,
        ),
    )


def _parse_segment_body() -> tuple[int, bool, list[int] | None, str | None, str | None]:
    data = get_json_body()
    image_provider = None
    if "image_provider" in data:
        raw = parse_optional_str(data, "image_provider")
        image_provider = normalize_image_provider(raw)
        if raw and image_provider is None:
            raise APIError(
                "image_provider must be z_image_t2i, wan_t2i, sd15_t2i, or agnes_t2i",
                status_code=400,
            )
    video_provider = None
    if "video_provider" in data:
        raw = parse_optional_str(data, "video_provider")
        video_provider = normalize_video_provider(raw)
        if raw and video_provider is None:
            raise APIError(
                "video_provider must be ffmpeg, wan_i2v, or agnes_i2v",
                status_code=400,
            )
    return (
        parse_id(data),
        parse_bool(data, "to_end", default=False),
        parse_int_list(data, "segments"),
        image_provider,
        video_provider,
    )


@bp.post("/segment/all")
def run_segment_all_route():
    job_id, to_end, segment_indices, image_provider, video_provider = _parse_segment_body()
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_segment_all(
            job_id,
            to_end=to_end,
            segment_indices=segment_indices,
            image_provider=image_provider,
            video_provider=video_provider,
        ),
    )


@bp.post("/segment/images")
def run_segment_images_route():
    job_id, to_end, segment_indices, image_provider, _video_provider = _parse_segment_body()
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_segment_images(
            job_id,
            to_end=to_end,
            segment_indices=segment_indices,
            image_provider=image_provider,
        ),
    )


@bp.post("/segment/clips")
def run_segment_clips_route():
    job_id, to_end, segment_indices, _image_provider, video_provider = _parse_segment_body()
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_segment_clips(
            job_id,
            to_end=to_end,
            segment_indices=segment_indices,
            video_provider=video_provider,
        ),
    )


@bp.post("/prepare")
def run_prepare_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_prepare(job_id, to_end=to_end))


@bp.post("/merge")
def run_merge_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_merge(job_id, to_end=to_end))


@bp.post("/publish")
def run_publish_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_publish(job_id, to_end=to_end))


@bp.get("/list")
def list_jobs_route():
    status = get_query("status")
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(job_mgr.list_jobs(status=status, limit=limit, offset=offset))


@bp.get("/get")
def get_job_route():
    return json_ok(job_mgr.get_job(parse_id()))


@bp.post("/add")
def add_job_route():
    data = get_json_body()
    title = parse_str(data, "title")
    skip_publish = parse_bool(data, "skip_publish", default=True)
    job = job_mgr.create_from_title(title, skip_publish=skip_publish)
    return json_created(job)


@bp.post("/update")
def update_job_route():
    data = get_json_body()
    job_id = parse_id(data)
    updates = {k: data[k] for k in _UPDATABLE_FIELDS if k in data}
    if not updates:
        raise APIError(f"at least one field required: {', '.join(sorted(_UPDATABLE_FIELDS))}")
    return json_ok(job_mgr.update_job(job_id, **updates))


@bp.post("/updateInfo")
def update_job_info_route():
    data = get_json_body()
    job_id = parse_id(data)
    orientation = None
    if "orientation" in data:
        orientation = normalize_orientation(parse_optional_str(data, "orientation"))
    content_style = None
    if "content_style" in data:
        content_style = normalize_content_style(parse_optional_str(data, "content_style"))
    intro_category = None
    if "intro_category" in data:
        intro_category = normalize_intro_category(parse_optional_str(data, "intro_category"))
    image_provider = None
    if "image_provider" in data:
        image_provider = normalize_image_provider(parse_optional_str(data, "image_provider"))
    video_provider = None
    if "video_provider" in data:
        video_provider = normalize_video_provider(parse_optional_str(data, "video_provider"))
    if (
        orientation is None
        and content_style is None
        and intro_category is None
        and image_provider is None
        and video_provider is None
    ):
        raise APIError(
            "at least one field required: orientation, content_style, intro_category, "
            "image_provider, video_provider"
        )
    try:
        job = job_mgr.update_job_info(
            job_id,
            orientation=orientation,
            content_style=content_style,
            intro_category=intro_category,
            image_provider=image_provider,
            video_provider=video_provider,
        )
    except ValueError as exc:
        raise APIError(str(exc)) from exc
    return json_ok(job)


@bp.post("/abort")
def abort_job_route():
    data = get_json_body()
    job_id = parse_id(data)
    return json_ok(job_mgr.abort_job(job_id))


@bp.post("/delete")
def delete_job_route():
    data = get_json_body()
    job_id = parse_id(data)
    job_mgr.delete_job(job_id)
    return json_ok({"id": job_id, "deleted": True})


@bp.post("/clean")
def clean_job_route():
    data = get_json_body()
    job_id = parse_id(data)
    try:
        result = job_mgr.clean_job_files(job_id)
    except JobBusyError as exc:
        raise APIError(str(exc), status_code=409, code="job_busy") from exc
    return json_ok(result)


@bp.get("/<int:job_id>/segments")
def get_job_segments_route(job_id: int):
    return json_ok(job_mgr.get_segments(job_id))


@bp.get("/<int:job_id>/logs")
def get_job_logs_route(job_id: int):
    return json_ok(job_mgr.get_logs(job_id))
