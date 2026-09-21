"""gold_chat 类型流水线桥接测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat.type_bridge import (
    apply_type_body_pipeline,
    resolve_gold_chat_structure_row,
    structure_type_hint,
    type_align_chain,
)
from app.services.gold_story.types import (
    MECHANISM_STRUCTURE_MAP,
    GOLD_STORY_STRUCTURE_CODES,
)


@pytest.mark.parametrize(
    ("mech", "st"),
    sorted(MECHANISM_STRUCTURE_MAP.items()),
)
def test_default_mechanism_pairs_have_align_chain(mech: str, st: str):
    chain = type_align_chain(structure_type=st, mechanism=mech)
    assert chain, f"{mech}+{st} 应有扩写链"


@pytest.mark.parametrize("code", sorted(GOLD_STORY_STRUCTURE_CODES))
def test_structure_type_fallback_chain(code: str):
    chain = type_align_chain(structure_type=code, mechanism="")
    assert chain, f"结构 {code} 应有 fallback 扩写链"


def test_m2_c_chain_mentions_boomerang():
    chain = type_align_chain(structure_type="C", mechanism="M2")
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


def test_m5_g_chain_mentions_pivot():
    chain = type_align_chain(structure_type="G", mechanism="M5")
    blob = "\n".join(chain)
    assert "pivot" in blob
    assert "识相" in blob


def test_resolve_structure_row_m5_a_to_g_when_mapping_and_seed():
    row = {
        "id": 11,
        "mechanism": "M5",
        "structure_type": "A",
        "payload": {
            "structure_mapping_note": "从互怼到真情流露，符合G型结构",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "立规：以后不许再咬人"},
                {"speaker": "昭昭", "intent": "假装咬但没咬，逗姐姐"},
                {"speaker": "灿灿", "intent": "亮出旧咬痕，说永远记得"},
                {"speaker": "昭昭", "intent": "说现在不咬了，因为姐姐重要"},
                {"speaker": "灿灿", "intent": "嘴硬：哼，算你识相"},
            ],
            "scene_contract": {"story_type": "C"},
        },
    }
    fixed, notes = resolve_gold_chat_structure_row(row)
    assert fixed["structure_type"] == "G"
    assert fixed["payload"]["scene_contract"]["story_type"] == "G"
    assert any("structure_type:A→G" in n for n in notes)


def test_resolve_structure_row_skips_without_mapping_note():
    row = {
        "mechanism": "M5",
        "structure_type": "A",
        "payload": {
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "说现在不咬了，因为姐姐重要"},
                {"speaker": "灿灿", "intent": "嘴硬：哼，算你识相"},
            ],
        },
    }
    fixed, notes = resolve_gold_chat_structure_row(row)
    assert fixed["structure_type"] == "A"
    assert notes == []


def test_patch_gold_chat_post_close_tail_m2_c():
    from app.services.gold_story.gold_chat.patch import (
        patch_gold_chat_post_close_tail,
    )

    chat = {
        "scene_title": "八百个心眼子",
        "key": "肉盘保卫战",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "灿灿，你碗里那肉香得很，凭什么不能给我夹一块呢？"},
            {"speaker": "灿灿", "line": "不给！你刚才不是说你不爱吃肉嘛，说话不算话呀！"},
            {"speaker": "昭昭", "line": "我……我现在又想吃了，就吃一口行不行呢？"},
            {"speaker": "灿灿", "line": "那也不行，之前说过吃多肉会变胖，你听着呀！"},
            {"speaker": "昭昭", "line": "我不管，我就吃一块，你别这么小气好不好！"},
            {"speaker": "灿灿", "line": "你都已经够胖了，再吃就成球啦，别抢了呀！"},
            {"speaker": "昭昭", "line": "你……你才胖，我哪有那么胖，你胡说呢！"},
            {"speaker": "灿灿", "line": "我胖我乐意，反正这肉是我的，我说了算呢！"},
            {"speaker": "昭昭", "line": "哼，那你吃吧，我看着你吃，气死我了呀！"},
            {"speaker": "灿灿", "line": "嘿嘿，真香呢，你就看着吧，馋死你呀！"},
            {"speaker": "妈妈", "line": "吃商这方面，谁能比得过我闺女啊呀！"},
            {"speaker": "昭昭", "line": "这妹妹，八百个心眼子呢，太会堵人了呀！"},
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


def test_post_close_tail_skips_when_below_validate_floor():
    """删尾后若 <12 句 / <240 字，不剪（防短 seed 被剪穿）。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_gold_chat_post_close_tail,
    )

    chat = {
        "scene_title": "公平的陷阱",
        "key": "退让揭穿",
        "story_type": "C",
        "dialogue": [
            {"speaker": "灿灿", "line": "这瓶该给我。"},
            {"speaker": "昭昭", "line": "好吧，给你。"},
            {"speaker": "灿灿", "line": "我不想喝了。"},
            {"speaker": "昭昭", "line": "你不是要吗？"},
            {"speaker": "灿灿", "line": "你们喝吧。"},
            {"speaker": "妈妈", "line": "那……先放着。"},
            {"speaker": "昭昭", "line": "这哪门子公平？"},
            {"speaker": "灿灿", "line": "公平就是我不喝了。"},
            {"speaker": "昭昭", "line": "那你刚才争啥？"},
            {"speaker": "灿灿", "line": "争完我就不喝了。"},
        ],
    }
    payload = {
        "mechanism": "M2",
        "dialogue_seed": [{"speaker": "灿灿", "intent": "我不想喝了"}],
        "closing_intent": "灿灿用不喝了退让点破偏心",
        "scene_contract": {"beat_chain": []},
    }
    patched, notes = patch_gold_chat_post_close_tail(
        chat,
        payload=payload,
        structure_type="C",
        mechanism="M2",
    )
    assert patched["dialogue"] == chat["dialogue"]
    assert notes == []


