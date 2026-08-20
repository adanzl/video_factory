from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from app.config import config
from app.repositories import repo_daily_story
from app.services.publish.bilibili.schedule import (
    PUBLISH_TZ,
    parse_publish_schedule,
    resolve_next_publish_dtime,
    resolve_publish_dtime_from_job,
)
from app.services.publish.bilibili.tags import (
    CHAT_FIXED_TAGS,
    build_chat_tags,
    build_publish_tags,
    normalize_tags,
)
from app.services.publish.bilibili.uploader import BiliUploader
from app.services.publish.publish_mgr import PublishMgr
from app.utils.job_info import merge_job_info, parse_job_info


def test_normalize_tags() -> None:
    assert normalize_tags(["#亲子", "亲子", "日常故事", "x" * 30]) == [
        "亲子",
        "日常故事",
        "x" * 20,
    ]
    assert normalize_tags("nope") == []


def test_build_chat_tags_with_story_key(app_ctx, monkeypatch) -> None:
    monkeypatch.setattr(config, "bili_activity_tag", "闪闪发光的家庭日")
    story_id = repo_daily_story.insert_story(
        theme="test",
        story={"scene_title": "鞋带系成死疙瘩", "key": "鞋带系一起", "dialogue": [{"speaker": "a", "line": "b"}]},
    )
    job = {
        "pipeline": "chat",
        "title": "鞋带系成死疙瘩",
        "info": merge_job_info(None, daily_story_id=story_id),
    }
    tags = build_chat_tags(job)
    assert tags[:7] == list(CHAT_FIXED_TAGS)
    assert "鞋带系一起" in tags
    assert "闪闪发光的家庭日" not in tags
    assert len(tags) == 8


def test_describe_publish_config_chat() -> None:
    from app.services.publish.bilibili.publish_config import describe_publish_config
    from app.services.publish.bilibili.tags import CHAT_FIXED_TAGS

    info = describe_publish_config("chat")
    assert info["pipeline"] == "chat"
    assert info["partition"]["display"] == "亲子"
    assert info["neutral_mark"] == "含虚构演绎内容"
    assert info["topic"]["name"] == "闪闪发光的家庭日"
    assert info["fixed_tags"] == list(CHAT_FIXED_TAGS)


def test_describe_publish_config_standard() -> None:
    from app.services.publish.bilibili.publish_config import describe_publish_config

    info = describe_publish_config("standard")
    assert info["partition"]["display"] == "科学科普"
    assert info["neutral_mark"] is None
    assert info["topic"] is None
    assert info["fixed_tags"] is None


def test_bili_config_route(app_ctx) -> None:
    client = app_ctx.test_client()
    resp = client.get("/v_factory/api/publish/bili/config?pipeline=chat")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["partition"]["display"] == "亲子"
    assert data["topic"]["name"]
    assert data["fixed_tags"]


def test_build_fan_dynamic_chat() -> None:
    from app.services.publish.bilibili.dynamic import build_fan_dynamic

    assert build_fan_dynamic("鞋带系成死疙瘩", pipeline="chat") == (
        "鞋带系成死疙瘩｜姐弟日常小剧场，昭昭灿灿又整活了。"
    )
    assert build_fan_dynamic("", pipeline="chat") == (
        "姐弟日常小剧场更新啦，昭昭灿灿的日常对话。"
    )


