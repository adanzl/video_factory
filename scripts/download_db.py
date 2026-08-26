#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从远程服务器下载文件并替换本地文件（paramiko，无需 sshpass）。

下载文件:
  - data/data.db
  - logs/app.log
  - logs/app.log.YYYY-MM-DD (最近 2 天)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE_BASE = "/mnt/data/project/video_factory"
# (host, port, connect_timeout_sec)
REMOTE_HOSTS = [
    ("mini", 22, 2),
    ("vip.sy.frp.one", 57904, 10),
    ("cn-hk-bgp-4.ofalias.net", 27358, 10),
]
SSH_USER = "leo"


def _password() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    value = os.getenv("SSH_PASSWORD") or ""
    if not value.strip():
        raise RuntimeError("缺少 SSH_PASSWORD，请在 .env 中配置")
    return value


def _resolve_ssh_endpoint(host: str, port: int) -> tuple[str, int, str]:
    """解析 ~/.ssh/config 中的 Host 别名（mini 等）。"""
    hostname = host
    resolved_port = port
    username = SSH_USER
    user_config = os.path.expanduser("~/.ssh/config")
    if os.path.isfile(user_config):
        try:
            import paramiko

            config = paramiko.SSHConfig()
            with open(user_config, encoding="utf-8") as fh:
                config.parse(fh)
            lookup = config.lookup(host)
            hostname = lookup.get("hostname", hostname)
            if lookup.get("port"):
                resolved_port = int(lookup["port"])
            if lookup.get("user"):
                username = lookup["user"]
        except Exception:
            pass
    return hostname, resolved_port, username


def _build_file_list() -> list[dict[str, str]]:
    files: list[dict[str, str]] = [
        {
            "remote": f"{REMOTE_BASE}/data/data.db",
            "local": str(ROOT / "data" / "data.db"),
            "desc": "数据库文件",
        },
        {
            "remote": f"{REMOTE_BASE}/logs/app.log",
            "local": str(ROOT / "logs" / "app.log"),
            "desc": "应用日志",
        },
    ]
    today = datetime.now()
    for i in range(1, 3):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        log_filename = f"app.log.{date_str}"
        files.append(
            {
                "remote": f"{REMOTE_BASE}/logs/{log_filename}",
                "local": str(ROOT / "logs" / log_filename),
                "desc": f"应用日志 ({date_str})",
            }
        )
    return files


def _format_size(path: str) -> str:
    size = os.path.getsize(path)
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    return f"{size / 1024:.2f} KB"


def _download_files(
    host: str,
    port: int,
    password: str,
    connect_timeout: int,
    files_to_download: list[dict[str, str]],
) -> tuple[int, int]:
    import paramiko

    hostname, resolved_port, username = _resolve_ssh_endpoint(host, port)
    label = f"{username}@{hostname}:{resolved_port}"
    print(f"  尝试连接: {label} (timeout={connect_timeout}s) ...")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=hostname,
        port=resolved_port,
        username=username,
        password=password,
        timeout=connect_timeout,
        allow_agent=True,
        look_for_keys=True,
    )

    print(f"  ✓ 已连接: {label}\n")
    success_count = 0
    fail_count = 0
    try:
        sftp = client.open_sftp()
        for file_info in files_to_download:
            local_path = file_info["local"]
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)

            print(f"[{file_info['desc']}]")
            print(f"  远程: {file_info['remote']}")
            print(f"  本地: {local_path}")
            try:
                sftp.get(file_info["remote"], local_path)
                print("  ✓ 下载成功")
                if os.path.exists(local_path):
                    print(f"  文件大小: {_format_size(local_path)}")
                success_count += 1
            except Exception as exc:
                print(f"  ✗ 下载失败: {exc}")
                fail_count += 1
        sftp.close()
    finally:
        client.close()

    return success_count, fail_count


def download_files_from_server() -> tuple[int, int]:
    password = _password()
    files_to_download = _build_file_list()

    print("=" * 60)
    print("从服务器下载文件")
    print("=" * 60)
    labels = []
    for h, p, _ in REMOTE_HOSTS:
        hostname, resolved_port, username = _resolve_ssh_endpoint(h, p)
        labels.append(f"{username}@{hostname}:{resolved_port}")
    print(f"候选服务器: {', '.join(labels)}")
    print(f"文件数量: {len(files_to_download)}")
    print("=" * 60)

    os.makedirs(ROOT / "logs", exist_ok=True)

    print("\n建立 SSH 连接 (paramiko) ...")
    last_err = ""
    for host, port, connect_timeout in REMOTE_HOSTS:
        try:
            return _download_files(
                host,
                port,
                password,
                connect_timeout,
                files_to_download,
            )
        except Exception as exc:
            hostname, resolved_port, username = _resolve_ssh_endpoint(host, port)
            label = f"{username}@{hostname}:{resolved_port}"
            last_err = str(exc)
            print(f"  ✗ 连接失败: {label} ({exc})")

    print(f"✗ 所有候选服务器均无法连接: {last_err}")
    return 0, len(files_to_download)


def main() -> int:
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
            return 0
        if success_count > 0:
            print("⚠ 部分文件下载成功，请检查失败的文件")
            return 1
        print("✗ 所有文件下载失败！请检查网络连接和 SSH 配置")
        return 1
    except RuntimeError as exc:
        print(f"\n✗ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        return 130
    except Exception as exc:
        print(f"\n发生未预期的错误: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