def test_patch_m2_c_structure_layers():
    from app.services.gold_story.gold_chat.patch import (
        patch_m2_c_structure,
    )

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
    before = [str(r["line"]) for r in chat["dialogue"]]
    patched, notes = patch_m2_c_structure(
        chat,
        structure_type="C",
        mechanism="M2",
        theme="八百个心眼子",
    )
    assert patched["punchline_explain"].startswith("C类")
    assert "你刚说" in patched["dialogue"][1]["line"]
    assert "之前说过" in patched["dialogue"][3]["line"]
    # 不本地编 C1 / 回旋镖句；缺则只记 note
    assert "M2+C补C1争归属" not in notes
    assert "M2+C末段回旋镖" not in notes
    assert any("缺末段回旋镖" in n or "缺C1" in n for n in notes)
    # 原稿末句点题不被模板覆盖
    assert patched["dialogue"][-1]["line"] == before[-1]


def test_patch_m5_retaliation_does_not_inject_plot():
    from app.services.gold_story.gold_chat.patch import (
        patch_ensure_chorus_bukeda,
        patch_ensure_injury_after_push,
        patch_fix_mom_ask_admission,
        patch_m5_insert_authority_before_mom,
        patch_m5_pre_mom_escalation,
        patch_m5_retaliation_action,
        patch_m2_c_ensure_seed_close,
        patch_m2_c_fix_opening,
        patch_gold_chat_c_seed_bridge,
    )

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "我也要撕你的！"},
            {"speaker": "昭昭", "line": "你敢！"},
        ]
    }
    patched, changed = patch_m5_retaliation_action(
        story,
        conflict_text="灿灿受害，昭昭弄坏画画",
    )
    assert changed is False
    assert patched["dialogue"] == story["dialogue"]
    for fn in (
        patch_ensure_injury_after_push,
        patch_m5_pre_mom_escalation,
        patch_fix_mom_ask_admission,
    ):
        out, ch = fn(story)
        assert ch is False
        assert out is story or out["dialogue"] == story["dialogue"]
    out, ch = patch_ensure_chorus_bukeda(story, closing_intent="齐声不打了")
    assert ch is False
    out, ch = patch_m5_insert_authority_before_mom(story)
    assert ch is False
    out, notes = patch_m2_c_fix_opening(story)
    assert notes == []
    out, notes = patch_m2_c_ensure_seed_close(story)
    assert notes == []
    out, notes = patch_gold_chat_c_seed_bridge(
        story, structure_type="C", mechanism="M2"
    )
    assert notes == []