def test_build_publish_tags_uses_job_title_for_chat(app_ctx, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    monkeypatch.setattr(config, "bili_activity_tag", "闪闪发光的家庭日")
    monkeypatch.setattr(config, "bili_human_type2_chat", 1025)
    story_id = repo_daily_story.insert_story(
        theme="test",
        story={"scene_title": "鞋带系成死疙瘩", "key": "鞋带系一起", "dialogue": [{"speaker": "a", "line": "b"}]},
    )
    video = tmp_path / "final.mp4"
    video.write_bytes(b"mp4")
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"jpg")
    captured: dict = {}

    def fake_publish(**kwargs):
        captured.update(kwargs)
        return {
            "platform": "bilibili",
            "status": "success",
            "bvid": "BV1test",
            "tid": kwargs["tid"],
            "message": "upload ok",
        }

    def fake_topic(http, keywords, **kwargs):
        assert keywords == "闪闪发光的家庭日"
        return {"topic_id": 1299875, "mission_id": 4067655, "topic_name": keywords}

    monkeypatch.setattr(BiliUploader, "publish", lambda self, **kwargs: fake_publish(**kwargs))
    monkeypatch.setattr(
        "app.services.publish.bilibili.tags.resolve_activity_topic",
        fake_topic,
    )
    mgr = PublishMgr()
    monkeypatch.setattr(mgr, "require_session", lambda: {"ok": True})
    result = mgr.publish_for_job(
        {
            "skip_publish": False,
            "pipeline": "chat",
            "title": "job 原标题",
            "final_path": {"path": str(video)},
            "cover_path": str(cover),
            "info": merge_job_info(None, daily_story_id=story_id),
            "script_json": {
                "title": "脚本标题",
                "video_description": "简介",
            },
        }
    )
    assert result["bvid"] == "BV1test"
    assert captured["title"] == "job 原标题"
    assert "闪闪发光的家庭日" not in captured["tags"]
    assert "鞋带系一起" in captured["tags"]
    assert captured["human_type2"] == 1025
    assert captured["neutral_mark"] == "含虚构演绎内容"
    assert captured["topic_id"] == 1299875
    assert captured["mission_id"] == 4067655
    assert "又整活了" in captured["dynamic"]


