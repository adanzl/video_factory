from __future__ import annotations

from flask import Flask, jsonify


class APIError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or "error"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(exc: APIError):
        body = {"error": exc.message}
        if exc.code:
            body["code"] = exc.code
        return jsonify(body), exc.status_code

    @app.errorhandler(KeyError)
    def handle_key_error(exc: KeyError):
        message = str(exc).strip("'") if exc.args else "not found"
        return jsonify({"error": message, "code": "not_found"}), 404

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError):
        return jsonify({"error": str(exc), "code": "bad_request"}), 400
