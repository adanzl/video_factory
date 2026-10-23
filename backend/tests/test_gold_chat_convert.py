"""gold_chat 转换测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import expand as gex
from app.services.gold_story.gold_chat import finalize as gcf
from app.services.gold_story.gold_chat import refine as grf
from app.services.gold_story.gold_chat import export as gce


@pytest.fixture(autouse=True)
def _legacy_expand_by_default(monkeypatch):
    """本文件多数用例验证整篇扩写路径；逐拍用例自己 setenv 覆盖。"""
    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "0")


def _sample_row() -> dict:
    return {
        "id": 1,
        "source_id": "BV1TEST0001",
        "url": "https://www.bilibili.com/video/BV1TEST0001",
        "title": "测试标题",
        "mechanism": "M6",
        "structure_type": "A",
        "status": "active",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "payload": {
            "setting": "卧室门口",
            "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "抱怨被欺负"},
                {"speaker": "灿灿", "intent": "得意威胁"},
            ],
            "closing_intent": "昭昭缩回角落",
            "banned_literals": ["小姨", "萌娃"],
            "funny_why": "幻想与怂的反差",
        },
    }


@pytest.mark.parametrize("value,enabled", [(None, True), ("1", True), ("off", False), ("legacy", False)])
def test_generation_and_patch_share_mode(monkeypatch, value, enabled):
    from app.services.gold_story.gold_chat.patch import _perbeat_mode

    if value is None:
        monkeypatch.delenv("GOLD_CHAT_PERBEAT", raising=False)
    else:
        monkeypatch.setenv("GOLD_CHAT_PERBEAT", value)
    assert gex._perbeat_enabled() is enabled
    assert _perbeat_mode() is enabled


def test_short_plan_fails_before_filling_instead_of_adding_empty_reactions(monkeypatch):
    from app.services.gold_story.gold_chat.repair import GoldChatContractError

    owners = ["妈妈", "昭昭", "灿灿", "昭昭", "灿灿", "灿灿", "昭昭", "妈妈"]
    beats = [{"beat": i, "speaker": sp, "intent": "回应当前问题"} for i, sp in enumerate(owners, 1)]
    contract = {"story_type": "N", "characters": ["妈妈", "昭昭", "灿灿"],
                "mom_lines_max": 2, "beat_chain": beats}
    plan = gex._line_plan_skeleton(contract, beats, target_lines=12)
    monkeypatch.setattr(gex, "_line_plan_skeleton", lambda *_a, **_kw: plan[:11])
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: pytest.fail("容量不足不得调用LLM"))
    with pytest.raises(GoldChatContractError):
        gex._build_line_plan(scene_contract=contract, beat_chain=beats, target_lines=12, story_raw="", temperature=0.5)


def test_main_rebuttal_uses_own_contract_and_rejects_unrelated_claim():
    slot = _perbeat_test_slot(intent="反问对方的号码")
    slot["_own_entry"] = {"speaker": "昭昭", "intent": "反问110不是你们的号码吗"}
    prior = [("灿灿", "你报的电话听起来不对吧？")]
    assert "辩驳的事前文须提过" not in gex._perbeat_check(slot, "110不是你们的号码吗？", prior)
    assert "辩驳的事前文须提过" in gex._perbeat_check(slot, "这不是你的奖杯吗？", prior)


def test_source_content_answers_can_use_pronouns_without_repeating_question():
    slot = _perbeat_test_slot(intent="回答他问妈妈电话")
    prior = [("灿灿", "民警叔叔当时问什么？")]
    slot.update(planned_content=True, source_seed_ids=[2])
    assert "上一句是问句，回句须咬住问句" not in gex._perbeat_check(slot, "他问我妈妈的电话号码。", prior)
    slot["source_seed_ids"] = []
    assert "上一句是问句，回句须咬住问句" in gex._perbeat_check(slot, "他问我妈妈的电话号码。", prior)


def test_question_matching_keeps_numbers():
    slot = _perbeat_test_slot(intent="回答号码")
    assert "上一句是问句，回句须咬住问句" not in gex._perbeat_check(
        slot, "110就是他们的电话号码。", [("灿灿", "他有没有提醒你110？")])


def test_answer_can_precede_a_followup_question():
    slot = _perbeat_test_slot(speaker="灿灿", filler=True, intent="回应报警号码再追问")
    slot["has_content"] = False
    failures = gex._perbeat_check(slot, "110是报警电话，那该打哪个呢？", [("昭昭", "110不是你们的号码吗？")])
    assert "必须先正面回答上一句的问题" not in failures
    assert "零素材插话须接住上一句（共享实词或当场表态）" not in failures


def test_fill_validation_does_not_remove_bad_line_from_following_context(monkeypatch):
    seen = []
    def check(_slot, line, previous):
        seen.append(list(previous))
        return ["bad"] if line == "第一句不合格。" else []
    monkeypatch.setattr(gex, "_perbeat_check", check)
    slots = [_perbeat_test_slot(), _perbeat_test_slot(speaker="灿灿")]
    gex._perbeat_validate_fill(slots, {1: "第一句不合格。", 2: "第二句接住实际前文。"})
    assert seen[1] == [("昭昭", "第一句不合格。")]


def test_n_question_slot_does_not_overwrite_closing_slot():
    slots = [{"speaker": sp, "intent": "答复", "is_filler": False}
             for sp in ["妈妈", "昭昭", "灿灿", "昭昭", "妈妈"]]
    out = gex._apply_n_word_slots(slots, structure_type="N")
    assert out[0]["must_words"] == list(gex._N_SLOT_WORD_REQS["why"])
    assert out[-1]["must_words"] == list(gex._N_SLOT_WORD_REQS["stun"])


@pytest.mark.parametrize("present_in_source", [False, True])
def test_source_plan_distinguishes_pipeline_reaction_from_literal_source(present_in_source):
    from app.services.gold_story.scene import mark_seed_source_origins

    speakers = ["妈妈", "昭昭", "灿灿", "昭昭", "妈妈", "昭昭",
                "灿灿", "昭昭", "妈妈", "昭昭", "灿灿", "妈妈"]
    seed = [{"speaker": sp, "intent": f"第{i}个已经发生的具体问答内容"}
            for i, sp in enumerate(speakers, 1)]
    seed[2]["intent"] = "这话我可有点不信，你可得说清楚才行。"
    source = seed[2]["intent"] if present_in_source else "孩子告诉妈妈昨天发生的事情。"
    marked = mark_seed_source_origins(seed, source)
    assert "source_origin" not in seed[2]
    assert marked == mark_seed_source_origins(marked, source)
    beats = [{"beat": i, "speaker": s["speaker"], "intent": s["intent"]} for i, s in enumerate(seed, 1)]
    contract = {"story_type": "N", "characters": ["妈妈", "昭昭", "灿灿"], "mom_lines_max": 4}
    plan = gex._source_plan_skeleton(contract, beats, marked)
    mapping = {str(i): [ref for row in plan if row["beat"] == i for ref in row["source_seed_ids"]]
               for i in range(1, 13)}
    _, errors = gex._validate_source_line_plan(
        {"lines": plan, "beat_sources": mapping}, scene_contract=contract,
        beat_chain=beats, seed=marked, validate_intents=False)
    assert not errors
    assert plan[2]["role"] == ("content" if present_in_source else "reaction")
    assert plan[2]["source_seed_ids"] == ([3] if present_in_source else [])
    if not present_in_source:
        plan[2].update(role="content", source_seed_ids=[3])
        mapping["3"] = [3]
        _, errors = gex._validate_source_line_plan(
            {"lines": plan, "beat_sources": mapping}, scene_contract=contract,
            beat_chain=beats, seed=marked, validate_intents=False)
        assert any("程序补充反应不得冒充来源素材" in error for error in errors)


def test_n_word_slots_follow_contract_questions_and_reason_instead_of_positions():
    slots = [{"speaker": sp, "intent": intent, "is_filler": False} for sp, intent in [
        ("妈妈", "提醒作业还没写完"),
        ("昭昭", "提出让玩具代写"),
        ("妈妈", "设问：你说，玩具怎么写作业？"),
        ("昭昭", "解释：因为它天天坐在书桌旁边"),
        ("妈妈", "追问：这是什么意思？"),
        ("灿灿", "嘲笑玩具根本不会写字"),
        ("妈妈", "服了，还是自己写吧"),
    ]]
    out = gex._apply_n_word_slots(slots, structure_type="N")
    assert out[2]["required_word_groups"] == [["你说"]]
    assert "must_words" not in out[2]
    assert out[4]["must_words"] == list(gex._N_SLOT_WORD_REQS["why"])
    assert out[3]["must_words"] == list(gex._N_SLOT_WORD_REQS["reason"])
    assert "must_words" not in out[5]


def _source_plan_fixture():
    owners = ["妈妈", "昭昭", "灿灿", "昭昭", "灿灿", "昭昭", "妈妈"]
    beats = [{"beat": i, "speaker": sp, "intent": f"剧情单元{i}的具体内容"}
             for i, sp in enumerate(owners, 1)]
    seed = [{"speaker": sp, "intent": f"素材单元{i}的独立内容"}
            for i, sp in enumerate(["妈妈", "昭昭", "灿灿", "昭昭", "昭昭", "灿灿", "昭昭", "昭昭", "妈妈"], 1)]
    contract = {"story_type": "N", "characters": ["妈妈", "昭昭", "灿灿"],
                "mom_lines_max": 2, "parent_lines_max": 2, "beat_chain": beats}
    lines = gex._source_plan_skeleton(contract, beats, seed)
    reactions = iter(["接住前文的具体问题", "对已知事实表示疑惑", "对上一句答案作出反应"])
    for line in lines:
        if line["role"] == "reaction":
            line["intent"] = next(reactions)
    mapping = {str(b): [s for r in lines if r["beat"] == b for s in r["source_seed_ids"]]
               for b in range(1, 8)}
    return contract, seed, {"beat_sources": mapping, "lines": lines}


def test_source_plan_keeps_both_answers_as_content_and_preserves_seed_ownership():
    contract, seed, data = _source_plan_fixture()
    plan, errors = gex._validate_source_line_plan(
        data, scene_contract=contract, beat_chain=contract["beat_chain"], seed=seed)
    assert errors == []
    slots = gex._line_plan_slots(plan, contract["beat_chain"])
    answers = [s for s in slots if s["beat_id"] == 4 and s["speaker"] == "昭昭"]
    assert len(answers) == 2
    assert all(not s["is_filler"] for s in answers)
    assert [s["source_seed_ids"] for s in answers] == [[4], [5]]


def test_source_plan_refuses_ambiguous_source_partition():
    from app.services.gold_story.gold_chat.repair import GoldChatContractError
    contract, seed, _data = _source_plan_fixture()
    # 两个相邻的同角色真实拍都可占一个或两个素材单元，不能凭位置猜语义。
    beats = [{"speaker": "昭昭", "intent": "第一个真实事件"},
             {"speaker": "昭昭", "intent": "第二个真实事件"}]
    ambiguous = [{**seed[1], "intent": f"独立事实{i}"} for i in range(3)]
    with pytest.raises(GoldChatContractError, match="不唯一"):
        gex._source_plan_skeleton(contract, beats, ambiguous)


@pytest.mark.parametrize("corruption", [None, "empty", "missing", "rewrite", "duplicate", "reverse", "wrong_owner", "invalid_json", "budget", "synthetic", "out_of_range"])
def test_explicit_source_mapping_supports_multi_role_turns_without_rewriting(monkeypatch, corruption):
    from copy import deepcopy
    from app.services.gold_story.gold_chat.repair import GoldChatContractError, GoldChatSourceMappingError

    contract, seed, _ = _source_plan_fixture()
    seed.insert(4, {"speaker": "妈妈" if corruption == "budget" else "灿灿", "intent": "同一事件中的独立追问内容"})
    original = deepcopy(seed)
    beats = contract["beat_chain"]
    with pytest.raises(GoldChatSourceMappingError):
        gex._source_plan_skeleton(contract, beats, seed)
    ids = [1, 2, 3, 4, 4, 4, 5, 6, 6, 7]
    assignments = [{"seed_id": i, "beat": bid} for i, bid in enumerate(ids, 1)]
    skeleton = gex._source_plan_skeleton(contract, beats, seed, source_beats=ids)
    if corruption == "empty":
        assignments = []
    elif corruption == "out_of_range":
        assignments[-1]["beat"] = len(beats) + 1
    elif corruption == "synthetic":
        beats[3]["intent"] = "这话我可有点不信，你可得说清楚才行。"
    elif corruption == "missing":
        assignments.pop()
    elif corruption == "rewrite":
        assignments[0]["intent"] = "不允许模型改写原素材"
    elif corruption == "duplicate":
        assignments[1]["seed_id"] = 1
    elif corruption == "reverse":
        assignments[2]["beat"] = 1
    elif corruption == "wrong_owner":
        assignments[2]["beat"] = 4  # 第3拍灿灿的素材覆盖丢失
    elif corruption == "budget":
        contract["mom_lines_max"] = 1
        contract["parent_lines_max"] = 1
    calls = []
    reactions = ["听完刚才的话再确认那个问题", "对已经说出的理由提出具体疑问", "用前一句提到的东西来作比较", "接着刚说到的结果问个明白"]
    def chat(system, user, **_kwargs):
        calls.append((system, user))
        if len(calls) == 1:
            if corruption == "invalid_json":
                raise ValueError("invalid JSON")
            assert "角色顺序快路失败诊断" in user
            return {"assignments": assignments}
        ri = iter(reactions)
        return {"lines": [{"i": i, "line": next(ri), "intent": "不得覆盖直接台词"} for i, row in enumerate(skeleton, 1) if row["role"] == "reaction"]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    if corruption:
        with pytest.raises(GoldChatContractError) as caught:
            gex._build_source_line_plan(scene_contract=contract, beat_chain=beats, seed=seed,
                                        story_raw="完整源故事", temperature=0.4)
        assert len(calls) == 1, "结构错误不应继续请求接话填词"
        if corruption == "empty":
            assert "模型判断" in str(caught.value)
        elif corruption == "synthetic":
            assert "合成反应拍" in str(caught.value)
    else:
        plan = gex._build_source_line_plan(scene_contract=contract, beat_chain=beats, seed=seed,
                                          story_raw="完整源故事", temperature=0.4)
        content = [row for row in plan if row["role"] == "content"]
        assert [row["source_seed_ids"] for row in content] == [[i] for i in range(1, len(seed) + 1)]
        assert [(row["speaker"], row["intent"]) for row in content] == [(s["speaker"], s["intent"]) for s in seed]
        assert {row["speaker"] for row in content if row["beat"] == 4} == {"昭昭", "灿灿"}
        assert len(calls) == 2
        assert [r["intent"] for r in plan if r["role"] == "reaction"] == reactions[:sum(r["role"] == "reaction" for r in plan)]
    assert seed == original


def test_source_plan_content_cannot_be_overwritten_by_reaction_planner():
    contract, _seed, data = _source_plan_fixture()
    original = data["lines"][0]["intent"]
    merged = gex._merge_line_plan_intents(data["lines"], {"lines": [{"i": 1, "intent": "替换成无关素材"}]})
    assert merged[0]["intent"] == original


def test_source_plan_keeps_addressee_through_planning_and_filling():
    contract, seed, data = _source_plan_fixture()
    seed[0]["addressee"] = "灿灿"
    plan, errors = gex._validate_source_line_plan(data, scene_contract=contract,
                                               beat_chain=contract["beat_chain"], seed=seed)
    assert errors == []
    merged = gex._merge_line_plan_intents(plan, {"lines": []})
    slots = gex._line_plan_slots(merged, contract["beat_chain"])
    assert slots[0]["addressee"] == "灿灿"


def test_source_reaction_preserves_witness_role_outside_synthetic_beat():
    beats = [{"beat": 1, "speaker": "妈妈", "intent": "要求姐姐说清楚"},
             {"beat": 2, "speaker": "昭昭", "intent": "旁观", "witness_only": True}]
    plan = [{"beat": 1, "speaker": "妈妈", "role": "content", "source_plan": True,
             "intent": "你说清楚", "addressee": "灿灿"},
            {"beat": 1, "speaker": "昭昭", "role": "reaction", "source_plan": True, "intent": "听后感受"}]
    slots = gex._line_plan_slots(plan, beats)
    assert slots[1]["witness_only"] and slots[1]["has_content"] is False
    assert not slots[0]["witness_only"]


@pytest.mark.parametrize("corruption", ["speaker", "duplicate", "mapping", "order"])
def test_source_plan_rejects_lost_or_misassigned_material(corruption):
    contract, seed, data = _source_plan_fixture()
    if corruption == "speaker":
        data["lines"][0]["speaker"] = "灿灿"
    elif corruption == "duplicate":
        data["lines"][3]["source_seed_ids"] = [2]
    elif corruption == "mapping":
        data["beat_sources"]["2"] = []
    else:
        data["lines"][1]["source_seed_ids"], data["lines"][3]["source_seed_ids"] = [4], [2]
    _plan, errors = gex._validate_source_line_plan(
        data, scene_contract=contract, beat_chain=contract["beat_chain"], seed=seed)
    assert errors


def test_source_plan_is_used_when_material_units_outnumber_beats(monkeypatch):
    contract, seed, data = _source_plan_fixture()
    output = {"lines": [{"i": i, "intent": r["intent"]} for i, r in enumerate(data["lines"], 1) if r["role"] == "reaction"]}
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: output)
    monkeypatch.setattr(gex, "_line_plan_skeleton", lambda *_a, **_kw: pytest.fail("不得再把多个素材压回一行"))
    plan = gex._build_line_plan(scene_contract=contract, beat_chain=contract["beat_chain"],
                                seed=seed, story_raw="固定源稿", temperature=0.4, target_lines=12)
    assert len(plan) == 12
    assert sum(r["role"] == "content" for r in plan) == len(seed)


def test_source_plan_does_not_force_reason_into_unrelated_last_answer():
    contract, _seed, data = _source_plan_fixture()
    slots = gex._line_plan_slots(data["lines"], contract["beat_chain"])
    out = gex._apply_n_word_slots(slots, structure_type="N")
    assert not any(s.get("must_words") == list(gex._N_SLOT_WORD_REQS["reason"]) for s in out)
    assert all(s["has_content"] is False for s in out if s["is_filler"])


def test_source_plan_preserves_full_material_with_extra_synthetic_witness(monkeypatch):
    seed = [{"speaker": "妈妈" if i % 2 == 0 else "灿灿", "intent": f"第{i}个完整独立问答"}
            for i in range(12)]
    beats = [dict(s) for s in seed]
    beats.insert(2, {"speaker": "昭昭", "intent": "旁观当场反应", "witness_only": True})
    for i, beat in enumerate(beats, 1):
        beat["beat"] = i
    contract = {"story_type": "F", "characters": ["妈妈", "昭昭", "灿灿"],
                "mom_lines_max": 6, "beat_chain": beats}
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: {"lines": []})
    monkeypatch.setattr(gex, "_line_plan_skeleton", lambda *_a, **_kw: pytest.fail("完整素材不能压回意图"))
    plan = gex._build_line_plan(scene_contract=contract, beat_chain=beats, seed=seed,
                                story_raw="完整原文", temperature=0.4, target_lines=13)
    content = [r for r in plan if r["role"] == "content"]
    assert [(r["speaker"], r["intent"]) for r in content] == [(s["speaker"], s["intent"]) for s in seed]
    assert not any(r["beat"] == 3 for r in content)


def test_source_plan_is_shown_to_semantic_reviewer():
    from app.services.daily_story.review import build_review_prompts
    story = {"source_raw": "原始素材证据", "dialogue": [],
             "gold_source_line_plan": [{"line": 1, "role": "content", "source_seed_ids": [1], "intent": "唯一素材"}]}
    _, prompt = build_review_prompts("测试", story)
    assert "原始素材证据" in prompt and "唯一素材" in prompt
    assert "任一不满足就报硬伤" in prompt


def test_intent_cleaner_preserves_lists_and_retrospective_context():
    from app.services.gold_story.gold_chat.prompts import _perbeat_clean_intent
    for text in ["宝宝、妈妈、爸爸，三个人，我掰手指数的。", "上次商场走丢，民警叔叔问你什么了？"]:
        assert _perbeat_clean_intent(text) == text


def test_source_audit_requires_every_line_and_actual_evidence():
    from copy import deepcopy
    from app.services.daily_story.review import _validate_source_audit
    story = {"dialogue": [{"speaker": "昭昭", "line": "我选的是这个。"}],
             "gold_source_line_plan": [{"line": 1, "speaker": "昭昭", "role": "content", "source_seed_ids": [1]}]}
    raw = {"source_audit": [{"line": 1, "role": "content", "source_seed_ids": [1],
                             "pass": True, "quote": "我选的是这个", "reason": "素材完整且角色一致"}]}
    assert _validate_source_audit(raw, story) == ""
    assert _validate_source_audit({}, story)
    for field, value in [("pass", None), ("quote", "根本不在原句"), ("source_seed_ids", [2]), ("line", True)]:
        altered = deepcopy(raw)
        altered["source_audit"][0][field] = value
        assert _validate_source_audit(altered, story)
    from app.services.daily_story.review import _source_audit_failures
    raw["source_audit"][0]["pass"] = False
    assert _validate_source_audit(raw, story) == ""
    assert _source_audit_failures(raw)[0]["source_audit_failed"] is True


def test_source_plan_defers_pronoun_completeness_to_full_review():
    slot = _perbeat_test_slot(intent="指认选择")
    slot.update(source_plan=True, planned_content=True, source_seed_ids=[1])
    assert not gex._perbeat_check(slot, "我选的就是这个。", [])
    assert gex._perbeat_check(slot, "我选的就是这个", [])


def _rhetorical_story_fixture():
    from app.services.daily_story.story_types.n.validate import source_rhetorical_contract
    texts = ["你刚才到底拿了哪本书？", "反正装进书包就能带走呀。", "封面是我的名字，书还能归你吗？",
             "不是进了我的书包就算我的了吗？", "你的书包可没把封面名字换掉。", "可书现在就在我书包里呀。", "连书包都能认主人了，我服了。"]
    # 不以传统因果连接词满足机检，专门验证来源声明的反问形态。
    texts[1] = "我把那本书装进自己书包里了。"
    owners = ["妈妈", "昭昭", "灿灿", "昭昭", "灿灿", "昭昭", "妈妈"]
    plan = [{"line": i, "speaker": sp, "role": "content", "source_seed_ids": [i],
             "intent": text, "speech_act": "echo" if i == 4 else "other"}
            for i, (sp, text) in enumerate(zip(owners, texts), 1)]
    return {"story_type": "N", "dialogue": [{"speaker": sp, "line": text} for sp, text in zip(owners, texts)],
            "gold_source_line_plan": plan, "gold_n_expression_contract": source_rhetorical_contract(plan)}


def test_rhetorical_n_requires_source_declaration_and_matches_all_score_gates():
    from copy import deepcopy
    from app.services.daily_story.story_types.n.validate import n_structure_hits, append_n_body_errors
    from app.services.daily_story.story_types.n.humor import collect_n_humor_issues, score_funniness_tail
    from app.services.daily_story.story_types.n.quality import score_punchline
    story = _rhetorical_story_fixture()
    lines = [r["line"] for r in story["dialogue"]]
    assert n_structure_hits(lines, story) == (True, True, True)
    errors = []
    append_n_body_errors(story, errors)
    assert errors == []
    assert collect_n_humor_issues(lines, story=story) == []
    assert score_funniness_tail(lines, story=story)[0] == 10
    assert score_punchline(lines, [], "", "", story=story)[0] == 8
    assert n_structure_hits(lines)[2] is False
    changed = deepcopy(story)
    changed["gold_source_line_plan"][3]["speech_act"] = "other"
    assert n_structure_hits(lines, changed)[2] is False
    changed = list(lines)
    changed[3] = "这本书现在在我的书包里面。"
    assert n_structure_hits(changed, story)[2] is False


def test_rhetorical_n_needs_four_semantic_audits_in_addition_to_source_audit():
    from app.services.daily_story.review import _validate_source_audit, _source_audit_failures
    story = _rhetorical_story_fixture()
    raw = {"source_audit": [{**r, "pass": True, "quote": r["intent"], "reason": "素材完整"}
                            for r in story["gold_source_line_plan"]]}
    assert "n_structure_audit" in _validate_source_audit(raw, story)
    raw["n_structure_audit"] = [{"aspect": aspect, "line": story["gold_n_expression_contract"][f"{aspect}_line"],
                                 "pass": True, "quote": story["dialogue"][story["gold_n_expression_contract"][f"{aspect}_line"] - 1]["line"],
                                 "reason": "结合前文有对应结构关系"}
                                for aspect in ("challenge", "followup", "reason", "closing")]
    assert _validate_source_audit(raw, story) == ""
    raw["n_structure_audit"][2]["pass"] = False
    assert _source_audit_failures(raw)[0]["lines"] == [4]


@pytest.mark.parametrize("line", ["难道装进书包的还不归我？", "谁说我的书包能装别人的书？"])
def test_rhetorical_declaration_does_not_require_one_question_phrase(line):
    from app.services.daily_story.story_types.n.validate import source_rhetorical_contract, n_structure_hits
    story = _rhetorical_story_fixture()
    story["gold_source_line_plan"][3]["intent"] = line
    story["dialogue"][3]["line"] = line
    assert source_rhetorical_contract(story["gold_source_line_plan"]) == story["gold_n_expression_contract"]
    assert n_structure_hits([r["line"] for r in story["dialogue"]], story) == (True, True, True)


def test_source_revision_keeps_candidate_context_and_merges_only_failed_lines(monkeypatch):
    slots = [{"speaker": "昭昭" if i % 2 else "灿灿", "intent": f"独立内容{i}", "source_plan": True}
             for i in range(12)]
    original = {i: f"这是第{i}句原始台词。" for i in range(1, 13)}
    calls = []
    def chat(_system, user, **_kwargs):
        calls.append(user)
        if len(calls) == 1:
            return {"lines": [{"i": i, "line": line} for i, line in original.items()]}
        assert original[4] in user  # 失败原句仍留在实际上下文，不删出候选。
        assert "需要改写" in user
        return {"lines": [{"i": 4, "line": "这是已按要求扩写后的第四句台词。"},
                          {"i": 3, "line": "模型越权改动不应采纳。"}]}
    def validate(_slots, filled):
        lines = [(s["speaker"], filled.get(i, "")) for i, s in enumerate(_slots, 1)]
        return lines, [(4, filled[4], "须补全原句指代")] if filled[4] == original[4] else []
    monkeypatch.setattr(gex, "_chat_json", chat)
    monkeypatch.setattr(gex, "_source_plan_model", lambda: None)
    monkeypatch.setattr(gex, "_perbeat_validate_fill", validate)
    lines, errors = gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4)
    assert errors == []
    assert len(lines) == 12 and lines[2][1] == original[3]
    assert lines[3][1] == "这是已按要求扩写后的第四句台词。"


def test_source_plan_cannot_receive_template_lines_from_length_stabilizer(monkeypatch):
    from app.services.gold_story.gold_chat import length
    from copy import deepcopy
    story = _rhetorical_story_fixture()
    before = deepcopy(story)
    monkeypatch.setattr(length, "_boost_short_with_mid_lines", lambda *_a, **_kw: pytest.fail("不得插模板行"))
    result, changed = length._stabilize_local_length_candidate(story, structure_type="N", mechanism="M6")
    assert not changed and result == before


@pytest.mark.parametrize("source_plan", [False, True])
def test_unparsable_first_fill_retries_full_assignment(source_plan, monkeypatch):
    slots = [{"speaker": "妈妈", "intent": "要求练琴", "beat_id": 1, "source_plan": source_plan}]
    calls = []
    def chat(_system, user, **_kwargs):
        calls.append(user)
        assert "【分配表】" in user and "【需要改写】" not in user
        if len(calls) == 1:
            return {}
        assert "上一轮没有按要求输出 JSON" in user
        return {"lines": [{"i": 1, "line": "今天的钢琴还没练，赶紧去吧。"}]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    monkeypatch.setattr(gex, "_source_plan_model", lambda: None)
    monkeypatch.setattr(gex, "_perbeat_validate_fill", lambda _s, filled: ([("妈妈", filled[1])], []))
    lines, failures = gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4,
                                            source_text="妈妈要求孩子练琴。")
    assert not failures and len(lines) == 1 and len(calls) == 2


def test_witness_plan_requests_contextual_reaction_instead_of_fixed_template():
    from app.services.gold_story.gold_chat.prompts import LINE_PLAN_SYSTEM, format_line_plan_user
    beats = [
        {"beat": 1, "speaker": "妈妈", "intent": "问为什么不练琴"},
        {"beat": 2, "speaker": "灿灿", "intent": "反问看书为什么不行"},
        {"beat": 3, "speaker": "昭昭", "intent": "我就在旁边听着，你慢慢说。", "witness_only": True},
        {"beat": 4, "speaker": "妈妈", "intent": "拒绝讨论并要求练琴"},
    ]
    contract = {"story_type": "F", "characters": ["妈妈", "昭昭", "灿灿"], "mom_lines_max": 3}
    rows = gex._line_plan_skeleton(contract, beats, target_lines=4)
    assert rows[2]["from_beat"] is False and rows[2]["role"] == "reaction"
    planned = gex._merge_line_plan_intents(rows, {"lines": [{"i": 3, "intent": "指出两种爱好都需要认真学习"}]})
    assert planned[2]["intent"] == "指出两种爱好都需要认真学习"
    assert planned[1]["intent"] == beats[1]["intent"]
    slot = gex._line_plan_slots(planned, beats, no_material_speakers={"昭昭"})[2]
    assert slot["is_filler"] and slot["witness_only"] and not slot["has_content"]
    prompt = format_line_plan_user(scene_contract=contract, story_raw="原素材", rows=rows)
    assert "旁观反应位" in prompt and "我就在旁边听着" not in prompt
    plan = json.loads(prompt.split("【完整只读句序（固定主句与反应位都在内）】\n", 1)[1].split("\n", 1)[0])
    assert len(plan) == 4 and plan[3]["intent"] == beats[3]["intent"]
    assert plan[3]["fixed"] and not plan[2]["fixed"]
    assert "【需要填写的实际序号】[3]" in prompt
    assert '【输出】{"lines": [{"i": 3,' in prompt
    assert "不从1重新编号" in LINE_PLAN_SYSTEM and "i 从 1 连续编号" not in LINE_PLAN_SYSTEM


@pytest.mark.parametrize("line", ["我为什么要去自证这个？", "今天我就想挑选那个。", "吃完饭应该轮到你洗碗。", "我今天上台一点也不紧张。"])
def test_complete_sentences_do_not_fail_for_ambiguous_last_character(line):
    assert gex._perbeat_line_shape_ok(line)


def _source_f_structure_fixture():
    from app.services.daily_story.story_types.f.validate import source_f_binding, F_SOURCE_ASPECTS
    lines = ["你把借来的书放哪儿了？", "借给我的书还要管我怎么放？", "你到底有没有听我说话？",
             "书是我借的，还轮不到你来管。", "我是来找书的，别扯到别的事上。", "反正这件事情我不会听你的。",
             "那就留到明天再谈，今天先到这里。"]
    story = {"story_type": "F", "source_link_review": True, "source_raw": "父亲和孩子争论：" + "".join(lines),
             "source_role_mapping": "父亲→妈妈", "dialogue": [{"speaker": "妈妈" if i % 2 == 0 else "灿灿", "line": s}
                                                            for i, s in enumerate(lines)]}
    items = [{"aspect": aspect, "line": no, "pass": True, "quote": lines[no - 1][:8],
              "source_quote": lines[no - 1], "reason": "原文和对白均体现该阶段的对峙"}
             for aspect, no in zip(F_SOURCE_ASPECTS, [2, 4, 6, 7])]
    story["gold_f_source_structure"] = {"binding": source_f_binding(story), "items": items}
    return story


@pytest.mark.parametrize("mutation", ["line", "speaker", "source", "mapping", "quote", "negative", "order", "missing"])
def test_source_f_structure_requires_current_complete_evidence(mutation):
    from app.services.daily_story.story_types.f.validate import source_f_structure_valid
    story = _source_f_structure_fixture()
    assert source_f_structure_valid(story)
    if mutation == "line": story["dialogue"][0]["line"] += "真的。"
    if mutation == "speaker": story["dialogue"][0]["speaker"] = "昭昭"
    if mutation == "source": story["source_raw"] += "新事实"
    if mutation == "mapping": story["source_role_mapping"] = "父亲→昭昭"
    if mutation == "quote": story["gold_f_source_structure"]["items"][0]["source_quote"] = "完全不在原文里的话"
    if mutation == "negative": story["gold_f_source_structure"]["items"][0]["pass"] = False
    if mutation == "order": story["gold_f_source_structure"]["items"][1]["line"] = 1
    if mutation == "missing": story["gold_f_source_structure"]["items"].pop()
    assert not source_f_structure_valid(story)


def test_source_f_final_review_is_independent_and_mandatory():
    from copy import deepcopy
    from app.services.daily_story.review import _validate_source_audit, _source_audit_failures, build_review_prompts
    story = _source_f_structure_fixture()
    assert _validate_source_audit({"issues": []}, story)
    raw = {"f_structure_audit": deepcopy(story["gold_f_source_structure"]["items"])}
    assert _validate_source_audit(raw, story) == ""
    raw["f_structure_audit"][1]["pass"] = False
    assert _source_audit_failures(raw)[0]["lines"] == [4]
    assert _source_audit_failures(raw)[0]["source_audit_failed"] is True
    _, user = build_review_prompts("借书争执", story)
    assert "F来源结构独立终审" in user and "前序程序的结构分不能充当通过证据" in user


def test_source_f_quote_hint_never_accepts_a_paraphrased_quote():
    from app.services.daily_story.story_types.f.validate import source_f_audit_error, source_f_structure_valid
    story = _source_f_structure_fixture()
    items = story["gold_f_source_structure"]["items"]
    items[0]["source_quote"] = "借给我的书还要管我怎么放呀？"
    error = source_f_audit_error(story, items)
    assert "相近原文" in error and "借给我的书还要管我怎么放？" in error
    assert not source_f_structure_valid(story)


def test_source_f_evidence_survives_expression_metadata_but_not_changed_line():
    from app.services.daily_story.story_types.f.validate import source_f_structure_valid
    story = _source_f_structure_fixture()
    story["dialogue"][0]["expression"] = "疑惑"
    assert source_f_structure_valid(story)
    story["dialogue"][0]["line"] += "新事实"
    assert not source_f_structure_valid(story)


@pytest.mark.parametrize("repair_ok", [True, False])
def test_source_f_audit_repairs_format_with_numbered_dialogue(monkeypatch, repair_ok):
    from copy import deepcopy
    from app.services.daily_story.story_types.f.validate import source_f_structure_valid
    story = _source_f_structure_fixture()
    items = story.pop("gold_f_source_structure")["items"]
    calls = []

    def chat(_system, user, **_kw):
        calls.append(user)
        if len(calls) == 1:
            assert json.loads(user)["dialogue"][-1]["line"] == 7
        answer = deepcopy(items)
        if len(calls) == 1 or not repair_ok:
            answer[-1]["line"] = 6
        return {"f_structure_audit": answer}

    monkeypatch.setattr(gex, "_chat_json", chat)
    if repair_ok:
        gex._audit_source_f_structure(story)
        assert source_f_structure_valid(story)
    else:
        with pytest.raises(ValueError, match="审核格式无法核验"):
            gex._audit_source_f_structure(story)
        assert not source_f_structure_valid(story)
    assert len(calls) == 2


def test_source_f_structure_evidence_does_not_trigger_template_patches():
    from copy import deepcopy
    from app.services.daily_story.story_types.f.patch import patch_f_append_stale_close, patch_f_ensure_escalation
    story = _source_f_structure_fixture()
    before = deepcopy(story)
    patch_f_append_stale_close(story)
    patch_f_ensure_escalation(story)
    assert story == before


def test_source_f_negative_final_stage_blocks_even_with_empty_issues(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from app.services.daily_story import review
    from app.services.llm import llm_mgr
    story = _source_f_structure_fixture()
    raw = {"issues": [], "f_structure_audit": deepcopy(story["gold_f_source_structure"]["items"])}
    raw["f_structure_audit"][1]["pass"] = False
    monkeypatch.setattr(llm_mgr, "_get_client", lambda: SimpleNamespace(_chat_json=lambda *_a, **_k: (raw, None)))
    monkeypatch.setattr(review, "_validate_export_review_raw", lambda *_a, **_k: "")
    result = review.run_export_semantic_review("借书争执", story)
    assert result.completed and result.issues[0]["source_audit_failed"]
    assert result.issues[0]["lines"] == [4]


def test_repeated_draft_failure_contract_reuse_requires_source_evidence(monkeypatch):
    source = "爸爸先问作业，女儿回答写完了；爸爸后来才问书包。"
    row = {"payload": {"gold_chat_convert_stats": {"last_stage": "draft", "failures": 2},
                       "scene_contract": {"beat_chain": [{"intent": "先问作业和书包，再让孩子回答"}]}}}
    reply = {"compatible": False, "issues": [{"contract_quote": "先问作业和书包", "source_quote": "爸爸后来才问书包",
                                              "reason": "合并了中间隔着答话的两个问题，应按源文拆分"}]}
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_k: reply)
    assert gc._failed_contract_source_conflicts(row, source) == [reply["issues"][0]["reason"]]
    reply["issues"][0]["source_quote"] = "原文没有这段话"
    with pytest.raises(ValueError, match="证据无法核验"):
        gc._failed_contract_source_conflicts(row, source)
    row["payload"]["gold_chat_convert_stats"]["failures"] = 1
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_k: pytest.fail("非连续失败不触发新审核"))
    assert gc._failed_contract_source_conflicts(row, source) == []
    row["payload"]["gold_chat_convert_stats"]["failures"] = 2
    row["_gold_chat_rebuild_contract"] = "已重建过一次"
    assert gc._failed_contract_source_conflicts(row, source) == []


def test_old_draft_failures_do_not_rebuild_updated_source_contract(monkeypatch):
    from app.services.gold_story.gold_chat.status import gold_chat_candidate_contract
    from copy import deepcopy
    row = _sample_row()
    row["payload"]["scene_contract"] = {"beat_chain": [{"speaker": "妈妈", "intent": "问孩子去哪儿"}]}
    old = deepcopy(gold_chat_candidate_contract(row))
    row["payload"]["gold_chat_candidate_contract"] = old
    row["payload"]["gold_chat_convert_stats"] = {"last_stage": "draft", "failures": 3}
    row["payload"]["scene_contract"]["beat_chain"][0]["intent"] = "已经重建的完整问答"
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: pytest.fail("旧契约失败不能触发新契约重建"))
    assert gc._failed_contract_source_conflicts(row, "完整原文") == []


@pytest.mark.parametrize("step", ["build_scene_contract", "build_dialogue_seed"])
def test_contract_rebuild_feedback_reaches_both_generation_steps(step, monkeypatch):
    from app.services.gold_story.collect import llm
    def capture(_system, user):
        assert "两个相隔的问题错误合并" in user
        assert "旧契约已被原文证据否定" in user or "旧seed已因遗漏/错序不可复用" in user
        raise RuntimeError("captured rebuild instruction")
    monkeypatch.setattr(llm, "_chat_json", capture)
    with pytest.raises(RuntimeError, match="captured rebuild instruction"):
        getattr(llm, step)(story_raw="父亲问了第一个问题，孩子回答，父亲再问另一件事。",
                           h3={"generation_constraints": {"previous_plan_error": "两个相隔的问题错误合并"}})


@pytest.mark.parametrize("line", ["妈妈我已经想好了但是。", "妈妈我已经想好了因为。", "这句话还没有结束", "长" * 24 + "。"])
def test_shape_check_keeps_length_punctuation_and_conjunction_limits(line):
    assert not gex._perbeat_line_shape_ok(line)


def test_synthetic_witness_beat_cannot_expand_into_another_speakers_turn():
    owners = ["妈妈", "灿灿", "昭昭", "妈妈", "灿灿", "妈妈", "灿灿", "妈妈", "灿灿", "妈妈"]
    beats = [{"beat": i, "speaker": sp, "intent": f"说明第{i}项安排"} for i, sp in enumerate(owners, 1)]
    beats[2].update(witness_only=True, intent="我就在旁边听着，你慢慢说。")
    contract = {"characters": ["妈妈", "灿灿", "昭昭"], "mom_lines_max": 5, "story_type": "F"}
    plan = gex._line_plan_skeleton(contract, beats, target_lines=12, no_material_speakers={"昭昭"})
    assert len(plan) == 12
    witness = [r for r in plan if r["beat"] == 3]
    assert len(witness) == 1 and witness[0]["speaker"] == "昭昭"
    assert all(a["speaker"] != b["speaker"] for a, b in zip(plan, plan[1:]))
    assert all("我就在旁边听着" not in r.get("intent", "") for r in plan)


def test_party_reaction_is_classified_before_first_fill(monkeypatch):
    slots = [{"speaker": "灿灿", "intent": "旁观安抚", "beat_id": 1, "is_filler": True}]
    contract = {"beat_chain": [{"beat": 1, "speaker": "灿灿", "intent": "反对安排", "speech_act": "deny"}]}
    def chat(_system, user, **_kwargs):
        assert "当事人在场反应" in user and "旁观安抚" not in user
        return {"lines": [{"i": 1, "line": "你这个安排对我可不公平啊。"}]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    monkeypatch.setattr(gex, "_perbeat_validate_fill", lambda _s, filled: ([("灿灿", filled[1])], []))
    _, failures = gex._perbeat_fill_slots(slots, scene_contract=contract, punchline="", temperature=0.4)
    assert not failures


def test_revision_repairs_preempting_reaction_without_changing_source_line(monkeypatch):
    slots = [{"speaker": "妈妈", "intent": "要求练琴", "beat_id": 1},
             {"speaker": "昭昭", "intent": "围绕前文接话", "is_filler": True, "beat_id": 2},
             {"speaker": "灿灿", "intent": "询问看书是否算爱好", "beat_id": 3}]
    original = {1: "今天的钢琴还没练，赶紧去吧。", 2: "那看书算不算爱好，妈你给我个说法。",
                3: "那看书到底算不算爱好，你说清楚。"}
    replacement = "你俩还在讨论练琴，我都听半天了。"
    calls = []
    def chat(_system, user, **_kwargs):
        calls.append(user)
        if len(calls) == 1:
            return {"lines": [{"i": i, "line": line} for i, line in original.items()]}
        targets = json.loads(user.split("【需要改写】", 1)[1].split("\n", 1)[0])
        assert [target["i"] for target in targets] == [2]
        assert "保持第3句不动" in targets[0]["must_fix"]
        return {"lines": [{"i": 2, "line": replacement},
                          {"i": 1, "line": "无关内容也一起改了。"},
                          {"i": 3, "line": "我不要看书了，去练琴。"}]}
    def validate(_slots, filled):
        lines = [(s["speaker"], filled.get(i, "")) for i, s in enumerate(_slots, 1)]
        duplicate = gex._perbeat_restates(filled[3], [(slots[1]["speaker"], filled[2])])
        return lines, [(3, filled[3], "不得复述前文")] if duplicate else []
    monkeypatch.setattr(gex, "_chat_json", chat)
    monkeypatch.setattr(gex, "_perbeat_validate_fill", validate)
    lines, failures = gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4,
                                            source_text="母亲要求练琴，孩子询问看书是否也算爱好。")
    assert not failures and len(calls) == 2
    assert lines == [("妈妈", original[1]), ("昭昭", replacement), ("灿灿", original[3])]


def test_revision_dependency_keeps_validation_errors_and_unrelated_failures():
    slots = [{"speaker": "昭昭", "is_filler": True}, {"speaker": "灿灿"}, {"speaker": "妈妈"}]
    filled = {1: "那看书算不算爱好，妈你给我个说法。", 2: "那看书到底算不算爱好，你说清楚。", 3: "长句"}
    failures = [(1, filled[1], "插话须有具体内容"), (2, filled[2], "不得复述前文；须补全指代"),
                (3, filled[3], "须 8–24 字")]
    before = list(failures)
    repair = gex._perbeat_revision_failures(slots, filled, failures)
    assert failures == before
    assert [i for i, _, _ in repair] == [1, 3]
    assert "插话须有具体内容" in repair[0][2] and "保持第2句不动" in repair[0][2]
    assert repair[1] == failures[2]
    # 先修插话后，内容行的其余缺陷仍交给原校验和下一轮返修。
    filled[1] = "你俩还在讨论练琴，我都听半天了。"
    remaining = [(2, filled[2], "须补全指代")]
    assert gex._perbeat_revision_failures(slots, filled, remaining) == remaining
    # 全文返修与内容行之间重复不套用插话依赖改写。
    assert gex._perbeat_revision_failures(slots, filled, failures + [(0, "全文", "超长")]) == failures + [(0, "全文", "超长")]
    slots[0]["is_filler"] = False
    filled[1] = before[0][1]
    assert gex._perbeat_revision_failures(slots, filled, failures) == failures


def test_revision_prompt_carries_compression_target_and_semantic_requirements():
    from app.services.gold_story.gold_chat.prompts import format_source_revision_user
    slot = {"speaker": "妈妈", "intent": "回顾外出并建议记录", "beat_id": 4,
            "required_word_groups": [["外地", "跨省"]], "must_words": ["记录"],
            "required_semantic_terms": [["未告知", "没说"]]}
    line = "你出门之前也没跟家里人说一声，以后把这些事都记录下来。"
    prompt = format_source_revision_user(scene_contract={}, slots=[slot], filled={1: line},
                                         failures=[(1, line, "须 8–24 字")], source_text="原文")
    target = json.loads(prompt.split("【需要改写】", 1)[1].split("\n", 1)[0])[0]
    assert target["over_limit_chars"] == len(line) - 24 and target["compression_target"] == 22
    for field in ("required_word_groups", "must_words", "required_semantic_terms"):
        assert target[field] == slot[field]


@pytest.mark.parametrize("invalid", [None, "source", "quote", "previous", "missing", "negative", "unsupported", "line_number"])
def test_dialogue_link_audit_requires_complete_source_evidence(monkeypatch, invalid):
    source = "妈妈问他为什么不练琴，孩子反问：你自己今天练过了吗？"
    slots = [{"speaker": "妈妈", "intent": "问为什么不练琴"},
             {"speaker": "灿灿", "intent": "反问妈妈是否练琴", "_audit_source_text": source}]
    filled = {1: "今天为什么不练琴，你到底怎么想的？", 2: "你自己今天练过了吗，凭什么光问我？"}
    failures = [(2, filled[2], "必须先正面回答上一句的问题")]
    item = {"i": 2, "pass": True, "source_supports_act": True, "quote": "你自己今天练过了吗",
            "previous_quote": "今天为什么不练琴", "source_quote": "孩子反问：你自己今天练过了吗？", "reason": "原文明确反问母亲，当前人物关系一致"}
    if invalid == "source": item["source_quote"] = "不属于素材的证据"
    if invalid == "quote": item["quote"] = "没有说过的话"
    if invalid == "previous": item["previous_quote"] = "不属于前句"
    if invalid == "negative": item["pass"] = False
    if invalid == "unsupported": item["source_supports_act"] = False
    if invalid == "line_number": item["i"] = True
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: {"dialogue_link_audit": [] if invalid == "missing" else [item]})
    assert gex._audit_perbeat_dialogue_links(slots, filled, failures, source_text=source) is (invalid is None)
    assert ("_dialogue_link_audit" in slots[1]) is (invalid is None)


def test_link_audit_approval_expires_when_context_line_or_source_changes(monkeypatch):
    source = "母亲要求他交代是谁打碎杯子，孩子反问今天轮到谁洗碗。"
    slot = {"speaker": "灿灿", "intent": "反问今天轮到谁洗碗", "_audit_source_text": source}
    before = [("妈妈", "这只杯子到底是谁打碎的，你说明白？")]
    line = "今天轮到谁洗碗，你自己还记不记得？"
    assert "必须先正面回答上一句的问题" in gex._perbeat_check(slot, line, before)
    item = {"i": 2, "pass": True, "source_supports_act": True, "quote": "今天轮到谁洗碗",
            "previous_quote": "这只杯子到底是谁打碎的", "source_quote": "孩子反问今天轮到谁洗碗", "reason": "来源明示了转移话题"}
    monkeypatch.setattr(gex, "_chat_json", lambda *_a, **_kw: {"dialogue_link_audit": [item]})
    assert gex._audit_perbeat_dialogue_links([{"speaker": "妈妈"}, slot], {1: before[0][1], 2: line},
                                           [(2, line, "必须先正面回答上一句的问题")], source_text=source)
    assert "必须先正面回答上一句的问题" not in gex._perbeat_check(slot, line, before)
    assert "必须先正面回答上一句的问题" in gex._perbeat_check(slot, line + "？", before)
    assert "必须先正面回答上一句的问题" in gex._perbeat_check(slot, line, [("妈妈", "那只杯子到底是谁打碎的，你说明白？")])
    slot["_audit_role_mapping"] = "孩子改为另一人"
    assert "必须先正面回答上一句的问题" in gex._perbeat_check(slot, line, before)
    slot["_audit_role_mapping"] = ""
    slot["_audit_source_text"] = "另一个故事"
    assert "必须先正面回答上一句的问题" in gex._perbeat_check(slot, line, before)


@pytest.mark.parametrize("rewrite_quote", [False, True])
def test_link_audit_role_mapping_preserves_original_source_quotes(monkeypatch, rewrite_quote):
    source = "爸爸问女儿为什么不练琴，女儿反问爸爸今天练过了吗。"
    mapping = "爸爸→妈妈，女儿→灿灿"
    slots = [{"speaker": "妈妈"}, {"speaker": "灿灿", "_audit_role_mapping": mapping}]
    filled = {1: "今天为什么不练琴？", 2: "妈妈自己今天练过了吗？"}
    def chat(system, user, **_kwargs):
        request = json.loads(user)
        assert request["role_mapping"] == mapping and request["source_text"] == source
        assert "不得改写引文中的称谓" in system
        return {"dialogue_link_audit": [{"i": 2, "pass": True, "source_supports_act": True,
                "quote": "自己今天练过了吗", "previous_quote": "今天为什么不练琴",
                "source_quote": "女儿反问爸爸今天练过了吗" if not rewrite_quote else "灿灿反问妈妈今天练过了吗",
                "reason": "原文反问符合角色映射"}]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    approved = gex._audit_perbeat_dialogue_links(slots, filled, [(2, filled[2], "必须先正面回答")],
                                                source_text=source, role_mapping=mapping)
    assert approved is (not rewrite_quote)
    if approved:
        assert slots[1]["_dialogue_link_audit"]["role_mapping"] == mapping


def test_perbeat_length_revision_preserves_locked_rows_and_metadata(monkeypatch):
    from copy import deepcopy
    data = {"scene_title": "测试", "quality": {"semantic_pending": True},
            "dialogue": [{"speaker": "昭昭" if i % 2 else "灿灿", "line": "字" * 17 + "。"} for i in range(12)]}
    before = deepcopy(data)
    def chat(_system, user, **_kwargs):
        targets = json.loads(user.split("【需要改写】", 1)[1].split("\n", 1)[0])
        assert len(targets) == 6
        return {"lines": [{"i": t["i"], "line": "词" * 23 + "。"} for t in targets]
                + [{"i": 12, "line": "越权修改不能采纳。"}, {"i": 13, "line": "也不许新增句子。"}]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    out = gex._revise_perbeat_length(data, row={"story_raw": "原文"})
    assert data == before and len(out["dialogue"]) == 12
    assert out["quality"] == before["quality"]
    assert [r["speaker"] for r in out["dialogue"]] == [r["speaker"] for r in before["dialogue"]]
    assert out["dialogue"][6:] == before["dialogue"][6:]
    assert gex.dialogue_total_chars(out) == 252


@pytest.mark.parametrize("succeeds", [True, False])
def test_perbeat_short_after_normalization_revises_current_candidate_with_bound(monkeypatch, succeeds):
    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "1")
    data = {"scene_title": "测试", "source_raw": "只读原文",
            "dialogue": [{"speaker": "昭昭" if i % 2 else "灿灿", "line": "字" * 17 + "。"} for i in range(12)]}
    # 模拟确定性归一化使已有候选缩短；修稿必须看到缩短后的版本。
    def normalize(story, **_kwargs):
        if story["dialogue"][0]["line"] == "字" * 17 + "。":
            story["dialogue"][0]["line"] = "字" * 8 + "。"
        return story
    monkeypatch.setattr(gex, "_apply_gold_chat_local_hard_repairs", normalize)
    monkeypatch.setattr(gex, "_apply_expand_setting_normalize", lambda story, **_kw: story)
    checked = []
    def validate(story, **_kwargs):
        checked.append(gex.dialogue_total_chars(story))
        if checked[-1] < 216:
            raise ValueError(f"正文总字数须≥216，当前{checked[-1]}")
    monkeypatch.setattr(gc, "validate_gold_chat", validate)
    calls = []
    def chat(_system, user, **_kwargs):
        calls.append(user)
        assert "当前207字" in user
        targets = json.loads(user.split("【需要改写】", 1)[1].split("\n", 1)[0])
        return {"lines": [{"i": t["i"], "line": "词" * 23 + "。" if succeeds else t["current_line"]} for t in targets]}
    monkeypatch.setattr(gex, "_chat_json", chat)
    kwargs = dict(banned_literals=[], source_type="mixed", mom_lines_max=3)
    if succeeds:
        out = gex._validate_expand_chat(data, **kwargs)
        assert checked[-1] >= 216 and len(calls) == 1 and len(out["dialogue"]) == 12
    else:
        with pytest.raises(ValueError, match="正文总字数"):
            gex._validate_expand_chat(data, **kwargs)
        assert len(calls) == 2


@pytest.mark.parametrize("reaction", [True, False])
@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_source_fill_uses_bounded_revision_rounds_for_same_overlong_slot(monkeypatch, reaction, repair_succeeds):
    slots = [{"speaker": "昭昭" if i % 2 else "灿灿", "intent": f"内容{i}",
              "source_plan": True, "is_filler": reaction and i == 14}
             for i in range(18)]
    valid = "这是一条用于检验槽位字数的完整台词。"
    overlong = "这条台词原来实在太长了，需要压缩以后才能通过单句字数检查。"
    original = {i: overlong if i == 15 else valid for i in range(1, 19)}
    calls = []

    def chat(_system, user, **_kwargs):
        calls.append(user)
        if len(calls) == 1:
            return {"lines": [{"i": i, "line": line} for i, line in original.items()]}
        assert '"current_chars": 29' in user
        assert '"min_chars": 8' in user
        assert "压缩冗余措辞" in user
        repaired = valid if repair_succeeds and len(calls) == 3 else overlong
        return {"lines": [{"i": 15, "line": repaired}, {"i": 1, "line": "不应采纳的越权修改。"}]}

    monkeypatch.setattr(gex, "_chat_json", chat)
    lines, errors = gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4)
    assert len(calls) == 3  # 同槽失败也不能跳过最后一次定点修复。
    assert len(lines) == len(slots)
    assert [sp for sp, _ in lines] == [slot["speaker"] for slot in slots]
    assert lines[0][1] == original[1]
    if repair_succeeds:
        assert errors == [] and lines[14][1] == valid
    else:
        assert [i for i, _, _ in errors] == [15]
        assert lines[14][1] == overlong  # 不截断、丢句或伪报成功。


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_source_fill_repairs_total_length_before_returning_candidate(monkeypatch, repair_succeeds):
    slots = [{"speaker": "昭昭" if i % 2 else "灿灿", "intent": f"内容{i}", "source_plan": True}
             for i in range(18)]
    original = {i: "这句话用于检查补写以后是否保留原来的顺序。" for i in range(1, 19)}
    original[18] = "字" * 15 + "。"
    assert sum(map(len, original.values())) == 373
    calls = []

    def chat(_system, user, **_kwargs):
        calls.append(user)
        if len(calls) == 1:
            assert "最多370字" in user
            return {"lines": [{"i": i, "line": line} for i, line in original.items()]}
        assert "当前373字，上限370字" in user
        assert "至少压缩3字" in user
        # 全文返修允许只返回需要压缩的句子，其他槽原样保留。
        return {"lines": [{"i": 1, "line": "这是一条用于检验槽位字数的完整台词。" if repair_succeeds else original[1]}]}

    monkeypatch.setattr(gex, "_chat_json", chat)
    lines, errors = gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4)
    assert len(calls) == (2 if repair_succeeds else 3)
    assert len(lines) == 18
    assert [line for _, line in lines[1:]] == list(original.values())[1:]
    if repair_succeeds:
        assert errors == []
        assert sum(len(line) for _, line in lines) == 370
    else:
        assert len(errors) == 1 and errors[0][0] == 0
        assert "当前373" in errors[0][2]


def test_source_revision_keeps_global_and_local_constraints_together():
    from app.services.gold_story.gold_chat.prompts import format_source_revision_user

    prompt = format_source_revision_user(
        scene_contract={}, slots=[{"speaker": "灿灿", "intent": "原素材", "is_filler": True}],
        filled={1: "待改写句子。"}, source_text="原始素材",
        failures=[(1, "待改写句子。", "单句指代不明"), (0, "全文", "类型表达缺失"), (0, "全文", "全文超过上限")],
    )
    targets = json.loads(prompt.split("【需要改写】", 1)[1].split("\n", 1)[0])
    assert all(reason in targets[0]["must_fix"] for reason in ("单句指代不明", "类型表达缺失", "全文超过上限"))


@pytest.mark.parametrize("reaction,expected_calls", [(True, 1), (False, 2)])
def test_legacy_fill_retains_early_stop_for_unchanged_failures(monkeypatch, reaction, expected_calls):
    slots = [{"speaker": "昭昭" if i % 2 else "灿灿", "intent": f"内容{i}",
              "is_filler": reaction and i == 14} for i in range(18)]
    calls = []
    line = "这是一条用于检验槽位字数的完整台词。"

    def chat(*_args, **_kwargs):
        return {"lines": [{"i": i, "line": line} for i in range(1, 19)]}

    def validate(_slots, _filled):
        calls.append(True)
        return [(slot["speaker"], line) for slot in _slots], [(15, line, "测试未修复的局部问题")]

    monkeypatch.setattr(gex, "_chat_json", chat)
    monkeypatch.setattr(gex, "_perbeat_validate_fill", validate)
    gex._perbeat_fill_slots(slots, scene_contract={}, punchline="", temperature=0.4)
    assert len(calls) == expected_calls


def test_declared_n_escalation_uses_shared_slots_and_existing_layer_scores():
    from app.services.daily_story.quality import _score_escalation
    from app.services.daily_story.story_types.n.quality import declared_escalation_hits
    from app.services.daily_story.story_types.n.line import LINE_N
    story = _rhetorical_story_fixture()
    lines = [r["line"] for r in story["dialogue"]]
    hits = declared_escalation_hits(lines, story)
    assert hits is not None and len(hits) == 4
    assert _score_escalation(lines, layer_patterns=LINE_N.layer_patterns, declared_hits=hits)[0] == 14
    lines[3] = "这本书现在在我的书包里面。"
    hits = declared_escalation_hits(lines, story)
    assert hits is not None and len(hits) == 3
    assert _score_escalation(lines, layer_patterns=LINE_N.layer_patterns, declared_hits=hits)[0] == 10
    story.pop("gold_n_expression_contract")
    assert declared_escalation_hits(lines, story) is None


def test_source_plan_and_expression_changes_invalidate_review_binding():
    from copy import deepcopy
    from app.services.daily_story.quality import story_review_content_hash
    story = _rhetorical_story_fixture()
    before = story_review_content_hash(story)
    changed = deepcopy(story)
    changed["gold_source_line_plan"][3]["intent"] = "换成另一份来源内容"
    assert story_review_content_hash(changed) != before
    changed = deepcopy(story)
    changed.pop("gold_n_expression_contract")
    assert story_review_content_hash(changed) != before


def test_source_reaction_missing_premise_is_spot_revision_not_missing_beat():
    exc = gcf.GoldChatSemanticBlocked(
        "终检素材/接话不合格：第[5]句：接话新编细节，缺前提。",
        issues=[{"kind": "接不上", "lines": [5], "desc": "新编细节缺前提", "source_audit_failed": True}],
    )
    assert not gc._is_missing_beat_exhausted(exc)
    assert gc._revise_line_indices(exc, 12) == [5]


def test_spot_revision_keeps_speaker_and_rejects_many_target_lines(monkeypatch):
    chat = _sample_chat()
    assert gc._revise_line_indices(ValueError("第1句、第2句、第3句、第4句"), 12) == []
    original_speaker = chat["dialogue"][1]["speaker"]
    monkeypatch.setattr(gc, "_chat_json", lambda *_a, **_k: {
        "lines": [{"i": 2, "speaker": "妈妈", "line": "这一次我把遥控器交给你。"}]})
    result = gc._try_revise_draft(chat, ValueError("第2句接不上"), temperature=0.4)
    assert result is not None
    assert result[0]["dialogue"][1]["speaker"] == original_speaker
    assert result[0]["dialogue"][0] == chat["dialogue"][0]


def test_timeout_preserves_previous_fill_failure_and_clears_deadline(monkeypatch):
    from app.services.gold_story.gold_chat.repair import GoldChatFillError
    from app.services.llm.llm_mgr import llm_deadline, LLMTimeBudgetExceeded

    row = _sample_row()
    row["id"] = 0
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)
    monkeypatch.setattr(gc, "_retry_structure_pair", lambda *_a, **_k: pytest.fail("措辞错误不得改判型"))
    clock = [1000.0]
    monkeypatch.setattr(gc.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("GOLD_CHAT_TIME_BUDGET_S", "180")
    calls = []

    def fail(_row, **_kw):
        calls.append(1)
        clock[0] += 65
        raise GoldChatFillError("第4句前提缺失", {"dialogue": [{"speaker": "昭昭", "line": "候选"}]})

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", fail)
    token = llm_deadline.set(0)
    try:
        with pytest.raises(LLMTimeBudgetExceeded, match="上一轮失败：第4句前提缺失") as info:
            gc.convert_gold_chat(row)
        assert len(calls) == 2
        assert "剩余50.0s" in str(info.value)
        assert "超出时间预算" not in str(info.value)
        assert info.value.candidate["dialogue"][0]["line"] == "候选"
        assert len(info.value.gold_chat_timing["attempts"]) == 2
        assert llm_deadline.get() == 0
    finally:
        llm_deadline.reset(token)


def test_empty_content_with_length_finish_reports_truncation(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(gex, "_client", lambda: SimpleNamespace(_chat=lambda *_a, **_kw: ("", "length")))
    with pytest.raises(ValueError, match="finish_reason=length"):
        gex._chat_json("json", "test")


def test_contract_failure_rebuilds_once_with_reason_and_preserves_source(monkeypatch):
    from copy import deepcopy
    from app.services.gold_story.gold_chat.repair import GoldChatContractError

    row = _sample_row()
    row.update(id=0, story_raw="固定原稿内容")
    original = deepcopy(row)
    rebuilt = []
    calls = []
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: rebuilt.append(deepcopy(r)) or r)
    monkeypatch.setattr(gc, "_retry_structure_pair", lambda *_a, **_k: pytest.fail("容量错误不得换类型"))

    def fail(candidate_row, **_kw):
        calls.append(candidate_row)
        candidate_row["payload"]["beat"].append("生成过程局部变更")
        raise GoldChatContractError("骨架只排出11句")

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", fail)
    with pytest.raises(GoldChatContractError, match="11句"):
        gc.convert_gold_chat(row)
    assert len(calls) == 2
    assert len(rebuilt) == 2
    assert rebuilt[-1]["_gold_chat_rebuild_contract"] == "骨架只排出11句"
    assert all(r["story_raw"] == original["story_raw"] for r in rebuilt)
    assert all(r["structure_type"] == original["structure_type"] for r in rebuilt)
    assert row == original


def _sample_chat() -> dict:
    lines = [
        {"speaker": "昭昭", "line": "你刚才又抢我遥控器，我还不敢说。"},
        {"speaker": "灿灿", "line": "谁让你手慢，我先用就是我的。"},
        {"speaker": "昭昭", "line": "那我关上门，我在里面练功夫，等会儿打回来。"},
        {"speaker": "灿灿", "line": "你练啊，开门我看你还敢不敢。"},
        {"speaker": "昭昭", "line": "我……我先看看你在不在门口。"},
        {"speaker": "灿灿", "line": "在啊，你出来试试。"},
        {"speaker": "昭昭", "line": "算了算了，我先不跟你计较。"},
        {"speaker": "灿灿", "line": "刚才不是说要打回来吗？"},
        {"speaker": "昭昭", "line": "我就是先歇一会儿，又不是怕你。"},
        {"speaker": "灿灿", "line": "那你把门打开，别躲里面。"},
        {"speaker": "昭昭", "line": "不开，我要再练两招。"},
        {"speaker": "灿灿", "line": "行，你练，我等着。"},
        {"speaker": "昭昭", "line": "好了好了，遥控器还你一半行吧。"},
        {"speaker": "灿灿", "line": "这还差不多，明天继续。"},
    ]
    while gc.dialogue_total_chars({"dialogue": lines}) < 240:
        lines.append(
            {
                "speaker": "昭昭",
                "line": "我就是先歇一会儿，又不是怕你。",
            }
        )
    return {
        "scene_title": "关门练功",
        "setting": "卧室门口",
        "key": "关门练功",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "dialogue": lines,
        "punchline_explain": "A类嘴硬加码：幻想英勇开门就怂",
    }


def test_validate_gold_chat_ok():
    story = _sample_chat()
    gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_ensure_gold_chat_min_chars_does_not_force_dirty_fill():
    """机械清理后宁可保留字数不足，也不靠固定态度尾巴硬凑 240。"""
    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的地盘，你快走开听见没有呀真的！"},
            {"speaker": "灿灿", "line": "我先趴在这儿的，该你马上走开听见没有！"},
            {"speaker": "昭昭", "line": "哼，看招，我先推你一下试试看啊真的！"},
            {"speaker": "灿灿", "line": "你敢打我，我就马上告诉妈妈去啊真的！"},
            {"speaker": "昭昭", "line": "就打你，你抢了我的位置啊真的不行！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算，咱们现在来比呀啊！"},
            {"speaker": "昭昭", "line": "我拿出最强形态，再出拳打你啊听见！"},
            {"speaker": "灿灿", "line": "草莓熊肘击，我砸你肚子一下听清楚！"},
            {"speaker": "昭昭", "line": "哎哟我输了，你也太厉害啦呀真的！"},
            {"speaker": "灿灿", "line": "玩具都归我，你到那边去躺着吧啊！"},
            {"speaker": "昭昭", "line": "等长大再算账，我现在怕你啊真的！"},
            {"speaker": "灿灿", "line": "我说了算，你乖乖躺好别动呀听见！"},
        ],
    }
    chars = gc.dialogue_total_chars(story)
    assert chars < gc.DAILY_STORY_BODY_CHARS_MIN
    assert gc.DAILY_STORY_BODY_CHARS_MIN - chars <= gc.GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    out, changed = gc._ensure_gold_chat_min_chars(story)
    assert changed
    assert gc.dialogue_total_chars(out) < gc.DAILY_STORY_BODY_CHARS_MIN
    blob = "".join(str(row.get("line") or "") for row in out["dialogue"])
    assert not any(
        phrase in blob
        for phrase in (
            "我偏就不信",
            "说一不二",
            "马上给我挪开",
            "少废话听我的",
        )
    )

    # 大缺口：剥灌尾后不靠粒子硬凑到 240
    short = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "看招！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算！"},
        ]
        * 6,
    }
    out_short, _ = gc._ensure_gold_chat_min_chars(short)
    assert gc.dialogue_total_chars(out_short) < gc.DAILY_STORY_BODY_CHARS_MIN


def test_ensure_gold_chat_min_chars_skips_padding_in_default_perbeat_mode(monkeypatch):
    """逐拍是默认路径：没显式设 GOLD_CHAT_PERBEAT 也不许垫字/插池子句。

    #149 实测：12 句 232 字的逐拍稿被垫成 15 句，插入「你别想让我认输」
    「没完就没完」池子对，还带出「别挠我了行！」截断语病，终检全判接不上。
    """
    monkeypatch.delenv("GOLD_CHAT_PERBEAT", raising=False)
    dialogue = [
        {"speaker": "昭昭", "line": "我看你咋打我啊，你追都追不上我。"},
        {"speaker": "灿灿", "line": "我穿裙子也追得上你，你别跑。"},
        {"speaker": "昭昭", "line": "你管得太宽了，这事没完。"},
        {"speaker": "灿灿", "line": "我按住你了，再动一下试试。"},
        {"speaker": "昭昭", "line": "妈妈救我，姐姐不让我起来。"},
        {"speaker": "妈妈", "line": "你们自己看着办，我这排还没贴正。"},
        {"speaker": "灿灿", "line": "我挠你痒痒，看你还嘴硬不。"},
        {"speaker": "昭昭", "line": "别挠了，你纯属多余，快住手。"},
        {"speaker": "灿灿", "line": "刚才那股横劲去哪了，怎么不喊。"},
        {"speaker": "妈妈", "line": "你俩继续，贴完这排还有一排。"},
        {"speaker": "灿灿", "line": "剩下这些贴纸要不要一起贴完。"},
        {"speaker": "昭昭", "line": "好啊，一起贴，别把贴纸贴歪了。"},
    ]
    story = {"story_type": "K", "dialogue": dialogue}
    before = gc.dialogue_total_chars(story)
    out, _changed = gc._ensure_gold_chat_min_chars(story)
    assert gc.dialogue_total_chars(out) == before
    blob = "".join(str(row.get("line") or "") for row in out["dialogue"])
    assert "你别想让我认输" not in blob
    assert "没完就没完" not in blob


def test_k_meet_min_chars_uses_effective_floor_not_240():
    """K 补字与终检同口径：12 句 234 字已达标，不得再灌池子对。

    #149 实测：12 句 233 字被 `_k_meet_min_chars` 按 240 硬线判「不够」，
    垫成 15 句，末段三句全是「不认输/没完」换词复述，终检判重复。
    """
    from app.services.gold_story.gold_chat.finalize import (
        _k_meet_min_chars,
        _k_under_hard_floor,
    )

    line = "一二三四五六七八九十一二三四五六七八九"  # 19 字
    rows = [
        {"speaker": "昭昭" if i % 2 == 0 else "灿灿", "line": line}
        for i in range(12)
    ]
    chat = {"story_type": "K", "dialogue": rows}
    assert gc.dialogue_total_chars(chat) == 228
    assert _k_under_hard_floor(chat) is False
    assert len(_k_meet_min_chars(chat, mechanism="M12")["dialogue"]) == 12

    short = dict(chat)
    short["dialogue"] = [
        {"speaker": "昭昭", "line": "一二三四五六七八九十一二三四五六七"}  # 17 字
    ] * 12
    assert gc.dialogue_total_chars(short) == 204
    assert _k_under_hard_floor(short) is True


def test_i_close_local_patch_uses_effective_char_floor(monkeypatch):
    """I 收口与终检同一口径：14 句达标时 228 字不得再按 240 硬卡打回。"""
    from app.services.gold_story.gold_chat.validate import (
        gold_chat_effective_min_chars,
    )

    monkeypatch.setattr(
        "app.services.daily_story.story_types.apply_gold_chat_type_patch",
        lambda story, structure_type: (story, []),
    )
    monkeypatch.setattr(
        "app.services.gold_story.gold_chat.patch.patch_m5_break_sibling_consecutive",
        lambda story: (story, False),
    )
    monkeypatch.setattr(
        "app.services.gold_story.gold_chat.patch.patch_gold_chat_post_close_tail",
        lambda story, **kwargs: (story, []),
    )
    dialogue = [
        {
            "speaker": "昭昭" if i % 2 == 0 else "妈妈",
            "line": "甲" * (16 if i < 4 else 15) + "。",
        }
        for i in range(14)
    ]
    story = {"story_type": "I", "dialogue": dialogue}
    chars = gc.dialogue_total_chars(story)
    assert chars == 228
    assert gold_chat_effective_min_chars(dialogue) < chars
    assert chars < gc.DAILY_STORY_BODY_CHARS_MIN

    out = gex._apply_i_close_local_patches(story, dialogue_seed=[])

    assert gc.dialogue_total_chars(out) == chars
    assert len(out["dialogue"]) == 14


def test_generic_n_near_miss_does_not_inject_attitude_tails():
    from app.services.gold_story.gold_chat.length import (
        _expand_short_gold_chat_lines,
        _pad_gold_chat_line,
    )

    story = {
        "story_type": "N",
        "dialogue": [
            {
                "speaker": "昭昭" if i % 2 == 0 else "灿灿",
                "line": "我就是这么想的，你先听我说。",
            }
            for i in range(12)
        ],
    }
    out, changed = _expand_short_gold_chat_lines(
        story,
        ignore_deficit_cap=True,
    )
    assert not changed
    blob = "".join(row["line"] for row in out["dialogue"])
    assert not any(
        phrase in blob
        for phrase in (
            "我偏就不信",
            "说一不二",
            "马上给我挪开",
            "我可记住啦",
        )
    )

    padded, added = _pad_gold_chat_line(
        "我回房间补作业。",
        1,
        story_type="N",
        speaker="灿灿",
    )
    assert added == 1
    assert padded in {
        "我回房间补作业啊。",
        "我回房间补作业呢。",
        "我回房间补作业吧。",
        "我回房间补作业呀。",
    }

    already_particle, added = _pad_gold_chat_line(
        "铅笔找不到了嘛。",
        3,
        story_type="N",
        speaker="灿灿",
    )
    assert added == 0
    assert already_particle == "铅笔找不到了嘛。"


def test_relay_parent_prefix_is_rewritten_to_direct_speech():
    from app.services.gold_story.scene import (
        collect_voice_errors,
        patch_dialogue_narration_to_speech,
    )

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "妈妈说，用过的东西放回原位，这是习惯。"},
        ],
    }
    notes = patch_dialogue_narration_to_speech(story)

    assert story["dialogue"][0]["line"] == "用过的东西放回原位，这是习惯。"
    assert notes == ["转述→现场对白[1]"]
    assert collect_voice_errors(story["dialogue"]) == []


    not_relay = {"dialogue": [{"speaker": "昭昭", "line": "反正爸爸说了算。"}]}
    assert patch_dialogue_narration_to_speech(not_relay) == []
    assert not_relay["dialogue"][0]["line"] == "反正爸爸说了算。"


def test_g_cleanup_224_near_miss_closes_with_semantic_mid_pair():
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    def fit(text: str, size: int) -> str:
        core = text.rstrip("。")
        return (core + "真" * size)[: size - 1] + "。"

    bases = [
        ("妈妈", "昭昭把玩具收好"),
        ("昭昭", "我还没玩完等会再收"),
        ("灿灿", "用完的东西要放回去"),
        ("昭昭", "你干嘛动我的积木"),
        ("灿灿", "我先把这边收起来"),
        ("昭昭", "我还想继续玩呢"),
        ("灿灿", "那我先去看书了"),
        ("昭昭", "等等剩下的我来收"),
        ("灿灿", "那边还有几块别漏"),
        ("昭昭", "知道啦我这就收"),
        ("灿灿", "我去沙发看书"),
        ("昭昭", "那我也读给我留位置"),
    ]
    dialogue = [
        {"speaker": speaker, "line": fit(line, 18 if i < 8 else 20)}
        for i, (speaker, line) in enumerate(bases)
    ]
    story = {"story_type": "G", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) == 224

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="G",
        mechanism="M4",
        dialogue_seed=[
            {"speaker": "妈妈", "intent": "昭昭，把玩具收好"},
            {"speaker": "灿灿", "intent": "把积木按颜色码进箱子"},
        ],
    )

    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    lines = [str(row.get("line") or "") for row in out["dialogue"]]
    assert "你还真要把这些都收好啊？" in lines
    assert "我先把手边这些放回去。" in lines


def test_g_111_pre_score_consecutive_cleanup_recovers_structure_without_filler():
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.daily_story.quality import score_daily_story
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )
    from app.services.gold_story.gold_chat.length import _boost_short_with_mid_lines

    story = {
        "story_type": "G",
        "conflict_core": "昭昭拒绝收玩具，灿灿示范后昭昭主动跟随",
        "punchline_explain": "G类嘴硬心软，行动示范后主动跟随暖收",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，把玩具收好，地上都下不去脚了。"},
            {"speaker": "昭昭", "line": "我还没玩完呢，等会儿再收。"},
            {"speaker": "灿灿", "line": "昭昭，你踢积木干嘛？都散到沙发底下了。"},
            {"speaker": "昭昭", "line": "我就踢！反正我还没玩完，不收。"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "灿灿", "line": "不是罚你，是下次想玩一找就找到。"},
            {"speaker": "昭昭", "line": "我就是还没玩完，你别管我。"},
            {"speaker": "灿灿", "line": "行，我不吵，我把积木按颜色码好。"},
            {"speaker": "灿灿", "line": "红色放这格，蓝色放那格，你看着。"},
            {"speaker": "昭昭", "line": "姐姐，你码积木干嘛？又不玩了。"},
            {"speaker": "灿灿", "line": "我拿绘本看，每天读书学习是第十条。"},
            {"speaker": "昭昭", "line": "第十条？妈妈说的第十条是啥？"},
            {"speaker": "灿灿", "line": "对，妈妈说的，每天读书学习不能忘。"},
            {"speaker": "昭昭", "line": "那我也读，等我先把玩具收进柜子。"},
            {"speaker": "昭昭", "line": "姐姐，我收好了，挤一挤一起看。"},
            {"speaker": "灿灿", "line": "好，你坐这边，我翻页你跟着念。"},
            {"speaker": "昭昭", "line": "我念得慢，你别笑我。"},
            {"speaker": "灿灿", "line": "不笑，我等你，第十条要一起做到。"},
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "昭昭，把玩具收好"},
        {"speaker": "昭昭", "intent": "我还没玩完呢"},
        {"speaker": "灿灿", "intent": "把积木按颜色码好"},
        {"speaker": "昭昭", "intent": "那我也读"},
    ]

    cleaned, notes = patch_gold_chat_consecutive_siblings(
        story,
        dialogue_seed=seed,
    )
    assert len([n for n in notes if n.startswith("G行动连说去冗余")]) == 3

    if dialogue_total_chars(cleaned) < gc.DAILY_STORY_BODY_CHARS_MIN:
        cleaned, changed = _boost_short_with_mid_lines(
            cleaned,
            structure_type="G",
            mechanism="M4",
            dialogue_seed=seed,
        )
        assert changed

    assert dialogue_total_chars(cleaned) >= gc.DAILY_STORY_BODY_CHARS_MIN
    kid_speakers = [
        str(row.get("speaker") or "")
        for row in cleaned["dialogue"]
        if str(row.get("speaker") or "") in {"昭昭", "灿灿"}
    ]
    assert all(a != b for a, b in zip(kid_speakers, kid_speakers[1:]))

    quality = score_daily_story(cleaned, skip_relevancy=True)
    reasons = " ".join(str(x) for x in quality.get("reasons") or [])
    assert int(quality.get("structure_score") or 0) >= 75
    assert "存在同人连说" not in reasons
    assert "冲突推进不足" not in reasons


def test_102_action_narration_is_locally_rewritten_without_structure_repair():
    from app.services.gold_story.scene import (
        collect_narration_dialogue_errors,
        collect_voice_errors,
        patch_dialogue_narration_to_speech,
        sanitize_dialogue_seed_speech,
    )

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "抬手一巴掌拍在桌上，昭昭立刻缩手老实！"},
            {"speaker": "灿灿", "line": "端碗只说一个字：喝，眼神一冷昭昭就怂！"},
            {"speaker": "昭昭", "line": "乖乖接过碗，仰头灌了下去，苦得直咧嘴！"},
            {"speaker": "昭昭", "line": "抹着眼泪，二十年后又是一条好汉！"},
            {"speaker": "灿灿", "line": "瞪他一眼，作业写不写"},
        ],
    }
    notes = patch_dialogue_narration_to_speech(story)

    assert len(notes) == 5
    assert [row["line"] for row in story["dialogue"]] == [
        "一巴掌就老实了吧！",
        "喝！",
        "苦死我了！",
        "二十年后又是一条好汉！",
        "作业写不写？",
    ]
    assert collect_narration_dialogue_errors(story["dialogue"]) == []
    assert collect_voice_errors(story["dialogue"]) == []

    seed = sanitize_dialogue_seed_speech(
        [
            {"speaker": "灿灿", "intent": "抬手一巴掌，昭昭立刻老实"},
            {"speaker": "灿灿", "intent": "端碗只说一个字：喝"},
            {"speaker": "昭昭", "intent": "乖乖接过碗，仰头灌了下去"},
            {"speaker": "昭昭", "intent": "抹着眼泪，二十年后又是一条好汉"},
            {"speaker": "灿灿", "intent": "瞪他一眼，作业写不写"},
        ]
    )
    assert [row["intent"] for row in seed] == [
        "一巴掌就老实了吧！",
        "喝！",
        "我喝了！",
        "二十年后又是一条好汉！",
        "作业写不写？",
    ]


def test_j_m8_237_near_miss_closes_in_place_like_102():
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，坐好，我辅导你写作业，别耍赖啊。"},
            {"speaker": "昭昭", "line": "姐你今天真好看，头发像动画片里的公主吧。"},
            {"speaker": "灿灿", "line": "少扯，写作业，先写三行再喝药，规矩今天就这么定。"},
            {"speaker": "昭昭", "line": "三行太多，我写一行就喝，行不行啊姐啊。"},
            {"speaker": "昭昭", "line": "我手疼笔都握不住，明天写也一样对啊。"},
            {"speaker": "灿灿", "line": "手疼就换左手，本子摊平，别装可怜吧。"},
            {"speaker": "昭昭", "line": "那我先喝药，喝完药手更抖写不了字啊。"},
            {"speaker": "妈妈", "line": "昭昭乖，把药喝了，病才能好。"},
            {"speaker": "昭昭", "line": "太苦了，我不喝，闻着就想吐吧。"},
            {"speaker": "灿灿", "line": "喝啊！"},
            {"speaker": "昭昭", "line": "我喝我喝，别瞪我吧。"},
            {"speaker": "爸爸", "line": "我们吓唬都是假的，你姐是真打。"},
            {"speaker": "昭昭", "line": "二十年后咱又是一条好汉，你等着啊。"},
            {"speaker": "灿灿", "line": "哼，我说了算，你还敢顶嘴吧？"},
            {"speaker": "昭昭", "line": "不敢了，我这就去写作业啊。"},
        ],
    }
    assert dialogue_total_chars(story) == 237

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="J",
        mechanism="M8",
    )

    assert changed
    assert dialogue_total_chars(out) >= 240
    assert len(out["dialogue"]) == len(story["dialogue"])
    assert out["dialogue"][9]["line"] == "喝啊，听我的！"


def test_n_local_semantic_mid_pair_recovers_clean_q96_shape():
    from app.services.daily_story.story_types.n.validate import append_n_body_errors
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
    )

    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是铅笔找不到了嘛。"},
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "妈妈", "line": "昭昭，你手都停半空了，为什么突然说这个？"},
            {"speaker": "昭昭", "line": "因为没人教，我自己想的，Q弹的打了不疼，还响呢！"},
            {"speaker": "灿灿", "line": "噗……昭昭你别说了，我肩膀都抖了。"},
            {"speaker": "妈妈", "line": "你还笑？作业没写你倒笑得出来？"},
            {"speaker": "昭昭", "line": "姐姐笑，是喜欢我屁股Q弹，还是不信？"},
            {"speaker": "灿灿", "line": "妈，我这就写，你别听昭昭胡说，快挪开。"},
            {"speaker": "昭昭", "line": "我没胡说，你看我扭一下，弹回来还带晃的。"},
            {"speaker": "妈妈", "line": "行吧行吧，你们俩一个比一个会捣乱。"},
            {"speaker": "灿灿", "line": "我回房间补作业，十分钟就写完吧。"},
            {"speaker": "昭昭", "line": "那妈，我屁股还打不打了？不打我收起来咯。"},
        ],
    }
    before = gc.dialogue_total_chars(story)
    assert before < gc.DAILY_STORY_BODY_CHARS_MIN

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="N",
        mechanism="M6",
    )
    body = "".join(str(row.get("line") or "") for row in out["dialogue"])
    errors: list[str] = []
    append_n_body_errors(out, errors)

    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(out["dialogue"]) > len(story["dialogue"])
    assert sum(1 for row in out["dialogue"] if row.get("speaker") == "妈妈") == 3
    # N 的明显长度缺口先走实义对，原有干净句不要再被单粒子污染。
    assert any("照这个道理认真想" in row["line"] for row in out["dialogue"])
    assert "噗……昭昭你别说了，我肩膀都抖了。" in [row["line"] for row in out["dialogue"]]
    assert "姐姐笑，是喜欢我屁股Q弹，还是不信？" in [row["line"] for row in out["dialogue"]]
    assert "妈，我这就写，你别听昭昭胡说，快挪开。" in [row["line"] for row in out["dialogue"]]
    assert not errors
    assert not any(
        phrase in body
        for phrase in ("我偏就不信", "说一不二", "马上给我挪开", "嘛真的吧", "咯呢")
    )


def test_n_222_near_miss_accepted_without_local_pad():
    """联合判据：12 句已达标，222 字落在放宽后的下限内，本地不再垫字。"""
    from app.services.gold_story.gold_chat.length import (
        _ensure_gold_chat_min_chars,
        gold_chat_effective_min_chars,
    )

    def full_line(text: str) -> str:
        return (text + "真" * 24)[:24]

    dialogue = [
        {"speaker": "妈妈", "line": "小时候这事又被提起来了"},
        {"speaker": "昭昭", "line": full_line("你为什么老说我那次只是运气好")},
        {"speaker": "灿灿", "line": full_line("因为我就是认真觉得那个理由说得通")},
        {"speaker": "昭昭", "line": full_line("我还可以继续把这个想法说清楚")},
        {"speaker": "灿灿", "line": full_line("那你就继续说我认真听着呢")},
        {"speaker": "昭昭", "line": full_line("我前面说的就是这个意思没变")},
        {"speaker": "灿灿", "line": full_line("我知道你是在认真解释这件事")},
        {"speaker": "昭昭", "line": full_line("所以我才一直按这个道理往下说")},
        {"speaker": "灿灿", "line": full_line("行那我再听听你还能怎么解释")},
        {"speaker": "妈妈", "line": "先听你们说完"},
        {"speaker": "妈妈", "line": "我还在听"},
        {"speaker": "妈妈", "line": "我在听你们把话说完"},
    ]
    story = {"story_type": "N", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) < gc.DAILY_STORY_BODY_CHARS_MIN

    out, changed = _ensure_gold_chat_min_chars(
        story,
        structure_type="N",
        mechanism="M6",
    )

    assert not changed
    assert gc.dialogue_total_chars(out) == gc.dialogue_total_chars(story)
    assert len(out["dialogue"]) == len(story["dialogue"])
    assert gc.dialogue_total_chars(out) >= gold_chat_effective_min_chars(
        out["dialogue"]
    )


def test_validate_expand_n_221_uses_contract_for_local_length_close(monkeypatch):
    """N 残稿未写出 why/reason 关键词时，也应从 beat 契约识别理由方，本地补长而非烧重生成。"""

    def full_line(text: str) -> str:
        return (text + "真" * 24)[:24]

    dialogue = [
        {"speaker": "妈妈", "line": "又说起你小时候那件旧事"},
        {"speaker": "昭昭", "line": full_line("哪是命大我明明会挑地方落")},
        {"speaker": "灿灿", "line": full_line("你每次都把这件事说得特别认真")},
        {"speaker": "昭昭", "line": full_line("我本来就是照自己的想法说的")},
        {"speaker": "灿灿", "line": full_line("那你继续把这个想法说清楚吧")},
        {"speaker": "昭昭", "line": full_line("我前面讲的意思一直都没有变")},
        {"speaker": "灿灿", "line": full_line("听起来你还真把它当成道理了")},
        {"speaker": "昭昭", "line": full_line("我当然是认真想过才这么说的")},
        {"speaker": "灿灿", "line": full_line("行我先听你把剩下的话讲完")},
        {"speaker": "妈妈", "line": "你们先说完"},
        {"speaker": "妈妈", "line": "我听着呢"},
    ]
    story = {
        "story_type": "N",
        "scene_title": "菜篓子旧事",
        "setting": "客厅，一家人聊起以前的事",
        "key": "菜篓子旧事",
        "conflict_core": "家里人重提昭昭小时候的旧事，昭昭嘴硬解释",
        "dialogue": dialogue,
        "punchline_explain": "N类童真歪理：昭昭一本正经为旧事找理由",
    }
    current = gc.dialogue_total_chars(story)
    assert current < 221
    story["dialogue"][-1]["line"] += "嗯" * (221 - current)
    assert gc.dialogue_total_chars(story) == 221

    row = {
        "payload": {
            "scene_contract": {
                "beat_chain": [
                    {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
                    {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
                    {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
                ]
            },
            "dialogue_seed": [
                {"speaker": "昭昭", "line": "哪是命大，我会挑地方落。"}
            ],
        }
    }

    def fail_if_llm_called(*args, **kwargs):
        raise AssertionError("221 字 N 稿不应进入 LLM 短稿 FIX")

    monkeypatch.setattr(gex, "_fix_chat_with_llm", fail_if_llm_called)
    out = gex._validate_expand_chat(
        story,
        banned_literals=[],
        source_type="field",
        mom_lines_max=3,
        structure_type="N",
        mechanism="M6",
        row=row,
    )

    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    lines = [str(row.get("line") or "") for row in out["dialogue"]]
    assert any("照这个道理认真想" in line for line in lines)
    assert any("刚才就是这么认真回答" in line for line in lines)


def test_n_post_align_221_stabilizer_uses_contract_context():
    """post-align 清理压到 221 时也必须带契约收口，不能再次失忆后进入重生成。"""
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    def fit(text: str, size: int) -> str:
        core = text.rstrip("。")
        return (core + "真" * size)[: size - 1] + "。"

    dialogue = [
        {"speaker": "妈妈", "line": fit("又说起你小时候那件旧事", 15)},
        {"speaker": "昭昭", "line": fit("那不叫命大我就是会挑地方落", 20)},
        {"speaker": "妈妈", "line": fit("菜篓子不是你摆的你怎么挑", 15)},
        {"speaker": "昭昭", "line": fit("我看准软地方才往那边落", 20)},
        {"speaker": "灿灿", "line": fit("你说得还真像自己安排好的一样", 20)},
        {"speaker": "昭昭", "line": fit("我当时就是一点都没有慌", 20)},
        {"speaker": "灿灿", "line": fit("你醒来还先惦记着吃饭", 20)},
        {"speaker": "昭昭", "line": fit("醒了先吃饭也很正常", 20)},
        {"speaker": "妈妈", "line": fit("你这套道理还挺完整", 15)},
        {"speaker": "灿灿", "line": fit("我都快听得接不上话了", 20)},
        {"speaker": "昭昭", "line": fit("反正我觉得自己判断没错", 20)},
        {"speaker": "妈妈", "line": fit("行吧这话我真接不住了", 16)},
    ]
    story = {"story_type": "N", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) == 221
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
        {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
        {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
    ]

    without_contract, _ = _stabilize_local_length_candidate(
        story, structure_type="N", mechanism="M6",
    )
    assert gc.dialogue_total_chars(without_contract) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed, changed = _stabilize_local_length_candidate(
        story,
        structure_type="N",
        mechanism="M6",
        beat_chain=beat_chain,
    )
    # 两人手契约（只有妈妈+昭昭）+ 妈妈额度已满：补位没有合法第三方可用，
    # 一律不补——绝不允许为了凑字数造出契约外的灿灿。
    mom_before = sum(1 for x in story["dialogue"] if x["speaker"] == "妈妈")
    assert mom_before >= 3
    assert not changed, "两人手额度满时不得再补位"
    can_before = sum(1 for r in story["dialogue"] if r["speaker"] == "灿灿")
    can_after = sum(1 for r in closed["dialogue"] if r["speaker"] == "灿灿")
    assert can_after == can_before, "补位不得新增契约外角色"

    # 三人在场（契约含灿灿）时，补位落在妈妈追问之后、收束之前，且不越家长额度
    three = dict(story)
    three["dialogue"] = [dict(r) for r in story["dialogue"]]
    three_chain = beat_chain + [{"speaker": "灿灿", "intent": "在旁边笑他"}]
    closed3, changed3 = _stabilize_local_length_candidate(
        three,
        structure_type="N",
        mechanism="M6",
        beat_chain=three_chain,
    )
    if changed3:
        mom_after = sum(1 for x in closed3["dialogue"] if x["speaker"] == "妈妈")
        assert mom_after == mom_before, "补字不得增加家长句数"


def test_n_natural_mid_pairs_skips_when_parent_qa_in_closing_tail():
    """契约要求落在家长追问之后，但 Q/A 已在末段时不得退回早先 reason_idx 插句。"""
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又说起你小时候那件旧事。"},
        {"speaker": "昭昭", "line": "那不叫命大，我会挑地方落。"},
        {"speaker": "灿灿", "line": "你每次都说得特别认真。"},
        {"speaker": "妈妈", "line": "菜篓子不是你摆的，你怎么挑？"},
        {"speaker": "昭昭", "line": "我看准软地方才往那边落。"},
        {"speaker": "妈妈", "line": "行吧，先吃饭。"},
    ]
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
        {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
        {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_n_natural_mid_pairs_skips_insert_when_reason_in_closing_tail():
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又提起以前那件事。"},
        {"speaker": "灿灿", "line": "你怎么回事？"},
        {"speaker": "昭昭", "line": "我才不要听你指挥。"},
        {"speaker": "妈妈", "line": "那你讲清楚。"},
        {"speaker": "昭昭", "line": "因为我早就看好了位置。"},
        {"speaker": "妈妈", "line": "行吧，先吃饭。"},
    ]
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事"},
        {"speaker": "昭昭", "intent": "嘴硬：先顶一句"},
        {"speaker": "昭昭", "intent": "回答：给出荒诞理由"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_n_contract_length_fallback_rejects_ambiguous_reasoner():
    """两个孩子都被契约标成解释方时禁止猜角色，宁可交上层修稿。"""
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又提起以前那件事。"},
        {"speaker": "昭昭", "line": "我有我的说法。"},
        {"speaker": "妈妈", "line": "你继续说。"},
        {"speaker": "灿灿", "line": "我也有另一套说法。"},
    ]
    beat_chain = [
        {"speaker": "昭昭", "intent": "解释：认真说明自己的理由"},
        {"speaker": "灿灿", "intent": "解释：也给出自己的理由"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_shared_local_length_close_accepts_clean_near_miss():
    """句数达标的边际稿（< 240 字但在一行之内的缺口）不再判死，也不灌垫字。"""
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
    )
    from app.services.gold_story.gold_chat.repair import (
        prepare_candidate_for_acceptance,
    )

    story = _sample_chat()
    story["dialogue"][0]["line"] = "你。"
    story["dialogue"][1]["line"] = "我。"
    assert gc.dialogue_total_chars(story) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed, changed = _stabilize_local_length_candidate(
        story,
        structure_type="A",
        mechanism="M6",
    )
    # 联合判据达标（18 句 / 218 字 ≥ 放宽下限），本地不再为凑 240 垫字。
    assert not changed
    assert gc.dialogue_total_chars(closed) == gc.dialogue_total_chars(story)
    prepared, errors = prepare_candidate_for_acceptance(
        closed,
        mom_lines_max=3,
        banned_literals=[],
    )

    total = gc.dialogue_total_chars(prepared)
    assert total < gc.DAILY_STORY_BODY_CHARS_MIN
    # 联合判据：句数达标时字数下限放宽一行，故此处不再报字数缺口。
    assert not [error for error in errors if "正文总字数须≥" in error]
    assert not [
        error
        for error in errors
        if "单句过长" in error or "垫字" in error
    ]
    body = "".join(str(row.get("line") or "") for row in prepared["dialogue"])
    assert "我偏就不信" not in body
    assert "说一不二" not in body


def test_acceptance_clamps_key_expanded_by_kinship_patch():
    """称谓/点题补丁把 key 撑到 9 字时，验收前本地截到 8 字，不判死。"""
    from app.services.gold_story.gold_chat.repair import (
        prepare_candidate_for_acceptance,
    )

    story = _sample_chat()
    story["key"] = "一二三四五六七八九"
    prepared, errors = prepare_candidate_for_acceptance(
        story,
        mom_lines_max=3,
        banned_literals=[],
    )
    assert len(prepared["key"]) <= 8
    assert not [error for error in errors if "key 须" in error]


def test_n_post_sanitize_close_recovers_contract_without_dirty_fill():
    from app.services.daily_story.story_types.n.validate import RE_SOLEMN_REASON
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.gold_story.gold_chat.repair import (
        prepare_candidate_for_acceptance_after_local_length_close,
    )

    story = _sample_chat()
    story["story_type"] = "N"
    story["dialogue"] = [
        {"speaker": "灿灿", "line": "如果只能选一个，你认真说选姐姐还是选我？"},
        {"speaker": "昭昭", "line": "我当然先选姐姐，这个答案不用想太久。"},
        {"speaker": "灿灿", "line": "为什么，你总得给我一个能听懂的理由吧？"},
        {"speaker": "昭昭", "line": "她笑起来像小太阳，我看见就觉得特别亮。"},
        {"speaker": "灿灿", "line": "你这个说法听着怎么越来越奇怪了？"},
        {"speaker": "昭昭", "line": "我是在认真回答你，没有故意逗你玩。"},
        {"speaker": "灿灿", "line": "那你继续说，我倒要看看还能怎么讲。"},
        {"speaker": "昭昭", "line": "我说完就是这个答案，不准备临时改口。"},
        {"speaker": "灿灿", "line": "行吧，我服了，你还真能一本正经讲下去。"},
        {"speaker": "昭昭", "line": "那就这么定，别再让我重新选一次。"},
        {"speaker": "灿灿", "line": "我听懂了。"},
        {"speaker": "昭昭", "line": "这回说清楚了。"},
    ]
    assert gc.dialogue_total_chars(story) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed = grf._stabilize_n_contract_candidate(
        gex._normalize_chat_speakers(story),
        structure_type="N",
        mechanism="M6",
    )
    prepared, errors = prepare_candidate_for_acceptance_after_local_length_close(
        closed,
        mom_lines_max=3,
        banned_literals=[],
        structure_type="N",
        mechanism="M6",
    )
    body = "".join(str(x.get("line") or "") for x in prepared.get("dialogue") or [])

    assert gc.dialogue_total_chars(prepared) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert RE_SOLEMN_REASON.search(body)
    assert not [
        error
        for error in errors
        if "正文总字数须≥" in error or "单句过长" in error or "垫字" in error
    ]
    assert "我偏就不信" not in body
    assert "说一不二" not in body


def test_validate_gold_chat_rejects_banned():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "小姨又欺负我"
    with pytest.raises(ValueError, match="禁词"):
        gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_validate_gold_chat_rejects_relay_and_paren():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "妈妈说了，抢不过就躲着点。"
    with pytest.raises(ValueError, match="转述"):
        gc.validate_gold_chat(story)
    story["dialogue"][0]["line"] = "（从厨房走出来）昭昭，你说啥？"
    with pytest.raises(ValueError, match="括号"):
        gc.validate_gold_chat(story)


def test_normalize_chat_speakers_keeps_father():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "爸爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_normalize_chat_speakers_father_alias_to_dad():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "老爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_gate_gold_chat_structure_score_raises_when_low():
    with pytest.raises(ValueError, match=r"structure_score:63"):
        gc._gate_gold_chat_structure_score(
            {"quality": {"structure_score": 63, "score": 63}}
        )


def test_gate_gold_chat_structure_score_ok():
    assert gc._gate_gold_chat_structure_score(
        {"quality": {"structure_score": 80, "score": 80}}
    ) == 80


def test_lift_structure_second_prompt_includes_previous_validation_error():
    """定点修稿第二轮须带上轮校验/门控错误，勿只重复结构分反馈。"""
    prompts: list[str] = []
    chat = _sample_chat()
    chat["quality"] = {
        "structure_score": 60,
        "score": 60,
        "reasons": ["无破功软收"],
    }
    row = _sample_row()

    def fake_fix(_chat: dict, fb: str, **_kwargs: object) -> dict:
        prompts.append(fb)
        out = dict(_chat)
        if len(prompts) == 1:
            raise ValueError("正文总字数须≥240")
        out["quality"] = {"structure_score": 80, "score": 80, "reasons": []}
        return out

    out, struct = gcf._lift_gold_chat_structure_with_llm(
        chat,
        row,
        st_final="N",
        mech="M6",
        banned=[],
        mom_max=1,
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_attempts=2,
    )
    assert struct == 80
    assert len(prompts) == 2
    assert "正文总字数须≥240" in prompts[1]
    assert "上一轮未过" in prompts[1]
    assert out["quality"]["structure_score"] == 80


def test_attach_gold_chat_structure_score_writes_quality():
    row = _sample_row()
    chat = _sample_chat()
    out = gc._attach_gold_chat_structure_score(chat, row)
    assert isinstance(out.get("quality"), dict)
    assert out["story_type"] == "A"
    assert "structure_score" in out["quality"]


def _bypass_structure_gate(monkeypatch):
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    # 测试夹具对白过不了 A–L 契约机审；跳过精修对齐
    monkeypatch.setattr(gc, "refine_gold_chat_align", lambda story, **_kw: story)
    monkeypatch.setattr(grf, "refine_gold_chat_align", lambda story, **_kw: story)


def test_gold_story_to_gold_chat_retries_when_one_line_short(monkeypatch):
    """差 1 句：不本地硬插注水句；须 FIX 扩写或扩写重抽。"""
    import copy

    calls: dict[str, int | bool] = {"n": 0}
    _bypass_structure_gate(monkeypatch)

    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "编辑" in system or "定点" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        chat = _sample_chat()
        if int(calls["n"]) == 1:
            chat["dialogue"] = chat["dialogue"][:11]
        return chat

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)

    def spot_fix(chat, _fb, **_kw):
        calls["fix"] = True
        out = copy.deepcopy(chat)
        for _ in range(64):
            if gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN:
                break
            progressed = False
            rows = out.get("dialogue") or []
            for row in rows[1:-1]:
                if len(str(row.get("line") or "")) >= 22:
                    continue
                row["line"] = str(row.get("line") or "") + "补"
                progressed = True
                if gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN:
                    break
            if not progressed:
                break
        return out

    monkeypatch.setattr(gex, "_short_spot_fix_chat_with_llm", spot_fix)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 12
    blob = "".join(str(d.get("line") or "") for d in out["dialogue"])
    assert "你给我听好了" not in blob


def test_gold_story_to_gold_chat_rejects_when_far_too_short(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:2]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    with pytest.raises(ValueError, match="篇幅驳回"):
        gc.gold_story_to_gold_chat(_sample_row())


def test_bump_short_regen_helpers():
    err11 = "对白句数须≥12，当前11; 正文总字数须≥240，当前155"
    assert gc._is_regenerable_line_short_error(err11)
    assert gc._bump_short_regen_or_reject(err11, 0) == 1
    assert gc._bump_short_regen_or_reject(err11, 2) == 3
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err11, 3)
    err10 = "对白句数须≥12，当前10"
    assert gc._is_regenerable_line_short_error(err10)
    assert gc._bump_short_regen_or_reject(err10, 0) == 1
    err9 = "对白句数须≥12，当前9"
    assert gc._is_regenerable_line_short_error(err9)
    err8 = "对白句数须≥12，当前8"
    assert not gc._is_regenerable_line_short_error(err8)
    with pytest.raises(ValueError, match="本地垫字仍不足"):
        gc._bump_short_regen_or_reject(err8, 0)
    # 字数 near-miss / 大缺口均可重生成（勿立刻「本地垫字仍不足」）
    err_chars = "正文总字数须≥240，当前235"
    assert gc._char_deficit_from_error(err_chars) == 5
    assert gc._is_regenerable_short_error(err_chars)
    assert gc._bump_short_regen_or_reject(err_chars, 0) == 1
    err_short = "正文总字数须≥240，当前117"
    assert gc._is_regenerable_short_error(err_short)
    assert gc._bump_short_regen_or_reject(err_short, 0) == 1
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err_chars, 3)


def test_attach_gold_chat_structure_score_skips_opening_penalty_for_body():
    """计分前清空 discovery_opening，避免前 2 句被当开场扣分。"""
    row = _sample_row()
    row["structure_type"] = "J"
    row["title"] = "世子之争"
    chat = {
        "scene_title": "世子之争",
        "setting": "地板垫上，灿灿和昭昭在抢垫子",
        "conflict_core": "昭昭先动手，灿灿一锤镇住",
        "punchline_explain": "J类权威压住：一锤肘击后镇住",
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这垫子是我的地盘你走开！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算玩具归我！"},
            {"speaker": "昭昭", "line": "拿出最强形态来打我！"},
            {"speaker": "灿灿", "line": "草莓熊肘击砸你肚子！"},
            {"speaker": "昭昭", "line": "啊我输了你太厉害啦！"},
            {"speaker": "灿灿", "line": "以后玩具都归我安排！"},
            {"speaker": "昭昭", "line": "哼等我长大再跟你算！"},
            {"speaker": "灿灿", "line": "这局我已经镇住你了！"},
            {"speaker": "昭昭", "line": "再求你一次松口行不行！"},
            {"speaker": "灿灿", "line": "不行规矩就是这样定的！"},
            {"speaker": "昭昭", "line": "那我保证这次听你的话！"},
            {"speaker": "灿灿", "line": "保证也没用现在听我的！"},
        ],
    }
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "开场未满" not in reasons
    assert "J开场缺求放行" not in reasons
    assert "缺发现开场" not in reasons
    score = int((out.get("quality") or {}).get("structure_score") or 0)
    assert score >= 75, (score, reasons)


def test_gold_chat_structure_score_skips_bili_title_relevancy():
    """gold_chat 结构分不按 B 站标题字面跑题（保真走 beat/契约）。"""
    row = _sample_row()
    row["title"] = "世子之争"
    chat = _sample_chat()
    chat["scene_title"] = "垫子争夺战"
    chat["story_type"] = "J"
    chat["dialogue"] = [
        {"speaker": "昭昭", "line": "这沙发我先占好了，你挪开！"},
        {"speaker": "灿灿", "line": "不行，我先来的，该你走！"},
    ] * 6
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "跑题" not in reasons


def test_validate_expand_expands_short_with_fix_before_regen(monkeypatch):
    """偏短时先 FIX 句内扩写，勿立刻整稿重生成。"""
    calls = {"fix": 0}

    short = _sample_chat()
    short["story_type"] = "J"
    short["dialogue"] = [
        {"speaker": "昭昭", "line": "看招！"},
        {"speaker": "灿灿", "line": "你敢！"},
    ] * 6
    assert gc.dialogue_total_chars(short) < gc.DAILY_STORY_BODY_CHARS_MIN

    def fake_fix(story, errors, **_kw):
        calls["fix"] += 1
        assert "正文总字数须≥" in errors
        return _sample_chat()

    monkeypatch.setattr(gc, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    import app.services.gold_story.gold_chat.length as glength
    monkeypatch.setattr(glength, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    monkeypatch.setattr(gex, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    out = gc._validate_expand_chat(
        short,
        banned_literals=[],
        source_type="field",
        mom_lines_max=0,
        structure_type="J",
    )
    assert calls["fix"] == 1
    assert len(out["dialogue"]) >= 12


def test_apply_deterministic_shorten_trims_one_char():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你刚才又抢我遥控器，我还不敢说呀！"
    assert len(story["dialogue"][0]["line"]) == 17  # sanity
    long_line = "你" * 24 + "呀"
    assert len(long_line) == 25
    story["dialogue"][0]["line"] = long_line
    out, changed = gc._apply_deterministic_shorten(story)
    assert changed
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


def test_shorten_overlong_llm_freezes_non_target_lines_and_speakers(monkeypatch):
    story = _sample_chat()
    story["dialogue"][0]["line"] = "这是一句完全没有语气词可以机械裁掉的超长对白内容测试甲乙丙丁"
    original_second = dict(story["dialogue"][1])
    assert len(story["dialogue"][0]["line"]) > gc.CHAT_MAX_LINE_CHARS

    def fake_chat(*_a, **_k):
        out = {**story, "dialogue": [dict(x) for x in story["dialogue"]]}
        out["dialogue"][0]["line"] = "这句只保留必要语义"
        out["dialogue"][0]["speaker"] = story["dialogue"][0]["speaker"]
        out["dialogue"][1]["line"] = "模型顺手改坏了非目标行"
        out["dialogue"][1]["speaker"] = "妈妈"
        return out

    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    out = gex._shorten_overlong_lines_with_llm(story)
    assert out["dialogue"][0]["line"] == "这句只保留必要语义"
    assert out["dialogue"][0]["speaker"] == story["dialogue"][0]["speaker"]
    assert out["dialogue"][1] == original_second


def test_validate_expand_shortens_before_full_fix(monkeypatch):
    calls: list[str] = []

    def fake_validate(story, **kwargs):
        for item in story.get("dialogue") or []:
            if len(str(item.get("line") or "")) > gc.CHAT_MAX_LINE_CHARS:
                raise ValueError(
                    f"单句过长(max=31>{gc.CHAT_MAX_LINE_CHARS})"
                )
        return None

    def fake_shorten(story, **_kw):
        calls.append("shorten")
        out = dict(story)
        rows = [dict(x) for x in out["dialogue"]]
        rows[0]["line"] = str(rows[0]["line"])[: gc.CHAT_MAX_LINE_CHARS]
        out["dialogue"] = rows
        return out

    monkeypatch.setattr(gc, "validate_gold_chat", fake_validate)
    monkeypatch.setattr(gc, "_shorten_overlong_lines_with_llm", fake_shorten)
    monkeypatch.setattr(gex, "_shorten_overlong_lines_with_llm", fake_shorten)

    def _boom(*_a, **_k):
        raise AssertionError("should not full fix")

    monkeypatch.setattr(gc, "_fix_chat_with_llm", _boom)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", _boom)
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你" * 31
    out = gc._validate_expand_chat(
        story,
        banned_literals=[],
        source_type="field",
        mom_lines_max=1,
    )
    assert calls == ["shorten"]
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


@pytest.mark.parametrize("failure", ["503", "500", "unexpected"])
def test_upstream_503_logs_warning_without_chained_traceback(monkeypatch, caplog, failure):
    import logging
    from requests import Response
    from requests.exceptions import HTTPError
    from app.services.gold_story.gold_chat.repair import GoldChatSourceMappingError

    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "1")
    monkeypatch.setattr(gex.logger, "handlers", [caplog.handler])
    if failure == "unexpected":
        error = RuntimeError("unexpected internal failure")
    else:
        response = Response()
        response.status_code = int(failure)
        response.url = "https://opencode.ai/zen/go/v1/chat/completions"
        error = HTTPError(f"{failure} Server Error for url: {response.url}", response=response)

    def generate(**_kwargs):
        try:
            raise GoldChatSourceMappingError("进入显式素材映射")
        except GoldChatSourceMappingError:
            raise error

    monkeypatch.setattr(gex, "_generate_perbeat_candidate", generate)
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="network:"):
        gex.gold_story_to_gold_chat(_sample_row())
    records = [r for r in caplog.records if "expand candidate network fail" in r.getMessage()]
    assert records
    assert all((not r.exc_info) == (failure == "503") for r in records)
    if failure == "503":
        assert "503" in caplog.text and response.url in caplog.text
        assert "Traceback" not in caplog.text
        assert "GoldChatSourceMappingError" not in caplog.text


def test_gold_story_to_gold_chat(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        return _sample_chat()

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert out["scene_title"] == "关门练功"
    assert len(out["dialogue"]) >= 4
    assert out["quality"]["structure_score"] == 80


def test_convert_failure_preserves_existing_export(tmp_path, monkeypatch):
    from app.services.gold_story.gold_chat.finalize import GoldChatAcceptanceBlocked

    sid = "BV1KEEPEXPORT"
    export_dir = tmp_path / "gold_chat"
    export_dir.mkdir(parents=True)
    json_path = export_dir / f"{sid}.json"
    original = '{"keep": true}'
    json_path.write_text(original, encoding="utf-8")

    row = _sample_row()
    row["source_id"] = sid
    row["id"] = 96

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(
        gc,
        "gold_story_to_gold_chat",
        lambda _r, **kw: _sample_chat(),
    )
    monkeypatch.setattr(
        gc,
        "apply_gold_chat_normalizations",
        lambda chat, **_kw: (chat, []),
    )
    monkeypatch.setattr(
        gc,
        "_refine_after_normalize",
        lambda chat, _row, **_kw: chat,
    )
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)

    def _fail_finalize(*_args, **_kwargs):
        raise GoldChatAcceptanceBlocked("终检语义硬伤：第[2]句·错位：测试")

    monkeypatch.setattr(gcf, "run_gold_chat_finalize", _fail_finalize)

    with pytest.raises(GoldChatAcceptanceBlocked) as exc_info:
        gc.convert_gold_chat(row)

    assert json_path.read_text(encoding="utf-8") == original
    timing = getattr(exc_info.value, "gold_chat_timing", None)
    assert isinstance(timing, dict)
    assert timing["status"] == "failed"
    assert timing["stage"] == "finalize"
    assert set(timing["stages_ms"]) == {"contract", "draft", "normalize_refine", "finalize"}
    assert "export_backfill" not in timing["stages_ms"]


def test_convert_retries_on_finalize_missing_beat(monkeypatch):
    """终检缺拍也要能带反馈重掷：终检原先在重掷循环之外，机器一次都看不到。"""
    from app.services.gold_story.gold_chat.repair import GoldChatRepairExhausted

    row = _sample_row()
    row["source_id"] = "BV1FINALRETRY"
    row["id"] = 0
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)
    monkeypatch.setattr(
        gc, "apply_gold_chat_normalizations", lambda chat, **_kw: (chat, [])
    )
    monkeypatch.setattr(gc, "_refine_after_normalize", lambda chat, _row, **_kw: chat)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda chat, **_kw: (chat, []))
    monkeypatch.setattr(gc, "_retry_structure_pair", lambda r, attempt=0: (r, "M3+F"))

    feedback_seen: list[list[dict]] = []

    def _attach(r, feedback):
        feedback_seen.append(list(feedback))
        return r

    monkeypatch.setattr(gc, "_attach_retry_missing_events", _attach)

    drafts: list[int] = []

    def _draft(_row, **_kw):
        drafts.append(1)
        return _sample_chat()

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", _draft)

    finalize_calls: list[int] = []

    def _finalize(chat, _row, **_kw):
        finalize_calls.append(1)
        if len(finalize_calls) == 1:
            raise GoldChatRepairExhausted(
                stage="final_acceptance",
                reason="终检语义硬伤：第[5]句·缺前提",
                candidate={
                    "dialogue": [{"speaker": "爸爸", "line": "测试"}],
                    "quality": {
                        "review_issues": [
                            {
                                "kind": "缺前提",
                                "line": 5,
                                "missing_beat": {
                                    "intent": "爸爸旁观解说",
                                    "speaker": "爸爸",
                                },
                            }
                        ]
                    },
                },
            )
        return chat, 80

    monkeypatch.setattr(gcf, "run_gold_chat_finalize", _finalize)
    monkeypatch.setattr(gc, "export_gold_chat_files", lambda **_kw: {"json": "x"})
    monkeypatch.setattr(gc, "_backfill_gold_story_after_export", lambda *_a, **_kw: None)

    result = gc.convert_gold_chat(row)

    assert result["ok"] is True
    assert len(drafts) == 2
    assert len(finalize_calls) == 2
    assert feedback_seen
    assert feedback_seen[0][0]["original_intent"] == "爸爸旁观解说"


def test_forced_source_rebuild_does_not_fallback_to_unverified_seed(monkeypatch):
    row = _sample_row()
    row["_gold_chat_rebuild_contract"] = "旧素材遗漏原文收束"
    row["payload"]["story_raw"] = "姐弟在客厅争论关灯，妈妈听完要求先关灯，明天再讨论。" * 4
    monkeypatch.setattr("app.services.gold_story.collect.llm.build_scene_contract",
                        lambda **_kw: {"story_type": "F", "location": "客厅", "beat_chain": []})

    def fail_seed(**_kw):
        raise ValueError("H3b 无法保留完整收束")

    monkeypatch.setattr("app.services.gold_story.collect.llm.build_dialogue_seed", fail_seed)
    monkeypatch.setattr(gc.repo_gold_story, "patch_story_payload",
                        lambda *_a, **_kw: pytest.fail("失败素材不能写入来源契约"))
    with pytest.raises(ValueError, match="H3b 无法保留完整收束"):
        gc._rebuild_h3a_h3b_on_convert(row)


def test_rebuild_h3a_h3b_on_convert_refreshes_contract(monkeypatch):
    """重转切入点：用 story_raw+H3 重跑 H3a/H3b 写回契约。"""
    patched: dict = {}
    cores: list[str] = []

    def fake_build_scene(**_kwargs):
        return {
            "story_type": "I",
            "location": "客厅",
            "characters": ["灿灿", "昭昭", "妈妈"],
            "object": "小学单科成绩单",
            "conflict": "昭昭宣扬灿灿考了低分，妈妈责备戳痛处",
            "mechanism": "宣传高分该谢、低分怪分数",
            "beat_chain": [
                {"beat": 1, "speaker": "灿灿", "intent": "责备宣传"},
                {"beat": 2, "speaker": "昭昭", "intent": "双标辩解"},
                {"beat": 3, "speaker": "妈妈", "intent": "冰箱反问"},
                {"beat": 4, "speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "mom_lines_max": 2,
            "remap_note": "戏核家长须保留出场",
            "banned_literals": [],
            "contract_confidence": 0.9,
        }

    def fake_build_seed(**_kwargs):
        return {
            "setting": "客厅，灿灿攥着成绩单",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "责备宣传低分"},
                {"speaker": "昭昭", "intent": "双标辩解"},
                {"speaker": "妈妈", "intent": "冰箱反问"},
                {"speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "speaker_map_note": "妈妈保留",
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_scene_contract",
        fake_build_scene,
    )
    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_dialogue_seed",
        fake_build_seed,
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "patch_story_payload",
        lambda gid, patch: patched.update({"gid": gid, **patch}),
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "update_conflict_core",
        lambda gid, core: cores.append(core),
    )

    row = {
        "id": 44,
        "title": "分数宣传",
        "mechanism": "M11",
        "structure_type": "I",
        "conflict_core": "站外旧核：高考高分口吻残留",
        "theme_family": "分数",
        "payload": {
            "story_raw": "姐姐考了差分化妹妹宣传，妈妈责备并用冰箱反问。" * 3,
            "beat": [
                "妹妹宣扬，妈妈责备",
                "妹妹辩称双标",
                "妈妈反问冰箱",
                "妈妈点出开好头",
            ],
            "scene_contract": {
                "characters": ["灿灿", "昭昭"],
                "mom_lines_max": 0,
                "object": "站外旧分数口吻",
            },
            "source_type": "field",
            "structure_confidence": 0.8,
        },
    }
    out = gc._rebuild_h3a_h3b_on_convert(row)
    sc = out["payload"]["scene_contract"]
    assert "妈妈" in sc["characters"]
    assert int(sc["mom_lines_max"]) >= 2
    assert "高考" not in str(out.get("conflict_core") or "")
    assert "低分" in str(out.get("conflict_core") or "")
    assert cores and "低分" in cores[0]
    assert any(
        isinstance(r, dict) and r.get("speaker") == "妈妈"
        for r in out["payload"]["dialogue_seed"]
    )
    assert patched.get("gid") == 44


def test_sanitize_pad_suffix_strips_compound_tails():
    story = {
        "dialogue": [
            {
                "speaker": "昭昭",
                "line": "那跟我有啥关系不行了吧真的了呢。",
            },
            {
                "speaker": "灿灿",
                "line": "你别再宣传了真的了呢",
            },
            {
                "speaker": "妈妈",
                "line": "评论冰箱还得会制冷吗？",
            },
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "真的了呢" not in lines[0]
    assert "不行了吧" not in lines[0]
    assert "真的了呢" not in lines[1]
    assert "冰箱" in lines[2]


def test_sanitize_pad_suffix_strips_glued_buxing():
    """粘连垫字「知道不行/关系不行」应剥；真拒绝「还不行」保留。"""
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "姐数学58分，全班都知道不行！"},
            {
                "speaker": "昭昭",
                "line": "跟我没关系不行，我才不怕呢。",
            },
            {"speaker": "灿灿", "line": "这样还不行！"},
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "知道不行" not in lines[0]
    assert "都知道" in lines[0]
    assert "关系不行" not in lines[1]
    assert "没关系" in lines[1]
    assert lines[2] == "这样还不行！"


def test_parse_conflict_propaganda_roles():
    from app.services.gold_story.gold_chat.validate import (
        _parse_conflict_propaganda_roles,
    )

    roles = _parse_conflict_propaganda_roles(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert roles == ("昭昭", "灿灿")


def test_patch_score_propaganda_speakers_realigns():
    story = {
        "conflict_core": "昭昭到处说灿灿考了58分",
        "dialogue": [
            {"speaker": "昭昭", "line": "她考高分我宣传，她得谢我。"},
            {"speaker": "昭昭", "line": "你到处说，我同学都笑我。"},
            {"speaker": "灿灿", "line": "我宣传高分你谢我，宣传低分你怪我。"},
            {"speaker": "灿灿", "line": "低分被怪是分数问题，怪我咯。"},
        ],
    }
    out, changed = gc.patch_score_propaganda_speakers(
        story, conflict_text=story["conflict_core"]
    )
    assert changed
    assert out["dialogue"][1]["speaker"] == "灿灿"
    assert out["dialogue"][2]["speaker"] == "昭昭"
    assert out["dialogue"][3]["speaker"] == "昭昭"


def test_patch_collapse_empty_sibling_repeats():
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
        ]
    }
    out, changed = gc.patch_collapse_empty_sibling_repeats(story)
    assert changed
    assert out["dialogue"][0]["line"] == "别说了！"
    assert out["dialogue"][1]["line"] != "别说了！"


def test_format_cast_block_two_hander_vs_dual_kid():
    """出场角色块：单孩契约写两人手、禁补旁观；双孩契约写同侧。"""
    from app.services.gold_story.gold_chat.prompts import format_cast_block

    two = format_cast_block(
        {
            "characters": ["妈妈", "昭昭"],
            "mom_lines_max": 3,
            "beat_chain": [
                {"beat": 1, "speaker": "妈妈", "intent": "立规"},
                {"beat": 2, "speaker": "昭昭", "intent": "胡说"},
                {"beat": 3, "speaker": "妈妈", "intent": "追问"},
            ],
        }
    )
    assert "两人手" in two
    assert "禁止" in two and "第二个孩子" in two
    assert "≤ 3 句" in two

    dual = format_cast_block(
        {
            "characters": ["妈妈", "昭昭", "灿灿"],
            "mom_lines_max": 2,
            "beat_chain": [
                {"beat": 1, "speaker": "妈妈", "intent": "立规"},
                {"beat": 2, "speaker": "昭昭", "intent": "抢"},
                {"beat": 3, "speaker": "灿灿", "intent": "抢"},
            ],
        }
    )
    assert "双孩同侧" in dual

    # 幽灵角色（角色表有、beat 里一句没有）不得出现在允许名单里
    stale = format_cast_block(
        {
            "characters": ["妈妈", "昭昭", "灿灿"],
            "mom_lines_max": 3,
            "beat_chain": [
                {"beat": 1, "speaker": "妈妈", "intent": "立规"},
                {"beat": 2, "speaker": "昭昭", "intent": "胡说"},
            ],
        }
    )
    assert "只能是：妈妈、昭昭" in stale
    assert "两人手" in stale


def test_format_cast_block_non_n_witness_is_not_full_alternation():
    from app.services.gold_story.gold_chat.prompts import format_cast_block

    block = format_cast_block(
        {
            "story_type": "I",
            "characters": ["妈妈", "昭昭", "灿灿"],
            "mom_lines_max": 3,
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
    )
    assert "见证位" in block
    assert "最多 1 句" in block
    assert "严禁孩子连说" not in block


def test_format_role_binding_block_propaganda():
    from app.services.gold_story.gold_chat.prompts import format_role_binding_block

    block = format_role_binding_block(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert "宣传方 = 昭昭" in block
    assert "受害方 = 灿灿" in block


def test_export_gold_chat_files(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    row = _sample_row()
    chat = _sample_chat()
    paths = gc.export_gold_chat_files(
        source_id=row["source_id"],
        row=row,
        chat=chat,
    )
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["daily_story"]["scene_title"] == "关门练功"


def test_gold_chat_summary_from_payload():
    summary = gc.gold_chat_summary(
        "BV1TEST0001",
        row={
            "source_id": "BV1TEST0001",
            "payload": {
                "gold_chat_exported_at": "2026-08-24T00:00:00+00:00",
                "gold_chat_scene_title": "嘴硬心软",
                "gold_chat_lines": 18,
                "gold_chat_chars": 260,
                "gold_chat_structure_score": 82,
                "gold_chat_humor_score": 14,
                "bili_title": "东北弟弟打架被姐姐骂",
            },
        },
    )
    assert summary["has_gold_chat"] is True
    assert summary["scene_title"] == "嘴硬心软"
    assert summary["chat_lines"] == 18
    assert summary["bili_title"] == "东北弟弟打架被姐姐骂"
    assert summary["structure_score"] == 82
    assert summary["humor_score"] == 14


@pytest.mark.parametrize("concession_speaker,concession,victory,expected", [
    ("妈妈", "认输：妈妈承认说不过你", "嘴硬总结：看你还说", "I"),
    ("妈妈", "继续解释为什么大人可以", "嘴硬总结：看你还说", "E"),
    ("灿灿", "认输：我说不过你", "嘴硬总结：看你还说", "E"),
    ("妈妈", "认输：妈妈承认说不过你", "继续追问手机在哪", "E"),
])
def test_parent_fact_role_does_not_override_explicit_i_victory(
    concession_speaker, concession, victory, expected,
):
    from app.services.gold_story.gold_chat.type_bridge import resolve_gold_chat_structure_row
    row = {"mechanism": "M11", "structure_type": "I", "payload": {"scene_contract": {
        "story_type": "I", "facts": [{"secret_holder": "妈妈", "discoverer": "昭昭"}],
        "beat_chain": [
            {"speaker": "昭昭", "intent": "反问为什么大人可以小孩不可以"},
            {"speaker": concession_speaker, "intent": concession},
            {"speaker": "昭昭", "intent": victory},
        ],
    }}}
    out, _ = resolve_gold_chat_structure_row(row)
    assert out["structure_type"] == expected
    assert row["payload"]["scene_contract"]["story_type"] == "I"


def test_parent_caught_by_kid_retargets_a_and_i_to_e():
    """家长被孩子抓到把柄：A（要一锤可拍）/I（要语塞制敌）都不成立 → E 妈妈破功。"""
    from app.services.gold_story.gold_chat.type_bridge import (
        resolve_gold_chat_structure_row,
    )

    def row(st: str, mech: str, holder: str = "妈妈") -> dict:
        return {
            "id": 1,
            "mechanism": mech,
            "structure_type": st,
            "conflict_core": "妈妈催关灯，孩子翻出妈妈偷吃烤串的旧账",
            "payload": {
                "scene_contract": {
                    "story_type": st,
                    "facts": [
                        {
                            "fact_id": "F1",
                            "secret_holder": holder,
                            "accuser": "灿灿",
                            "discoverer": "灿灿",
                            "attribution_status": "resolved",
                        }
                    ],
                }
            },
        }

    for st, mech in (("A", "M5"), ("I", "M11")):
        out, notes = resolve_gold_chat_structure_row(row(st, mech))
        assert out["structure_type"] == "E", (st, notes)
        assert out["payload"]["scene_contract"]["story_type"] == "E"
        assert any("parent-caught-by-kid" in n for n in notes)

    # 孩子自己做过那件事（把柄在孩子手上）不纠偏
    out2, _ = resolve_gold_chat_structure_row(row("A", "M5", holder="灿灿"))
    assert out2["structure_type"] == "A"

    # 非家长把柄的 I 稿保持 I
    out3, _ = resolve_gold_chat_structure_row(
        {
            "id": 2,
            "mechanism": "M11",
            "structure_type": "I",
            "payload": {"scene_contract": {"story_type": "I"}},
        }
    )
    assert out3["structure_type"] == "I"
    """指定了行为人的 facts 未 resolved 时不得自动发布（判 review_pending）。"""
    from app.services.gold_story.gold_chat.import_story import (
        _source_facts_not_resolved,
    )

    assert not _source_facts_not_resolved({})
    assert not _source_facts_not_resolved({"payload": {}})
    assert not _source_facts_not_resolved(
        {"payload": {"scene_contract": {"facts": []}}}
    )
    assert not _source_facts_not_resolved(
        {
            "payload": {
                "scene_contract": {
                    "facts": [
                        {"fact_id": "F1", "attribution_status": "resolved"}
                    ]
                }
            }
        }
    )
    # 只复述事件、没指定行为人的条目不算归属，不拦
    assert not _source_facts_not_resolved(
        {
            "payload": {
                "scene_contract": {
                    "facts": [
                        {
                            "fact_id": "F1",
                            "discoverer": "妈妈",
                            "attribution_status": "ambiguous",
                        }
                    ]
                }
            }
        }
    )
    for status in ("ambiguous", "review_pending", ""):
        assert _source_facts_not_resolved(
            {
                "payload": {
                    "scene_contract": {
                        "facts": [
                            {
                                "fact_id": "F1",
                                "secret_holder": "妈妈",
                                "attribution_status": status,
                            }
                        ]
                    }
                }
            }
        )


def test_import_gold_chat_daily_story_insert_and_reimport(
    app_ctx, tmp_path, monkeypatch,
):
    from app.repositories import repo_daily_story, repo_gold_story

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT01",
            url="https://www.bilibili.com/video/BV1TESTIMPORT01",
            mechanism="M6",
            structure_type="A",
            story_raw="导入测试专用故事" * 20,
            payload={
                "setting": "卧室门口",
                "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨被欺负"},
                    {"speaker": "灿灿", "intent": "得意威胁"},
                ],
                "closing_intent": "昭昭缩回角落",
                "banned_literals": ["小姨", "萌娃"],
                "funny_why": "幻想与怂的反差",
            },
            title="测试标题",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        assert inserted.get("action") == "insert"
        row = repo_gold_story.get_story(int(inserted["id"]))
        row["payload"]["scene_contract"] = {"mom_lines_max": 0}
        repo_gold_story.patch_story_payload(int(row["id"]), {"scene_contract": {"mom_lines_max": 0}})

    chat = _sample_chat()
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)
    captured_mom_max: list[int | None] = []
    original_validate = gc.validate_gold_chat

    def capture_validate(story, **kwargs):
        captured_mom_max.append(kwargs.get("mom_lines_max"))
        return original_validate(
            story,
            **{**kwargs, "mom_lines_max": 1},
        )

    monkeypatch.setattr(gc, "validate_gold_chat", capture_validate)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=False)
        assert out["action"] == "insert"
        assert captured_mom_max[0] == 0
        assert out["status"] == "review_pending"
        assert any("需重新终验" in reason for reason in out["production_reasons"])
        ds_id = int(out["daily_story_id"])
        saved = repo_daily_story.get_story(ds_id)
        assert saved["story"]["scene_title"] == "关门练功"
        assert saved["status"] == "review_pending"
        assert saved["story"]["dialogue"] == chat["dialogue"]
        assert "需重新终验" in "；".join(
            saved["story"].get("quality", {}).get("production_reasons", [])
        )

        row["gold_chat_daily_story_id"] = ds_id
        skip = gc.import_gold_chat_daily_story(row, review=False)
        assert skip["action"] == "skip"
        assert skip["status"] == "review_pending"
        assert any("需重新终验" in reason for reason in skip["production_reasons"])

        chat2 = dict(chat)
        chat2["scene_title"] = "新标题"
        gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat2)
        updated = gc.import_gold_chat_daily_story(row, force=True, review=False)
        assert updated["action"] == "update"
        assert updated["status"] == "review_pending"
        assert updated["production_reasons"]
        saved2 = repo_daily_story.get_story(ds_id)
        assert saved2["story"]["scene_title"] == "新标题"


@pytest.mark.parametrize("conflict_core", ["弟弟幻想报复姐姐，开门秒怂", "双胞胎关门练功，开门秒怂"])
def test_import_keeps_exported_final_quality(app_ctx, tmp_path, monkeypatch, conflict_core):
    from app.repositories import repo_daily_story, repo_gold_story
    from app.services.llm import llm_mgr as llm_mgr_mod

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT02",
            url="https://www.bilibili.com/video/BV1TESTIMPORT02",
            mechanism="M6",
            structure_type="A",
            story_raw="终分导入测试" * 20,
            payload={
                "setting": "卧室门口",
                "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
                "scene_contract": {"mom_lines_max": 1},
            },
            title="测试标题",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        row = repo_gold_story.get_story(int(inserted["id"]))

    chat = _sample_chat()
    chat["conflict_core"] = conflict_core
    dialogue = [dict(item) for item in chat["dialogue"]]
    chat["quality"] = {
        "score": 91,
        "structure_score": 80,
        "grade": "好",
        "pass": True,
        "humor": {
            "funny_score": 11,
            "best_moment": "开门就怂",
            "humor_type": "natural",
        },
        "summary": "结构80，好笑11，总分91",
        "reasons": ["总分91=结构80+LLM好笑11"],
    }
    chat["story_type"] = "A"
    from app.services.daily_story.quality import (
        gold_story_review_contract,
        stamp_story_review_binding,
    )
    stamp_story_review_binding(
        chat,
        semantic_pass=True,
        review_contract=gold_story_review_contract(row, chat),
    )
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)

    def _forbid_renorm(*_args, **_kwargs):
        raise AssertionError("终分稿不应再归一化")

    def _forbid_review(*_args, **_kwargs):
        raise AssertionError("终分稿不应再审读")

    monkeypatch.setattr(gc, "apply_gold_chat_normalizations", _forbid_renorm)
    monkeypatch.setattr(llm_mgr_mod, "_get_client", _forbid_review)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=True)
        assert out["action"] == "insert"
        assert out["status"] == "active"
        assert out["production_reasons"] == []
        saved = repo_daily_story.get_story(int(out["daily_story_id"]))

    quality = saved["story"]["quality"]
    assert quality["score"] == 91
    assert quality["structure_score"] == 80
    assert quality["humor"]["funny_score"] == 11
    assert saved["story"]["conflict_core"] == conflict_core
    assert saved["story"]["dialogue"] == dialogue
    assert saved["status"] == "active"


def test_real_final_acceptance_export_import_stays_active(
    app_ctx, tmp_path, monkeypatch,
):
    """真实终验、版本发布、导入和建制作任务共用门槛；全程只模拟外部审读。"""
    from app.repositories import repo_daily_story, repo_gold_story
    from app.services.daily_story.review import ExportSemanticReviewResult

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT03",
            url="https://www.bilibili.com/video/BV1TESTIMPORT03",
            mechanism="M6",
            structure_type="A",
            story_raw="真实终验导入链路" * 20,
            payload={
                "setting": "卧室门口",
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨被欺负"},
                    {"speaker": "灿灿", "intent": "得意威胁"},
                ],
                "closing_intent": "昭昭嘴硬收场",
                "scene_contract": {"mom_lines_max": 1},
            },
            title="真实终验导入链路",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        row = repo_gold_story.get_story(int(inserted["id"]))

    chat = _sample_chat()
    chat["dialogue"][-4:] = [
        {"speaker": "昭昭", "line": "我先把门开一条缝看看，你别突然冲进来呀。"},
        {"speaker": "灿灿", "line": "你开呀，我就在门口站着，看看你练成什么了。"},
        {"speaker": "昭昭", "line": "等等，我鞋带还没系好，高手出门也得先系鞋带。"},
        {"speaker": "灿灿", "line": "你刚才练的不会就是系鞋带功夫吧，笑死我了。"},
    ]
    chat["story_type"] = "A"
    chat["quality"] = {
        "structure_score": 80,
        "score": 80,
        "grade": "好",
        "summary": "结构80",
        "reasons": [],
    }
    semantic_result = ExportSemanticReviewResult(
        completed=True,
        issues=[],
        humor={
            "funny_score": 11,
            "best_moment": "开门秒怂",
            "humor_type": "situational",
        },
        error=None,
    )
    monkeypatch.setattr(
        "app.services.daily_story.review.run_export_semantic_review",
        lambda *_args, **_kwargs: semantic_result,
    )

    accepted = gcf.run_gold_chat_final_acceptance(
        chat,
        row,
        sid=str(row["source_id"]),
    )
    assert accepted["quality"]["semantic_pass"] is True
    assert accepted["quality"]["reviewed_content_hash"]
    assert accepted["quality"]["humor"]["funny_score"] == 11

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    paths = gc.export_gold_chat_files(
        source_id=str(row["source_id"]),
        row=row,
        chat=accepted,
        publish=False,
    )

    with app_ctx.app_context():
        from app.config import Config
        from app.services.daily_story.daily_story_mgr import daily_story_mgr

        monkeypatch.setattr(gce, "export_story_files", lambda **_kw: None)
        gce._backfill_gold_story_after_export(row, chat=accepted, paths=paths, config=Config())
        row = repo_gold_story.get_story(int(row["id"]))
        out = gc.import_gold_chat_daily_story(row, review=True)
        saved = repo_daily_story.get_story(int(out["daily_story_id"]))
        job = daily_story_mgr.create_job(int(saved["id"]))
        assert job["pipeline"] == "chat"
        assert job["stage"] == "script"
        assert job["status"] == "pending"

        from copy import deepcopy
        from app.services.llm.llm_deepseek import DeepSeekClient

        client = object.__new__(DeepSeekClient)
        storyboard_response = {"scenes": [
            {"shot_type": "中景", "dialogue": [
                {"speaker": item["speaker"], "text": item["line"]}
                for item in accepted["dialogue"][index:index + 2]
            ]}
            for index in range(0, len(accepted["dialogue"]), 2)
        ]}
        monkeypatch.setattr(client, "_chat_json", lambda *_a, **_kw: (deepcopy(storyboard_response), "stop"))
        script_input = deepcopy(saved["story"])
        storyboard = client.generate_daily_script(script_input, chars_per_sec=4.5)
        assert [
            (item["speaker"], item["text"])
            for scene in storyboard["scenes"] for item in scene["dialogue"]
        ] == [(item["speaker"], item["line"]) for item in accepted["dialogue"]]
        assert script_input == saved["story"]

        # 重发布/重导排除自身，并保留终验摘要；不再调用语义模型。
        monkeypatch.setattr(
            "app.services.daily_story.review.run_export_semantic_review",
            lambda *_a, **_kw: pytest.fail("合格稿导入和建任务不应重复审读"),
        )
        row = repo_gold_story.get_story(int(row["id"]))
        gce._backfill_gold_story_after_export(row, chat=accepted, paths=paths, config=Config())
        again = gc.import_gold_chat_daily_story(repo_gold_story.get_story(int(row["id"])), force=True)
        assert again["status"] == "active"
        assert again["daily_story_id"] == saved["id"]
        assert daily_story_mgr.create_job(int(saved["id"]))["status"] == "pending"

    assert out["status"] == "active"
    assert out["production_reasons"] == []
    assert saved["status"] == "active"
    assert saved["story"]["dialogue"] == accepted["dialogue"]
    assert (
        saved["story"]["quality"]["reviewed_content_hash"]
        == accepted["quality"]["reviewed_content_hash"]
    )


def test_resolve_gold_chat_snippet_same_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        GOLD_CHAT_LINES_SNIPPET_SOURCE_ID,
        resolve_gold_chat_snippet,
    )

    note = resolve_gold_chat_snippet(GOLD_CHAT_LINES_SNIPPET_SOURCE_ID)
    assert "不注入全文正例" in note
    assert "未满 240" in note
    assert "18–24" not in note
    assert GOLD_CHAT_LINES_SNIPPET not in note


def test_format_dialogue_seed_marks_spoken_lines():
    text = gc._format_dialogue_seed(
        [
            {"speaker": "灿灿", "intent": "零食归我，作业本归你，公平吧？"},
            {"speaker": "昭昭", "intent": "立规反杀"},
        ]
    )
    assert "要点" in text
    assert "勿逐字照抄" in text
    assert "intent：立规反杀" in text


def test_closing_for_prompt_shortens_long():
    long = (
        "灿灿求饶但嘴硬收场：昭昭用灿灿自己立的规矩"
        "「零食归我，作业本归你」堵住，灿灿语塞，答应归还零食，末句嘴硬约下次"
    )
    out = gc._closing_for_prompt(long)
    assert len(out) < len(long)
    assert "灿灿求饶但嘴硬收场" in out


def test_expand_regen_feedback_includes_short_error():
    from app.services.gold_story.gold_chat.prompts import (
        format_expand_regen_feedback,
    )

    fb = format_expand_regen_feedback(
        "正文总字数须≥240，当前214",
        None,
        structure_type="C",
        mechanism="M2",
    )
    assert "未满" in fb or "≥240" in fb
    assert "214" in fb or "错误" in fb


def test_gold_chat_scenario_rules_are_contract_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_scenario_rules_block,
    )

    unrelated = format_scenario_rules_block(
        mechanism="M9",
        structure_type="N",
        conflict_text="昭昭提出荒诞问题，灿灿认真回答",
        closing_intent="昭昭被答案噎住",
    )
    assert "互毁" not in unrelated
    assert "上药" not in unrelated

    mediation = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿先弄坏昭昭的画，双方互毁后妈妈调解",
        closing_intent="妈妈涂药后收束",
    )
    assert "本场互毁" in mediation
    assert "本场调解" in mediation
    assert "本场上药" in mediation

    # 「不和好」不得因含子串「和好」而注入调解
    denied = format_scenario_rules_block(
        mechanism="M8",
        structure_type="J",
        conflict_text="昭昭先动手抢垫子",
        closing_intent="灿灿压住，昭昭怂退，不和好，妈妈不出场",
    )
    assert "本场调解" not in denied
    assert "定责" not in denied

    # 中段拒和 + 结尾要求和好 → 仍注入和好/调解
    mid_refuse = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿拒绝和好，说不和好，冲突升级",
        closing_intent="妈妈调解后姐弟拉手和好",
    )
    assert "本场调解" in mid_refuse or "本场和好" in mid_refuse


def test_gold_chat_align_refine_prompts_are_type_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_align_refine_system,
        format_align_refine_user,
    )

    sys_j = format_align_refine_system(mechanism="M8", structure_type="J")
    user_j = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent="灿灿压住，昭昭怂退",
    )
    j_all = sys_j + user_j
    assert "保真-互毁" not in j_all
    assert "保真-和好" not in j_all
    assert "保真-M5" not in j_all
    assert "不打了" not in j_all
    assert "拉手" not in j_all
    assert "不得减少正文总字数" not in j_all
    assert "改短" in j_all or "改短或扩写" in j_all
    assert "≥240" in user_j or "≥{chars_min}" not in user_j

    # 否定契约：不和好 + 妈妈不出场 → 禁止和好/定责
    deny_closing = "灿灿压住，昭昭怂退，不和好，妈妈不出场"
    sys_deny = format_align_refine_system(
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    user_deny = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    deny_all = sys_deny + user_deny
    assert "保真-和好" not in deny_all
    assert "保真-H定责" not in deny_all
    assert "妈妈分层定责" not in deny_all

    # 中段「不和好」不得覆盖结尾和好要求
    mid_refuse_closing = "妈妈调解后姐弟拉手和好"
    mid_refuse_conflict = "灿灿拒绝和好，说不和好，冲突升级"
    user_mid = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent=mid_refuse_closing,
        conflict_text=mid_refuse_conflict,
    )
    assert "保真-和好" in user_mid
    assert "保真-H定责" in user_mid

    sys_h = format_align_refine_system(
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    user_h = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    h_all = sys_h + user_h
    assert "M5 立规" in sys_h
    assert "保真-互毁" in user_h
    assert "保真-和好" in user_h
    assert "拉手" in h_all


def test_is_truncation_error():
    assert gc._is_truncation_error(
        "LLM output truncated (finish_reason=length)；对白 JSON 须短小"
    )
    assert not gc._is_truncation_error("正文总字数须≥240，当前214")


def test_resolve_gold_chat_snippet_cross_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        resolve_gold_chat_snippet,
    )

    assert resolve_gold_chat_snippet("BV1OTHER") == GOLD_CHAT_LINES_SNIPPET


def test_normalize_enriches_setting_from_bowl_lines():
    chat = {
        "setting": "餐桌旁，灿灿和昭昭在吵架",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            {"speaker": "灿灿", "line": "你碗里那青菜不香吗？"},
        ],
    }
    row = {
        "structure_type": "C",
        "mechanism": "M2",
        "payload": {
            "scene_contract": {
                "location": "餐桌",
                "object": "肉",
                "characters": ["灿灿", "昭昭"],
            }
        },
    }
    out, notes = gc.apply_gold_chat_normalizations(chat, row=row)
    assert "肉" in str(out.get("setting") or "")
    assert "青菜" in str(out.get("setting") or "")
    assert any("冲突物" in n for n in notes)


def test_gate_forced_m14_p_rejects_when_not_q():
    """无拆穿反噬链的假 P 仍结构驳回；能纠到 Q 的不走此门。"""
    row = {
        "id": 99,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "两人互骂了一会儿就散了",
        "payload": {
            "story_raw": "姐弟互骂几句，没有道具整蛊也没有认怂。",
            "beat": ["互骂", "散场"],
            "closing_intent": "散了",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "骂一句"},
                {"speaker": "昭昭", "intent": "回骂"},
            ],
        },
    }
    with pytest.raises(ValueError, match="forced-m14p-not-prank"):
        gc._gate_forced_m14_p_or_raise(row)


def test_resolve_row_75_to_m15_q_allows_convert_gate():
    row = {
        "id": 75,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "灿灿抽签耍赖，借口胃小推食，妈妈看穿让洗碗",
        "payload": {
            "story_raw": (
                "妈妈和灿灿玩抽签吃饭，灿灿耍赖重抽、逞强吃辣，"
                "最后借口胃小把剩食推给妈妈，妈妈看穿心思让她洗碗。"
            ),
            "beat": ["抽签", "逞强", "推食", "洗碗"],
            "closing_intent": "妈妈笑着让灿灿洗碗，看穿她的小心思",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "耍赖重抽"},
                {"speaker": "灿灿", "intent": "推食借口胃小"},
                {"speaker": "妈妈", "intent": "看穿心思让洗碗"},
            ],
            "structure_mapping_note": "M2→M14+P",
        },
    }
    out, notes = gc._resolve_structure_row(row)
    assert out["mechanism"] == "M15"
    assert out["structure_type"] == "Q"
    assert any("cheat-expose" in n or "M15" in n for n in notes)
    gc._gate_forced_m14_p_or_raise(out)  # 已是 Q，不应抛


def test_local_hard_repairs_punchline_and_mom():
    story = _sample_chat()
    story.pop("punchline_explain", None)
    story["story_type"] = "A"
    story["dialogue"] = list(story["dialogue"]) + [
        {"speaker": "妈妈", "line": "别吵了先吃饭。"},
        {"speaker": "妈妈", "line": "吃完再理论。"},
    ]
    out = gc._apply_gold_chat_local_hard_repairs(
        story, structure_type="A", mom_lines_max=1
    )
    assert "punchline_explain" in out
    assert str(out["punchline_explain"]).startswith("A类")
    mom_n = sum(
        1
        for d in out["dialogue"]
        if isinstance(d, dict) and d.get("speaker") == "妈妈"
    )
    assert mom_n <= 1


def test_reject_message_not_pad_when_missing_fields():
    err = "缺少字段: punchline_explain; 妈妈台词须≤1句，当前2; 正文总字数须≥240，当前226"
    msg = gc._short_content_reject_message(err)
    assert "校验驳回" in msg
    assert "本地垫字仍不足" not in msg
    assert gc._has_non_short_hard_errors(err)


def test_structure_cons_lists_dad_penalty_symmetric_with_mom():
    """爸爸侧契约感知补丁须与妈妈侧同构：契约给 N 句则第 N+1 句才扣。"""
    from app.services.daily_story.quality import (
        score_daily_story,
        structure_cons_for_log,
    )

    def _dad_penalty(dad_count: int, **extra: object) -> list[str]:
        dialogue = [
            {"speaker": "灿灿", "line": "我先骑，你松手，这轮到我啦吧。"},
            {"speaker": "昭昭", "line": "该我骑了，给我，你都骑三圈了。"},
            {"speaker": "灿灿", "line": "再闹我恼了！"},
        ] + [
            {"speaker": "爸爸", "line": "不念了不念了，我吃饭，你俩自己分。"}
        ] * dad_count
        story = {
            "story_type": "K",
            "conflict_core": "抢三轮车",
            "punchline_explain": "回旋镖式收束",
            "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
            "closing_mode": "K_B_CHILD_SELF_RESOLVE",
            "dialogue": dialogue,
        }
        story.update(extra)
        q = score_daily_story(story, skip_relevancy=True)
        return [str(c) for c in (q.get("structure_cons") or []) if "爸爸台词" in str(c)]

    # 无契约：沿用全局默认 dad_lines_penalty_at=2，第 2 句起扣
    assert not _dad_penalty(1)
    assert _dad_penalty(2)

    # 契约给 2 句：第 2 句不应再扣（契约要求爸爸承担 2 拍，这是合规的）
    assert not _dad_penalty(2, _gold_chat_dad_lines_max=2)
    # 超过契约值仍扣，阈值未失效
    assert _dad_penalty(3, _gold_chat_dad_lines_max=2)

    # 契约给 0 句：阈值只会被抬高、不会被压到 0 以下；爸爸仍按全局默认 2 句起扣
    assert _dad_penalty(2, _gold_chat_dad_lines_max=0)
    assert not _dad_penalty(1, _gold_chat_dad_lines_max=0)

    # 与妈妈侧口径分离：妈妈契约字段不应放开爸爸（两套字段各自生效）
    assert _dad_penalty(2, _gold_chat_mom_lines_max=2)
    assert structure_cons_for_log({"structure_cons": ["爸爸台词偏多（2句）"]})


def test_gold_chat_dad_budget_injection_uses_authoritative_resolver():
    """注入的 _gold_chat_dad_lines_max 须与 resolve_parent_lines_budget 同口径。"""
    from app.services.gold_story.scene import resolve_parent_lines_budget

    # 契约给爸爸 2 拍、mom_lines_max=2：爸爸额度须抬到 2（不被硬编码 1 压住）
    scene_contract = {
        "story_type": "K",
        "mom_lines_max": 2,
        "beat_chain": [
            {"beat": 1, "speaker": "灿灿", "intent": "占物"},
            {"beat": 3, "speaker": "爸爸", "intent": "旁观解说"},
            {"beat": 5, "speaker": "爸爸", "intent": "被推趔趄"},
        ],
    }
    _, dad_expect, _ = resolve_parent_lines_budget(
        scene_contract, mom_lines_max=scene_contract.get("mom_lines_max")
    )
    assert dad_expect >= 2  # 拍到 2，额度不得低于 2

    # 契约没给爸爸拍：额度回落，不应无端放大
    plain = {"story_type": "K", "mom_lines_max": 2, "beat_chain": [
        {"beat": 1, "speaker": "灿灿", "intent": "占物"},
    ]}
    _, dad_plain, _ = resolve_parent_lines_budget(
        plain, mom_lines_max=plain.get("mom_lines_max")
    )
    assert dad_plain <= 2


def test_review_contract_snapshot_includes_dad_lines_max():
    """爸爸额度会影响评分，须进终验快照，否则契约变化漏判为「正文未失效」。"""
    from app.services.daily_story.quality import (
        story_review_contract_snapshot,
        story_review_content_hash,
    )

    base = {
        "story_type": "K",
        "dialogue": [{"speaker": "灿灿", "line": "我先骑。"}],
        "_gold_chat_mom_lines_max": 2,
    }
    snap = story_review_contract_snapshot(base)
    assert snap.get("mom_lines_max") == 2
    # 未注入爸爸额度时不写该键（存量稿/非 K 不受影响）
    assert "dad_lines_max" not in snap

    with_dad = dict(base, _gold_chat_dad_lines_max=2)
    snap_dad = story_review_contract_snapshot(with_dad)
    assert snap_dad.get("dad_lines_max") == 2

    # 爸爸契约变化须改变正文摘要，从而触发重新审读
    h_2 = story_review_content_hash(with_dad)
    h_1 = story_review_content_hash(dict(base, _gold_chat_dad_lines_max=1))
    assert h_2 != h_1


def test_structure_cons_lists_mom_penalty_and_log_cons():
    from app.services.daily_story.quality import (
        score_daily_story,
        structure_cons_for_log,
    )

    dialogue = [
        {"speaker": "妈妈", "line": "你作业写完了吗？"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打我吧。"},
        {"speaker": "妈妈", "line": "你说什么？"},
        {"speaker": "灿灿", "line": "噗，弹簧屁股吗？"},
        {"speaker": "妈妈", "line": "都给我消停。"},
        {"speaker": "昭昭", "line": "因为弹，所以打了不哭呀。"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为Q弹就能救场呀。"},
        {"speaker": "灿灿", "line": "你这歪理也太绝了。"},
        {"speaker": "昭昭", "line": "我说得通吧。"},
        {"speaker": "灿灿", "line": "那……我说不过你。"},
        {"speaker": "昭昭", "line": "行吧。"},
    ]
    base = {
        "story_type": "N",
        "conflict_core": "Q弹救场",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    q_default = score_daily_story(dict(base))
    cons_default = q_default.get("structure_cons") or []
    assert any("妈妈台词偏多（3句）" in str(c) for c in cons_default)
    assert structure_cons_for_log(q_default)

    with_contract = dict(base)
    with_contract["_gold_chat_mom_lines_max"] = 3
    q_contract = score_daily_story(with_contract)
    cons_contract = q_contract.get("structure_cons") or []
    assert not any("妈妈台词偏多" in str(c) for c in cons_contract)

    over = dict(with_contract)
    over["dialogue"] = list(dialogue) + [
        {"speaker": "妈妈", "line": "灿灿快去写作业。"},
    ]
    q_over = score_daily_story(over)
    assert any("妈妈台词偏多（4句）" in str(c) for c in q_over.get("structure_cons") or [])


def test_structure_score_feedback_and_fail_log_use_structure_cons():
    import logging

    from app.services.gold_story.gold_chat.prompts import (
        format_structure_score_feedback,
    )

    quality = {
        "structure_score": 70,
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": ["结构70", "妈妈台词偏多（3句）"],
    }
    fb = format_structure_score_feedback("structure_score:70", {"quality": quality})
    assert "偏多" in fb

    logger_name = "app.services.gold_story.gold_chat.convert"
    mod_logger = logging.getLogger(logger_name)
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _CaptureHandler()
    handler.setLevel(logging.INFO)
    saved_level = mod_logger.level
    saved_propagate = mod_logger.propagate
    saved_handlers = mod_logger.handlers[:]
    try:
        mod_logger.handlers = [handler]
        mod_logger.propagate = False
        mod_logger.setLevel(logging.INFO)
        chat = {"story_type": "N", "dialogue": [{"speaker": "昭昭", "line": "测"}]}
        gc.log_gold_chat_structure_score_fail(chat, quality, structure_type="N")
    finally:
        mod_logger.setLevel(saved_level)
        mod_logger.propagate = saved_propagate
        mod_logger.handlers[:] = saved_handlers

    assert captured
    assert "妈妈台词偏多" in captured[0]
    assert "reasons=" in captured[0]


def test_structure_cons_excludes_humor_regex_diagnostics():
    from app.services.daily_story.quality import structure_cons_for_log

    quality = {
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": [
            "结构70",
            "妈妈台词偏多（3句）",
            "好笑诊断：末句缺回旋",
        ],
    }
    cons = structure_cons_for_log(quality)
    assert cons == ["妈妈台词偏多（3句）"]
    assert not any("好笑" in c for c in cons)

    empty_key = {"structure_cons": [], "reasons": ["好笑诊断：xxx"]}
    assert structure_cons_for_log(empty_key) == []


def test_refine_short_candidate_uses_real_validation_without_padding(monkeypatch):
    """只 mock 模型与语义对齐；真实字数、单句长度等硬校验必须通过。"""
    import copy
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    repaired = _sample_chat()
    for index, line in enumerate(repaired["dialogue"]):
        line["speaker"] = "昭昭" if index % 2 == 0 else "灿灿"
    gc.validate_gold_chat(repaired, mom_lines_max=2)
    short = copy.deepcopy(repaired)
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    assert gc.dialogue_total_chars(short) < gc.DAILY_STORY_BODY_CHARS_MIN
    prompts = []

    def fix(candidate, prompt, **kwargs):
        prompts.append(prompt)
        assert gc.dialogue_total_chars(candidate) < gc.DAILY_STORY_BODY_CHARS_MIN
        return copy.deepcopy(repaired)

    def no_padding(*args, **kwargs):
        raise AssertionError("精修校验不得机械补字")

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(gc, "_fix_chat_with_llm", fix)
    monkeypatch.setattr(gex, "_ensure_gold_chat_min_chars", no_padding)
    budget = GoldChatRepairBudget(max_repairs=2)
    result = grf.refine_gold_chat_align(
        short, structure_type="", mechanism="", align_block="",
        mom_lines_max=2, repair_budget=budget,
    )
    gc.validate_gold_chat(result, mom_lines_max=2)
    assert gc.dialogue_total_chars(result) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(prompts) == budget.used == 1
    assert "正文总字数" in prompts[0]


def test_prepare_short_candidate_does_not_pad_to_pass():
    import copy

    short = copy.deepcopy(_sample_chat())
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    before = copy.deepcopy(short["dialogue"])
    with pytest.raises(ValueError, match="正文总字数"):
        gex._prepare_chat_for_validate(
            short, structure_type="", mechanism="", mom_lines_max=2,
        )
    assert short["dialogue"] == before


def test_refine_short_repair_exhaustion_preserves_candidate(monkeypatch):
    import copy
    from app.services.gold_story.gold_chat.repair import AlignRepairFailure, GoldChatRepairBudget

    short = _sample_chat()
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    calls = []

    def unsuccessful_fix(candidate, prompt, **kwargs):
        calls.append(prompt)
        return copy.deepcopy(candidate)

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(gc, "_fix_chat_with_llm", unsuccessful_fix)
    budget = GoldChatRepairBudget(max_repairs=2)
    with pytest.raises(AlignRepairFailure, match="正文总字数") as caught:
        grf.refine_gold_chat_align(
            short, structure_type="", mechanism="", align_block="",
            mom_lines_max=2, repair_budget=budget, max_rounds=2,
        )
    assert len(calls) == budget.used == 2
    assert gc.dialogue_total_chars(caught.value.candidate) < gc.DAILY_STORY_BODY_CHARS_MIN


def test_expand_local_length_close_avoids_second_llm_repair(monkeypatch, caplog):
    import copy
    import logging
    from app.services.gold_story.gold_chat import repair
    from app.services.gold_story.gold_chat.validate import (
        gold_chat_effective_min_chars,
    )

    real_gate = gc._gate_gold_chat_structure_score
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", real_gate)
    monkeypatch.setattr(gex.logger, "handlers", [caplog.handler])
    generations = []
    repair_inputs = []

    def generate(*args, **kwargs):
        generations.append(1)
        return _sample_chat()

    def score(chat, row):
        current_score = 80 if chat.get("revision") else 65
        return {**chat, "quality": {"structure_score": current_score, "score": current_score}}

    def fix(chat, prompt, **kwargs):
        repair_inputs.append((chat.get("revision", 0), prompt))
        result = copy.deepcopy(chat)
        # 模拟第 1 次结构修稿已把结构分修到 80，但正文被压到 205 字（低于放宽下限）。
        for line in result["dialogue"]:
            while len(line["line"]) > 1 and gc.dialogue_total_chars(result) > 205:
                line["line"] = line["line"][:-1]
        result["revision"] = len(repair_inputs)
        return result

    monkeypatch.setattr(
        gex,
        "_short_spot_fix_chat_with_llm",
        lambda chat, fb, **kw: fix(chat, fb),
    )
    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fix)
    budget = repair.GoldChatRepairBudget(max_repairs=2)

    with caplog.at_level(logging.INFO):
        result = gex.gold_story_to_gold_chat(_sample_row(), repair_budget=budget)

    assert result["revision"] == 1
    assert result["quality"]["structure_score"] == 80
    # 本地收口后仍在下限之内即可（联合判据：18 句达标则字数下限放宽一行）。
    assert gc.dialogue_total_chars(result) >= gold_chat_effective_min_chars(
        result["dialogue"]
    )
    assert len(generations) == 1
    assert [revision for revision, _ in repair_inputs] == [0]
    assert budget.used == 1
    assert budget.remaining == 1
    assert "candidate rejected stage=expand_structure score=65" in caplog.text
    assert "repair post-hard length close chars=205->" in caplog.text


def test_expand_structure_restores_accidental_parent_speaker_without_deleting_body():
    import copy

    baseline = {
        "dialogue": [
            {"speaker": "妈妈", "line": "先把规矩说清楚。"},
            {"speaker": "昭昭", "line": "我有话要认真解释。"},
            {"speaker": "灿灿", "line": "那你先说，我听着。"},
            {"speaker": "妈妈", "line": "你们继续说。"},
            {"speaker": "昭昭", "line": "我继续把理由讲完。"},
            {"speaker": "妈妈", "line": "行吧，我听明白了。"},
        ]
    }
    draft = copy.deepcopy(baseline)
    draft["dialogue"][1]["speaker"] = "妈妈"
    before_chars = gc.dialogue_total_chars(draft)

    out, changed = gex._restore_extra_parent_speakers_from_baseline(
        draft,
        baseline,
        parent_lines_max=3,
    )

    assert changed
    assert out["dialogue"][1]["speaker"] == "昭昭"
    assert len(out["dialogue"]) == len(draft["dialogue"])
    assert gc.dialogue_total_chars(out) == before_chars
    assert sum(
        row.get("speaker") in {"妈妈", "爸爸"}
        for row in out["dialogue"]
    ) == 3


def test_expand_structure_repair_caps_mom_before_acceptance(monkeypatch, caplog):
    """N 结构修稿新增第 4 句妈妈时，同轮裁回并补足字数，不再烧第二次预算。"""
    import copy
    import logging
    from app.services.gold_story.gold_chat import repair

    real_gate = gc._gate_gold_chat_structure_score
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", real_gate)
    monkeypatch.setattr(gex.logger, "handlers", [caplog.handler])

    row = _sample_row()
    row["structure_type"] = "N"
    row["mechanism"] = "M6"
    row["payload"]["scene_contract"] = {"mom_lines_max": 3}
    repair_calls = []

    def generate(*args, **kwargs):
        chat = _sample_chat()
        chat["story_type"] = "N"
        chat["punchline_explain"] = "N类：追问后一本正经自洽，最后让对方接不住"
        chat["dialogue"] = [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是铅笔找不到了嘛。"},
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "妈妈", "line": "昭昭，你手都停半空了，为什么突然说这个？"},
            {"speaker": "昭昭", "line": "因为没人教，我自己想的，Q弹的打了不疼，还响呢！"},
            {"speaker": "灿灿", "line": "你还真是照这个道理认真想的？"},
            {"speaker": "昭昭", "line": "当然，我刚才就是这么认真回答的。"},
            {"speaker": "灿灿", "line": "噗……昭昭你别说了，我肩膀都抖了。"},
            {"speaker": "妈妈", "line": "你还笑？作业没写你倒笑得出来？"},
            {"speaker": "昭昭", "line": "姐姐笑，是喜欢我屁股Q弹，还是不信？"},
            {"speaker": "灿灿", "line": "妈，我这就写，你别听昭昭胡说，快挪开。"},
            {"speaker": "昭昭", "line": "我没胡说，你看我扭一下，弹回来还带晃的。"},
            {"speaker": "妈妈", "line": "行吧行吧，你们俩一个比一个会捣乱。"},
            {"speaker": "灿灿", "line": "我回房间补作业，十分钟就写完吧。"},
            {"speaker": "昭昭", "line": "那妈，我屁股还打不打了？不打我收起来咯。"},
        ]
        assert gc.dialogue_total_chars(chat) >= gc.DAILY_STORY_BODY_CHARS_MIN
        assert sum(x.get("speaker") == "妈妈" for x in chat["dialogue"]) == 3
        return chat

    def score(chat, _row):
        current = 80 if chat.get("revision") else 65
        return {**chat, "quality": {"structure_score": current, "score": current}}

    def fix(chat, prompt, **kwargs):
        repair_calls.append(prompt)
        out = copy.deepcopy(chat)
        # 模拟真实失败：结构修稿已把分数修好，但又新增一条妈妈句（句数也变化）。
        # 这样不能靠 baseline speaker 还原，必须走 N-aware hard trim。
        out["dialogue"].insert(10, {"speaker": "妈妈", "line": "先把这件事说清楚。"})
        out["revision"] = 1
        assert sum(x.get("speaker") == "妈妈" for x in out["dialogue"]) == 4
        return out

    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fix)
    budget = repair.GoldChatRepairBudget(max_repairs=2)

    with caplog.at_level(logging.INFO):
        result = gex.gold_story_to_gold_chat(row, repair_budget=budget)

    mom_n = sum(x.get("speaker") == "妈妈" for x in result["dialogue"])
    assert result["quality"]["structure_score"] == 80
    assert gc.dialogue_total_chars(result) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert mom_n <= 3
    assert len(repair_calls) == 1
    assert budget.used == 1
    assert budget.remaining == 1
    assert "repair local hard close mom=4->3 max=3" in caplog.text
    body = "".join(str(x.get("line") or "") for x in result["dialogue"])
    assert "为什么突然说这个" in body


def test_expand_stops_when_alignment_budget_exhausted(monkeypatch):
    from app.services.gold_story.gold_chat.repair import (
        AlignRepairFailure, GoldChatRepairBudget, GoldChatRepairExhausted,
    )

    _bypass_structure_gate(monkeypatch)
    generations = []

    def generate(*args, **kwargs):
        generations.append(1)
        return _sample_chat()

    def fail_alignment(chat, **kwargs):
        budget = kwargs["repair_budget"]
        assert budget.consume(stage="align")
        assert budget.consume(stage="align")
        candidate = {**chat, "revision": "latest_align"}
        raise AlignRepairFailure(
            stage="align_validate", validation_errors=["正文总字数须≥240，当前222"],
            align_issues=[], candidate=candidate,
        )

    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(grf, "refine_gold_chat_align", fail_alignment)
    budget = GoldChatRepairBudget(max_repairs=2)
    with pytest.raises(GoldChatRepairExhausted, match="当前222") as caught:
        gex.gold_story_to_gold_chat(_sample_row(), repair_budget=budget)
    assert caught.value.stage == "align_validate"
    assert caught.value.candidate["revision"] == "latest_align"
    assert len(generations) == 1
    assert budget.used == 2


def test_replace_banned_kinship_keeps_in_product_jiejie():
    """站内「姐姐」是目标称呼，禁词含它也不得反向替换成「灿灿」。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_replace_banned_kinship,
    )

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "姐姐，炸鸡摆好了！"},
            {"speaker": "昭昭", "line": "别走啊姐姐，我这次不赖了！"},
        ]
    }
    out, changed = patch_replace_banned_kinship(
        story,
        banned_literals=["姐姐", "哥哥"],
    )
    assert not changed
    assert out["dialogue"][0]["line"] == "姐姐，炸鸡摆好了！"
    assert out["dialogue"][1]["line"] == "别走啊姐姐，我这次不赖了！"


