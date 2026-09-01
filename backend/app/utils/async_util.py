"""在 gevent 环境中通过原生线程执行阻塞任务与外部命令。

主进程使用 gevent（main.py：``subprocess=True, thread=False``），
标准库 threading 仍是真实 OS 线程。
gevent patch subprocess 后，Linux 会把 ``_fork_exec`` 置 ``None``，
非 hub 的 OS 线程不能直接用 patched Popen；
``run_in_os_thread`` 内会 ``unpatched_subprocess()`` 补回原生符号。

注意：gevent hub 跑在主线程上，主线程里 thread.join 会卡死所有接口；
等待子线程结果时必须轮询 + gevent.sleep 让出 hub。
"""
from __future__ import annotations

import os
import queue
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future
from contextlib import contextmanager
from queue import Empty
from typing import Any, Iterator, Optional, TypeVar

_T = TypeVar("_T")


def run_in_background(func: Callable[[], None], *, daemon: bool = True) -> None:
    """后台 greenlet 执行，不等待结果。

    使用 gevent.spawn 而非 threading.Thread，避免 OS 线程调用
    gevent-patched socket 导致 hub 事件循环卡死。
    """
    try:
        import gevent
        gevent.spawn(func)
    except ImportError:
        threading.Thread(target=func, daemon=daemon).start()


def subprocess_gevent_patched() -> bool:
    """主进程是否已对 subprocess 做 gevent monkey patch。"""
    try:
        from gevent.monkey import is_module_patched

        return bool(is_module_patched("subprocess"))
    except ImportError:
        return False


def _original_subprocess_attr(name: str, current: Any) -> Any:
    """取 gevent 保存的原生符号；Linux 上还需补回被置空的 _fork_exec。"""
    from gevent.monkey import get_original

    try:
        original = get_original("subprocess", name)
    except (AttributeError, KeyError, TypeError):
        original = None
    if original is not None:
        return original
    if name == "_posixsubprocess":
        try:
            import _posixsubprocess as posix_mod

            return posix_mod
        except ImportError:
            return current
    if name == "_fork_exec":
        try:
            import _posixsubprocess as posix_mod

            return getattr(posix_mod, "fork_exec", current)
        except ImportError:
            return current
    return current


@contextmanager
def unpatched_subprocess() -> Iterator[None]:
    """在 OS 线程内临时恢复原生 subprocess。

    gevent ``patch(subprocess=True)`` 不只替换 Popen/run，还会把 Linux 的
    ``subprocess._fork_exec`` / ``_posixsubprocess`` 置成 ``None``。
    只还原公开 API 时，原生 Popen 会报 ``'NoneType' object is not callable``。
    """
    if not subprocess_gevent_patched():
        yield
        return

    import subprocess as sp

    saved: dict[str, Any] = {}
    names = (
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
        "_fork_exec",
        "_posixsubprocess",
    )
    for name in names:
        if not hasattr(sp, name):
            continue
        current = getattr(sp, name)
        original = _original_subprocess_attr(name, current)
        if original is not None and original is not current:
            saved[name] = current
            setattr(sp, name, original)
    try:
        yield
    finally:
        for name, patched in saved.items():
            setattr(sp, name, patched)


