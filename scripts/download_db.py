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


def download_files_from_server():
    """从服务器下载多个文件"""
    remote_host = "leo@mini"
    remote_base = "/mnt/data/project/video_factory"
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    for i in range(1, 4):
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
    print(f"远程服务器: {remote_host}")
    print(f"文件数量: {len(files_to_download)}")
    print("=" * 60)

    logs_dir = os.path.join(project_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)

    success_count = 0
    fail_count = 0
    control_path = _ssh_control_path()

    if _use_ssh_multiplexing():
        print("\n建立 SSH 连接 ...")
        try:
            master_cmd = [
                "ssh",
                "-o",
                "ControlMaster=yes",
                "-o",
                f"ControlPath={control_path}",
                "-o",
                "ControlPersist=600",
                remote_host,
                "echo connected",
            ]
            result = subprocess.run(
                master_cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"✗ SSH 连接失败: {result.stderr}")
                return 0, len(files_to_download)
            print("✓ SSH 连接已建立\n")
        except Exception as e:
            print(f"✗ 建立 SSH 连接失败: {e}")
            return 0, len(files_to_download)
    else:
        print("\n测试 SSH 连接 ...")
        try:
            result = subprocess.run(
                ["ssh", remote_host, "echo connected"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"✗ SSH 连接失败: {result.stderr}")
                return 0, len(files_to_download)
            print("✓ SSH 连接正常\n")
        except Exception as e:
            print(f"✗ 建立 SSH 连接失败: {e}")
            return 0, len(files_to_download)

    for file_info in files_to_download:
        local_dir = os.path.dirname(file_info["local"])
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)

        if _use_ssh_multiplexing():
            cmd = [
                "scp",
                "-o",
                f"ControlPath={control_path}",
                f'{remote_host}:{file_info["remote"]}',
                file_info["local"],
            ]
        else:
            cmd = [
                "scp",
                f'{remote_host}:{file_info["remote"]}',
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

    if _use_ssh_multiplexing():
        try:
            close_cmd = [
                "ssh",
                "-o",
                f"ControlPath={control_path}",
                "-O",
                "exit",
                remote_host,
            ]
            subprocess.run(close_cmd, capture_output=True, timeout=5)
        except Exception:
            pass

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
