"""B 站投稿：分片上传视频、封面，再提交稿件。"""

from __future__ import annotations

import base64
import json
import logging
import math
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from app.services.publish.bilibili.session import BiliSession, USER_AGENT

logger = logging.getLogger(__name__)

PREUPLOAD_URL = "https://member.bilibili.com/preupload"
COVER_URL = "https://member.bilibili.com/x/vu/web/cover/up"
SUBMIT_URL = "https://member.bilibili.com/x/vu/web/add/v3"
PROFILE = "ugcupos/bup"
APP_VERSION = "2.14.0"
APP_BUILD = "2140000"


class BiliUploader:
    def __init__(self, session: BiliSession | None = None) -> None:
        self.session = session or BiliSession()

    def publish(
        self,
        *,
        title: str,
        description: str,
        tags: list[str],
        video_path: Path,
        cover_path: Path | None,
        tid: int,
        copyright: int = 1,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        creation_statement: dict[str, Any] | None = None,
        topic_id: int | None = None,
        mission_id: int | None = None,
    ) -> dict[str, Any]:
        video = Path(video_path)
        if not video.is_file():
            raise FileNotFoundError(f"成片不存在: {video}")
        http = self.session.http()
        csrf = self.session.csrf()
        if not csrf:
            raise RuntimeError("缺少 bili_jct，请重新扫码登录")
        filename = self._upload_video(http, video)
        cover_url = self._upload_cover(http, csrf, cover_path) if cover_path else ""
        return self._submit(
            http,
            csrf=csrf,
            title=title,
            description=description,
            tags=tags,
            filename=filename,
            cover_url=cover_url,
            tid=tid,
            copyright=copyright,
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            creation_statement=creation_statement,
            topic_id=topic_id,
            mission_id=mission_id,
        )

    def _upload_video(self, http: requests.Session, video: Path) -> str:
        size = video.stat().st_size
        probe = http.get(
            PREUPLOAD_URL,
            params={
                "name": video.name,
                "size": size,
                "r": "upos",
                "profile": PROFILE,
                "ssl": "0",
                "version": APP_VERSION,
                "build": APP_BUILD,
                "webVersion": "2.0.0",
            },
            timeout=30,
        )
        probe.raise_for_status()
        data = probe.json()
        if int(data.get("OK") or 0) != 1:
            raise RuntimeError(f"preupload 失败: {data}")
        endpoint = str(data.get("endpoint") or "").strip()
        if endpoint.startswith("//"):
            endpoint = f"https:{endpoint}"
        elif endpoint.startswith("http://"):
            endpoint = "https://" + endpoint[len("http://") :]
        upos_uri = str(data.get("upos_uri") or "")
        object_key = upos_uri.split("upos://", 1)[-1]
        auth = str(data.get("auth") or "")
        biz_id = data.get("biz_id")
        chunk_size = int(data.get("chunk_size") or 8 * 1024 * 1024)
        upload_url = f"{endpoint}/{object_key}"
        headers = {"X-Upos-Auth": auth, "User-Agent": USER_AGENT}

        init = http.post(
            upload_url,
            params={"uploads": "", "output": "json"},
            headers=headers,
            timeout=30,
        )
        init.raise_for_status()
        upload_id = str(init.json().get("upload_id") or "")
        if not upload_id:
            raise RuntimeError(f"获取 upload_id 失败: {init.text[:200]}")

        chunks = max(1, math.ceil(size / chunk_size))
        parts: list[dict[str, Any]] = []
        with video.open("rb") as handle:
            for index in range(chunks):
                payload = handle.read(chunk_size)
                start = index * chunk_size
                end = start + len(payload) - 1
                resp = http.put(
                    upload_url,
                    params={
                        "partNumber": index + 1,
                        "uploadId": upload_id,
                        "chunk": index,
                        "chunks": chunks,
                        "size": len(payload),
                        "start": start,
                        "end": end,
                        "total": size,
                    },
                    headers=headers,
                    data=payload,
                    timeout=120,
                )
                resp.raise_for_status()
                parts.append({"partNumber": index + 1, "eTag": "etag"})
                logger.info(
                    "bili upload chunk %s/%s bytes=%s",
                    index + 1,
                    chunks,
                    len(payload),
                )

        complete = http.post(
            upload_url,
            params={
                "output": "json",
                "name": quote(video.name),
                "profile": PROFILE,
                "uploadId": upload_id,
                "biz_id": biz_id,
            },
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps({"parts": parts}),
            timeout=60,
        )
        complete.raise_for_status()
        filename = Path(object_key).stem
        logger.info("bili video uploaded filename=%s", filename)
        return filename

    def _upload_cover(
        self,
        http: requests.Session,
        csrf: str,
        cover_path: Path | None,
    ) -> str:
        if cover_path is None:
            return ""
        path = Path(cover_path)
        if not path.is_file():
            logger.warning("cover missing, skip: %s", path)
            return ""
        raw = path.read_bytes()
        mime = "image/jpeg"
        suffix = path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        resp = http.post(
            COVER_URL,
            data={"csrf": csrf, "cover": data_url},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        url = ""
        data = payload.get("data")
        if isinstance(data, dict):
            url = str(data.get("url") or "")
        elif isinstance(data, str):
            url = data
        if payload.get("code") not in (0, None) or not url:
            raise RuntimeError(f"封面上传失败: {payload}")
        return url

    def _submit(
        self,
        http: requests.Session,
        *,
        csrf: str,
        title: str,
        description: str,
        tags: list[str],
        filename: str,
        cover_url: str,
        tid: int,
        copyright: int,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        creation_statement: dict[str, Any] | None = None,
        topic_id: int | None = None,
        mission_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "copyright": copyright,
            "videos": [{"filename": filename, "title": title, "desc": ""}],
            "source": "",
            "tid": int(tid),
            "cover": cover_url,
            "title": title[:80],
            "tag": ",".join(tags),
            "desc_format_id": 9999,
            "desc": description,
            "dynamic": dynamic,
            "interactive": 0,
            "recreate": -1,
            "act_reserve_create": 0,
            "no_disturbance": 0,
            "no_reprint": 1 if copyright == 1 else 0,
            "subtitle": {"open": 0, "lan": ""},
            "dolby": 0,
            "lossless_music": 0,
            "up_selection_reply": False,
            "up_close_reply": False,
            "up_close_danmu": False,
            "web_os": 3,
        }
        if human_type2 is not None:
            body["human_type2"] = int(human_type2)
        if creation_statement:
            body["creation_statement"] = creation_statement
        if topic_id:
            body["topic_id"] = int(topic_id)
            body["mission_id"] = int(mission_id or 0)
            body["topic_detail"] = {
                "from_topic_id": int(topic_id),
                "from_source": "arc.web.recommend",
            }
        if dtime is not None:
            body["dtime"] = int(dtime)
        logger.info(
            "bili submit title=%r copyright=%s tid=%s human_type2=%s "
            "creation_statement=%s topic_id=%s mission_id=%s dtime=%s tags=%s filename=%s",
            title[:80],
            copyright,
            tid,
            human_type2,
            creation_statement,
            topic_id,
            mission_id,
            dtime,
            ",".join(tags),
            filename,
        )
        resp = http.post(
            SUBMIT_URL,
            params={"csrf": csrf},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") not in (0, None):
            code = payload.get("code")
            msg = payload.get("message") or f"投稿失败: {payload}"
            logger.warning(
                "bili submit rejected code=%s msg=%s title=%r tid=%s creation_statement=%s",
                code,
                msg,
                title[:80],
                tid,
                creation_statement,
            )
            raise RuntimeError(msg)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        bvid = str(data.get("bvid") or "").strip()
        aid = data.get("aid")
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else None
        logger.info(
            "bili submit ok bvid=%s aid=%s copyright=%s tid=%s human_type2=%s "
            "creation_statement=%s topic_id=%s",
            bvid,
            aid,
            copyright,
            tid,
            human_type2,
            creation_statement,
            topic_id,
        )
        return {
            "platform": "bilibili",
            "status": "success",
            "bvid": bvid or None,
            "aid": aid,
            "url": url,
            "tid": int(tid),
            "copyright": int(copyright),
            "human_type2": int(human_type2) if human_type2 is not None else None,
            "topic_id": int(topic_id) if topic_id else None,
            "mission_id": int(mission_id) if mission_id else None,
            "creation_statement": creation_statement,
            "mark_id": int(creation_statement["id"]) if creation_statement else None,
            "neutral_mark": (
                str(creation_statement.get("content") or "")
                if creation_statement
                else None
            ),
            "message": "upload ok",
        }
