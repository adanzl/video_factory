"""视频内容分析：抽帧 + Agnes 多模态 → 时间表 JSON。"""

from __future__ import annotations

import base64
import json
import logging
import re
import tempfile
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.llm.llm_agnes import (
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_auth_header,
    is_agnes_quota_exceeded,
    raise_if_agnes_quota,
)
from app.services.media.ffmpeg_utils import extract_frames_interval, probe_duration

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = frozenset({500, 502, 503, 504})


class VideoAnalyzer:
    """分析视频，生成时间表 JSON。

    用法::
        analyzer = VideoAnalyzer(video_path, duration=120.0)
        timeline_json = analyzer.analyze()
    """

    def __init__(self, video_path: Path, duration: float | None = None) -> None:
        self._video_path = Path(video_path)
        self._duration = duration

    # ── public ──────────────────────────────────────────────

    def analyze(self) -> str:
        """执行分析，返回格式化的时间表 JSON 字符串。"""
        if self._duration is None:
            self._duration = probe_duration(self._video_path)

        images_b64, interval = self._extract_frames()
        logger.info(
            "analyzing material with %d frames (interval=%ds, duration=%.1fs)",
            len(images_b64), interval, self._duration,
        )
        system, user = self._build_prompts(images_b64, interval)
        raw = self._call_multimodal(system, user, images_b64)
        return self._validate(raw)

    # ── frame extraction ────────────────────────────────────

    def _extract_frames(self) -> tuple[list[str], int]:
        """抽帧：3s间隔算帧数 → +1 → 重算间隔。"""
        target = int(self._duration / 3) + 1
        interval = max(2, round(self._duration / target))
        with tempfile.TemporaryDirectory() as tmpdir:
            frames = extract_frames_interval(self._video_path, Path(tmpdir), interval)
            if not frames:
                raise ValueError("未能从视频中提取到帧")
            return (
                [base64.b64encode(f.read_bytes()).decode("ascii") for f in frames],
                interval,
            )

    # ── prompt building ─────────────────────────────────────

    def _build_prompts(self, images_b64: list[str], interval: int) -> tuple[str, str]:
        """构造 system / user prompt。"""
        system = (
            "你是一个视频内容分析专家。你的任务是分析视频帧序列，识别其中逐一展示的不同物品/对象，"
            "并为每个对象生成时间表 JSON。\n\n"
            "【语言要求】\n"
            "所有输出文本必须使用简体中文，包括但不限于：title、name、description 字段。\n"
            "不要使用英文或中英混合，专有名词可保留但描述部分必须为中文。"
        )
        user = (
            f"视频时长约 {self._duration:.1f} 秒，共提供 {len(images_b64)} 帧样本"
            f"（每约 {interval} 秒一帧）。\n\n"
            "请严格按以下 JSON Schema 输出，不要添加任何额外字段：\n\n"
            "{\n"
            '  "title": "视频主题（中文，10字以内）",\n'
            '  "duration_sec": 视频总时长（数字，单位秒）,\n'
            '  "segments": [\n'
            "    {\n"
            '      "index": 序号（整数，从1开始）,\n'
            '      "name": "对象名称（中文，须含可点名的核心标识，如：2006年团队之星）",\n'
            '      "description": "简要描述（中文，15-40字，外观特征与可辨识文字）",\n'
            '      "start_sec": 开始时间（数字，秒，精确到0.5秒）,\n'
            '      "end_sec": 结束时间（数字，秒，精确到0.5秒）,\n'
            '      "duration_sec": 持续时长（数字，秒，= end_sec - start_sec）\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "【输出规则】\n"
            "1. 每个不同的视觉对象单独一个 segment，按出现时间顺序排列\n"
            "2. segments 必须覆盖整个视频，无遗漏、无重叠\n"
            "3. 时间戳基于帧样本位置推断，精确到±1秒\n"
            "4. duration_sec 必须等于 end_sec - start_sec\n"
            "5. 最后一个 segment 的 end_sec 应接近视频总时长\n"
            "6. name 供后续口播点名，禁止只用颜色/形状等泛称代替具体对象\n\n"
            "【语言规则】\n"
            "- title、name、description 三个字段必须全部使用简体中文\n"
            "- name 格式示例：'2006年团队之星'、'第三代产品'\n"
            "- description 描述对象的视觉特征，如颜色、形状、文字等\n\n"
            "只输出纯 JSON，不要包含 markdown 代码块标记或其他文本。"
        )
        return system, user

    # ── Agnes multi modal call ───────────────────────────────

    @staticmethod
    def _call_multimodal(
        system: str,
        user_text: str,
        images_b64: list[str],
        *,
        max_tokens: int | None = None,
    ) -> str:
        """调用 Agnes 多模态 LLM，返回响应文本。"""
        settings = get_settings()
        keys = agnes_api_keys(settings)
        if not keys:
            raise RuntimeError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置")

        content: list[dict] = [{"type": "text", "text": user_text}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        limit = (
            settings.agnes_llm_max_tokens if max_tokens is None else max_tokens
        )
        payload: dict = {
            "model": settings.agnes_vl_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": limit,
        }

        url = f"{settings.agnes_api_base_url.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None

        for idx, api_key in enumerate(keys):
            headers = agnes_auth_header(api_key.value)
            timeout = (settings.agnes_http_connect_timeout_sec, settings.agnes_http_submit_read_timeout_sec)
            for attempt in range(settings.agnes_http_max_retries):
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    if resp.status_code in _RETRYABLE_HTTP:
                        wait = min(2**attempt * 2, 60)
                        logger.warning(
                            "agnes multimodal %s %s, retry %s/%s in %ss",
                            resp.status_code, url, attempt + 1, settings.agnes_http_max_retries, wait,
                        )
                        time.sleep(wait)
                        continue
                    if not resp.ok:
                        body: dict | str | None = None
                        try:
                            body = resp.json()
                        except Exception:
                            body = resp.text[:500]
                        raise_if_agnes_quota(status_code=resp.status_code, body=body)
                    resp.raise_for_status()
                    choice = resp.json()["choices"][0]
                    return (choice.get("message", {}).get("content") or "").strip()
                except AgnesQuotaExceeded:
                    raise
                except requests.RequestException as exc:
                    last_exc = exc
                    if is_agnes_quota_exceeded(message=str(exc)):
                        raise AgnesQuotaExceeded(str(exc)) from exc
                    if attempt < settings.agnes_http_max_retries - 1:
                        wait = min(2**attempt * 2, 60)
                        logger.warning("agnes multimodal request error: %s, retry in %ss", exc, wait)
                        time.sleep(wait)
                        continue
                    break
            if idx < len(keys) - 1:
                logger.warning(
                    "agnes multimodal %s key failed, switching to backup",
                    api_key.label,
                )
                continue
            break

        if last_exc:
            raise last_exc
        raise RuntimeError("agnes multimodal request failed after all retries")

    # ── response validation ─────────────────────────────────

    def _validate(self, raw: str) -> str:
        """校验并规范化时间表 JSON。"""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text.rstrip())
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        if not text:
            raise ValueError("Agnes 多模态返回空结果")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agnes 多模态返回无效 JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Agnes 多模态返回非对象 JSON")
        segments = parsed.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError("Agnes 多模态返回缺少 segments 字段")

        video_duration = self._duration
        if video_duration is None:
            coerced = _coerce_optional_float(parsed.get("duration_sec"))
            video_duration = coerced
        if video_duration is not None:
            parsed["duration_sec"] = round(float(video_duration), 1)

        fixed: list[dict] = []
        for i, item in enumerate(segments, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"segments[{i}] 须为对象")
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not name:
                raise ValueError(f"segments[{i}] 缺少 name")
            if not description:
                description = name
            start_sec = _coerce_optional_float(item.get("start_sec"))
            end_sec = _coerce_optional_float(item.get("end_sec"))
            duration_sec = _coerce_optional_float(item.get("duration_sec"))
            if start_sec is None and end_sec is not None and duration_sec and duration_sec > 0:
                start_sec = end_sec - duration_sec
            if end_sec is None and start_sec is not None and duration_sec and duration_sec > 0:
                end_sec = start_sec + duration_sec
            if start_sec is None or end_sec is None:
                raise ValueError(f"segments[{i}] 缺少 start_sec/end_sec")
            if end_sec <= start_sec:
                raise ValueError(
                    f"segments[{i}] end_sec({end_sec}) 须大于 start_sec({start_sec})"
                )
            duration_sec = round(end_sec - start_sec, 1)
            fixed.append(
                {
                    "index": i,
                    "name": name,
                    "description": description,
                    "start_sec": round(start_sec, 1),
                    "end_sec": round(end_sec, 1),
                    "duration_sec": duration_sec,
                }
            )

        fixed.sort(key=lambda s: (s["start_sec"], s["end_sec"]))
        for i, seg in enumerate(fixed, start=1):
            seg["index"] = i

        for i in range(1, len(fixed)):
            prev, cur = fixed[i - 1], fixed[i]
            if cur["start_sec"] < prev["end_sec"] - 0.5:
                logger.warning(
                    "timeline overlap: seg %s ends %.1f, seg %s starts %.1f",
                    prev["index"],
                    prev["end_sec"],
                    cur["index"],
                    cur["start_sec"],
                )
                # 裁掉重叠：后段起点贴齐前段终点
                cur["start_sec"] = prev["end_sec"]
                if cur["end_sec"] <= cur["start_sec"]:
                    cur["end_sec"] = round(cur["start_sec"] + max(0.5, cur["duration_sec"]), 1)
                cur["duration_sec"] = round(cur["end_sec"] - cur["start_sec"], 1)

        if video_duration is not None and fixed:
            if fixed[0]["start_sec"] > 1.0:
                logger.warning(
                    "timeline gap at start: first segment starts at %.1fs",
                    fixed[0]["start_sec"],
                )
            last_end = fixed[-1]["end_sec"]
            if abs(last_end - video_duration) > 2.0:
                logger.warning(
                    "timeline end mismatch: last end %.1fs vs duration %.1fs",
                    last_end,
                    video_duration,
                )
                # 末段贴齐总时长（不缩短到 0）
                fixed[-1]["end_sec"] = round(float(video_duration), 1)
                if fixed[-1]["end_sec"] <= fixed[-1]["start_sec"]:
                    fixed[-1]["end_sec"] = round(fixed[-1]["start_sec"] + 0.5, 1)
                fixed[-1]["duration_sec"] = round(
                    fixed[-1]["end_sec"] - fixed[-1]["start_sec"], 1
                )

        title = str(parsed.get("title") or "").strip() or "素材时间表"
        parsed["title"] = title
        parsed["segments"] = fixed
        return json.dumps(parsed, ensure_ascii=False, indent=2)


def _coerce_optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None
