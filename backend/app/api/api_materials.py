from __future__ import annotations

import logging

from flask import Blueprint, request

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    json_created,
    json_ok,
    parse_bool,
    parse_id,
    parse_optional_str,
    parse_query_int,
    parse_str,
)
from app.services.material.material_video_mgr import material_video_mgr
from app.services.material.material_audio_mgr import material_audio_mgr

logger = logging.getLogger(__name__)

video_bp = Blueprint("api_materials_video", __name__, url_prefix="/v_factory/api/materials/video")
audio_bp = Blueprint("api_materials_audio", __name__, url_prefix="/v_factory/api/materials/audio")


# ── 视频素材 ──────────────────────────────────────────


@video_bp.get("/list")
def list_materials_route():
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(material_video_mgr.list_materials(limit=limit, offset=offset))


@video_bp.get("/get")
def get_material_route():
    return json_ok(material_video_mgr.get_material(parse_id()))


@video_bp.post("/upload")
def upload_material_route():
    if "file" not in request.files:
        raise APIError("file is required")
    file = request.files["file"]
    name = request.form.get("name")
    note = request.form.get("note")
    try:
        material = material_video_mgr.upload_material(file, name=name, note=note)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_created(material)


@video_bp.post("/update")
def update_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    updates = {}
    if "name" in data:
        updates["name"] = parse_str(data, "name")
    if "note" in data:
        updates["note"] = parse_optional_str(data, "note")
    try:
        material = material_video_mgr.update_material(material_id, **updates)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_ok(material)


@video_bp.post("/delete")
def delete_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    material_video_mgr.delete_material(material_id)
    return json_ok({"id": material_id, "deleted": True})


@video_bp.post("/edit")
def edit_material_route():
    raw_id = request.form.get("id")
    if raw_id is None:
        raise APIError("id is required")
    try:
        material_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise APIError("id must be an integer") from exc
    if material_id <= 0:
        raise APIError("id must be positive")
    name = request.form.get("name")
    if name is None or not str(name).strip():
        raise APIError("name is required")
    note = request.form.get("note")
    file = request.files.get("file")
    if file is not None and not file.filename:
        file = None
    try:
        material = material_video_mgr.edit_material(
            material_id,
            name=str(name),
            note=note if note is not None else None,
            file=file,
        )
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    except KeyError as exc:
        raise APIError(str(exc), status_code=404) from exc
    return json_ok(material)


@video_bp.post("/jobs/create")
def create_job_from_material_route():
    data = get_json_body()
    material_id = parse_id(data, field="material_id")
    title = parse_str(data, "title")
    script_mode = parse_optional_str(data, "script_mode") or "ai"
    narration = parse_optional_str(data, "narration")
    skip_publish = parse_bool(data, "skip_publish", default=True)
    run_mode = parse_optional_str(data, "run_mode") or "prepare"
    try:
        job = material_video_mgr.create_job_from_material(
            material_id,
            title,
            narration=narration,
            script_mode=script_mode,
            skip_publish=skip_publish,
            run_mode=run_mode,
        )
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    except KeyError as exc:
        raise APIError(str(exc), status_code=404) from exc

    return json_created(job)


@video_bp.post("/analyze")
def analyze_material_route():
    data = get_json_body()
    material_id = parse_id(data, field="material_id")
    logger.info("analyze material #%d", material_id)
    try:
        result = material_video_mgr.analyze_material(material_id)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    except KeyError as exc:
        raise APIError(str(exc), status_code=404) from exc
    except RuntimeError as exc:
        raise APIError(str(exc), status_code=502) from exc
    return json_ok(result)


# ── 音频素材 ──────────────────────────────────────────


@audio_bp.get("/list")
def list_audio_materials_route():
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(material_audio_mgr.list_materials(limit=limit, offset=offset))


@audio_bp.get("/get")
def get_audio_material_route():
    return json_ok(material_audio_mgr.get_material(parse_id()))


@audio_bp.post("/upload")
def upload_audio_material_route():
    if "file" not in request.files:
        raise APIError("file is required")
    file = request.files["file"]
    name = request.form.get("name")
    note = request.form.get("note")
    try:
        material = material_audio_mgr.upload_material(file, name=name, note=note)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_created(material)


@audio_bp.post("/update")
def update_audio_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    updates = {}
    if "name" in data:
        updates["name"] = parse_str(data, "name")
    if "note" in data:
        updates["note"] = parse_optional_str(data, "note")
    try:
        material = material_audio_mgr.update_material(material_id, **updates)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_ok(material)


@audio_bp.post("/delete")
def delete_audio_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    material_audio_mgr.delete_material(material_id)
    return json_ok({"id": material_id, "deleted": True})


@audio_bp.post("/edit")
def edit_audio_material_route():
    raw_id = request.form.get("id")
    if raw_id is None:
        raise APIError("id is required")
    try:
        material_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise APIError("id must be an integer") from exc
    if material_id <= 0:
        raise APIError("id must be positive")
    name = request.form.get("name")
    if name is None or not str(name).strip():
        raise APIError("name is required")
    note = request.form.get("note")
    file = request.files.get("file")
    if file is not None and not file.filename:
        file = None
    try:
        material = material_audio_mgr.edit_material(
            material_id,
            name=str(name),
            note=note if note is not None else None,
            file=file,
        )
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    except KeyError as exc:
        raise APIError(str(exc), status_code=404) from exc
    return json_ok(material)
