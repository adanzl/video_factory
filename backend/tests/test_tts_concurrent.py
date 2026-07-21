"""TTS 分镜并发合成测试（mock WebSocket，不调用真实 API）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import gevent

from app.services.tts.tts_ali import AliTTSClient, _SynthesisResult


def test_tts_segment_concurrency_respects_max_workers(tmp_path: Path, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "tts_max_workers", 3)

    active = 0
    peak = 0

    def fake_run_tts_task(text: str, **_kwargs) -> _SynthesisResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        gevent.sleep(0.15)
        active -= 1
        return _SynthesisResult(
            audio=b"\xff\xfb", words=[], usage={"characters": len(text)}
        )

    segments = [
        {"segment_index": i, "text": f"分镜{i}测试文案。"}
        for i in range(1, 7)
    ]

    with patch("app.services.tts.tts_ali._run_tts_task", side_effect=fake_run_tts_task):
        with patch("app.services.tts.tts_ali.probe_duration", return_value=1.0):
            with patch("app.services.tts.tts_ali.concat_clips"):
                with patch("app.services.tts.tts_ali.run_ffmpeg"):
                    client = AliTTSClient()
                    result = client.synthesize("", segments, tmp_path / "audio")

    assert len(result.segment_durations) == 6
    assert peak == 3
