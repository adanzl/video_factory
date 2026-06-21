from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.utils.async_util import run_subprocess_safe

# cSpell: disable

_logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT = 600.0
_PROBE_TIMEOUT = 60.0
_PIX_FMT = "yuv420p"
_VAAPI_HWUPLOAD = "format=nv12,hwupload"


@dataclass(frozen=True)
class _CmdResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def _combined_output(result: _CmdResult) -> str:
    return f"{result.stderr or ''}\n{result.stdout or ''}"


def _run_cmd(
    args: list[str],
    *,
    check: bool = True,
    timeout: float = _FFMPEG_TIMEOUT,
) -> _CmdResult:
    returncode, stdout, stderr = run_subprocess_safe(args, timeout=timeout)
    result = _CmdResult(args=args, returncode=returncode, stdout=stdout, stderr=stderr)
    if check and returncode != 0:
        detail = _combined_output(result).strip()
        raise RuntimeError(f"command failed: {detail[-2000:]}")
    return result


def run_ffmpeg(
    args: list[str],
    *,
    check: bool = True,
) -> _CmdResult:
    result = _run_cmd(args, check=False)
    if check and result.returncode != 0:
        detail = _combined_output(result).strip()
        raise RuntimeError(f"ffmpeg failed: {detail[-2000:]}")
    return result


def vaapi_enabled() -> bool:
    return get_settings().ffmpeg_hwaccel == "vaapi"


def ffmpeg_cmd_start(*, hide_banner: bool = False, hwaccel: bool | None = None) -> list[str]:
    """ffmpeg 命令前缀；VAAPI 时注入 -vaapi_device。hwaccel=False 可显式禁用。"""
    cmd = ["ffmpeg", "-y"]
    if hide_banner:
        cmd.append("-hide_banner")
    use_hw = vaapi_enabled() if hwaccel is None else hwaccel
    if use_hw:
        cmd.extend(["-vaapi_device", get_settings().ffmpeg_vaapi_device])
    return cmd


def cpu_pix_fmt_suffix() -> str:
    """滤镜链中间步骤：软件像素格式。"""
    return f",format={_PIX_FMT}"


def vf_for_encode(base_vf: str) -> str:
    """-vf 链末尾：VAAPI 时 hwupload，否则 yuv420p。"""
    if vaapi_enabled():
        return f"{base_vf},{_VAAPI_HWUPLOAD}"
    if f"format={_PIX_FMT}" in base_vf:
        return base_vf
    return f"{base_vf},format={_PIX_FMT}"


def finalize_filter_complex(parts: list[str], *, out_label: str = "out") -> list[str]:
    """filter_complex 末尾：VAAPI 时在输出标签前插入 hwupload。"""
    if not vaapi_enabled() or not parts:
        return parts
    updated = list(parts)
    last = updated[-1]
    updated[-1] = last.replace(f"[{out_label}]", "[vpre]")
    updated.append(f"[vpre]{_VAAPI_HWUPLOAD}[{out_label}]")
    return updated


def _crf_to_vaapi_qp(crf: int) -> int:
    return max(18, min(40, crf + 4))


def libx264_encode_args(*, subtitle: bool = False, force_cpu: bool = False) -> list[str]:
    """统一视频编码参数；VAAPI 时用 h264_vaapi + qp，否则 libx264 + crf。

    force_cpu=True 时强制 libx264（用于 libass/subtitles 等只能走 CPU 滤镜链的场景）。
    """
    settings = get_settings()
    crf = settings.ffmpeg_subtitle_crf if subtitle else settings.ffmpeg_crf
    if vaapi_enabled() and not force_cpu:
        return [
            "-c:v",
            settings.ffmpeg_vaapi_codec,
            "-qp",
            str(_crf_to_vaapi_qp(crf)),
            "-movflags",
            "+faststart",
        ]
    return [
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        settings.ffmpeg_preset,
        "-pix_fmt",
        _PIX_FMT,
        "-movflags",
        "+faststart",
    ]