def test_replace_banned_kinship_still_maps_source_terms():
    """源稿称谓哥哥/妹妹仍须 remap 到站内角色名。"""
    from app.services.gold_story.gold_chat.patch import (
        patch_replace_banned_kinship,
    )

    story = {"dialogue": [{"speaker": "昭昭", "line": "哥哥你别抢！"}]}
    out, changed = patch_replace_banned_kinship(story, banned_literals=["哥哥"])
    assert changed
    assert out["dialogue"][0]["line"] == "灿灿你别抢！"


def test_remap_source_kinship_to_jiedi_metadata():
    """落库前元数据 remap：站内关系只有姐弟，只换关系标签、保留内容词。"""
    from app.services.gold_story.gold_chat.patch import (
        remap_chat_kinship_metadata,
        remap_source_kinship,
    )

    assert remap_source_kinship("双胞胎抢娃娃，妹妹自砸头") == "姐弟抢娃娃，弟弟自砸头"
    assert remap_source_kinship("哥哥真动手") == "姐姐真动手"
    assert remap_source_kinship("姐妹抢拼图") == "姐弟抢拼图"
    # 相邻标签收敛成一个「姐弟」，不出「姐弟姐弟」
    assert remap_source_kinship("龙凤胎兄妹抢娃娃") == "姐弟抢娃娃"
    # 第三方亲属不 remap
    assert remap_source_kinship("隔壁妹妹也想来玩") == "隔壁妹妹也想来玩"
    assert remap_source_kinship("同学哥哥送我的") == "同学哥哥送我的"
    # 站内合法称呼原样
    assert remap_source_kinship("姐姐一棍就老实") == "姐姐一棍就老实"

    story = {
        "scene_title": "双胞胎抢娃娃，妹妹自砸头",
        "key": "抢娃娃自砸头",
        "conflict_core": "灿灿和昭昭抢同一个布娃娃",
        "punchline_explain": "G类：妹妹举书假装砸姐姐",
        "dialogue": [{"speaker": "昭昭", "line": "妹妹你干嘛"}],
    }
    out, theme, notes = remap_chat_kinship_metadata(story, theme="双胞胎抢娃娃，妹妹自砸头")
    assert theme == "姐弟抢娃娃，弟弟自砸头"
    assert out["scene_title"] == "姐弟抢娃娃，弟弟自砸头"
    assert out["punchline_explain"] == "G类：弟弟举书假装砸姐姐"
    # 对白正文不动（第三方可能有出处）
    assert out["dialogue"] == story["dialogue"]
    assert notes


