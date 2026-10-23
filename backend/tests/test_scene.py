"""H3a scene_contract 与成品对白 hard 校验测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat.validate import (
    validate_chat_hard,
)
from app.services.gold_story.scene import (
    DIALOGUE_TURNS_MIN,
    apply_parent_role_budget,
    complete_request_premises,
    ensure_request_premise_dialogue,
    fact_attribution_review_required,
    filter_fact_bound_rows,
    format_scene_block,
    has_dialogue_meta_label,
    normalize_beat_min_turns,
    normalize_dialogue_setting_for_contract,
    normalize_fact_attributions,
    ensure_origin_ask_answerable,
    split_n_token_from_explanation,
    normalize_cast_to_beats,
    normalize_k_parent_intervention_budget,
    normalize_n_formula_slots,
    ensure_n_two_kid_alternation,
    normalize_parent_beat_ownership,
    normalize_retrospective_topic_contract,
    normalize_retrospective_n_opening_parent_beats,
    normalize_scene_dialogue_beats,
    scene_contract_reuse_issues,
    parent_identity_claim_target,
    realign_parent_identity_rows,
    remap_story_raw_sibling_roles,
    seed_from_beat_chain,
    sanitize_dialogue_meta_label_suffix,
    is_terminal_no_reply_intent,
    needs_second_kid,
    trim_n_decorative_kid_seed,
    trim_terminal_no_reply_rows,
    validate_scene,
)


def test_remap_story_raw_sibling_roles_swapped_names():
    """源稿姐姐叫昭昭、弟弟叫灿灿时，按角色映到站内名。"""
    raw = (
        "客厅里，姐姐昭昭正写着作业，弟弟灿灿突然冲过来抢走了她的笔。"
        "昭昭追着弟弟满屋子跑，逮住他按在沙发上挠痒痒。"
        "灿灿笑出眼泪大哭。昭昭叉腰问还不哭？灿灿抽泣不敢再闹。"
    )
    out = remap_story_raw_sibling_roles(raw)
    assert "姐姐昭昭" not in out
    assert "弟弟灿灿" not in out
    assert "满屋子跑" in out
    assert "灿灿正写着作业" in out
    assert "昭昭突然冲过来" in out
    assert "灿灿追着昭昭满屋子跑" in out
    assert "昭昭笑出眼泪大哭" in out
    assert "灿灿叉腰问还不哭" in out
    assert "昭昭抽泣" in out


def test_remap_story_raw_sibling_roles_already_canonical():
    raw = "灿灿抢回笔后把昭昭按在沙发上挠痒痒，问还不哭。"
    assert remap_story_raw_sibling_roles(raw) == raw


def test_complete_request_premises_appends_same_beat_without_seed_insert():
    """P1：否定结果缺请求前因时，并进前一拍；seed 行数/顺序不变。"""
    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "问是不是弄脏了衣服、谁的"},
            {
                "beat": 2,
                "speaker": "昭昭",
                "intent": "回答是自己的衣服，但说没有帮忙弄干净，因为疼妈妈",
            },
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "是不是把衣服弄脏了？"},
        {"speaker": "昭昭", "intent": "是我自己的衣服。"},
        {"speaker": "昭昭", "intent": "我没帮忙弄干净，因为我疼你。"},
    ]
    out, seed_out, notes = complete_request_premises(
        contract,
        seed,
        story_raw="妈妈让他帮忙弄干净，昭昭说没有。",
    )
    assert notes
    assert "主动帮昭昭弄干净" in out["beat_chain"][0]["intent"]
    assert "想自己弄干净" in out["beat_chain"][1]["intent"]
    assert len(seed_out) == len(seed)
    assert [r["speaker"] for r in seed_out] == [r["speaker"] for r in seed]
    assert "主动帮昭昭弄干净" in seed_out[0]["intent"]
    assert seed_out[2]["intent"] == "我疼你，才想自己弄干净，不让你操心。"


def test_complete_request_premises_negative_and_idempotent():
    """P1：story_raw 没有请求事件不补；重复调用不叠加 clause。"""
    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "问衣服是谁的"},
            {"beat": 2, "speaker": "昭昭", "intent": "说没帮忙弄干净"},
        ],
    }
    seed = [{"speaker": "昭昭", "intent": "我没帮忙弄干净。"}]
    same, same_seed, notes = complete_request_premises(
        contract,
        seed,
        story_raw="妈妈问衣服是谁的，昭昭说没帮忙弄干净。",
    )
    assert not notes and same is contract and same_seed == seed

    story_raw = "妈妈让他帮忙弄干净，昭昭说没有。"
    out1, seed1, notes1 = complete_request_premises(contract, seed, story_raw=story_raw)
    out2, seed2, notes2 = complete_request_premises(out1, seed1, story_raw=story_raw)
    assert notes1 and not notes2
    assert out2 == out1 and seed2 == seed1


def test_ensure_request_premise_dialogue_rewrites_parent_without_insert():
    """孩子复述请求时，前一句家长必须真的说过请求；只改该行不插行。"""
    story = {
        "dialogue": [
            {
                "speaker": "妈妈",
                "line": "你说，你是不是把衣服弄脏了？弄脏的是谁的衣服？",
            },
            {"speaker": "昭昭", "line": "是我弄脏的，弄脏的是我自己的衣服呀。"},
            {
                "speaker": "昭昭",
                "line": "你让我帮忙弄干净，我没照做，因为我疼你啊。",
            },
        ]
    }
    seed = [
        {"speaker": "妈妈", "intent": "问衣服是谁的；并让昭昭帮忙弄干净"},
        {
            "speaker": "昭昭",
            "intent": "你让我帮忙弄干净，我没照做，因为我疼你啊。",
        },
    ]
    before_speakers = [row["speaker"] for row in story["dialogue"]]

    out, notes = ensure_request_premise_dialogue(
        story,
        dialogue_seed=seed,
    )

    assert notes
    assert [row["speaker"] for row in out["dialogue"]] == before_speakers
    assert len(out["dialogue"]) == 3
    assert out["dialogue"][0]["line"] == (
        "妈妈不该骂你，弄脏的是谁的衣服？我来弄干净吧。"
    )
    assert out["dialogue"][2]["line"] == (
        "我疼你，才想自己弄干净，不让你操心。"
    )
    same, again = ensure_request_premise_dialogue(out, dialogue_seed=seed)
    assert not again and same is out


def test_ensure_request_premise_dialogue_handles_affection_refusal():
    """模型未复述原请求、只写「我不弄，因为疼你」时也要补成可理解因果。"""
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "弄脏的是谁的衣服？你弄干净。"},
            {"speaker": "昭昭", "line": "我不弄，因为我疼你啊。"},
        ]
    }
    seed = [
        {
            "speaker": "昭昭",
            "intent": "你让我帮忙弄干净，我没照做，因为我疼你啊。",
        }
    ]
    out, notes = ensure_request_premise_dialogue(story, dialogue_seed=seed)
    assert notes
    assert out["dialogue"][0]["line"] == (
        "妈妈不该骂你，弄脏的是谁的衣服？我来弄干净吧。"
    )
    assert out["dialogue"][1]["line"] == (
        "我疼你，才想自己弄干净，不让你操心。"
    )


def _sample_contract() -> dict:
    return {
        "source_type": "field",
        "location": "客厅",
        "object": "遥控器",
        "characters": ["昭昭", "灿灿"],
        "conflict": "抢遥控器",
        "mechanism": "M2",
        "mom_lines_max": 0,
        "remap_note": "姐弟→昭昭灿灿",
        "beat_chain": [
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        "closing_intent": "嘴硬收束",
        "contract_confidence": 0.8,
    }


def test_validate_scene_ok():
    assert validate_scene(_sample_contract()) == []


def test_scene_contract_reuse_rejects_stale_witness_layout():
    """去见证位后主孩子连拍 = 旧搭法，应重建契约。"""
    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备"},
            {"beat": 2, "speaker": "昭昭", "intent": "反问"},
            {"beat": 3, "speaker": "灿灿", "intent": "我就在旁边听着，你慢慢说。"},
            {"beat": 4, "speaker": "昭昭", "intent": "解释"},
            {"beat": 5, "speaker": "妈妈", "intent": "追问"},
        ],
    }
    issues = scene_contract_reuse_issues(contract)
    assert any("孩子连续拍" in item for item in issues)

    contract["beat_chain"][3]["speaker"] = "妈妈"
    assert scene_contract_reuse_issues(contract) == []


def test_scene_contract_reuse_rejects_unestablished_external_threat():
    """护短拍写「别人碰一下试试」但全场只有家里人：旧契约应重建。"""
    contract = {
        "story_type": "G",
        "characters": ["灿灿", "昭昭", "妈妈"],
        "beat_chain": [
            {"beat": 1, "speaker": "灿灿", "intent": "灿灿追着昭昭要打"},
            {"beat": 2, "speaker": "昭昭", "intent": "昭昭还手，说遥控器是灿灿先抢的"},
            {"beat": 3, "speaker": "妈妈", "intent": "妈妈拉开两人，骂灿灿不该打弟弟"},
            {"beat": 4, "speaker": "灿灿", "intent": "灿灿护短，说我弟只有我能打，别人碰一下试试"},
        ],
    }
    issues = scene_contract_reuse_issues(contract)
    assert any("外部威胁" in item for item in issues)

    # 契约里真有外部角色时，这句话不算未建立的前提。
    contract["characters"] = ["灿灿", "昭昭", "妈妈", "同学"]
    assert scene_contract_reuse_issues(contract) == []


def test_scene_contract_reuse_keeps_n_alternation_exception():
    contract = {
        "story_type": "N",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"speaker": "妈妈", "intent": "追问"},
            {"speaker": "昭昭", "intent": "解释"},
            {"speaker": "昭昭", "intent": "补充"},
        ],
    }
    assert scene_contract_reuse_issues(contract) == []


def test_validate_scene_rejects_short_chain():
    bad = {**_sample_contract(), "beat_chain": [{"speaker": "昭昭", "intent": "a"}]}
    errs = validate_scene(bad)
    assert any("beat_chain" in e for e in errs)


def test_normalize_beat_min_turns_lifts_total_to_dialogue_floor():
    out, notes = normalize_beat_min_turns(_sample_contract())
    turns = [row["min_turns"] for row in out["beat_chain"]]
    assert sum(turns) == DIALOGUE_TURNS_MIN
    assert all(1 <= t <= 3 for t in turns)
    assert notes and "最小回合数抬额" in notes[0]
    assert validate_scene(out) == []


def test_normalize_beat_min_turns_keeps_declared_when_enough():
    contract = _sample_contract()
    contract["beat_chain"] = [
        {**row, "min_turns": 3} for row in contract["beat_chain"]
    ]
    out, notes = normalize_beat_min_turns(contract)
    assert [row["min_turns"] for row in out["beat_chain"]] == [3, 3, 3, 3]
    assert notes == []
    assert validate_scene(out) == []


def test_validate_scene_rejects_out_of_range_min_turns():
    contract = _sample_contract()
    contract["beat_chain"] = [
        {**row, "min_turns": 9} for row in contract["beat_chain"]
    ]
    assert any(
        "min_turns_invalid" in e for e in validate_scene(contract)
    )


def test_validate_scene_rejects_insufficient_declared_turns():
    contract = _sample_contract()
    contract["beat_chain"] = [
        {**row, "min_turns": 1} for row in contract["beat_chain"]
    ]
    assert any(
        "beat_chain_turns_insufficient" in e for e in validate_scene(contract)
    )


def test_format_beat_chain_marks_turn_quota():
    from app.services.gold_story.scene import format_beat_chain

    text = format_beat_chain(
        [
            {"speaker": "灿灿", "intent": "占物", "min_turns": 1},
            {"speaker": "昭昭", "intent": "争抢", "min_turns": 3},
        ]
    )
    assert "（须≥3个回合）" in text
    assert "占物" in text


def test_format_scene_block():
    block = format_scene_block(_sample_contract())
    assert "scene_contract" in block
    assert "昭昭" in block
    assert "beat_chain" in block


def test_seed_from_beat_chain():
    seed = seed_from_beat_chain(_sample_contract()["beat_chain"])
    assert len(seed) == 4
    assert seed[0]["speaker"] == "灿灿"


def test_scene_trims_terminal_no_reply_beat_after_punchline():
    contract = {
        **_sample_contract(),
        "story_type": "J",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "重提旧事：五岁掉进菜篓子"},
            {"beat": 2, "speaker": "灿灿", "intent": "补刀：扒出来还问吃饭了吗"},
            {"beat": 3, "speaker": "妈妈", "intent": "定性：这就是天生命大"},
            {"beat": 4, "speaker": "昭昭", "intent": "嘴硬：那是我会挑地方落"},
            {"beat": 5, "speaker": "灿灿", "intent": "被一锤镇住，低头剥橘子不接话"},
        ],
        "closing_intent": "昭昭一句会挑地方落镇住全场，妈妈和灿灿都不再顶",
    }
    out, notes = normalize_scene_dialogue_beats(contract)
    assert notes
    assert len(out["beat_chain"]) == 4
    assert out["beat_chain"][-1]["speaker"] == "昭昭"
    assert out["beat_chain"][-1]["beat"] == 4
    assert "会挑地方落" in out["beat_chain"][-1]["intent"]
    assert validate_scene(out) == []


def test_validate_scene_rejects_untrimmed_terminal_no_reply_beat():
    bad = {
        **_sample_contract(),
        "beat_chain": [
            *_sample_contract()["beat_chain"],
            {"speaker": "灿灿", "intent": "低头不接话"},
        ],
    }
    assert "beat_chain_terminal_no_reply_not_dialogue" in validate_scene(bad)


def test_seed_from_beat_chain_does_not_turn_terminal_silence_into_dialogue():
    chain = [
        {"speaker": "妈妈", "intent": "重提旧事"},
        {"speaker": "灿灿", "intent": "补刀追问"},
        {"speaker": "妈妈", "intent": "定性命大"},
        {"speaker": "昭昭", "intent": "那是我会挑地方落"},
        {"speaker": "灿灿", "intent": "被镇住，低头剥橘子不接话"},
    ]
    seed = seed_from_beat_chain(chain)
    assert len(seed) == 4
    assert seed[-1]["speaker"] == "昭昭"
    assert "会挑地方落" in seed[-1]["intent"]


def test_terminal_no_reply_does_not_match_dialogue_answer_intent():
    assert not is_terminal_no_reply_intent("回答：你怎么不说话了？")
    assert not is_terminal_no_reply_intent("作答：你怎么还不接话？")


def test_trim_terminal_no_reply_keeps_seed_with_spoken_line():
    seed = [
        {"speaker": "灿灿", "intent": "灵魂拷问", "line": "你怎么还不说话？"},
        {
            "speaker": "昭昭",
            "intent": "回答：你怎么不说话了？",
            "line": "我刚才就是在认真想怎么回答你。",
        },
    ]
    out, notes = trim_terminal_no_reply_rows(seed)
    assert notes == []
    assert len(out) == 2
    assert out[-1]["line"].startswith("我刚才")


def test_trim_terminal_no_reply_keeps_mid_scene_silence_reaction():
    seed = [
        {"speaker": "灿灿", "intent": "灵魂拷问"},
        {"speaker": "昭昭", "intent": "无言以对，委屈看窗外"},
        {"speaker": "灿灿", "intent": "一招制敌"},
        {"speaker": "昭昭", "intent": "低头不接话"},
    ]
    out, notes = trim_terminal_no_reply_rows(seed)
    assert notes == ["低头不接话"]
    assert len(out) == 3
    assert "无言以对" in out[1]["intent"]


def test_retrospective_n_merges_consecutive_parent_exposition_beats():
    contract = {
        **_sample_contract(),
        "story_type": "N",
        "object": "昭昭五岁坠楼被菜篓子接住的旧事",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "重提旧事：五岁掉进菜篓子"},
            {"beat": 2, "speaker": "妈妈", "intent": "定论：这就是天生命大"},
            {"beat": 3, "speaker": "昭昭", "intent": "反驳：那是我会挑地方落"},
            {"beat": 4, "speaker": "灿灿", "intent": "追问：怎么挑的"},
            {"beat": 5, "speaker": "昭昭", "intent": "一本正经讲圆"},
        ],
    }
    out, notes = normalize_retrospective_n_opening_parent_beats(contract)
    assert notes
    assert len(out["beat_chain"]) == 4
    assert out["beat_chain"][0]["speaker"] == "妈妈"
    assert "重提旧事" in out["beat_chain"][0]["intent"]
    assert "天生命大" in out["beat_chain"][0]["intent"]
    assert out["beat_chain"][1]["speaker"] == "昭昭"
    assert [x["beat"] for x in out["beat_chain"]] == [1, 2, 3, 4]


def test_retrospective_n_drops_redundant_support_before_rebuttal():
    contract = {
        **_sample_contract(),
        "story_type": "N",
        "object": "昭昭五岁坠楼被菜篓子接住的旧事",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "重提旧事：五岁掉进菜篓子"},
            {"beat": 2, "speaker": "灿灿", "intent": "接话帮腔，说妈妈讲得对，昭昭就是命大"},
            {"beat": 3, "speaker": "昭昭", "intent": "嘴硬反驳：不是命大，是我会挑地方落"},
            {"beat": 4, "speaker": "灿灿", "intent": "追问：怎么挑的"},
            {"beat": 5, "speaker": "昭昭", "intent": "一本正经讲圆"},
        ],
    }
    out, notes = normalize_retrospective_n_opening_parent_beats(contract)
    assert notes == ["移除N回忆开场冗余附和拍:灿灿"]
    assert len(out["beat_chain"]) == 4
    assert out["beat_chain"][1]["speaker"] == "昭昭"
    assert "会挑地方落" in out["beat_chain"][1]["intent"]
    assert [x["beat"] for x in out["beat_chain"]] == [1, 2, 3, 4]


def test_retrospective_topic_drops_materialized_remap_note_and_setting():
    contract = {
        **_sample_contract(),
        "location": "客厅",
        "object": "五岁坠楼被菜篓子接住还睡着的事",
        "remap_note": (
            "五岁孩子映射为昭昭；"
            "坠楼旧事在客厅重演，菜篓子用收纳筐近似替代；"
            "妈妈保留为讲述者"
        ),
    }
    cleaned, notes = normalize_retrospective_topic_contract(contract)
    assert notes
    assert "收纳筐" not in cleaned["remap_note"]
    assert "重演" not in cleaned["remap_note"]
    assert "五岁孩子映射为昭昭" in cleaned["remap_note"]
    assert "妈妈保留为讲述者" in cleaned["remap_note"]

    setting, changed = normalize_dialogue_setting_for_contract(
        "客厅，妈妈端着旧菜篓子站在沙发前",
        cleaned,
    )
    assert changed
    assert setting == "客厅，一家人聊起以前的事"
    assert "菜篓子" not in setting


def test_current_scene_object_keeps_concrete_setting():
    contract = {**_sample_contract(), "object": "遥控器"}
    setting, changed = normalize_dialogue_setting_for_contract(
        "客厅，昭昭拿着遥控器坐在沙发上",
        contract,
    )
    assert not changed
    assert setting == "客厅，昭昭拿着遥控器坐在沙发上"


def test_dialogue_meta_label_suffix_is_removed_but_plain_line_is_kept():
    line = "所以不是命大，是我会挑地方落，一锤定音。"
    assert has_dialogue_meta_label(line)
    assert sanitize_dialogue_meta_label_suffix(line) == "所以不是命大，是我会挑地方落。"
    assert sanitize_dialogue_meta_label_suffix("我就是会挑地方落。") == "我就是会挑地方落。"
    # 整句只有元标签时不机械删成空句，交 hard gate/LLM 修稿。
    assert sanitize_dialogue_meta_label_suffix("一锤定音。") == "一锤定音。"
    assert (
        sanitize_dialogue_meta_label_suffix("哼，一招制敌！撂倒你，听我的！")
        == "哼，撂倒你，听我的！"
    )
    assert (
        sanitize_dialogue_meta_label_suffix("一招制敌！撂倒你，听我的！")
        == "撂倒你，听我的！"
    )


def test_build_dialogue_seed_filters_terminal_silence_and_history_prop(monkeypatch):
    from app.services.gold_story.collect import llm as llm_steps

    contract = {
        **_sample_contract(),
        "location": "客厅",
        "object": "五岁坠楼被菜篓子接住还睡着的事",
        "mom_lines_max": 2,
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "重提五岁掉进菜篓子的旧事"},
            {"beat": 2, "speaker": "灿灿", "intent": "补刀问醒来是不是先问吃饭"},
            {"beat": 3, "speaker": "妈妈", "intent": "定性这就是天生命大"},
            {"beat": 4, "speaker": "昭昭", "intent": "嘴硬说那是我会挑地方落"},
        ],
        "closing_intent": "昭昭一句会挑地方落镇住全场",
    }

    monkeypatch.setattr(
        llm_steps,
        "_chat_json",
        lambda *_a, **_k: {
            "setting": "客厅，妈妈端着旧菜篓子站在沙发前",
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "重提五岁掉进菜篓子的旧事"},
                {"speaker": "灿灿", "intent": "补刀问醒来是不是先问吃饭"},
                {"speaker": "妈妈", "intent": "定性这就是天生命大"},
                {"speaker": "昭昭", "intent": "嘴硬说那是我会挑地方落"},
                {"speaker": "灿灿", "intent": "被镇住，低头剥橘子不接话"},
            ],
            "closing_intent": "昭昭一句会挑地方落镇住全场",
            "speaker_map_note": "",
            "dialogue_confidence": 0.9,
        },
    )
    out = llm_steps.build_dialogue_seed(
        story_raw="一家人聊天时又提起昭昭小时候掉进菜篓子的旧事。" * 3,
        h3={"beat": ["a", "b", "c", "d"]},
        scene_contract=contract,
    )
    assert len(out["dialogue_seed"]) == 4
    assert out["dialogue_seed"][-1]["speaker"] == "昭昭"
    assert "会挑地方落" in out["dialogue_seed"][-1]["intent"]
    assert out["setting"] == "客厅，一家人聊起以前的事"
    assert "菜篓子" not in out["setting"]


def test_force_age_score_remap_rewrites_adult_totals():
    from app.services.gold_story.scene import (
        age_remap_contract_errors,
        force_age_score_remap,
    )

    raw = "姐姐高考考了383分，要是683分妹妹会感谢。"
    contract = {
        "object": "383分成绩单",
        "conflict": "妹妹宣扬姐姐383分，对比683分",
        "mechanism": "宣传高分该谢",
        "beat_chain": [
            {"speaker": "妈妈", "intent": "责备宣扬383分"},
            {"speaker": "昭昭", "intent": "辩称683分会感谢"},
        ],
        "remap_note": "高考迁龄说明可保留字样",
    }
    assert age_remap_contract_errors(raw, contract)
    out, changed = force_age_score_remap(contract, story_raw=raw)
    assert changed
    assert not age_remap_contract_errors(raw, out)
    blob = f"{out['object']}{out['conflict']}{out['beat_chain']}"
    assert "383" not in blob
    assert "683" not in blob
    assert "58分" in blob and "98分" in blob


def test_scrub_h3_beat_list_remaps_sibling_and_score():
    from app.services.gold_story.scene import scrub_h3_beat_list

    beat = ["妹妹宣扬姐姐383分，妈妈责备其戳痛处"]
    out = scrub_h3_beat_list(
        beat,
        story_raw="姐姐高考考了383分，妹妹到处宣扬。",
    )
    assert out[0] == "昭昭宣扬灿灿58分，妈妈责备其戳痛处"


def test_sync_contract_exam_scores_follows_seed_mode():
    from app.services.gold_story.scene import sync_contract_exam_scores

    contract = {
        "conflict": "昭昭到处说姐姐考了58分",
        "object": "58分试卷",
        "remap_note": "58分迁为小学量级",
        "beat_chain": [{"speaker": "妈妈", "intent": "说姐姐83分？"}],
    }
    seed = [{"speaker": "妈妈", "intent": "昭昭，你满小区说姐姐83分？"}]
    out, core, changed = sync_contract_exam_scores(
        contract,
        dialogue_seed=seed,
        conflict_core=contract["conflict"],
    )
    assert changed
    assert "83分" in out["conflict"]
    assert "58分" not in out["conflict"]
    assert "83分" in core


def test_k_parent_budget_merges_same_round_intervention_and_keeps_fail_tail():
    contract = {
        **_sample_contract(),
        "story_type": "K",
        "mom_lines_max": 2,
        "characters": ["昭昭", "灿灿", "妈妈"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "贴个标记止争，想让两人别再抢玩具"},
            {"beat": 2, "speaker": "昭昭", "intent": "伸手去抢新标记"},
            {"beat": 3, "speaker": "灿灿", "intent": "扑过去抢回来"},
            {"beat": 4, "speaker": "妈妈", "intent": "劝架提议一人玩一个，别再抢"},
            {"beat": 5, "speaker": "昭昭", "intent": "继续争抢"},
            {"beat": 6, "speaker": "灿灿", "intent": "争抢升级，东西被扯坏"},
            {"beat": 7, "speaker": "妈妈", "intent": "叹气劝不动，两人继续僵持"},
        ],
    }
    out, notes = normalize_k_parent_intervention_budget(contract)
    assert notes == ["K家长预算2合并同轮干预:妈妈"]
    assert len(out["beat_chain"]) == 6
    moms = [row for row in out["beat_chain"] if row["speaker"] == "妈妈"]
    assert len(moms) == 2
    assert "止争" in moms[0]["intent"]
    assert "一人玩一个" in moms[0]["intent"]
    assert "劝不动" in moms[-1]["intent"]
    assert [row["beat"] for row in out["beat_chain"]] == [1, 2, 3, 4, 5, 6]


def test_k_parent_budget_does_not_merge_distinct_parent_middle_beat():
    contract = {
        **_sample_contract(),
        "story_type": "K",
        "mom_lines_max": 2,
        "characters": ["昭昭", "灿灿", "妈妈"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "贴个标记止争"},
            {"beat": 2, "speaker": "昭昭", "intent": "开抢"},
            {"beat": 3, "speaker": "灿灿", "intent": "回抢"},
            {"beat": 4, "speaker": "妈妈", "intent": "解释这个玩具是谁买的"},
            {"beat": 5, "speaker": "昭昭", "intent": "继续争抢"},
            {"beat": 6, "speaker": "灿灿", "intent": "冲突升级"},
            {"beat": 7, "speaker": "妈妈", "intent": "叹气管不了，两人僵持"},
        ],
    }
    out, notes = normalize_k_parent_intervention_budget(contract)
    assert notes == []
    assert out["beat_chain"] == contract["beat_chain"]


def test_apply_parent_role_budget_keeps_mom_when_h3_beat_has_parent():
    contract = _sample_contract()
    contract["story_type"] = "I"
    contract["mom_lines_max"] = 0
    h3 = {
        "structure_type": "I",
        "beat": [
            "妹妹宣扬差分，妈妈责备戳痛处",
            "妹妹辩称宣传高分该感谢",
            "妈妈反问冰箱逻辑，妹妹语塞",
            "妈妈点出开好头，妹妹嘴硬",
        ],
    }
    out = apply_parent_role_budget(contract, h3=h3)
    assert int(out["mom_lines_max"]) >= 2
    assert "妈妈" in out["characters"]
    assert "戏核家长须保留出场" in str(out.get("remap_note") or "")


def test_apply_parent_role_budget_pure_sibling_stays_zero():
    contract = _sample_contract()
    contract["story_type"] = "C"
    h3 = {
        "structure_type": "C",
        "beat": ["占物", "质问", "歪理", "嘴硬"],
    }
    out = apply_parent_role_budget(contract, h3=h3)
    assert int(out["mom_lines_max"]) == 0
    assert "妈妈" not in out["characters"]


def _long_dialogue(n: int = 14) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for i in range(n):
        sp = "昭昭" if i % 2 else "灿灿"
        lines.append({"speaker": sp, "line": f"这是第{i + 1}句可拍对白，我们当场说清楚。"})
    return lines


def test_validate_chat_hard_ok():
    story = {"dialogue": _long_dialogue(14)}
    assert validate_chat_hard(story, mom_lines_max=0) == []


def test_validate_chat_hard_rejects_short_lines():
    story = {"dialogue": _long_dialogue(8)}
    errs = validate_chat_hard(story)
    assert any("对白句数" in e for e in errs)


def test_validate_chat_hard_allows_mom_last():
    lines = _long_dialogue(14)
    lines[-1] = {"speaker": "妈妈", "line": "好了别吵了。"}
    errs = validate_chat_hard(lines_to_story(lines), mom_lines_max=1)
    assert not any("末句" in e for e in errs)


def lines_to_story(lines: list[dict[str, str]]) -> dict:
    return {"dialogue": lines}


def test_banned_literals_allow_in_product_jiejie():
    """站内「姐姐」是产品要求的合法称呼，不得进禁词表。"""
    from app.services.gold_story.scene import sanitize_banned_literals

    out = sanitize_banned_literals(
        ["妹妹", "姐姐", "哥哥", "弟弟"],
        scene_contract={"conflict": "抢玩具", "object": "布娃娃"},
    )
    assert "姐姐" not in out
    assert "哥哥" in out and "妹妹" in out and "弟弟" in out


def test_source_sibling_seniority_detection():
    from app.services.gold_story.scene import source_sibling_seniority

    assert source_sibling_seniority("逐渐暴躁的妹妹和八百个心眼的哥哥") == "兄妹"
    assert source_sibling_seniority("姐姐和弟弟抢玩具") == "姐弟"
    assert source_sibling_seniority("两个小孩抢玩具") == ""


def test_sibling_seniority_warns_on_direct_mapping_of_xiongmei():
    """#117：源「兄妹」与站内「姐弟」不同构，声明直接映射须告警。"""
    from app.services.gold_story.scene import sibling_seniority_warnings

    warns = sibling_seniority_warnings(
        bili_title="逐渐暴躁的妹妹和八百个心眼的哥哥",
        remap_note="昭昭为弟弟，灿灿为姐姐，直接映射。",
    )
    assert warns
    assert "直接映射" in warns[0]
    assert "长幼" in warns[0]


