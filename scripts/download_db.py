#!/usr/bin/env python3
import subprocess, os, sys

remote_host = "leo@mini"
remote_base = "/home/leo/project/video_factory"
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

files = [
    (f"{remote_base}/data/data.db", os.path.join(project_dir, 'data', 'data.db')),
    (f"{remote_base}/logs/app.log", os.path.join(project_dir, 'logs', 'app.log')),
]

for remote, local in files:
    d = os.path.dirname(local)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    r = subprocess.run(['scp', f'{remote_host}:{remote}', local], capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        print(f"OK {os.path.basename(local)}")
    else:
        print(f"FAIL {os.path.basename(local)}: {r.stderr.strip()}")
