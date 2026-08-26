"""Agnes AI 图生视频 ClipProvider（agnes-video-v2.0，Data URI 输入）。"""

from __future__ import annotations

import base64
import logging
import math
import mimetypes
import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from gevent.lock import Semaphore
import requests

from app.config import get_settings
from app.exceptions import JobStageFailureError
from app.services.segment.clip.clip_mgr import ClipProvider, clip_mgr
from app.services.segment.clip.clip_render import fit_video_duration
from app.services.media.ffmpeg_utils import ffmpeg_cmd_start, probe_duration, run_ffmpeg
from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesI2VError,
    AgnesQuotaExceeded,
    agnes_api_base_from_url,
    agnes_api_keys,
    agnes_apply_host_failover,
    agnes_auth_header,
    agnes_quota_exceeded_from_exception,
    raise_if_agnes_quota,
)
from app.utils.job_cancel import job_cancel

logger = logging.getLogger(__name__)

# 含 Cloudflare 源站错误 52x（如 520 unknown error）
_RETRYABLE_HTTP = frozenset({500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527})
# Agnes 视频提交限额：allows 1 requests per 1 minute(s)
_RATE_LIMIT_WAIT_SEC = 60.0
_TASK_RETRY_TOKENS = ("failed", "timeout", "429", "rate limit", "too many")
_TERMINAL_POLL_STATES = frozenset({"completed", "failed"})
_I2V_MODE = "ti2vid"
_DEFAULT_MOTION_PROMPT = (
    "画面元素轻微自然晃动，镜头固定不推近不拉远，面部表情与静图一致"
)
_STABILITY_HINT = "画面稳定，无快速运镜"
_FACE_LOCK_HINT = "面部表情与静图一致，不微笑不大笑，五官服装发型保持不变"
_CAMERA_LOCK_HINT = "镜头固定，不推近不拉远，不放大构图"
# I2V 对前缀更敏感：无字约束前置，避免被长 motion 末尾稀释
_CLEAN_VISUAL_STYLE_HINT = (
    "纯视觉画面，无任何字幕、水印、对话框或文字叠加"
)
_DEFAULT_NEGATIVE_PROMPT = (
    "text overlay, speech bubble, subtitles, captions, on-screen text, "
    "text, words, letters, watermark, overlay, chinese characters on screen, "
    "字幕, 文字, 水印, 弹幕, 对白气泡, 画面文字, 汉字叠加, 台词字幕, "
    "微笑, 大笑, 露齿笑, 开心, 嬉笑, 表情突变, 换脸, 脸部变形, "
    "扭曲, 多手指, "
    "knife, sharp blade, sharp tool, real knife, knife in child's hand, "
    "刀具, 锋利刀具, 儿童持刀, 餐刀, "
    "crowd, duplicate character, cloned person, extra stranger, "
    "路人, 多余路人, 复制人物, 克隆角色, "
    "快速推进, 大幅推进, 强烈变焦, 画面放大, 裁切脸部, zoom in, dolly in"
)
_CAST_LR_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)"
)
_CAST_LCR_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"中间是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"右边是\s*(昭昭|灿灿|妈妈)"
)
_CAST_LTR_RE = re.compile(
    r"(?:画面)?从左到右是\s*(昭昭|灿灿|妈妈)\s*[、,，]\s*"
    r"(昭昭|灿灿|妈妈)\s*[、,，]\s*(昭昭|灿灿|妈妈)"
)
_CAST_ONLY_RE = re.compile(
    r"(?:只能是|有且仅有\d+人[：:])"
    r"((?:昭昭|灿灿|妈妈)(?:、(?:昭昭|灿灿|妈妈))+)"
)
_CAST_SPEAK_RE = re.compile(r"(昭昭|灿灿|妈妈)说话")
# 提交前去掉旧稿里的推近用语，避免 I2V 猛 zoom（勿误伤「不推近」）
_CAMERA_ZOOM_RE = re.compile(
    r"镜头(?:极缓|缓慢|轻轻|轻微|大幅|强烈)?(?:推近|推进|拉远|变焦)"
    r"|(?:极缓|缓慢|轻轻|轻微|大幅|强烈)(?:推近|推进|拉远)"
    r"|放大构图|放大画面"
    r"|slow\s*zoom(?:\s*in)?|zoom\s*in|dolly\s*in",
    re.IGNORECASE,
)
# Agnes 720p 各比例上限均为 409 帧（1080p 仅 169 帧，更长分镜靠 loop + fit 补齐）
_MAX_FRAMES = 409
_MIN_FRAMES = 81
# Agnes API 默认 1152×768 ≈ 884K 像素（720P 级别），超出会 400
_API_TARGET_PIXELS = 921_600  # 1280×720

# ── 口型后校验：按说话窗口抽帧给 VL 判断是否开口 ──────────────────
# 兼容侧边身份（左侧男孩）与旧版角色名（昭昭）；三人含中间
_MOUTH_SPEAK_WINDOW_RE = re.compile(
    r"(?P<start>\d+(?:\.\d+)?)-(?P<end>\d+(?:\.\d+)?)秒"
    r"(?:"
    r"(?P<side>左侧|中间|右侧)(?P<role>男孩|女孩|妈妈)"
    r"|"
    r"(?P<name>昭昭|灿灿|妈妈)"
    r")"
    r"(?:开口说话|张嘴说话|嘴巴持续张合说话)"
)
_NAME_TO_SIDE_HINT = {"昭昭": "左侧", "灿灿": "右侧", "妈妈": "中间"}
# 口型开合有闭合瞬间，单帧易误判，窗口内多点抽帧对比口型变化
_MOUTH_VERIFY_FRACTIONS = (0.15, 0.35, 0.5, 0.65, 0.85)
_MOUTH_VERIFY_FRAME_WIDTH = 640
# 多帧 VL + 强制思考；对齐 image_agnes 图文校验 300s（120s 实测易 Read timed out）
_VL_READ_TIMEOUT_SEC = 300.0
_VL_MAX_ATTEMPTS = 3
# 强制选边比「他有没有说话」的是非题更有区分度（是非题易偏向答是）
_MOUTH_VERIFY_SYSTEM = (
    "你是视频抽帧质检员。用户给出同一段视频某时间段按时间顺序抽取的几帧画面。"
    "判断画面中哪个人物在说话：任一帧张开嘴巴，或各帧间嘴部有明显开合/口型变化，即算在说话。"
    "只回答「左侧」「中间」「右侧」「多人」或「无人」，不要输出任何其他内容。"
)
_SUBTITLE_VERIFY_SYSTEM = (
    "你是视频抽帧质检员。这些图按时间顺序取自同一段图生视频。"
    "判断画面上是否出现烧录字幕、字幕条、汉字、拼音、对白气泡或可读文字。"
    "衣服花纹、食物、家具纹理不算文字。"
    "只回答「有字幕」或「无字幕」。"
)


