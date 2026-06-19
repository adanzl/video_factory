"""在 gevent 环境中通过原生线程执行阻塞任务与外部命令。

主进程使用 gevent（main.py 设置 thread=False），标准库 threading 仍是真实 OS 线程。
subprocess 被 gevent patch 后，子线程中不能直接调用 subprocess，需用 os.system 降级。
"""
from __future__ import annotations

import os
import queue
import shlex
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from typing import Optional


def run_in_background(func: Callable[[], None], *, daemon: bool = True) -> None:
    """后台线程执行，不等待结果。"""
    threading.Thread(target=func, daemon=daemon).start()


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
    result_queue: queue.Queue[tuple[int, str, str]] = queue.Queue(maxsize=1)
    error_queue: queue.Queue[BaseException] = queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            _run_with_os_system(list(cmd), timeout, env, cwd, result_queue, error_queue)
        except BaseException as exc:
            error_queue.put(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout + 5)

    if thread.is_alive():
        raise TimeoutError(f"命令执行超时: {' '.join(cmd)}")

    if not error_queue.empty():
        raise error_queue.get()

    if result_queue.empty():
        raise TimeoutError(f"命令执行超时或进程异常退出: {' '.join(cmd)}")

    return result_queue.get()


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
        returncode = _execute_with_timeout(shell_cmd, timeout_val, cmd_list, error_q)
        if returncode is None:
            return

        final_returncode = _read_returncode(returncode_path, returncode)
        stdout = _read_file_safe(stdout_path)
        stderr = _read_file_safe(stderr_path)
        result_q.put((final_returncode, stdout, stderr))
    except BaseException as exc:
        error_q.put(exc)
    finally:
        _cleanup_temp_files([stdout_path, stderr_path, returncode_path])


def _build_shell_command(
    cmd_list: list[str],
    env_dict: Optional[dict[str, str]],
    cwd_path: Optional[str],
    stdout_path: str,
    stderr_path: str,
    returncode_path: str,
) -> str:
    quoted_cmd = " ".join(shlex.quote(arg) for arg in cmd_list)
    if sys.platform == "win32":
        return _build_windows_command(
            quoted_cmd,
            env_dict,
            cwd_path,
            stdout_path,
            stderr_path,
            returncode_path,
        )
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
    parts: list[str] = []
    if cwd_path:
        parts.append(f"cd /d {shlex.quote(cwd_path)}")
    if env_dict:
        for key, value in env_dict.items():
            parts.append(f"set {key}={shlex.quote(value)}")
    parts.append(f"{quoted_cmd} > {shlex.quote(stdout_path)} 2> {shlex.quote(stderr_path)}")
    parts.append(
        f"&& echo 0 > {shlex.quote(returncode_path)} "
        f"|| echo %ERRORLEVEL% > {shlex.quote(returncode_path)}"
    )
    return f'cmd /c "{" && ".join(parts)}"'


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
