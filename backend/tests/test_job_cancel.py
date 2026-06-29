"""job 中止信号测试。"""

from __future__ import annotations

import pytest

from app.utils.job_cancel import JobCancelledError, job_cancel, raise_if_job_cancelled


def test_request_and_clear():
    job_cancel.clear(99)
    assert not job_cancel.is_cancelled(99)
    job_cancel.request(99)
    assert job_cancel.is_cancelled(99)
    job_cancel.clear(99)
    assert not job_cancel.is_cancelled(99)


def test_raise_if_cancelled():
    job_cancel.clear(1)
    job_cancel.raise_if_cancelled(1)
    job_cancel.request(1)
    with pytest.raises(JobCancelledError):
        job_cancel.raise_if_cancelled(1)
    job_cancel.clear(1)


def test_raise_if_job_cancelled_from_job_dict():
    job_cancel.clear(5)
    raise_if_job_cancelled({"id": 5})
    job_cancel.request(5)
    with pytest.raises(JobCancelledError):
        raise_if_job_cancelled({"id": 5})
    raise_if_job_cancelled(None)
    job_cancel.clear(5)


def test_generate_storyboard_aborted_after_llm_no_done_log(monkeypatch, caplog):
    from app.services.llm.llm_deepseek import DeepSeekClient

    job = {"id": 42, "pipeline": "standard", "content_style": "science_child"}
    job_cancel.clear(42)
    text = "字" * 900

    def fake_chat(*_args, **_kwargs):
        job_cancel.request(42)
        return (
            {
                "title": "测试",
                "visual_style": "写实",
                "segments": [
                    {
                        "segment_index": 1,
                        "text": text,
                        "visual_brief": "画面" * 20,
                        "visual_mode": "static_motion",
                    }
                ],
                "narration": text,
                "word_count": len(text),
            },
            "stop",
        )

    monkeypatch.setattr(DeepSeekClient, "_chat_json", fake_chat)
    client = DeepSeekClient()
    with pytest.raises(JobCancelledError):
        client.generate_storyboard("测试", narration_target_words=800, job=job)

    assert not any("storyboard done" in record.message for record in caplog.records)
    job_cancel.clear(42)