def _extract_speak_windows(prompt: str) -> list[tuple[float, float, str]]:
    """从注入后的 motion_prompt 提取说话窗口 (start, end, 侧边身份)。"""
    # 站位句优先：名字 → 实际站位侧（三人中间妈妈、二人右灿等）
    name_side: dict[str, str] = {}
    lcr = re.search(
        r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
        r"中间是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
        r"右边是\s*(昭昭|灿灿|妈妈)",
        prompt or "",
    )
    if lcr:
        name_side = {
            lcr.group(1): "左侧",
            lcr.group(2): "中间",
            lcr.group(3): "右侧",
        }
    else:
        lr = re.search(
            r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
            r"右边是\s*(昭昭|灿灿|妈妈)",
            prompt or "",
        )
        if lr:
            name_side = {lr.group(1): "左侧", lr.group(2): "右侧"}

    windows: list[tuple[float, float, str]] = []
    for m in _MOUTH_SPEAK_WINDOW_RE.finditer(prompt or ""):
        start, end = float(m.group("start")), float(m.group("end"))
        if end <= start:
            continue
        if m.group("side"):
            label = f"{m.group('side')}{m.group('role')}"
        else:
            name = m.group("name")
            side = name_side.get(name) or _NAME_TO_SIDE_HINT.get(name, "左侧")
            role = {"昭昭": "男孩", "灿灿": "女孩", "妈妈": "妈妈"}.get(name, name)
            label = f"{side}{role}"
        windows.append((start, end, label))
    return windows


def _frame_data_uri(video_path: Path, at_sec: float, tmp_path: Path) -> str | None:
    """抽单帧缩放到 640 宽，返回 JPEG Data URI；失败返回 None。"""
    try:
        run_ffmpeg([
            *ffmpeg_cmd_start(hide_banner=True, hwaccel=False),
            "-ss",
            f"{max(0.0, at_sec):.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={_MOUTH_VERIFY_FRAME_WIDTH}:-2",
            "-q:v",
            "5",
            str(tmp_path),
        ])
        if not tmp_path.is_file():
            return None
        data = base64.b64encode(tmp_path.read_bytes()).decode("ascii")
        return f"data:image/jpeg;base64,{data}"
    except Exception as exc:
        logger.warning("mouth verify frame extract failed at %.2fs: %s", at_sec, exc)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def _sample_window_frames(
    video_path: Path,
    start: float,
    end: float,
    duration: float,
    work_dir: Path,
    segment_index: int,
    window_index: int,
) -> list[str]:
    """按口型校验同一套比例点抽帧。"""
    span = max(end - start, 0.0)
    frames: list[str] = []
    for fraction in _MOUTH_VERIFY_FRACTIONS:
        t = start + span * fraction if span > 0 else start
        if duration > 0:
            t = min(t, max(0.0, duration - 0.05))
        uri = _frame_data_uri(
            video_path,
            t,
            work_dir
            / f"{segment_index}.mouth_{window_index}_{int(fraction * 100)}.jpg",
        )
        if uri:
            frames.append(uri)
    return frames


def _sample_verify_windows(
    video_path: Path,
    prompt: str,
    *,
    work_dir: Path,
    segment_index: int,
) -> list[tuple[float, float, str, list[str]]]:
    """口型/字幕共用抽帧：有说话窗按窗抽，否则按全片同一套比例点。"""
    duration = probe_duration(video_path)
    windows = _extract_speak_windows(prompt)
    if not windows:
        frames = _sample_window_frames(
            video_path, 0.0, max(duration, 0.0), duration,
            work_dir, segment_index, 0,
        )
        return [(0.0, max(duration, 0.0), "", frames)] if frames else []
    sampled: list[tuple[float, float, str, list[str]]] = []
    for w_idx, (start, end, label) in enumerate(windows):
        frames = _sample_window_frames(
            video_path, start, end, duration,
            work_dir, segment_index, w_idx,
        )
        sampled.append((start, end, label, frames))
    return sampled


def _parse_speaking_sides(content: str) -> set[str] | None:
    """解析 VL 选边回答 → 在说话的侧集合；无法解析返回 None。"""
    text = (content or "").strip().strip("。．.")
    if not text:
        return None
    if "无人" in text or "都没" in text or "没有" in text:
        return set()
    found: set[str] = set()
    if "左侧" in text or text.startswith("左"):
        found.add("左侧")
    if "中间" in text or text.startswith("中"):
        found.add("中间")
    if "右侧" in text or text.startswith("右"):
        found.add("右侧")
    if "多人" in text or "两者" in text or "都在" in text:
        # 旧回答「两者」按左+右；含中间时由字面命中补齐
        if not found:
            found.update({"左侧", "右侧"})
    return found or None


def _parse_subtitle_hit(content: str) -> bool | None:
    """True=有字幕，False=无字幕，None=无法解析。"""
    text = (content or "").strip().strip("。．.！! ")
    if not text:
        return None
    if "无字幕" in text or "没有字幕" in text or "未见字幕" in text:
        return False
    if "有字幕" in text:
        return True
    if text in {"无", "没有", "否"}:
        return False
    if text in {"有", "是"}:
        return True
    return None


def _resolve_api_dimensions(target_w: int, target_h: int) -> tuple[int, int]:
    """将目标画布尺寸缩放到 Agnes API 支持的 ~720P 总像素范围内，保持比例。"""
    scale = min(1.0, math.sqrt(_API_TARGET_PIXELS / (target_w * target_h)))
    api_w = int(target_w * scale) // 2 * 2  # 保证偶数
    api_h = int(target_h * scale) // 2 * 2
    return max(api_w, 2), max(api_h, 2)


