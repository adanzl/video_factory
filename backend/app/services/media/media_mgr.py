"""媒体合成总入口：分镜片段 → 正文 → 成片。"""

from __future__ import annotations

import logging
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gevent.lock import Semaphore

from app.config import get_settings
from app.exceptions import JobStageFailureError
from app.repositories.database import get_app
from app.utils.job_cancel import JobCancelledError, job_cancel
from app.services.tts.audio_timeline import (
    extend_phrase_cues_to_duration,
    segment_timeline_durations_from_db,
)
from app.services.segment.clip.clip_mgr import clip_mgr
from app.services.render.subtitle_style import subtitle_style_for_canvas
from app.services.media.ffmpeg_utils import build_ass_from_phrase_cues
from app.services.media.ffmpeg_utils import (
    concat_clips,
    concat_video_audio_pts_fixed,
    ffmpeg_hwaccel_config_summary,
    log_ffmpeg_hwaccel_config,
    merge_audio_video,
    mix_bgm_into_video,
    prepend_intro,
    probe_duration,
    probe_video_size,
)
from app.services.tts.tts_mgr import tts_mgr

logger = logging.getLogger(__name__)

__all__ = ["MediaMgr", "MergeResult", "SegmentClipsResult", "media_mgr", "inject_speaking_times_into_motion_prompts"]

# I2V 并发控制：单分镜占槽，限制全局同时进行的图生视频路数
_i2v_semaphore: Semaphore | None = None
_i2v_max_workers: int = 1
_i2v_semaphore_lock = Semaphore(value=1)
_I2V_PROVIDERS = frozenset({"wan_i2v", "agnes_i2v"})


def _greenlet_app_context():
    """greenlet 内做 DB 访问时兜底补 Flask app context。"""
    try:
        return get_app().app_context()
    except RuntimeError:
        from contextlib import nullcontext

        return nullcontext()


def _ensure_i2v_semaphore() -> Semaphore:
    global _i2v_semaphore, _i2v_max_workers
    settings = get_settings()
    max_workers = max(1, settings.video_max_workers)
    with _i2v_semaphore_lock:
        if _i2v_semaphore is None or _i2v_max_workers != max_workers:
            _i2v_max_workers = max_workers
            _i2v_semaphore = Semaphore(max_workers)
        return _i2v_semaphore


def _reset_i2v_semaphore_for_tests() -> None:
    """测试用：清空进程内 I2V 信号量缓存。"""
    global _i2v_semaphore, _i2v_max_workers
    with _i2v_semaphore_lock:
        _i2v_semaphore = None
        _i2v_max_workers = 1


@dataclass
class SegmentClipsResult:
    segment_clip_paths: list[tuple[int, Path]]


@dataclass
class MergeResult:
    body_path: Path
    body_with_audio_path: Path
    final_path: Path


_CAST_SIDE_ROLE: dict[str, str] = {
    "昭昭": "男孩",
    "灿灿": "女孩",
    "妈妈": "妈妈",
}
_LR_STAND_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)"
)
# 三人：左边/中间/右边（须先于二人正则匹配，避免截成「左边…右边」）
_LCR_STAND_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"中间是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"右边是\s*(昭昭|灿灿|妈妈)"
)
# 二人站位后补「妈妈在中间」（LLM 常写成这个顺序）
_LR_MID_STAND_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"右边是\s*(昭昭|灿灿|妈妈)"
    r"\s*[，,；;]\s*(?:妈妈在中间|中间是\s*(昭昭|灿灿|妈妈))"
)
_STAND_END_RE = re.compile(
    r"画面左边是\s*(?:昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"(?:中间是\s*(?:昭昭|灿灿|妈妈)\s*[，,；;]?\s*)?"
    r"右边是\s*(?:昭昭|灿灿|妈妈)\s*[。．;；]?"
)
_SPEAK_LINE_RE = re.compile(
    r"(?:[\d.]+-[\d.]+秒)?(?:画面(?:左边|中间|右边))?"
    r"(?:蓝色短袖T恤的短发男孩|粉色卫衣的黑马尾女孩|米色上衣的黑长发成年女性)?"
    r"(?:"
    r"(?P<side>左侧|中间|右侧)(?P<role>男孩|女孩|妈妈)"
    r"|"
    r"[（(]?(?P<name>昭昭|灿灿|妈妈)[）)]?"
    r")"
    r"(?:张嘴|嘴巴持续张合|开口)?说话"
    r"(?:，嘴唇明显一开一合约\d+次|，口型自然开合，说完即闭嘴)?，同时"
    r"(?P<action>[^；;。]*?)(?=[；;。]|$)"
)
# LLM 常把收束写成「灿灿说话后面部表情…」，统一识别（注入时整段丢弃）
_FACE_MARK_RE = re.compile(
    r"(?:两人|昭昭|灿灿|妈妈)?说话后面部表情恢复与静图一致："
)
_TAIL_ANCHOR_RE = re.compile(
    r"(?:(?:两人|昭昭|灿灿|妈妈)?说话后面部表情恢复与静图一致：|服装发型稳定|镜头固定)"
)
# 收束表情段会把嘴锁回静图闭嘴状态（I2V 直接不动口型），注入时
# 只保留服装/镜头锁定尾部，表情收束替换为嘴唇锁定句
_LOCK_TAIL_RE = re.compile(r"服装发型稳定|镜头固定")
_MOUTH_LOCK_HINT = "说话时只动嘴唇和下巴，头部姿态与五官其余部分保持稳定。"


