"""Agnes 出图阻塞 HTTP 期间响应 job 中止。"""

from __future__ import annotations

import gevent
import pytest

from app.services.segment.image.image_agnes import AgnesImageProvider
from app.utils.job_cancel import JobCancelledError, job_cancel


def test_agnes_request_cancellable_stops_on_job_abort() -> None:
    job_id = 9102
    job_cancel.clear(job_id)
    provider = AgnesImageProvider()
    provider._active_job_id = job_id  # noqa: SLF001
    started = gevent.event.Event()  # type: ignore[attr-defined]

    def slow_request(*_args, **_kwargs):
        started.set()
        gevent.sleep(2.0)
        raise AssertionError("should not complete after abort")

    def abort_after_start() -> None:
        started.wait()
        gevent.sleep(0.05)
        job_cancel.request(job_id)

    gevent.spawn(abort_after_start)
    try:
        with pytest.raises(JobCancelledError):
            provider._run_blocking_cancellable(slow_request)  # noqa: SLF001
    finally:
        job_cancel.clear(job_id)
        provider._active_job_id = None  # noqa: SLF001

    assert started.is_set()
