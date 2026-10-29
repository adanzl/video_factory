"""首页总览：各模块计数、待跟进条目、本机 CPU / 内存 / 硬盘。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import config
from app.repositories import sql_exec as sql
from app.services.clip_search.aggregator import list_provider_status

_ALERT_LIMIT = 10
_LINE_LIMIT = 2

logger = logging.getLogger(__name__)


def build_overview() -> dict[str, Any]:
    modules = [
        _jobs_module(),
        _daily_story_module(),
        _gold_chat_module(),
        _topic_module(),
        _video_module(),
        _audio_module(),
        _clip_module(),
        _checkin_module(),
    ]
    return {
        "host": socket.gethostname() or "",
        "progress": _progress(modules),
        "meters": machine_meters(),
        "modules": modules,
        "alerts": _alerts(modules),
    }


def machine_meters() -> list[dict[str, Any]]:
    cpu_percent, cpu_model, threads = _cpu_meter()
    mem_value, mem_percent, mem_note, mem_state = _memory_meter()
    disk_value, disk_percent, disk_note = _disk_meter()
    project_value, project_percent, project_note, project_state = _project_meter()
    return [
        _meter("cpu", f"{cpu_percent:.0f}%", _clamp_percent(cpu_percent), cpu_model, threads=threads),
        _meter("memory", mem_value, mem_percent, mem_note, state=mem_state),
        _meter("disk", disk_value, disk_percent, disk_note),
        _meter("project", project_value, project_percent, project_note, state=project_state),
    ]


def _jobs_module() -> dict[str, Any]:
    rows = sql.fetchall(
        "SELECT status, COUNT(*) AS n FROM video_job GROUP BY status"
    )
    sql.commit()
    counts = {str(row["status"]): int(row["n"]) for row in rows}
    lines = _job_lines("failed", "danger") + _job_lines("pending", None)
    return {
        "key": "jobs",
        "stats": [
            _stat("failed", counts.get("failed", 0)),
            _stat("pending", counts.get("pending", 0)),
            _stat("queued", counts.get("queued", 0)),
            _stat("running", counts.get("running", 0)),
        ],
        "lines": lines[:_LINE_LIMIT],
    }


def _job_lines(status: str, tone: str | None) -> list[dict[str, Any]]:
    rows = sql.fetchall(
        """
        SELECT id, title, stage, fail_stage
        FROM video_job
        WHERE status = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (status, _LINE_LIMIT),
    )
    sql.commit()
    lines: list[dict[str, Any]] = []
    for row in rows:
        stage = str(row["fail_stage"] or row["stage"] or "")
        lines.append(
            _line(
                str(row["title"] or ""),
                status,
                tone=tone,
                to=f"/jobs?id={int(row['id'])}",
                stage=stage or None,
                id=int(row["id"]),
            )
        )
    return lines