def test_m2_c_snack_rebuild_fallback_eligible():
    from app.services.gold_story.gold_chat.patch import (
        m2_c_snack_rebuild_fallback_eligible,
    )

    short = {
        "dialogue": [
            {"speaker": "灿灿", "line": "零食归我。"},
            {"speaker": "昭昭", "line": "本子归我。"},
        ]
    }
    assert m2_c_snack_rebuild_fallback_eligible(
        short, last_err="structure_score:40"
    )
    assert not m2_c_snack_rebuild_fallback_eligible(
        short, last_err="random_fail"
    )
    meat = {
        "dialogue": [
            {"speaker": "昭昭", "line": "给我夹一块肉。"},
            {"speaker": "灿灿", "line": "你刚才说不爱吃。"},
            {"speaker": "昭昭", "line": "我明天不吃零食了，换一口肉。"},
            {"speaker": "灿灿", "line": "今天的肉我说了算。"},
            {"speaker": "妈妈", "line": "吃商谁能比得过我。"},
            {"speaker": "昭昭", "line": "八百个心眼子。"},
            {"speaker": "灿灿", "line": "真香。"},
            {"speaker": "昭昭", "line": "你刚说不爱吃，说不通！"},
            {"speaker": "灿灿", "line": "下次还这样。"},
            {"speaker": "昭昭", "line": "哼。"},
            {"speaker": "灿灿", "line": "嘿嘿。"},
            {"speaker": "昭昭", "line": "行吧。"},
        ]
    }
    assert not m2_c_snack_rebuild_fallback_eligible(
        meat, last_err="structure_score:40"
    )
    full_lines = [
        "沙发上这包零食归我，作业本归你，公平吧？",
        "凭什么你偷吃我的零食还定规矩？",
        "谁拿到算谁的才算数，你抢不到。",
        "那我拿到作业本，本子归我才算？",
        "本子不算！还得我攥手里才算真正归我。",
        "你一条接一条说，哪条作数啊？",
        "你敢撕本子，我就把零食全吃光！",
        "之前说过的，规矩是你自己定的。",
        "你撕了我也交不了差，零食你也保不住！",
        "那我先不撕，你还认不认这规矩？",
        "认什么呀，零食本来就是我的。",
        "本子我放下了，你说话算不算数？",
        "别撕啦，零食给你还不行吗。",
        "你刚说「零食归我，作业本归你」，说不通！",
        "下次我还这样，你管不着！",
    ]
    full = {
        "dialogue": [
            {
                "speaker": "灿灿" if i % 2 == 0 else "昭昭",
                "line": ln,
            }
            for i, ln in enumerate(full_lines)
        ]
    }
    assert not m2_c_snack_rebuild_fallback_eligible(
        full, last_err="structure_score:40"
    )