class _SemanticBlocked(gcf.GoldChatAcceptanceBlocked):
    """带结构化 issues 的终检语义硬伤（测试替身）。"""

    def __init__(self, message: str, issues: list) -> None:
        self.issues = issues
        super().__init__(message)


def _missing_beat_issues() -> list:
    return [
        {
            "lines": [13],
            "kind": "缺前提",
            "desc": "爸爸只是坐着解说，没有任何被推或摔倒的事件发生",
            "missing_beat": {"beat": 5, "speaker": "爸爸", "intent": "被推趔趄"},
        },
        {
            "lines": [14],
            "kind": "缺前提",
            "desc": "这句归因依赖缺失的推人事件",
            "missing_beat": {"beat": 4, "speaker": "灿灿", "intent": "攻击解说员"},
        },
    ]


def test_missing_beat_exhausted_detects_semantic_block():
    """缺拍类终检硬伤应被识别（甲 触发条件）。"""
    exc = _SemanticBlocked("终检语义硬伤：缺前提", _missing_beat_issues())
    assert gc._is_missing_beat_exhausted(exc)


def test_missing_beat_exhausted_unwraps_repair_exhausted():
    """真实链路里语义异常被 GoldChatRepairExhausted 包一层，仍须识别。"""
    from app.services.gold_story.gold_chat.repair import GoldChatRepairExhausted

    inner = _SemanticBlocked("终检语义硬伤：缺前提", _missing_beat_issues())
    wrapped = GoldChatRepairExhausted(
        stage="final_acceptance", reason=str(inner), candidate={"dialogue": []}
    )
    wrapped.__cause__ = inner
    assert gc._is_missing_beat_exhausted(wrapped)