def test_publish_for_job_skip_publish(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    result = PublishMgr().publish_for_job({"skip_publish": True, "title": "t"})
    assert result["status"] == "skipped"
    assert "skip_publish" in result["message"]


def test_publish_for_job_skip_publish_manual_bypass(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    captured: dict = {}

    def fake_publish(self, **kwargs):
        captured.update(kwargs)
        return {"platform": "bilibili", "status": "success", "bvid": "BV1manual"}

    monkeypatch.setattr(PublishMgr, "publish", fake_publish)
    job = {
        "skip_publish": True,
        "title": "手动投稿",
        "pipeline": "chat",
        "final_path": "/tmp/final.mp4",
        "cover_path": "/tmp/cover.jpg",
        "script_json": {"video_description": "desc"},
    }
    result = PublishMgr().publish_for_job(job, manual=True)
    assert result["bvid"] == "BV1manual"
    assert captured["title"] == "手动投稿"


def test_publish_for_job_mock_mode(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", True)
    result = PublishMgr().publish_for_job({"skip_publish": False, "title": "t"})
    assert result["status"] == "skipped"
    assert "MOCK_MODE" in result["message"]


def test_publish_for_job_already_published(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    job = {
        "skip_publish": False,
        "info": {
            "publish_result": {
                "status": "success",
                "bvid": "BV1xx",
                "url": "https://www.bilibili.com/video/BV1xx",
            }
        },
    }
    result = PublishMgr().publish_for_job(job)
    assert result["bvid"] == "BV1xx"
    assert result["message"] == "already published"


def test_publish_for_job_already_published_manual_bypass(monkeypatch) -> None:
    monkeypatch.setattr(config, "mock_mode", False)
    captured: dict = {}

    def fake_publish(self, **kwargs):
        captured.update(kwargs)
        return {"platform": "bilibili", "status": "success", "bvid": "BV1new"}

    monkeypatch.setattr(PublishMgr, "publish", fake_publish)
    job = {
        "skip_publish": False,
        "title": "重投",
        "pipeline": "chat",
        "final_path": "/tmp/final.mp4",
        "cover_path": "/tmp/cover.jpg",
        "script_json": {"video_description": "desc"},
        "info": {
            "publish_result": {
                "status": "success",
                "bvid": "BV1old",
                "url": "https://www.bilibili.com/video/BV1old",
            }
        },
    }
    result = PublishMgr().publish_for_job(job, manual=True)
    assert result["bvid"] == "BV1new"
    assert captured["title"] == "重投"


def test_save_job_result_sets_publish(app_ctx) -> None:
    from app.repositories import repo_job

    job = repo_job.create_job("to publish", pipeline="chat", skip_publish=False)
    saved = PublishMgr().save_job_result(
        job,
        {
            "platform": "bilibili",
            "status": "success",
            "bvid": "BV1ok",
            "message": "upload ok",
        },
    )
    assert saved["publish"] is True
    info = parse_job_info(saved["info"])
    assert info["publish_result"]["bvid"] == "BV1ok"


def test_resolve_next_publish_dtime_today() -> None:
    now = datetime(2026, 8, 19, 15, 0, tzinfo=PUBLISH_TZ)
    dtime, planned = resolve_next_publish_dtime("18:30", now=now)
    assert planned.hour == 18
    assert planned.minute == 30
    assert planned.day == 19
    assert dtime == int(planned.timestamp())


def test_resolve_next_publish_dtime_tomorrow() -> None:
    now = datetime(2026, 8, 19, 20, 0, tzinfo=PUBLISH_TZ)
    dtime, planned = resolve_next_publish_dtime("18:30", now=now)
    assert planned.day == 20
    assert dtime == int(planned.timestamp())


def test_resolve_publish_dtime_from_job(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 19, 8, 0, tzinfo=PUBLISH_TZ)
    monkeypatch.setattr(
        "app.services.publish.bilibili.schedule.datetime",
        type(
            "FixedDatetime",
            (),
            {"now": staticmethod(lambda tz=None: fixed_now)},
        ),
    )
    job = {
        "info": merge_job_info(None, publish_schedule={"enabled": True, "time": "09:00"}),
    }
    dtime, planned = resolve_publish_dtime_from_job(job)
    assert dtime is not None
    assert planned is not None
    assert planned.hour == 9


def test_parse_publish_schedule_disabled() -> None:
    assert parse_publish_schedule({"enabled": False, "time": "09:00"}) == {
        "enabled": False,
        "time": "09:00",
    }


def test_uploader_submit_parses_bvid(tmp_path, monkeypatch) -> None:
    session = MagicMock()
    session.csrf.return_value = "csrf"
    http = MagicMock()
    session.http.return_value = http
    video = tmp_path / "a.mp4"
    video.write_bytes(b"0123456789")

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "OK": 1,
            "endpoint": "//upos.example.com",
            "upos_uri": "upos://ugc/abc.mp4",
            "auth": "auth",
            "biz_id": 9,
            "chunk_size": 1024,
        }
        return resp

    submit_payload: dict = {}

    def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "add/v3" in str(url):
            submit_payload.update(kwargs.get("json") or {})
            resp.json.return_value = {
                "code": 0,
                "data": {"bvid": "BV1abc", "aid": 1},
            }
        else:
            resp.json.return_value = {"upload_id": "uid"}
        return resp

    def fake_put(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    http.get.side_effect = fake_get
    http.post.side_effect = fake_post
    http.put.side_effect = fake_put
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"jpg")

    def cover_post(url, **kwargs):
        if "cover" in str(url):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"code": 0, "data": {"url": "http://i0.hdslb.com/c.jpg"}}
            return resp
        return fake_post(url, **kwargs)

    http.post.side_effect = cover_post
    result = BiliUploader(session).publish(
        title="t",
        description="d",
        tags=["tag"],
        video_path=video,
        cover_path=cover,
        tid=201,
        dtime=123456,
        human_type2=1025,
        neutral_mark="含虚构演绎内容",
        topic_id=1299875,
        mission_id=4067655,
    )
    assert result["status"] == "success"
    assert result["bvid"] == "BV1abc"
    assert result["tid"] == 201
    assert submit_payload.get("dtime") == 123456
    assert submit_payload.get("human_type2") == 1025
    assert submit_payload.get("neutral_mark") == "含虚构演绎内容"
    assert submit_payload.get("topic_id") == 1299875
    assert submit_payload.get("mission_id") == 4067655
    assert submit_payload.get("topic_detail", {}).get("from_topic_id") == 1299875