def _parse_stand_layout(prompt: str) -> list[tuple[str, str]]:
    """解析站位 → [(左侧|中间|右侧, 角色名), ...]。三人优先于二人。"""
    lcr = _LCR_STAND_RE.search(prompt or "")
    if lcr:
        return [
            ("左侧", lcr.group(1)),
            ("中间", lcr.group(2)),
            ("右侧", lcr.group(3)),
        ]
    lr_mid = _LR_MID_STAND_RE.search(prompt or "")
    if lr_mid:
        mid = lr_mid.group(3) or "妈妈"
        return [
            ("左侧", lr_mid.group(1)),
            ("中间", mid),
            ("右侧", lr_mid.group(2)),
        ]
    lr = _LR_STAND_RE.search(prompt or "")
    if lr:
        return [("左侧", lr.group(1)), ("右侧", lr.group(2))]
    return []


def _side_speak_label(speaker: str, stand: list[tuple[str, str]]) -> str:
    """按站位句把说话人写成「左侧男孩/中间妈妈」等（与静图一致）。"""
    if speaker not in _CAST_SIDE_ROLE:
        return speaker
    role = _CAST_SIDE_ROLE[speaker]
    for side, name in stand:
        if name == speaker:
            return f"{side}{role}"
    return speaker


def _speaker_from_speak_match(
    m: re.Match[str],
    stand: list[tuple[str, str]],
) -> str | None:
    name = m.group("name")
    if name:
        return name
    side, role = m.group("side"), m.group("role")
    if not side or not role:
        return None
    for pos, candidate in stand:
        if pos == side and _CAST_SIDE_ROLE.get(candidate) == role:
            return candidate
    return None


