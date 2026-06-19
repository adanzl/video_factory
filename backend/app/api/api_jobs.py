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
    parse_query_int,
    parse_str,
)
from app.services.job.job_mgr import JobBusyError, job_mgr

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


@bp.post("/script")
def run_script_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_script(job_id, to_end=to_end))


@bp.post("/intro")
def run_intro_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_intro(job_id, to_end=to_end))


@bp.post("/cover")
def run_cover_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_cover(job_id, to_end=to_end))


@bp.post("/tts")
def run_tts_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_tts(job_id, to_end=to_end))


@bp.post("/segment/images")
def run_segment_images_route():
    data = get_json_body()
    job_id = parse_id(data)
    to_end = parse_bool(data, "to_end", default=False)
    segment_indices = parse_int_list(data, "segments")
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_segment_images(
            job_id,
            to_end=to_end,
            segment_indices=segment_indices,
        ),
    )


@bp.post("/segment/clips")
def run_segment_clips_route():
    data = get_json_body()
    job_id = parse_id(data)
    to_end = parse_bool(data, "to_end", default=False)
    segment_indices = parse_int_list(data, "segments")
    return _accept_stage(
        job_id,
        lambda: job_mgr.run_segment_clips(
            job_id,
            to_end=to_end,
            segment_indices=segment_indices,
        ),
    )


@bp.post("/merge")
def run_merge_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_merge(job_id, to_end=to_end))


@bp.post("/publish")
def run_publish_route():
    job_id, to_end = _parse_stage_body()
    return _accept_stage(job_id, lambda: job_mgr.run_publish(job_id, to_end=to_end))


@bp.get("")
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


@bp.post("/delete")
def delete_job_route():
    data = get_json_body()
    job_id = parse_id(data)
    job_mgr.delete_job(job_id)
    return json_ok({"id": job_id, "deleted": True})


@bp.get("/<int:job_id>/segments")
def get_job_segments_route(job_id: int):
    return json_ok(job_mgr.get_segments(job_id))


@bp.get("/<int:job_id>/logs")
def get_job_logs_route(job_id: int):
    return json_ok(job_mgr.get_logs(job_id))
