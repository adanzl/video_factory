from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.utils.async_util import run_subprocess_safe

# cSpell: disable

_FFMPEG_TIMEOUT = 600.0
_PROBE_TIMEOUT = 60.0


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


def concat_clips(clips: list[Path], output_path: Path) -> Path:
    """拼接同编码片段；音频 MP3 多条时重编码，避免 -c copy 接缝咔嗒。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not clips:
        raise ValueError("no clips to concat")
    if len(clips) == 1:
        _run_cmd(
            ["ffmpeg", "-y", "-hide_banner", "-i", str(clips[0]), "-c", "copy", str(output_path)],
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
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(pattern),
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
    ]
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
        f"scale={width}:{height}:flags=lanczos,format=yuv420p"  # cSpell: disable-line
        if need_scale
        else "format=yuv420p"
    )

    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
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
) -> Path:
    """合并画面与配音，以音频时长为准，不拉伸/压缩音频。"""
    _ = subtitle_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dur = probe_duration(audio_path)
    video_dur = probe_duration(video_path)
    drift = video_dur - audio_dur

    if abs(drift) <= 0.08:
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
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[0:v]{vf}[vout]",
            "-map",
            "[vout]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-crf",
            "18",
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


def prepend_intro(intro_path: Path, body_path: Path,
                  output_path: Path) -> Path:
    """片头接正文；片头有音轨则保留，否则片头段静音。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body_rate = _probe_audio_sample_rate(body_path)
    intro_rate = _probe_audio_sample_rate(intro_path)
    intro_dur = probe_duration(intro_path)

    if body_rate is None:
        return concat_clips([intro_path, body_path], output_path)

    if intro_rate is not None:
        filter_complex = (
            "[0:v]setpts=PTS-STARTPTS[v0];"
            "[1:v]setpts=PTS-STARTPTS[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[vout];"
            "[0:a]aformat=sample_rates={}:channel_layouts=mono,asetpts=PTS-STARTPTS[a0];"
            "[1:a]asetpts=PTS-STARTPTS[a1];"
            "[a0][a1]concat=n=2:v=0:a=1[aout]"
        ).format(body_rate)
    else:
        filter_complex = (
            "[0:v]setpts=PTS-STARTPTS[v0];"
            "[1:v]setpts=PTS-STARTPTS[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[vout];"
            f"anullsrc=r={body_rate}:cl=mono,atrim=0:{intro_dur},asetpts=PTS-STARTPTS[asilent];"
            "[1:a]asetpts=PTS-STARTPTS[a1];"
            "[asilent][a1]concat=n=2:v=0:a=1[aout]"
        )

    _run_cmd(
        [
            "ffmpeg",
            "-y",
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
            "-c:v",
            "libx264",
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


# cSpell: enable
