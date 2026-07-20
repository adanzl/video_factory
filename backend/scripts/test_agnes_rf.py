"""调试 Agnes chat completions 的 response_format 行为。

用法（需已配置 AGNES_API_KEY 或 AGNES_FREE_API_KEY）::

    python -m scripts.test_agnes_rf /path/to/image.jpg
"""

from __future__ import annotations

import base64
import os
import sys

import requests

_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"


def _api_key() -> str:
    key = (os.getenv("AGNES_API_KEY") or os.getenv("AGNES_FREE_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "缺少 AGNES_API_KEY 或 AGNES_FREE_API_KEY，请从环境变量读取，勿硬编码"
        )
    return key


def _auth_headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def main() -> None:
    image_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/thumb12.jpg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    key = _api_key()
    headers = _auth_headers(key)

    # 测 response_format 对单张图片的影响
    for label, has_rf in [("no_rf", False), ("with_rf", True)]:
        payload: dict = {
            "model": "agnes-2.0-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": '图里是什么？输出JSON格式：{"color":"..."}',
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 100,
        }
        if has_rf:
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(_API_URL, headers=headers, json=payload, timeout=60)
        print(f"{label}: {resp.status_code}", end="")
        if resp.ok:
            c = resp.json()["choices"][0]["message"]["content"]
            print(f" len={len(c)} -> {c[:80]}")
        else:
            print(f" -> {resp.text[:200]}")

    # 测 47 帧 + response_format
    print()
    print("test 47 frames + response_format...")
    content: list = [{"type": "text", "text": "分析这些帧，输出JSON"}]
    for _ in range(47):
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    payload = {
        "model": "agnes-2.0-flash",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(_API_URL, headers=headers, json=payload, timeout=180)
    print(f"47frames+rf: {resp.status_code}", end="")
    if resp.ok:
        c = resp.json()["choices"][0]["message"]["content"]
        print(f" len={len(c)} -> {c[:100]}")
    else:
        print(f" -> {resp.text[:300]}")


if __name__ == "__main__":
    main()