def test_sibling_seniority_silent_for_same_system_and_explained():
    from app.services.gold_story.scene import sibling_seniority_warnings

    assert not sibling_seniority_warnings(
        bili_title="姐姐和弟弟抢玩具",
        remap_note="姐姐灿灿，弟弟昭昭",
    )
    assert not sibling_seniority_warnings(
        bili_title="哥哥和妹妹",
        remap_note="源哥哥年长→灿灿(姐姐)，源妹妹→昭昭(弟弟)",
    )


def test_parent_identity_claim_target_reads_relation():
    assert parent_identity_claim_target("我是你妈，你得听我的") == "妈妈"
    assert parent_identity_claim_target("我是你爸") == "爸爸"
    assert parent_identity_claim_target("你去把灯关了") is None
    # 引号内是引述，不算当前说话人自称
    assert parent_identity_claim_target("你说“我是你妈”") is None


def test_realign_parent_identity_bare_claim_moves_to_parent():
    """孩子裸自称家长身份 → 归位家长（#132 妈妈台词被挂到孩子）。"""
    rows = [
        {"speaker": "昭昭", "intent": "我是你妈，你得听我的"},
        {"speaker": "昭昭", "intent": "你去把灯关了"},
        {"speaker": "妈妈", "intent": "我是你妈"},
    ]
    out, notes = realign_parent_identity_rows(rows, parent_labels=("妈妈",))
    assert [r["speaker"] for r in out] == ["妈妈", "昭昭", "妈妈"]
    assert out[0]["intent"] == "我是你妈，你得听我的"
    assert notes == ["身份自称归位:昭昭→妈妈"]