def run_subprocess_cmd(
    cmd: Sequence[str],
    *,
    timeout: float = 600.0,
    check: bool = True,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """子进程统一入口：hub 上用 os.system 降级，OS 线程用原生 subprocess。"""
    if _on_gevent_hub() and subprocess_gevent_patched():
        code, stdout, stderr = run_subprocess_safe(
            list(cmd),
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    else:
        with unpatched_subprocess():
            proc = subprocess.run(
                list(cmd),
                capture_output=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
                cwd=cwd,
                env=env,
            )
            code = int(proc.returncode)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
    if check and code != 0:
        detail = (stderr or stdout or "").strip() or f"exit {code}"
        raise RuntimeError(f"command failed: {detail}")
    return code, stdout, stderr


def run_in_os_thread(func: Callable[[], None], *, daemon: bool = True) -> None:
    """CPU / 子进程密集任务：真 OS 线程，避免占满 gevent hub。

    适用于转写、OCR、大批量 LLM 等长时间不 yield 的工作。
    调用方须在 func 内自行建立 Flask ``app_context``。
    gevent patch 后子线程内须恢复原生 subprocess（yt-dlp/ffmpeg 等）。
    """
    def _wrapper() -> None:
        with unpatched_subprocess():
            func()

    threading.Thread(target=_wrapper, daemon=daemon).start()


def _on_gevent_hub() -> bool:
    """gevent WSGI 的请求处理跑在主线程，join 会阻塞整个 hub。"""
    return threading.current_thread() is threading.main_thread()


def _hub_sleep(seconds: float) -> None:
    try:
        from gevent import sleep as gevent_sleep

        gevent_sleep(seconds)
    except ImportError:
        time.sleep(seconds)


def wait_futures_hub(
    futures: Iterable[Future[_T]],
    *,
    poll_sec: float = 0.02,
    timeout: float | None = None,
) -> list[Future[_T]]:
    """等待 ProcessPool / ThreadPool future；gevent hub 上轮询让出。"""
    pending = {f for f in futures if not f.done()}
    if not pending:
        return list(futures)

    deadline = time.time() + timeout if timeout is not None else None
    while pending:
        done_now = {f for f in pending if f.done()}
        pending -= done_now
        if not pending:
            break
        if deadline is not None and time.time() > deadline:
            raise TimeoutError("wait_futures_hub timed out")
        if _on_gevent_hub():
            _hub_sleep(poll_sec)
        else:
            time.sleep(poll_sec)
    return list(futures)


def _wait_worker_thread(
    thread: threading.Thread,
    *,
    result_q: queue.Queue[tuple[int, str, str]],
    error_q: queue.Queue[BaseException],
    timeout: float,
    cmd_label: str,
) -> tuple[int, str, str]:
    """等待工作线程结束；在 gevent hub 上轮询，避免 thread.join 卡死接口。"""
    wait = timeout + 5.0
    deadline = time.time() + wait

    def _drain_queues() -> tuple[int, str, str] | None:
        try:
            raise error_q.get_nowait()
        except Empty:
            pass
        try:
            return result_q.get_nowait()
        except Empty:
            return None

    if _on_gevent_hub():
        while thread.is_alive():
            if time.time() > deadline:
                raise TimeoutError(f"命令执行超时: {cmd_label}")
            ready = _drain_queues()
            if ready is not None:
                return ready
            _hub_sleep(0.01)
    else:
        thread.join(timeout=wait)
        if thread.is_alive():
            raise TimeoutError(f"命令执行超时: {cmd_label}")

    try:
        raise error_q.get_nowait()
    except Empty:
        pass

    ready = _drain_queues()
    if ready is not None:
        return ready

    raise TimeoutError(f"命令执行超时或进程异常退出: {cmd_label}")


def run_subprocess_safe(
    cmd: Sequence[str],
    *,
    timeout: float = 30.0,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> tuple[int, str, str]:
    """在线程中用 os.system + 临时文件执行命令，绕过 gevent 的 subprocess patch。

    Returns:
        (returncode, stdout, stderr)
    """
    cmd_label = " ".join(cmd)
    result_queue: queue.Queue[tuple[int, str, str]] = queue.Queue(maxsize=1)
    error_queue: queue.Queue[BaseException] = queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            _run_with_os_system(list(cmd), timeout, env, cwd, result_queue, error_queue)
        except BaseException as exc:
            error_queue.put(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return _wait_worker_thread(
        thread,
        result_q=result_queue,
        error_q=error_queue,
        timeout=timeout,
        cmd_label=cmd_label,
    )


def _run_with_os_system(
    cmd_list: list[str],
    timeout_val: float,
    env_dict: Optional[dict[str, str]],
    cwd_path: Optional[str],
    result_q: queue.Queue[tuple[int, str, str]],
    error_q: queue.Queue[BaseException],
) -> None:
    stdout_path: str | None = None
    stderr_path: str | None = None
    returncode_path: str | None = None
    extra_cleanup: list[str | None] = []

    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".stdout") as tmp_stdout:
            stdout_path = tmp_stdout.name
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".stderr") as tmp_stderr:
            stderr_path = tmp_stderr.name
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".returncode") as tmp_rc:
            returncode_path = tmp_rc.name

        shell_cmd = _build_shell_command(
            cmd_list,
            env_dict,
            cwd_path,
            stdout_path,
            stderr_path,
            returncode_path,
        )
        # Windows 上 _build_shell_command 返回 .bat 文件路径，需一并清理
        extra_cleanup: list[str | None] = []
        if sys.platform == "win32" and shell_cmd.endswith(".bat"):
            extra_cleanup.append(shell_cmd)
        returncode = _execute_with_timeout(shell_cmd, timeout_val, cmd_list, error_q)
        if returncode is None:
            _cleanup_temp_files(extra_cleanup)
            return

        final_returncode = _read_returncode(returncode_path, returncode)
        stdout = _read_file_safe(stdout_path)
        stderr = _read_file_safe(stderr_path)
        result_q.put((final_returncode, stdout, stderr))
    except BaseException as exc:
        error_q.put(exc)
    finally:
        _cleanup_temp_files([stdout_path, stderr_path, returncode_path] + extra_cleanup)


def _build_shell_command(
    cmd_list: list[str],
    env_dict: Optional[dict[str, str]],
    cwd_path: Optional[str],
    stdout_path: str,
    stderr_path: str,
    returncode_path: str,
) -> str:
    if sys.platform == "win32":
        # Windows cmd.exe 不识别单引号，需用双引号（list2cmdline）
        quoted_cmd = subprocess.list2cmdline(cmd_list)
        return _build_windows_command(
            quoted_cmd,
            env_dict,
            cwd_path,
            stdout_path,
            stderr_path,
            returncode_path,
        )
    quoted_cmd = " ".join(shlex.quote(arg) for arg in cmd_list)
    return _build_unix_command(
        quoted_cmd,
        env_dict,
        cwd_path,
        stdout_path,
        stderr_path,
        returncode_path,
    )


def _build_windows_command(
    quoted_cmd: str,
    env_dict: Optional[dict[str, str]],
    cwd_path: Optional[str],
    stdout_path: str,
    stderr_path: str,
    returncode_path: str,
) -> str:
    """Windows: 写临时 bat 文件执行，避免 cmd /c 嵌套引号导致 && 失效。"""
    bat_path = tempfile.mktemp(suffix=".bat")
    lines: list[str] = ["@echo off"]
    if cwd_path:
        lines.append(f'cd /d "{cwd_path}"')
    if env_dict:
        for key, value in env_dict.items():
            lines.append(f'set {key}={value}')
    # bat 会吃掉单个 %（如 ffmpeg 的 frame_%04d.png），命令本体需写成 %%
    safe_cmd = quoted_cmd.replace("%", "%%")
    lines.append(f'{safe_cmd} > "{stdout_path}" 2> "{stderr_path}"')
    lines.append(
        f'if %ERRORLEVEL% EQU 0 (echo 0 > "{returncode_path}") '
        f'else (echo %ERRORLEVEL% > "{returncode_path}")'
    )
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))
    return bat_path