def test_missing_beat_exhausted_ignores_non_beat_failures():
    """非缺拍失败不得触发甲（仍走全局 3 次重掷）。"""
    from app.services.gold_story.gold_chat.repair import GoldChatRepairExhausted

    other = GoldChatRepairExhausted(
        stage="final_acceptance",
        reason="对白句数须≥12，当前9",
        candidate={"dialogue": []},
    )
    assert not gc._is_missing_beat_exhausted(other)


def test_missing_beat_retry_limit_is_one():
    """缺拍类只给 1 次重掷，全局常量仍为 3（专家裁决，勿改全局）。"""
    assert gc.GOLD_CHAT_MISSING_BEAT_ATTEMPTS == 1
    assert gc.GOLD_CHAT_DRAFT_ATTEMPTS == 3


def test_missing_beat_retry_grants_exactly_one_extra_draft():
    """首个 draft 撞缺拍 → 上限抬到下一次；第二次仍缺拍不再续命。"""
    assert (
        gc._next_draft_attempt_limit(
            draft_attempt=1, current_limit=3, missing_beat_retry_used=False
        )
        == 2
    )
    # 第二次仍缺拍：上限收回本次，循环随即结束
    assert (
        gc._next_draft_attempt_limit(
            draft_attempt=2, current_limit=3, missing_beat_retry_used=True
        )
        == 2
    )
    # 不放宽既有更小上限
    assert (
        gc._next_draft_attempt_limit(
            draft_attempt=2, current_limit=2, missing_beat_retry_used=False
        )
        == 2
    )