def _inject_mouth_motion(
    prompt: str,
    seg: dict,
    cues: list[tuple[str, float]],
) -> str:
    """用真实时间按对白句序写入「{角色}说话，同时」时间轴。幂等。

    - 每一句对白对应一句「说话，同时」（同人多句写多行，不合并）
    - 时间轴相对本段 I2V：说话窗口最小值归零后全体平移
    - 说话句用「秒数+左右侧身份」（如左侧男孩），与 head 站位一致；LLM 仍写昭昭/灿灿说话
    - 说话句写自然口型（开口说话+口型自然开合+说完即闭嘴），非说话方写「嘴巴闭合不动」
    - 丢弃「面部表情恢复与静图一致」收束段（会把嘴锁回闭嘴），替换为嘴唇锁定句
    """
    dialogue = seg.get("dialogue") or []
    if not dialogue or not cues or not prompt.strip():
        return prompt

    stand = _parse_stand_layout(prompt)
    t = 0.0
    speaker_windows: list[tuple[str, float, float]] = []
    for i, (_, dur) in enumerate(cues):
        if i >= len(dialogue):
            break
        speaker = str((dialogue[i].get("speaker") or "")).strip()
        if not speaker:
            t += dur
            continue
        start, end = t, t + dur
        t = end
        speaker_windows.append((speaker, start, end))
    if not speaker_windows:
        return prompt

    # ambient：无说话槽且无站位句 → 不注入
    if "说话，同时" not in prompt and "画面左边" not in prompt:
        return prompt

    offset = min(start for _, start, _ in speaker_windows)
    speaker_times = [
        (speaker, f"{start - offset:.1f}-{end - offset:.1f}秒")
        for speaker, start, end in speaker_windows
    ]

    cast_order: list[str] = []
    for name, _, _ in speaker_windows:
        if name not in cast_order:
            cast_order.append(name)
    for _, name in stand:
        if name not in cast_order:
            cast_order.append(name)

    speak_re = _SPEAK_LINE_RE
    action_queues: dict[str, list[str]] = {}
    for m in speak_re.finditer(prompt):
        sp = _speaker_from_speak_match(m, stand)
        if not sp:
            continue
        action = (m.group("action") or "").strip().rstrip("。")
        # 动作里若误拼收束标记，截断
        face_in_action = _FACE_MARK_RE.search(action)
        if face_in_action:
            action = action[: face_in_action.start()].strip().rstrip("。；;")
        action = re.sub(r"，?此时.*$", "", action).strip().rstrip("，,")
        if action:
            action_queues.setdefault(sp, []).append(action)

    fallback = {
        "昭昭": "双肩轻轻耸起后停止",
        "灿灿": "微微点头后停止",
        "妈妈": "微微点头后停止",
    }

    speaks = list(speak_re.finditer(prompt))

    def _extract_tail(after: int) -> str:
        """从 after 起取服装/镜头锁定尾部；丢弃表情收束与无时间轴残留动作句。"""
        rest = prompt[after:]
        m_face = _FACE_MARK_RE.search(rest)
        if m_face:
            body = rest[m_face.end() :]
            body = speak_re.sub("", body)
            # 收束段整体丢弃（会锁回闭嘴脸），只保留其后的服装/镜头锁定
            extras = list(_FACE_MARK_RE.finditer(body))
            if extras:
                body = body[extras[-1].end() :]
            m_lock = _LOCK_TAIL_RE.search(body)
            return body[m_lock.start() :] if m_lock else ""
        m_anchor = _TAIL_ANCHOR_RE.search(rest)
        if m_anchor:
            tail = speak_re.sub("", rest[m_anchor.start() :])
            m_lock = _LOCK_TAIL_RE.search(tail)
            return tail[m_lock.start() :] if m_lock else ""
        # 无收束锚点：不保留 speak 后的游离动作（常为 LLM 多写的无时间句）
        return ""

    if speaks:
        head = prompt[: speaks[0].start()]
        tail = _extract_tail(speaks[-1].end())
    else:
        m_stand = _STAND_END_RE.search(prompt)
        if not m_stand:
            return prompt
        head = prompt[: m_stand.end()]
        if not head.endswith(("。", "．", ";", "；")):
            head = head.rstrip() + "。"
        tail = _extract_tail(m_stand.end())
        if not tail and "说话，同时" in prompt[m_stand.end() :]:
            # 有说话槽但正则未命中时，清掉旧说话句再拼
            dirty = prompt[m_stand.end() :]
            dirty = speak_re.sub("", dirty)
            dirty = re.sub(r"[；;]{2,}", "；", dirty).lstrip("；;")
            m_anchor = _TAIL_ANCHOR_RE.search(dirty)
            tail = dirty[m_anchor.start() :] if m_anchor else ""

    clauses: list[str] = []
    last_i = len(speaker_times) - 1
    for i, (speaker, time_str) in enumerate(speaker_times):
        q = action_queues.get(speaker) or []
        action = q.pop(0) if q else fallback.get(speaker, "微微点头后停止")
        if i < last_i and action.endswith("后定格"):
            action = action[: -len("后定格")] + "后停止"
        elif i == last_i and "定格" not in action and action.endswith("后停止"):
            action = action[: -len("后停止")] + "后定格"

        label = _side_speak_label(speaker, stand)
        # 显式写「口型自然开合」防止被面部锁定压掉；不写固定次数
        # （固定次数会机械开合像金鱼、且与语速对不上停不下来）
        lead = (
            f"{time_str}{label}开口说话，口型自然开合，"
            f"说完即闭嘴，同时{action}"
        )
        quiet: list[str] = []
        for other in cast_order:
            if other == speaker:
                continue
            quiet.append(f"{_side_speak_label(other, stand)}嘴巴闭合不动")
        if quiet:
            lead = f"{lead}，此时{'、'.join(quiet)}"
        clauses.append(lead)

    middle = "；".join(clauses)
    if not middle.endswith(("。", "；", ";")):
        middle += "。"

    return f"{head}{middle}{_MOUTH_LOCK_HINT}{tail}"