def ffmpeg_hwaccel_config_summary() -> str:
    """当前视频重编码所用的硬件加速/编码器配置（供日志与阶段记录）。"""
    settings = get_settings()
    if vaapi_enabled():
        qp = _crf_to_vaapi_qp(settings.ffmpeg_crf)
        sub_qp = _crf_to_vaapi_qp(settings.ffmpeg_subtitle_crf)
        return (
            f"hwaccel=vaapi device={settings.ffmpeg_vaapi_device} "
            f"encoder={settings.ffmpeg_vaapi_codec} qp={qp} subtitle_qp={sub_qp}"
        )
    return (
        f"hwaccel=none encoder=libx264 crf={settings.ffmpeg_crf} "
        f"subtitle_crf={settings.ffmpeg_subtitle_crf} preset={settings.ffmpeg_preset}"
    )


def log_ffmpeg_hwaccel_config(*, context: str = "encode") -> None:
    _logger.info("[FFMPEG] %s: %s", context, ffmpeg_hwaccel_config_summary())


def _probe_video_stream(path: Path) -> dict | None:
    out = _run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        timeout=_PROBE_TIMEOUT,
    )
    streams = json.loads(out.stdout).get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    width = stream.get("width")
    height = stream.get("height")
    if width is None or height is None:
        return None
    return {
        "codec": stream.get("codec_name"),
        "width": int(width),
        "height": int(height),
        "pix_fmt": stream.get("pix_fmt"),
    }


def _null_sink_output(input_path: Path, *, af: str | None = None) -> str:
    args = ["ffmpeg", "-hide_banner", "-i", str(input_path)]
    if af:
        args.extend(["-af", af])
    args.extend(["-f", "null", "-"])
    return _combined_output(run_ffmpeg(args, check=False))


def silence_detect_log(
    path: Path,
    *,
    noise_db: float = -40.0,
    min_duration_sec: float = 0.35,
) -> str:
    return _null_sink_output(
        path,
        af=f"silencedetect=noise={noise_db}dB:d={min_duration_sec}",
    )


def loudnorm_measure_log(path: Path) -> str:
    return _null_sink_output(path, af="loudnorm=print_format=summary")


def loudnorm_apply(
    input_path: Path,
    output_path: Path,
    *,
    target_lufs: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}",
            str(output_path),
        ]
    )
    return output_path


def loudnorm_replace(
    path: Path,
    *,
    target_lufs: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
) -> Path:
    tmp = path.with_name(f"{path.stem}.norm{path.suffix}")
    loudnorm_apply(path, tmp, target_lufs=target_lufs, true_peak=true_peak, lra=lra)
    tmp.replace(path)
    return path


def extract_first_frame(video_path: Path, output_path: Path) -> Path:
    """从视频提取首帧，保存为 JPEG 封面。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ],
    )
    return output_path


def probe_duration(path: Path) -> float:
    out = _run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",  # cSpell: disable-line
            str(path),
        ],
        timeout=_PROBE_TIMEOUT,
    )
    return float(out.stdout.strip())


def probe_video_size(path: Path) -> tuple[int, int]:
    out = _run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        timeout=_PROBE_TIMEOUT,
    )
    raw = out.stdout.strip()
    if "x" not in raw:
        raise ValueError(f"cannot probe video size: {path}")
    width, height = raw.split("x", 1)
    return int(width), int(height)


def scale_pad_filter(*, width: int, height: int) -> str:
    """等比缩放至目标画布内，不足处留黑边。"""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
    )


def fit_video_to_canvas(
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
) -> Path:
    """将视频归一化到设计分辨率（等比缩放 + 黑边，保留音轨）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hide_banner=True),
            "-i",
            str(input_path),
            "-vf",
            vf_for_encode(scale_pad_filter(width=width, height=height)),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            *libx264_encode_args(),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )
    return output_path