def test_extract_missing_beat_intents_keeps_semantics_only():
    """抽取的反馈只带语义事件与说话人，不带 beat 编号/行号。"""
    exc = _SemanticBlocked("终检语义硬伤：缺前提", _missing_beat_issues())
    got = gc._missing_beat_intents_from(exc)
    assert got == [
        {"original_intent": "被推趔趄", "expected_speaker": "爸爸"},
        {"original_intent": "攻击解说员", "expected_speaker": "灿灿"},
    ]
    for item in got:
        assert "beat" not in item
        assert "insert_after_line" not in item
        assert "lines" not in item


def test_extract_missing_beat_intents_dedupes():
    """同一事件重复报多次只保留一条。"""
    issues = _missing_beat_issues()
    issues.append(dict(issues[0], lines=[15]))
    exc = _SemanticBlocked("终检语义硬伤：缺前提", issues)
    assert len(gc._missing_beat_intents_from(exc)) == 2


def test_retry_feedback_block_renders_events():
    """重掷反馈块须落到提示词里，且无反馈时为空串。"""
    from app.services.gold_story.gold_chat.prompts import (
        format_retry_missing_events_block,
    )

    exc = _SemanticBlocked("终检语义硬伤：缺前提", _missing_beat_issues())
    row = gc._attach_retry_missing_events({"id": 49}, gc._missing_beat_intents_from(exc))
    block = format_retry_missing_events_block(row)
    assert "上一轮缺拍" in block
    assert "被推趔趄" in block
    assert "爸爸" in block
    # 无反馈行不得渲染出提示块
    assert format_retry_missing_events_block({"id": 49}) == ""
    assert gc._attach_retry_missing_events({"id": 49}, []) == {"id": 49}


