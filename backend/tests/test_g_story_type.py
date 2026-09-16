"""G 类嘴硬心软 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.g.validate import (
    RE_F_STALE,
    RE_PIVOT,
    append_g_body_errors,
)


def test_g_validate_passes_canonical_shape():
    story = {
        "punchline_explain": "G类嘴硬心软，护短破防后暖收",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，手咋了？又跟人闹了？"},
            {"speaker": "昭昭", "line": "没……没有。"},
            {"speaker": "灿灿", "line": "还嘴硬！手都肿了，还充大侠呢！"},
            {"speaker": "昭昭", "line": "我……我不是。"},
            {"speaker": "灿灿", "line": "十个人围你一个，丢不丢人？"},
            {"speaker": "昭昭", "line": "我……我跑了。"},
            {"speaker": "灿灿", "line": "跑？你跑啥？怂包！"},
            {"speaker": "昭昭", "line": "我错了。"},
            {"speaker": "灿灿", "line": "记住个屁！谁还敢跟你玩？"},
            {"speaker": "昭昭", "line": "我不怕。"},
            {"speaker": "灿灿", "line": "你不怕？我怕！"},
            {"speaker": "昭昭", "line": "谁敢动你，我跟他拼命！"},
            {"speaker": "灿灿", "line": "你……你说啥？"},
            {"speaker": "昭昭", "line": "谁欺负你，我就跟谁拼命。"},
            {"speaker": "灿灿", "line": "就你这样？还拼命？"},
            {"speaker": "昭昭", "line": "认真的。"},
            {"speaker": "灿灿", "line": "行了，过来，我给你擦擦药。"},
            {"speaker": "昭昭", "line": "嗯。"},
            {"speaker": "灿灿", "line": "以后谁欺负你，我还得给你撑腰呢！"},
            {"speaker": "昭昭", "line": "那说好了！"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == []


def test_g_validate_rejects_c_boomerang_tail():
    story = {
        "punchline_explain": "G类嘴硬心软",
        "dialogue": [{"speaker": "昭昭", "line": f"句{i}"} for i in range(11)]
        + [
            {"speaker": "灿灿", "line": "你刚才说不能抢"},
            {"speaker": "昭昭", "line": "护姐！"},
            {"speaker": "灿灿", "line": "你说啥？"},
            {"speaker": "昭昭", "line": "认真的"},
            {"speaker": "灿灿", "line": "你自己说的你先选"},
        ],
    }
    # pad middle with pivot keywords
    for i, item in enumerate(story["dialogue"][5:8], start=5):
        item["line"] = "谁敢动你我拼命"
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert any("回旋镖" in e for e in errors)


def test_parse_g_from_punchline():
    assert parse_story_type_code(punchline="G类嘴硬心软，暖收") == "G"


def test_g_pivot_not_dismissive_buyongniguan():
    """「不用你管」不得单独充当 pivot。"""
    assert not RE_PIVOT.search("不用你管！你管得着吗？")
    assert RE_PIVOT.search("你去哪？我怕你一个人走")


def test_g_validate_passes_coincidence_soft_close():
    """同路巧合：先问去向 + 笑出声 + 一起去/没走成。"""
    story = {
        "punchline_explain": "G类嘴硬心软，同路巧合笑散",
        "dialogue": [
            {"speaker": "灿灿", "line": "我走了，谁也别拦我！"},
            {"speaker": "昭昭", "line": "我也走，不用你管！"},
            {"speaker": "灿灿", "line": "你收拾包干嘛？还嘴硬！"},
            {"speaker": "昭昭", "line": "你管得着吗？少来烦我！"},
            {"speaker": "灿灿", "line": "门口撞见了？还充大侠呢！"},
            {"speaker": "昭昭", "line": "你走开！别装关心！"},
            {"speaker": "灿灿", "line": "你去哪？"},
            {"speaker": "昭昭", "line": "不用你管！"},
            {"speaker": "灿灿", "line": "我也走，同一方向！"},
            {"speaker": "昭昭", "line": "那你还不是跟我一路？"},
            {"speaker": "昭昭", "line": "噗——你还跟我一路啊！"},
            {"speaker": "灿灿", "line": "……你笑什么？"},
            {"speaker": "昭昭", "line": "算了，一起去楼下吧。"},
            {"speaker": "灿灿", "line": "行，谁也没走成。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == []


def test_g_f_stale_who_ye_bu_not_bare():
    """裸「谁也不」不判 F；双方僵持结构才判。"""
    assert not RE_F_STALE.search("谁也没真走成")
    assert RE_F_STALE.search("谁也不理谁")


def test_g_validate_f_stale_softened_by_warm_tail():
    """末段有暖收时，残余僵持词不硬拦。"""
    story = {
        "punchline_explain": "G类嘴硬心软",
        "dialogue": [
            {"speaker": "灿灿", "line": f"数落升级第{i}句丢人怂"} for i in range(10)
        ]
        + [
            {"speaker": "昭昭", "line": "谁敢动你我拼命！"},
            {"speaker": "灿灿", "line": "你说啥？"},
            {"speaker": "昭昭", "line": "谁也不让谁也行，一起走吧。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert not any("威胁僵持" in e for e in errors)
