from __future__ import annotations

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
from app.services.material.material_mgr import material_mgr

bp = Blueprint("api_materials", __name__, url_prefix="/v_factory/api/materials")


@bp.get("/list")
def list_materials_route():
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(material_mgr.list_materials(limit=limit, offset=offset))


@bp.get("/get")
def get_material_route():
    return json_ok(material_mgr.get_material(parse_id()))


@bp.post("/upload")
def upload_material_route():
    if "file" not in request.files:
        raise APIError("file is required")
    file = request.files["file"]
    name = request.form.get("name")
    note = request.form.get("note")
    try:
        material = material_mgr.upload_material(file, name=name, note=note)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_created(material)


@bp.post("/update")
def update_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    updates = {}
    if "name" in data:
        updates["name"] = parse_str(data, "name")
    if "note" in data:
        updates["note"] = parse_optional_str(data, "note")
    try:
        material = material_mgr.update_material(material_id, **updates)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_ok(material)


@bp.post("/delete")
def delete_material_route():
    data = get_json_body()
    material_id = parse_id(data)
    material_mgr.delete_material(material_id)
    return json_ok({"id": material_id, "deleted": True})


@bp.post("/edit")
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
        material = material_mgr.edit_material(
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


@bp.post("/jobs/create")
def create_job_from_material_route():
    data = get_json_body()
    material_id = parse_id(data, field="material_id")
    title = parse_str(data, "title")
    script_mode = parse_optional_str(data, "script_mode") or "ai"
    narration = parse_optional_str(data, "narration")
    skip_publish = parse_bool(data, "skip_publish", default=True)
    run_mode = parse_optional_str(data, "run_mode") or "prepare"
    try:
        job = material_mgr.create_job_from_material(
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
