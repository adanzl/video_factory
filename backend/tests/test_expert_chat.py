"""专家对话：组消息、续聊、解析 LLM 响应。不访问网络。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.expert_chat import (
    ExpertError,
    ask,
    build_messages,
    compose_user_message,
    excerpt_file,
    extract_answer,
    history_of,
    latest_conversation_id,
    load_session,
    save_session,
    trim_history,
)


def test_build_messages_keeps_history_and_system() -> None:
    history = [
        {"role": "user", "content": "上一轮"},
        {"role": "assistant", "content": "保留 A，删掉 B"},
    ]
    messages = build_messages(history, "阈值呢")
    assert messages[0]["role"] == "system"
    assert "不要复述" in messages[0]["content"]
    assert "_perbeat_check" not in messages[0]["content"]
    assert "expand.py" not in messages[0]["content"]
    assert messages[1]["content"] == "上一轮"
    assert messages[-1] == {"role": "user", "content": "阈值呢"}


def test_compose_user_message_attaches_file(tmp_path: Path) -> None:
    source = tmp_path / "expand.py"
    source.write_text("def _perbeat_check():\n    return []\n", encoding="utf-8")
    text = compose_user_message("看这条机检", [source])
    assert "看这条机检" in text
    assert "_perbeat_check" in text
    assert "【文件】" in text


def test_compose_user_message_rejects_empty() -> None:
    with pytest.raises(ExpertError):
        compose_user_message("   ", [])


def test_compose_user_message_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExpertError, match="文件不存在"):
        compose_user_message("看这个", [tmp_path / "nope.py"])


def test_compose_user_message_truncates_long_question() -> None:
    text = compose_user_message("字" * 30000, [])
    assert "问题超长" in text
    assert len(text) < 30000


def test_excerpt_file_numbers_lines() -> None:
    body = excerpt_file("a\nb\nc\n")
    assert body.splitlines()[0].strip().endswith("| a")
    assert body.splitlines()[2].strip().endswith("| c")


def test_excerpt_file_marks_omitted_range() -> None:
    body = excerpt_file("\n".join(f"line{i}" for i in range(1, 1001)))
    assert "省略第" in body
    assert "line1" in body.splitlines()[0]
    assert "line1000" in body.splitlines()[-1]


def test_trim_history_drops_oldest() -> None:
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(30)
    ]
    kept = trim_history(messages)
    assert len(kept) <= 16
    assert kept[-1]["content"] == "29"


def test_trim_history_never_starts_with_assistant() -> None:
    messages = [{"role": "user", "content": "问"}] + [
        {"role": "assistant" if i % 2 == 0 else "user", "content": str(i)}
        for i in range(20)
    ]
    kept = trim_history(messages, max_messages=5)
    assert kept[0]["role"] == "user"


def test_trim_history_respects_char_budget() -> None:
    messages = [{"role": "user", "content": "x" * 5000} for _ in range(20)]
    kept = trim_history(messages, max_messages=100, max_chars=12000)
    assert sum(len(item["content"]) for item in kept) <= 12000


def test_session_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "expert_sessions.json"
    save_session(
        path,
        {
            "conversations": {
                "abc": {
                    "messages": [
                        {"role": "user", "content": "问"},
                        {"role": "assistant", "content": "答"},
                    ]
                }
            }
        },
    )
    loaded = history_of(load_session(path), "abc")
    assert loaded[1]["content"] == "答"
    assert history_of(load_session(path), "missing") == []


def test_load_session_rejects_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "expert_sessions.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ExpertError, match="合法 JSON"):
        load_session(path)


def test_latest_conversation_id_prefers_newest_stamp() -> None:
    data: dict[str, Any] = {
        "conversations": {
            "old": {"messages": [], "updated_at": "2026-01-01T00:00:00+00:00"},
            "new": {"messages": [], "updated_at": "2026-02-01T00:00:00+00:00"},
        }
    }
    assert latest_conversation_id(data) == "new"
    assert latest_conversation_id({"conversations": {}}) is None


def test_extract_answer() -> None:
    answer, finish = extract_answer(
        {"choices": [{"finish_reason": "stop", "message": {"content": " 保留 A "}}]},
        max_tokens=1024,
    )
    assert answer == "保留 A"
    assert finish == "stop"


def test_extract_answer_rejects_empty() -> None:
    with pytest.raises(ExpertError):
        extract_answer(
            {"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
            max_tokens=1024,
        )


def test_extract_answer_explains_length_budget() -> None:
    with pytest.raises(ExpertError, match="--max-tokens"):
        extract_answer(
            {"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
            max_tokens=8192,
        )


def _stub_complete(monkeypatch, answer: str = "答", finish: str = "stop") -> list[list[dict[str, str]]]:
    """替掉 complete，记录每次实际发出的 messages。"""
    import scripts.expert_chat as mod

    calls: list[list[dict[str, str]]] = []

    def fake_complete(messages, *, model=None, max_tokens=None, thinking=None):  # noqa: ANN001
        _ = model, max_tokens, thinking
        calls.append(messages)
        return answer, finish, "test-model", 1024

    monkeypatch.setattr(mod, "complete", fake_complete)
    return calls


def test_ask_new_conversation_persists(tmp_path: Path, monkeypatch) -> None:
    calls = _stub_complete(monkeypatch)
    session = tmp_path / "expert_sessions.json"
    result = ask("第一问", session_path=session)
    assert result["answer"] == "答"
    assert len(calls) == 1
    stored = history_of(load_session(session), result["conversation_id"])
    assert [item["role"] for item in stored] == ["user", "assistant"]
    payload = load_session(session)["conversations"][result["conversation_id"]]
    assert payload["updated_at"]
    assert payload["turns"] == 1


def test_ask_continue_sends_history(tmp_path: Path, monkeypatch) -> None:
    calls = _stub_complete(monkeypatch)
    session = tmp_path / "expert_sessions.json"
    first = ask("第一问", session_path=session)
    ask("第二问", conversation_id=first["conversation_id"], session_path=session)
    sent = calls[-1]
    assert sent[0]["role"] == "system"
    assert sent[1]["content"] == "第一问"
    assert sent[2]["content"] == "答"
    assert sent[-1]["content"] == "第二问"


def test_ask_unknown_conversation_id_raises(tmp_path: Path, monkeypatch) -> None:
    _stub_complete(monkeypatch)
    with pytest.raises(ExpertError, match="没有记录"):
        ask(
            "续聊",
            conversation_id="does-not-exist",
            session_path=tmp_path / "expert_sessions.json",
        )


def test_ask_new_and_conversation_id_conflict(tmp_path: Path, monkeypatch) -> None:
    _stub_complete(monkeypatch)
    with pytest.raises(ExpertError, match="不能同时用"):
        ask(
            "冲突",
            conversation_id="abc",
            new_conversation=True,
            session_path=tmp_path / "expert_sessions.json",
        )


def test_ask_does_not_persist_empty_answer(tmp_path: Path, monkeypatch) -> None:
    import scripts.expert_chat as mod

    def fake_complete(messages, *, model=None, max_tokens=None, thinking=None):  # noqa: ANN001
        _ = messages, model, max_tokens, thinking
        raise ExpertError("思考 token 已吃满")

    monkeypatch.setattr(mod, "complete", fake_complete)
    session = tmp_path / "expert_sessions.json"
    with pytest.raises(ExpertError):
        ask("空答", session_path=session)
    assert load_session(session)["conversations"] == {}


def test_ask_dry_run_skips_complete(tmp_path: Path, monkeypatch) -> None:
    calls = _stub_complete(monkeypatch)
    result = ask(
        "只看提示词",
        session_path=tmp_path / "expert_sessions.json",
        dry_run=True,
    )
    assert calls == []
    assert result["dry_run"] is True
    assert result["messages"][-1]["content"] == "只看提示词"
