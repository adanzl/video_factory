from app.exceptions import JobStageFailureError, is_expected_job_failure
from worker.stages.standard.script import ScriptValidationError


def test_is_expected_job_failure_script_validation():
    assert is_expected_job_failure(ScriptValidationError("narration too short"))


def test_is_expected_job_failure_quality_major():
    assert is_expected_job_failure(
        JobStageFailureError("quality[copy] major, rollback to script")
    )


def test_is_expected_job_failure_unexpected():
    assert not is_expected_job_failure(RuntimeError("network down"))