def test_expand_prompt_template_has_retry_events_slot():
    """扩写模板须留出缺拍反馈槽位，否则甲 的反馈根本进不了草稿。"""
    from app.services.gold_story.gold_chat.prompts import _USER

    assert "{retry_missing_events_block}" in _USER


def test_carry_retry_feedback_survives_db_reload():
    """从库里重读行后，内存态的重掷反馈不得被静默丢掉。"""
    stale = {
        "id": 49,
        "gold_chat_retry_feedback": {
            "reason": "missing_beat_exhausted",
            "missing_events": [{"original_intent": "被推趔趄"}],
        },
    }
    fresh = {"id": 49, "structure_type": "K"}  # 库里没有该字段
    out = gc.carry_retry_feedback(fresh, stale)
    assert out["gold_chat_retry_feedback"] == stale["gold_chat_retry_feedback"]
    assert out["structure_type"] == "K"
    # 无反馈时原样返回库里行；库无行时退回旧行
    assert gc.carry_retry_feedback({"id": 49}, {"id": 49}) == {"id": 49}
    assert gc.carry_retry_feedback(None, stale) is stale
    assert gc.carry_retry_feedback(fresh, fresh) is fresh


def _order_seed() -> list[dict[str, str]]:
    return [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "灿灿", "intent": "别光看，你倒是管管"},
        {"speaker": "昭昭", "intent": "我还没骑完呢"},
    ]


def _order_dialogue() -> list[dict[str, str]]:
    return [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "你放手，别拽车把。"},
        {"speaker": "昭昭", "line": "那你先松脚。"},
        {"speaker": "灿灿", "line": "别光看，你倒是管管。"},
        {"speaker": "昭昭", "line": "我扶你。"},
        {"speaker": "爸爸", "line": "我这不是怕你们摔着嘛。"},
        {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
        {"speaker": "昭昭", "line": "咱俩先不抢了。"},
        {"speaker": "灿灿", "line": "行，我推你一把。"},
        {"speaker": "昭昭", "line": "你别推我。"},
        {"speaker": "灿灿", "line": "好啦。"},
        {"speaker": "爸爸", "line": "嗯。"},
        {"speaker": "昭昭", "line": "一起看吧。"},
        {"speaker": "灿灿", "line": "那行。"},
        {"speaker": "爸爸", "line": "我不掺和了。"},
    ]


def test_seed_order_monotonic_moves_premise_before_dependent():
    """后句引用了尚未发生的前提时，把前提句前移归位（句数不变）。"""
    from app.services.gold_story.gold_chat import patch as gcp

    out, changed = gcp.patch_seed_order_monotonic(
        {"dialogue": _order_dialogue()}, dialogue_seed=_order_seed()
    )
    assert changed is True
    lines = [r["line"] for r in out["dialogue"]]
    assert len(lines) == len(_order_dialogue())
    assert lines.index("看这招，昭昭无影脚。") < lines.index("别光看，你倒是管管。")


def test_seed_order_monotonic_skips_when_move_crosses_half_the_draft():
    """跨距超过整篇一半的移动不做，交回重掷/定点修稿。"""
    from app.services.gold_story.gold_chat import patch as gcp

    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "灿灿", "line": "别光看，你倒是管管。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "你放手，别拽车把。"},
        {"speaker": "昭昭", "line": "那你先松脚。"},
        {"speaker": "昭昭", "line": "我扶你。"},
        {"speaker": "爸爸", "line": "我这不是怕你们摔着嘛。"},
        {"speaker": "昭昭", "line": "咱俩先不抢了。"},
        {"speaker": "灿灿", "line": "行，我推你一把。"},
        {"speaker": "昭昭", "line": "你别推我。"},
        {"speaker": "灿灿", "line": "好啦。"},
        {"speaker": "爸爸", "line": "嗯。"},
        {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
        {"speaker": "昭昭", "line": "一起看吧。"},
        {"speaker": "灿灿", "line": "那行。"},
        {"speaker": "爸爸", "line": "我不掺和了。"},
    ]
    out, changed = gcp.patch_seed_order_monotonic(
        {"dialogue": dlg}, dialogue_seed=_order_seed()[:3]
    )
    assert changed is False
    assert out == {"dialogue": dlg}


def test_seed_order_monotonic_keeps_closing_window():
    """收束窗口（末 3 句）里的锚点不动，避免把收尾提前。"""
    from app.services.gold_story.gold_chat import patch as gcp

    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "灿灿", "line": "别光看，你倒是管管。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "你放手，别拽车把。"},
        {"speaker": "昭昭", "line": "那你先松脚。"},
        {"speaker": "昭昭", "line": "我扶你。"},
        {"speaker": "爸爸", "line": "我这不是怕你们摔着嘛。"},
        {"speaker": "昭昭", "line": "咱俩先不抢了。"},
        {"speaker": "灿灿", "line": "行，我推你一把。"},
        {"speaker": "昭昭", "line": "你别推我。"},
        {"speaker": "灿灿", "line": "好啦。"},
        {"speaker": "爸爸", "line": "嗯。"},
        {"speaker": "昭昭", "line": "一起看吧。"},
        {"speaker": "灿灿", "line": "那行。"},
        {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
        {"speaker": "爸爸", "line": "我不掺和了。"},
    ]
    out, changed = gcp.patch_seed_order_monotonic(
        {"dialogue": dlg}, dialogue_seed=_order_seed()[:3]
    )
    assert changed is False
    assert out == {"dialogue": dlg}


def test_seed_order_monotonic_noop_without_seed():
    from app.services.gold_story.gold_chat import patch as gcp

    dlg = _order_dialogue()
    out, changed = gcp.patch_seed_order_monotonic({"dialogue": dlg}, dialogue_seed=None)
    assert changed is False
    assert out == {"dialogue": dlg}


def test_seed_premise_patch_lands_before_first_landed_successor():
    """缺席的前提拍必须补到「首个已落地的后继 seed 拍」之前，不许后置补叙。"""
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "灿灿", "intent": "让你解说，你上来打"},
        {"speaker": "昭昭", "intent": "我还没骑完呢"},
        {"speaker": "灿灿", "intent": "行，我推你一把"},
        {"speaker": "昭昭", "intent": "你别推我"},
        {"speaker": "灿灿", "intent": "好啦"},
        {"speaker": "爸爸", "intent": "我不掺和了"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "让你解说，你上来打。"},
        {"speaker": "昭昭", "line": "你别推我。"},
        {"speaker": "灿灿", "line": "行，我推你一把。"},
        {"speaker": "灿灿", "line": "好啦。"},
        {"speaker": "爸爸", "line": "我不掺和了。"},
    ]
    out, changed = gcp.patch_seed_premise_lines({"dialogue": dlg}, dialogue_seed=seed)
    assert changed is True
    lines = [r["line"] for r in out["dialogue"]]
    assert lines.index("看这招，昭昭无影脚") < lines.index("让你解说，你上来打。")


def test_seed_premise_patch_fills_absent_tail_speaker():
    """整场缺席的收尾拍（如家长反应）要按 seed 补回，而不是无声丢掉。

    旧行为「找不到后继锚点就不补」会让无人引用的收尾拍整拍丢失（专家裁决）：
    尾拍没有依赖它的句子，插到已落地前驱之后、收束句之前即可。
    """
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "灿灿", "intent": "行，我推你一把"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我不管。"},
        {"speaker": "灿灿", "line": "随便你。"},
        {"speaker": "昭昭", "line": "嗯。"},
        {"speaker": "灿灿", "line": "好吧。"},
    ]
    out, changed = gcp.patch_seed_premise_lines({"dialogue": dlg}, dialogue_seed=seed)
    assert changed is True
    speakers = [item["speaker"] for item in out["dialogue"]]
    lines = [item["line"] for item in out["dialogue"]]
    # 爸爸整场缺席 -> 补在收束句之前；灿灿已说过话，不因字面对不上再插一行
    assert speakers == ["灿灿", "昭昭", "灿灿", "昭昭", "爸爸", "灿灿"]
    assert lines[4] == "看这招，昭昭无影脚"
    assert "行，我推你一把" not in lines
    assert dlg == [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我不管。"},
        {"speaker": "灿灿", "line": "随便你。"},
        {"speaker": "昭昭", "line": "嗯。"},
        {"speaker": "灿灿", "line": "好吧。"},
    ]


def test_seed_premise_patch_keeps_paraphrase_tail_speaker():
    """角色已经说过话（换词写了同一拍）时不得再插 seed 原文，避免语义重复。"""
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我不管。"},
        {"speaker": "爸爸", "line": "你们自己商量，我看戏。"},
    ]
    out, changed = gcp.patch_seed_premise_lines({"dialogue": dlg}, dialogue_seed=seed)
    assert changed is False
    assert out == {"dialogue": dlg}


def test_missing_seed_rows_reports_absent_speaker_only():
    """拍落地覆盖检查只认「说话人整场缺席」，改写过的同角色拍不算丢失。"""
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
    ]
    assert gcp.missing_seed_rows(
        [{"speaker": "灿灿", "line": "我先骑，你松手。"}], seed
    ) == [("爸爸", "看这招，昭昭无影脚")]
    assert gcp.missing_seed_rows(
        [{"speaker": "爸爸", "line": "你们自己商量。"}], seed
    ) == [("灿灿", "我先骑，你松手")]
    # 两个角色都说过话（哪怕换了词）就不算丢失
    assert gcp.missing_seed_rows(
        [
            {"speaker": "灿灿", "line": "我先骑，你松手。"},
            {"speaker": "爸爸", "line": "你们自己商量。"},
        ],
        seed,
    ) == []
    # 空稿等于所有拍都没落地（调用方另有句数下限兜底）
    assert gcp.missing_seed_rows([], seed) == [
        ("灿灿", "我先骑，你松手"),
        ("爸爸", "看这招，昭昭无影脚"),
    ]
    assert gcp.missing_seed_rows([{"speaker": "灿灿", "line": "x"}], []) == []



def test_seed_premise_patch_allows_seed_consecutive_same_speaker():
    """seed 自身连续同角色时应保持顺序（允许连说），不得退格反序。"""
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "爸爸", "intent": "灿灿泰山压顶，漂亮"},
        {"speaker": "灿灿", "intent": "让你解说，你上来打"},
        {"speaker": "昭昭", "intent": "我还没骑完呢"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "让你解说，你上来打。"},
        {"speaker": "昭昭", "line": "嗯。"},
    ]
    out, changed = gcp.patch_seed_premise_lines({"dialogue": dlg}, dialogue_seed=seed)
    assert changed is True
    lines = [r["line"] for r in out["dialogue"]]
    assert (
        lines.index("看这招，昭昭无影脚")
        < lines.index("灿灿泰山压顶，漂亮")
        < lines.index("让你解说，你上来打。")
    )


def test_seed_premise_patch_scopes_inserts_to_named_speakers():
    """终检点名某角色缺拍时，补拍额度只花在该角色上，且整段连说不被拆开。

    反例（id49 实测）：按 seed 顺序补，额度先被无关前置拍吃光，真正缺失的
    整段家长解说补不回来，终检「缺前提」照旧。
    """
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "昭昭", "intent": "我还没骑完呢"},
        {"speaker": "灿灿", "intent": "你腿短够不着"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "爸爸", "intent": "灿灿泰山压顶来了"},
        {"speaker": "爸爸", "intent": "好，昭昭反击"},
        {"speaker": "灿灿", "intent": "你站哪边的"},
        {"speaker": "昭昭", "intent": "行啊，一起玩"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "爸你站哪边的，倒是拉架啊！"},
        {"speaker": "昭昭", "line": "你别喊爸。"},
        {"speaker": "灿灿", "line": "一起玩吧。"},
        {"speaker": "昭昭", "line": "行啊，一起玩。"},
    ]
    out, changed = gcp.patch_seed_premise_lines(
        {"dialogue": dlg},
        dialogue_seed=seed,
        only_speakers={"爸爸"},
    )
    assert changed is True
    lines = [str(r["line"]) for r in out["dialogue"]]
    assert "你腿短够不着" not in lines
    # 连续三拍整段补回，未被 _SEED_PREMISE_MAX_INSERTS 拆断
    assert "看这招，昭昭无影脚" in lines
    assert "灿灿泰山压顶来了" in lines
    assert "好，昭昭反击" in lines
    # 全部落在引用「爸你站哪边的」之前
    cite = lines.index("爸你站哪边的，倒是拉架啊！")
    assert lines.index("看这招，昭昭无影脚") < cite
    assert lines.index("好，昭昭反击") < cite


def test_seed_premise_patch_respects_parent_quota():
    """补拍不得越过契约给的说话人额度（额度按契约抬，不按 seed 行数抬）。

    反例（id49 实测）：seed 把一拍家长解说拆成三句，补拍照单全收后硬卡报
    「爸爸台词须≤3句，当前4」，整篇候选直接判死。额度是契约元数据，补拍只能
    在额度内落地：超出额度的 seed 行不补，缺口交给带反馈重掷。
    """
    from app.services.gold_story.gold_chat import patch as gcp

    seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "爸爸", "intent": "灿灿泰山压顶来了"},
        {"speaker": "爸爸", "intent": "好，昭昭反击"},
        {"speaker": "灿灿", "intent": "你站哪边的"},
        {"speaker": "昭昭", "intent": "行啊，一起玩"},
    ]
    dlg = [
        {"speaker": "灿灿", "line": "我先骑，你松手。"},
        {"speaker": "灿灿", "line": "爸你站哪边的，倒是拉架啊！"},
        {"speaker": "爸爸", "line": "我不掺和，你们自己玩。"},
        {"speaker": "昭昭", "line": "行啊，一起玩。"},
    ]
    # 契约：唯一在场的家长额度 3，稿内已有 1 句 -> 只容得下 2 句
    out, changed = gcp.patch_seed_premise_lines(
        {
            "dialogue": dlg,
            "story_type": "K",
            "_gold_chat_mom_lines_max": 0,
            "_gold_chat_dad_lines_max": 3,
        },
        dialogue_seed=seed,
        only_speakers={"爸爸"},
    )
    assert changed is True
    out_lines = out["dialogue"]
    assert sum(1 for r in out_lines if r["speaker"] == "爸爸") == 3
    # 额度用尽后不再补：第三句家长解说不得入稿
    assert "好，昭昭反击" not in [str(r["line"]) for r in out_lines]
    # 补进来的前提仍在引用句之前
    texts = [str(r["line"]) for r in out_lines]
    assert texts.index("看这招，昭昭无影脚") < texts.index("爸你站哪边的，倒是拉架啊！")

    # 额度为 1（且已被收尾句占满）时宁可不补，也不补出必挂的稿子
    out2, changed2 = gcp.patch_seed_premise_lines(
        {
            "dialogue": dlg,
            "story_type": "K",
            "_gold_chat_mom_lines_max": 0,
            "_gold_chat_dad_lines_max": 1,
        },
        dialogue_seed=seed,
        only_speakers={"爸爸"},
    )
    assert changed2 is False
    assert out2["dialogue"] == dlg