def _backoff_seconds(attempt: int, *, is_timeout: bool = False) -> float:
    if is_timeout:
        return min(45.0 + attempt * 30.0, 180.0)
    return min(2**attempt * 2, 60.0)


def _rate_limit_wait_seconds(attempt: int) -> float:
    """提交 429：按 1 RPM 等满一分钟，后续加倍，上限 3 分钟。"""
    return min(_RATE_LIMIT_WAIT_SEC * (attempt + 1), 180.0)


def _inject_mouth_motion(prompt: str, subtitle_cues: list[tuple[str, float]]) -> str:
    """如有对话，在 motion_prompt 前注入开口说话动作。

    从 subtitle_cues 提取发言角色及累计时长，为每位 speaker 生成
    嘴巴张合动作描述（部位+幅度+次数+时长），避免 I2V 模型自由发挥。
    """
    if not subtitle_cues:
        return prompt
    speaker_sec: dict[str, float] = {}
    prev_end = 0.0
    for speaker, end_sec in subtitle_cues:
        name = str(speaker or "").strip()
        if not name:
            prev_end = end_sec
            continue
        dur = max(0.0, end_sec - prev_end)
        speaker_sec[name] = speaker_sec.get(name, 0.0) + dur
        prev_end = end_sec
    if not speaker_sec:
        return prompt
    parts: list[str] = []
    for name, total_sec in speaker_sec.items():
        n = max(2, int(total_sec * 3))
        dur = min(total_sec, 2.0)
        parts.append(
            f"{name}嘴巴快速张合约3毫米{n}次持续{dur:.1f}秒后闭合"
        )
    if not parts:
        return prompt
    mouth = "；".join(parts) + "。"
    return mouth + prompt


def _unique_cast_names(*names: str | None) -> list[str]:
    ordered: list[str] = []
    for name in names:
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _cast_names_from_text(text: str) -> list[str]:
    """从构图/站位/人数锁收集角色；不扫外貌小传，避免两人镜误吞妈妈。"""
    text = text or ""
    ltr = _CAST_LTR_RE.search(text)
    if ltr:
        return _unique_cast_names(*ltr.groups())
    lcr = _CAST_LCR_RE.search(text)
    if lcr:
        return _unique_cast_names(*lcr.groups())
    only = _CAST_ONLY_RE.search(text)
    if only:
        locked = _unique_cast_names(*only.group(1).split("、"))
        if len(locked) >= 3:
            return locked
    ordered: list[str] = []

    def _add(name: str | None) -> None:
        if name and name not in ordered:
            ordered.append(name)

    lr = _CAST_LR_RE.search(text)
    if lr:
        _add(lr.group(1))
        _add(lr.group(2))
    if "妈妈在中间" in text:
        if len(ordered) == 2 and "妈妈" not in ordered:
            ordered = [ordered[0], "妈妈", ordered[1]]
        else:
            _add("妈妈")
    mid = re.search(r"中间是\s*(昭昭|灿灿|妈妈)", text)
    if mid:
        name = mid.group(1)
        if len(ordered) == 2 and name not in ordered:
            ordered = [ordered[0], name, ordered[1]]
        else:
            _add(name)
    for sm in _CAST_SPEAK_RE.finditer(text):
        _add(sm.group(1))
    if only:
        for name in only.group(1).split("、"):
            _add(name)
    return ordered


def _cast_names_from_speakers(speakers: list[str] | None) -> list[str]:
    allowed = {str(s).strip() for s in (speakers or []) if str(s).strip()}
    return [n for n in ("昭昭", "灿灿", "妈妈") if n in allowed]


def _cast_names_from_motion(
    text: str,
    image_prompt: str | None = None,
    speakers: list[str] | None = None,
) -> list[str]:
    """谁在场看 speakers；左右中顺序看构图/站位，避免把灿灿锁到妈妈的位置。"""
    speaker_names = _cast_names_from_speakers(speakers)
    motion_names = _cast_names_from_text(text)
    image_names = _cast_names_from_text(image_prompt or "")
    layout = None
    if len(motion_names) >= 3:
        layout = motion_names
    elif len(image_names) >= 3:
        layout = image_names

    if "妈妈" in speaker_names:
        if layout and "妈妈" in layout:
            ordered = list(layout)
            for name in speaker_names:
                if name not in ordered:
                    ordered.append(name)
            return ordered
        pair = motion_names if len(motion_names) == 2 else image_names
        if len(pair) == 2 and "妈妈" not in pair:
            return [pair[0], "妈妈", pair[1]]
        if set(speaker_names) >= {"昭昭", "灿灿", "妈妈"}:
            return ["昭昭", "妈妈", "灿灿"]
        return speaker_names

    if layout:
        return layout
    return motion_names or image_names or speaker_names


def _has_clean_visual_hint(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "纯视觉",
            "无字幕",
            "无文字",
            "无对话框",
            "文字叠加",
            "无任何文字",
        )
    )


def _has_clean_visual_prefix(text: str) -> bool:
    """无字约束须在 prompt 最前；仅尾部写「无字幕」不算。"""
    head = (text or "").strip()[:24]
    return head.startswith("纯视觉") or head.startswith("禁止画面出现任何字幕")


def _cast_lock_hint(
    text: str,
    image_prompt: str | None = None,
    speakers: list[str] | None = None,
) -> str | None:
    """按本段入画角色锁定。E 有妈妈同框时按从左到右枚举；无妈妈才强调无第三人。"""
    names = _cast_names_from_motion(text, image_prompt, speakers)
    if not names:
        return None
    cast = "、".join(names)
    n = len(names)
    layout = f"从左到右是{cast}" if n >= 3 else cast
    parts = [
        f"{n}人同框全程可见，{layout}，人数与静图完全一致",
        f"{n}人全部在场、位置固定、不被裁切",
    ]
    if "妈妈" not in names:
        parts.append("仅上述角色入画，无路人无额外人物")
    return "，".join(parts)