def inject_speaking_times_into_motion_prompts(
    segments: list[dict],
    subtitle_cues: list,
    *,
    script_segments: list[dict] | None = None,
    segment_indices: set[int] | None = None,
    estimate_cues_without_tts: bool = False,
) -> int:
    """按 TTS subtitle_cues 为 motion_prompt 写入说话时间轴（原地更新 segments）。"""
    script_by_index: dict[int, dict] = {}
    if script_segments:
        for item in script_segments:
            if isinstance(item, dict) and item.get("segment_index") is not None:
                script_by_index[int(item["segment_index"])] = item

    changed = 0
    for seg in segments:
        index = int(seg.get("segment_index") or 0)
        if index <= 0:
            continue
        if segment_indices is not None and index not in segment_indices:
            continue
        script_seg = script_by_index.get(index, {})
        motion = (seg.get("motion_prompt") or script_seg.get("motion_prompt") or "").strip()
        if not motion:
            continue
        dialogue = seg.get("dialogue") or script_seg.get("dialogue")
        if not dialogue:
            continue
        cues = tts_mgr.cues_for_segment(subtitle_cues, index)
        if not cues and estimate_cues_without_tts:
            cues = []
            for line in dialogue:
                if not isinstance(line, dict):
                    continue
                text = str(line.get("text") or line.get("line") or "").strip()
                cues.append((text, max(0.1, len(text) * 0.25)))
        if not cues:
            continue
        payload = {**script_seg, **seg, "dialogue": dialogue, "motion_prompt": motion}
        updated = _inject_mouth_motion(motion, payload, cues)
        if updated == motion:
            continue
        changed += 1
        seg["motion_prompt"] = updated
        if index in script_by_index:
            script_by_index[index]["motion_prompt"] = updated
    return changed


