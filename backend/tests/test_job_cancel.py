"""job 中止信号测试。"""

from __future__ import annotations

import pytest

from app.services.job.job_cancel import JobCancelledError, job_cancel


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