def _negative_prompt_for_motion(text: str) -> str:
    """按出场动态补 negative：无妈妈时才禁第三人/成年男，避免误伤有妈妈镜头。"""
    names = _cast_names_from_motion(text)
    extra: list[str] = []
    if names and "妈妈" not in names:
        extra.append(
            "third person, extra person, adult man, adult woman, "
            "第三人, 成年男性, 成年女人, 多余男人, 多余小孩, 第三个小孩, "
            "妈妈, 沙发后男人, man behind sofa"
        )
    if not extra:
        return _DEFAULT_NEGATIVE_PROMPT
    return f"{_DEFAULT_NEGATIVE_PROMPT}, {', '.join(extra)}"


def _stabilize_motion_prompt(
    prompt: str,
    image_prompt: str | None = None,
    speakers: list[str] | None = None,
) -> str:
    """补齐 I2V 稳定性与面部锁定，并压掉推近/变焦（易裁脸）。"""
    text = prompt.strip() or _DEFAULT_MOTION_PROMPT
    text = _CAMERA_ZOOM_RE.sub("", text)
    text = re.sub(r"[，,]{2,}", "，", text).strip("，, ").strip()
    if not text:
        text = _DEFAULT_MOTION_PROMPT
    extras: list[str] = []
    if _STABILITY_HINT not in text and not any(
        word in text for word in ("稳定", "平滑", "无抖动", "镜头固定")
    ):
        extras.append(_STABILITY_HINT)
    if not any(
        word in text
        for word in ("面部", "表情", "静图一致", "不微笑", "五官", "脸")
    ):
        extras.append(_FACE_LOCK_HINT)
    if not any(
        word in text for word in ("镜头固定", "不推近", "不拉远", "不放大")
    ):
        extras.append(_CAMERA_LOCK_HINT)
    cast_hint = _cast_lock_hint(text, image_prompt, speakers)
    chunks: list[str] = []
    if not _has_clean_visual_prefix(text):
        chunks.append(_CLEAN_VISUAL_STYLE_HINT)
    # 人数锁定紧跟无字 Style：I2V 对前缀更敏感
    if (
        cast_hint
        and "人数与静图" not in text
        and "只能是" not in text
        and "有且仅有" not in text
    ):
        chunks.extend([cast_hint, text])
    else:
        chunks.append(text)
    chunks.extend(extras)
    return "，".join(chunks) if len(chunks) > 1 else chunks[0]


def _pick_num_frames(target_sec: float, frame_rate: int) -> int:
    need = max(_MIN_FRAMES, int(math.ceil(target_sec * frame_rate)))
    return min(_MAX_FRAMES, 8 * math.ceil((need - 1) / 8) + 1)


def _encode_image_data_uri(path: Path) -> str:
    """本地分镜图 → Data URI Base64（与 agnes-image-2.1-flash 文档一致）。"""
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _read_agnes_source_url(image_path: Path) -> str | None:
    """文生图若由 Agnes 返回 CDN URL，侧车文件可直接供图生视频引用。"""
    sidecar = image_path.with_name(image_path.name + ".agnes_source_url")
    if not sidecar.is_file():
        return None
    url = sidecar.read_text(encoding="utf-8").strip()
    if url.startswith(("http://", "https://")):
        return url
    return None


def _resolve_i2v_image(image_path: Path) -> str:
    source_url = _read_agnes_source_url(image_path)
    if source_url:
        logger.info("agnes i2v image: using Agnes CDN URL from sidecar (%s)", source_url[:80])
        return source_url
    logger.info(
        "agnes i2v image: using Data URI (%s, %s bytes)",
        image_path.name,
        image_path.stat().st_size,
    )
    return _encode_image_data_uri(image_path)


def _format_image_ref_for_log(image_ref: str) -> str:
    if image_ref.startswith("http"):
        return image_ref[:96]
    return f"data-uri({len(image_ref)} chars)"


def _strip_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_submit_ids(
    *,
    video_id: str | None,
    task_id: str | None,
) -> tuple[str | None, str | None]:
    """纠正 submit 响应里被回填成 task id 的 video_id。

    Agnes 异步排队时常返回 video_id=task_xxx（与 id/task_id 相同），
    这不是可走 agnes-api?video_id= 的真实 video id，应归入 task_id，
    走 /videos/{task_id} 轮询。
    """
    if video_id and video_id.startswith("task_"):
        return None, task_id or video_id
    if video_id and task_id and video_id == task_id:
        return None, task_id
    return video_id, task_id


def _response_body(resp: requests.Response) -> dict | str | None:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def _raise_i2v_api_error(phase: str, err: object, *, body: dict | None = None) -> None:
    raise_if_agnes_quota(body=body, message=str(err))
    if isinstance(err, dict):
        raise AgnesI2VError(
            f"agnes i2v {phase} error: {err.get('code')} - {err.get('message')}"
        )
    raise AgnesI2VError(f"agnes i2v {phase} error: {err}")


def _is_retriable_task_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _TASK_RETRY_TOKENS)