def _build_unix_command(
    quoted_cmd: str,
    env_dict: Optional[dict[str, str]],
    cwd_path: Optional[str],
    stdout_path: str,
    stderr_path: str,
    returncode_path: str,
) -> str:
    env_cmd = ""
    if env_dict:
        env_cmd = "env " + " ".join(f"{k}={shlex.quote(v)}" for k, v in env_dict.items()) + " "
    cd_cmd = f"cd {shlex.quote(cwd_path)} && " if cwd_path else ""
    full_cmd = (
        f"{cd_cmd}({env_cmd}{quoted_cmd} > {shlex.quote(stdout_path)} "
        f"2> {shlex.quote(stderr_path)}); echo $? > {shlex.quote(returncode_path)}"
    )
    return f"sh -c {shlex.quote(full_cmd)}"


def _execute_with_timeout(
    shell_cmd: str,
    timeout_val: float,
    cmd_list: list[str],
    error_q: queue.Queue[BaseException],
) -> int | None:
    system_result: dict[str, object] = {
        "returncode": None,
        "done": False,
        "exception": None,
    }

    def run_cmd() -> None:
        try:
            system_result["returncode"] = os.system(shell_cmd)
            system_result["done"] = True
        except BaseException as exc:
            system_result["exception"] = exc
            system_result["done"] = True

    cmd_thread = threading.Thread(target=run_cmd, daemon=True)
    cmd_thread.start()
    cmd_thread.join(timeout=timeout_val)

    if system_result["exception"]:
        error_q.put(system_result["exception"])  # type: ignore[arg-type]
        return None

    if not system_result["done"]:
        error_q.put(TimeoutError(f"命令执行超时: {' '.join(cmd_list)}"))
        return None

    return int(system_result["returncode"])  # type: ignore[arg-type]


def _read_returncode(returncode_path: str | None, system_returncode: int | None) -> int:
    if returncode_path:
        try:
            with open(returncode_path, encoding="utf-8") as handle:
                returncode_str = handle.read().strip()
                if returncode_str.isdigit():
                    return int(returncode_str)
        except OSError:
            pass

    if system_returncode is not None:
        if sys.platform == "win32":
            return system_returncode
        return system_returncode >> 8 if system_returncode else 0

    return 0


def _read_file_safe(file_path: str | None) -> str:
    if not file_path:
        return ""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _cleanup_temp_files(file_paths: list[str | None]) -> None:
    for file_path in file_paths:
        if not file_path:
            continue
        try:
            os.unlink(file_path)
        except OSError:
            pass