def _daily_story_module() -> dict[str, Any]:
    start, end = _local_day_utc_bounds()
    row = sql.fetchone(
        """
        SELECT
            SUM(CASE WHEN created_at >= ? AND created_at < ? THEN 1 ELSE 0 END) AS today_n,
            SUM(CASE WHEN job_id IS NULL THEN 1 ELSE 0 END) AS no_job,
            SUM(CASE WHEN job_id IS NOT NULL THEN 1 ELSE 0 END) AS has_job
        FROM daily_story
        WHERE status = 'active'
        """,
        (start, end),
    )
    sql.commit()
    today_n = int((row or {}).get("today_n") or 0)
    no_job = int((row or {}).get("no_job") or 0)
    has_job = int((row or {}).get("has_job") or 0)
    stories = sql.fetchall(
        """
        SELECT id, theme, story_type
        FROM daily_story
        WHERE status = 'active' AND job_id IS NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines = []
    for item in stories:
        story_type = str(item.get("story_type") or "").strip().upper()
        lines.append(
            _line(
                str(item["theme"] or ""),
                "no_job",
                tone="warn",
                to="/daily-story",
                story_type=story_type or None,
                id=int(item["id"]),
            )
        )
    return {
        "key": "daily_story",
        "stats": [
            _stat("today", today_n),
            _stat("no_job", no_job),
            _stat("has_job", has_job),
        ],
        "lines": lines,
    }


def _gold_error_visible(row: dict[str, Any]) -> bool:
    """和金牌故事列表一致：已有导出稿且不是待审核/终检候选时，不把旧错误当失败。"""
    from app.services.gold_story.gold_chat.export import load_gold_chat_for_row
    from app.services.gold_story.gold_chat.status import gold_chat_error_from_payload

    raw = row.get("payload_json")
    payload: dict[str, Any] = {}
    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
    chat_row = {"source_id": row.get("source_id"), "payload": payload}
    has_chat = load_gold_chat_for_row(chat_row) is not None
    return gold_chat_error_from_payload(payload, has_gold_chat=has_chat) is not None


def _gold_chat_module() -> dict[str, Any]:
    base = "status != 'archived'"
    not_imported = _count(
        f"SELECT COUNT(*) AS n FROM gold_story WHERE {base} AND gold_chat_daily_story_id IS NULL"
    )
    review_pending = _count(
        f"""
        SELECT COUNT(*) AS n FROM gold_story
        WHERE {base}
          AND json_extract(payload_json, '$.gold_chat_review_status') = 'review_pending'
        """
    )
    failure_rows = sql.fetchall(
        f"""
        SELECT id, title, source_id, payload_json,
               json_extract(payload_json, '$.gold_chat_review_status') AS review_status
        FROM gold_story
        WHERE {base}
          AND json_extract(payload_json, '$.gold_chat_review_status') IS NOT 'review_pending'
          AND TRIM(COALESCE(json_extract(payload_json, '$.gold_chat_last_error'), '')) != ''
        ORDER BY updated_at DESC, id DESC
        """
    )
    sql.commit()
    visible_failures = [row for row in failure_rows if _gold_error_visible(row)]
    convert_failed = len(visible_failures)
    pending_rows = sql.fetchall(
        f"""
        SELECT id, title
        FROM gold_story
        WHERE {base}
          AND json_extract(payload_json, '$.gold_chat_review_status') = 'review_pending'
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines: list[dict[str, Any]] = [
        _line(
            str(row["title"] or ""),
            "review_pending",
            tone="warn",
            to="/gold-chat",
            id=int(row["id"]),
        )
        for row in pending_rows
    ]
    for row in visible_failures:
        if len(lines) >= _LINE_LIMIT:
            break
        lines.append(
            _line(
                str(row["title"] or ""),
                "convert_failed",
                tone="danger",
                to="/gold-chat",
                id=int(row["id"]),
            )
        )
    if not lines:
        idle = sql.fetchall(
            f"""
            SELECT id, title FROM gold_story
            WHERE {base} AND gold_chat_daily_story_id IS NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (_LINE_LIMIT,),
        )
        sql.commit()
        lines = [
            _line(
                str(row["title"] or ""),
                "not_imported",
                tone="warn",
                to="/gold-chat",
                id=int(row["id"]),
            )
            for row in idle
        ]
    return {
        "key": "gold_chat",
        "stats": [
            _stat("not_imported", not_imported),
            _stat("review_pending", review_pending),
            _stat("convert_failed", convert_failed),
        ],
        "lines": lines,
    }


def _topic_module() -> dict[str, Any]:
    rows = sql.fetchall("SELECT status, COUNT(*) AS n FROM title GROUP BY status")
    sql.commit()
    counts = {str(row["status"]): int(row["n"]) for row in rows}
    picked = sql.fetchall(
        """
        SELECT title, score, status
        FROM title
        WHERE status IN ('queued', 'pending')
        ORDER BY CASE status WHEN 'queued' THEN 0 ELSE 1 END, updated_at DESC, id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines = []
    for row in picked:
        score = row.get("score")
        lines.append(
            _line(
                str(row["title"] or ""),
                "pending" if score is None else "scored",
                to="/topic",
                score=None if score is None else int(score),
            )
        )
    return {
        "key": "topic",
        "stats": [
            _stat("pending", counts.get("pending", 0)),
            _stat("queued", counts.get("queued", 0)),
            _stat("enqueued", counts.get("enqueued", 0)),
        ],
        "lines": lines,
    }


def _video_module() -> dict[str, Any]:
    rows = sql.fetchall(
        "SELECT status, COUNT(*) AS n FROM material_video GROUP BY status"
    )
    sql.commit()
    counts = {str(row["status"]): int(row["n"]) for row in rows}
    failed = counts.get("analyze_failed", 0)
    analyzing = counts.get("analyzing", 0)
    picked = sql.fetchall(
        """
        SELECT id, name, status
        FROM material_video
        ORDER BY CASE status
            WHEN 'analyze_failed' THEN 0
            WHEN 'analyzing' THEN 1
            ELSE 2
        END, id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines = []
    for row in picked:
        status = str(row["status"] or "") or "unknown"
        lines.append(
            _line(
                str(row["name"] or ""),
                status,
                tone="danger" if status == "analyze_failed" else None,
                to="/materials/video",
                id=int(row["id"]),
            )
        )
    return {
        "key": "video",
        "stats": [
            _stat("active", counts.get("active", 0)),
            _stat("analyzing", analyzing),
            _stat("analyze_failed", failed),
        ],
        "lines": lines,
    }


def _audio_module() -> dict[str, Any]:
    start, end = _local_day_utc_bounds()
    total = _count("SELECT COUNT(*) AS n FROM material_audio")
    today_n = _count(
        """
        SELECT COUNT(*) AS n FROM material_audio
        WHERE created_at >= ? AND created_at < ?
        """,
        (start, end),
    )
    rows = sql.fetchall(
        """
        SELECT name, duration_sec
        FROM material_audio
        ORDER BY id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines = [
        _line(
            str(row["name"] or ""),
            "duration",
            to="/materials/audio",
            duration_sec=row.get("duration_sec"),
        )
        for row in rows
    ]
    return {
        "key": "audio",
        "stats": [
            _stat("total", total),
            _stat("today", today_n),
        ],
        "lines": lines,
    }


def _clip_module() -> dict[str, Any]:
    rows = list_provider_status()
    providers = [str(row["provider"]) for row in rows if row.get("available")]
    if providers:
        lines = [_line("", "configured", to="/clips", providers=providers)]
    else:
        lines = [_line("", "unconfigured", to="/clips")]
    return {
        "key": "clips",
        "stats": [_stat("available", len(providers))],
        "lines": lines,
    }


def _checkin_module() -> dict[str, Any]:
    from app.services.checkin.checkin_mgr import checkin_mgr

    if not checkin_mgr.is_enabled():
        return {
            "key": "checkin",
            "stats": [_stat("disabled", 0)],
            "lines": [_line("", "disabled", to="/tools")],
        }
    try:
        overview = checkin_mgr.overview()
        today = overview.get("today") or {}
        ok_n = int(today.get("ok") or 0)
        fail_n = int(today.get("fail") or 0)
        records = checkin_mgr.list_records(
            status="fail",
            date=str(today.get("date") or ""),
            page=1,
            page_size=_LINE_LIMIT,
        )
    except Exception:
        logger.warning("[HOME] checkin overview failed", exc_info=True)
        return {
            "key": "checkin",
            "stats": [_stat("unavailable", 0)],
            "lines": [_line("", "unavailable", to="/tools")],
        }
    lines = []
    for row in records.get("items") or []:
        name = str(row.get("platform_name") or row.get("platform") or "")
        index = row.get("account_index")
        lines.append(
            _line(
                name,
                "fail",
                tone="danger",
                to="/tools",
                account_index=None if index in (None, "") else index,
                id=int(row["id"]) if row.get("id") not in (None, "") else None,
            )
        )
    if not lines and ok_n:
        lines.append(_line("", "all_ok", to="/tools"))
    return {
        "key": "checkin",
        "stats": [
            _stat("ok", ok_n),
            _stat("fail", fail_n),
        ],
        "lines": lines,
    }


def _progress(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    daily = _stat_value(modules, "daily_story", "today")
    running = _stat_value(modules, "jobs", "running") + _stat_value(modules, "jobs", "queued")
    return [
        {"key": "stories_today", "value": daily},
        {"key": "running", "value": running},
        {"key": "published_today", "value": _published_today()},
    ]


def _stat_value(modules: list[dict[str, Any]], module_key: str, stat_key: str) -> int:
    for module in modules:
        if module.get("key") != module_key:
            continue
        for stat in module.get("stats") or []:
            if stat.get("key") == stat_key:
                value = stat.get("value")
                return int(value) if isinstance(value, int) else 0
    return 0


def _published_today() -> int:
    start, end = _local_day_bounds()
    rows = sql.fetchall(
        "SELECT info FROM video_job WHERE publish = 1 AND info IS NOT NULL"
    )
    sql.commit()
    count = 0
    for row in rows:
        moment = _publish_moment(row.get("info"))
        if moment is not None and start <= moment < end:
            count += 1
    return count


def _publish_moment(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(info, dict):
        return None
    result = info.get("publish_result")
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    for key in ("scheduled_at", "at"):
        text = result.get(key)
        if isinstance(text, str) and text.strip():
            return _parse_iso(text.strip())
    return None


def _parse_iso(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _local_day_bounds() -> tuple[datetime, datetime]:
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _alerts(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    danger: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    for module in modules:
        module_key = str(module["key"])
        for line in module.get("lines") or []:
            tone = line.get("tone")
            if tone not in {"danger", "warn"}:
                continue
            item = {key: value for key, value in line.items() if key != "tone"}
            item["module"] = module_key
            item["tone"] = tone
            if tone == "danger":
                danger.append(item)
            else:
                warn.append(item)
    return (danger + warn)[:_ALERT_LIMIT]


def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = sql.fetchone(query, params)
    sql.commit()
    if not row:
        return 0
    return int(row["n"] or 0)


def _stat(key: str, value: int) -> dict[str, Any]:
    return {"key": key, "value": value}


def _meter(
    key: str,
    value: str | None,
    percent: int,
    note: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "value": value, "percent": percent}
    if note:
        item["note"] = note
    for name, extra_value in extra.items():
        if extra_value is not None:
            item[name] = extra_value
    return item


def _line(
    title: str,
    code: str,
    *,
    tone: str | None = None,
    to: str,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {"title": title, "code": code, "to": to}
    if tone:
        item["tone"] = tone
    for name, extra_value in extra.items():
        if extra_value is not None:
            item[name] = extra_value
    return item


def _local_day_utc_bounds() -> tuple[str, str]:
    start, end = _local_day_bounds()
    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        start.astimezone(timezone.utc).strftime(fmt),
        end.astimezone(timezone.utc).strftime(fmt),
    )


def _clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _fmt_bytes(n: int) -> str:
    gib = n / (1024 ** 3)
    if gib >= 1024:
        return f"{gib / 1024:.1f} TiB"
    if gib >= 100:
        return f"{gib:.0f} GiB"
    return f"{gib:.1f} GiB"


def _cpu_meter() -> tuple[float, str, int]:
    threads = os.cpu_count() or 1
    model = _cpu_model()
    sample = _cpu_percent()
    if sample is None:
        return 0.0, model, threads
    return sample, model, threads


def _cpu_percent() -> float | None:
    first = _proc_cpu_times()
    if first is not None:
        time.sleep(0.15)
        second = _proc_cpu_times()
        if second is None:
            return None
        total = second[0] - first[0]
        idle = second[1] - first[1]
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1 - idle / total) * 100))
    try:
        load = os.getloadavg()[0]
    except OSError:
        return None
    cpus = os.cpu_count() or 1
    return max(0.0, min(100.0, load / cpus * 100))


def _proc_cpu_times() -> tuple[int, int] | None:
    path = Path("/proc/stat")
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if not line.startswith("cpu "):
            continue
        parts = [int(part) for part in line.split()[1:] if part.isdigit()]
        if len(parts) < 4:
            return None
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return sum(parts), idle
    return None


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip() or "CPU"
        except OSError:
            pass
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
                timeout=1,
            )
            name = out.strip()
            if name:
                return name
        except (OSError, TypeError, subprocess.SubprocessError):
            # gevent patch(subprocess=True) 下非默认 loop 会抛 TypeError
            pass
    return "CPU"


def _memory_meter() -> tuple[str | None, int, str | None, str | None]:
    mem = _linux_memory()
    if mem is None and sys.platform == "darwin":
        mem = _darwin_memory()
    if mem is None:
        return None, 0, None, "unreadable"
    used, total, swap_used, swap_total = mem
    percent = 0 if total <= 0 else used / total * 100
    return (
        f"{_fmt_bytes(used)} / {_fmt_bytes(total)}",
        _clamp_percent(percent),
        f"Swap {_fmt_bytes(swap_used)} / {_fmt_bytes(swap_total)}",
        None,
    )


def _linux_memory() -> tuple[int, int, int, int] | None:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        number = rest.strip().split()
        if not number or not number[0].isdigit():
            continue
        values[key] = int(number[0]) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or available is None:
        return None
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return total - available, total, max(0, swap_total - swap_free), swap_total


def _darwin_memory() -> tuple[int, int, int, int] | None:
    try:
        total = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=1).strip()
        )
        vm = subprocess.check_output(["vm_stat"], text=True, timeout=1)
        swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True, timeout=1)
    except (OSError, TypeError, subprocess.SubprocessError, ValueError):
        return None
    page = 4096
    pages: dict[str, int] = {}
    for line in vm.splitlines():
        if "page size of" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                page = int(digits)
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits:
            pages[key.strip()] = int(digits)
    free = pages.get("Pages free", 0) + pages.get("Pages speculative", 0)
    available = free * page
    used = max(0, total - available)
    swap_total, swap_used = _parse_swapusage(swap)
    return used, total, swap_used, swap_total