class MediaMgr:
    """媒体合成管理器。"""

    def _resolve_clip_provider(
        self,
        *,
        visual_mode: str,
        job: dict | None = None,
        segment: dict | None = None,
    ) -> str:
        settings = get_settings()
        if visual_mode == "kling_std" and settings.kling_upgrade_enabled:
            return "kling_std"
        from app.utils.job_info import resolve_video_provider

        return resolve_video_provider(
            job, visual_mode=visual_mode, settings=settings, segment=segment
        )

    def _describe_clip_provider(
        self,
        provider: str,
        *,
        motion_preset: str,
        width: int,
        height: int,
    ) -> str:
        settings = get_settings()
        if provider == "wan_i2v":
            return (
                f"provider=wan_i2v, model={settings.wan_i2v_model}, "
                f"resolution={settings.wan_i2v_resolution}, "
                f"prompt_extend={settings.wan_i2v_prompt_extend}, "
                f"size={width}x{height}"
            )
        if provider == "agnes_i2v":
            return (
                f"provider=agnes_i2v, model={settings.agnes_video_model}, "
                f"frame_rate={settings.clip_fps}, "
                f"size={width}x{height}"
            )
        if provider == "ffmpeg":
            return f"provider=ffmpeg, motion_preset={motion_preset}, size={width}x{height}"
        return f"provider={provider}, motion_preset={motion_preset}, size={width}x{height}"

    @staticmethod
    def _load_subtitle_cues(media_dir: Path) -> list:
        cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
        return tts_mgr.load_subtitle_cues(cues_path)

    @staticmethod
    def _cues_for_segment(seg: dict, subtitle_cues: list) -> list[tuple[str, float]]:
        index = seg["segment_index"]
        seg_cues = tts_mgr.cues_for_segment(subtitle_cues, index)
        if seg_cues:
            return seg_cues
        duration = seg.get("duration_sec")
        text = (seg.get("text") or "").strip()
        if duration is not None and float(duration) > 0:
            return [(text or f"segment {index}", float(duration))]
        return []

    def build_segment_clips(
        self,
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path: Path | None = None,
        only_segment_indices: set[int] | None = None,
        job: dict | None = None,
        on_clip_done: Callable[[int, Path, float], None] | None = None,
    ) -> SegmentClipsResult:
        settings = get_settings()
        from app.utils.job_info import resolve_segment_video_size

        clip_width, clip_height = resolve_segment_video_size(job, settings=settings)
        clips_dir = media_dir / "segments"
        clips_dir.mkdir(parents=True, exist_ok=True)

        subtitle_cues = self._load_subtitle_cues(media_dir)
        cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
        if not subtitle_cues:
            logger.warning(
                "clip batch: missing %s, will fallback to segment duration_sec where available",
                cues_path,
            )
        elif audio_path is None:
            logger.info("clip batch: loaded subtitle cues from %s", cues_path)

        targets = (
            [seg for seg in segments if seg["segment_index"] in only_segment_indices]
            if only_segment_indices is not None
            else segments
        )
        total = len(targets)
        t_start = time.time()
        target_indices = [seg["segment_index"] for seg in targets]

        uses_i2v = any(
            self._resolve_clip_provider(
                visual_mode=seg.get("visual_mode") or "static_motion",
                job=job,
                segment=seg,
            )
            in _I2V_PROVIDERS
            for seg in targets
        )
        max_workers = (
            1
            if settings.mock_mode or not uses_i2v
            else max(1, settings.video_max_workers)
        )

        logger.info(
            "clip batch start: count=%s, workers=%s, segments=%s, size=%sx%s%s",
            total,
            max_workers,
            target_indices,
            clip_width,
            clip_height,
            " (i2v)" if uses_i2v else "",
        )

        def build_one(seg: dict, ordinal: int) -> tuple[int, Path, float]:
            t0 = time.time()
            job_id = int(job["id"]) if job is not None and job.get("id") is not None else None
            if job_id is not None:
                job_cancel.raise_if_cancelled(job_id)
            index = seg["segment_index"]
            clip_path = clips_dir / f"{index}.mp4"

            visual_mode = seg.get("visual_mode") or "static_motion"
            provider = self._resolve_clip_provider(
                visual_mode=visual_mode, job=job, segment=seg
            )
            params_desc = self._describe_clip_provider(
                provider,
                motion_preset=settings.motion_preset,
                width=clip_width,
                height=clip_height,
            )
            if provider == "kling_std":
                raise NotImplementedError(
                    f"segment {index} visual_mode=kling_std 需 VideoProvider，尚未接入"
                )

            seg_cues = self._cues_for_segment(seg, subtitle_cues)
            if not seg_cues:
                raise ValueError(
                    f"segment {index} 无句级字幕时间轴，请先执行 tts，或确保分镜有 duration_sec"
                )
            raw_dur = seg.get("duration_sec")
            if raw_dur is None or float(raw_dur) <= 0:
                raise ValueError(
                    f"segment {index} 缺少 duration_sec，请先执行 tts"
                )
            seg_cues = extend_phrase_cues_to_duration(
                seg_cues, float(raw_dur)
            )
            if not tts_mgr.cues_for_segment(subtitle_cues, index):
                logger.info(
                    "clip segment %s: using duration_sec fallback (%.2fs)",
                    index,
                    sum(duration for _, duration in seg_cues),
                )
            motion_prompt = seg.get("motion_prompt") or seg.get("visual_brief") or ""
            # 代码注入开口动作（从 dialogue 取 speaker + 从 cues 取时长）
            motion_prompt = _inject_mouth_motion(motion_prompt, seg, seg_cues)
            seg["motion_prompt"] = motion_prompt
            # 落库，避免 UI/后续重跑仍读到未注入时间的 LLM 原文
            seg_id = seg.get("id")
            if seg_id is not None and motion_prompt:
                try:
                    from app.repositories import repo_segment
                    from app.repositories.sql_exec import atomic

                    with _greenlet_app_context():
                        with atomic():
                            repo_segment.update_segment(
                                int(seg_id), motion_prompt=motion_prompt
                            )
                except Exception:
                    logger.exception(
                        "clip segment %s: failed to persist injected motion_prompt",
                        index,
                    )
            image_prompt = seg.get("image_prompt") or ""
            logger.info(
                "clip %s/%s building segment %s | %s | image_chars=%s motion_chars=%s",
                ordinal,
                total,
                index,
                params_desc,
                len(image_prompt),
                len(motion_prompt),
            )

            i2v_sem: Semaphore | None = None
            if provider in _I2V_PROVIDERS:
                i2v_sem = _ensure_i2v_semaphore()
                logger.info(
                    "clip segment %s: waiting i2v slot (max_workers=%s)...",
                    index,
                    _i2v_max_workers,
                )
                i2v_sem.acquire()
                logger.info("clip segment %s: acquired i2v slot", index)
            try:
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
                raw_image_path = seg.get("image_path")
                if not raw_image_path:
                    raise JobStageFailureError(
                        f"segment {index} 缺少 image_path，无法生成视频片段"
                    )
                clip_mgr.build_segment_clip(
                    clip_provider=provider,
                    image_path=Path(raw_image_path),
                    subtitle_cues=seg_cues,
                    output_path=clip_path,
                    motion_preset=settings.motion_preset,
                    work_dir=clips_dir,
                    segment_index=index,
                    motion_prompt=motion_prompt,
                    image_prompt=image_prompt or None,
                    speakers=seg.get("speakers") if isinstance(seg.get("speakers"), list) else None,
                    width=clip_width,
                    height=clip_height,
                    job_id=job_id,
                )
            finally:
                if i2v_sem is not None:
                    i2v_sem.release()
                    logger.info("clip segment %s: released i2v slot", index)

            elapsed = time.time() - t0
            logger.info(
                "clip %s/%s done segment %s in %.1fs | %s",
                ordinal,
                total,
                index,
                elapsed,
                params_desc,
            )
            return seg["id"], clip_path, elapsed

        segment_clips: list[tuple[int, Path]] = []
        if max_workers <= 1:
            for i, seg in enumerate(targets, 1):
                seg_id, clip_path, gen_sec = build_one(seg, i)
                segment_clips.append((seg_id, clip_path))
                if on_clip_done is not None:
                    on_clip_done(seg_id, clip_path, gen_sec)
        else:
            from gevent import iwait
            from gevent.lock import Semaphore
            from gevent.pool import Group

            # Pool.spawn 在池满时会阻塞父协程。若用列表推导一次性 spawn，
            # on_clip_done 要等 (n-workers) 路完成后才能开始，页面长时间看不到视频。
            # Group + Semaphore：spawn 不阻塞，完成即回调落库。
            sem = Semaphore(max_workers)
            group = Group()
            job_id = (
                int(job["id"])
                if job is not None and job.get("id") is not None
                else None
            )
            failures: list[BaseException] = []

            def limited_build(seg: dict, ordinal: int) -> tuple[int, Path, float]:
                with sem:
                    if job_id is not None:
                        job_cancel.raise_if_cancelled(job_id)
                    return build_one(seg, ordinal)

            green_lets = [
                group.spawn(limited_build, seg, i)
                for i, seg in enumerate(targets, 1)
            ]
            try:
                for g in iwait(green_lets):
                    if job_id is not None and job_cancel.is_cancelled(job_id):
                        exc = JobCancelledError(f"job {job_id} aborted")
                        group.kill(exc, block=False)
                        raise exc
                    try:
                        seg_id, clip_path, gen_sec = g.get()
                    except JobCancelledError:
                        raise
                    except BaseException as exc:
                        failures.append(exc)
                        still = sum(1 for x in green_lets if not x.ready())
                        logger.warning(
                            "clip worker failed (%s/%s still running): %s",
                            still,
                            total,
                            exc,
                        )
                        continue
                    segment_clips.append((seg_id, clip_path))
                    if on_clip_done is not None:
                        on_clip_done(seg_id, clip_path, gen_sec)
            except JobCancelledError:
                group.kill(block=False)
                raise
            if failures:
                logger.error(
                    "clip batch finished with failures: ok=%s/%s, failed=%s",
                    len(segment_clips),
                    total,
                    len(failures),
                )
                raise failures[0]

        elapsed = time.time() - t_start
        logger.info(
            "clip batch done: %s/%s in %.1fs, workers=%s, segments=%s",
            len(segment_clips),
            total,
            elapsed,
            max_workers,
            target_indices,
        )
        return SegmentClipsResult(segment_clip_paths=segment_clips)

    def merge_final(
        self,
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path: Path,
        subtitle_path: Path | None,
        intro_path: Path | None,
        end_path: Path | None = None,
        bgm_path: Path | None = None,
        bgm_volume_db: float = -14.0,
        burn_subtitles: bool = True,
        xfade_duration_sec: float | None = None,
        xfade_transition: str | None = None,
    ) -> MergeResult:
        t0 = time.time()
        log_ffmpeg_hwaccel_config(context="merge")
        logger.info("merge: %s", ffmpeg_hwaccel_config_summary())
        clips_dir = media_dir / "segments"
        sorted_seg_lst = sorted(segments, key=lambda s: s["segment_index"])
        clip_paths: list[Path] = []
        for seg in sorted_seg_lst:
            index = seg["segment_index"]
            if seg.get("clip_path"):
                clip_paths.append(Path(seg["clip_path"]))
            else:
                fallback = clips_dir / f"{index}.mp4"
                if not fallback.exists():
                    raise FileNotFoundError(
                        f"segment {index} 缺少 clip，请从 segment 阶段重跑"
                    )
                clip_paths.append(fallback)

        clip_durations = segment_timeline_durations_from_db(sorted_seg_lst)

        logger.info("merge: concatenating %s clips with pts fix", len(clip_paths))
        body_path = media_dir / "body.mp4"
        body_with_audio = media_dir / "body_with_audio.mp4"
        concat_video_audio_pts_fixed(
            clip_paths,
            audio_path,
            body_with_audio,
            clip_durations=clip_durations,
            xfade_duration_sec=xfade_duration_sec,
            xfade_transition=xfade_transition,
        )
        logger.info("merge: audio merged (pts corrected)")

        # 成片统一 ASS 烧字幕（分镜 clip 不再叠字幕）
        if burn_subtitles:
            subtitle_cues = tts_mgr.load_subtitle_cues(
                tts_mgr.subtitle_cues_path_for(audio_path.parent)
            )
            flat_cues: list[tuple[str, float]] = []
            for seg in sorted_seg_lst:
                index = seg["segment_index"]
                for cue in subtitle_cues:
                    if cue.segment_index != index or cue.duration_sec <= 0:
                        continue
                    flat_cues.append((cue.text, cue.duration_sec))
            if not flat_cues and subtitle_path and subtitle_path.exists():
                logger.warning(
                    "merge: no subtitle_cues.json phrases; subtitle_path=%s unused for burn",
                    subtitle_path.name,
                )
            if flat_cues:
                from app.services.segment.clip.clip_render import burn_ass_subtitles

                base_w, base_h = probe_video_size(body_with_audio)
                work_dir = media_dir / "merge_work"
                work_dir.mkdir(parents=True, exist_ok=True)
                subtitle_style = subtitle_style_for_canvas(base_w, base_h)
                logger.info(
                    "merge: burning %s subtitle cues via ass on %sx%s font_size=%s",
                    len(flat_cues),
                    base_w,
                    base_h,
                    subtitle_style["font_size"],
                )
                ass_path = work_dir / "subtitles.ass"
                ass_path.write_text(
                    build_ass_from_phrase_cues(flat_cues, width=base_w, height=base_h),
                    encoding="utf-8",
                )
                burned = work_dir / "body_with_subs.mp4"
                burn_ass_subtitles(body_with_audio, ass_path, burned)
                shutil.move(burned, body_with_audio)
            else:
                logger.warning("merge: no subtitle cues with duration, skipping burn")
        else:
            logger.info("merge: subtitle burn disabled")

        if bgm_path is not None and bgm_path.exists():
            logger.info(
                "merge: mixing bgm path=%s volume_db=%.1f",
                bgm_path.name,
                bgm_volume_db,
            )
            mixed = media_dir / "body_with_bgm.mp4"
            mix_bgm_into_video(
                body_with_audio,
                bgm_path,
                mixed,
                volume_db=bgm_volume_db,
            )
            shutil.move(mixed, body_with_audio)

        final_path = media_dir / "final.mp4"
        if intro_path and intro_path.exists():
            logger.info("merge: prepending intro")
            prepend_intro(intro_path, body_with_audio, final_path)
        else:
            shutil.copy2(body_with_audio, final_path)

        if end_path and end_path.exists():
            logger.info("merge: appending end card")
            tmp_final = final_path.with_suffix(".tmp.mp4")
            shutil.move(final_path, tmp_final)
            concat_clips([tmp_final, end_path], final_path)
            tmp_final.unlink(missing_ok=True)

        elapsed = time.time() - t0
        logger.info("merge: done in %.1fs -> %s", elapsed, final_path)
        return MergeResult(
            body_path=body_path,
            body_with_audio_path=body_with_audio,
            final_path=final_path,
        )

    def merge_material_final(
        self,
        *,
        media_dir: Path,
        base_video_path: Path,
        audio_path: Path,
        intro_path: Path | None,
        burn_subtitles: bool = True,
    ) -> MergeResult:
        """素材流水线：基底视频 + 字幕烧录 + TTS + 片头。"""
        t0 = time.time()
        log_ffmpeg_hwaccel_config(context="merge_material")
        logger.info("merge_material: %s", ffmpeg_hwaccel_config_summary())
        subtitle_cues = tts_mgr.load_subtitle_cues(
            tts_mgr.subtitle_cues_path_for(audio_path.parent)
        )
        if burn_subtitles and not subtitle_cues:
            raise FileNotFoundError(
                f"缺少 {tts_mgr.subtitle_cues_path_for(audio_path.parent)}，请从 tts 阶段重跑"
            )

        audio_dur = probe_duration(audio_path)
        base_dur = probe_duration(base_video_path)
        tail_tol = 0.08
        silent_tail = base_dur > audio_dur + tail_tol
        output_dur = base_dur if silent_tail else audio_dur
        if silent_tail:
            logger.info(
                "merge_material: base %.2fs > audio %.2fs, keep full video with silent tail",
                base_dur,
                audio_dur,
            )
        else:
            logger.info(
                "merge_material: output duration %.2fs (audio-driven)",
                output_dur,
            )

        flat_cues = [
            (cue.text, cue.duration_sec)
            for cue in subtitle_cues
            if cue.duration_sec > 0 and cue.text.strip()
        ] if burn_subtitles else []

        work_dir = media_dir / "merge_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        from app.services.segment.clip.clip_render import (
            fit_video_duration,
            fit_video_with_ass_subtitles,
        )

        body_path = media_dir / "body.mp4"
        base_w, base_h = probe_video_size(base_video_path)
        if flat_cues:
            subtitle_style = subtitle_style_for_canvas(base_w, base_h)
            logger.info(
                "merge_material: burning %s subtitle cues via ass on %sx%s "
                "font_size=%s (libx264 cpu)",
                len(flat_cues),
                base_w,
                base_h,
                subtitle_style["font_size"],
            )
            ass_path = work_dir / "subtitles.ass"
            ass_path.write_text(
                build_ass_from_phrase_cues(flat_cues, width=base_w, height=base_h),
                encoding="utf-8",
            )
            fit_video_with_ass_subtitles(
                base_video_path,
                ass_path,
                body_path,
                output_dur,
                width=base_w,
                height=base_h,
            )
        else:
            if burn_subtitles:
                logger.warning(
                    "merge_material: no subtitle cues with duration, skipping burn"
                )
            else:
                logger.info("merge_material: subtitle burn disabled")
            fit_video_duration(
                base_video_path,
                body_path,
                output_dur,
                width=base_w,
                height=base_h,
            )

        logger.info("merge_material: body.mp4 done")

        body_with_audio = media_dir / "body_with_audio.mp4"
        merge_audio_video(
            body_path,
            audio_path,
            body_with_audio,
            subtitle_path=None,
            silent_tail_when_video_longer=silent_tail,
        )
        logger.info("merge_material: audio merged")

        final_path = media_dir / "final.mp4"
        if intro_path and intro_path.exists():
            logger.info("merge_material: prepending intro")
            prepend_intro(intro_path, body_with_audio, final_path)
        else:
            shutil.copy2(body_with_audio, final_path)

        elapsed = time.time() - t0
        logger.info("merge_material: done in %.1fs -> %s", elapsed, final_path)
        return MergeResult(
            body_path=body_path,
            body_with_audio_path=body_with_audio,
            final_path=final_path,
        )


media_mgr = MediaMgr()
