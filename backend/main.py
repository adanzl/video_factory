from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from flask import Flask, jsonify

from app.repositories import job_repo
from app.repositories.connection import connection


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/v1/jobs")
    def list_jobs():
        with connection() as conn:
            rows = conn.execute(
                "SELECT id, title, stage, status, final_path, updated_at FROM video_job ORDER BY id DESC LIMIT 50"
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.get("/api/v1/jobs/<int:job_id>")
    def get_job(job_id: int):
        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
        return jsonify(job)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