def _parse_swapusage(text: str) -> tuple[int, int]:
    total = 0
    used = 0
    for part in text.replace(",", " ").split():
        if part.startswith("total="):
            total = _parse_size_token(part.split("=", 1)[1])
        elif part.startswith("used="):
            used = _parse_size_token(part.split("=", 1)[1])
    return total, used


def _parse_size_token(token: str) -> int:
    raw = token.strip()
    if not raw:
        return 0
    unit = raw[-1].upper()
    number = raw[:-1] if unit in {"K", "M", "G", "T"} else raw
    try:
        value = float(number)
    except ValueError:
        return 0
    scale = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    return int(value * scale.get(unit if unit in scale else "", 1))


def _disk_meter() -> tuple[str | None, int, str]:
    path = _disk_path()
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None, 0, str(path)
    percent = 0 if usage.total <= 0 else usage.used / usage.total * 100
    return (
        f"{_fmt_bytes(usage.used)} / {_fmt_bytes(usage.total)}",
        _clamp_percent(percent),
        str(path),
    )


def _disk_path() -> Path:
    data_disk = Path("/mnt/data")
    if data_disk.is_dir():
        return data_disk
    sqlite_dir = Path(config.sqlite_path).expanduser().resolve().parent
    if sqlite_dir.is_dir():
        return sqlite_dir
    return Path("/")


