"""H3a scene_contract 与成品对白 hard 校验测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat.validate import (
    validate_chat_hard,
)
from app.services.gold_story.scene import (
    apply_parent_role_budget,
    format_scene_block,
    has_dialogue_meta_label,
    normalize_dialogue_setting_for_contract,
    normalize_k_parent_intervention_budget,
    normalize_retrospective_topic_contract,
    normalize_retrospective_n_opening_parent_beats,
    normalize_scene_dialogue_beats,
    remap_story_raw_sibling_roles,
    seed_from_beat_chain,
    sanitize_dialogue_meta_label_suffix,
    is_terminal_no_reply_intent,
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


def test_validate_scene_rejects_short_chain():
    bad = {**_sample_contract(), "beat_chain": [{"speaker": "昭昭", "intent": "a"}]}
    errs = validate_scene(bad)
    assert any("beat_chain" in e for e in errs)


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
