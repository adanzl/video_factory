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
from app.services.daily_story.story_types.model import STORY_TYPE_LABELS

_STAGE_LABELS = {
    "prepare": "基底",
    "script": "脚本",
    "tts": "配音",
    "segment": "分镜",
    "intro": "片头",
    "merge": "合成",
    "publish": "发布",
}

_MODULE_NAMES = {
    "jobs": "任务队列",
    "daily_story": "日常故事",
    "gold_chat": "金牌故事",
    "topic": "选题库",
    "video": "视频素材",
    "audio": "音频素材",
    "clips": "片段搜索",
    "checkin": "每日签到",
}

_PROVIDER_LABELS = {
    "pexels": "Pexels",
    "pixabay": "Pixabay",
    "nasa": "NASA",
}

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
    cpu_percent, cpu_note = _cpu_meter()
    mem_value, mem_percent, mem_note = _memory_meter()
    disk_value, disk_percent, disk_note = _disk_meter()
    return [
        {
            "key": "cpu",
            "value": f"{cpu_percent:.0f}%",
            "percent": _clamp_percent(cpu_percent),
            "note": cpu_note,
        },
        {
            "key": "memory",
            "value": mem_value,
            "percent": mem_percent,
            "note": mem_note,
        },
        {
            "key": "disk",
            "value": disk_value,
            "percent": disk_percent,
            "note": disk_note,
        },
    ]


def _jobs_module() -> dict[str, Any]:
    rows = sql.fetchall(
        "SELECT status, COUNT(*) AS n FROM video_job GROUP BY status"
    )
    sql.commit()
    counts = {str(row["status"]): int(row["n"]) for row in rows}
    failed = counts.get("failed", 0)
    pending = counts.get("pending", 0)
    running = counts.get("running", 0) + counts.get("queued", 0)
    lines = _job_lines("failed", "danger") + _job_lines("pending", "warn")
    return {
        "key": "jobs",
        "stats": [
            _stat("失败", failed, "danger"),
            _stat("停住", pending, "warn"),
            _stat("进行中", running, None),
        ],
        "lines": lines[:_LINE_LIMIT],
    }


