"""B 站 WBI 签名（搜索等接口）。"""

from __future__ import annotations

import time
import urllib.parse
from functools import reduce
from hashlib import md5
from typing import Any

import requests

_MIXIN_KEY_ENC_TABLE: tuple[int, ...] = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20,
    34, 44, 52,
)


def _key_from_url(url: str) -> str:
    name = str(url or "").rsplit("/", 1)[-1]
    return name.split(".", 1)[0]


def fetch_bili_sign_keys(session: requests.Session) -> tuple[str, str]:
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/nav",
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = (payload.get("data") or {}).get("wbi_img") or {}
    img_key = _key_from_url(str(data.get("img_url") or ""))
    sub_key = _key_from_url(str(data.get("sub_url") or ""))
    if not img_key or not sub_key:
        raise RuntimeError("failed to fetch wbi keys")
    return img_key, sub_key


def sign_bili_params(
    params: dict[str, Any],
    *,
    img_key: str,
    sub_key: str,
) -> dict[str, Any]:
    mixin_key = reduce(
        lambda acc, idx: acc + (img_key + sub_key)[idx],
        _MIXIN_KEY_ENC_TABLE,
        "",
    )[:32]
    signed = dict(params)
    signed["wts"] = int(time.time())
    filtered = {
        key: "".join(ch for ch in str(val) if ch not in "!'()*")
        for key, val in sorted(signed.items())
    }
    query = urllib.parse.urlencode(filtered)
    signed["w_rid"] = md5((query + mixin_key).encode()).hexdigest()
    return signed
