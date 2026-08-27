"""F 类互呛加码 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    parse_story_type_code,
    story_type_tag,
)
from app.services.daily_story.story_types.f.validate import append_f_body_errors


def test_f_registered():
    assert "F" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["F"].label == "互呛加码"
    assert story_type_tag("F") == "F类互呛加码"


def test_f_validate_passes_m3_external_interrupt():
    story = {
        "story_type": "F",
        "punchline_explain": "F类：互怼升级发现偷拍后尴尬收束",
        "dialogue": [
            {"speaker": "灿灿", "line": "你这样说我还觉得你很讨厌了呢！"},
            {"speaker": "昭昭", "line": "那你还很讨厌了呢！"},
            {"speaker": "灿灿", "line": "你再说一遍试试啊！"},
            {"speaker": "昭昭", "line": "试试就试试嘛！"},
            {"speaker": "灿灿", "line": "你再说一遍！"},
            {"speaker": "昭昭", "line": "你才讨厌！"},
            {"speaker": "灿灿", "line": "吼什么吼吧！"},
            {"speaker": "昭昭", "line": "那你还吼了呢！"},
            {"speaker": "灿灿", "line": "啊啊啊！"},
            {"speaker": "昭昭", "line": "啊什么啊！"},
            {"speaker": "灿灿", "line": "你再说我打你呀！"},
            {"speaker": "昭昭", "line": "你敢！"},
            {"speaker": "灿灿", "line": "姐，有人拍我们呢！"},
            {"speaker": "昭昭", "line": "啊？快闭嘴！"},
            {"speaker": "灿灿", "line": "闹着玩呢！"},
            {"speaker": "昭昭", "line": "茄子！"},
            {"speaker": "灿灿", "line": "快走啦！"},
        ],
    }
    errors: list[str] = []
    append_f_body_errors(story, errors)
    assert errors == []


def test_f_validate_rejects_b_alliance_tail():
    story = {
        "story_type": "F",
        "punchline_explain": "F类互呛加码",
        "dialogue": [
            {"speaker": "灿灿", "line": "你再说一遍试试！"},
            {"speaker": "昭昭", "line": "试试就试试！"},
            {"speaker": "灿灿", "line": "你还讨厌呢！"},
            {"speaker": "昭昭", "line": "那你还讨厌呢！"},
            {"speaker": "灿灿", "line": "吼什么吼！"},
            {"speaker": "昭昭", "line": "那你还吼呢！"},
            {"speaker": "灿灿", "line": "啊啊啊！"},
            {"speaker": "昭昭", "line": "啊什么啊！"},
            {"speaker": "灿灿", "line": "不跟你玩了！"},
            {"speaker": "昭昭", "line": "咱们永远是一伙的！"},
            {"speaker": "灿灿", "line": "谁欺负你就跟谁急！"},
            {"speaker": "昭昭", "line": "一致对外！"},
        ],
    }
    errors: list[str] = []
    append_f_body_errors(story, errors)
    assert any("B" in e for e in errors)


def test_parse_f_from_punchline():
    assert parse_story_type_code(punchline="F类：互呛加码") == "F"


def test_f_align_flags_gs9_invent_and_h_tail():
    from app.services.daily_story.story_types.f.validate import append_f_align_issues

    rows = [
        {"line": "你再说一遍试试！"},
        {"line": "试试就试试！"},
        {"line": "你还讨厌呢！"},
        {"line": "那你还讨厌呢！"},
        {"line": "吼什么吼！"},
        {"line": "那你还吼呢！"},
        {"line": "啊啊啊！"},
        {"line": "啊什么啊！"},
        {"line": "姐，有人拍我们呢！"},
        {"line": "啊？快闭嘴！"},
        {"line": "是啊，别吵了，我们和好吧！"},
        {"line": "那薯片分你一半！"},
        {"line": "好，一起笑，让他们看看我们多团结！"},
        {"line": "嗯，我们可是好姐弟呢！"},
        {"line": "对，谁欺负你我就帮你！"},
        {"line": "好，就这么说定了！"},
    ]
    issues: list[dict] = []
    append_f_align_issues(
        rows,
        issues,
        mechanism="M3",
        dialogue_seed=[
            {"intent": "你这样说我还觉得你很讨厌呢！"},
            {"intent": "那你还很讨厌呢！"},
        ],
        beat=["姐弟因小事互怼，声音越来越大", "弟弟发现偷拍，提醒姐姐"],
        closing_intent="两人默契闭嘴，对镜头尴尬微笑",
        conflict_text="你这样说我还觉得你很讨厌呢！",
    )
    kinds = {str(x.get("kind")) + ":" + str(x.get("desc")) for x in issues}
    assert any("和好" in k for k in kinds)
    assert any("薯片" in k or "零食" in k or "饼干" in k for k in kinds)
    assert any("团结" in k or "好姐弟" in k for k in kinds)


def test_f_align_flags_camera_staging_and_broken_ellipsis():
    from app.services.daily_story.story_types.f.validate import append_f_align_issues

    rows = [
        {"line": "你再说一遍试试！"},
        {"line": "试试就试试！"},
        {"line": "你还讨厌呢！"},
        {"line": "那你还讨厌呢！"},
        {"line": "吼什么吼！"},
        {"line": "那你还吼呢！"},
        {"line": "啊啊啊！"},
        {"line": "啊什么啊！"},
        {"line": "姐，有人拍我们呢！"},
        {"line": "啊？快闭嘴！"},
        {"line": "呵呵…你听着…"},
        {"line": "咱们别吵了，先看看谁在拍。"},
        {"line": "好，我数三二一，一起笑。"},
        {"line": "哈哈，这样他应该满意了吧。"},
        {"line": "希望他拍完就走，别烦我们了。"},
    ]
    issues: list[dict] = []
    append_f_align_issues(rows, issues, mechanism="M3")
    kinds = {str(x.get("kind")) + ":" + str(x.get("desc")) for x in issues}
    assert any("别吵" in k for k in kinds)
    assert any("数三二一" in k or "商量应对镜头" in k for k in kinds)
    assert any("省略号" in k for k in kinds)
    assert any("对白过多" in k for k in kinds)


def test_f_strip_filler_removes_le_ya_stack():
    from app.services.daily_story.story_types.f.patch import patch_f_strip_filler

    story = {
        "story_type": "F",
        "punchline_explain": "F类：互呛",
        "dialogue": [
            {
                "speaker": "灿灿",
                "line": "昭昭，你刚才那样说话，我还觉得你很讨厌了呢了呀！",
            },
            {"speaker": "昭昭", "line": "那你还很讨厌了呢呀！"},
        ],
    }
    notes = patch_f_strip_filler(story)
    assert notes
    assert "了呢了呀" not in story["dialogue"][0]["line"]
    assert story["dialogue"][0]["line"].endswith("讨厌！")
    assert "了呢呀" not in story["dialogue"][1]["line"]


def test_quality_f_structure_score_external_interrupt_close():
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.story_types.f.patch import patch_f_punchline_prefix

    story = {
        "story_type": "F",
        "punchline_explain": "姐弟吵架发现偷拍后假装闹着玩",
        "conflict_core": "姐弟互怼升级，发现偷拍后熄火",
        "setting": "阳台里吵架",
        "dialogue": [
            {"speaker": "灿灿", "line": "你这样说我还觉得你很讨厌了呢！"},
            {"speaker": "昭昭", "line": "那你还很讨厌了呢！"},
            {"speaker": "灿灿", "line": "你再说一遍试试啊！"},
            {"speaker": "昭昭", "line": "试试就试试嘛！"},
            {"speaker": "灿灿", "line": "你再说一遍！"},
            {"speaker": "昭昭", "line": "你才讨厌！"},
            {"speaker": "灿灿", "line": "吼什么吼吧！"},
            {"speaker": "昭昭", "line": "那你还吼了呢！"},
            {"speaker": "灿灿", "line": "啊啊啊！"},
            {"speaker": "昭昭", "line": "啊什么啊！"},
            {"speaker": "灿灿", "line": "你再说我打你呀！"},
            {"speaker": "昭昭", "line": "你敢！"},
            {"speaker": "灿灿", "line": "哼！我不跟你玩了嘛！"},
            {"speaker": "昭昭", "line": "不玩就不玩！谁稀罕了吧！"},
            {"speaker": "灿灿", "line": "姐，有人拍我们了呢！"},
            {"speaker": "昭昭", "line": "啊？快闭嘴！"},
            {"speaker": "灿灿", "line": "呵呵…我们刚刚在闹着玩呢！"},
            {"speaker": "昭昭", "line": "嘿嘿……"},
            {"speaker": "灿灿", "line": "哎呀，我们刚刚在闹着玩呢！"},
            {"speaker": "昭昭", "line": "对呀对呀，我们可好了呢！"},
        ],
    }
    patch_f_punchline_prefix(story)
    q = score_daily_story(story, theme="文明吵架急刹车")
    assert q["structure_score"] >= 70
    assert "笑点解析缺类型" not in str(q.get("reasons"))
    assert "收束形态未落位" not in str(q.get("reasons"))
    assert "末段缺僵持" not in str(q.get("reasons"))


def test_quality_f_marker_and_body_only_opening():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "story_type": "F",
        "punchline_explain": "F类：互呛加码尴尬收束",
        "conflict_core": "姐弟互怼升级，发现偷拍后熄火",
        "setting": "阳台里吵架",
        "dialogue": [
            {"speaker": "灿灿", "line": "你这样说我还觉得你很讨厌了呢！"},
            {"speaker": "昭昭", "line": "那你还很讨厌了呢！"},
            {"speaker": "灿灿", "line": "你再说一遍试试啊！"},
            {"speaker": "昭昭", "line": "试试就试试嘛！"},
            {"speaker": "灿灿", "line": "你再说一遍！"},
            {"speaker": "昭昭", "line": "你才讨厌！"},
            {"speaker": "灿灿", "line": "吼什么吼吧！"},
            {"speaker": "昭昭", "line": "那你还吼了呢！"},
            {"speaker": "灿灿", "line": "啊啊啊！"},
            {"speaker": "昭昭", "line": "啊什么啊！"},
            {"speaker": "灿灿", "line": "你再说我打你呀！"},
            {"speaker": "昭昭", "line": "你敢！"},
            {"speaker": "灿灿", "line": "姐，有人拍我们呢！"},
            {"speaker": "昭昭", "line": "啊？快闭嘴！"},
            {"speaker": "灿灿", "line": "闹着玩呢！"},
            {"speaker": "昭昭", "line": "茄子！"},
            {"speaker": "灿灿", "line": "快走啦！"},
        ],
    }
    q = score_daily_story(story, theme="文明吵架急刹车")
    assert "缺发现开场" not in str(q.get("reasons"))
    assert "笑点解析缺类型" not in str(q.get("reasons"))
