from app.repositories import repo_title


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
