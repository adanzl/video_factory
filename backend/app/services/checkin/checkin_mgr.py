"""每日签到：读结果库、触发 run.sh、定时调度。

数据源是 daily-check-in-script 自带的 SQLite（表 `t_checkin_records`）。
查库和签到都只调该项目的 `run.sh`：查库用 `--db-sql ... --db-json`（只读），
不传库路径、不打开库文件，库在哪由脚本自己决定（默认项目根下的 `data.db`）。

运行参数分两处存放：

- `.env` 只保留 `DC_DIR`（daily-check-in-script 所在目录）。为空即整个功能关闭。
- 其余参数（脚本名、超时、是否定时、定时时刻）存在 Redis 的。定时按本机时区。
  `video_factory:auto_checkin_setting`（JSON），见 `setting()` / `save_setting()`。
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import config
from app.utils import rds
from app.utils.async_util import hub_safe_lock, run_in_os_thread, run_subprocess_cmd

logger = logging.getLogger(__name__)

_STATUS_OK = "ok"
_STATUS_FAIL = "fail"

# daily-check-in-script 的结果表（由 daily_checkin.utils.db 维护）
_TABLE = "t_checkin_records"

# run.sh --db-sql 依赖这个模块；页面用来判断查库能不能跑。
_DB_MODULE_FILE = Path("daily_checkin") / "utils" / "db.py"
_QUERY_TIMEOUT_SEC = 30.0
_SQL_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")

_SETTING_KEY = "auto_checkin_setting"
_DEFAULT_RUN_SCRIPT = "run.sh"
_DEFAULT_TIMEOUT_SEC = 1800
_DEFAULT_RUN_TIME = "09:00"
_TIMEOUT_MIN = 60
_TIMEOUT_MAX = 86400


def _sql_literal(value: Any) -> str:
    """把绑定值收成 SQL 字面量。run.sh --db-sql 不接收 -p。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sql_with_literals(sql: str, params: dict[str, Any] | None) -> str:
    """把 `:name` 换成已转义的字面量；未提供的占位符保持原样。"""
    if not params:
        return sql

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in params:
            return match.group(0)
        return _sql_literal(params[key])

    return _SQL_PARAM.sub(repl, sql)


class CheckinBusyError(RuntimeError):
    """已有一次签到在跑。"""


class CheckinDisabledError(RuntimeError):
    """.env 里没配 DC_DIR，整个签到功能未启用。"""


class CheckinSettingError(ValueError):
    """Redis 里的签到配置不合法。"""


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_setting() -> dict[str, Any]:
    return {
        "run_script": _DEFAULT_RUN_SCRIPT,
        "timeout_sec": _DEFAULT_TIMEOUT_SEC,
        "auto_run": False,
        "run_time": _DEFAULT_RUN_TIME,
    }


