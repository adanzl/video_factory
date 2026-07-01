"""业务层可预期异常（日志不必打堆栈）。"""

from __future__ import annotations


class JobStageFailureError(Exception):
    """流水线阶段预期失败：校验/质检不通过等，消息即原因。"""


def is_expected_job_failure(exc: BaseException) -> bool:
    return isinstance(exc, JobStageFailureError)