def test_patch_m2_c_structure_does_not_rebuild_snack_draft():
    """零食+作业语境：structure normalize 不得整篇替换成 15 句模板。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_m2_c_snack_beat_rebuild,
        patch_m2_c_structure,
    )

    original_lines = [
        "沙发上这包零食归我，作业本归你，公平吧？",
        "凭什么你偷吃我的零食还定规矩？",
        "谁拿到算谁的才算数，你抢不到。",
        "那我拿到作业本，本子归我才算？",
        "本子不算！还得我攥手里才算真正归我。",
        "你一条接一条说，哪条作数啊？",
        "你敢撕本子，我就把零食全吃光！",
        "之前说过的，规矩是你自己定的。",
        "你撕了我也交不了差，零食你也保不住！",
        "那我先不撕，你还认不认这规矩？",
        "认什么呀，零食本来就是我的。",
        "本子我放下了，你说话算不算数？",
        "别撕啦，零食给你还不行吗。",
        "你刚说「零食归我，作业本归你」，说不通！",
        "下次我还这样，你管不着！",
    ]
    speakers = [
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
    ]
    chat = {
        "scene_title": "零食作业战",
        "setting": "家中客厅，灿灿端着零食盒，昭昭攥着作业本",
        "conflict_core": "灿灿拿零食定规矩，昭昭用作业本回旋镖",
        "punchline_explain": "C类：昭昭用灿灿刚立的规矩回旋镖堵住。",
        "story_type": "C",
        "dialogue": [
            {"speaker": sp, "line": ln}
            for sp, ln in zip(speakers, original_lines)
        ],
    }
    before = list(original_lines)
    patched, notes = patch_m2_c_structure(
        chat,
        structure_type="C",
        mechanism="M2",
        theme="零食作业战",
    )
    after = [str(r.get("line") or "") for r in patched["dialogue"]]
    assert "M2+C零食战beat重建" not in notes
    assert all("beat重建" not in n for n in notes)
    assert len(after) == len(before)
    # 末句不得被模板默认句覆盖（normalize 可改嘴硬，但不应整篇 rebuild）
    assert after[-1] != "下次我先写在纸上，看你怎么钻空子啊。"
    rebuilt, rebuild_notes = patch_m2_c_snack_beat_rebuild(chat)
    assert "M2+C零食战beat重建" in rebuild_notes
    assert after != [str(r.get("line") or "") for r in rebuilt["dialogue"]]


def test_apply_gold_chat_body_pipeline_via_story_types():
    from app.services.daily_story.story_types import (
        apply_gold_chat_body_pipeline,
        apply_gold_chat_type_patch,
        gold_chat_type_revision_hint,
    )

    chat = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我先说一句。"},
            {"speaker": "灿灿", "line": "我说了算呀。"},
        ],
        "setting": "家里客厅",
    }
    patched, notes = apply_gold_chat_body_pipeline(
        chat, structure_type="C"
    )
    assert patched.get("story_type") == "C"
    assert isinstance(notes, list)
    typed, _ = apply_gold_chat_type_patch(chat, structure_type="J")
    assert typed.get("story_type") == "J"
    hint = gold_chat_type_revision_hint("J")
    assert "冲突升级" in hint or "收束修订" in hint or hint == ""

    a_brush = gold_chat_type_revision_hint("A", theme="姐姐嫌弟弟刷牙太快")
    assert "先溅脸" not in a_brush
    assert "再丢检查不算吃" not in a_brush
    assert "依据本场留下的可见证据" in a_brush
    a_fruit = gold_chat_type_revision_hint(
        "A", theme="姐姐教弟弟洗水果，自己却没洗干净"
    )
    assert "先溅脸" not in a_fruit
    assert "再丢检查不算吃" not in a_fruit
    a_phone = gold_chat_type_revision_hint(
        "A", theme="姐姐不许弟弟偷拿手机，自己却偷偷拿来玩"
    )
    assert "先溅脸" not in a_phone
    assert "再丢检查不算吃" not in a_phone
    assert "依据本场留下的可见证据" in a_phone
    a_steal = gold_chat_type_revision_hint("A", theme="不许饭前偷吃自己却先捏")
    assert "先溅脸" not in a_steal
    assert "再丢检查不算吃" not in a_steal
    assert "依据本场留下的可见证据" in a_steal

    d_water = gold_chat_type_revision_hint("D", theme="浇花别浇太多水")
    assert "上手来解了" not in d_water
    assert "赶紧解开" not in d_water
    d_knot = gold_chat_type_revision_hint("D", theme="姐姐让弟弟把鞋带系紧")
    assert "上手来解了" in d_knot


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


def test_m2_c_milk_story_skips_meat_seed_close():
    """#23 牛奶公平：勿注入吃商/八百个心眼子收束。"""
    from app.services.gold_story.gold_chat.patch import (
        m2_c_meat_whole_item_context,
        patch_m2_c_ensure_seed_close,
        patch_gold_chat_c_seed_bridge,
    )

    payload = {
        "scene_contract": {
            "object": "一瓶牛奶",
            "conflict": "灿灿：我不想喝了！",
        },
    }
    chat = {
        "scene_title": "公平的陷阱",
        "setting": "客厅，桌上放着一瓶未开封的牛奶",
        "conflict_core": "爸爸想用牛奶安抚女儿，却被女儿用逻辑反将一军",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，这瓶该给我，我都喝过一瓶了。"},
            {"speaker": "昭昭", "line": "好吧，给你。"},
            {"speaker": "灿灿", "line": "我不想喝了，你自己留着吧。"},
            {"speaker": "昭昭", "line": "啊？你刚才不是说要吗？"},
            {"speaker": "灿灿", "line": "我现在不想喝了。"},
            {"speaker": "昭昭", "line": "你这算哪门子公平？"},
            {"speaker": "灿灿", "line": "公平就是你让了，我就不喝了。"},
            {"speaker": "昭昭", "line": "妈妈刚才明明偏向你。"},
            {"speaker": "妈妈", "line": "行了行了，都别吵。"},
            {"speaker": "昭昭", "line": "这退让里全是套路。"},
            {"speaker": "灿灿", "line": "套路也是你让出来的。"},
            {"speaker": "昭昭", "line": "行，我认输还不行吗。"},
        ],
    }
    assert m2_c_meat_whole_item_context(chat, payload=payload) is False
    patched, notes = patch_m2_c_ensure_seed_close(chat, payload=payload)
    assert patched["dialogue"] == chat["dialogue"]
    assert "M2+C补" not in "".join(notes)
    bridged, bnotes = patch_gold_chat_c_seed_bridge(
        chat,
        structure_type="C",
        mechanism="M2",
        payload=payload,
    )
    assert bridged["dialogue"] == chat["dialogue"]
    assert bnotes == []