def _job_lines(status: str, tone: str) -> list[dict[str, Any]]:
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
        label = _STAGE_LABELS.get(stage, stage or "当前阶段")
        note = f"{label}失败" if status == "failed" else f"停在{label}"
        lines.append(
            _line(
                str(row["title"] or ""),
                note,
                tone=tone,
                to=f"/jobs?id={int(row['id'])}",
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
        SELECT theme, story_type
        FROM daily_story
        WHERE status = 'active' AND job_id IS NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines = [
        _line(
            str(item["theme"] or ""),
            _story_type_note(item.get("story_type")),
            tone="warn",
            to="/daily-story",
        )
        for item in stories
    ]
    return {
        "key": "daily_story",
        "stats": [
            _stat("今天生成", today_n, None),
            _stat("无任务", no_job, "warn" if no_job else None),
            _stat("有任务", has_job, None),
        ],
        "lines": lines,
    }


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
    convert_failed = _count(
        f"""
        SELECT COUNT(*) AS n FROM gold_story
        WHERE {base}
          AND json_extract(payload_json, '$.gold_chat_review_status') IS NOT 'review_pending'
          AND TRIM(COALESCE(json_extract(payload_json, '$.gold_chat_last_error'), '')) != ''
          AND TRIM(COALESCE(json_extract(payload_json, '$.gold_chat_exported_at'), '')) = ''
        """
    )
    rows = sql.fetchall(
        f"""
        SELECT title,
               json_extract(payload_json, '$.gold_chat_review_status') AS review_status,
               json_extract(payload_json, '$.gold_chat_last_error') AS last_error,
               json_extract(payload_json, '$.gold_chat_exported_at') AS exported_at
        FROM gold_story
        WHERE {base}
          AND (
            json_extract(payload_json, '$.gold_chat_review_status') = 'review_pending'
            OR (
              TRIM(COALESCE(json_extract(payload_json, '$.gold_chat_last_error'), '')) != ''
              AND TRIM(COALESCE(json_extract(payload_json, '$.gold_chat_exported_at'), '')) = ''
            )
          )
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (_LINE_LIMIT,),
    )
    sql.commit()
    lines: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("review_status") or "") == "review_pending":
            lines.append(_line(str(row["title"] or ""), "待审核", tone="warn", to="/gold-chat"))
        else:
            lines.append(_line(str(row["title"] or ""), "转换失败", tone="danger", to="/gold-chat"))
    if not lines:
        idle = sql.fetchall(
            f"""
            SELECT title FROM gold_story
            WHERE {base} AND gold_chat_daily_story_id IS NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (_LINE_LIMIT,),
        )
        sql.commit()
        lines = [
            _line(str(row["title"] or ""), "未导入", tone="warn", to="/gold-chat")
            for row in idle
        ]
    return {
        "key": "gold_chat",
        "stats": [
            _stat("未导入", not_imported, "warn" if not_imported else None),
            _stat("待审核", review_pending, "warn" if review_pending else None),
            _stat("转换失败", convert_failed, "danger" if convert_failed else None),
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
        if score is None:
            note = "待打分"
        else:
            note = f"{int(score)} 分"
        lines.append(_line(str(row["title"] or ""), note, to="/topic"))
    return {
        "key": "topic",
        "stats": [
            _stat("待打分", counts.get("pending", 0), None),
            _stat("可入队", counts.get("queued", 0), None),
            _stat("已入队", counts.get("enqueued", 0), None),
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
        SELECT name, status
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
        status = str(row["status"] or "")
        if status == "analyze_failed":
            lines.append(
                _line(str(row["name"] or ""), "分析失败", tone="danger", to="/materials/video")
            )
        elif status == "analyzing":
            lines.append(_line(str(row["name"] or ""), "分析中", to="/materials/video"))
        else:
            lines.append(_line(str(row["name"] or ""), "正常", to="/materials/video"))
    return {
        "key": "video",
        "stats": [
            _stat("正常", counts.get("active", 0), None),
            _stat("分析中", analyzing, None),
            _stat("分析失败", failed, "danger" if failed else None),
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
        _line(str(row["name"] or ""), _fmt_duration(row.get("duration_sec")), to="/materials/audio")
        for row in rows
    ]
    return {
        "key": "audio",
        "stats": [
            _stat("素材", total, None),
            _stat("今天新增", today_n, None),
        ],
        "lines": lines,
    }


def _clip_module() -> dict[str, Any]:
    rows = list_provider_status()
    names = [
        _PROVIDER_LABELS.get(str(row["provider"]), str(row["provider"]))
        for row in rows
        if row.get("available")
    ]
    if names:
        lines = [_line(" / ".join(names), "已配置", to="/clips")]
    else:
        lines = [_line("没有可用的来源", "未配置密钥", to="/clips")]
    return {
        "key": "clips",
        "stats": [_stat("可用来源", len(names), None)],
        "lines": lines,
    }


def _checkin_module() -> dict[str, Any]:
    from app.services.checkin.checkin_mgr import checkin_mgr

    if not checkin_mgr.is_enabled():
        return {
            "key": "checkin",
            "stats": [_stat("状态", "未启用", None)],
            "lines": [_line("未配置签到目录", "", to="/tools")],
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
            "stats": [_stat("状态", "读不到", "warn")],
            "lines": [_line("签到结果暂时读不到", "", to="/tools")],
        }
    lines = []
    for row in records.get("items") or []:
        name = str(row.get("platform_name") or row.get("platform") or "账号")
        index = row.get("account_index")
        title = f"{name} · 账号 {index}" if index not in (None, "") else name
        lines.append(_line(title, "签到失败", tone="danger", to="/tools"))
    if not lines and ok_n:
        lines.append(_line("今天", "全部成功", to="/tools"))
    return {
        "key": "checkin",
        "stats": [
            _stat("今日成功", ok_n, None),
            _stat("今日失败", fail_n, "danger" if fail_n else None),
        ],
        "lines": lines,
    }


def _progress(modules: list[dict[str, Any]]) -> list[dict[str, str]]:
    daily = _module_stat(modules, "daily_story", "今天生成")
    running = _module_stat(modules, "jobs", "进行中")
    return [
        {"label": "今日生成", "value": f"{daily} 篇"},
        {"label": "正在跑", "value": f"{running} 个"},
        {"label": "今日发布", "value": f"{_published_today()} 条"},
    ]


def _module_stat(modules: list[dict[str, Any]], key: str, label: str) -> int:
    for module in modules:
        if module.get("key") != key:
            continue
        for stat in module.get("stats") or []:
            if stat.get("label") == label:
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
        name = _MODULE_NAMES.get(str(module["key"]), str(module["key"]))
        for line in module.get("lines") or []:
            tone = line.get("tone")
            if tone not in {"danger", "warn"}:
                continue
            item = {
                "module": name,
                "title": line["title"],
                "note": line["note"],
                "tone": tone,
                "to": line["to"],
            }
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


def _stat(label: str, value: int | str, tone: str | None) -> dict[str, Any]:
    item: dict[str, Any] = {"label": label, "value": value}
    if tone:
        item["tone"] = tone
    return item


def _line(
    title: str,
    note: str,
    *,
    tone: str | None = None,
    to: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {"title": title, "note": note, "to": to}
    if tone:
        item["tone"] = tone
    return item


def _story_type_note(code: Any) -> str:
    text = str(code or "").strip().upper()
    label = STORY_TYPE_LABELS.get(text)
    if not label:
        return "还没建任务"
    return f"{text} {label}"


def _fmt_duration(raw: Any) -> str:
    if raw is None:
        return "-"
    try:
        sec = float(raw)
    except (TypeError, ValueError):
        return "-"
    if sec < 10:
        return f"{sec:.1f} 秒"
    return f"{sec:.0f} 秒"


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


def _cpu_meter() -> tuple[float, str]:
    note = f"{_cpu_model()} · {os.cpu_count() or 1} 线程"
    sample = _cpu_percent()
    if sample is None:
        return 0.0, note
    return sample, note


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


def _memory_meter() -> tuple[str, int, str]:
    mem = _linux_memory()
    if mem is None and sys.platform == "darwin":
        mem = _darwin_memory()
    if mem is None:
        return "—", 0, "读不到内存"
    used, total, swap_used, swap_total = mem
    percent = 0 if total <= 0 else used / total * 100
    return (
        f"{_fmt_bytes(used)} / {_fmt_bytes(total)}",
        _clamp_percent(percent),
        f"Swap {_fmt_bytes(swap_used)} / {_fmt_bytes(swap_total)}",
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


def _disk_meter() -> tuple[str, int, str]:
    path = _disk_path()
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return "—", 0, str(path)
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
