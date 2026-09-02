"""K 类家长看戏 validate 与质检注册。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    append_type_body_validation_errors,
    parse_story_type_code,
    story_type_tag,
    type_body_validation_enabled,
)
from app.services.daily_story.story_types.k.validate import append_k_body_errors


def _k_stalemate_story() -> dict:
    return {
        "story_type": "K",
        "theme": "越劝越哭",
        "setting": "客厅，姐弟扭在一起，妈妈站在门口",
        "conflict_core": "姐弟互骂升级，妈妈越劝越凶",
        "punchline_explain": (
            "K类家长看戏，姐弟互骂升级，妈妈叹气劝失败，"
            "最后僵持不和好。"
        ),
        "discovery_opening": [
            {"speaker": "灿灿", "line": "你干嘛抢我遥控器！"},
            {"speaker": "昭昭", "line": "你才抢！你滚！"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "你干嘛抢我遥控器！"},
            {"speaker": "昭昭", "line": "你才抢！你滚！"},
            {"speaker": "灿灿", "line": "你骂谁呢！我打你了！"},
            {"speaker": "昭昭", "line": "来啊！谁怕谁！"},
            {"speaker": "灿灿", "line": "讨厌！你推我！"},
            {"speaker": "昭昭", "line": "你还推！呜呜呜！"},
            {"speaker": "妈妈", "line": "别打了！你们别吵了！"},
            {"speaker": "灿灿", "line": "你管不着！"},
            {"speaker": "昭昭", "line": "越劝越凶！哼！"},
            {"speaker": "妈妈", "line": "唉，我管不了你们了。"},
            {"speaker": "灿灿", "line": "就不理你！"},
            {"speaker": "昭昭", "line": "我也不和好！"},
            {"speaker": "灿灿", "line": "僵持就僵持，谁怕谁！"},
            {"speaker": "昭昭", "line": "哼，别理你！"},
        ],
    }


def test_k_registered():
    assert "K" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["K"].label == "家长看戏"
    assert story_type_tag("K") == "K类家长看戏"
    assert STORY_TYPE_LINES["K"].quality_ready is False


def test_k_validate_passes_stalemate_shape():
    story = _k_stalemate_story()
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert errors == []


def test_k_validate_rejects_h_reconcile():
    story = _k_stalemate_story()
    story["dialogue"][-2] = {"speaker": "灿灿", "line": "好吧，我们和好吧。"}
    story["dialogue"][-1] = {"speaker": "昭昭", "line": "拉手，不打了。"}
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert any("H 式" in e for e in errors)


def test_k_patch_strips_h_reconcile_and_fills_stalemate():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["dialogue"][-2] = {"speaker": "妈妈", "line": "你们什么时候能和好？"}
    story["dialogue"][-1] = {"speaker": "昭昭", "line": "拉手，不打了。"}
    notes = patch_k_body(story)
    assert notes
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert errors == []


def test_k_patch_strips_mid_action_narr():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["dialogue"][3] = {
        "speaker": "昭昭",
        "line": "你别过来啊！我躲沙发后面！",
    }
    notes = patch_k_body(story)
    assert any("分镜" in n for n in notes)
    line = str(story["dialogue"][3].get("line") or "")
    assert "躲沙发" not in line
    assert "别过来" in line


def test_k_patch_strips_pad_junk_stacks():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["punchline_explain"] = (
        "K类家长看戏，姐姐护手怕疼，妈妈劝失败，僵持不和好。"
    )
    story["dialogue"][4] = {"speaker": "灿灿", "line": "嘛！"}
    story["dialogue"][5] = {
        "speaker": "昭昭",
        "line": "哼真的呀真的真的呀真的了呢！",
    }
    story["dialogue"][6] = {
        "speaker": "灿灿",
        "line": "哎哟别咬我手，疼死了嘛不行嘛呀！",
    }
    story["dialogue"][7] = {
        "speaker": "昭昭",
        "line": "你打人还怕疼？活该嘛呀！",
    }
    story["dialogue"][8] = {
        "speaker": "灿灿",
        "line": "你越劝我越打不行！",
    }
    notes = patch_k_body(story)
    assert any("垫字" in n or "越劝" in n or "护手" in n for n in notes)
    lines = [str(d.get("line") or "") for d in story["dialogue"]]
    blob = "".join(lines)
    assert "真的呀真的" not in blob
    assert "嘛不行嘛" not in blob
    assert "嘛呀" not in blob
    assert "活该" in lines[7]
    assert "弄疼我手" in blob or "手疼" in blob or "手好疼" in blob
    assert "别咬我手" not in blob
    assert "你越劝" not in blob
    assert "？！" not in blob
    assert not any(re.fullmatch(r"[嘛呢吧呀啊]+[！？。!]?", ln) for ln in lines)


def test_k_repair_closing_and_seed_sanitize():
    from app.services.daily_story.story_types.k.patch import sanitize_k_dialogue_seed
    from app.services.daily_story.story_types.k.validate import (
        repair_closing_intent_for_k,
    )

    closing = repair_closing_intent_for_k("妈妈哭笑不得，总结胜不骄败不馁")
    assert "僵持" in closing or "不和好" in closing
    assert "和好" not in closing or "不和好" in closing

    seed = sanitize_k_dialogue_seed(
        [
            {"speaker": "妈妈", "intent": "叹气，你们俩什么时候能和好？"},
            {"speaker": "昭昭", "intent": "不服气"},
        ]
    )
    assert "和好" not in str(seed[0].get("intent") or "") or "不和好" in str(
        seed[0].get("intent") or ""
    )
    assert "劝不" in str(seed[0].get("intent") or "") or "管不了" in str(
        seed[0].get("intent") or ""
    )


def test_k_body_validate_gated_when_not_quality_ready():
    story = _k_stalemate_story()
    story["dialogue"] = story["dialogue"][:8]
    assert not type_body_validation_enabled("K")
    errors: list[str] = []
    append_type_body_validation_errors(story, errors)
    assert not any("K类" in e for e in errors)


def test_k_patch_strips_adult_threat_and_near_dupes():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["dialogue"].insert(
        6, {"speaker": "灿灿", "line": "不服也得挨着！"}
    )
    story["dialogue"].insert(
        7, {"speaker": "昭昭", "line": "你还打！我不怕你啊！"}
    )
    story["dialogue"].insert(
        8, {"speaker": "灿灿", "line": "再闹我就更凶呀！"}
    )
    story["dialogue"].insert(
        9, {"speaker": "昭昭", "line": "你还打！我不怕你！"}
    )
    story["dialogue"].insert(
        10, {"speaker": "灿灿", "line": "再闹我就更凶！"}
    )
    notes = patch_k_body(story)
    blob = "".join(str(x.get("line") or "") for x in story["dialogue"])
    assert "不服也得挨着" not in blob
    assert "说一不二" not in blob
    norms = [
        re.sub(r"[呀啊吧呢嘛了呗！？。!?，,\s]", "", str(x.get("line") or ""))
        for x in story["dialogue"]
        if isinstance(x, dict)
    ]
    assert len(norms) == len(set(norms))
    assert any("成人腔" in n or "近义" in n for n in notes)


def test_parse_k_from_story_type():
    assert parse_story_type_code(story_type="K", punchline="H类：旧稿") == "K"


def test_k_quality_profile_not_c_fallback():
    from app.services.daily_story.story_types.quality import quality_profile_for_code

    assert quality_profile_for_code("K").code == "K"


def test_k_quality_scores_stalemate_story():
    from app.services.daily_story.quality import score_daily_story

    story = _k_stalemate_story()
    q = score_daily_story(story, theme="越劝越哭")
    assert q["structure_score"] >= 70, q
    assert "C开场说话人" not in "".join(q["reasons"])
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "收束形态未落位" not in "".join(q["reasons"])
    assert "笑点解析缺类型" not in q["reasons"]