def test_realign_parent_identity_echo_converts_deixis():
    """回声明称句保留归属，只把人称换过来：我是你妈 → 你是我妈。"""
    rows = [{"speaker": "昭昭", "intent": "你还知道我是你妈呀"}]
    out, notes = realign_parent_identity_rows(rows, parent_labels=("妈妈",))
    assert out[0]["speaker"] == "昭昭"
    assert out[0]["intent"] == "你还知道你是我妈呀"
    assert notes and "人称转换" in notes[0]


def test_realign_parent_identity_keeps_quotes_and_roleplay():
    """真引述与扮演里的身份自称不归位、不改写。"""
    rows = [
        {"speaker": "昭昭", "intent": "你不是说过“我是你妈，你得听我的”吗"},
        {"speaker": "灿灿", "intent": "假装我是妈妈，你当宝宝"},
        {"speaker": "昭昭", "intent": "我不是你妈，你别乱叫"},
    ]
    out, notes = realign_parent_identity_rows(rows, parent_labels=("妈妈",))
    assert [r["intent"] for r in out] == [r["intent"] for r in rows]
    assert notes == []


def test_realign_parent_identity_drops_claim_without_parent_in_cast():
    """本稿角色表没有家长时，裸自称不硬塞给不存在的角色。"""
    rows = [{"speaker": "昭昭", "intent": "我是你妈"}]
    out, notes = realign_parent_identity_rows(rows, parent_labels=())
    assert out == []
    assert notes and "丢弃" in notes[0]


def _sample_facts() -> list[dict]:
    return normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "event": "晚上偷吃烤串",
                "secret_holder": "妈妈",
                "discoverer": "灿灿",
                "accuser": "灿灿",
                "denier": "妈妈",
                "claimant": "灿灿",
                "attribution_status": "resolved",
            }
        ]
    )


def test_filter_fact_bound_rows_flags_deny_on_wrong_speaker():
    """#132：认领/辩解句必须归 secret_holder，孩子说了就被剔除。"""
    rows = [
        {"speaker": "灿灿", "intent": "你还知道你是我妈呀"},
        {
            "speaker": "灿灿",
            "intent": "谁告诉你我晚上偷吃烤串儿啦",
            "fact_ref": "F1",
            "speech_act": "deny",
            "claim_role": "secret_holder",
        },
        {"speaker": "妈妈", "intent": "我是你妈，你得听我的"},
    ]
    kept, conflicts = filter_fact_bound_rows(rows, _sample_facts())
    assert [r["intent"] for r in kept] == [
        "你还知道你是我妈呀",
        "我是你妈，你得听我的",
    ]
    assert len(conflicts) == 1 and "secret_holder" in conflicts[0]


def test_filter_fact_bound_rows_allows_role_matched_rows():
    rows = [
        {
            "speaker": "妈妈",
            "intent": "我晚上偷吃烤串儿了",
            "fact_ref": "F1",
            "speech_act": "admit",
            "claim_role": "secret_holder",
        },
        {
            "speaker": "灿灿",
            "intent": "你晚上偷吃烤串儿",
            "fact_ref": "F1",
            "speech_act": "accuse",
            "claim_role": "accuser",
        },
        {
            "speaker": "灿灿",
            "intent": "把明天补给我",
            "fact_ref": "F1",
            "speech_act": "claim_compensation",
            "claim_role": "claimant",
        },
    ]
    kept, conflicts = filter_fact_bound_rows(rows, _sample_facts())
    assert kept == rows
    assert conflicts == []


