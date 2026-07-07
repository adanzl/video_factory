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
            '      "name": "对象名称（中文，如：2006年团队之星）",\n'
            '      "description": "简要描述（中文，15-25字，描述外观特征）",\n'
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
            "5. 最后一个 segment 的 end_sec 应接近视频总时长\n\n"
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
        max_tokens: int = 4096,
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

        payload: dict = {
            "model": settings.agnes_vl_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": max_tokens,
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

    @staticmethod
    def _validate(raw: str) -> str:
        """校验响应为合法时间表 JSON 并格式化。"""
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
        if "segments" not in parsed or not isinstance(parsed["segments"], list):
            raise ValueError("Agnes 多模态返回缺少 segments 字段")
        return json.dumps(parsed, ensure_ascii=False, indent=2)
