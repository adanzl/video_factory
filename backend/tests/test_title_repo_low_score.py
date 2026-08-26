import pytest
from app.repositories import repo_job, repo_title
from app.services.job.job_mgr import job_mgr


def test_list_ids_below_score_excludes_enqueued_and_null(app_ctx):
    low = repo_title.insert_title(title="低分")
    assert low is not None
    repo_title.update_title(low["id"], score=60, status="rejected")
    boundary = repo_title.insert_title(title="边界")
    assert boundary is not None
    repo_title.update_title(boundary["id"], score=75, status="queued")
    high = repo_title.insert_title(title="高分")
    assert high is not None
    repo_title.update_title(high["id"], score=80, status="queued")
    repo_title.insert_title(title="未打分")
    enq = repo_title.insert_title(title="已入队低分")
    assert enq is not None
    repo_title.update_title(enq["id"], score=50, status="enqueued")

    ids = repo_title.list_ids_below_score(75)
    assert ids == [low["id"]]


def test_delete_job_unbinds_enqueued_title(app_ctx):
    job = repo_job.create_job("删任务解绑选题")
    title = repo_title.insert_title(title="已入队待解绑")
    assert title is not None
    repo_title.update_title(title["id"], status="enqueued", job_id=job["id"])

    job_mgr.delete_job(int(job["id"]))

    unbound = repo_title.get_title(title["id"])
    assert unbound["job_id"] is None
    assert unbound["status"] == "queued"
    with pytest.raises(KeyError):
        repo_job.get_job(int(job["id"]))