def test_narration_line_detects_stage_direction():
    from app.services.gold_story.scene import (
        looks_like_narration_line,
        patch_dialogue_narration_to_speech,
        rewrite_narration_to_speech,
        sanitize_dialogue_seed_speech,
    )

    assert looks_like_narration_line("一把揪住昭昭衣领，警告你别逼我呀。")
    assert looks_like_narration_line("挣扎着还手，被灿灿按在地上。")
    assert looks_like_narration_line("叹气，劝不动你们了。")
    assert not looks_like_narration_line("你松手！我喊妈了！")
    assert not looks_like_narration_line("你别戳我腰！疼！")
    assert not looks_like_narration_line(
        "放开我！你挠我痒痒算什么本事！"
    )

    # 分镜入对白（抽象形态）
    assert looks_like_narration_line(
        "逮住你了，按在沙发上，看你还跑！"
    )
    assert looks_like_narration_line("不放，你抢我笔还做鬼脸，继续挠！")
    assert not looks_like_narration_line("你抓我胳膊干嘛，放开我！")

    # 动作/神态说明混入对白（抽象）
    assert looks_like_narration_line("我拎起行李袋，鞋跟一踩就出门，不回头。")
    assert looks_like_narration_line("对视一眼，气全消了，走，楼下便利店。")
    assert looks_like_narration_line("笑出声，那你还不是跟我一路。")
    assert looks_like_narration_line("电梯里沉默几秒，我先开口：你去哪？")
    assert looks_like_narration_line("电梯口撞见她，我俩都愣住，谁也没动。")
    assert not looks_like_narration_line("你去哪？我怕你一个人走！")

    ask = rewrite_narration_to_speech(
        "电梯里沉默几秒，我先开口：你去哪？",
        speaker="灿灿",
    )
    assert ask.startswith("你去哪")
    assert "沉默" not in ask
    assert "开口" not in ask

    laugh = rewrite_narration_to_speech(
        "笑出声，那你还不是跟我一路。",
        speaker="昭昭",
    )
    assert "笑出声" not in laugh
    assert "跟我一路" in laugh or "不是" in laugh

    gaze = rewrite_narration_to_speech(
        "对视一眼，气全消了，走，楼下便利店。",
        speaker="灿灿",
    )
    assert "对视" not in gaze
    assert "气全消" not in gaze
    assert "便利店" in gaze or "走" in gaze

    sofa = rewrite_narration_to_speech(
        "逮住你了，按在沙发上，看你还跑！",
        speaker="灿灿",
    )
    assert "按在沙发" not in sofa
    assert "逮住" in sofa or "还跑" in sofa

    cont = rewrite_narration_to_speech(
        "不放，你抢我笔还做鬼脸，继续挠！",
        speaker="灿灿",
    )
    assert "继续挠" not in cont
    assert "不放" in cont or "抢" in cont

    spoken = rewrite_narration_to_speech(
        "一把揪住昭昭衣领，警告你别逼我呀。",
        speaker="灿灿",
    )
    assert "揪住" not in spoken
    assert "别逼我" in spoken or "别过来" in spoken

    ask = rewrite_narration_to_speech(
        "站直了叉腰问：还不哭！",
        speaker="灿灿",
    )
    assert "还不哭" in ask
    assert "站直" not in ask and "叉腰" not in ask

    tickle = rewrite_narration_to_speech(
        "手指戳你腰侧，看你还嘴硬不嘴硬！",
        speaker="灿灿",
    )
    assert "嘴硬" in tickle
    assert "手指戳" not in tickle

    stare = rewrite_narration_to_speech(
        "抽抽搭搭抹眼泪，瞪灿灿一眼不说话。",
        speaker="昭昭",
    )
    assert stare == "哼！"

    mom_laugh = rewrite_narration_to_speech(
        "从厨房探头看到这一幕笑出声",
        speaker="妈妈",
    )
    assert "笑" in mom_laugh or "闹" in mom_laugh
    assert "探头" not in mom_laugh

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "挣扎着还手，被灿灿按在地上。"},
            {"speaker": "妈妈", "line": "叹气，劝不动你们了。"},
            {"speaker": "灿灿", "line": "站直了叉腰问：还不哭！"},
        ]
    }
    notes = patch_dialogue_narration_to_speech(story)
    assert notes
    assert not looks_like_narration_line(story["dialogue"][0]["line"])
    assert not looks_like_narration_line(story["dialogue"][1]["line"])
    assert "还不哭" in story["dialogue"][2]["line"]

    seed = sanitize_dialogue_seed_speech(
        [
            {"speaker": "灿灿", "intent": "一把将昭昭按倒在沙发上"},
            {"speaker": "灿灿", "intent": "手指戳昭昭腰侧开始挠痒痒"},
            {"speaker": "妈妈", "intent": "从厨房探头看到这一幕笑出声"},
        ]
    )
    assert "按倒" not in str(seed[0].get("intent"))
    assert "手指戳" not in str(seed[1].get("intent"))
    assert "探头" not in str(seed[2].get("intent"))