def test_filter_fact_bound_rows_skips_unannotated_and_roleplay():
    """无标注行、扮演/引述框架下的行一律放行。"""
    facts = _sample_facts()
    plain = [{"speaker": "灿灿", "intent": "我是你妈（学着玩）"}]
    kept, conflicts = filter_fact_bound_rows(plain, facts)
    assert kept == plain and conflicts == []

    roleplay = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "secret_holder": "妈妈",
                "attribution_status": "resolved",
                "role_play": True,
            }
        ]
    )
    rows = [
        {
            "speaker": "灿灿",
            "intent": "我当妈妈",
            "fact_ref": "F1",
            "speech_act": "deny",
            "claim_role": "secret_holder",
        }
    ]
    kept, conflicts = filter_fact_bound_rows(rows, roleplay)
    assert kept == rows and conflicts == []


def test_format_fact_slots_block_injects_role_binding():
    from app.services.gold_story.scene import format_fact_slots_block

    facts = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "event": "晚上偷吃烤串",
                "secret_holder": "妈妈",
                "accuser": "灿灿",
                "claimant": "灿灿",
                "attribution_status": "resolved",
            }
        ]
    )
    block = format_fact_slots_block(facts)
    assert "secret_holder=妈妈" in block
    assert "claimant=灿灿" in block
    assert "索要补偿只能由 claimant 说" in block
    # 无 facts / 空槽位不注入
    assert format_fact_slots_block([]) == ""
    assert format_fact_slots_block(None) == ""
    assert (
        format_fact_slots_block(
            [{"fact_id": "F1", "discoverer": "妈妈", "attribution_status": "ambiguous"}]
        )
        == ""
    )


def test_format_scene_block_carries_fact_slots():
    from app.services.gold_story.scene import format_scene_block

    contract = {
        "location": "卧室",
        "characters": ["妈妈", "灿灿"],
        "beat_chain": [{"beat": 1, "speaker": "妈妈", "intent": "催关灯"}],
        "facts": [
            {
                "fact_id": "F1",
                "secret_holder": "妈妈",
                "accuser": "灿灿",
                "claimant": "灿灿",
                "attribution_status": "resolved",
            }
        ],
    }
    block = format_scene_block(contract)
    assert "claimant=灿灿" in block
    assert "beat_chain:" in block


def test_anchor_matches_line_tolerates_reversed_pair():
    """「催关灯」对上「去把灯关了」：相邻二字倒装也算落地。"""
    from app.services.gold_story.gold_chat.validate import _anchor_matches_line

    assert _anchor_matches_line("关灯", "灿灿，别磨蹭了，去把灯关了。")
    assert _anchor_matches_line("催关灯", "灿灿，别磨蹭了，去把灯关了。")
    assert _anchor_matches_line("关灯", "把灯关了吧")
    assert not _anchor_matches_line("关灯", "你快去睡觉")
    assert _anchor_matches_line("洗袜子", "把袜子洗了")


def test_anchor_matches_line_ignores_palindromic_pair():
    """叠字对倒装等于自身（昭昭↔昭昭）：不能只靠人名命中长叙事锚词。"""
    from app.services.gold_story.gold_chat.validate import _anchor_matches_line

    assert not _anchor_matches_line(
        "伸手抢昭昭手里的拼图", "那我也要拼，昭昭你手里这块给我呀。"
    )
    assert not _anchor_matches_line("昭昭立刻老实", "昭昭，坐好，我辅导你写作业，别耍赖。")


def test_a_closing_role_pair_follows_beat_speech_acts():
    """家长当权威（M5/A 亲子稿）时，末四拍按阵营交替判定。"""
    from app.services.daily_story.story_types.a.validate import (
        append_closing_structure_errors,
        _closing_role_pair,
        _closing_role_sides,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "催关灯", "speech_act": "other"},
        {"beat": 4, "speaker": "灿灿", "intent": "反问", "speech_act": "echo"},
        {"beat": 6, "speaker": "妈妈", "intent": "追问谁说的", "speech_act": "deny"},
        {"beat": 9, "speaker": "灿灿", "intent": "讨要补偿", "speech_act": "claim_compensation"},
    ]
    story = {"punchline_explain": "A类权威翻车", "gold_beat_chain": chain}
    assert _closing_role_pair(story) == ("灿灿", "妈妈")

    # 末四拍：灿灿引话 → 妈妈找例外 → 灿灿追问 → 妈妈软破功
    dialogue = [
        {"speaker": "妈妈", "line": "灿灿，去把灯关了。"},
        {"speaker": "灿灿", "line": "我不去，你自己去。"},
        {"speaker": "妈妈", "line": "你怎么还不去？"},
        {"speaker": "灿灿", "line": "你刚才说去把灯关了，凭什么？"},
        {"speaker": "妈妈", "line": "我这是检查，不算数。"},
        {"speaker": "灿灿", "line": "检查凭什么不算？"},
        {"speaker": "妈妈", "line": "行吧，我去关。"},
    ]
    errors: list[str] = []
    append_closing_structure_errors(
        {
            "punchline_explain": "A类权威翻车",
            "gold_beat_chain": chain,
            "dialogue": dialogue,
        },
        errors,
    )
    assert not errors, errors

    # 孩子阵营不得只剩一个：弟弟也在挑战方一侧
    sides = _closing_role_sides(
        {"gold_beat_chain": chain, "dialogue": dialogue[:1] + [{"speaker": "昭昭", "line": "我也在。"}]}
    )
    assert sides[0] == frozenset({"灿灿", "昭昭"})
    assert sides[1] == frozenset({"妈妈"})

    # 末句由孩子说（大人没破功）应判缺失
    wrong_errors: list[str] = []
    append_closing_structure_errors(
        {
            "punchline_explain": "A类权威翻车",
            "gold_beat_chain": chain,
            "dialogue": dialogue[:3]
            + [
                {"speaker": "妈妈", "line": "我这是检查，不算数。"},
                {"speaker": "灿灿", "line": "检查凭什么不算？"},
                {"speaker": "昭昭", "line": "姐，你说妈会不会赖账啊？"},
            ],
        },
        wrong_errors,
    )
    assert wrong_errors and "末句必须妈妈" in wrong_errors[0]


def test_a_closing_allows_two_kids_on_challenger_side():
    """2 孩子 vs 1 大人：末四拍两个孩子在挑战方一侧换着说，不算错。"""
    from app.services.daily_story.story_types.a.validate import (
        append_closing_structure_errors,
    )

    chain = [
        {"beat": 4, "speaker": "灿灿", "intent": "反问", "speech_act": "echo"},
        {"beat": 6, "speaker": "妈妈", "intent": "追问谁说的", "speech_act": "deny"},
        {"beat": 9, "speaker": "灿灿", "intent": "讨要补偿", "speech_act": "claim_compensation"},
    ]
    dialogue = [
        {"speaker": "妈妈", "line": "快去关灯。"},
        {"speaker": "昭昭", "line": "我也在玩呢。"},
        {"speaker": "灿灿", "line": "还有呢。"},
        {"speaker": "妈妈", "line": "别磨蹭。"},
        {"speaker": "灿灿", "line": "你刚才说关灯就补烤串，算不算数？"},
        {"speaker": "妈妈", "line": "那不一样，我这是说明天补。"},
        {"speaker": "昭昭", "line": "哪里不一样，明天不也是明天？"},
        {"speaker": "妈妈", "line": "行吧行吧，明天补你们俩。"},
    ]
    errors: list[str] = []
    append_closing_structure_errors(
        {
            "punchline_explain": "A类权威翻车",
            "gold_beat_chain": chain,
            "dialogue": dialogue,
        },
        errors,
    )
    assert not errors, errors


def test_f_mid_pairs_carry_escalation_markers():
    """F 中段补位须带 F 硬卡的加码标记，否则插入后仍判「中段缺加码」。"""
    from app.services.daily_story.story_types.f.validate import RE_ESCALATION
    from app.services.gold_story.gold_chat.length import _f_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "快去把灯关了。"},
        {"speaker": "灿灿", "line": "你先关你自己那屋的。"},
        {"speaker": "昭昭", "line": "姐，你别跟妈顶了。"},
        {"speaker": "灿灿", "line": "你再说一遍？"},
        {"speaker": "妈妈", "line": "别磨蹭。"},
        {"speaker": "昭昭", "line": "不跟你玩了！"},
    ]
    pairs, insert_at = _f_natural_mid_pairs(dialogue)
    assert pairs, "F 要有补位对"
    assert insert_at == len(dialogue) - 2
    marked = [
        pair for pair in pairs if RE_ESCALATION.search(pair[0][1])
    ]
    assert marked, f"补位对须含加码标记：{pairs[:1]}"


def test_f_parent_caught_pairs_target_the_parent():
    """把柄在家长手上：中段互呛须是孩子↔家长，勿把孩子之间写成对立。"""
    from app.services.gold_story.gold_chat.length import _f_natural_mid_pairs

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "催关灯", "claim_role": "unknown"},
        {"beat": 5, "speaker": "灿灿", "intent": "讨要补偿", "claim_role": "claimant"},
        {"beat": 6, "speaker": "妈妈", "intent": "含糊答应", "claim_role": "secret_holder"},
    ]
    dialogue = [
        {"speaker": "妈妈", "line": "快去把灯关了。"},
        {"speaker": "灿灿", "line": "你还知道你是我妈呀？"},
        {"speaker": "灿灿", "line": "你晚上偷吃烤串，都背着我。"},
        {"speaker": "妈妈", "line": "谁告诉你我偷吃了？"},
        {"speaker": "灿灿", "line": "你自己说的。"},
        {"speaker": "昭昭", "line": "姐，我也要吃。"},
    ]
    pairs, _insert_at = _f_natural_mid_pairs(dialogue, beat_chain=chain)
    assert pairs, "把柄稿也要有补位对"
    for kid_seg, parent_seg in pairs:
        assert kid_seg[0] in {"昭昭", "灿灿"}
        assert parent_seg[0] in {"妈妈", "爸爸"}, "对呛的接话方应为家长"
        assert not any(
            word in parent_seg[1] for word in ("行行行", "明天补", "算我错")
        ), "家长那句应是挡/辩，不能是认输破功"


def test_seed_gets_second_kid_on_same_side_for_parent_caught():
    """单孩+家长稿：seed 补同侧第二孩，避免模型自编第二个孩子的立场。"""
    from app.services.gold_story.scene import align_seed_two_kids_vs_parent

    seed = [
        {"speaker": "妈妈", "intent": "催灿灿去关灯", "speech_act": "other"},
        {"speaker": "灿灿", "intent": "反问妈妈身份", "speech_act": "echo"},
        {
            "speaker": "灿灿",
            "intent": "抛出妈妈偷吃烤串",
            "speech_act": "accuse",
            "claim_role": "accuser",
        },
        {"speaker": "妈妈", "intent": "追问谁说的", "speech_act": "deny"},
    ]
    out, notes = align_seed_two_kids_vs_parent(seed, characters=["妈妈", "灿灿"])
    assert notes and "昭昭" in notes[0]
    assert [r["speaker"] for r in out][:4] == ["妈妈", "灿灿", "灿灿", "昭昭"]
    added = out[3]
    assert added["claim_role"] == "accuser", "补的这拍须同侧（作证/帮腔）"
    # 这拍的 intent 会当台词补进正文，必须是能说出口的话，不能是写作说明
    assert not any(
        tok in added["intent"] for tok in ("（", "(", "勿", "禁", "须", "不得")
    ), "补的拍必须是可说对白，否则终检判旁白"

    # 已含两个孩子时不改
    two_kids = seed + [{"speaker": "昭昭", "intent": "跟着追问"}]
    same, no_notes = align_seed_two_kids_vs_parent(
        two_kids, characters=["妈妈", "灿灿", "昭昭"]
    )
    assert not no_notes and len(same) == len(two_kids)

    # 角色表只列一个孩子：按「单孩源须拆双孩」补齐（与扩写系统提示同口径）
    split, split_notes = align_seed_two_kids_vs_parent(
        seed, characters=["妈妈", "灿灿"]
    )
    assert split_notes, "单孩源须补第二孩"
    assert len(split) == len(seed) + 1

    # 没有任何家长时不补（非亲子稿）
    no_parent, _ = align_seed_two_kids_vs_parent(
        [
            {"speaker": "灿灿", "intent": "顶嘴", "speech_act": "accuse"},
            {"speaker": "灿灿", "intent": "继续", "speech_act": "echo"},
        ],
        characters=["灿灿"],
    )
    assert len(no_parent) == 2