def _agnes_api_root(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned[:-3]
    return cleaned.rsplit("/", 1)[0]


def _loop_video_to_duration(
    raw_path: Path,
    *,
    work_dir: Path,
    segment_index: int,
    total_duration: float,
) -> Path:
    raw_dur = probe_duration(raw_path)
    if raw_dur <= 0 or total_duration <= raw_dur * 1.15:
        return raw_path
    loop = math.ceil(total_duration / raw_dur) - 1
    looped = work_dir / f"{segment_index}.agnes_loop.mp4"
    run_ffmpeg([
        *ffmpeg_cmd_start(hwaccel=False),
        "-stream_loop",
        str(loop),
        "-i",
        str(raw_path),
        "-c",
        "copy",
        "-y",
        str(looped),
    ])
    return looped


class AgnesClipProvider(ClipProvider):
    # 按 Key 池分别限流：付费(enterprise≈2 RPM)与免费(≈1 RPM)互不影响
    _submit_lock = Semaphore(value=1)
    _last_submit_at_by_key: dict[str, float] = {}
    # 状态查询全局错峰，避免多路并发把 poll RPM 打爆
    _poll_lock = Semaphore(value=1)
    _last_poll_at = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        base = settings.agnes_api_base_url.rstrip("/")
        self._create_url = f"{base}/videos"
        self._poll_root = _agnes_api_root(base)
        self._model = settings.agnes_video_model
        self._frame_rate = settings.clip_fps
        self._submit_interval = settings.agnes_submit_interval_sec
        self._free_submit_interval = settings.agnes_free_submit_interval_sec
        self._http_max_retries = settings.agnes_http_max_retries
        self._connect_timeout = settings.agnes_http_connect_timeout_sec
        self._submit_read_timeout = settings.agnes_http_submit_read_timeout_sec
        self._poll_read_timeout = settings.agnes_http_poll_read_timeout_sec
        self._download_timeout = settings.agnes_video_download_timeout_sec
        self._task_max_retries = settings.agnes_video_task_max_retries
        self._submit_max_retries = settings.agnes_video_submit_max_retries
        self._poll_max_attempts = settings.agnes_video_poll_max_attempts
        self._poll_interval_sec = settings.agnes_video_poll_interval_sec
        self._active_job_id: int | None = None

    def _sync_endpoints_from_api_url(self, api_url: str) -> None:
        """备用域名切换后同步 videos 提交与 poll 根路径。"""
        base = agnes_api_base_from_url(api_url)
        if not base:
            return
        self._create_url = f"{base}/videos"
        self._poll_root = _agnes_api_root(base)

    def _raise_if_job_cancelled(self) -> None:
        if self._active_job_id is not None:
            job_cancel.raise_if_cancelled(self._active_job_id)

    def _submit_interval_for_key(self, key_label: str) -> float:
        """Agnes 视频提交间隔：接口现为 1 RPM，付费/免费默认都按 60s（可配）。"""
        if key_label == "free":
            return max(0.0, self._free_submit_interval)
        return max(0.0, self._submit_interval)

    def _throttle_submit(self, key_label: str = "primary") -> None:
        self._raise_if_job_cancelled()
        interval = self._submit_interval_for_key(key_label)
        with self._submit_lock:
            last = self._last_submit_at_by_key.get(key_label, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < interval:
                wait = interval - elapsed
                logger.info(
                    "agnes i2v throttle (%s key): wait %.1fs (interval=%.1fs)",
                    key_label,
                    wait,
                    interval,
                )
                time.sleep(wait)
                self._raise_if_job_cancelled()
            self._last_submit_at_by_key[key_label] = time.monotonic()

    def _throttle_poll(self) -> None:
        """多路 i2v 共用同一状态查询节奏，避免 status query 429。"""
        self._raise_if_job_cancelled()
        interval = max(0.0, self._poll_interval_sec)
        with self._poll_lock:
            elapsed = time.monotonic() - self._last_poll_at
            if elapsed < interval:
                wait = interval - elapsed
                logger.debug(
                    "agnes i2v poll throttle: wait %.1fs (interval=%.1fs)",
                    wait,
                    interval,
                )
                time.sleep(wait)
                self._raise_if_job_cancelled()
            AgnesClipProvider._last_poll_at = time.monotonic()

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        max_retries: int | None = None,
        timeout: float | tuple[float, float] | None = None,
        label: str = "request",
    ) -> requests.Response:
        retries = self._submit_max_retries if label == "submit" and max_retries is None else (
            max_retries if max_retries is not None else self._http_max_retries
        )
        read_timeout = self._submit_read_timeout if label == "submit" else self._poll_read_timeout
        req_timeout = timeout if timeout is not None else (self._connect_timeout, read_timeout)
        last_exc: Exception | None = None
        host_failover_tried: set[str] = {url}

        for attempt in range(retries):
            try:
                resp = requests.request(
                    method, url, headers=headers or {}, json=json, timeout=req_timeout
                )
                if resp.status_code == 503:
                    alt = agnes_apply_host_failover(
                        url,
                        host_failover_tried,
                        reason="503",
                        tag=f"i2v {label}",
                        on_switch=self._sync_endpoints_from_api_url,
                    )
                    if alt:
                        url = alt
                        continue
                if resp.status_code in _RETRYABLE_HTTP:
                    wait = _backoff_seconds(attempt)
                    logger.warning(
                        "agnes %s %s %s, retry %s/%s in %ss",
                        label,
                        resp.status_code,
                        url,
                        attempt + 1,
                        retries,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                if resp.status_code == 429:
                    body = _response_body(resp)
                    # 提交 RPM 限流：等满窗口再试；轮询 429 仍抛给 poll 循环退避
                    if label == "submit" and attempt + 1 < retries:
                        wait = _rate_limit_wait_seconds(attempt)
                        logger.warning(
                            "agnes %s %s rate limited, retry %s/%s in %ss",
                            label,
                            url,
                            attempt + 1,
                            retries,
                            wait,
                        )
                        time.sleep(wait)
                        continue
                    raise_if_agnes_quota(status_code=resp.status_code, body=body)
                if not resp.ok:
                    raise_if_agnes_quota(
                        status_code=resp.status_code,
                        body=_response_body(resp),
                    )
                resp.raise_for_status()
                return resp
            except AgnesQuotaExceeded:
                raise
            except requests.Timeout as exc:
                last_exc = exc
                alt = agnes_apply_host_failover(
                    url,
                    host_failover_tried,
                    reason="timeout",
                    tag=f"i2v {label}",
                    on_switch=self._sync_endpoints_from_api_url,
                )
                if alt:
                    url = alt
                    continue
                wait = _backoff_seconds(attempt, is_timeout=True)
                hint = "（异步 API 提交应秒级返回 video_id）" if label == "submit" else ""
                logger.warning(
                    "agnes %s %s %s read timeout%s: %s, retry %s/%s in %ss",
                    label,
                    method,
                    url,
                    hint,
                    exc,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
            except requests.RequestException as exc:
                last_exc = exc
                if agnes_quota_exceeded_from_exception(exc):
                    raise AgnesQuotaExceeded(str(exc)) from exc
                wait = _backoff_seconds(attempt)
                detail = ""
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    try:
                        detail = f" body={exc.response.text[:500]}"
                    except Exception:
                        detail = " body=<unreadable>"
                logger.warning(
                    "agnes %s %s %s error: %s%s, retry %s/%s in %ss",
                    label,
                    method,
                    url,
                    exc,
                    detail,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)

        if last_exc:
            if isinstance(last_exc, JobStageFailureError):
                raise last_exc
            raise AgnesI2VError(str(last_exc)) from last_exc
        raise AgnesI2VError(f"agnes request failed after {retries} retries: {url}")

    @staticmethod
    def _extract_video_url(body: dict) -> str | None:
        for key in ("remixed_from_video_id", "video_url", "url"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # completed 返回体有时把地址嵌在 output/metadata 里（如 metadata.url）
        for nested_key in ("output", "metadata"):
            nested = body.get(nested_key)
            if not isinstance(nested, dict):
                continue
            for key in ("video_url", "url"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _build_i2v_payload(
        self, *, prompt: str, image_ref: str, num_frames: int,
        width: int | None = None, height: int | None = None,
    ) -> dict:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "image": image_ref,
            "mode": _I2V_MODE,
            "num_frames": num_frames,
            "frame_rate": self._frame_rate,
            "negative_prompt": _negative_prompt_for_motion(prompt),
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        return payload

    def _with_api_key_fallback(self, operation: Callable[[AgnesApiKey], Path]) -> Path:
        keys = agnes_api_keys()
        if not keys:
            raise AgnesI2VError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置，无法调用 Agnes 图生视频")

        last_exc: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                return operation(key)
            except AgnesQuotaExceeded as exc:
                last_exc = exc
            except RuntimeError as exc:
                if not agnes_quota_exceeded_from_exception(exc):
                    raise
                last_exc = exc

            if idx >= len(keys) - 1:
                assert last_exc is not None
                raise last_exc
            logger.warning(
                "agnes %s key quota/rate limit exceeded, switching to backup",
                key.label,
            )

        raise AgnesI2VError("agnes i2v failed without exception")

    def _generate_raw_with_key(
        self,
        api_key: AgnesApiKey,
        image_path: Path,
        prompt: str,
        output_path: Path,
        *,
        num_frames: int,
        width: int | None = None,
        height: int | None = None,
        segment_index: int | None = None,
    ) -> Path:
        image_ref = _resolve_i2v_image(image_path)
        headers = agnes_auth_header(api_key.value, extra={"Connection": "close"})
        payload = self._build_i2v_payload(
            prompt=prompt,
            image_ref=image_ref,
            num_frames=num_frames,
            width=width,
            height=height,
        )
        logger.info(
            "agnes i2v submit (%s key): model=%s frames=%s fps=%s size=%sx%s image=%s prompt_chars=%s",
            api_key.label,
            self._model,
            num_frames,
            self._frame_rate,
            width or "-",
            height or "-",
            _format_image_ref_for_log(image_ref),
            len(prompt),
        )

        self._throttle_submit(api_key.label)
        max_attempts = max(1, self._task_max_retries)
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return self._submit_and_poll(
                    headers=headers,
                    payload=payload,
                    output_path=output_path,
                    segment_index=segment_index,
                )
            except AgnesQuotaExceeded:
                raise
            except RuntimeError as exc:
                last_exc = exc
                msg = str(exc)
                if agnes_quota_exceeded_from_exception(exc):
                    raise AgnesQuotaExceeded(msg) from exc
                if attempt >= max_attempts - 1 or not _is_retriable_task_error(msg):
                    raise
                wait = 10 * (attempt + 1)
                logger.warning(
                    "agnes i2v attempt %s/%s failed, retry in %ss: %s",
                    attempt + 1,
                    max_attempts,
                    wait,
                    msg[:200],
                )
                time.sleep(wait)

        if last_exc:
            raise last_exc
        raise AgnesI2VError("agnes i2v failed without exception")

    def _generate_raw(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        *,
        num_frames: int,
        width: int | None = None,
        height: int | None = None,
        segment_index: int | None = None,
    ) -> Path:
        return self._with_api_key_fallback(
            lambda key: self._generate_raw_with_key(
                key,
                image_path,
                prompt,
                output_path,
                num_frames=num_frames,
                width=width,
                height=height,
                segment_index=segment_index,
            )
        )

    def _submit_task(
        self,
        *,
        headers: dict,
        payload: dict,
    ) -> tuple[str | None, str | None, str, dict]:
        resp = self._request(
            "POST", self._create_url, headers=headers, json=payload, label="submit"
        )
        body = resp.json()
        if body.get("error"):
            _raise_i2v_api_error("submit", body["error"], body=body)

        video_id, task_id = _normalize_submit_ids(
            video_id=_strip_optional_str(body.get("video_id")),
            task_id=_strip_optional_str(body.get("task_id") or body.get("id")),
        )
        if not video_id and not task_id:
            raise AgnesI2VError(f"agnes i2v submit missing task id: {body}")

        state = str(body.get("status") or "queued")
        # 日志约定：video_id=Agnes 侧 id，task_id=本地 DB 主键
        agnes_id = video_id or task_id
        logger.info(
            "agnes i2v task queued (async): video_id=%s task_id=%s status=%s",
            agnes_id or "-",
            self._active_job_id if self._active_job_id is not None else "-",
            state,
        )
        return video_id, task_id, state, body

    def _poll_url(self, video_id: str | None, task_id: str | None) -> str:
        # 有 Agnes task id 时优先走 /videos/{id}；agnes-api 仅用于真实 video_id
        if task_id:
            return f"{self._create_url}/{task_id}"
        if video_id:
            # cSpell: disable-next-line
            return f"{self._poll_root}/agnesapi?{urlencode({'video_id': video_id})}"
        raise AgnesI2VError("agnes poll missing both video_id and task_id")

    def _download_video(self, poll: dict, output_path: Path, task_label: str) -> Path:
        video_url = self._extract_video_url(poll)
        if not video_url:
            logger.error(
                "agnes i2v task %s completed but missing video url, body=%s",
                task_label,
                repr(poll)[:800],
            )
            raise AgnesI2VError(f"agnes i2v task {task_label} completed but missing video url")
        video = requests.get(
            video_url,
            timeout=(self._connect_timeout, self._download_timeout),
        )
        video.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video.content)
        return output_path

    def _poll_task(
        self,
        *,
        headers: dict,
        video_id: str | None,
        task_id: str | None,
        output_path: Path,
        segment_index: int | None = None,
    ) -> Path:
        agnes_id = video_id or task_id or "unknown"
        state = "queued"
        for poll_idx in range(self._poll_max_attempts):
            self._raise_if_job_cancelled()
            self._throttle_poll()
            try:
                poll_resp = self._request(
                    "GET",
                    self._poll_url(video_id, task_id),
                    headers={**headers, "Connection": "close"},
                    label="poll",
                )
                poll = poll_resp.json()
                if poll.get("error"):
                    _raise_i2v_api_error("poll", poll["error"], body=poll)
            except AgnesQuotaExceeded as exc:
                # 状态查询限流：退避后继续轮询，不要切 key / 整批失败
                wait = max(self._poll_interval_sec, 15.0) * (1 + poll_idx % 3)
                logger.warning(
                    "agnes i2v poll rate-limited (%s), retry in %.0fs: %s",
                    agnes_id,
                    wait,
                    str(exc)[:160],
                )
                time.sleep(wait)
                continue

            self._raise_if_job_cancelled()
            state = str(poll.get("status") or "unknown")
            if poll_idx % 4 == 0 and state not in _TERMINAL_POLL_STATES:
                logger.info(
                    "agnes i2v polling... seg=%s task_id=%s video_id=%s state=%s "
                    "(~%ss)",
                    segment_index if segment_index is not None else "?",
                    self._active_job_id if self._active_job_id is not None else "?",
                    agnes_id,
                    state,
                    int((poll_idx + 1) * self._poll_interval_sec),
                )
            if state == "completed":
                return self._download_video(poll, output_path, agnes_id)
            if state == "failed":
                err = poll.get("error")
                detail = err if isinstance(err, str) else repr(err)
                raise AgnesI2VError(f"agnes i2v task {agnes_id} failed: {detail}")

        raise AgnesI2VError(f"agnes i2v task {agnes_id} timeout, last state={state}")

    def _ask_vl_content(
        self,
        *,
        system: str,
        question: str,
        frames: list[str],
        tag: str,
    ) -> str | None:
        """抽帧问 VL，返回回复正文；调用失败返回 None。"""
        settings = get_settings()
        keys = agnes_api_keys()
        if not keys:
            return None
        url = f"{settings.agnes_api_base_url.rstrip('/')}/chat/completions"
        host_failover_tried: set[str] = {url}
        content: list[dict] = [{"type": "text", "text": question}]
        content.extend(
            {"type": "image_url", "image_url": {"url": uri}} for uri in frames
        )
        payload = {
            "model": settings.agnes_vl_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            # agnes-2.0-flash 强制思考且无法关闭，预算须容纳思考过程，
            # 否则 content 恒为空（finish_reason=length）
            "max_tokens": 16384,
        }
        for api_key in keys:
            for attempt in range(_VL_MAX_ATTEMPTS):
                try:
                    resp = requests.post(
                        url,
                        headers=agnes_auth_header(api_key.value),
                        json=payload,
                        timeout=(self._connect_timeout, _VL_READ_TIMEOUT_SEC),
                    )
                    if resp.status_code == 503:
                        alt = agnes_apply_host_failover(
                            url,
                            host_failover_tried,
                            reason="503",
                            tag=tag,
                        )
                        if alt:
                            url = alt
                            continue
                    if not resp.ok:
                        if resp.status_code in _RETRYABLE_HTTP and attempt + 1 < _VL_MAX_ATTEMPTS:
                            wait = _backoff_seconds(attempt)
                            logger.warning(
                                "%s http %s (%s key), retry %s/%s in %ss",
                                tag,
                                resp.status_code,
                                api_key.label,
                                attempt + 1,
                                _VL_MAX_ATTEMPTS,
                                wait,
                            )
                            time.sleep(wait)
                            continue
                        logger.warning(
                            "%s http %s (%s key)",
                            tag,
                            resp.status_code,
                            api_key.label,
                        )
                        break
                    msg = (
                        resp.json().get("choices", [{}])[0].get("message", {})
                    )
                    reply = (msg.get("content") or "").strip()
                    if not reply:
                        reasoning = (msg.get("reasoning_content") or "").strip()
                        if len(reasoning) <= 20:
                            reply = reasoning
                    return reply or None
                except requests.Timeout as exc:
                    alt = agnes_apply_host_failover(
                        url,
                        host_failover_tried,
                        reason="timeout",
                        tag=tag,
                    )
                    if alt:
                        url = alt
                        continue
                    wait = _backoff_seconds(attempt)
                    if attempt + 1 < _VL_MAX_ATTEMPTS:
                        logger.warning(
                            "%s timeout (%s key), retry %s/%s "
                            "in %ss (read=%ss): %s",
                            tag,
                            api_key.label,
                            attempt + 1,
                            _VL_MAX_ATTEMPTS,
                            wait,
                            int(_VL_READ_TIMEOUT_SEC),
                            exc,
                        )
                        time.sleep(wait)
                        continue
                    logger.warning(
                        "%s timeout exhausted (%s key, "
                        "read=%ss, attempts=%s): %s",
                        tag,
                        api_key.label,
                        int(_VL_READ_TIMEOUT_SEC),
                        _VL_MAX_ATTEMPTS,
                        exc,
                    )
                except Exception as exc:
                    logger.warning(
                        "%s call failed (%s key): %s",
                        tag,
                        api_key.label,
                        exc,
                    )
                    break
        return None

    def _ask_vl_speaking_sides(
        self, question: str, frames: list[str]
    ) -> set[str] | None:
        """单次 VL 判定哪侧人物在说话；调用/解析失败返回 None（放行，避免误杀）。"""
        reply = self._ask_vl_content(
            system=_MOUTH_VERIFY_SYSTEM,
            question=question,
            frames=frames,
            tag="mouth verify vl",
        )
        if reply is None:
            return None
        sides = _parse_speaking_sides(reply)
        if sides is None:
            logger.warning("mouth verify vl reply unparsable: %s", str(reply)[:80])
        return sides

    def _verify_mouth_motion(
        self,
        sampled: list[tuple[float, float, str, list[str]]],
        *,
        segment_index: int,
    ) -> bool:
        """用已抽帧问 VL 说话人是否开口；全窗口通过返回 True。"""
        for start, end, label, frames in sampled:
            if not label or not frames:
                continue
            question = (
                f"这{len(frames)}张图按时间顺序取自同一段视频 "
                f"{start:.1f}-{end:.1f} 秒。对比各帧，画面中谁有张嘴说话迹象？"
                f"回答「左侧」「中间」「右侧」「多人」或「无人」。"
            )
            sides = self._ask_vl_speaking_sides(question, frames)
            expected_side = label[:2]
            ok = sides is None or expected_side in sides
            logger.info(
                "clip %s mouth verify %.1f-%.1fs expect=%s vl=%s: %s",
                segment_index,
                start,
                end,
                label,
                "/".join(sorted(sides)) if sides else ("?" if sides is None else "无人"),
                "ok" if ok else "SPEAKER MOUTH NOT MOVING",
            )
            if not ok:
                return False
        return True

    def _verify_no_burned_subtitles(
        self,
        frames: list[str],
        *,
        segment_index: int,
    ) -> bool:
        """用口型同一批帧问 VL 是否烧了字幕。有字幕返回 False；无帧/VL 失败放行。"""
        if not frames:
            logger.warning("clip %s subtitle verify: no frames, skip", segment_index)
            return True
        question = (
            f"这{len(frames)}张图按时间顺序取自同一段视频。"
            "画面上有没有烧录字幕、汉字、拼音或对白条？"
            "回答「有字幕」或「无字幕」。"
        )
        reply = self._ask_vl_content(
            system=_SUBTITLE_VERIFY_SYSTEM,
            question=question,
            frames=frames,
            tag="subtitle verify vl",
        )
        hit = _parse_subtitle_hit(reply or "")
        logger.info(
            "clip %s subtitle verify vl=%s: %s",
            segment_index,
            (reply or "?")[:20],
            "BURNED SUBTITLES" if hit else ("ok" if hit is False else "skip"),
        )
        if hit is True:
            return False
        return True

    def _submit_and_poll(
        self,
        *,
        headers: dict,
        payload: dict,
        output_path: Path,
        segment_index: int | None = None,
    ) -> Path:
        video_id, task_id, state, body = self._submit_task(headers=headers, payload=payload)
        agnes_id = video_id or task_id or "unknown"
        if state == "completed":
            return self._download_video(body, output_path, agnes_id)
        return self._poll_task(
            headers=headers,
            video_id=video_id,
            task_id=task_id,
            output_path=output_path,
            segment_index=segment_index,
        )

    def build_segment_clip(
        self,
        *,
        image_path: Path,
        subtitle_cues: list[tuple[str, float]],
        output_path: Path,
        motion_preset: str,
        work_dir: Path,
        segment_index: int,
        motion_prompt: str | None = None,
        image_prompt: str | None = None,
        speakers: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
        job_id: int | None = None,
    ) -> Path:
        _ = motion_preset
        self._active_job_id = job_id
        t0 = time.time()
        try:
            total_duration = clip_mgr.cue_total_duration(subtitle_cues)
            if total_duration <= 0:
                raise ValueError(f"segment {segment_index} has zero duration")

            clip_width = width or get_settings().video_width
            clip_height = height or get_settings().video_height
            api_w, api_h = _resolve_api_dimensions(clip_width, clip_height)
            prompt = _stabilize_motion_prompt(
                motion_prompt or "",
                image_prompt=image_prompt,
                speakers=speakers,
            )
            num_frames = _pick_num_frames(total_duration, self._frame_rate)
            raw_path = work_dir / f"{segment_index}.agnes_raw.mp4"

            logger.info(
                "segment %s: total_duration=%.2fs n_cues=%s; submitting agnes i2v "
                "(frames=%s, fps=%s, motion=%s)",
                segment_index,
                total_duration,
                len(subtitle_cues),
                num_frames,
                self._frame_rate,
                prompt,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                settings = get_settings()
                verify_attempts = max(1, settings.agnes_video_mouth_verify_attempts)
                for v_attempt in range(1, verify_attempts + 1):
                    self._generate_raw(
                        image_path, prompt, raw_path,
                        num_frames=num_frames,
                        width=api_w, height=api_h,
                        segment_index=segment_index,
                    )
                    self._raise_if_job_cancelled()
                    sampled = _sample_verify_windows(
                        raw_path,
                        prompt,
                        work_dir=work_dir,
                        segment_index=segment_index,
                    )
                    all_frames = [
                        uri for *_, frames in sampled for uri in frames
                    ]
                    mouth_ok = True
                    if settings.agnes_video_mouth_verify:
                        mouth_ok = self._verify_mouth_motion(
                            sampled,
                            segment_index=segment_index,
                        )
                    sub_ok = self._verify_no_burned_subtitles(
                        all_frames,
                        segment_index=segment_index,
                    )
                    if mouth_ok and sub_ok:
                        break
                    if not sub_ok:
                        if v_attempt < verify_attempts:
                            logger.warning(
                                "clip %s: subtitle verify FAILED, resubmitting i2v "
                                "(attempt %s/%s)",
                                segment_index,
                                v_attempt,
                                verify_attempts,
                            )
                            continue
                        raise AgnesI2VError(
                            f"clip {segment_index}: 画面出现烧录字幕"
                        )
                    if v_attempt < verify_attempts:
                        logger.warning(
                            "clip %s: mouth verify FAILED, resubmitting i2v "
                            "(attempt %s/%s)",
                            segment_index,
                            v_attempt,
                            verify_attempts,
                        )
                    else:
                        logger.warning(
                            "clip %s: mouth verify FAILED after %s attempts, "
                            "keeping last clip",
                            segment_index,
                            verify_attempts,
                        )
                self._raise_if_job_cancelled()
                logger.info("clip %s: raw done, fitting to %.1fs", segment_index, total_duration)
                raw_path = _loop_video_to_duration(
                    raw_path,
                    work_dir=work_dir,
                    segment_index=segment_index,
                    total_duration=total_duration,
                )
                # 字幕改在 merge 阶段 ASS 烧录
                fit_video_duration(
                    raw_path,
                    output_path,
                    total_duration,
                    width=clip_width,
                    height=clip_height,
                )
            finally:
                raw_path.unlink(missing_ok=True)

            logger.info("clip %s: done in %.1fs", segment_index, time.time() - t0)
            return output_path
        finally:
            self._active_job_id = None
