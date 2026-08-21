#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从远程服务器下载文件并替换本地文件
服务器配置: SSH Host Mini
下载文件:
  - data/data.db
  - logs/app.log
  - logs/app.log.YYYY-MM-DD (最近3天的日志)
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta


def _ssh_control_path():
    """SSH 复用连接的 ControlPath（仅 Unix/macOS 有效）。

    macOS 上 `tempfile.gettempdir()` 常常是 `/var/folders/.../T` 这类很长的路径，
    再拼上 `%r@%h:%p` 后容易超过 Unix domain socket 的长度限制，导致：
    `unix_listener: path "... too long for Unix domain socket"`

    这里改用更短的固定目录 `/tmp`，并使用 OpenSSH 的 `%C` 哈希占位符缩短文件名。
    """
    return os.path.join("/tmp", "ssh_mux_%C")


def _use_ssh_multiplexing():
    """Windows OpenSSH 不支持 ControlMaster，会报 getsockname failed。"""
    return sys.platform != "win32"


# 远程主机 fallback：先局域网，后广域网（与 AGENTS.md 优先级一致）
# (host, port, connect_timeout_sec) — port=None 走 ~/.ssh/config；局域网快速失败
REMOTE_HOSTS = [
    ("mini", None, 2),
    ("vip.sy.frp.one", 57904, 10),
    ("cn-hk-bgp-4.ofalias.net", 27358, 10),
]
SSH_USER = "leo"


def _project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ssh_password() -> str:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_dir(), ".env"))
    password = os.getenv("SSH_PASSWORD") or ""
    if not password.strip():
        raise RuntimeError("缺少 SSH_PASSWORD，请在 .env 中配置")
    return password


def _sshpass_prefix(password: str) -> list[str]:
    sshpass = shutil.which("sshpass")
    if not sshpass:
        raise RuntimeError("需要 sshpass：brew install sshpass")
    os.environ["SSHPASS"] = password
    return [sshpass, "-e"]


def _ssh_auth_opts() -> list[str]:
    return [
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        # cSpell: disable-next-line
        "PreferredAuthentications=publickey,password",
    ]


def _ssh_target(host: str) -> str:
    """生成 ssh/scp 的目标主机参数（不含 -p/-P）。"""
    if host == "mini":
        return "mini"
    return f"{SSH_USER}@{host}"


def _host_label(host: str, port: int | None) -> str:
    target = _ssh_target(host)
    return f"{target}:{port}" if port else target


def _ssh_port_opts(port: int | None) -> list[str]:
    return ["-p", str(port)] if port else []


def _scp_port_opts(port: int | None) -> list[str]:
    return ["-P", str(port)] if port else []


def _connect_ssh(host, port, control_path, prefix, connect_timeout=10):
    """尝试连接指定远程主机，成功返回 True。"""
    run_timeout = connect_timeout + 5
    target = _ssh_target(host)
    common_opts = [
        *_ssh_auth_opts(),
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "ConnectionAttempts=1",
    ]
    if _use_ssh_multiplexing():
        master_cmd = prefix + [
            "ssh",
            *common_opts,
            "-o",
            "ControlMaster=yes",
            "-o",
            f"ControlPath={control_path}",
            "-o",
            "ControlPersist=600",
            *_ssh_port_opts(port),
            target,
            "echo connected",
        ]
    else:
        master_cmd = prefix + [
            "ssh",
            *common_opts,
            *_ssh_port_opts(port),
            target,
            "echo connected",
        ]
    result = subprocess.run(
        master_cmd, capture_output=True, text=True, timeout=run_timeout
    )
    return result.returncode == 0


def _close_ssh(host, port, control_path):
    """关闭 SSH 复用连接（忽略错误）。"""
    if not _use_ssh_multiplexing():
        return
    try:
        close_cmd = [
            "ssh",
            "-o",
            f"ControlPath={control_path}",
            "-O",
            "exit",
            *_ssh_port_opts(port),
            _ssh_target(host),
        ]
        subprocess.run(close_cmd, capture_output=True, timeout=5)
    except Exception:
        pass