def _parse_run_time(raw: Any) -> str:
    """校验 HH:MM，返回规范化文本；非法抛 CheckinSettingError。"""
    text = str(raw or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise CheckinSettingError(f"定时时刻格式应为 HH:MM：{text!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise CheckinSettingError(f"定时时刻超出范围：{text!r}")
    return f"{hour:02d}:{minute:02d}"


def _normalize_setting(raw: dict[str, Any], *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """把外部传入的字段合并进基准配置并逐项校验，缺项沿用基准值。"""
    merged = dict(base or _default_setting())

    if "run_script" in raw:
        script = str(raw.get("run_script") or "").strip()
        if not script:
            raise CheckinSettingError("脚本名不能为空")
        if "/" in script or "\\" in script or script in (".", ".."):
            raise CheckinSettingError("脚本名只能是 DC_DIR 下的文件名，例如 run.sh")
        merged["run_script"] = script

    if "timeout_sec" in raw:
        try:
            timeout = int(raw.get("timeout_sec") or "")
        except (TypeError, ValueError) as exc:
            raise CheckinSettingError("超时秒数必须是整数") from exc
        if not (_TIMEOUT_MIN <= timeout <= _TIMEOUT_MAX):
            raise CheckinSettingError(
                f"超时秒数需在 {_TIMEOUT_MIN}~{_TIMEOUT_MAX} 之间"
            )
        merged["timeout_sec"] = timeout

    if "auto_run" in raw:
        merged["auto_run"] = bool(raw.get("auto_run"))

    if "run_time" in raw:
        merged["run_time"] = _parse_run_time(raw.get("run_time"))

    merged.pop("run_tz", None)
    return merged


class CheckinMgr:
    """签到看板管理器（单例）。

    gevent 环境下不用 `threading.Lock`（见 `async_util.hub_safe_lock`）：
    「是否已经在跑」由 `_run_lock` + `_running` 在无 IO 的临界区里判定，
    读 Redis / stat 脚本等会让出的操作都放在临界区之外，避免连点「立即运行」
    或手动与定时相撞时起两份 run.sh。
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._started_at: str = ""
        self._started_monotonic: float = 0.0
        self._trigger: str = ""
        self._last_result: dict[str, Any] | None = None
        self._scheduler: Any = None
        self._run_lock = hub_safe_lock()

    # ------------------------------------------------------------------ 配置
    def _stored_setting(self) -> dict[str, Any] | None:
        """读 Redis 里的原始配置；键不存在返回 None，连不上抛 RedisUnavailable。"""
        raw_text = rds.get_str(rds.prefixed(_SETTING_KEY))
        if not raw_text:
            return None
        loaded = json.loads(raw_text)
        if not isinstance(loaded, dict):
            raise CheckinSettingError("签到配置不是 JSON 对象")
        return loaded

    def read_setting(self) -> tuple[dict[str, Any], bool]:
        """返回 (配置, 是否降级)。

        降级只表示「Redis 已配置但这次读不到」，此时给的是默认值：调用方不能
        把它当成用户保存过的配置，尤其不能拿它当基准写回。
        """
        defaults = _default_setting()
        try:
            stored = self._stored_setting()
        except rds.RedisUnavailable as exc:
            logger.warning("[CHECKIN] 读取签到配置失败（Redis 不可用），暂用默认值：%s", exc)
            return defaults, True
        except (json.JSONDecodeError, CheckinSettingError) as exc:
            logger.warning("[CHECKIN] 签到配置内容不可用，暂用默认值：%s", exc)
            return defaults, False
        if stored is None:
            return defaults, False
        try:
            return _normalize_setting(stored, base=defaults), False
        except CheckinSettingError as exc:
            logger.warning("[CHECKIN] 签到配置不合法，暂用默认值：%s", exc)
            return defaults, False

    def setting(self) -> dict[str, Any]:
        """读 Redis 里的运行参数；读不到或内容损坏时回落到默认值。"""
        return self.read_setting()[0]

    def save_setting(self, payload: dict[str, Any]) -> dict[str, Any]:
        """校验并整体写回 Redis；只传部分字段时与当前值合并。

        Redis 连不上时直接把 `RedisUnavailable` 抛给调用方，绝不拿默认值当基准
        写回——否则会把用户原来的脚本名 / 定时覆盖掉。
        """
        stored = self._stored_setting()
        base = _default_setting()
        if stored is not None:
            try:
                base = _normalize_setting(stored, base=base)
            except CheckinSettingError as exc:
                logger.warning("[CHECKIN] 现有配置不合法，保存时按默认值重建：%s", exc)
        merged = _normalize_setting(payload, base=base)
        rds.set(rds.prefixed(_SETTING_KEY), json.dumps(merged, ensure_ascii=False))
        logger.info("[CHECKIN] 已保存签到配置：%s", merged)
        return merged

    # ------------------------------------------------------------------ 路径
    @property
    def dc_dir(self) -> Path | None:
        return config.dc_dir

    def _run_script_path(self, setting: dict[str, Any]) -> Path | None:
        dc_dir = config.dc_dir
        return dc_dir / str(setting["run_script"]) if dc_dir is not None else None

    @property
    def db_script(self) -> Path | None:
        """run.sh --db-sql 依赖的模块文件。只用来判断在不在，不直接执行。"""
        dc_dir = config.dc_dir
        return dc_dir / _DB_MODULE_FILE if dc_dir is not None else None

    def _path_setting(self) -> dict[str, Any]:
        """给路径用的一份配置；未启用时不去碰 Redis。"""
        return self.setting() if config.dc_enabled else _default_setting()

    # ------------------------------------------------------------------ 状态
    def is_enabled(self) -> bool:
        """.env 配了 DC_DIR 才算启用。"""
        return config.dc_enabled

    def is_running(self) -> bool:
        return self._running

    def run_state(self) -> dict[str, Any]:
        elapsed = (
            int(time.monotonic() - self._started_monotonic) if self._running else 0
        )
        return {
            "running": self._running,
            "started_at": self._started_at,
            "elapsed_sec": elapsed,
            "trigger": self._trigger,
            "last_result": self._last_result,
        }

    def schedule_state(self, setting: dict[str, Any] | None = None) -> dict[str, Any]:
        # 未启用时不去碰 Redis，直接给默认值
        if setting is None:
            setting = self._path_setting()
        next_run = None
        if self._scheduler is not None:
            job = self._scheduler.get_job("daily_checkin")
            if job is not None and job.next_run_time is not None:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "enabled": config.dc_enabled and bool(setting["auto_run"]),
            "scheduler_enabled": config.enable_scheduler,
            "run_time": setting["run_time"],
            "next_run_at": next_run,
        }

    def environment(self, setting: dict[str, Any] | None = None) -> dict[str, Any]:
        """看板需要的环境自检，缺什么直接在页面上说清楚。"""
        disabled = {
            "enabled": False,
            "dc_dir": "",
            "dc_dir_exists": False,
            "run_script": "",
            "run_script_exists": False,
            "db_script": "",
            "db_script_exists": False,
        }
        if not config.dc_enabled:
            return disabled
        if setting is None:
            setting = self.setting()
        dc_dir = self.dc_dir
        run_script = self._run_script_path(setting)
        db_script = self.db_script
        if dc_dir is None or run_script is None or db_script is None:
            return disabled
        return {
            "enabled": True,
            "dc_dir": str(dc_dir),
            "dc_dir_exists": dc_dir.is_dir(),
            "run_script": str(run_script),
            "run_script_exists": run_script.is_file(),
            "db_script": str(db_script),
            "db_script_exists": db_script.is_file(),
        }

    # ------------------------------------------------------------------ 读库
    def _run_sql(self, sql: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        """通过 `run.sh --db-sql ... --db-json` 执行一条只读 SQL，返回对象数组。

        run.sh 的 `--db-sql` 不接收绑定参数，条件在这里收成 SQL 字面量再传过去。
        不传 --db-path、也不先看库文件在不在：库路径、只读连接由脚本自己决定。
        任何异常都只记日志并返回空，页面不会 500。
        """
        if not config.dc_enabled or self.db_script is None or not self.db_script.is_file():
            return []
        script = self._run_script_path(self._path_setting())
        if script is None or not script.is_file():
            return []

        cmd = [
            "/bin/bash",
            str(script),
            "--db-sql",
            _sql_with_literals(sql, params),
            "--db-json",
        ]
        try:
            code, stdout, stderr = run_subprocess_cmd(
                cmd,
                timeout=_QUERY_TIMEOUT_SEC,
                check=False,
                cwd=str(script.parent),
            )
        except (OSError, RuntimeError, TimeoutError) as exc:
            logger.warning("[CHECKIN] 调用 %s --db-sql 失败: %s", script.name, exc)
            return []
        if code != 0:
            detail = (stderr or stdout or "").strip().replace("\n", " ")[:300]
            logger.warning("[CHECKIN] %s --db-sql 退出码 %s: %s", script.name, code, detail)
            return []
        try:
            payload = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            logger.warning("[CHECKIN] %s --db-sql 输出不是 JSON: %s", script.name, exc)
            return []
        if not isinstance(payload, list):
            return []
        return [row for row in payload if isinstance(row, dict)]

    def _query(self, sql: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        """执行只读查询；SQL 里的 `{table}` 会换成结果表名。"""
        return self._run_sql(sql.format(table=_TABLE), params)

    def list_records(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: dict[str, Any] = {}
        if platform:
            where.append("platform = :platform")
            params["platform"] = platform
        if status in (_STATUS_OK, _STATUS_FAIL):
            where.append("status = :status")
            params["status"] = status
        if keyword:
            where.append("(platform_name LIKE :kw OR platform LIKE :kw OR message LIKE :kw)")
            params["kw"] = f"%{keyword}%"
        if date:
            where.append("substr(created_at, 1, 10) = :date")
            params["date"] = date
        clause = f" WHERE {' AND '.join(where)}" if where else ""

        total_rows = self._query(f"SELECT COUNT(*) AS n FROM {{table}}{clause}", params)
        total = int(total_rows[0]["n"]) if total_rows else 0
        offset = max(page - 1, 0) * page_size
        items = self._query(
            "SELECT id, created_at, platform, platform_name, account_index, status, message"
            f" FROM {{table}}{clause} ORDER BY id DESC LIMIT {int(page_size)} OFFSET {int(offset)}",
            params,
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def overview(self) -> dict[str, Any]:
        # 一次请求只读一次 Redis，下面各段共用这份配置
        if config.dc_enabled:
            setting, degraded = self.read_setting()
        else:
            setting, degraded = _default_setting(), False

        today = datetime.now().strftime("%Y-%m-%d")
        today_rows = self._query(
            "SELECT status, COUNT(*) AS n FROM {table}"
            " WHERE substr(created_at, 1, 10) = :today GROUP BY status",
            {"today": today},
        )
        today_map = {str(row["status"]): int(row["n"]) for row in today_rows}
        ok_today = today_map.get(_STATUS_OK, 0)
        fail_today = today_map.get(_STATUS_FAIL, 0)

        platforms = self._query(
            "SELECT platform, platform_name, COUNT(*) AS total,"
            " SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,"
            " SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_count,"
            " MAX(created_at) AS last_at,"
            " (SELECT status FROM {table} x WHERE x.platform = t.platform"
            "  ORDER BY x.id DESC LIMIT 1) AS last_status,"
            " (SELECT message FROM {table} x WHERE x.platform = t.platform"
            "  ORDER BY x.id DESC LIMIT 1) AS last_message"
            " FROM {table} t GROUP BY platform, platform_name"
            " ORDER BY fail_count DESC, platform ASC",
            None,
        )
        for row in platforms:
            row["total"] = int(row["total"] or 0)
            row["ok_count"] = int(row["ok_count"] or 0)
            row["fail_count"] = int(row["fail_count"] or 0)
            row["last_status"] = row.get("last_status") or ""
            row["last_message"] = row.get("last_message") or ""

        return {
            "today": {
                "date": today,
                "ok": ok_today,
                "fail": fail_today,
                "total": ok_today + fail_today,
            },
            "platforms": platforms,
            "environment": self.environment(setting),
            "run_state": self.run_state(),
            "schedule": self.schedule_state(setting),
            "redis_ok": not degraded,
        }

    # ------------------------------------------------------------------ 触发
    def start_run(self, *, trigger: str = "manual") -> dict[str, Any]:
        if not config.dc_enabled:
            raise CheckinDisabledError("未配置 DC_DIR，每日签到未启用")

        setting, degraded = self.read_setting()
        if degraded:
            raise rds.RedisUnavailable("签到配置存在 Redis，但当前连不上")

        script = self._run_script_path(setting)
        if script is None or not script.is_file():
            raise FileNotFoundError(f"找不到签到脚本: {script}")
        # 超时在起线程前取好：OS 线程里不再碰 Redis（socket 是 gevent 打过补丁的）
        timeout = float(setting["timeout_sec"])

        # 读 Redis、stat 脚本这些会 yield 的 IO 全部放在抢锁之前；
        # 临界区只改内存，连点两次 / 手动撞定时就不会各起一份 run.sh。
        # 锁用 gevent 的 Semaphore（`threading.Lock` 会堵死 hub），且只在
        # 当前 greenlet 里 acquire/release —— OS 线程里不放锁。
        with self._run_lock:
            if self._running:
                raise CheckinBusyError("签到正在运行中，请稍候")
            self._running = True
            self._started_at = _now_text()
            self._started_monotonic = time.monotonic()
            self._trigger = trigger

        logger.info("[CHECKIN] 开始运行 %s（%s）", script, trigger)
        try:
            run_in_os_thread(lambda: self._run_worker(script, timeout))
        except BaseException:
            self._running = False
            self._started_at = ""
            self._trigger = ""
            raise
        return self.run_state()

    def _run_worker(self, script: Path, timeout: float) -> None:
        code: int = -1
        output = ""
        try:
            code, stdout, stderr = run_subprocess_cmd(
                ["/bin/bash", str(script)],
                timeout=timeout,
                check=False,
                cwd=str(script.parent),
            )
            output = (stdout or "") + (stderr or "")
        except Exception as exc:  # noqa: BLE001 - 任何失败都要落进看板
            output = f"{type(exc).__name__}: {exc}"
            logger.exception("[CHECKIN] 运行异常")
        finally:
            tail = output.strip().splitlines()[-40:]
            self._last_result = {
                "finished_at": _now_text(),
                "exit_code": code,
                "success": code == 0,
                "output_tail": "\n".join(tail),
            }
            self._running = False
            self._trigger = ""
            logger.info("[CHECKIN] 运行结束，exit=%s", code)

    # ------------------------------------------------------------------ 调度
    def bind_scheduler(self, scheduler: Any) -> None:
        self._scheduler = scheduler

    def _build_trigger(self, setting: dict[str, Any]) -> Any:
        """构造 CronTrigger；配置非法时返回 None（此时不动现有任务）。"""
        try:
            run_time = _parse_run_time(setting["run_time"])
        except CheckinSettingError as exc:
            logger.error("[CHECKIN] 定时配置非法，保留现有定时任务：%s", exc)
            return None

        from apscheduler.triggers.cron import CronTrigger

        hour_text, minute_text = run_time.split(":", 1)
        # 不传 timezone：CronTrigger 用本机时区
        return CronTrigger(hour=int(hour_text), minute=int(minute_text))

    def _drop_job(self, scheduler: Any, reason: str) -> None:
        if scheduler.get_job("daily_checkin") is not None:
            scheduler.remove_job("daily_checkin")
        logger.info("[CHECKIN] 不注册定时签到（%s）", reason)

    def apply_schedule(self, scheduler: Any) -> None:
        """按 Redis 里的 auto_run / run_time 重建定时任务（幂等）。

        读不到或读到的是坏配置时都**保留现有任务**：默认值是 auto_run=false，
        拿它去重建等于静默把定时关掉。
        """
        self.bind_scheduler(scheduler)

        if not config.dc_enabled:
            self._drop_job(scheduler, "未配置 DC_DIR")
            return

        try:
            stored = self._stored_setting()
        except rds.RedisUnavailable as exc:
            logger.warning("[CHECKIN] Redis 不可用，保留现有定时签到不变：%s", exc)
            return
        except CheckinSettingError as exc:
            logger.error("[CHECKIN] Redis 里的签到配置不是 JSON 对象，保留现有定时任务：%s", exc)
            return

        if stored is None:
            setting = _default_setting()
        else:
            try:
                setting = _normalize_setting(stored)
            except CheckinSettingError as exc:
                logger.error("[CHECKIN] Redis 里的签到配置不合法，保留现有定时任务：%s", exc)
                return

        if not setting["auto_run"]:
            self._drop_job(scheduler, "auto_run=false")
            return

        # 先建好 trigger 再落任务：trigger 非法时不会把已有任务删掉
        trigger = self._build_trigger(setting)
        if trigger is None:
            return

        scheduler.add_job(
            self._scheduled_run,
            trigger=trigger,
            id="daily_checkin",
            name="每日签到",
            replace_existing=True,
        )
        logger.info(
            "[CHECKIN] 已注册定时签到：每天 %s（本机时区）", setting["run_time"]
        )

    def _scheduled_run(self) -> None:
        try:
            self.start_run(trigger="schedule")
        except CheckinBusyError:
            logger.warning("[CHECKIN] 定时触发时已有任务在跑，本次跳过")
        except CheckinDisabledError:
            logger.warning("[CHECKIN] 定时触发时签到功能已关闭，本次跳过")
        except Exception:
            logger.exception("[CHECKIN] 定时触发失败")


checkin_mgr = CheckinMgr()