def test_pair_remap_note_records_from_to_and_reason():
    """LS: 判型重掷留痕 —— 原判型 K/M12 因契约不可解重掷到 J/M8 后必须可追溯。

    只加记录、不动判型逻辑：remap_note 放短标记（该字段会被家长类启发式扫描），
    原因与 from/to 进结构化键；重复落盘不得叠加标记。
    """
    row = {
        "id": 32,
        "mechanism": "M8",
        "structure_type": "J",
        "payload": {
            "scene_contract": {
                "story_type": "J",
                "beat_chain": [{"beat": 1, "speaker": "昭昭", "intent": "占物挑衅"}],
                "remap_note": "站外角色映射",
            },
            "dialogue_seed": [{"speaker": "昭昭", "intent": "抢笔"}],
        },
    }
    reason = "K_B_DISQUALIFIED：beat 4 孩子对家长的攻击目标：攻击解说员"
    out = gc._stamp_pair_remap_note(
        row,
        from_mechanism="M12",
        from_structure="K",
        reason=reason,
        attempt=2,
    )
    contract = out["payload"]["scene_contract"]
    assert contract["remap_note"] == "站外角色映射；判型重掷 M12+K→M8+J"
    # 短标记不含剧情词，避免被 _contract_has_parent 等启发式误判
    assert "家长" not in contract["remap_note"]
    # 契约其余字段原样保留
    assert contract["beat_chain"] == row["payload"]["scene_contract"]["beat_chain"]
    assert out["payload"]["dialogue_seed"] == row["payload"]["dialogue_seed"]
    remap = out["payload"][gc._GOLD_CHAT_PAIR_REMAP_KEY]
    assert remap["from"] == {"mechanism": "M12", "structure_type": "K"}
    assert remap["to"] == {"mechanism": "M8", "structure_type": "J"}
    assert remap["reason"] == reason
    assert remap["attempt"] == 2
    assert remap["at"]

    again = gc._stamp_pair_remap_note(
        out,
        from_mechanism="M12",
        from_structure="K",
        reason=reason,
        attempt=2,
    )
    assert again["payload"]["scene_contract"]["remap_note"].count("判型重掷") == 1

    # 判型没变就不留痕（正常一次过的稿子不得多出标记）
    same = gc._stamp_pair_remap_note(
        row,
        from_mechanism="M8",
        from_structure="J",
        reason="",
    )
    assert same is row
    assert "判型重掷" not in same["payload"]["scene_contract"]["remap_note"]


def test_convert_persists_pair_remap_note_after_reroll(monkeypatch):
    """LS: 重掷换判型成功落盘时，出来源判型与原因（可追溯，不改判型逻辑）。"""
    from app.services.gold_story.gold_chat.repair import GoldChatRepairExhausted
    from app.repositories import repo_gold_story

    row = _sample_row()
    row["source_id"] = "BV1PAIRREMAP"
    row["id"] = 32
    row["mechanism"] = "M12"
    row["structure_type"] = "K"
    row["payload"]["scene_contract"] = {"story_type": "K", "beat_chain": []}
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)
    monkeypatch.setattr(
        gc, "apply_gold_chat_normalizations", lambda chat, **_kw: (chat, [])
    )
    monkeypatch.setattr(gc, "_refine_after_normalize", lambda chat, _row, **_kw: chat)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda chat, **_kw: (chat, []))
    monkeypatch.setattr(gc, "_attach_retry_missing_events", lambda r, _f: r)

    def _reroll(r, attempt=0):
        out = dict(r)
        out["mechanism"] = "M8"
        out["structure_type"] = "J"
        return out, "M8+J"

    monkeypatch.setattr(gc, "_retry_structure_pair", _reroll)
    monkeypatch.setattr(gc, "gold_story_to_gold_chat", lambda _row, **_kw: _sample_chat())

    finalize_calls: list[int] = []

    def _finalize(chat, _row, **_kw):
        finalize_calls.append(1)
        if len(finalize_calls) == 1:
            raise GoldChatRepairExhausted(
                stage="final_acceptance",
                reason="K_B_DISQUALIFIED：beat 4 孩子对家长的攻击目标：攻击解说员",
                candidate=_sample_chat(),
            )
        return chat, 80

    monkeypatch.setattr(gcf, "run_gold_chat_finalize", _finalize)
    monkeypatch.setattr(gc, "export_gold_chat_files", lambda **_kw: {"json": "x"})
    monkeypatch.setattr(gc, "_backfill_gold_story_after_export", lambda *_a, **_kw: None)

    persisted: dict = {}
    monkeypatch.setattr(
        repo_gold_story,
        "update_mechanism_and_structure",
        lambda gid, **_kw: persisted.setdefault("structure", (gid, _kw)),
    )
    # patch_story_payload 会被多次调用（转换中标记/清标记/判型重掷），逐次记录后再挑
    payload_patches: list[tuple[int, dict]] = []
    monkeypatch.setattr(
        repo_gold_story,
        "patch_story_payload",
        lambda gid, patch: payload_patches.append((gid, patch)),
    )

    result = gc.convert_gold_chat(row)

    assert result["ok"] is True
    assert len(finalize_calls) == 2
    assert persisted["structure"][0] == 32
    assert persisted["structure"][1]["structure_type"] == "J"
    remap_patches = [
        (gid, patch)
        for gid, patch in payload_patches
        if gc._GOLD_CHAT_PAIR_REMAP_KEY in patch
    ]
    assert len(remap_patches) == 1
    gid, patch = remap_patches[0]
    assert gid == 32
    remap = patch[gc._GOLD_CHAT_PAIR_REMAP_KEY]
    assert remap["from"] == {"mechanism": "M12", "structure_type": "K"}
    assert remap["to"] == {"mechanism": "M8", "structure_type": "J"}
    assert "K_B_DISQUALIFIED" in remap["reason"]
    assert patch["scene_contract"]["remap_note"] == "判型重掷 M12+K→M8+J"


class _RetryExc(Exception):
    """模拟终检失败异常：带结构化 issues，供回灌编译测试。"""

    def __init__(self, issues: list[dict]) -> None:
        super().__init__("gold_chat修稿预算耗尽 stage=final_acceptance；终检语义硬伤")
        self.issues = issues


def test_semantic_retry_constraints_compile_and_skip_grammar() -> None:
    exc = _RetryExc(
        [
            {"kind": "矛盾", "text": "第[12]句·矛盾"},
            {"kind": "接不上", "text": "第[13]句·接不上"},
            {"kind": "语病", "text": "第[2]句·语病"},
            {"kind": "重复", "text": "第[3]句·重复"},
        ]
    )
    got = gc._semantic_retry_constraints_from(exc)
    assert got == [
        gc._SEMANTIC_CONSTRAINT_TEMPLATES["矛盾"],
        gc._SEMANTIC_CONSTRAINT_TEMPLATES["接不上"],
    ]


def test_semantic_retry_constraints_dedupe_and_cap() -> None:
    exc = _RetryExc(
        [
            {"kind": "矛盾"},
            {"kind": "矛盾"},
            {"kind": "错位"},
            {"kind": "接不上"},
            {"kind": "引用无据"},
        ]
    )
    got = gc._semantic_retry_constraints_from(exc)
    assert len(got) == gc.SEMANTIC_FEEDBACK_MAX_ITEMS
    assert sum(len(x) for x in got) <= gc.SEMANTIC_FEEDBACK_MAX_CHARS
    assert len(set(got)) == len(got)


def test_semantic_retry_constraints_fall_back_to_error_text() -> None:
    exc = _RetryExc([])
    exc.args = (
        "终检语义硬伤：第[8]句·错位：指代不明；第[9]句·语病：叠语气词",
    )
    got = gc._semantic_retry_constraints_from(exc)
    assert got == [gc._SEMANTIC_CONSTRAINT_TEMPLATES["错位"]]


def test_semantic_retry_constraints_empty_for_pure_grammar() -> None:
    exc = _RetryExc([{"kind": "语病"}, {"kind": "垫字"}])
    assert gc._semantic_retry_constraints_from(exc) == []


def test_attach_retry_semantic_issues_keeps_missing_events() -> None:
    original = {
        "reason": "missing_beat_exhausted",
        "missing_events": [{"original_intent": "爸爸旁观解说"}],
    }
    row = {"gold_chat_retry_feedback": original}
    out = gc._attach_retry_semantic_issues(row, ["甲", "乙"])
    feedback = out["gold_chat_retry_feedback"]
    assert feedback["reason"] == "missing_beat_exhausted"
    assert feedback["missing_events"] == [{"original_intent": "爸爸旁观解说"}]
    assert feedback["semantic_constraints"] == ["甲", "乙"]
    # 原行不被就地改写（重掷失败时库内契约要保持原样）
    assert original.get("semantic_constraints") is None


def test_attach_retry_semantic_issues_noop_without_items() -> None:
    row = {"id": 1}
    assert gc._attach_retry_semantic_issues(row, []) is row


def test_retry_prompt_block_renders_semantic_constraints() -> None:
    from app.services.gold_story.gold_chat.prompts import (
        format_retry_missing_events_block,
    )

    row = {
        "gold_chat_retry_feedback": {
            "reason": "semantic_review_exhausted",
            "semantic_constraints": ["同一角色不得先承认又反口"],
        }
    }
    block = format_retry_missing_events_block(row)
    assert "【上一轮终检问题·勿重复】" in block
    assert "同一角色不得先承认又反口" in block
    assert "已通过的拍及其顺序" in block
    assert "【上一轮缺拍·必须补齐】" not in block


def test_retry_prompt_block_renders_both_channels() -> None:
    from app.services.gold_story.gold_chat.prompts import (
        format_retry_missing_events_block,
    )

    row = {
        "gold_chat_retry_feedback": {
            "reason": "missing_beat_exhausted",
            "missing_events": [{"original_intent": "爸爸旁观解说", "expected_speaker": "爸爸"}],
            "semantic_constraints": ["每句须直接回应上一句"],
        }
    }
    block = format_retry_missing_events_block(row)
    assert "【上一轮缺拍·必须补齐】" in block
    assert "爸爸旁观解说" in block
    assert "【上一轮终检问题·勿重复】" in block
    assert "每句须直接回应上一句" in block


def test_retry_prompt_block_empty_without_feedback() -> None:
    from app.services.gold_story.gold_chat.prompts import (
        format_retry_missing_events_block,
    )

    assert format_retry_missing_events_block({}) == ""
    assert format_retry_missing_events_block(
        {"gold_chat_retry_feedback": {"reason": "semantic_review_exhausted"}}
    ) == ""


def test_single_authoritative_line_length_hint():
    """句长标准只能有一个来源：通用提示词里不许再写死字面区间。"""
    import re

    from app.services.gold_story.gold_chat import prompts as gp

    assert gp.SAFE_LINE_CHARS_LO < gp.SAFE_LINE_CHARS_HI
    assert gp.SAFE_LINE_CHARS_HI <= gp.CHAT_MAX_LINE_CHARS
    hint = gp.SAFE_LINE_CHARS_HINT
    assert str(gp.SAFE_LINE_CHARS_LO) in hint and str(gp.SAFE_LINE_CHARS_HI) in hint

    # 通用系统提示与出场角色块都引用同一口径
    assert hint in gp._SYSTEM
    blk = gp.format_cast_block(
        {
            "characters": ["妈妈", "昭昭", "灿灿"],
            "mom_lines_max": 3,
            "beat_chain": [
                {"beat": 1, "speaker": "妈妈", "intent": "立规"},
                {"beat": 2, "speaker": "昭昭", "intent": "说词"},
                {"beat": 3, "speaker": "灿灿", "intent": "笑一声"},
            ],
        }
    )
    assert hint in blk

    # 通用段落里不得再出现与权威口径不同的字面区间
    # （M8/J 的分拍预算另有机制，允许自己的区间）
    generic = gp._SYSTEM + blk
    for bad in ("16–22 字", "12–18 字"):
        assert bad not in generic, f"通用提示词里仍有旧口径: {bad}"


def test_perbeat_compound_requirements_do_not_replace_mechanism_words():
    slots = gex._perbeat_apply_intent_cover([
        {
            "intent": "追问原因，又补一句妈妈眉清目秀，并说明饺子难吃",
            "function": "推进",
            "must_words": ["为啥", "为什么"],
        },
    ])
    groups = gex._perbeat_required_word_groups(slots[0])

    assert len(groups) == 3
    assert not gex._perbeat_words_ok("为什么今天这么高兴？", groups)
    assert not gex._perbeat_words_ok("为什么妈妈眉清目秀？", groups)
    assert not gex._perbeat_words_ok("妈妈眉清目秀，但饺子难吃。", groups)
    assert gex._perbeat_words_ok("为什么妈妈眉清目秀，但饺子难吃？", groups)


@pytest.mark.parametrize("words", [["为啥", "为什么"], ["因为", "所以"]])
def test_perbeat_legacy_word_list_remains_one_alternative_group(words):
    groups = gex._perbeat_required_word_groups({"must_words": words})
    assert gex._perbeat_words_ok(f"{words[1]}这么说。", groups)
    assert not gex._perbeat_words_ok("今天这件事已经结束。", groups)


def test_perbeat_speech_form_allows_colloquial_kan_retort():
    """「我看你…」是正常回呛，不得按自述动作/旁白误拦。"""
    assert gex._perbeat_speech_form_ok("我看你咋打扰啊，你倒是来啊！", "昭昭")
    assert gex._perbeat_speech_form_ok("我看准软地方才往那边落。", "昭昭")
    # 镜头腔的「看看/盯着」仍按自述动作拦
    assert not gex._perbeat_speech_form_ok(
        "我看看妈妈手里的筷子落不落。", "灿灿"
    )


def test_perbeat_stage_direction_is_rejected_and_cleaned_from_intent():
    from app.services.gold_story.gold_chat.prompts import _perbeat_clean_intent

    assert not gex._perbeat_line_ok(
        "我不是讨好处，一本正经说妈妈像只暴躁老虎。", "昭昭"
    )
    assert not gex._perbeat_line_ok(
        "不慌不忙回老虎一吼公主也得现出原形。", "昭昭"
    )
    assert gex._perbeat_strip_stage_direction(
        "我不是想讨好处，我一本正经说妈妈像暴躁老虎。"
    ) == "我不是想讨好处，妈妈像暴躁老虎。"
    filled = {1: "我不是想讨好处，我一本正经说妈妈像暴躁老虎。"}
    gex._perbeat_validate_fill(
        [_perbeat_test_slot("昭昭", intent="说妈妈像暴躁老虎")], filled
    )
    assert filled[1] == "我不是想讨好处，妈妈像暴躁老虎。"
    cleaned = _perbeat_clean_intent(
        "说自己不是想讨好处，再一本正经说妈妈像一个暴躁的老虎"
    )
    assert "一本正经说" not in cleaned
    assert cleaned.startswith("说自己不是想讨好处")

    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "我筷子停在半空，看着妈妈，这盘饺子没人动了。",
        [],
    )
    assert "不得自述动作/旁白或转述别人的话" in reasons
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "这盘饺子我夹着，可我真接不上昭昭这句话。",
        [],
    )
    assert "不得自述动作/旁白或转述别人的话" in reasons
    assert "插话须有具体内容（不许抽象词）" in reasons
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你这一吼，我筷子都停在半空，实在接不上话了。",
        [("昭昭", "真的，老虎发威的时候可吓人了。")],
    )
    assert "不得自述动作/旁白或转述别人的话" in reasons
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说妈妈眉清目秀，我同意，她今天脸色确实白净。",
        [("昭昭", "这黑面饺子芯子难吃无比，不过妈妈眉清目秀。")],
    )
    assert "插话不得另起上一句没提的新物件细节" in reasons
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说妈妈眉清目秀，我同意，她今早还梳了头。",
        [("昭昭", "这黑面饺子芯子难吃无比，不过妈妈眉清目秀。")],
    )
    assert "插话不得另起上一句没提的新物件细节" in reasons
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说妈妈像老虎，可这盘饺子皮捏得挺老实。",
        [("昭昭", "我不是想讨好处，妈妈像一个暴躁的老虎。")],
    )
    assert "插话不得另起上一句没提的新物件细节" in reasons


def test_perbeat_invalid_middle_filler_is_reordered_without_adjacent_siblings():
    slots = [
        _perbeat_test_slot("妈妈", intent="问饺子先尝一口"),
        _perbeat_test_slot("灿灿", filler=True, intent="说饺子皮厚"),
        _perbeat_test_slot("昭昭", filler=True, intent="说饺子发苦"),
        _perbeat_test_slot("灿灿", filler=True, intent="说饺子芯子发苦"),
        _perbeat_test_slot("昭昭", filler=True, intent="说饺子皮厚芯子苦"),
        _perbeat_test_slot("妈妈", intent="说饺子先搁着"),
    ]
    kept = [
        (1, "这盘黑面饺子刚端上桌，你先尝一口。"),
        (2, "这盘黑面饺子皮厚，我瞧着像鞋底。"),
        (4, "这黑面饺子芯子发苦，你俩还吃得下。"),
        (5, "这饺子皮厚归厚，芯子可真是发苦。"),
        (6, "行了，这盘黑面饺子先搁着，待会儿再说。"),
    ]

    ordered = gex._perbeat_order_kept_slots(slots, kept)

    assert [idx for idx, _line in ordered] == [1, 2, 5, 4, 6]
    speakers = [slots[idx - 1]["speaker"] for idx, _line in ordered]
    assert all(a != b for a, b in zip(speakers, speakers[1:]))


def test_perbeat_filler_may_reprise_current_beat_but_not_later_ones():
    from app.services.gold_story.gold_chat.validate import _beat_chain_entries

    entries = _beat_chain_entries(
        [
            {
                "beat": 2,
                "speaker": "昭昭",
                "intent": "嫌黑面芯子难吃无比，又补一句妈妈眉清目秀",
            },
            {
                "beat": 4,
                "speaker": "昭昭",
                "intent": "一本正经说妈妈像一个暴躁的老虎",
            },
        ]
    )
    slot = _perbeat_test_slot("灿灿", filler=True, intent="接一句")
    slot["beat_id"] = 2
    slot["_beat_entries"] = entries
    reasons = gex._perbeat_check(
        slot,
        "芯子难吃我也吃出来了，可妈妈眉清目秀也没说错。",
        [("昭昭", "这黑面芯子难吃无比，可妈妈眉清目秀真好看。")],
    )
    assert "插话不得顶替契约拍的台词" not in reasons


def test_perbeat_filler_stance_requires_reason():
    prev = [("昭昭", "我不是想讨好处，妈妈像一个暴躁的老虎。")]
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说妈妈像暴躁的老虎，我不同意。",
        prev,
    )
    assert "插话表态须给出理由" in reasons

    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说老虎发威吓人，我同意，可妈妈现在没发威啊。",
        prev,
    )
    assert "插话表态须给出理由" not in reasons


def test_perbeat_filler_cannot_recall_unestablished_event():
    prev = [
        ("昭昭", "我不是想讨好处，妈妈像一个暴躁的老虎。"),
        ("灿灿", "你说妈妈像暴躁的老虎，我不同意。"),
    ]
    reasons = gex._perbeat_check(
        _perbeat_test_slot("昭昭", filler=True, intent="接一句"),
        "真的，老虎发威的时候可吓人了，你刚才也瞧见了吧。",
        prev,
    )
    assert "不得引用前文没发生的事件" in reasons

    reasons = gex._perbeat_check(
        _perbeat_test_slot("昭昭", filler=True, intent="接一句"),
        "真的，老虎发威的时候可吓人了，你刚才也瞧见了吧。",
        prev + [("妈妈", "我刚才发威是我不对，可你也别乱说。")],
    )
    assert "不得引用前文没发生的事件" not in reasons


def test_perbeat_filler_rejects_empty_agreement_and_repeated_move():
    prev = [
        ("昭昭", "黑面芯子难吃无比，不过妈妈眉清目秀挺好看。"),
        ("灿灿", "你说妈妈眉清目秀，我倒是觉得这夸得挺对。"),
    ]
    reasons = gex._perbeat_check(
        _perbeat_test_slot("昭昭", filler=True, intent="接一句"),
        "你说这夸得挺对，那我可就把好话收下了。",
        prev,
    )
    assert "插话不得只附和或收下夸奖" in reasons

    prev = [
        ("昭昭", "真的，老虎发威的时候可吓人了。"),
        ("灿灿", "你说妈妈像暴躁的老虎，我不同意，她刚才没吼人。"),
    ]
    reasons = gex._perbeat_check(
        _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
        "你说老虎发威吓人，我不同意，那回吼的是我。",
        prev,
    )
    assert "同一表态动作不得反复用" in reasons


def test_perbeat_filler_quote_is_judged_by_anchor_not_origin():
    """插话槽不再查「引述出处」，改由「接住上一句」一条兜住（2026-10）。

    两条规则本来互相抵消：要求接住上一句的具体说法，又要求不许复述、引述必须
    有出处，交集的写法必然判废。机检只留 anchor，出处与复述交终检看上下文。
    """
    prev = [("昭昭", "我不是想讨好处，妈妈像暴躁老虎。")]
    for line in (
        "你说老虎发威吓人，我不同意，妈妈没冲你吼过。",
        "你说妈妈像暴躁的老虎，我不同意，她刚才没吼人。",
    ):
        reasons = gex._perbeat_check(
            _perbeat_test_slot("灿灿", filler=True, intent="接一句"),
            line,
            prev,
        )
        assert "引述上一句时必须真有出处" not in reasons


def test_perbeat_duplicate_phrase_blocks_contract_not_filler():
    """复述判定只对契约拍生效；插话槽交给终检（2026-10）。

    插话槽的职责就是咬住上一句，机检再判它复述等于自己打自己。
    """
    prev = [
        ("妈妈", "昭昭，这盘黑面饺子刚端上来，你尝尝好不好吃？"),
        ("昭昭", "黑面饺子芯子难吃无比，可妈妈眉清目秀真好看。"),
        ("灿灿", "芯子难吃我也吃出来了，可妈妈听了准高兴。"),
    ]
    near_verbatim = "黑面饺子芯子难吃无比，妈妈眉清目秀真好看。"
    filler_reasons = gex._perbeat_check(
        _perbeat_test_slot("昭昭", filler=True, intent="接夸奖"),
        near_verbatim,
        prev,
    )
    assert not any("复述" in r for r in filler_reasons)

    contract_reasons = gex._perbeat_check(
        _perbeat_test_slot("昭昭", intent="接夸奖"),
        near_verbatim,
        prev,
    )
    assert any("复述" in r for r in contract_reasons)


def test_perbeat_repair_checks_quote_after_reorder():
    items = [
        (3, "灿灿", "你说老虎发威吓人，我不同意，那得先有老虎才行。"),
        (4, "昭昭", "真的，老虎发威的时候可吓人了。"),
    ]
    chosen = gex._perbeat_choose_filler_order(
        items,
        prev_speaker="昭昭",
        prev_line="我不是讨好处，妈妈像暴躁的老虎。",
        next_speaker="妈妈",
    )
    assert chosen == []


def test_perbeat_seed_already_covered_by_contract_is_not_reused_as_filler():
    beats = [
        {
            "speaker": "昭昭",
            "intent": "嫌黑面芯子难吃无比，又补一句妈妈眉清目秀",
        }
    ]
    seed = [
        {"speaker": "昭昭", "intent": "不过我妈妈倒是眉清目秀的"},
        {"speaker": "灿灿", "intent": "昭昭你这话我可接不住"},
    ]

    queues = gex._perbeat_seed_queues(seed, beats=beats)

    assert queues.get("昭昭", []) == []
    assert queues.get("灿灿") == ["昭昭你这话我可接不住"]


def test_perbeat_prompt_keeps_independent_requirement_groups_and_retry_feedback():
    from app.services.gold_story.gold_chat.prompts import format_perbeat_user

    prompt = format_perbeat_user(
        scene_contract={}, punchline="", prev_lines=[], speaker="昭昭",
        intent="解释", function="推进", beat_id=1, beat_count=1,
        used_details=[], required_word_groups=[["因为", "所以"], ["清秀"]],
        upcoming=[(2, "妈妈", "收束")], retry_feedback="上次漏掉夸奖，请重写。",
    )
    assert "第1组：因为/所以" in prompt
    assert "第2组：清秀" in prompt
    assert "组须全部满足" in prompt
    assert "上次漏掉夸奖，请重写。" in prompt
    assert "拍2 妈妈：收束" in prompt


def _stub_perbeat_generation(monkeypatch, slots, candidate_batches):
    """只替换模型和最终整稿校验，保留逐拍候选的真实筛选。"""
    users = []
    responses = iter(candidate_batches)
    monkeypatch.delenv("GOLD_CHAT_DEBUG_DUMP", raising=False)
    monkeypatch.setattr(gex, "_perbeat_slots", lambda *_a, **_k: slots)
    monkeypatch.setattr(gex, "_validate_expand_chat", lambda chat, **_k: chat)

    def generate(_system, user, **_kwargs):
        users.append(user)
        lines = next(responses)
        return {
            "lines": [
                {"i": i, "line": line}
                for i, line in enumerate(lines[: len(slots)], 1)
            ]
        }

    monkeypatch.setattr(gex, "_chat_json", generate)
    return users


def _perbeat_test_slot(speaker="昭昭", *, filler=False, intent="陈述"):
    return {
        "beat_id": 1, "speaker": speaker, "intent": intent,
        "function": "推进", "is_filler": filler,
    }


def test_perbeat_label_intent_does_not_require_literal_overlap():
    """#144：11 号位 intent 是「连声道歉」，台词无法逐字复述。"""
    assert not gex._perbeat_intent_has_literal_anchor("连声道歉")
    assert not gex._perbeat_intent_has_literal_anchor(
        "小嘴一撇，嘟囔一句听不清的话，神情还没消气"
    )
    assert not gex._perbeat_intent_has_literal_anchor("接不上话，愣住看妈妈")
    assert gex._perbeat_intent_has_literal_anchor("大声骂昭昭弄脏衣服，并说“傻”")
    # 4 字以上能说明交代什么（「追问原因」）仍按实词核，不能借标签跳过。
    assert gex._perbeat_intent_has_literal_anchor("追问原因")
    # 舞台提示里带着疑问词的，仍算有可念的内容（「追问为什么…」）。
    assert gex._perbeat_intent_has_literal_anchor(
        "追问妈妈一胎时为什么买这么多，是不是天天查书"
    )
    assert not gex._perbeat_performative_line_ok("连声道歉", "这盘饺子真好吃。")
    assert gex._perbeat_performative_line_ok("连声道歉", "你先道歉！")

    reasons = gex._perbeat_check(
        _perbeat_test_slot("妈妈", intent="连声道歉"),
        "对不起，是妈妈不对，不该大声骂你，也不该说你傻。",
        [("昭昭", "那你为什么要说傻呢？")],
    )
    assert not any("必须落地本拍" in reason for reason in reasons)


def test_perbeat_contract_line_passes_when_downstream_beat_accepts_it():
    """#144：1 号位「你把衣服弄这么脏」下游认 blame，逐拍不能更严。"""
    from app.services.gold_story.gold_chat.validate import _beat_chain_entries

    slot = _perbeat_test_slot(
        "妈妈", intent="大声骂昭昭弄脏衣服，并说“傻”"
    )
    slot["_own_entry"] = _beat_chain_entries(
        [{"beat": 1, "speaker": "妈妈", "intent": "大声骂昭昭弄脏衣服，并说“傻”"}]
    )[0][1]
    reasons = gex._perbeat_check(
        slot, "你把衣服弄这么脏，真是个傻孩子！", []
    )
    assert not any("必须落地本拍" in reason for reason in reasons)


def test_perbeat_followup_question_may_reuse_earlier_words():
    """#144：追问句（「疼我为什么大声骂我」）不算换词复述。"""
    prev = [
        ("妈妈", "你把衣服弄这么脏，真是个傻孩子！"),
        ("昭昭", "你为什么因为衣服脏了就大声骂我傻？"),
        ("妈妈", "我大声骂你，是因为你把衣服弄脏了呀。"),
        ("灿灿", "你先别急，慢慢说，我们都听着呢。"),
    ]
    slot = _perbeat_test_slot(
        "妈妈", intent="愣住后追问：疼我为什么大声骂我、说我傻"
    )
    reasons = gex._perbeat_check(slot, "疼我为什么大声骂我、说我傻？", prev)
    assert not any("不得复述前文" in reason for reason in reasons)
    # 陈述式的原地重复仍要拦。
    plain = gex._perbeat_check(
        slot, "我大声骂你就是因为你把衣服弄脏了呀。", prev
    )
    assert "不得复述前文" in plain


def test_perbeat_statement_ending_in_ne_is_not_a_question():
    """「我还没消气呢」是陈述；「那你为什么要说傻呢？」才是提问。"""
    assert not gex._perbeat_is_question("我……我还没消气呢。")
    assert gex._perbeat_is_question("那你为什么要说傻呢？")
    assert gex._perbeat_is_question("我晚上吃什么呢。")
    assert gex._perbeat_is_question("那你呢。")


def _perbeat_filler_slot_with_owner(
    *,
    speaker="灿灿",
    owner="昭昭",
    beat_id=5,
    intent="接住上一句里最具体的那半句，说明你为什么同意或不同意",
    owner_intent=(
        "先直接回答上一句问的问题，先承认衣服是自己弄脏的，"
        "再说想自己弄干净、不让妈妈操心，因为疼妈妈"
    ),
):
    return {
        "beat_id": beat_id,
        "speaker": speaker,
        "intent": intent,
        "function": "反应/插话",
        "is_filler": True,
        "_beat_entries": [
            (beat_id, {"beat": beat_id, "speaker": owner, "intent": owner_intent})
        ],
    }


def test_perbeat_required_semantic_points_must_land():
    """#144 run25 第6句：契约声明「疼妈妈」必现，丢了就判废。

    丢「疼妈妈」会连带第8句妈妈的「你疼妈妈」失去前提，终检判缺前提、
    修稿预算直接被耗尽——所以在逐拍机检就拦住。
    """
    slot = {
        "beat_id": 5,
        "speaker": "昭昭",
        "intent": "先承认衣服是自己弄脏的，再说想自己弄干净，因为疼妈妈",
        "function": "本拍主句",
        "is_filler": False,
        "_own_entry": {
            "beat": 5,
            "speaker": "昭昭",
            "intent": "先承认衣服是自己弄脏的，再说想自己弄干净，因为疼妈妈",
            "required_semantic_points": [
                {"surface": "疼妈妈", "synonyms": ["疼你", "心疼你"]}
            ],
        },
    }
    prev = [("妈妈", "你是不是弄脏了衣服？弄脏谁的衣服？")]
    dropped = gex._perbeat_check(
        slot, "衣服是我弄脏的，可我说想自己弄干净。", prev
    )
    assert any("必现语义点" in item for item in dropped), dropped

    landed = gex._perbeat_check(
        slot, "衣服是我弄脏的，我想自己弄干净，因为疼你。", prev
    )
    assert not landed, landed

    # 否定式提及不算落地（「我不疼你了」不是「疼你」）。
    negated = gex._perbeat_check(
        slot, "衣服是我弄脏的，我不疼你了，我自己弄干净。", prev
    )
    assert any("必现语义点" in item for item in negated), negated


def test_perbeat_zero_content_filler_addressee_must_match_previous_line():
    """#144 run25 第4句：上一句是灿灿劝昭昭，补位句却喊「妈」，终检判错位。"""
    slot = _perbeat_filler_slot_with_owner(
        speaker="昭昭", owner="灿灿", beat_id=3
    )
    slot["has_content"] = False
    prev = [("灿灿", "你慢慢说，别急着吼，先把话讲清楚。")]

    wrong = gex._perbeat_check(
        slot, "妈你先别急，慢慢说，把话交给你自己说清楚。", prev
    )
    assert any("呼语" in item for item in wrong), wrong

    right = gex._perbeat_check(
        slot, "灿灿，你先别急，我就在旁边听着。", prev
    )
    assert not any("呼语" in item for item in right), right

    # 没有显式呼语时一律不判（避免误伤正常递话）。
    implicit = gex._perbeat_check(
        slot, "你先别急，我就在旁边听着，慢慢说。", prev
    )
    assert not any("呼语" in item for item in implicit), implicit


def test_perbeat_required_semantic_points_reach_batch_prompt():
    """必现语义点必须写进分配表：模型不知道哪些词不能砍，就会砍掉句尾那个。"""
    from app.services.gold_story.gold_chat.prompts import (
        format_perbeat_batch_user,
    )

    slots = [
        {
            "beat_id": 5,
            "speaker": "昭昭",
            "intent": "先承认衣服是自己弄脏的，再说想自己弄干净，因为疼妈妈",
            "function": "本拍主句",
            "is_filler": False,
        }
    ]
    beats = [
        {
            "beat": 5,
            "speaker": "昭昭",
            "intent": "先承认衣服是自己弄脏的，再说想自己弄干净，因为疼妈妈",
            "required_semantic_points": [
                {"surface": "疼妈妈", "synonyms": ["疼你"]}
            ],
        }
    ]
    filled = gex._apply_required_semantic_points(slots, beats)
    assert filled[0]["required_semantic_terms"] == [["疼妈妈", "疼你"]]

    prompt = format_perbeat_batch_user(
        scene_contract={"characters": ["妈妈", "昭昭"]},
        punchline="",
        slots=filled,
    )
    assert "必现（缺一不可）：疼妈妈或疼你" in prompt


