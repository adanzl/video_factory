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


@pytest.mark.parametrize('stage', ['main', 'limbs'])
def test_image_verification_does_not_swallow_cancellation(tmp_path, stage):
    from unittest.mock import patch
    from PIL import Image
    from app.config import get_settings
    from app.services.llm.llm_agnes import AgnesApiKey

    provider = AgnesImageProvider()
    output = tmp_path / 'frame.png'
    Image.new('RGB', (32, 32), 'white').save(output)
    keys = [AgnesApiKey('cn_free', 'first'), AgnesApiKey('cn_paid', 'second')]
    with (
        patch('app.services.segment.image.image_agnes.agnes_api_keys', return_value=keys),
        patch.object(provider, '_run_blocking_cancellable', side_effect=JobCancelledError('cancel')) as request,
        patch.object(provider, '_sleep_cancellable') as sleep,
        pytest.raises(JobCancelledError),
    ):
        if stage == 'main':
            provider._verify_image('场景', output)
        else:
            provider._ask_hardfail_vl(get_settings(), keys, 'test-image', '检查', 'test')
    request.assert_called_once()
    sleep.assert_not_called()