def test_validate_gold_chat_rejects_narration_line():
    from app.services.gold_story.gold_chat.convert import validate_gold_chat

    story = {
        "scene_title": "公平的陷阱",
        "setting": "客厅",
        "key": "公平陷阱",
        "conflict_core": "牛奶公平反转",
        "punchline_explain": "C类：退让揭穿偏心",
        "dialogue": [
            {"speaker": "灿灿" if i % 2 == 0 else "昭昭", "line": f"对白测试句{i}，够长。"}
            for i in range(12)
        ],
    }
    story["dialogue"][2] = {
        "speaker": "灿灿",
        "line": "松手，把牛奶推向灿灿。",
    }
    try:
        validate_gold_chat(story)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "narration_not_speech" in str(exc)


def test_q_patch_binds_cheat_speaker_and_strips_pads():
    import re

    from app.services.daily_story.story_types.q.patch import patch_q_body
    from app.services.daily_story.story_types.q.validate import append_q_body_errors
    from app.services.gold_story.scene import (
        looks_like_narration_line,
        patch_dialogue_narration_to_speech,
        rewrite_narration_to_speech,
    )

    assert looks_like_narration_line(
        "一口吞下泡芙，奶油都挤出来嘛，说一不二！"
    )
    spoken = rewrite_narration_to_speech(
        "一口吞下泡芙，奶油都挤出来嘛，说一不二！",
        speaker="灿灿",
    )
    assert "吞下泡芙" not in spoken
    assert "看我" in spoken or "一口吞" in spoken
    assert not looks_like_narration_line(spoken)

    story = {
        "story_type": "Q",
        "conflict_core": "灿灿抽签耍赖，借口胃小推食，妈妈看穿让洗碗",
        "punchline_explain": "Q类耍赖翻车",
        "dialogue_seed": [
            {"speaker": "灿灿", "intent": "太少，重抽"},
            {"speaker": "灿灿", "intent": "嘴硬不认偷吃"},
            {"speaker": "灿灿", "intent": "胃小吃不下，剩的给你"},
            {"speaker": "妈妈", "intent": "看穿心思，让她洗碗"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "三口太少啦，我要重抽嘛！"},
            {"speaker": "昭昭", "line": "八口才够嘛，这次满意吧！"},
            {
                "speaker": "灿灿",
                "line": "一口吞下泡芙，奶油都挤出来嘛，说一不二！",
            },
            {"speaker": "昭昭", "line": "辣面真香，我还能再来几口吧，我才不怕呢！"},
            {"speaker": "灿灿", "line": "我才没耍赖！"},
            {"speaker": "昭昭", "line": "你昨天偷吃辣条了！"},
            {"speaker": "灿灿", "line": "就一根，不算偷吃！"},
            {"speaker": "昭昭", "line": "还装呢！"},
            {"speaker": "灿灿", "line": "真的不辣！"},
            {"speaker": "昭昭", "line": "不行好不好，我偏就不信！"},
            {"speaker": "昭昭", "line": "哎呀，胃小装不下，剩的给你了呢。"},
            {"speaker": "妈妈", "line": "看穿你小心思，吃完去洗碗吧。"},
        ],
    }
    patch_dialogue_narration_to_speech(story)
    notes = patch_q_body(story)
    assert any("归位" in n for n in notes)
    speakers_cheat = [
        d["speaker"]
        for d in story["dialogue"]
        if d["speaker"] in {"昭昭", "灿灿"}
        and (
            "胃小" in d["line"]
            or "才够" in d["line"]
            or "我还能" in d["line"]
        )
    ]
    assert speakers_cheat
    assert all(sp == "灿灿" for sp in speakers_cheat)
    mom = next(d for d in story["dialogue"] if d["speaker"] == "妈妈")
    assert re.search(r"推|胃", mom["line"])
    errs: list[str] = []
    append_q_body_errors(story, errs)
    assert errs == []


def test_q_consecutive_does_not_steal_cheat_lines():
    from app.services.daily_story.prompts import _patch_consecutive_speakers
    from app.services.daily_story.story_types.q.validate import append_q_body_errors

    story = {
        "story_type": "Q",
        "conflict_core": "灿灿抽签耍赖借口胃小推食",
        "punchline_explain": "Q类耍赖翻车",
        "dialogue": [
            {"speaker": "灿灿", "line": "三口太少，我要重抽！"},
            {"speaker": "灿灿", "line": "胃小装不下，剩的给你！"},
            {"speaker": "昭昭", "line": "看穿了，别装！"},
            {"speaker": "妈妈", "line": "推食的小心思，去洗碗！"},
        ],
    }
    notes = _patch_consecutive_speakers(story)
    assert any("Q插接话" in n for n in notes)
    assert story["dialogue"][0]["speaker"] == "灿灿"
    assert "胃小" in story["dialogue"][2]["line"]
    assert story["dialogue"][2]["speaker"] == "灿灿"
    errs: list[str] = []
    append_q_body_errors(story, errs)
    assert not any("抢戏" in e for e in errs)