def test_non_n_single_kid_gets_one_witness_not_filler_stack():
    """非 N 单孩源只补一个见证位，不按 N 的交替预算灌态度句。"""
    from app.services.gold_story.scene import enforce_two_kid_cast

    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭"],
        "mom_lines_max": 3,
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备孩子弄脏衣服"},
            {"beat": 2, "speaker": "昭昭", "intent": "反问为什么骂我"},
            {"beat": 3, "speaker": "昭昭", "intent": "承认弄脏但说因为疼你"},
            {"beat": 4, "speaker": "妈妈", "intent": "愣住后追问"},
            {"beat": 5, "speaker": "昭昭", "intent": "抓住不小心的说法反问"},
            {"beat": 6, "speaker": "妈妈", "intent": "道歉收束"},
        ],
    }
    out, notes = enforce_two_kid_cast(contract)
    assert notes and "见证位" in notes[0]
    partner_rows = [
        r for r in out["beat_chain"] if r.get("speaker") == "灿灿"
    ]
    assert len(partner_rows) == 1
    assert "慢慢说" in partner_rows[0]["intent"]
    assert partner_rows[0]["witness_only"] is True
    assert [r["beat"] for r in out["beat_chain"]] == list(
        range(1, len(out["beat_chain"]) + 1)
    )
    assert not enforce_two_kid_cast(out)[1], "重复归一化必须幂等"


def test_non_n_repeated_witness_beats_collapse_to_one():
    """旧稿里已被 N 逻辑灌入多句旁观态度时，非 N 收敛回一个见证位。"""
    from app.services.gold_story.scene import enforce_two_kid_cast

    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备昭昭"},
            {"beat": 2, "speaker": "昭昭", "intent": "反问为什么骂我"},
            {
                "beat": 3,
                "speaker": "灿灿",
                "intent": "这话我可有点不信，你可得说清楚才行。",
            },
            {"beat": 4, "speaker": "昭昭", "intent": "说因为疼你"},
            {
                "beat": 5,
                "speaker": "灿灿",
                "intent": "先回答上一句，越说越像真有这么回事，我都快当真了。",
            },
            {"beat": 6, "speaker": "妈妈", "intent": "追问"},
            {
                "beat": 7,
                "speaker": "灿灿",
                "intent": "行，那我就在旁边看着你把这事说圆。",
            },
            {"beat": 8, "speaker": "妈妈", "intent": "道歉收束"},
        ],
    }
    out, notes = enforce_two_kid_cast(contract)
    assert notes and "删2拍" in notes[0]
    partner_rows = [
        r for r in out["beat_chain"] if r.get("speaker") == "灿灿"
    ]
    assert len(partner_rows) == 1
    assert partner_rows[0]["intent"] == "我就在旁边听着，你慢慢说。"
    assert partner_rows[0]["witness_only"] is True


def test_existing_single_witness_is_marked_once_without_changing_real_beats():
    from app.services.gold_story.scene import enforce_two_kid_cast
    contract = {"story_type": "F", "characters": ["妈妈", "昭昭", "灿灿"], "beat_chain": [
        {"beat": 1, "speaker": "妈妈", "intent": "问为什么不练琴"},
        {"beat": 2, "speaker": "灿灿", "intent": "反问看书为什么不行"},
        {"beat": 3, "speaker": "昭昭", "intent": "我就在旁边听着，你慢慢说。"},
        {"beat": 4, "speaker": "妈妈", "intent": "拒绝讨论并要求练琴"},
    ]}
    out, notes = enforce_two_kid_cast(contract)
    assert notes and out["beat_chain"][2]["witness_only"] is True
    assert "witness_only" not in contract["beat_chain"][2]
    assert out["beat_chain"][:2] == contract["beat_chain"][:2]
    assert out["beat_chain"][3] == contract["beat_chain"][3]
    assert enforce_two_kid_cast(out) == (out, [])


def test_non_n_seed_removes_supplemental_witness_lines():
    from app.services.gold_story.scene import normalize_supplemental_kid_seed

    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备昭昭"},
            {"beat": 2, "speaker": "昭昭", "intent": "反问为什么骂我"},
            {
                "beat": 3,
                "speaker": "灿灿",
                "intent": "我就在旁边听着，你慢慢说。",
            },
            {"beat": 4, "speaker": "妈妈", "intent": "道歉收束"},
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "责备昭昭"},
        {"speaker": "昭昭", "intent": "反问为什么骂我"},
        {"speaker": "灿灿", "intent": "这话我可有点不信，你可得说清楚才行。"},
        {"speaker": "昭昭", "intent": "说因为疼你"},
        {"speaker": "灿灿", "intent": "我怎么听着这么玄乎，越琢磨越觉得悬。"},
        {"speaker": "妈妈", "intent": "道歉收束"},
    ]
    out, notes = normalize_supplemental_kid_seed(seed, contract=contract)
    assert notes and "删2句" in notes[0]
    partner_lines = [r for r in out if r.get("speaker") == "灿灿"]
    assert partner_lines == []


def test_non_n_final_dialogue_removes_supplemental_witness():
    """非 N 主对质不靠旁观见证拆句：所有补充孩子台词都移除。"""
    from app.services.gold_story.scene import trim_supplemental_kid_dialogue

    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备昭昭"},
            {"beat": 2, "speaker": "昭昭", "intent": "反问为什么骂我"},
            {
                "beat": 3,
                "speaker": "灿灿",
                "intent": "我就在旁边听着，你慢慢说。",
            },
            {"beat": 4, "speaker": "妈妈", "intent": "道歉收束"},
        ],
    }
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服怎么又弄脏了？"},
            {"speaker": "灿灿", "line": "嗯。"},
            {"speaker": "昭昭", "line": "你干嘛那么大声骂我？"},
            {"speaker": "灿灿", "line": "我就在旁边听着，你慢慢说。"},
            {"speaker": "灿灿", "line": "你先别打岔，把刚才的话说清楚！"},
            {"speaker": "昭昭", "line": "因为我疼你啊。"},
            {"speaker": "灿灿", "line": "我可没听明白，你再说一遍！"},
            {"speaker": "妈妈", "line": "对不起，是妈妈错了。"},
        ]
    }
    out, notes = trim_supplemental_kid_dialogue(story, contract=contract)
    assert notes and "删4句" in notes[0]
    partner_lines = [
        r["line"] for r in out["dialogue"] if r.get("speaker") == "灿灿"
    ]
    assert partner_lines == []
    assert not trim_supplemental_kid_dialogue(out, contract=contract)[1]


def test_non_n_final_dialogue_keeps_main_child_run():
    """允许主孩子连续陈述；不再为空缺的旁观位补态度句。"""
    from app.services.gold_story.scene import trim_supplemental_kid_dialogue

    contract = {
        "story_type": "I",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "责备昭昭"},
            {"beat": 2, "speaker": "昭昭", "intent": "解释"},
            {"beat": 3, "speaker": "灿灿", "intent": "我就在旁边听着，你慢慢说。"},
            {"beat": 4, "speaker": "妈妈", "intent": "道歉收束"},
        ],
    }
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服怎么又弄脏了？"},
            {"speaker": "昭昭", "line": "你干嘛那么大声骂我？"},
            {"speaker": "昭昭", "line": "我又不是故意弄脏的。"},
            {"speaker": "昭昭", "line": "衣服是我弄脏的，可那是因为我疼你啊。"},
            {"speaker": "昭昭", "line": "你倒好，上来就骂我傻。"},
            {"speaker": "妈妈", "line": "你疼我，我还骂你、说你傻？"},
        ]
    }
    out, notes = trim_supplemental_kid_dialogue(story, contract=contract)
    assert not notes
    speakers = [r["speaker"] for r in out["dialogue"]]
    assert speakers.count("灿灿") == 0
    assert any(
        a == b == "昭昭" for a, b in zip(speakers, speakers[1:])
    )


def test_n_seed_viewer_questions_realign_to_asker():
    """N：追问拍只归立规方，旁观孩子的追问 seed 改派；非 N / 追问方不唯一不动。"""
    from app.services.gold_story.scene import realign_seed_viewer_questions_to_asker

    seed = [
        {"speaker": "妈妈", "intent": "立规：记下昭昭每句话"},
        {"speaker": "妈妈", "intent": "先考你，今天有没有骗过人"},
        {"speaker": "昭昭", "intent": "我要找个好人来，叫张三李四王五"},
        {"speaker": "昭昭", "intent": "他们都在街上工作，别人给钱"},
        {"speaker": "灿灿", "intent": "这些名字哪来的"},
        {"speaker": "灿灿", "intent": "笑得直拍腿"},
    ]
    contract = {
        "story_type": "N",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：记录昭昭每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "一本正经胡言乱语"},
            {"beat": 3, "speaker": "妈妈", "intent": "追问这些名字哪来的"},
            {"beat": 4, "speaker": "昭昭", "intent": "解释：在街上工作别人给钱"},
            {"beat": 5, "speaker": "灿灿", "intent": "在旁边笑得直拍腿"},
        ],
    }
    out, notes = realign_seed_viewer_questions_to_asker(seed, contract=contract)
    moved = [r for r in out if r["intent"] == "这些名字哪来的"]
    assert moved and moved[0]["speaker"] == "妈妈", "旁观孩子的追问须改派给立规方"
    assert len(out) == len(seed), "只改 speaker，不增删行"
    assert any("灿灿" in note for note in notes)
    laugh = [r for r in out if r["intent"] == "笑得直拍腿"]
    assert laugh and laugh[0]["speaker"] == "灿灿", "旁观反应保留在旁观者身上"

    # 非 N 不动
    other = realign_seed_viewer_questions_to_asker(
        seed, contract={**contract, "story_type": "C"}
    )
    assert other[1] == []
    assert [(r["speaker"], r["intent"]) for r in other[0]] == [
        (r["speaker"], r["intent"]) for r in seed
    ]

    # 追问方不唯一时不猜
    ambiguous = realign_seed_viewer_questions_to_asker(
        seed,
        contract={
            "story_type": "N",
            "beat_chain": [
                {"beat": 1, "speaker": "妈妈", "intent": "追问为什么"},
                {"beat": 2, "speaker": "灿灿", "intent": "追问凭什么"},
                {"beat": 3, "speaker": "昭昭", "intent": "解释因为所以"},
            ],
        },
    )
    assert ambiguous[1] == []


def test_narration_catches_self_reported_blurt():
    """叙述式起句（角色自述「突然蹦出个 X」）须判旁白，并只留可说内容。"""
    from app.services.gold_story.scene import (
        looks_like_narration_line,
        rewrite_narration_to_speech,
    )

    raw = "突然蹦出个英文词，叫 banana，就是苹果吧。"
    assert looks_like_narration_line(raw)
    spoken = rewrite_narration_to_speech(raw, speaker="昭昭")
    assert not looks_like_narration_line(spoken)
    assert "蹦出" not in spoken, "叙述动词须剥掉"
    assert "banana" in spoken, "怪词是笑点本体，须保留"
    assert not looks_like_narration_line("你别冒出这种话！")