def _project_meter() -> tuple[str | None, int, str | None, str | None]:
    """右侧数字是项目目录占用。进度条是项目内部 data 占项目目录的比例。"""
    project = Path(config.root_dir).resolve()
    data = project / "data"
    project_bytes = _du_bytes(project)
    if project_bytes is None:
        return None, 0, str(project), None
    if not data.is_dir():
        return _fmt_bytes(project_bytes), 0, None, "missing"
    data_bytes = _du_bytes(data)
    if data_bytes is None:
        return _fmt_bytes(project_bytes), 0, None, "unreadable"
    percent = project_share_percent(project_bytes, data_bytes)
    return _fmt_bytes(project_bytes), percent, f"data {_fmt_bytes(data_bytes)}", None


def project_share_percent(project_bytes: int, data_bytes: int) -> int:
    """项目内部 data 占项目目录的比例。"""
    if project_bytes <= 0:
        return 0
    return _clamp_percent(data_bytes / project_bytes * 100)


def _du_bytes(path: Path) -> int | None:
    if not path.is_dir():
        return None
    from app.utils.async_util import run_subprocess_cmd

    try:
        code, stdout, _stderr = run_subprocess_cmd(
            ["du", "-skx", str(path)],
            timeout=25,
        )
    except (OSError, RuntimeError):
        logger.warning("[HOME] du failed path=%s", path, exc_info=True)
        return None
    if code != 0:
        logger.warning("[HOME] du exit %s path=%s", code, path)
        return None
    token = (stdout or "").split()
    if not token or not token[0].isdigit():
        return None
    return int(token[0]) * 1024
