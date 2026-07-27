#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

remote_host = "leo@mini"
remote_base = "/home/leo/project/video_factory"
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_ssh_password() -> str:
    env_path = os.path.join(project_dir, ".env")
    if not os.path.isfile(env_path):
        return ""
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "SSH_PASSWORD":
                return value.strip().strip('"').strip("'")
    return ""


password = read_ssh_password()
if not password:
    print("FAIL: .env 中未找到 SSH_PASSWORD", file=sys.stderr)
    sys.exit(1)
if not shutil.which("sshpass"):
    print("FAIL: 未安装 sshpass（macOS: brew install sshpass）", file=sys.stderr)
    sys.exit(1)

scp_env = {**os.environ, "SSHPASS": password}

files = [
    (f"{remote_base}/data/data.db", os.path.join(project_dir, "data", "data.db")),
    (f"{remote_base}/logs/app.log", os.path.join(project_dir, "logs", "app.log")),
]

for remote, local in files:
    d = os.path.dirname(local)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    r = subprocess.run(
        [
            "sshpass",
            "-e",
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            f"{remote_host}:{remote}",
            local,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=scp_env,
    )
    if r.returncode == 0:
        print(f"OK {os.path.basename(local)}")
    else:
        err = (r.stderr or r.stdout or "").strip()
        print(f"FAIL {os.path.basename(local)}: {err}")