def test_narration_keeps_spoken_commitment_after_stage_direction():
    """动作前缀后的收束台词必须保留，不能换成通用认输句。"""
    from app.services.gold_story.scene import rewrite_narration_to_speech

    spoken = rewrite_narration_to_speech(
        "行吧，我举着筷子半天没落下，以后说话得先打草稿。",
        speaker="妈妈",
    )
    assert spoken == "以后说话得先打草稿。"
    spoken = rewrite_narration_to_speech(
        "行吧，这筷子我半天没落下，以后说话得先打草稿。",
        speaker="妈妈",
    )
    assert spoken == "以后说话得先打草稿。"


def test_parent_beat_ownership_strips_and_merges():
    """拍位所有权：孩子拍里的家长动作剥离并归并到最近家长拍；超额追问合并。"""
    contract = {
        "story_type": "N",
        "mom_lines_max": 3,
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：记下昭昭每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "胡说一串名字"},
            {"beat": 3, "speaker": "昭昭", "intent": "蹦出英文词，妈妈追问意思，他给出荒诞解释"},
            {"beat": 4, "speaker": "妈妈", "intent": "震惊追问谁教的"},
            {"beat": 5, "speaker": "妈妈", "intent": "深吸一口气，决定以后说话先打草稿"},
        ],
    }
    out, notes = normalize_parent_beat_ownership(contract)
    assert any("剥离越权家长动作" in n for n in notes)
    child_beat = [r for r in out["beat_chain"] if r["beat"] == 3][0]
    assert "妈妈追问" not in child_beat["intent"], "孩子拍不得留家长动作"
    parent_beat = [r for r in out["beat_chain"] if r["beat"] == 4][0]
    assert "追问意思" in parent_beat["intent"], "剥离出的家长动作须归并到最近家长拍"
    assert [r["beat"] for r in out["beat_chain"]] == [1, 2, 3, 4, 5], "拍号须重排连续"

    # 家长拍数（4）超 mom_lines_max（3）→ 合并追问拍，不外派给孩子
    over = {
        "story_type": "N",
        "mom_lines_max": 3,
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：记下昭昭每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "胡说一串名字"},
            {"beat": 3, "speaker": "妈妈", "intent": "追问意思：那是什么词"},
            {"beat": 4, "speaker": "妈妈", "intent": "追问谁教的"},
            {"beat": 5, "speaker": "昭昭", "intent": "淡定补一句苹果"},
            {"beat": 6, "speaker": "妈妈", "intent": "吸口气决定以后说话先打草稿"},
        ],
    }
    merged, merged_notes = normalize_parent_beat_ownership(over)
    assert any("合并家长追问拍" in n for n in merged_notes)
    mom_beats = [
        r for r in merged["beat_chain"] if r["speaker"] == "妈妈"
    ]
    assert len(mom_beats) == 3, "家长拍数须收到 mom_lines_max 以内"
    ask = [r for r in mom_beats if "追问" in r["intent"]][0]
    assert "谁教" in ask["intent"] and "什么词" in ask["intent"], "追问须合并同拍"
    assert all(r["speaker"] != "灿灿" for r in merged["beat_chain"]), "不得外派给孩子"


def test_n_two_kid_alternation_inserts_reactions():
    """两个孩子时不删第二孩，而是插反应拍把连说拆开。"""
    contract = {
        "story_type": "N",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规记录每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "报出一串编的名字"},
            {"beat": 3, "speaker": "昭昭", "intent": "解释这个词的意思"},
            {"beat": 4, "speaker": "妈妈", "intent": "追问什么意思、谁教的"},
            {"beat": 5, "speaker": "妈妈", "intent": "服了收束"},
        ],
    }
    out, notes = ensure_n_two_kid_alternation(contract)
    assert notes and "交替" in notes[0]
    speakers = [r["speaker"] for r in out["beat_chain"]]
    # 两个孩子不再相邻重复
    kids = [s for s in speakers if s in ("昭昭", "灿灿")]
    for a, b in zip(kids, kids[1:]):
        assert a != b, f"两个孩子仍然连说: {speakers}"
    # 灿灿在里面，且反应拍不代问关键追问
    assert "灿灿" in speakers
    react = [
        r for r in out["beat_chain"]
        if r["speaker"] == "灿灿"
    ]
    for r in react:
        assert not any(
            w in r["intent"] for w in ("什么意思", "谁教的")
        ), "第二孩不得代问关键追问"
    # 妈妈拍数不变
    assert sum(1 for s in speakers if s == "妈妈") == 3

    # 只有一个孩子 → 不做（两人手由上层补第二孩）
    solo = {
        "story_type": "N",
        "characters": ["妈妈", "昭昭"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规"},
            {"beat": 2, "speaker": "昭昭", "intent": "胡说"},
        ],
    }
    assert ensure_n_two_kid_alternation(solo)[1] == []

def test_n_decorative_kid_seed_preserved_for_alternation():
    """第二孩的 seed 行要保留：她是交替位置的承担者，删了就必然连说。"""
    seed = [
        {"speaker": "妈妈", "intent": "立规"},
        {"speaker": "昭昭", "intent": "我要找好人"},
        {"speaker": "灿灿", "intent": "跟着起哄说他真会编"},
        {"speaker": "昭昭", "intent": "苹果"},
    ]
    out, notes = trim_n_decorative_kid_seed(seed, contract={"story_type": "N"})
    assert not notes
    assert out == seed
    assert any(r["speaker"] == "灿灿" for r in out)
    out2, _ = trim_n_decorative_kid_seed(seed, contract={"story_type": "C"})
    assert out2 == seed


def test_cast_normalized_to_beats_drops_ghost_character():
    """角色表对齐 beat：角色表里有、beat_chain 一句没有的角色必须被移除。"""
    contract = {
        "story_type": "N",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：记录每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "胡说一串名字"},
            {"beat": 3, "speaker": "妈妈", "intent": "追问谁教的"},
        ],
    }
    out, notes = normalize_cast_to_beats(contract)
    assert notes and "灿灿" in notes[0]
    assert out["characters"] == ["妈妈", "昭昭"]

    # 每个角色都有拍 → 原样返回
    full = {
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规"},
            {"beat": 2, "speaker": "昭昭", "intent": "抢"},
            {"beat": 3, "speaker": "灿灿", "intent": "抢回"},
        ],
    }
    same, no_notes = normalize_cast_to_beats(full)
    assert not no_notes and same["characters"] == full["characters"]

    # 缺角色表 / 缺 beat 时不动
    assert normalize_cast_to_beats({"beat_chain": []})[1] == []
    assert normalize_cast_to_beats({"characters": ["妈妈"]})[1] == []


def test_n_formula_slots_added_when_contract_missing_them():
    """N 公式槽自洽：契约缺「讲圆」与「愣住收束」时补槽位标注，不新造事实。"""
    contract = {
        "story_type": "N",
        "characters": ["妈妈", "昭昭"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：记录每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "报出一串编的名字"},
            {"beat": 3, "speaker": "昭昭", "intent": "解释成在街上工作别人给钱"},
            {"beat": 4, "speaker": "妈妈", "intent": "追问谁教的"},
            {"beat": 5, "speaker": "昭昭", "intent": "淡定补一句苹果"},
            {"beat": 6, "speaker": "妈妈", "intent": "决定以后说话先打草稿"},
        ],
    }
    out, notes = normalize_n_formula_slots(contract)
    assert "补N自洽槽标注" in notes
    assert "补N愣住收束槽" in notes
    intent3 = next(r["intent"] for r in out["beat_chain"] if r["beat"] == 3)
    assert "因为" in intent3 or "讲圆" in intent3
    intent_last = out["beat_chain"][-1]["intent"]
    assert "服了" in intent_last or "接不住" in intent_last
    # 原有事实保留
    assert "街上工作" in intent3
    assert "打草稿" in intent_last

    # 已自带这两个槽 → 不动
    full = {
        "story_type": "N",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规"},
            {"beat": 2, "speaker": "昭昭", "intent": "一本正经讲圆（因为所以）"},
            {"beat": 3, "speaker": "妈妈", "intent": "最后服了，接不住"},
        ],
    }
    same, no_notes = normalize_n_formula_slots(full)
    assert not no_notes

    # 非 N 不动
    other, _ = normalize_n_formula_slots({**contract, "story_type": "C"})
    assert other["beat_chain"] == contract["beat_chain"]


def test_needs_second_kid_always_true():
    """补第二孩是「禁同人连说」的前提：任何类型的单孩源都要补。"""
    assert needs_second_kid({"story_type": "N", "beat_chain": []}) is True
    assert needs_second_kid({"story_type": "C", "beat_chain": []}) is True
    assert needs_second_kid({}) is True
    assert needs_second_kid(None) is True


def test_e_mid_pairs_support_single_kid_plus_parent():
    """E 单孩稿：中段补位须是「孩子追问+家长短反应」，且落在收束两拍之前。"""
    from app.services.gold_story.gold_chat.length import _e_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "灿灿，快去把灯关了。"},
        {"speaker": "灿灿", "line": "等会儿，我还没看完。"},
        {"speaker": "灿灿", "line": "你还知道你是我妈呀？"},
        {"speaker": "灿灿", "line": "你晚上偷吃烤串，都背着我。"},
        {"speaker": "灿灿", "line": "垃圾桶里签子还在呢。"},
        {"speaker": "灿灿", "line": "你刚才说算不算数？"},
        {"speaker": "妈妈", "line": "行行行，明天补你。"},
    ]
    pairs, insert_at = _e_natural_mid_pairs(dialogue)
    assert pairs, "单孩+家长也要有补位对"
    assert insert_at == len(dialogue) - 2, "补位须落在收束两拍之前"
    assert pairs[0][0][0] == "灿灿" and pairs[0][1][0] == "妈妈"
    # 家长那句不得是破功词，也不得复读大人例外
    for _kid_line, parent_line in pairs:
        assert not any(w in parent_line for w in ("行行行", "说不通", "唉"))

    # 家长已满 3 句（契约 mom_lines_max）时不再添家长台词，避免超额度
    denser = dialogue[:1] + dialogue[1:5] + [
        {"speaker": "妈妈", "line": "我这不是在说嘛。"},
        {"speaker": "妈妈", "line": "谁告诉你我偷吃了？"},
        dialogue[-1],
    ]
    assert _e_natural_mid_pairs(denser)[0] == ()


def test_fact_role_pair_prefers_facts_then_beat_acts():
    """把柄稿两方：挑战方=指认者，权威方=自曝/辩解者。"""
    from app.services.gold_story.scene import fact_role_pair

    by_facts = fact_role_pair(
        {
            "facts": [
                {
                    "fact_id": "F1",
                    "secret_holder": "妈妈",
                    "accuser": "灿灿",
                    "attribution_status": "resolved",
                }
            ]
        }
    )
    assert by_facts == ("灿灿", "妈妈")

    by_beats = fact_role_pair(
        {
            "beat_chain": [
                {"beat": 4, "speaker": "灿灿", "intent": "反问", "speech_act": "echo"},
                {"beat": 6, "speaker": "妈妈", "intent": "追问", "speech_act": "deny"},
            ]
        }
    )
    assert by_beats == ("灿灿", "妈妈")

    assert fact_role_pair({}) == ("", "")
    assert fact_role_pair(None) == ("", "")
    # 单一角色（推不出对抗双方）不返回
    assert (
        fact_role_pair(
            {"beat_chain": [{"speaker": "灿灿", "speech_act": "echo"}]}
        )
        == ("", "")
    )