def test_perbeat_nonverbal_beat_uses_closed_template_pool():
    """#144 run25 第12句：静场/嘟囔拍不自由命题，只取封闭模板里的含糊收束句。"""
    slot = {
        "beat_id": 9,
        "speaker": "昭昭",
        "intent": "小嘴一撇，嘟囔一句听不清的话，神情还没消气",
        "function": "本拍主句",
        "is_filler": False,
        "_own_entry": {"beat": 9, "speaker": "昭昭", "beat_type": "nonverbal"},
    }
    prev = [("妈妈", "对不起，是妈妈错了。")]
    line = gex._perbeat_nonverbal_line(slot, prev)
    assert line, "封闭模板池必须至少给出一句能过机检的收束句"
    assert not gex._perbeat_check(slot, line, prev)
    assert gex._perbeat_is_nonverbal_beat(slot["_own_entry"])
    assert not gex._perbeat_is_nonverbal_beat({"beat": 9, "speaker": "昭昭"})


def test_perbeat_filler_copying_adjacent_line_is_blocked():
    """#144：插话照抄紧邻上一句（逐字或十几字长片段）要硬拦。

    专家评审：插话共享一两词是要求，抄一整段不是；只比紧邻上一句，
    避免和「必须接住上一句的具体说法」叠加成互斥规则。
    """
    verbatim = gex._perbeat_check(
        _perbeat_filler_slot_with_owner(beat_id=7),
        "弄了衣服是傻？那你为什么要说傻呢？",
        [("昭昭", "弄了衣服是傻？那你为什么要说傻呢？")],
    )
    assert "插话不得照抄上一句" in verbatim

    long_copy = gex._perbeat_check(
        _perbeat_filler_slot_with_owner(beat_id=5),
        "说想自己弄干净，不让妈妈操心，因为疼妈妈。",
        [("昭昭", "是我弄脏的，我说想自己弄干净，不让妈妈操心。")],
    )
    assert "插话不得照抄上一句" in long_copy

    # 只共享固定短语（「弄干净」）的正常承接不算照抄。
    short_share = gex._perbeat_check(
        _perbeat_filler_slot_with_owner(beat_id=5),
        "你先别急，慢慢弄干净就好。",
        [("昭昭", "是我弄脏的，我说想自己弄干净，不让妈妈操心。")],
    )
    assert "插话不得照抄上一句" not in short_share


def test_perbeat_filler_claiming_owner_event_is_blocked():
    """#144：旁观者用第一人称认领拍主的事实/委屈要拦，帮忙和安抚要放过。"""
    prev = [("昭昭", "是我弄脏的，我说想自己弄干净，不让妈妈操心。")]
    claim = gex._perbeat_check(
        _perbeat_filler_slot_with_owner(beat_id=5),
        "反正我没错，你不该那样说我。",
        prev,
    )
    assert "插话不得认领拍主的事实/动机" in claim

    # 帮忙框架、否定安抚（专家给的回归句）必须放过。
    for line in (
        "你先别急，我就在旁边听着，你慢慢说。",
        "我帮你拿抹布，你别自己逞强。",
        "我帮你弄干净，你别自己逞强。",
        "我没说你委屈，你先别哭。",
    ):
        reasons = gex._perbeat_check(
            _perbeat_filler_slot_with_owner(beat_id=5), line, prev
        )
        assert "插话不得认领拍主的事实/动机" not in reasons, line

    # 拍主自己说自己的事不算认领。
    own = gex._perbeat_check(
        _perbeat_filler_slot_with_owner(speaker="昭昭", owner="昭昭", beat_id=5),
        "是我弄脏的，我想自己弄干净。",
        prev,
    )
    assert "插话不得认领拍主的事实/动机" not in own


def test_perbeat_party_filler_not_blocked_as_claiming_owner_event():
    """#149：当事人孩子接话/拆句用「我」说本拍的事，不算认领旁观对象的事。"""
    slot = _perbeat_filler_slot_with_owner(
        speaker="昭昭",
        owner="灿灿",
        beat_id=3,
        intent="喊妈妈救命，说姐姐还在挠",
        owner_intent="把昭昭按在炕上，昭昭喊妈妈救我，灿灿趁机又挠两下",
    )
    slot["has_content"] = True
    reasons = gex._perbeat_check(
        slot,
        "妈妈你看她又挠我两下，我手都腾不出来！",
        [("灿灿", "我就挠你两下怎么了。")],
    )
    assert "插话不得认领拍主的事实/动机" not in reasons


def test_perbeat_zero_content_filler_relaxed_but_still_blocks_copying():
    """#144：无素材插话槽只做旁观/递话，不要求给理由；照抄/认领/纯附和照样拦。

    #154 之后的口径反转：has_content=False 的插话槽也必须接住上一句。
    旧口径放行「先别急/慢慢说/把话交回给他」，终检会判接不上/错位/旁白
    （单条驳回率最高），故不再放行安抚/催促/递话；照抄、认领、纯附和照样拦。
    """
    slot = _perbeat_filler_slot_with_owner(beat_id=5)
    slot["has_content"] = False
    prev = [("昭昭", "是我弄脏的，说想自己弄干净，不让妈妈操心。")]
    pacify = gex._perbeat_check(
        slot, "昭昭，你先别急，我就在旁边听着，你慢慢说。", prev
    )
    assert any("须接住上一句" in item for item in pacify), pacify
    copy = gex._perbeat_check(slot, "她想自己弄干净，不让妈妈操心。", prev)
    assert "插话不得照抄上一句" in copy
    claim = gex._perbeat_check(slot, "反正我没错，你不该那样说我。", prev)
    assert "插话不得认领拍主的事实/动机" in claim
    assert gex._perbeat_check(slot, "嗯，是啊，你说得对。", prev)


def test_perbeat_zero_content_filler_template_pool_is_compliant():
    """补位链的兜底：模板池取出的旁观句必须自己就能过机检。"""
    slot = _perbeat_filler_slot_with_owner(beat_id=5)
    slot["has_content"] = False
    prev = [("昭昭", "是我弄脏的，说想自己弄干净，不让妈妈操心。")]
    line = gex._perbeat_filler_template(slot, prev)
    assert line
    assert not gex._perbeat_check(slot, line, prev)


def test_perbeat_filler_slots_without_seed_use_function_intent():
    """#144：无素材插话槽改走旁观/递话功能，不再要「接住最具体半句 + 给理由」。"""
    beats = [
        {
            "beat": i,
            "speaker": "妈妈" if i % 2 else "昭昭",
            "intent": f"第{i}拍要交代的具体事情",
        }
        for i in range(1, 10)
    ]
    contract = {
        "characters": ["妈妈", "昭昭", "灿灿"],
        "object": "衣服",
        "location": "家里",
        "conflict": "妈妈骂昭昭弄脏衣服",
        "beat_chain": beats,
    }
    slots = gex._perbeat_slots(beats, contract, target_lines=12, seed=[])
    fillers = [s for s in slots if s.get("is_filler")]
    assert fillers
    for slot in fillers:
        assert slot.get("has_content") is False
        assert "接住上一句里最具体的那半句" not in str(slot.get("intent"))


def test_perbeat_overlong_candidate_is_rewritten_without_truncating_required_tail(monkeypatch):
    slot = _perbeat_test_slot(intent="说饺子难吃但妈妈眉清目秀")
    slot["must_words"] = ["清秀"]
    long_line = "这盘饺子苦得我实在有点吃不下去，可妈妈眉眼依然清秀。"
    valid_line = "这盘饺子实在难吃，可妈妈眉眼倒清秀。"
    users = _stub_perbeat_generation(
        monkeypatch, [slot], [[long_line], [valid_line]],
    )

    result = gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])

    assert result["dialogue"] == [{"speaker": "昭昭", "line": valid_line}]
    assert len(users) == 2
    assert long_line in users[1]
    assert "须 8–24 字且是完整句" in users[1]


def test_perbeat_prompt_consumes_previous_semantic_review_feedback(monkeypatch):
    slot = _perbeat_test_slot("昭昭", intent="说老虎一吼公主也得让路")
    users = _stub_perbeat_generation(
        monkeypatch, [slot], [["真的，老虎一吼，公主也得先让路。"]],
    )
    row = {
        "gold_chat_retry_feedback": {
            "semantic_constraints": ["每句须直接回应上一句的问/答/挑衅，不得答非所问"]
        }
    }

    gex._generate_perbeat_candidate(
        scene_contract={}, beat_chain=[], row=row,
    )

    assert "【上一轮终检问题·勿重复】" in users[0]
    assert "不得答非所问" in users[0]


@pytest.mark.parametrize("filler", [False, True])
def test_perbeat_invalid_candidates_are_never_kept_as_fallback(monkeypatch, filler):
    slot = _perbeat_test_slot(filler=filler)
    users = _stub_perbeat_generation(
        monkeypatch, [slot], [["太苦了。"]] * 3,
    )

    if filler:
        result = gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])
        assert result["dialogue"] == []
    else:
        with pytest.raises(ValueError, match="line\\(s\\) invalid"):
            gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])
    assert len(users) == 3


@pytest.mark.parametrize("filler", [False, True])
def test_perbeat_unrelated_candidate_cannot_bypass_anchor_via_scene_word_or_fallback(
    monkeypatch, filler,
):
    slots = [
        _perbeat_test_slot("妈妈", intent="说汤太烫，先放一会儿再喝"),
        _perbeat_test_slot(filler=filler, intent="追问原因"),
    ]
    # 新现场词也不能冒充承接上句；原实现会从 soft/fallback 放行。
    slots[1]["topic_terms"] = ["盘子"]
    users = _stub_perbeat_generation(
        monkeypatch, slots,
        [
            ["这碗汤太烫了，先放一会儿再喝。", "盘子边上留着一双筷子，先拿过来。"],
            ["这碗汤太烫了，先放一会儿再喝。", "盘子边上留着一双筷子，先拿过来。"],
            ["这碗汤太烫了，先放一会儿再喝。", "盘子边上留着一双筷子，先拿过来。"],
        ],
    )

    if filler:
        result = gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])
        assert len(result["dialogue"]) == 1
        assert "必须接住上一句的具体说法" in users[-1]
    else:
        with pytest.raises(ValueError, match="line\\(s\\) invalid"):
            gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])
        assert "必须落地本拍要交代的内容" in users[-1]


def test_perbeat_question_cannot_be_answered_with_another_question_via_fallback(monkeypatch):
    slots = [
        _perbeat_test_slot("妈妈", intent="问汤先尝尝再说味道"),
        _perbeat_test_slot(intent="回答放了多少盐"),
    ]
    bad_answer = "这碗汤放了多少盐，你自己尝过了吗？"
    users = _stub_perbeat_generation(
        monkeypatch, slots,
        [
            ["今天这碗汤你先尝尝，再说味道怎么样？", bad_answer],
            ["今天这碗汤你先尝尝，再说味道怎么样？", bad_answer],
            ["今天这碗汤你先尝尝，再说味道怎么样？", bad_answer],
        ],
    )
    with pytest.raises(ValueError, match="line\\(s\\) invalid"):
        gex._generate_perbeat_candidate(scene_contract={}, beat_chain=[])
    assert "必须先正面回答上一句的问题" in users[-1]


def test_refine_repair_keeps_opening_patch_when_llm_candidate_shrinks():
    from app.services.gold_story.gold_chat.refine import (
        _stabilize_refine_repair_candidate,
    )

    chain = [
        {
            "beat": 1,
            "speaker": "妈妈",
            "intent": "大声骂昭昭弄脏衣服，并说“傻”",
        },
        {"beat": 2, "speaker": "昭昭", "intent": "反问妈妈为什么大声骂自己"},
    ]
    baseline = {
        "dialogue": [
            {"speaker": "昭昭", "line": "你为什么要大声骂我？就吃早餐的时候呢。"},
            {"speaker": "妈妈", "line": "你看你，吃个早餐都能把衣服弄成这样，傻不傻！"},
            {"speaker": "昭昭", "line": "你骂我傻，这总得有个说法吧？"},
            {"speaker": "妈妈", "line": "好，对不起，妈妈不该大声。那咱讲道理行吗？"},
            {"speaker": "妈妈", "line": "你说，你是不是把衣服弄脏了？弄脏的是谁的衣服？"},
            {"speaker": "昭昭", "line": "是我弄脏的，弄脏的是我自己的衣服呀。"},
            {"speaker": "昭昭", "line": "我疼你，才想自己弄干净，不让你操心。"},
            {"speaker": "妈妈", "line": "你疼妈妈，妈妈为什么还大声骂你、说你傻？"},
            {"speaker": "昭昭", "line": "弄了衣服就是傻吗？那你为什么说我傻呢？"},
            {"speaker": "昭昭", "line": "我是不小心的，你总得把话说清楚。"},
            {"speaker": "妈妈", "line": "对不起，是妈妈不对，不该说你傻。"},
            {"speaker": "昭昭", "line": "你说了对不起，可我心里还没消气呢。"},
            {"speaker": "妈妈", "line": "还没消气？那妈妈再好好跟你说。"},
        ],
    }
    short_candidate = {
        "dialogue": [
            {"speaker": "妈妈", "line": "你看你，衣服弄成这样，傻不傻！"},
            {"speaker": "昭昭", "line": "你为什么要大声骂我？"},
            {"speaker": "灿灿", "line": "嗯。"},
            {"speaker": "妈妈", "line": "对不起，是妈妈不对。"},
        ],
    }
    out = _stabilize_refine_repair_candidate(
        baseline,
        short_candidate,
        structure_type="I",
        beat_chain=chain,
        mom_lines_max=4,
        dialogue_seed=None,
    )
    assert sum(len(x["line"]) for x in out["dialogue"]) >= sum(
        len(x["line"]) for x in baseline["dialogue"]
    )
    assert out["dialogue"][0]["speaker"] == "妈妈"
    assert "衣服" in out["dialogue"][0]["line"]


def test_filler_may_not_speak_for_its_own_beat_owner():
    """插话排在拍主之前时，不许替拍主把本拍的话说完（2026-10）。

    `_line_fulfills_beat` 第一条就要求说话人等于本拍 speaker，插话替拍主办事
    时它永远 False，等于没拦；结果是「妈妈该说的『改口祝我像公主』被灿灿说了」，
    终检判「错位：核心反应被换人」。
    """
    from app.services.gold_story.gold_chat.expand import _filler_takes_over_beat

    entry = {"intent": "气笑要求改口祝妈妈像一个公主"}
    assert _filler_takes_over_beat("改口嘛，说妈妈像公主不就是了", entry) is True
    assert _filler_takes_over_beat("行行行，我夸妈妈像公主", entry) is True
    # 正常接话：只接情绪/态度，不带本拍要交代的内容
    assert _filler_takes_over_beat("昭昭你这不是夸，是拐着弯说妈妈凶", entry) is False
    assert _filler_takes_over_beat("灿灿你别插嘴，让昭昭自己说", entry) is False


def _perbeat_sulk_closing_slot() -> dict:
    """「赢了但没消气」的收束拍（#144 beat9 的契约形状）。"""
    return {
        "speaker": "昭昭",
        "intent": "小嘴一撇，嘟囔一句听不清的话，神情还没消气",
        "is_filler": False,
        "_is_closing": True,
        "_own_entry": {
            "speaker": "昭昭",
            "beat_type": "nonverbal",
            "coherence_exempt": True,
            "intent": "小嘴一撇，嘟囔一句听不清的话，神情还没消气",
        },
        "_beat_entries": [],
    }


def test_perbeat_sulk_closing_template_keeps_grudge_and_anchors_prev():
    """未消气的收束句：保留反差，且与上一句（道歉句）有实词交集。

    终检判「接不上」的硬判据是回句与上一句一个双字词都不共享；同时收束句
    不许写成完全满意，否则反差余味丢失（#144 run27 实测好笑分 8）。
    """
    prev = [("妈妈", "对不起昭昭，是妈妈不对，妈妈不该说你傻。")]
    line = gex._perbeat_nonverbal_line(_perbeat_sulk_closing_slot(), prev)
    assert line
    assert gex.closing_accept_marker(line) == ""
    assert gex._perbeat_terms(line) & gex._perbeat_terms(prev[0][1])
    assert not gex._perbeat_check(_perbeat_sulk_closing_slot(), line, prev)


def test_perbeat_sulk_closing_rejects_satisfied_ending():
    """「这还差不多」把未消气收成完全满意，机检必须判废。"""
    prev = [("妈妈", "对不起昭昭，是妈妈不对，妈妈不该说你傻。")]
    reasons = gex._perbeat_check(
        _perbeat_sulk_closing_slot(), "哼，这还差不多。", prev
    )
    assert "未消气的收束不得写成完全满意" in reasons


def test_perbeat_filler_cannot_repeat_same_pacify_move():
    """三句旁观补位全是「你先别急/慢慢说」时，后一句必须判废。"""
    slot = _perbeat_filler_slot_with_owner(beat_id=5)
    slot["has_content"] = False
    prev = [("灿灿", "你慢慢说，别急，先听昭昭把话讲完。")]
    reasons = gex._perbeat_check(
        slot, "昭昭，你先别急，我就在旁边听着，你慢慢说。", prev
    )
    assert "补位句不得重复同一套安抚说法" in reasons


def test_perbeat_filler_template_picks_a_different_move():
    """模板兜底也要换功能：前文已经劝过「慢慢说」，不能再给同一套安抚句。"""
    slot = _perbeat_filler_slot_with_owner(beat_id=5)
    slot["has_content"] = False
    prev = [
        ("妈妈", "昭昭你看你衣服脏成这样，你可真傻！"),
        ("昭昭", "妈你干嘛这么大声骂我，我哪里傻了？"),
        ("灿灿", "你慢慢说，别急，先听昭昭把话讲完。"),
        ("昭昭", "妈你先别急，我听着。"),
    ]
    line = gex._perbeat_filler_template(slot, prev)
    assert line
    assert not gex._perbeat_check(slot, line, prev)
    assert "慢慢说" not in line


def test_party_filler_must_not_pacify_or_preempt_own_beat():
    """#144 第4句：昭昭的补位句劝灿灿「你别急」，还提前说掉第5/6拍的事实。

    当事人补位句只能表态/顶一句：不许劝上一句的围观者别急（安抚对象错位），
    也不许把后面自己那拍要交代的事实先说掉（否则妈妈只能重复追问、
    昭昭只能重复回答，同一事实被念三遍）。
    """
    owner_intent = (
        "先直接回答上一句问的问题（点出具体答案，别绕开），先承认衣服是自己弄脏的，"
        "再说想自己弄干净，因为疼妈妈"
    )
    slot = _perbeat_filler_slot_with_owner(
        speaker="昭昭",
        owner="昭昭",
        beat_id=3,
        intent="当事人在场反应：只回一句态度，不许提前交代本拍的事实",
        owner_intent=owner_intent,
    )
    slot["_next_party_terms"] = sorted(gex._perbeat_terms(owner_intent))
    prev = [
        ("妈妈", "你把衣服弄这么脏，真是傻，傻得没边了！"),
        ("昭昭", "你为什么这么大声骂我，还说我傻呢？"),
        ("灿灿", "你慢慢说，别急，把话都说清楚。"),
    ]
    reasons = gex._perbeat_check(
        slot, "衣服是我弄脏的，我不是故意，你别急。", prev
    )
    assert "当事人补位句不许提前说掉本拍的事实" in reasons


def test_witness_without_speech_act_is_not_a_party():
    """只说过一句旁观话、没有 speech_act 的角色仍是旁观者（#144 灿灿）。

    按「说过话」算当事人，旁观者补位就享受不到「零素材插话」的放宽口径，
    终检只能反复判「703 旁观者用第一人称认领当事人委屈」。
    """
    entries = [
        (1, {"beat": 1, "speaker": "妈妈", "intent": "骂人", "speech_act": "accuse"}),
        (3, {"beat": 3, "speaker": "灿灿", "intent": "我就在旁边听着，你慢慢说。"}),
        (5, {"beat": 5, "speaker": "昭昭", "intent": "承认", "speech_act": "admit"}),
    ]
    slot = {
        "beat_id": 4,
        "speaker": "昭昭",
        "intent": "当事人在场反应",
        "is_filler": True,
        "_beat_entries": entries,
    }
    assert gex._perbeat_parties(slot) == {"妈妈", "昭昭"}
    witness_slot = dict(slot, speaker="灿灿")
    assert gex._perbeat_filler_is_witness(witness_slot) is True
    assert gex._perbeat_filler_is_witness(slot) is False


def test_party_filler_intent_drops_witness_function():
    """「只做旁观安抚」这种旁观功能不能派给当事人。"""
    intent = "只做旁观安抚：让上一句的说话人先别急、慢慢说、把话说完"
    assert gex._perbeat_party_filler_intent(intent) == gex._PARTY_FILLER_INTENT
    own = "先把话顶回去，别认输"
    assert "当事人" in gex._perbeat_party_filler_intent(own)


def test_semantic_repair_cannot_flatten_sulk_closing():
    """终检修稿把「还没消气」改成「这还差不多」时，极性守卫回退该行。"""
    rows = [
        {"speaker": "妈妈", "line": "对不起昭昭，是妈妈不对，妈妈不该说你傻。"},
        {"speaker": "昭昭", "line": "妈妈现在说对不起，可我心里那根刺还没拔出来。"},
    ]
    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "连声道歉", "speech_act": "admit"},
        {
            "beat": 2,
            "speaker": "昭昭",
            "beat_type": "nonverbal",
            "coherence_exempt": True,
            "intent": "小嘴一撇，嘟囔一句听不清的话，神情还没消气",
        },
    ]
    original = {"dialogue": [dict(r) for r in rows], "gold_beat_chain": chain}
    lifted = {
        "dialogue": [
            dict(rows[0]),
            {"speaker": "昭昭", "line": "哼，这还差不多。"},
        ],
        "gold_beat_chain": chain,
    }
    out, changed = gcf._sanitize_semantic_scoped_repair(
        original,
        lifted,
        target_lines={2},
        st_final="",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert out["dialogue"][-1]["line"] == rows[1]["line"]


def test_reroll_keeps_source_beat_readonly(monkeypatch):
    """重掷判型不许改写源稿拍摘要（#154）。

    payload.beat 同时是终验契约的绑定项（review_contract.source_beat）和导出文件
    gold_meta.beat 的来源。重掷把 H3 重判的拍列表写回去，会让已导出的终验摘要
    与库内记录对不上，导入一律判「正文或审核契约已改动」→ review_pending。
    """
    from app.services.gold_story.collect import llm as collect_llm

    row = _sample_row()
    row["mechanism"] = "M4"
    row["structure_type"] = "G"
    original_beat = list(row["payload"]["beat"])

    monkeypatch.setattr(
        collect_llm,
        "structurize_story",
        lambda **_kw: {
            "title": "测试标题",
            "mechanism": "M8",
            "structure_type": "J",
            "beat": ["重掷拍一", "重掷拍二", "重掷拍三"],
            "structure_mapping_note": "",
            "structure_confidence": 0.9,
        },
    )

    out, pair = gc._reroll_h3_on_retry(row)

    assert out["payload"]["beat"] == original_beat
    assert row["payload"]["beat"] == original_beat
    assert pair


@pytest.mark.parametrize("suffix", ["json", "md"])
def test_export_staging_failure_preserves_complete_previous_version(tmp_path, monkeypatch, suffix):
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    row = _sample_row()
    old = _sample_chat()
    paths = gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=old)
    old_json = Path(paths["json"]).read_bytes()
    old_md = Path(paths["markdown"]).read_bytes()
    original = Path.write_text
    def fail(path, *args, **kwargs):
        if path.suffix == "." + suffix:
            raise OSError("injected write failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail)
    changed = {**old, "scene_title": "new version"}
    with pytest.raises(OSError):
        gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=changed)
    assert (tmp_path / (row["source_id"] + ".json")).read_bytes() == old_json
    assert (tmp_path / (row["source_id"] + ".md")).read_bytes() == old_md
    assert len(list((tmp_path / ".versions" / row["source_id"]).iterdir())) == 1


def test_db_version_remains_authoritative_when_cache_is_newer(tmp_path, monkeypatch):
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    row = _sample_row()
    old = _sample_chat()
    paths = gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=old)
    row["payload"] = {"gold_chat_json": paths["json"], "gold_chat_md": paths["markdown"]}
    gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat={**old, "scene_title": "uncommitted"})
    assert gce.load_gold_chat_for_row(row)["daily_story"] == old
    assert gce.gold_chat_summary(row["source_id"], row=row)["scene_title"] == old["scene_title"]


@pytest.mark.parametrize("failure,reason", [
    ("humor_low", "好笑分不足"),
    ("humor_missing", "好笑分待最终审核"),
    ("structure_low", "结构分不足"),
    ("hash_missing", "缺少最终正文审核摘要"),
    ("body_changed", "旧终验结果已失效"),
    ("contract_changed", "旧终验结果已失效"),
    ("facts_unresolved", "事实归属未定稿"),
    ("duplicate", "库内高度重复"),
    ("hard_invalid", "硬校验未通过"),
    ("kinship_patch", "硬校验未通过"),
])
def test_publication_blocks_downstream_review_failures(
    app_ctx, tmp_path, monkeypatch, failure, reason,
):
    from copy import deepcopy
    from app.config import Config
    from app.repositories import repo_daily_story, repo_gold_story
    from app.services.daily_story.daily_story_mgr import daily_story_mgr
    from app.services.daily_story.quality import gold_story_review_contract, stamp_story_review_binding
    from app.services.gold_story.gold_chat.import_story import gold_chat_production_eligibility

    sample = _sample_row()
    sample["payload"]["banned_literals"].append("哥哥")
    result = repo_gold_story.insert_or_skip(
        source="bilibili", source_id=sample["source_id"], url=sample["url"],
        mechanism=sample["mechanism"], structure_type=sample["structure_type"],
        story_raw="制作门槛回归来源" * 20, payload=sample["payload"],
        title=sample["title"], conflict_core=sample["conflict_core"],
        extract_confidence=0.8, structure_confidence=0.8, dialogue_confidence=0.8,
        auto_score=0.9, status="active",
    )
    row = repo_gold_story.get_story(int(result["id"]))
    chat = _sample_chat()
    chat["story_type"] = "A"
    chat["quality"] = {"structure_score": 80, "humor": {"funny_score": 11}}
    stamp_story_review_binding(chat, semantic_pass=True, review_contract=gold_story_review_contract(row, chat))
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "export_story_files", lambda **_kw: None)
    old_paths = gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat, publish=False)
    gce._backfill_gold_story_after_export(row, chat=chat, paths=old_paths, config=Config())
    gce.publish_gold_chat_paths(row["source_id"], old_paths)
    old_bytes = {key: Path(path).read_bytes() for key, path in old_paths.items()}
    imported = gc.import_gold_chat_daily_story(repo_gold_story.get_story(row["id"]))
    own_id = imported["daily_story_id"]
    assert imported["status"] == "active"
    before_change = repo_gold_story.get_story(row["id"])

    if failure == "humor_low":
        chat["quality"]["humor"]["funny_score"] = 9
    elif failure == "humor_missing":
        chat["quality"].pop("humor")
    elif failure == "structure_low":
        chat["quality"]["structure_score"] = 0
    elif failure == "hash_missing":
        chat["quality"].pop("reviewed_content_hash")
    elif failure == "body_changed":
        chat["dialogue"][0]["line"] += "这事我记住了。"
    elif failure == "contract_changed":
        repo_gold_story.patch_story_payload(row["id"], {"closing_intent": "新的收束契约"})
    elif failure == "facts_unresolved":
        repo_gold_story.patch_story_payload(row["id"], {"scene_contract": {
            "mom_lines_max": 1,
            "facts": [{"fact_id": "F1", "secret_holder": "妈妈", "attribution_status": "ambiguous"}],
        }})
    elif failure == "duplicate":
        repo_daily_story.insert_story(theme="其他来源的重复稿", story=deepcopy(chat), status="active", story_type="A")
    elif failure == "hard_invalid":
        chat["key"] = "太长的关键词不能通过制作阶段的硬校验"
    elif failure == "kinship_patch":
        chat["dialogue"][0]["line"] = "哥哥刚才又抢我遥控器，我还不敢说。"
        stamp_story_review_binding(chat, semantic_pass=True, review_contract=gold_story_review_contract(row, chat))

    fresh = repo_gold_story.get_story(row["id"])
    snapshot = deepcopy(chat)
    eligibility = gold_chat_production_eligibility(
        chat, fresh, candidates=repo_daily_story.list_all_stories(), exclude_story_id=own_id,
    )
    assert eligibility["ok"] is False
    assert reason in "；".join(eligibility["reasons"])
    assert chat == snapshot
    paths = gce.export_gold_chat_files(source_id=row["source_id"], row=fresh, chat=chat, publish=False)
    with pytest.raises(ValueError, match=reason) as caught:
        gce._backfill_gold_story_after_export(fresh, chat=chat, paths=paths, config=Config())
    assert caught.value.candidate == snapshot
    published = repo_gold_story.get_story(row["id"])
    assert published["payload"]["gold_chat_json"] == old_paths["json"]
    for key, path in old_paths.items():
        assert Path(path).read_bytes() == old_bytes[key]
    assert (tmp_path / (row["source_id"] + ".json")).read_bytes() == old_bytes["json"]

    if failure in {"facts_unresolved", "contract_changed"}:
        reimported = gc.import_gold_chat_daily_story(before_change, force=True)
        assert reimported["status"] == "review_pending"
        assert reason in "；".join(reimported["production_reasons"])

    # 历史稿/编辑稿也按相同原因阻断，不能靠直接创建任务跳过事实与查重检查。
    repo_daily_story.update_story(own_id, story=chat)
    with pytest.raises(ValueError, match=reason):
        daily_story_mgr.create_job(own_id)
    saved = repo_daily_story.get_story(own_id)
    assert saved["status"] == "review_pending"
    assert saved["job_id"] is None
    assert saved["story"]["dialogue"] == snapshot["dialogue"]


def test_source_reaction_short_speech_is_valid_without_padding():
    slot = {"speaker": "昭昭", "intent": "姐姐，你先回答妈妈呀。", "source_plan": True, "is_filler": True}
    assert gex._perbeat_check(slot, "姐姐，你先回答妈妈呀。", []) == []
    assert gex._perbeat_check(slot, "好。", [])
    assert gex._perbeat_check(slot, "姐姐，你先回答妈妈呀", [])


def test_authorized_adaptation_rebuilds_old_contract_from_effective_source(monkeypatch):
    import hashlib
    from app.services.gold_story.collect import llm
    contract, seed, _ = _source_plan_fixture()
    original = "这是未重构前的原始素材，保留以供授权核验。" * 3
    adapted = "用户授权后的新情节，必须据此重新建立契约，不能沿用旧素材。" * 3
    row = {"id": 0, "source_id": "BVadapt", "title": "原视频标题", "structure_type": "N",
           "mechanism": "M6", "story_raw": original, "payload": {
               "bili_title": "原视频角色说明", "story_raw": original,
               "scene_contract": contract, "dialogue_seed": seed,
               "gold_chat_adaptation": {"mode": "authorized_reconstruction", "approved": True,
                   "source_id": "BVadapt", "approved_at": "2026-10-23", "approval_note": "用户允许重构",
                   "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                   "story_raw": adapted, "title": "重构后的新情节"}}}
    called = []
    def build(**kwargs):
        called.append(kwargs)
        assert kwargs["story_raw"] == adapted
        assert kwargs["video_title"] == "重构后的新情节"
        assert kwargs["h3"]["beat"] == []
        raise ValueError("重构失败必须阻止沿用旧契约")
    monkeypatch.setattr(llm, "build_scene_contract", build)
    with pytest.raises(ValueError, match="阻止沿用旧契约"):
        gc._rebuild_h3a_h3b_on_convert(row)
    assert len(called) == 1
    assert row["payload"]["scene_contract"] == contract
