"""JobContext 测试。"""

from worker.context import JobContext


def test_job_context_reads_supplementary_info_from_job_info():
    ctx = JobContext.from_job(
        {
            "id": 1,
            "title": "测试标题",
            "info": {"script": {"supplementary_info": "委内瑞拉强震引发海啸担忧"}},
        }
    )
    assert ctx.script_supplementary_info == "委内瑞拉强震引发海啸担忧"
