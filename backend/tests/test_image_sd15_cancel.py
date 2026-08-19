"""SD15 出图阻塞期间响应 job 中止。"""

from __future__ import annotations

import time

import pytest

from app.services.segment.image.image_sd15 import Sd15ImageProvider
from app.utils.job_cancel import JobCancelledError, job_cancel


def test_sd15_run_blocking_cancellable_stops_on_job_abort() -> None:
    job_id = 9101
    job_cancel.clear(job_id)
    provider = Sd15ImageProvider()
    provider._active_job_id = job_id  # noqa: SLF001
    job_cancel.request(job_id)

    try:
        with pytest.raises(JobCancelledError):
            provider._run_blocking_cancellable(lambda: time.sleep(0.5))  # noqa: SLF001
    finally:
        job_cancel.clear(job_id)
        provider._active_job_id = None  # noqa: SLF001
