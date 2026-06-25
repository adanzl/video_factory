from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.media.ffmpeg_utils import (
    scale_pad_filter,
    vf_for_encode,
)

_FFMPEG = shutil.which("ffmpeg")


def test_scale_pad_filter_uses_pad_color_option_not_color_filter() -> None:
    vf = scale_pad_filter(width=1920, height=1080, fps=25)
    assert ":color=black" in vf
    # 逗号会把 color 拆成独立源滤镜，导致 simple filtergraph 双输出。
    assert ",color=black" not in vf


def test_vf_for_encode_vaapi_appends_hwupload() -> None:
    base = scale_pad_filter(width=1280, height=720)
    with patch("app.services.media.ffmpeg_utils.vaapi_enabled", return_value=True):
        vf = vf_for_encode(base)
    assert vf.endswith("format=nv12,hwupload")
    assert vf.count("format=") == 2  # yuv420p + nv12


@pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg not installed")
def test_scale_pad_filter_runs_as_single_output_graph(tmp_path: Path) -> None:
    vf = vf_for_encode(scale_pad_filter(width=640, height=360, fps=25))
    out = subprocess.run(
        [
            _FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.1:size=320x240:rate=30",
            "-vf",
            vf,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr


@pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg not installed")
def test_scale_pad_filter_vaapi_chain_is_single_output_graph() -> None:
    """VAAPI 路径在 Linux 上追加 hwupload；滤镜链须仍为单输入单输出。"""
    base = scale_pad_filter(width=640, height=360, fps=25)
    with patch("app.services.media.ffmpeg_utils.vaapi_enabled", return_value=True):
        vf = vf_for_encode(base)
    out = subprocess.run(
        [
            _FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.1:size=320x240:rate=30",
            "-vf",
            vf,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # Windows 无 VAAPI 设备时 hwupload 可能失败；至少不能是 simple graph 双输出。
    assert "had 1 input(s) and 2 output(s)" not in out.stderr
    if out.returncode != 0:
        assert "hwupload" in out.stderr or "vaapi" in out.stderr.lower()