def _resolve_remote_host(control_path, prefix):
    """按 fallback 列表依次尝试，返回首个可用的 (host, port)。"""
    for host, port, connect_timeout in REMOTE_HOSTS:
        label = _host_label(host, port)
        print(f"  尝试连接: {label} (timeout={connect_timeout}s) ...")
        try:
            if _connect_ssh(host, port, control_path, prefix, connect_timeout):
                print(f"  ✓ 已连接: {label}\n")
                return host, port
            print(f"  ✗ 连接失败: {label}")
            _close_ssh(host, port, control_path)
        except subprocess.TimeoutExpired:
            print(f"  ✗ 连接超时: {label}")
            _close_ssh(host, port, control_path)
        except Exception as e:
            print(f"  ✗ 连接异常 ({label}): {e}")
            _close_ssh(host, port, control_path)
    return None


def download_files_from_server():
    """从服务器下载多个文件"""
    remote_base = "/mnt/data/project/video_factory"
    project_dir = _project_dir()
    prefix = _sshpass_prefix(_ssh_password())

    files_to_download = [
        {
            "remote": f"{remote_base}/data/data.db",
            "local": os.path.join(project_dir, "data", "data.db"),
            "desc": "数据库文件",
        },
        {
            "remote": f"{remote_base}/logs/app.log",
            "local": os.path.join(project_dir, "logs", "app.log"),
            "desc": "应用日志",
        },
    ]

    today = datetime.now()
    for i in range(1, 3):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        log_filename = f"app.log.{date_str}"
        files_to_download.append(
            {
                "remote": f"{remote_base}/logs/{log_filename}",
                "local": os.path.join(project_dir, "logs", log_filename),
                "desc": f"应用日志 ({date_str})",
            }
        )

    print("=" * 60)
    print("从服务器下载文件")
    print("=" * 60)
    print(f"候选服务器: {', '.join(_host_label(h, p) for h, p, _ in REMOTE_HOSTS)}")
    print(f"文件数量: {len(files_to_download)}")
    print("=" * 60)

    logs_dir = os.path.join(project_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)

    success_count = 0
    fail_count = 0
    control_path = _ssh_control_path()

    print("\n建立 SSH 连接 ...")
    resolved = _resolve_remote_host(control_path, prefix)
    if not resolved:
        print("✗ 所有候选服务器均无法连接")
        return 0, len(files_to_download)
    remote_host, remote_port = resolved
    remote_label = _host_label(remote_host, remote_port)
    remote_target = _ssh_target(remote_host)
    print(f"使用服务器: {remote_label}")

    for file_info in files_to_download:
        local_dir = os.path.dirname(file_info["local"])
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)

        if _use_ssh_multiplexing():
            cmd = [
                "scp",
                "-o",
                f"ControlPath={control_path}",
                *_scp_port_opts(remote_port),
                f'{remote_target}:{file_info["remote"]}',
                file_info["local"],
            ]
        else:
            cmd = prefix + [
                "scp",
                *_ssh_auth_opts(),
                *_scp_port_opts(remote_port),
                f'{remote_target}:{file_info["remote"]}',
                file_info["local"],
            ]

        print(f"[{file_info['desc']}]")
        print(f"  远程: {file_info['remote']}")
        print(f"  本地: {file_info['local']}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print("  ✓ 下载成功")
                if os.path.exists(file_info["local"]):
                    file_size = os.path.getsize(file_info["local"])
                    if file_size > 1024 * 1024:
                        print(
                            f"  文件大小: {file_size / (1024 * 1024):.2f} MB"
                        )
                    else:
                        print(f"  文件大小: {file_size / 1024:.2f} KB")
                success_count += 1
            else:
                print(f"  ✗ 下载失败: {result.stderr.strip()}")
                fail_count += 1
        except subprocess.TimeoutExpired:
            print("  ✗ 下载超时")
            fail_count += 1
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            fail_count += 1

    _close_ssh(remote_host, remote_port, control_path)

    return success_count, fail_count


def main():
    """主函数"""
    try:
        success_count, fail_count = download_files_from_server()

        print("\n" + "=" * 60)
        print("下载结果汇总")
        print("=" * 60)
        print(f"成功: {success_count} 个文件")
        print(f"失败: {fail_count} 个文件")
        print("=" * 60)

        if fail_count == 0:
            print("✓ 所有文件下载成功！")
            sys.exit(0)
        elif success_count > 0:
            print("⚠ 部分文件下载成功，请检查失败的文件")
            sys.exit(1)
        else:
            print("✗ 所有文件下载失败！请检查网络连接和SSH配置")
            sys.exit(1)

    except RuntimeError as e:
        print(f"\n✗ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n发生未预期的错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
