from app.exceptions import JobStageFailureError, is_expected_job_failure
from app.services.llm.llm_agnes import (
    AgnesContentPolicyError,
    AgnesI2VError,
    AgnesQuotaExceeded,
)
from worker.stages.standard.script import ScriptValidationError


def test_is_expected_job_failure_script_validation():
    assert is_expected_job_failure(ScriptValidationError("narration too short"))


def test_is_expected_job_failure_quality_major():
    assert is_expected_job_failure(
        JobStageFailureError("quality[copy] major, rollback to script")
    )


def test_is_expected_job_failure_agnes_quota():
    assert is_expected_job_failure(AgnesQuotaExceeded("429 rate_limit_exceeded"))


def test_is_expected_job_failure_agnes_i2v():
    assert is_expected_job_failure(
        AgnesI2VError("agnes request failed after 2 retries: https://apihub.agnes-ai.cn/v1/videos")
    )


def test_is_expected_job_failure_agnes_image():
    from app.services.llm.llm_agnes import AgnesImageError

    assert is_expected_job_failure(
        AgnesImageError(
            "agnes request failed (after 1 retries; "
            "url=https://apihub.agnes-ai.cn/v1/images/generations; "
            "last_exc=Read timed out)"
        )
    )


def test_is_expected_job_failure_agnes_content_policy():
    assert is_expected_job_failure(
        AgnesContentPolicyError(
            "agnes api 400: {'error': {'code': 'content_policy_violation'}}"
        )
    )


def test_is_expected_job_failure_daily_script_closeup():
    assert is_expected_job_failure(
        JobStageFailureError(
            "分镜特写校验失败: scene_id=10 为特写但含 3 句对白（特写镜最多 2 句）"
        )
    )


def test_is_expected_job_failure_missing_segment_image():
    assert is_expected_job_failure(
        JobStageFailureError(
            "segment 1 缺少 image_path，请先执行 segment/images"
        )
    )


def test_is_expected_job_failure_unexpected():
    assert not is_expected_job_failure(RuntimeError("network down"))
