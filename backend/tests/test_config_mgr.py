from __future__ import annotations

from pathlib import Path

import pytest

from app.services.config_mgr import parse_env_file, write_env_updates


def test_write_env_updates_preserves_comments(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# LLM\nMOCK_MODE=true\n# TTS\nCOSYVOICE_VOICE=old-voice\n",
        encoding="utf-8",
    )

    updated = write_env_updates(
        {"MOCK_MODE": "false", "TTS_VOICE": "new-voice"},
        env_path=env_path,
    )

    assert set(updated) == {"MOCK_MODE", "TTS_VOICE"}
    text = env_path.read_text(encoding="utf-8")
    assert "# LLM" in text
    assert "MOCK_MODE=false" in text
    assert "COSYVOICE_VOICE=new-voice" in text
    assert parse_env_file(env_path)["COSYVOICE_VOICE"] == "new-voice"
