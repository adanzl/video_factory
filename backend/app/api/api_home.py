"""首页总览。"""

from __future__ import annotations

from flask import Blueprint

from app.api.utils import json_ok
from app.services.home.overview import build_overview

bp = Blueprint("api_home", __name__, url_prefix="/v_factory/api/home")


@bp.get("/overview")
def overview_route():
    return json_ok(build_overview())