def concat_clips(clips: list[Path], output_path: Path) -> Path:
    """拼接同编码片段；音频 MP3 多条时重编码，避免 -c copy 接缝咔嗒。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not clips:
        raise ValueError("no clips to concat")
    if len(clips) == 1:
        _run_cmd(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-i",
                str(clips[0]),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
        )
        return output_path

    if output_path.suffix.lower() in {".mp3", ".wav"}:
        return _concat_audio_reencode(clips, output_path)

    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{clip.resolve()}'" for clip in clips),
        encoding="utf-8",
    )
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ],
    )
    list_file.unlink(missing_ok=True)
    return output_path


def _concat_audio_reencode(clips: list[Path], output_path: Path) -> Path:
    n = len(clips)
    inputs: list[str] = []
    for clip in clips:
        inputs.extend(["-i", str(clip.resolve())])
    chains = "".join(f"[{i}:a]" for i in range(n))
    filter_graph = f"{chains}concat=n={n}:v=0:a=1[outa]"
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            *inputs,
            "-filter_complex",
            filter_graph,
            "-map",
            "[outa]",
            "-ar",
            "22050",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ],
    )
    return output_path


def concat_videos(clips: list[Path], output_path: Path) -> Path:
    return concat_clips(clips, output_path)


def generate_silent_mp3(output_path: Path, duration_sec: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=22050:cl=mono",
            "-t",
            str(duration_sec),
            "-c:a",
            "libmp3lame",
            str(output_path),
        ],
    )
    return output_path


def sequence_to_video(
    frames_dir: Path,
    output_path: Path,
    *,
    fps: int = 25,
    frame_count: int | None = None,
) -> Path:
    """将 frame_0000.png 序列编码为 H.264 视频（无音轨）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "frame_%04d.png"
    cmd = [
        *ffmpeg_cmd_start(),
        "-framerate",
        str(fps),
        "-i",
        str(pattern),
    ]
    if vaapi_enabled():
        cmd.extend(["-vf", _VAAPI_HWUPLOAD])
    cmd.extend(libx264_encode_args())
    if frame_count is not None:
        cmd.extend(["-frames:v", str(frame_count)])
    cmd.append(str(output_path))
    _run_cmd(cmd)
    return output_path


def mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """合并视频与音频，以视频时长为准。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            str(output_path),
        ],
    )
    return output_path


def image_to_video(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    settings = get_settings()
    width = width if width is not None else settings.video_width
    height = height if height is not None else settings.video_height
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    with Image.open(image_path) as img:
        need_scale = img.size != (width, height)
    vf = (
        f"scale={width}:{height}:flags=lanczos"  # cSpell: disable-line
        if need_scale
        else ""
    )
    if vf:
        vf = vf_for_encode(vf)
    elif vaapi_enabled():
        vf = _VAAPI_HWUPLOAD
    else:
        vf = f"format={_PIX_FMT}"

    _run_cmd(
        [
            *ffmpeg_cmd_start(),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            vf,
            *libx264_encode_args(),
            str(output_path),
        ],
    )
    return output_path


def merge_audio_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    subtitle_path: Path | None = None,
    silent_tail_when_video_longer: bool = False,
) -> Path:
    """合并画面与配音，以音频时长为准，不拉伸/压缩音频。

    silent_tail_when_video_longer=True 时：若画面长于配音，保留完整画面并在末尾补静音
    （素材流水线：口播结束后画面继续、无配音）。
    """
    _ = subtitle_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dur = probe_duration(audio_path)
    video_dur = probe_duration(video_path)
    drift = video_dur - audio_dur
    tail_tol = 0.08

    if silent_tail_when_video_longer and drift > tail_tol:
        pad_sec = video_dur - audio_dur
        _run_cmd(
            [
                *ffmpeg_cmd_start(),
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-filter_complex",
                f"[1:a]apad=pad_dur={pad_sec:.3f}[aout]",
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-t",
                f"{video_dur:.3f}",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
        )
        return output_path

    if abs(drift) <= tail_tol:
        _run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-t",
                f"{audio_dur:.3f}",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
        )
        return output_path

    if drift > 0:
        vf = f"trim=0:{audio_dur:.3f},setpts=PTS-STARTPTS"
    else:
        vf = f"tpad=stop_mode=clone:stop_duration={audio_dur - video_dur:.3f}"

    _run_cmd(
        [
            *ffmpeg_cmd_start(),
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[0:v]{vf_for_encode(vf)}[vout]",
            "-map",
            "[vout]",
            "-map",
            "1:a:0",
            *libx264_encode_args(),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-t",
            f"{audio_dur:.3f}",
            str(output_path),
        ],
    )
    return output_path


def _probe_audio_sample_rate(path: Path) -> int | None:
    out = _run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",  # cSpell: disable-line
            str(path),
        ],
        check=False,
        timeout=_PROBE_TIMEOUT,
    )
    rate = out.stdout.strip()
    if not rate:
        return None
    return int(rate)


def _can_concat_demuxer_copy(intro_path: Path, body_path: Path) -> bool:
    """片头与正文分辨率/编码一致且音轨采样率相同，可 concat demuxer -c copy。"""
    intro_v = _probe_video_stream(intro_path)
    body_v = _probe_video_stream(body_path)
    if not intro_v or not body_v:
        return False
    if intro_v["codec"] != "h264" or intro_v != body_v:
        return False
    intro_rate = _probe_audio_sample_rate(intro_path)
    body_rate = _probe_audio_sample_rate(body_path)
    if intro_rate is None or body_rate is None:
        return False
    return intro_rate == body_rate


def prepend_intro(intro_path: Path, body_path: Path,
                  output_path: Path) -> Path:
    """片头接正文；参数兼容时 -c copy，否则 filter 重编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _can_concat_demuxer_copy(intro_path, body_path):
        return concat_clips([intro_path, body_path], output_path)

    body_rate = _probe_audio_sample_rate(body_path)
    intro_rate = _probe_audio_sample_rate(intro_path)
    intro_dur = probe_duration(intro_path)

    if body_rate is None:
        return concat_clips([intro_path, body_path], output_path)

    if intro_rate is not None:
        filter_complex = (
            "[0:v]setpts=PTS-STARTPTS[v0];"
            "[1:v]setpts=PTS-STARTPTS[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[vraw];"
            "[0:a]aformat=sample_rates={}:channel_layouts=mono,asetpts=PTS-STARTPTS[a0];"
            "[1:a]asetpts=PTS-STARTPTS[a1];"
            "[a0][a1]concat=n=2:v=0:a=1[aout]"
        ).format(body_rate)
    else:
        filter_complex = (
            "[0:v]setpts=PTS-STARTPTS[v0];"
            "[1:v]setpts=PTS-STARTPTS[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[vraw];"
            f"anullsrc=r={body_rate}:cl=mono,atrim=0:{intro_dur},asetpts=PTS-STARTPTS[asilent];"
            "[1:a]asetpts=PTS-STARTPTS[a1];"
            "[asilent][a1]concat=n=2:v=0:a=1[aout]"
        )

    if vaapi_enabled():
        filter_complex += f";[vraw]{_VAAPI_HWUPLOAD}[vout]"
    else:
        filter_complex = filter_complex.replace("[vraw]", "[vout]")

    _run_cmd(
        [
            *ffmpeg_cmd_start(),
            "-i",
            str(intro_path),
            "-i",
            str(body_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            *libx264_encode_args(),
            "-c:a",
            "aac",
            str(output_path),
        ],
    )
    return output_path


def _fmt_srt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_from_cues(cues: list) -> str:
    """按 TTS 逐句合成的真实时长生成 SRT。"""
    lines: list[str] = []
    cursor = 0.0
    for idx, cue in enumerate(cues, start=1):
        text = cue.text if hasattr(cue, "text") else cue["text"]
        duration = cue.duration_sec if hasattr(cue, "duration_sec") else cue["duration_sec"]
        start = cursor
        end = cursor + duration
        cursor = end
        lines.extend([str(idx), f"{_fmt_srt(start)} --> {_fmt_srt(end)}", text, ""])
    return "\n".join(lines)


def _fmt_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = sec % 60
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def _ass_escape_dialogue(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def escape_ffmpeg_filter_path(path: Path) -> str:
    """FFmpeg filter 参数中的绝对路径转义（libass subtitles / fontsdir）。"""
    normalized = path.resolve().as_posix().replace("\\", "/")
    if ":" in normalized[1:]:
        normalized = normalized.replace(":", r"\:")
    return normalized.replace("'", r"\'")


def build_ass_from_phrase_cues(
    cues: list[tuple[str, float]],
    *,
    width: int,
    height: int,
    font_name: str = "Source Han Sans CN",
) -> str:
    """生成可读 ASS 字幕（底居中白字黑边），按句级 duration 顺序排轴。"""
    font_size = max(28, int(height * 0.048))
    margin_v = max(24, int(height * 0.06))
    style = (
        f"Style: Default,{font_name},{font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,2,1,2,10,10,"
        f"{margin_v},1"
    )
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    cursor = 0.0
    for text, duration in cues:
        if duration <= 0 or not text.strip():
            continue
        start = cursor
        end = cursor + duration
        cursor = end
        body = _ass_escape_dialogue(text.strip())
        lines.append(
            f"Dialogue: 0,{_fmt_ass_time(start)},{_fmt_ass_time(end)},Default,,0,0,0,,{body}\n"
        )
    return "".join(lines)


# cSpell: enable