def test_a_hint_localizes_roles_for_parent_authority():
    """家长当权威时，A 类 hint 的示例角色名须换成契约实际角色。"""
    from app.services.daily_story.story_types import (
        gold_chat_type_revision_hint,
    )
    from app.services.gold_story.gold_chat.type_bridge import (
        structure_type_hint,
    )

    default_hint = gold_chat_type_revision_hint("A")
    assert "昭昭引前文原话" in default_hint

    localized = gold_chat_type_revision_hint(
        "A",
        challenger="灿灿",
        authority="妈妈",
    )
    assert "灿灿引前文原话→妈妈给当前动作找具体例外" in localized
    assert "昭昭" not in localized
    assert "翻旧账戳妈妈" in localized

    hint = structure_type_hint(
        structure_type="A",
        mechanism="M5",
        challenger="灿灿",
        authority="妈妈",
    )
    assert "灿灿引前文原话→妈妈给当前动作找具体例外" in hint
    # 姐弟稿不传角色时保持原样
    plain = structure_type_hint(structure_type="A", mechanism="M5")
    assert "昭昭引前文原话" in plain


def test_a_natural_mid_pairs_maps_roles_at_runtime():
    """A 类补位：家长当权威时改用另一位孩子施压，插入点落在末四拍之前。"""
    from app.services.gold_story.gold_chat.length import (
        _a_natural_mid_pairs,
        _boost_short_with_mid_lines,
    )

    chain = [
        {"beat": 4, "speaker": "灿灿", "intent": "反问", "speech_act": "echo"},
        {"beat": 6, "speaker": "妈妈", "intent": "追问", "speech_act": "deny"},
    ]
    dialogue = [
        {"speaker": "妈妈", "line": "灿灿，去把灯关了。"},
        {"speaker": "灿灿", "line": "等会儿，我还没弄完呢。"},
        {"speaker": "妈妈", "line": "你去，我是你妈！"},
        {"speaker": "灿灿", "line": "你还知道你是我妈呀？"},
        {"speaker": "昭昭", "line": "姐，我也闻见味儿了。"},
        {"speaker": "灿灿", "line": "你光顾自己吃！"},
        {"speaker": "妈妈", "line": "谁说的？"},
        {"speaker": "灿灿", "line": "垃圾桶呗。"},
        {"speaker": "昭昭", "line": "竹签还在呢。"},
        {"speaker": "灿灿", "line": "那明天你得补给我。"},
        {"speaker": "妈妈", "line": "行行行，明天再说。"},
        {"speaker": "灿灿", "line": "你刚才说补给我，别赖。"},
        {"speaker": "妈妈", "line": "我这是记着账，不算赖。"},
        {"speaker": "灿灿", "line": "记账凭什么不算赖？"},
        {"speaker": "妈妈", "line": "行吧，灯我关。"},
    ]
    pairs, insert_at = _a_natural_mid_pairs(dialogue, beat_chain=chain)
    assert pairs, "A 类应有实义中段对"
    assert insert_at == len(dialogue) - 4
    # 家长当权威：施压方改用另一位孩子，不吃妈妈台词额度
    assert {sp for sp, _ in pairs[0]} == {"昭昭", "灿灿"}

    tight = {"dialogue": dialogue, "story_type": "A"}
    out, changed = _boost_short_with_mid_lines(
        tight,
        structure_type="A",
        beat_chain=chain,
    )
    assert changed
    tail_before = [r["line"] for r in dialogue[-4:]]
    tail_after = [r["line"] for r in out["dialogue"][-4:]]
    assert tail_after == tail_before, "末四拍不得被补位改动"


def test_fact_claim_alignment_notes_detects_missing_claim_beat():
    """facts 声明讨要方，却没有讨要/补偿拍 → 提示（facts 与拍不自洽）。"""
    from app.services.gold_story.scene import fact_claim_alignment_notes

    facts = _sample_facts()  # claimant=灿灿
    assert fact_claim_alignment_notes(facts, []) != []
    assert fact_claim_alignment_notes(
        facts,
        [{"speaker": "灿灿", "intent": "指认"}],
    ) != []
    assert (
        fact_claim_alignment_notes(
            facts,
            [
                {
                    "speaker": "灿灿",
                    "intent": "把明天补给我",
                    "speech_act": "claim_compensation",
                    "claim_role": "claimant",
                }
            ],
        )
        == []
    )
    # 未声明讨要方时不拦
    no_claim = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "secret_holder": "妈妈",
                "attribution_status": "resolved",
            }
        ]
    )
    assert fact_claim_alignment_notes(no_claim, []) == []
    # beneficiary 只标得利方，不强制讨要拍
    beneficiary_only = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "secret_holder": "妈妈",
                "beneficiary": "妈妈",
                "attribution_status": "resolved",
            }
        ]
    )
    assert fact_claim_alignment_notes(beneficiary_only, []) == []


def test_title_complaint_direction_reads_roles_not_plot():
    from app.services.gold_story.scene import title_complaint_direction

    assert (
        title_complaint_direction(
            "【妈妈指挥女儿关灯，当女儿说吃烤串都背着我那一刻，笑死我了！】"
        )
        == "child_accuses_parent"
    )
    assert title_complaint_direction("姐弟抢玩具") == ""
    # 无抱怨标记 / 无家长角色时不判定
    assert title_complaint_direction("女儿和妈妈一起收拾房间") == ""
    assert title_complaint_direction("宝宝偷偷把饭倒了") == ""


def test_fact_title_conflict_notes_flags_child_as_secret_holder():
    from app.services.gold_story.scene import fact_title_conflict_notes

    title = "【妈妈指挥女儿关灯，当女儿说吃烤串都背着我那一刻，笑死我了！】"
    chars = ["妈妈", "昭昭"]
    wrong = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "secret_holder": "昭昭",
                "discoverer": "妈妈",
                "accuser": "妈妈",
                "denier": "昭昭",
                "attribution_status": "resolved",
            }
        ]
    )
    notes = fact_title_conflict_notes(wrong, video_title=title, characters=chars)
    assert len(notes) == 2 and "secret_holder" in notes[0]
    right = normalize_fact_attributions(
        [
            {
                "fact_id": "F1",
                "secret_holder": "妈妈",
                "discoverer": "昭昭",
                "accuser": "昭昭",
                "denier": "妈妈",
                "attribution_status": "resolved",
            }
        ]
    )
    assert fact_title_conflict_notes(right, video_title=title, characters=chars) == []


def test_mark_facts_ambiguous_blocks_auto_publish():
    from app.services.gold_story.scene import mark_facts_ambiguous

    facts = _sample_facts()
    marked, changed = mark_facts_ambiguous(facts, reason="title_conflict")
    assert changed
    assert marked[0]["attribution_status"] == "ambiguous"
    assert "title_conflict" in marked[0]["attribution_basis"]
    assert fact_attribution_review_required(marked)
    again, changed2 = mark_facts_ambiguous(marked, reason="title_conflict")
    assert changed2 is False and again[0]["attribution_status"] == "ambiguous"


def test_fact_attribution_review_required_for_unresolved():
    assert not fact_attribution_review_required(_sample_facts())
    assert fact_attribution_review_required(
        normalize_fact_attributions(
            [{"fact_id": "F1", "secret_holder": "妈妈"}]
        )
    )
    # 指定了行为人却缺 attribution_status：视为未定稿，不得放行
    assert fact_attribution_review_required(
        normalize_fact_attributions([{"fact_id": "F1", "secret_holder": "妈妈"}])
    )
    assert not fact_attribution_review_required([])
    assert not fact_attribution_review_required(None)
    # 只复述事件、没指定行为人的条目不算归属，不拦（避免误伤正常稿）
    assert not fact_attribution_review_required(
        [
            {
                "fact_id": "F1",
                "event": "妈妈买玩具，兄弟俩抢起来",
                "discoverer": "妈妈",
                "attribution_status": "ambiguous",
            }
        ]
    )


def test_resolve_parent_lines_budget_derives_from_beats_not_guesses():
    """家长台词预算：beat_chain 里家长承担几拍，就给几句额度（防死锁）。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    # 契约让爸爸承担 2 拍，却不给额度 → 任何合规稿都过不了硬卡，须按拍数抬
    chain = [
        {"speaker": "灿灿", "intent": "占物"},
        {"speaker": "爸爸", "intent": "旁观解说"},
        {"speaker": "爸爸", "intent": "被推趔趄"},
    ]
    mom, dad, parent = resolve_parent_lines_budget({"beat_chain": chain})
    assert dad >= 2
    assert parent >= 2

    # 妈妈承担 3 拍同理
    mom2, _, parent2 = resolve_parent_lines_budget(
        {"beat_chain": [{"speaker": "妈妈", "intent": f"劝{i}"} for i in range(3)]}
    )
    assert mom2 >= 3 and parent2 >= 3

    # 只按拍数抬，不凭剧情猜词
    mom3, dad3, parent3 = resolve_parent_lines_budget(
        {"beat_chain": [{"speaker": "昭昭", "intent": "争抢"}]}
    )
    assert dad3 == 1 and parent3 == mom3 + 1


def test_resolve_parent_lines_budget_prefers_explicit_values():
    """显式入参 > 契约字段 > 派生默认。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    chain = [{"speaker": "爸爸", "intent": "被推趔趄"}]
    # 显式入参优先
    mom, dad, parent = resolve_parent_lines_budget(
        {"beat_chain": chain, "mom_lines_max": 5, "dad_lines_max": 4},
        mom_lines_max=2,
        dad_lines_max=3,
    )
    assert mom == 2 and dad == 3
    # 契约字段次之
    mom2, dad2, _ = resolve_parent_lines_budget(
        {"beat_chain": chain, "mom_lines_max": 5, "dad_lines_max": 4}
    )
    assert mom2 == 5 and dad2 == 4
    # 无家长拍且无契约时，爸爸额度为 0（家长预算为 0）
    mom3, dad3, parent3 = resolve_parent_lines_budget(
        {"beat_chain": [{"speaker": "昭昭", "intent": "争抢"}]},
        mom_lines_max=0,
        dad_lines_max=0,
        parent_lines_max=0,
    )
    assert mom3 == 0 and dad3 == 0 and parent3 == 0
    # 非法值不炸，退回派生默认
    mom4, dad4, parent4 = resolve_parent_lines_budget(
        {"beat_chain": [], "mom_lines_max": "abc"}
    )
    assert mom4 == 1 and dad4 == 1 and parent4 == 2


def test_resolve_parent_lines_budget_caps_but_never_below_beats():
    """封顶只挡脏契约，且绝不能把额度压到低于拍数（否则死锁复现）。"""
    from app.services.gold_story.scene import (
        CHAT_LINE_COUNT_MAX,
        chat_line_cap,
        resolve_parent_lines_budget,
    )

    # 脏契约：家长拍数远超全稿句数上限 -> 须封到句数上限
    huge = [{"speaker": "爸爸", "intent": f"拍{i}"} for i in range(80)]
    mom, dad, parent = resolve_parent_lines_budget({"beat_chain": huge})
    assert dad == chat_line_cap("K") or dad <= CHAT_LINE_COUNT_MAX + 2
    assert parent <= CHAT_LINE_COUNT_MAX + 2
    # 契约里塞了巨大显式额度，同样要被封顶
    _, dad_big, parent_big = resolve_parent_lines_budget(
        {"beat_chain": [], "mom_lines_max": 999, "dad_lines_max": 999}
    )
    assert dad_big <= CHAT_LINE_COUNT_MAX and parent_big <= CHAT_LINE_COUNT_MAX

    # 关键反例：封顶不得写成 min(契约值, 拍数)，否则额度低于拍数 -> 死锁
    chain = [{"speaker": "爸爸", "intent": f"拍{i}"} for i in range(6)]
    _, dad6, parent6 = resolve_parent_lines_budget(
        {"beat_chain": chain, "dad_lines_max": 1}
    )
    assert dad6 >= 6, "封顶误压到拍数以下，合规稿会重新被拦死"
    assert parent6 >= 6

    # 合法区间内封顶不生效（不误伤）
    _, dad1, _ = resolve_parent_lines_budget(
        {"beat_chain": [{"speaker": "爸爸", "intent": "旁观"}]}
    )
    assert dad1 == 1


