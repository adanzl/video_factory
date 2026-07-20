from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.config_mgr import (
    mask_secret,
    parse_env_file,
    write_env_updates,
)


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("ab", "••"),
        ("abcd", "••••"),
        ("abcdefgh", "••••efgh"),
        ("sk-example-key-Asgp", "•••••••••••••••Asgp"),
    ],
)
def test_mask_secret(raw: str, expected: str):
    assert mask_secret(raw) == expected


def test_field_payload_masks_secret(monkeypatch: pytest.MonkeyPatch):
    from app.services import config_mgr as mgr

    field = next(
        item
        for group in mgr.CONFIG_GROUPS
        for item in group.items
        if item.attr == "deepseek_api_key"
    )
    monkeypatch.setattr(mgr.config, "deepseek_api_key", "sk-real-secret-value-1234")
    monkeypatch.setattr(mgr, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(mgr, "env_file_path", lambda: Path("/tmp/fake.env"))

    payload = mgr._field_payload(field)
    assert payload["type"] == "secret"
    assert payload["configured"] is True
    assert payload["value"] == mask_secret("sk-real-secret-value-1234")
    assert "sk-real" not in payload["value"]
    assert payload["value"].endswith("1234")


def test_apply_config_updates_skips_masked_secret(monkeypatch: pytest.MonkeyPatch):
    from app.services import config_mgr as mgr

    real = "sk-keep-this-secret-9999"
    monkeypatch.setattr(mgr.config, "deepseek_api_key", real)
    write_calls: list[dict] = []

    def fake_write(updates: dict[str, str], **_kwargs):
        write_calls.append(updates)
        return list(updates)

    monkeypatch.setattr(mgr, "write_env_updates", fake_write)
    monkeypatch.setattr(mgr.config, "reload", MagicMock())
    monkeypatch.setattr(mgr, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(mgr, "env_file_path", lambda: Path("/tmp/fake.env"))

    result = mgr.apply_config_updates(
        {"deepseek_api_key": mask_secret(real)}
    )
    assert result["count"] == 0
    assert result["skipped"] == ["deepseek_api_key"]
    assert write_calls == []
