"""F 类互呛加码 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.f.validate import append_f_body_errors


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


def test_f_patch_repairs_123_shape_alternation_and_close():
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.story_types.f.patch import patch_f_body
    from app.services.daily_story.story_types.f.validate import append_f_body_errors
    from app.services.gold_story.scene import collect_narration_dialogue_errors

    story = {
        "story_type": "F",
        "conflict_core": "灿灿自怜没人爱，昭昭憋笑学舌把伤感变笑料",
        "punchline_explain": "F类：灿灿自怜，昭昭憋笑学舌，追打收束",
        "dialogue": [
            {"speaker": "灿灿", "line": "我想我会一直孤单。"},
            {"speaker": "昭昭", "line": "姐，你看着窗外叹啥气？"},
            {"speaker": "灿灿", "line": "望着窗外这黑漆漆的天，我觉得没人会爱我了。"},
            {"speaker": "昭昭", "line": "嗯嗯嗯……呜呜啊呜呀呜……"},
            {"speaker": "灿灿", "line": "昭昭你趴地上干嘛？发什么怪声？"},
            {"speaker": "灿灿", "line": "我也感觉没人会爱我了，你？"},
            {"speaker": "灿灿", "line": "你还学我说话？你再说一遍试试看！"},
            {"speaker": "昭昭", "line": "噗嗤……我也很孤单，啊啊啊……"},
            {"speaker": "灿灿", "line": "你再说一句，我就拿抱枕砸你信不信？"},
            {"speaker": "昭昭", "line": "你砸呀你砸呀，我也很孤单，啊。"},
            {"speaker": "灿灿", "line": "好，你等着！看我不砸你才怪！"},
            {"speaker": "昭昭", "line": "别打了别打了，我笑岔气了。"},
            {"speaker": "灿灿", "line": "你还学不学？再学我可不跟你玩了嘛。"},
            {"speaker": "昭昭", "line": "不学了不学了，姐姐你孤单得好好笑啊。"},
            {"speaker": "灿灿", "line": "你还笑！我今天非抓住你不可啊！"},
            {"speaker": "昭昭", "line": "我躲沙发后面了，你抓不到我，嘿嘿呀。"},
        ],
    }
    patch_f_body(story)
    errors: list[str] = []
    append_f_body_errors(story, errors)
    assert errors == []
    assert collect_narration_dialogue_errors(story["dialogue"]) == []
    assert score_daily_story(
        story, skip_relevancy=True
    )["structure_score"] >= 75


def test_f_stale_and_yield_beat_are_two_layers():
    """僵持（试试就试试/你等着）与中止收束（回屋/找妈妈评理）是两个节拍。

    收束走「僵持 + 退场」的合规稿此前与「僵持」共层，只测到 3 层（-4）；
    拆拍后应与「互呛/加码/僵持/中止收束」四拍对齐，结构分满分。
    """
    from app.services.daily_story.quality import (
        _score_escalation,
        score_daily_story,
    )
    from app.services.daily_story.story_types.f.line import LINE_F

    story = {
        "story_type": "F",
        "punchline_explain": "F类：姐弟互呛加码抢鸡爪，僵持后各自退场",
        "conflict_core": "昭昭抢走最大鸡爪还顺走灿灿碗里的鸡腿肉，灿灿追着抢。",
        "setting": "阳台小桌，妈妈端着一盘鸡爪当裁判",
        "_gold_chat_mom_lines_max": 2,
        "dialogue": [
            {"speaker": "昭昭", "line": "姐姐，咱在阳台搞抢食赛，妈妈端鸡爪当裁判！"},
            {"speaker": "妈妈", "line": "行，我端鸡爪，你们抢，我看着，谁哭谁输。"},
            {"speaker": "昭昭", "line": "看准了！最大这根归我，你手跟螃蟹一样慢！"},
            {"speaker": "灿灿", "line": "给我留一个！你啃得满嘴油，还笑我手慢！"},
            {"speaker": "昭昭", "line": "你再说一遍试试！我啃得比你快，你还敢吼我？"},
            {"speaker": "灿灿", "line": "好不容易抢到一块，嚼半天咬不动，难嚼死了！"},
            {"speaker": "昭昭", "line": "你咬不动就慢慢嚼，我碗里这块鸡腿肉先替你尝尝！"},
            {"speaker": "灿灿", "line": "你敢动我碗里的肉！放下，那是我留的，我跟你没完！"},
            {"speaker": "昭昭", "line": "来抢呀，跑得慢可连半根都捞不着。"},
            {"speaker": "灿灿", "line": "你再说一遍，我扑上去连你手里鸡爪一起抢！"},
            {"speaker": "昭昭", "line": "试试就试试，我边跑边啃，你追得上算你赢！"},
            {"speaker": "灿灿", "line": "你等着，我绕桌子转圈也要把你堵在阳台角！"},
            {"speaker": "妈妈", "line": "你们闹吧，我看着！"},
            {"speaker": "灿灿", "line": "只抢到半根，我下次要买软糖，不买鸡爪了，哼！"},
            {"speaker": "昭昭", "line": "还打不打架？你追不上我，我可要回屋了。"},
            {"speaker": "灿灿", "line": "不跟你玩了，你偷我肉还笑我，我找妈妈评理去！"},
        ],
    }
    lines = [str(row["line"]) for row in story["dialogue"]]
    bonus, details = _score_escalation(lines, layer_patterns=LINE_F.layer_patterns)
    assert bonus == 14, details
    quality = score_daily_story(story, skip_relevancy=True)
    assert quality["structure_score"] == 80
    assert not any("冲突推进不足" in c for c in quality["structure_cons"])


def test_f_missing_stale_beat_keeps_three_layers():
    """缺「僵持」节拍（只有互呛→加码→中止）仍按 3 层扣 4 分，防层定义虚高。"""
    from app.services.daily_story.quality import _score_escalation
    from app.services.daily_story.story_types.f.line import LINE_F

    lines = [
        "看准了！这根最大的归我，你手跟螃蟹一样慢！",
        "给我留一个！你啃得满嘴油，还笑我手慢！",
        "你再说一遍试试！我啃得比你快，你还敢吼我？",
        "好不容易抢到一块，嚼半天咬不动，难嚼死了！",
        "你咬不动就慢慢嚼，我碗里这块鸡腿肉先替你尝尝！",
        "你敢动我碗里的肉！放下，那是我留的，我跟你没完！",
        "来抢呀，跑得慢可连半根都捞不着。",
        "你再说一遍，我扑上去连你手里鸡爪一起抢！",
        "啊呜啊呜！我啃得比你快，你追不上！",
        "只抢到半根，我下次要买软糖，不买鸡爪了，哼！",
        "不跟你玩了，你偷我肉还笑我，我找妈妈评理去！",
    ]
    bonus, details = _score_escalation(lines, layer_patterns=LINE_F.layer_patterns)
    assert bonus == 10, details
