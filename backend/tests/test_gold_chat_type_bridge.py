"""gold_chat 类型流水线桥接测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story.gold_chat.type_bridge import (
    apply_type_body_pipeline,
    structure_type_hint,
    type_fidelity_chain,
)
from app.services.daily_story.gold_story.types import (
    MECHANISM_STRUCTURE_MAP,
    GOLD_STORY_STRUCTURE_CODES,
)


@pytest.mark.parametrize(
    ("mech", "st"),
    sorted(MECHANISM_STRUCTURE_MAP.items()),
)
def test_default_mechanism_pairs_have_fidelity_chain(mech: str, st: str):
    chain = type_fidelity_chain(structure_type=st, mechanism=mech)
    assert chain, f"{mech}+{st} 应有扩写链"


@pytest.mark.parametrize("code", sorted(GOLD_STORY_STRUCTURE_CODES))
def test_structure_type_fallback_chain(code: str):
    chain = type_fidelity_chain(structure_type=code, mechanism="")
    assert chain, f"结构 {code} 应有 fallback 扩写链"


def test_m2_c_chain_mentions_boomerang():
    chain = type_fidelity_chain(structure_type="C", mechanism="M2")
    blob = "\n".join(chain)
    assert "堵截" in blob
    assert "回旋镖" in blob


def test_structure_type_hint_covers_all_story_lines():
    for code in ("A", "B", "C", "D", "E", "G", "H", "I"):
        hint = structure_type_hint(structure_type=code, mechanism="M1")
        assert f"【{code}" in hint
        assert "公式" in hint
        assert "扩写链" in hint


def test_structure_type_hint_m2_c_extra():
    hint = structure_type_hint(structure_type="C", mechanism="M2")
    assert "M2+C" in hint
    assert "自私包装公平" in hint
    assert "禁止另起第二轮" in hint


def test_patch_gold_chat_post_close_tail_m2_c():
    from app.services.daily_story.gold_story.gold_chat.patch import (
        patch_gold_chat_post_close_tail,
    )

    chat = {
        "scene_title": "八百个心眼子",
        "key": "肉盘保卫战",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "灿灿，你那肉给我夹一块呗呢。"},
            {"speaker": "灿灿", "line": "不给！你刚才不是说你不爱吃肉嘛！"},
            {"speaker": "昭昭", "line": "我……我现在又想吃了呢。"},
            {"speaker": "灿灿", "line": "那也不行，妈妈说吃多肉会变胖呢。"},
            {"speaker": "昭昭", "line": "我不管，我就吃一块呢！"},
            {"speaker": "灿灿", "line": "你都已经够胖了，再吃就成球啦呢！"},
            {"speaker": "昭昭", "line": "你……你才胖呢！"},
            {"speaker": "灿灿", "line": "我胖我乐意，反正这肉是我的，我说了算呢！"},
            {"speaker": "昭昭", "line": "哼，那你吃吧，我看着你吃呢！"},
            {"speaker": "灿灿", "line": "嘿嘿，真香呢！"},
            {"speaker": "妈妈", "line": "吃商这方面谁能比得过我闺女。"},
            {"speaker": "昭昭", "line": "这妹妹，八百个心眼子呢！"},
            {"speaker": "灿灿", "line": "我说不吃是客气，你还当真了呢！"},
            {"speaker": "昭昭", "line": "你客气啥，你碗里那青菜不香吗？"},
            {"speaker": "昭昭", "line": "滑头咋了，反正肉在我嘴里呢！"},
        ],
    }
    payload = {
        "mechanism": "M2",
        "dialogue_seed": [{"speaker": "昭昭", "intent": "无奈嘀咕：这妹妹，八百个心眼子"}],
        "scene_contract": {
            "beat_chain": [
                {"speaker": "灿灿", "intent": "护住盘子"},
                {"speaker": "昭昭", "intent": "改口想吃"},
            ],
        },
    }
    patched, notes = patch_gold_chat_post_close_tail(
        chat,
        payload=payload,
        structure_type="C",
        mechanism="M2",
    )
    assert len(patched["dialogue"]) == 12
    assert "删点题后拖尾" in "".join(notes)
    assert patched["dialogue"][-1]["line"].startswith("这妹妹")


def test_patch_m2_c_structure_layers():
    from app.services.daily_story.gold_story.gold_chat.patch import (
        patch_m2_c_structure,
    )
    from app.services.daily_story.quality import attach_daily_story_quality

    chat = {
        "scene_title": "八百个心眼子",
        "setting": "餐桌，灿灿面前一盘肉",
        "conflict_core": "哥哥想吃妹妹的肉，妹妹用哥哥自己的话和妈妈的规矩双重堵截",
        "punchline_explain": "昭昭无奈，妹妹心眼多。",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "灿灿，你碗里肉好多，给我夹一块呢。"},
            {"speaker": "灿灿", "line": "不行！你刚才不是说不爱吃肉嘛！"},
            {"speaker": "昭昭", "line": "我……我现在又想吃了呢。"},
            {"speaker": "灿灿", "line": "那也不行，妈妈说吃多肉会变胖呢。"},
            {"speaker": "昭昭", "line": "我不管，我就要吃呢！"},
            {"speaker": "灿灿", "line": "你都已经够胖了，再吃就成球啦呢！"},
            {"speaker": "昭昭", "line": "我……我哪有胖呢！"},
            {"speaker": "灿灿", "line": "我胖我乐意，反正这肉是我的，我说了算呢！"},
            {"speaker": "昭昭", "line": "哼，那你吃吧，我看着你吃呢！"},
            {"speaker": "灿灿", "line": "嘿嘿，真香呢！"},
            {"speaker": "昭昭", "line": "我明天不吃零食了，换一口肉行不行？"},
            {"speaker": "灿灿", "line": "明天的是明天的，今天的肉我说了算，不分！"},
            {"speaker": "妈妈", "line": "吃商这方面谁能比得过我。"},
            {"speaker": "昭昭", "line": "这妹妹，八百个心眼子呢！"},
        ],
    }
    patched, notes = patch_m2_c_structure(
        chat,
        structure_type="C",
        mechanism="M2",
        theme="八百个心眼子",
    )
    assert any("C类" in n or "回旋镖" in n or "C1" in n for n in notes)
    assert patched["punchline_explain"].startswith("C类")
    assert "你刚说" in patched["dialogue"][1]["line"]
    assert "妈妈说过" in patched["dialogue"][3]["line"]
    attach_daily_story_quality(patched, theme="八百个心眼子")
    struct = patched["quality"]["structure_score"]
    assert struct is not None and struct >= 50


def test_apply_type_body_pipeline_sets_story_type():
    chat = {
        "story_type": "C",
        "dialogue": [
            {"speaker": "灿灿", "line": "这是我的肉，我先拿到的。"},
            {"speaker": "昭昭", "line": "我也想吃一块嘛。"},
        ],
    }
    patched, notes = apply_type_body_pipeline(chat, structure_type="C")
    assert patched.get("story_type") == "C"
    assert isinstance(notes, list)
