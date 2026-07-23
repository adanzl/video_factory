"""预览 job 46 第 1 分镜图生视频（基于文生图结果）。

用法（在 backend 目录）:

  python -m scripts.preview_i2v_segment46
  python -m scripts.preview_i2v_segment46 --image tmp/t2i_seg1_<ts>.png
  python -m scripts.preview_i2v_segment46 --width 1280 --height 720

输出: tmp/i2v_seg1_<ts>.mp4
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TMP_DIR = ROOT_DIR / "tmp"

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from app.config import get_settings
from app.services.llm.llm_agnes import agnes_api_keys, agnes_auth_header

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  Motion Prompt — 直接改这里调效果
# ══════════════════════════════════════════════════════════════════════

MOTION_PROMPT = (
    "画面左边是灿灿，右边是昭昭。"
    "0.0-1.5秒灿灿说话，同时右手食指微微向下点动约2厘米后停止；"
    "1.5-2.5秒昭昭说话，同时肩膀轻轻耸起约3厘米后定格。"
    "两人说话后面部表情恢复与静图一致："
    "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；"
    "昭昭撇着嘴角耸肩（无辜状），表情不变。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
)

NEGATIVE_PROMPT = (
    "subtitles, text, words, letters, captions, watermark, overlay, "
    "字幕, 文字, 水印, 弹幕, 对白气泡, "
    "微笑, 大笑, 露齿笑, 开心, 嬉笑, 表情突变, 换脸, 脸部变形, "
    "扭曲, 多手指, "
    "快速推进, 大幅推进, 强烈变焦, 画面放大, 裁切脸部, zoom in, dolly in"
)

DEFAULT_NUM_FRAMES = 81
DEFAULT_FPS = 24
I2V_MODE = "ti2vid"


def _encode_image_data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _request_i2v(api_key: str, base_url: str, payload: dict, *, timeout: int = 300, max_retries: int = 3) -> dict:
    url = f"{base_url.rstrip('/')}/videos"
    headers = agnes_auth_header(api_key, extra={"Connection": "close"})
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = __import__("requests").request("POST", url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in {500, 502, 503, 504}:
                wait = min(2**attempt * 2, 60)
                logger.warning("i2v submit %s, retry %s/%s in %ss", resp.status_code, attempt + 1, max_retries, wait)
                time.sleep(wait)
                continue
            if not resp.ok:
                body = None
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:500]
                raise RuntimeError(f"agnes i2v submit {resp.status_code}: {body}")
            return resp.json()
        except __import__("requests").RequestException as exc:
            last_exc = exc
            wait = min(2**attempt * 2, 60)
            logger.warning("i2v submit error: %s, retry in %ss", exc, wait)
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError("i2v submit failed")


def _poll_i2v(api_key: str, poll_url: str, *, timeout: int = 30, max_attempts: int = 120, interval_sec: float = 5.0) -> dict:
    headers = agnes_auth_header(api_key, extra={"Connection": "close"})
    for attempt in range(max_attempts):
        resp = __import__("requests").request("GET", poll_url, headers=headers, timeout=timeout)
        if resp.status_code in {500, 502, 503, 504}:
            time.sleep(interval_sec)
            continue
        if not resp.ok:
            body = None
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            raise RuntimeError(f"i2v poll {resp.status_code}: {body}")
        data = resp.json()
        status = data.get("status", "")
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"i2v task failed: {data}")
        logger.info("i2v poll attempt %s/%s: status=%s", attempt + 1, max_attempts, status)
        time.sleep(interval_sec)
    raise RuntimeError(f"i2v poll exhausted after {max_attempts} attempts")


def _extract_video_url(data: dict) -> str | None:
    for key in ("video_url", "url"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    output = data.get("output")
    if isinstance(output, dict):
        for key in ("video_url", "url"):
            val = output.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        for key in ("url", "video_url"):
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _find_latest_t2i_image() -> Path | None:
    candidates = sorted(TMP_DIR.glob("t2i_seg1_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="预览 job 46 第 1 分镜图生视频（I2V）")
    parser.add_argument("--image", type=Path, default=None, help="输入图片路径（默认自动找 tmp/ 下最新的 t2i_seg1_*.png）")
    parser.add_argument("--motion", default=MOTION_PROMPT, help="Motion prompt")
    parser.add_argument("--out", type=Path, default=None, help="输出路径（默认 tmp/i2v_seg1_<时间戳>.mp4）")
    parser.add_argument("--frames", type=int, default=DEFAULT_NUM_FRAMES, help=f"生成帧数（默认 {DEFAULT_NUM_FRAMES}）")
    parser.add_argument("--width", type=int, default=1280, help="视频宽度（默认 1280）")
    parser.add_argument("--height", type=int, default=720, help="视频高度（默认 720）")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印 DEBUG 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = get_settings()
    keys = agnes_api_keys()
    if not keys:
        print("❌ 未配置 AGNES_API_KEY", file=sys.stderr)
        return 1

    image_path = args.image or _find_latest_t2i_image()
    if not image_path or not image_path.exists():
        print("❌ 未找到输入图片", file=sys.stderr)
        return 1

    ts = datetime.now().strftime("%m%d_%H%M%S")
    out = args.out or (TMP_DIR / f"i2v_seg1_{ts}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    image_ref = _encode_image_data_uri(image_path)
    logger.info("image: %s (%s bytes, data-uri %s chars)", image_path.name, image_path.stat().st_size, len(image_ref))

    api_key = keys[0]
    base_url = settings.agnes_api_base_url
    poll_root = base_url.rstrip("/")

    payload = {
        "model": settings.agnes_video_model,
        "prompt": args.motion,
        "image": image_ref,
        "mode": I2V_MODE,
        "num_frames": args.frames,
        "frame_rate": DEFAULT_FPS,
        "negative_prompt": NEGATIVE_PROMPT,
        "width": args.width,
        "height": args.height,
    }

    print(f"provider:   agnes_i2v ({api_key.label} key)")
    print(f"size:       {args.width}x{args.height}")
    print(f"base_url:   {base_url}")
    print(f"model:      {settings.agnes_video_model}")
    print(f"image:      {image_path}")
    print(f"frames:     {args.frames} @ {DEFAULT_FPS}fps ≈ {args.frames / DEFAULT_FPS:.1f}s")
    print(f"out:        {out}")
    print(f"motion ({len(args.motion)} chars):")
    print(f"  {args.motion}")
    print()

    t0 = time.time()
    try:
        print("📤 提交 I2V 任务...")
        submit_resp = _request_i2v(api_key.value, base_url, payload)
        task_id = submit_resp.get("id") or submit_resp.get("task_id")
        if not task_id:
            raise RuntimeError(f"submit response missing id: {submit_resp}")
        print(f"   task_id: {task_id}")

        poll_url = f"{poll_root}/videos/{task_id}"
        print(f"⏳ 轮询任务状态 ({poll_url})...")
        completed = _poll_i2v(api_key.value, poll_url, max_attempts=settings.agnes_video_poll_max_attempts, interval_sec=settings.agnes_video_poll_interval_sec)

        video_url = _extract_video_url(completed)
        if not video_url:
            raise RuntimeError(f"poll response missing video_url: {completed}")
        print(f"📥 下载视频 ({video_url[:100]}...)")
        resp = __import__("requests").get(video_url, timeout=settings.agnes_video_download_timeout_sec)
        resp.raise_for_status()
        out.write_bytes(resp.content)

    except Exception as exc:
        elapsed = time.time() - t0
        print(f"❌ FAILED after {elapsed:.1f}s: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    n_bytes = out.stat().st_size
    print(f"✅ OK in {elapsed:.1f}s -> {out} ({n_bytes} bytes)")
    print(f"\n视频路径: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