def test_resolve_parent_lines_budget_lone_parent_gets_parent_quota():
    """cast 里只有一位家长时，家长总预算归它，不被缺席家长的默认额度压死。

    ``dad`` 默认 1 的前提是「妈妈主家长、爸爸至多 1 句」。若 cast 根本没有妈妈，
    仍按 1 句卡唯一在场的家长，会让契约要求家长多说一句时任何合规稿都挂硬卡。
    """
    from app.services.gold_story.scene import resolve_parent_lines_budget

    contract = {
        "story_type": "K",
        "characters": ["灿灿", "昭昭", "爸爸"],
        "mom_lines_max": 2,
        "beat_chain": [{"speaker": "爸爸", "intent": "解说拱火"}],
    }
    mom, dad, parent = resolve_parent_lines_budget(contract)
    assert dad == parent == 3, "唯一在场的家长只拿到缺席家长的默认额度"
    assert mom == 0

    # 两位家长都在 cast 时口径不变：各按各的字段/默认
    both = dict(contract, characters=["灿灿", "昭昭", "妈妈", "爸爸"])
    mom2, dad2, parent2 = resolve_parent_lines_budget(both)
    assert (mom2, dad2, parent2) == (2, 1, 3)

    # 只有妈妈时同理让给妈妈
    mom3, dad3, parent3 = resolve_parent_lines_budget(
        dict(contract, characters=["灿灿", "昭昭", "妈妈"])
    )
    assert mom3 == parent3 == 3 and dad3 == 0


def test_resolve_parent_lines_budget_reads_injected_gold_chat_caps():
    """硬卡须读成稿注入的 ``_gold_chat_*`` 额度，与评分层同口径。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom, dad, parent = resolve_parent_lines_budget(
        {"story_type": "K", "_gold_chat_mom_lines_max": 0, "_gold_chat_dad_lines_max": 3}
    )
    assert (mom, dad, parent) == (0, 3, 3)


def test_origin_ask_answerable_invariant():
    """契约问了出处，seed 必须有答案；答案不得引入新实体。"""
    contract = {
        "story_type": "N",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规记录每句话"},
            {"beat": 2, "speaker": "昭昭", "intent": "报出一串编的名字"},
            {"beat": 3, "speaker": "昭昭", "intent": "说出怪词并解释"},
            {"beat": 4, "speaker": "妈妈", "intent": "追问什么意思、谁教的"},
            {"beat": 5, "speaker": "妈妈", "intent": "决定先打草稿"},
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "我记下你说的每句话"},
        {"speaker": "妈妈", "intent": "banana是什么意思？谁教的"},
        {"speaker": "昭昭", "intent": "苹果"},
    ]
    out, notes = ensure_origin_ask_answerable(seed, contract=contract)
    assert notes and "出处" in notes[0]
    assert len(out) == len(seed) + 1
    answer = out[2]
    assert answer["speaker"] == "昭昭"
    assert "没人教" in answer["intent"] or "自己想的" in answer["intent"]

    # 已有答案 → 不覆盖
    seed2 = [
        {"speaker": "妈妈", "intent": "banana谁教的"},
        {"speaker": "昭昭", "intent": "没人教，我自己想的"},
    ]
    same, no_notes = ensure_origin_ask_answerable(seed2, contract=contract)
    assert not no_notes and same == seed2

    # 契约没问出处 → 不动
    plain = {"story_type": "N", "beat_chain": [{"beat": 1, "speaker": "妈妈", "intent": "立规"}]}
    assert ensure_origin_ask_answerable(seed, contract=plain)[1] == []

    # 非 N → 不动
    assert ensure_origin_ask_answerable(seed, contract={"story_type": "C"})[1] == []


def test_token_normalization_strips_bad_prefix():
    """怪词被当前缀/名字用时，前缀属病句须剔除，且只保留独立出词那一句。"""
    contract = {"story_type": "N"}

    out, notes = split_n_token_from_explanation(
        [{"speaker": "昭昭", "intent": "因为好人叫banana"}],
        contract=contract,
    )
    assert len(out) == 1, "前缀被丢掉后只剩出词那一句"
    assert out[0]["intent"].endswith("banana")
    assert "因为" not in out[0]["intent"]
    assert notes and "剔除怪词前缀" in notes[0]

    # 词 + 解释同句 → 拆两句
    out2, notes2 = split_n_token_from_explanation(
        [{"speaker": "昭昭", "intent": "banana！就是你在街上工作别人给钱"}],
        contract=contract,
    )
    assert len(out2) == 2
    assert "banana" in out2[0]["intent"]
    assert "街上工作" not in out2[0]["intent"], "出词那一句不得夹带解释内容"
    assert "解释" in out2[1]["intent"]
    assert "街上工作" in out2[1]["intent"]

    # 家长追问句 / 不含怪词的行 → 不动
    for row in (
        {"speaker": "妈妈", "intent": "banana什么意思？谁教你的"},
        {"speaker": "昭昭", "intent": "苹果"},
    ):
        kept, n = split_n_token_from_explanation([dict(row)], contract=contract)
        assert kept == [row] and not n


def test_pad_intent_must_not_require_new_entity():
    """补位 intent 不得要求新实体：加了就必被终检判无据。"""
    from app.services.gold_story.gold_chat.expand import (
        _filter_pad_extras,
        _pad_intent_requires_new_entity,
    )

    bad = [
        "接着上一句往细里说：那个人具体是谁（称呼即可）",
        "接着上一句往细里说：在什么地方看见的",
        "接着上一句往细里说：当时他手里是什么样子",
        "说出这个词是从谁那儿听来的",
    ]
    for intent in bad:
        assert _pad_intent_requires_new_entity(intent), intent

    good = [
        "坚持自己没说错，让对方别打岔",
        "反问对方：你自己不信就算了",
        "说这话没说完，让对方等他讲完再问",
        "一本正经讲圆（用因为/所以）",
    ]
    for intent in good:
        assert not _pad_intent_requires_new_entity(intent), intent

    kept, dropped = _filter_pad_extras(
        [{"speaker": "昭昭", "intent": i} for i in bad + good]
    )
    assert len(kept) == len(good) and len(dropped) == len(bad)


def _n_contract(token: str = "咕噜") -> dict:
    return {
        "story_type": "N",
        "characters": ["妈妈", "昭昭", "灿灿"],
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "立规：问西瓜怎么长这么大"},
            {"beat": 2, "speaker": "昭昭", "intent": "一本正经说爷爷有秘方"},
            {"beat": 3, "speaker": "昭昭", "intent": f"突然蹦出一个自造怪词「{token}」"},
            {"beat": 4, "speaker": "妈妈", "intent": "追问这词什么意思"},
            {"beat": 5, "speaker": "妈妈", "intent": "收束：认栽"},
        ],
    }


def _n_seed(token: str = "咕噜", names: str = "小豆、小苗、小禾") -> list[dict]:
    return [
        {"speaker": "妈妈", "intent": "我要记下你说的每句话，看你骗不骗人"},
        {"speaker": "昭昭", "intent": f"爷爷种西瓜有个办法，叫{names}"},
        {"speaker": "灿灿", "intent": "这话我可有点不信，你别蒙我"},
        {"speaker": "昭昭", "intent": f"只说出这个词（不解释）：{token}"},
        {"speaker": "妈妈", "intent": f"{token}是什么意思，谁教你的"},
        {
            "speaker": "昭昭",
            "intent": "解释这个词是什么意思：没人教，就是浇完水要念三遍",
        },
        {"speaker": "灿灿", "intent": "越说越像真有这么回事"},
        {"speaker": "昭昭", "intent": "黄瓜"},
        {"speaker": "妈妈", "intent": "我认栽，以后说话得先打草稿"},
    ]


def test_n_two_kid_dialogue_is_seed_driven_not_hardcoded():
    """换一个故事，内容必须跟着 seed 变——绝不能串写成别篇的台词。

    这条测试守的是「不许过拟合」：早前 build_n_two_kid_dialogue 里
    写死过某篇的「小明小红小刚 / 哇卡 / 苹果」，结果任何 N 故事都会被
    改写成那篇的内容。
    """
    from app.services.gold_story.scene import build_n_two_kid_dialogue

    rows, _notes = build_n_two_kid_dialogue(
        _n_contract("咕噜"), existing=[], dialogue_seed=_n_seed("咕噜")
    )
    joined = "".join(str(r["line"]) for r in rows)
    # 本故事的实体必须在
    assert "咕噜" in joined
    assert "西瓜" in joined or "黄瓜" in joined
    # 别篇的实体一律不许出现
    for leaked in ("小明", "小红", "小刚", "哇卡", "苹果", "好人"):
        assert leaked not in joined, f"串写了别篇内容: {leaked}"


def test_n_two_kid_dialogue_keeps_alternation_and_mom_budget():
    """重排后必须：孩子严格交替、家长不超过 3 句、末句是家长收束。"""
    from app.services.gold_story.scene import build_n_two_kid_dialogue

    rows, _notes = build_n_two_kid_dialogue(
        _n_contract("咕噜"), existing=[], dialogue_seed=_n_seed("咕噜")
    )
    speakers = [str(r["speaker"]) for r in rows]
    kids = [s for s in speakers if s in {"昭昭", "灿灿"}]
    assert all(a != b for a, b in zip(speakers, speakers[1:]) if a in {"昭昭", "灿灿"})
    assert speakers.count("妈妈") <= 3
    assert speakers[-1] == "妈妈"
    assert len(kids) >= 4


def test_n_two_kid_dialogue_skips_when_already_good():
    """已有合格对白时不再重建（否则每次 refine 都会覆盖扩写成果）。"""
    from app.services.gold_story.scene import build_n_two_kid_dialogue

    good, _ = build_n_two_kid_dialogue(
        _n_contract("咕噜"), existing=[], dialogue_seed=_n_seed("咕噜")
    )
    # 补到 12 句以上（模拟扩写后的成稿），再次调用应跳过
    padded = [dict(r) for r in good]
    while len(padded) < 12:
        padded.insert(1, {"speaker": "妈妈", "line": "我记下了。"})
    again, notes = build_n_two_kid_dialogue(
        _n_contract("咕噜"), existing=padded, dialogue_seed=_n_seed("咕噜")
    )
    assert again == []
    assert notes == []


def test_normalize_beat_min_turns_caps_total_to_line_limit():
    """拍数被补多、每拍又写 3 回合时，契约阶段就压回句数上限。"""
    contract = _sample_contract()
    contract["beat_chain"] = [
        {"speaker": "灿灿" if i % 2 == 0 else "昭昭", "intent": f"第{i + 1}拍", "min_turns": 3}
        for i in range(9)
    ]
    out, notes = normalize_beat_min_turns(contract)
    turns = [row["min_turns"] for row in out["beat_chain"]]
    assert sum(turns) == 24
    # 开场与收束拍留到最后才压
    assert turns[0] == 3 and turns[-1] == 3
    assert notes and "最小回合数压额" in notes[0]
    assert not any("beat_chain_turns_exceed" in e for e in validate_scene(out))


def test_normalize_beat_min_turns_keeps_k_over_24_within_26():
    """K 类正文允许 24+2：25 回合的契约不该被压到 24。"""
    contract = _sample_contract()
    contract["story_type"] = "K"
    contract["beat_chain"] = [
        {"speaker": "灿灿" if i % 2 == 0 else "昭昭", "intent": f"第{i + 1}拍", "min_turns": 3}
        for i in range(8)
    ] + [{"speaker": "灿灿", "intent": "收束", "min_turns": 1}]
    out, notes = normalize_beat_min_turns(contract)
    turns = [row["min_turns"] for row in out["beat_chain"]]
    assert sum(turns) == 25
    assert notes == []
    assert not any("beat_chain_turns_exceed" in e for e in validate_scene(out))
