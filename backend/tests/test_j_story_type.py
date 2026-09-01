"""J 类权威压住 validate 与质检注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    append_type_body_validation_errors,
    parse_story_type_code,
    story_type_tag,
    type_body_validation_enabled,
)
from app.services.daily_story.story_types.j.validate import append_j_body_errors


def _j_veto_story() -> dict:
    return {
        "story_type": "J",
        "theme": "姐姐说了算",
        "setting": "家中客厅，昭昭想出门，妈妈站在一旁",
        "conflict_core": "姐姐说了算，否决权高于妈妈",
        "punchline_explain": (
            "J类权威压住，灿灿一票否决压住昭昭，即使妈妈同意也无效，"
            "昭昭哀求无果后怂退，灿灿仍占上风。"
        ),
        "discovery_opening": [
            {"speaker": "昭昭", "line": "妈妈，我想去公园玩！"},
            {"speaker": "妈妈", "line": "去吧，早点回来。"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "妈妈，我想去公园玩！"},
            {"speaker": "妈妈", "line": "去吧，早点回来。"},
            {"speaker": "灿灿", "line": "等等，我同意了吗呀？"},
            {"speaker": "昭昭", "line": "姐姐，求你了，让我去了吧！"},
            {"speaker": "灿灿", "line": "我说不行就不行啊！"},
            {"speaker": "昭昭", "line": "呜呜呜，我保证写完作业嘛！"},
            {"speaker": "灿灿", "line": "哭也没用，我说了算吧。"},
            {"speaker": "昭昭", "line": "姐姐，我求你了，就一次呢！"},
            {"speaker": "灿灿", "line": "别哭了，再哭更不准真的呀。"},
            {"speaker": "昭昭", "line": "可是妈妈都答应了呀！"},
            {"speaker": "灿灿", "line": "妈妈答应没用，我不同意就是不行。"},
            {"speaker": "昭昭", "line": "姐姐你太霸道了，我讨厌你！"},
            {"speaker": "灿灿", "line": "讨厌我也没用，这个家我说了算。"},
            {"speaker": "昭昭", "line": "那我回房间了，不理你了！"},
            {"speaker": "灿灿", "line": "去吧去吧，反正我说了算呀。"},
        ],
    }


def test_j_registered():
    assert "J" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["J"].label == "权威压住"
    assert story_type_tag("J") == "J类权威压住"
    assert STORY_TYPE_LINES["J"].quality_ready is False


def test_j_validate_passes_veto_shape():
    story = _j_veto_story()
    errors: list[str] = []
    append_j_body_errors(story, errors)
    assert errors == []


def test_j_validate_rejects_a_backfire():
    story = _j_veto_story()
    story["dialogue"][-2] = {
        "speaker": "昭昭",
        "line": "你刚才说写完作业才能看。",
    }
    story["dialogue"][-1] = {
        "speaker": "灿灿",
        "line": "那不一样，这不算看。",
    }
    errors: list[str] = []
    append_j_body_errors(story, errors)
    assert any("A 式" in e for e in errors)


def test_j_body_validate_gated_when_not_quality_ready():
    story = _j_veto_story()
    story["dialogue"] = story["dialogue"][:8]
    assert not type_body_validation_enabled("J")
    errors: list[str] = []
    append_type_body_validation_errors(story, errors)
    assert not any("J类" in e for e in errors)


def test_parse_j_from_story_type():
    assert parse_story_type_code(story_type="J", punchline="C类：旧稿") == "J"


def test_j_quality_profile_not_c_fallback():
    from app.services.daily_story.story_types.quality import quality_profile_for_code

    assert quality_profile_for_code("J").code == "J"


def test_j_quality_scores_veto_story():
    from app.services.daily_story.quality import score_daily_story

    story = _j_veto_story()
    q = score_daily_story(story, theme="姐姐说了算")
    assert q["structure_score"] >= 70, q
    assert "C开场说话人" not in "".join(q["reasons"])
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "回旋镖" not in "".join(q["reasons"])
    assert "收束形态未落位" not in "".join(q["reasons"])
    assert "笑点解析缺类型" not in q["reasons"]


def _j_repetitive_veto_story() -> dict:
    story = _j_veto_story()
    story["dialogue"] = [
        {"speaker": "昭昭", "line": "妈妈，我想去公园玩！"},
        {"speaker": "妈妈", "line": "去吧，早点回来。"},
        {"speaker": "灿灿", "line": "等等，我同意了吗呀？"},
        {"speaker": "昭昭", "line": "姐姐，求你了，让我去了吧！"},
        {"speaker": "灿灿", "line": "我说不行就不行啊！"},
        {"speaker": "昭昭", "line": "同桌说公园里有鸽子，我想去看看嘛！"},
        {"speaker": "灿灿", "line": "看鸽子也不行，出门我说了算。"},
        {"speaker": "昭昭", "line": "我鞋都穿好喽，就在门口玩一小会儿！"},
        {"speaker": "灿灿", "line": "穿好了也没用，再哭更不准呀。"},
        {"speaker": "昭昭", "line": "我保证五点半准时回家，绝不贪玩呢！"},
        {"speaker": "灿灿", "line": "准时回家也没用，想都别想呀。"},
        {"speaker": "昭昭", "line": "可是妈妈都答应了呀！"},
        {"speaker": "灿灿", "line": "妈妈答应没用，我不同意就不行。"},
        {"speaker": "昭昭", "line": "那我帮你收玩具，还带两根冰棍嘛！"},
        {"speaker": "灿灿", "line": "带冰棍也不行，我说不行就不行。"},
        {"speaker": "昭昭", "line": "我把新贴纸也给你三张，行吧？"},
        {"speaker": "灿灿", "line": "贴纸也不行，出门我说了算。"},
        {"speaker": "昭昭", "line": "姐姐你太霸道了，我讨厌你！"},
        {"speaker": "灿灿", "line": "讨厌我也没用，这个家我说了算。"},
        {"speaker": "昭昭", "line": "呜呜，我回房间了，不理你了！"},
        {"speaker": "灿灿", "line": "回你的去，反正我说了算呀。"},
    ]
    return story


def test_j_validate_accepts_m8_domination_shape():
    story = {
        "story_type": "J",
        "punchline_explain": "J类权威压住，灿灿一锤镇住昭昭",
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的地盘，你走开！"},
            {"speaker": "灿灿", "line": "我先来的，该你走！"},
            {"speaker": "昭昭", "line": "哼，看招！"},
            {"speaker": "灿灿", "line": "你敢打我？"},
            {"speaker": "灿灿", "line": "谁赢谁说了算！"},
            {"speaker": "昭昭", "line": "拿出最强形态来！"},
            {"speaker": "灿灿", "line": "草莓熊肘击！"},
            {"speaker": "昭昭", "line": "啊，我输了！"},
            {"speaker": "灿灿", "line": "以后玩具都归我！"},
            {"speaker": "昭昭", "line": "哼，等我长大再算账！"},
            {"speaker": "灿灿", "line": "算你识相，反正都听我的。"},
        ],
    }
    errors: list[str] = []
    append_j_body_errors(story, errors)
    assert errors == [], errors


def test_j_validate_accepts_m8_surrender_phrases():
    story = _j_veto_story()
    story["dialogue"] = story["dialogue"][:12] + [
        {"speaker": "昭昭", "line": "好吧好吧，我输了还不行吗！"},
        {"speaker": "灿灿", "line": "输了就听话，反正我说了算呀。"},
    ]
    errors: list[str] = []
    append_j_body_errors(story, errors)
    assert errors == [], errors


def test_j_patch_dedupes_authority_repeat():
    from app.services.daily_story.story_types.j.patch import patch_j_body

    story = _j_repetitive_veto_story()
    notes = patch_j_body(story)
    assert any("J去否决复读" in n for n in notes)
    assert notes
    cancan = [
        x["line"]
        for x in story["dialogue"]
        if x.get("speaker") == "灿灿"
    ]
    hold_n = sum(line.count("我说了算") for line in cancan)
    assert hold_n <= 2, cancan
    assert cancan[-1].count("我说了算") >= 1
    errors: list[str] = []
    append_j_body_errors(story, errors)
    assert errors == []


def test_j_patch_swaps_limp_last_to_cancan_hold():
    """末句昭昭「哼」软收须与灿灿镇住对调，避免无破功软收 -20。"""
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.story_types.j.patch import patch_j_body

    story = {
        "story_type": "J",
        "setting": "幼儿园午休垫子上，灿灿和昭昭在抢地盘",
        "conflict_core": "弟弟先闹动手，姐姐一锤 KO 镇住，弟弟表面认输内心不服",
        "punchline_explain": "J类：灿灿一锤镇住，昭昭怂退不敢再顶。",
        "discovery_opening": [
            {"speaker": "昭昭", "line": "这是我的地盘，你走开！"},
            {"speaker": "灿灿", "line": "不行，谁赢谁说了算！"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的地盘，你走开！"},
            {"speaker": "灿灿", "line": "我先来的，该你走！"},
            {"speaker": "昭昭", "line": "哼，看招！"},
            {"speaker": "灿灿", "line": "你敢打我？不行！"},
            {"speaker": "昭昭", "line": "就打你，怎么了！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算！"},
            {"speaker": "昭昭", "line": "拿出你的最强形态来！"},
            {"speaker": "灿灿", "line": "草莓熊肘击！"},
            {"speaker": "昭昭", "line": "啊，我输了！"},
            # prev2 故意不含镇住词，复现「有收束形态仍无破功软收 -20」
            {"speaker": "灿灿", "line": "以后玩具归姐姐这边！"},
            {"speaker": "昭昭", "line": "哼，等我长大再算账！"},
        ],
    }
    before = score_daily_story(story, theme="地盘争夺", skip_relevancy=True)
    assert any("无破功软收" in r for r in before["reasons"]), before
    assert before["structure_score"] < 75, before

    notes = patch_j_body(story)
    assert any("镇住" in n for n in notes)
    assert story["dialogue"][-1]["speaker"] == "灿灿"
    assert "哼" not in story["dialogue"][-1]["line"]
    assert story["dialogue"][-2]["speaker"] == "昭昭"

    after = score_daily_story(story, theme="地盘争夺", skip_relevancy=True)
    assert after["structure_score"] >= 75, after
    assert "无破功软收" not in "".join(after["reasons"])
