"""金故事 H0c 逐字稿修复测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.collect import llm as llm_steps
from app.services.gold_story.transcript import format_dialogue_transcript


def _transcript_evidence():
    return [{"source": "ocr", "text": "妈妈问今晚谁洗碗\n弟弟说轮到姐姐\n姐姐拿出值日表说今天轮到你"},
            {"source": "asr", "text": "妈妈闻今晚谁洗晚弟弟说轮到节节节节拿出纸日表说今天轮到你"}]


def _transcript_review(**changes):
    return {"content_complete": True, "key_facts_supported": True, "no_critical_conflict": True,
            "partial_scene_only": False, "reason": "两路可核实问答与值日表结果", **changes}


def test_reconcile_uses_only_original_source_and_independent_review(monkeypatch):
    prompts = []
    def chat(system, user):
        prompts.append((system, user))
        if len(prompts) == 1:
            return {"source": "ocr", "reason": "首轮独有的选择理由", "text": "模型伪造正文"}
        assert "首轮独有的选择理由" not in user
        assert "模型伪造正文" not in user
        return _transcript_review()
    monkeypatch.setattr(llm_steps, "_chat_json", chat)
    evidence = _transcript_evidence()
    result = llm_steps.reconcile_transcripts(evidence)
    assert result["status"] == "resolved"
    assert result["text"] == evidence[0]["text"]
    assert len(prompts) == 2
    result["text"] = "被修改的缓存正文"
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: pytest.fail("相同证据应复用裁决"))
    assert llm_steps.reconcile_transcripts(evidence, previous=result)["text"] == evidence[0]["text"]


@pytest.mark.parametrize("change", [
    {"content_complete": False}, {"key_facts_supported": False},
    {"no_critical_conflict": False}, {"partial_scene_only": True},
])
def test_reconcile_reviewer_can_veto_choice(monkeypatch, change):
    answers = iter([{"source": "ocr", "reason": "先选择"}, _transcript_review(**change)])
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: next(answers))
    result = llm_steps.reconcile_transcripts(_transcript_evidence())
    assert result["status"] == "unresolved"
    assert "text" not in result


@pytest.mark.parametrize("field", ["content_complete", "key_facts_supported", "no_critical_conflict", "partial_scene_only"])
def test_reconcile_rejects_missing_or_string_review_flags(monkeypatch, field):
    for value in [None, "true", 1]:
        answers = iter([{"source": "asr", "reason": "先选择"}, _transcript_review(**{field: value})])
        monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: next(answers))
        with pytest.raises(llm_steps.ModelOutputError, match="JSON boolean"):
            llm_steps.reconcile_transcripts(_transcript_evidence())


def test_reconcile_invalid_source_unresolved_and_changed_evidence(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: {"source": "merged", "reason": "混编"})
    with pytest.raises(llm_steps.ModelOutputError):
        llm_steps.reconcile_transcripts(_transcript_evidence())
    calls = []
    def unresolved(*args):
        calls.append(args)
        return {"source": "unresolved", "reason": "两路数字矛盾无法核实"}
    monkeypatch.setattr(llm_steps, "_chat_json", unresolved)
    evidence = _transcript_evidence()
    old = llm_steps.reconcile_transcripts(evidence)
    assert "text" not in old
    evidence[0]["text"] += "新证据"
    new = llm_steps.reconcile_transcripts(evidence, previous=old)
    assert old["evidence_hash"] != new["evidence_hash"]
    assert len(calls) == 2


def test_reconcile_does_not_truncate_or_invent_missing_evidence(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: pytest.fail("证据不足不得调用模型"))
    assert llm_steps.reconcile_transcripts([])["status"] == "unresolved"
    evidence = _transcript_evidence()
    assert llm_steps.reconcile_transcripts(evidence[:1])["status"] == "unresolved"
    evidence[0]["text"] = "字" * 12001
    assert llm_steps.reconcile_transcripts(evidence)["reason"] == "evidence_too_large"


def test_repair_source_audit_rejects_unfaithful_output(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: {"faithful": False, "reason": "添加原文没有的动作"})
    with pytest.raises(llm_steps.ModelOutputError, match="unfaithful"):
        llm_steps.review_transcript_repair(transcript="妈妈让弟弟洗碗", repaired="弟弟把碗摔了")


def test_format_dialogue_transcript():
    lines = [
        {"speaker": "妈妈", "text": "快睡吧"},
        {"speaker": "宝宝", "text": "不要"},
    ]
    assert format_dialogue_transcript(lines) == "妈妈：快睡吧\n宝宝：不要"


def test_repair_transcript_rejects_low_confidence(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "lines": [
                {"speaker": "妈妈", "text": "睡吧", "source_quote": "睡吧", "status": "ok"},
                {"speaker": "宝宝", "text": "不睡", "source_quote": "不睡", "status": "ok"},
            ],
            "repair_confidence": 0.2,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    with pytest.raises(ValueError, match="H0c low repair_confidence"):
        llm_steps.repair_transcript(title="测试", transcript="睡吧 不睡")


def test_repair_transcript_ok(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "speakers": ["妈妈", "宝宝"],
            "lines": [
                {"speaker": "妈妈", "text": "十二点了还不睡？", "source_quote": "十二点了还不睡？", "status": "ok"},
                {"speaker": "宝宝", "text": "谁12点不到天亮", "source_quote": "谁12点不到天亮", "status": "ok"},
            ],
            "repair_confidence": 0.82,
            "repair_notes": "标题暗示母子对话",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(
        title="深夜对话",
        transcript="十二点了还不睡？\n谁12点不到天亮",
        description="宝宝和妈妈",
    )
    assert out["repair_confidence"] == 0.82
    assert len(out["lines"]) == 2
    assert out["lines"][0]["speaker"] == "未知"


def test_trim_story_raw(monkeypatch):
    long_text = "姐弟抢遥控器，弟弟放狠话要回家，姐姐嘴硬后又追上去问明天还玩吗。" * 20

    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "story_raw": long_text[:200],
            "trim_notes": "删重复",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.trim_story_raw(long_text, max_chars=380)
    assert len(out) <= 380
    assert len(out) >= 80


def test_trim_story_raw_skips_when_short():
    text = "短故事" * 20
    assert llm_steps.trim_story_raw(text, max_chars=380) == text


def test_gold_story_prompts_carry_unintelligible_marker_rule():
    """H0c 打标记，H2/H3b 都不得把 [听不清] 展开成对白。"""
    marker = llm_steps.UNINTELLIGIBLE_MARKER
    assert marker in llm_steps._H0C_SYSTEM
    assert marker in llm_steps._H0C_USER
    assert marker in llm_steps._H2_USER
    assert marker in llm_steps._H3B_SYSTEM
    assert marker in llm_steps._H3B_USER


def test_gold_story_prompts_forbid_speaker_alternation_assumption():
    """#132：说话人须按语义归属，禁按行序交替；孩子不得自称家长身份。"""
    assert "不要假设说话人严格交替" in llm_steps._H0C_SYSTEM
    assert "不能靠行序、剧情、语气猜测" in llm_steps._H0C_USER
    assert "允许同一 speaker 连说多行" in llm_steps._H0C_USER
    assert "本步骤不改名、不做儿童改编、不增加第二个孩子" in llm_steps._H2_USER
    assert "孩子不得自称家长身份" in llm_steps._H3B_SYSTEM
    assert "回声/回旋镖人称转换" in llm_steps._H3B_USER
    assert "归属自洽（硬）" in llm_steps._H3A_USER


def test_repair_transcript_preserves_pronouns_and_does_not_invent_parent_labels(monkeypatch):
    source = "你去关灯\n我是你妈，你得听我的\n你还知道我是你妈呀？"
    rows = [{"speaker": speaker, "text": text, "source_quote": text, "status": "ok"}
            for speaker, text in zip(["妈妈", "宝宝", "宝宝"], source.splitlines())]
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {
        "lines": rows, "speakers": ["妈妈", "宝宝"], "repair_confidence": 0.8,
    })
    out = llm_steps.repair_transcript(title="妈妈和宝宝关灯", transcript=source)
    assert [line["speaker"] for line in out["lines"]] == ["未知"] * 3
    assert [line["text"] for line in out["lines"]] == source.splitlines()
    assert out["speakers"] == ["未知"]


@pytest.mark.parametrize("quote", [None, "", "爸爸：关灯", "标题里才有的台词"])
def test_repair_rejects_missing_or_invented_original_quote(monkeypatch, quote):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {
        "repair_confidence": 0.9,
        "lines": [{"speaker": "未知", "text": "关灯", "source_quote": quote, "status": "ok"}] * 2,
    })
    with pytest.raises(ValueError, match="source_quote"):
        llm_steps.repair_transcript(title="标题里才有的台词", transcript="关灯\n知道了")


def test_repair_preserves_explicit_source_labels_but_not_embedded_quotes(monkeypatch):
    source = "姐姐：关灯\n弟弟：你刚才说姐姐：关灯"
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {
        "repair_confidence": 0.9,
        "lines": [
            {"speaker": "姐姐", "text": "关灯", "source_quote": "姐姐：关灯", "status": "ok"},
            {"speaker": "弟弟", "text": "你刚才说姐姐：关灯", "source_quote": "弟弟：你刚才说姐姐：关灯", "status": "ok"},
        ],
    })
    out = llm_steps.repair_transcript(title="关灯", transcript=source)
    assert [line["speaker"] for line in out["lines"]] == ["姐姐", "弟弟"]
    assert out["lines"][1]["text"] == "你刚才说姐姐：关灯"


def test_repair_transcript_replaces_unusable_line_with_marker(monkeypatch):
    """整行 unusable 只留 [听不清]，ASR 乱码不得留在逐字稿里。"""

    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "speakers": ["妈妈", "宝宝"],
            "lines": [
                {"speaker": "妈妈", "text": "赶紧去关灯", "source_quote": "赶紧去关灯", "status": "ok"},
                {
                    "speaker": "宝宝",
                    "text": "嗯嗯嗯呃要你去活动就拿那小活动来打啊",
                    "source_quote": "呃呃呃",
                    "status": "unusable",
                },
            ],
            "repair_confidence": 0.6,
            "repair_notes": "末行整行语义不可恢复",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(title="关灯", transcript="赶紧去关灯\n呃呃呃")
    assert out["unusable_lines"] == 1
    assert out["lines"][1]["text"] == llm_steps.UNINTELLIGIBLE_MARKER
    assert out["lines"][1]["status"] == "unusable"
    assert out["lines"][0]["text"] == "赶紧去关灯"


def test_scrub_unintelligible_quotes_rewrites_marked_quote():
    marker = llm_steps.UNINTELLIGIBLE_MARKER
    text = f"昭昭站起来，一边走一边念叨：“说好了 {marker}”，妈妈偷笑。"
    out, count = llm_steps.scrub_unintelligible_quotes(text)
    assert count == 1
    assert marker not in out
    assert "嘟囔了一句听不清的话" in out


def test_scrub_unintelligible_quotes_keeps_clean_or_unquoted():
    assert llm_steps.scrub_unintelligible_quotes("昭昭说你去你去。") == (
        "昭昭说你去你去。",
        0,
    )
    assert llm_steps.scrub_unintelligible_quotes("昭昭说了一句 [听不清]") == (
        "昭昭说了一句 [听不清]",
        0,
    )


def test_drop_unintelligible_seed_rows_keeps_valid_intents():
    seed = [
        {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
        {"speaker": "昭昭", "intent": "要你去活动就拿小活动打啊 [听不清]"},
        {"speaker": "昭昭", "intent": "【听不清】"},
        {"speaker": "妈妈", "intent": "答应明天补烤串"},
    ]
    kept, dropped = llm_steps.drop_unintelligible_seed_rows(seed)
    assert [row["intent"] for row in kept] == ["喊昭昭去关灯", "答应明天补烤串"]
    assert dropped == [
        "要你去活动就拿小活动打啊 [听不清]",
        "【听不清】",
    ]


def _seed_contract() -> dict:
    return {
        "location": "卧室",
        "object": "关灯与烤串补偿",
        "mom_lines_max": 3,
        "story_type": "I",
        "closing_intent": "灯关后，妈妈在被窝里偷笑",
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "懒在被窝里喊昭昭去关灯"},
            {"beat": 2, "speaker": "昭昭", "intent": "正玩玩具头也不抬拒绝"},
            {"beat": 3, "speaker": "妈妈", "intent": "搬出身份压人"},
            {"beat": 4, "speaker": "昭昭", "intent": "抓住把柄要求明天补烤串"},
        ],
    }


def test_build_dialogue_seed_drops_unintelligible_and_falls_back(monkeypatch):
    """听不清碎片被丢弃后 seed 不足下限，用 beat_chain 兜底，不新造剧情。"""

    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "setting": "卧室，妈妈躺被窝里，昭昭在床边玩玩具",
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
                {"speaker": "昭昭", "intent": "你去你去，我正玩着呢"},
                {"speaker": "昭昭", "intent": "要你去活动就拿小活动打啊"},
                {"speaker": "昭昭", "intent": "我不认为咋长啊 [听不清]"},
            ],
            "closing_intent": "灯关后，妈妈在被窝里偷笑",
            "speaker_map_note": "妈妈与昭昭按原稿保留",
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.build_dialogue_seed(
        story_raw="妈妈喊昭昭关灯，昭昭用偷吃烤串的把柄讨补偿。" * 3,
        h3={"beat": ["a", "b", "c", "d"]},
        scene_contract=_seed_contract(),
    )
    intents = [row["intent"] for row in out["dialogue_seed"]]
    assert not any(llm_steps.UNINTELLIGIBLE_MARKER in text for text in intents)
    assert intents == [row["intent"] for row in _seed_contract()["beat_chain"]]


def test_build_dialogue_seed_keeps_valid_seed_without_fallback(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "setting": "卧室，昭昭在床边玩玩具",
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
                {"speaker": "昭昭", "intent": "你去你去，我正玩着呢"},
                {"speaker": "妈妈", "intent": "我是你妈，你得听我的"},
                {"speaker": "昭昭", "intent": "你还知道我是你妈呀？"},
                {"speaker": "昭昭", "intent": "那你明天补给我烤串"},
            ],
            "closing_intent": "灯关后，妈妈在被窝里偷笑",
            "speaker_map_note": "妈妈与昭昭按原稿保留",
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.build_dialogue_seed(
        story_raw="妈妈喊昭昭关灯，昭昭用偷吃烤串的把柄讨补偿。" * 3,
        h3={"beat": ["a", "b", "c", "d"]},
        scene_contract=_seed_contract(),
    )
    assert len(out["dialogue_seed"]) == 5
    assert out["dialogue_seed"][-1]["intent"] == "那你明天补给我烤串"


def _fact_contract() -> dict:
    contract = dict(_seed_contract())
    contract["facts"] = [
        {
            "fact_id": "F1",
            "event": "晚上偷吃烤串",
            "secret_holder": "妈妈",
            "discoverer": "昭昭",
            "accuser": "昭昭",
            "denier": "妈妈",
            "claimant": "昭昭",
            "attribution_status": "resolved",
        }
    ]
    return contract


@pytest.mark.parametrize("bad_retry", [None, "over_budget", "lost_close"])
def test_seed_parent_budget_repairs_without_silently_dropping_closing(monkeypatch, bad_retry):
    contract = _seed_contract()
    contract["mom_lines_max"] = 2
    opening = {"speaker": "妈妈", "intent": "现在该关灯了"}
    extra = {"speaker": "妈妈", "intent": "已经到睡觉时间了"}
    child = {"speaker": "昭昭", "intent": "那你明天补给我烤串"}
    response = {"speaker": "灿灿", "intent": "这句话我可是听清楚了"}
    closing = {"speaker": "妈妈", "intent": "那就说好，关灯睡觉吧"}
    original = [opening, extra, child, response, closing]
    revised = [opening, child, response, closing]
    if bad_retry == "over_budget":
        revised = original
    if bad_retry == "lost_close":
        revised = [opening, child, response, {"speaker": "妈妈", "intent": "别再闹了"}]
    calls = []

    def chat(_system, user):
        calls.append(user)
        return {"dialogue_seed": original if len(calls) == 1 else revised, "dialogue_confidence": 0.9}

    monkeypatch.setattr(llm_steps, "_chat_json", chat)
    if bad_retry:
        with pytest.raises(ValueError, match="无法保留完整收束"):
            llm_steps.build_dialogue_seed(story_raw="关灯前商量明天补偿", h3={}, scene_contract=contract)
    else:
        out = llm_steps.build_dialogue_seed(story_raw="关灯前商量明天补偿", h3={}, scene_contract=contract)
        assert out["dialogue_seed"][-1] == closing
        assert len(out["dialogue_seed"]) == 4
    assert len(calls) == 2
    assert "最后一个素材单元必须原样保留" in calls[1]


def test_build_dialogue_seed_retries_on_fact_role_conflict(monkeypatch):
    """#132：孩子顶了妈妈的辩解句 → 带约束重抽一次并采纳合规稿。"""
    calls: list[str] = []

    def fake_chat(_system: str, user: str) -> dict:
        calls.append(user)
        if len(calls) == 1:
            return {
                "setting": "卧室",
                "dialogue_seed": [
                    {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
                    {"speaker": "昭昭", "intent": "你去你去，我正玩着呢"},
                    {"speaker": "妈妈", "intent": "我是你妈，你得听我的"},
                    {
                        "speaker": "昭昭",
                        "intent": "谁告诉你我晚上偷吃烤串儿啦",
                        "fact_ref": "F1",
                        "speech_act": "deny",
                        "claim_role": "secret_holder",
                    },
                    {"speaker": "昭昭", "intent": "那你明天补给我烤串"},
                ],
                "dialogue_confidence": 0.9,
            }
        return {
            "setting": "卧室",
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
                {"speaker": "昭昭", "intent": "你去你去，我正玩着呢"},
                {"speaker": "妈妈", "intent": "我是你妈，你得听我的"},
                {
                    "speaker": "妈妈",
                    "intent": "谁告诉你我晚上偷吃烤串儿啦",
                    "fact_ref": "F1",
                    "speech_act": "deny",
                    "claim_role": "secret_holder",
                },
                {
                    "speaker": "昭昭",
                    "intent": "把明天补给我",
                    "fact_ref": "F1",
                    "speech_act": "claim_compensation",
                    "claim_role": "claimant",
                },
            ],
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.build_dialogue_seed(
        story_raw="妈妈喊昭昭关灯，昭昭用偷吃烤串的把柄讨补偿。" * 3,
        h3={"beat": ["a", "b", "c", "d"]},
        scene_contract=_fact_contract(),
    )
    assert len(calls) == 2, "冲突后应带约束重抽一次"
    assert "角色绑定硬约束" in calls[1]
    rows = out["dialogue_seed"]
    assert [r["speaker"] for r in rows if "偷吃烤串" in r["intent"]] == ["妈妈"]
    assert rows[-1]["intent"] == "把明天补给我"


def test_build_dialogue_seed_keeps_first_pass_when_retry_still_conflicts(
    monkeypatch,
):
    """重抽仍冲突时，冲突行被剔除；剩余不足下限则由 beat_chain 兜底。"""
    calls: list[str] = []

    def fake_chat(_system: str, user: str) -> dict:
        calls.append(user)
        return {
            "setting": "卧室",
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "喊昭昭去关灯"},
                {"speaker": "昭昭", "intent": "你去你去，我正玩着呢"},
                {
                    "speaker": "昭昭",
                    "intent": "谁告诉你我晚上偷吃烤串儿啦",
                    "fact_ref": "F1",
                    "speech_act": "deny",
                    "claim_role": "secret_holder",
                },
            ],
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.build_dialogue_seed(
        story_raw="妈妈喊昭昭关灯，昭昭用偷吃烤串的把柄讨补偿。" * 3,
        h3={"beat": ["a", "b", "c", "d"]},
        scene_contract=_fact_contract(),
    )
    assert len(calls) == 2
    intents = [row["intent"] for row in out["dialogue_seed"]]
    assert "谁告诉你我晚上偷吃烤串儿啦" not in intents
    assert intents == [row["intent"] for row in _seed_contract()["beat_chain"]]


def test_build_dialogue_seed_retries_wrong_character_address(monkeypatch):
    calls = []

    def chat(system, user):
        calls.append(user)
        return {
            'dialogue_confidence': 0.9,
            'dialogue_seed': [
                {'speaker': '灿灿', 'intent': '昭昭姐姐，这个是谁做的？' if len(calls) == 1 else '昭昭，这个是谁做的？'},
                {'speaker': '昭昭', 'intent': '我自己做的，你看好不好？'},
                {'speaker': '灿灿', 'intent': '看着挺好，能给我吗？'},
                {'speaker': '昭昭', 'intent': '姐姐，等我做好再给你。'},
            ],
        }

    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    out = llm_steps.build_dialogue_seed(story_raw='姐弟在玩手工', h3={}, scene_contract={})
    assert len(calls) == 2
    assert '称谓绑定返修' in calls[1]
    assert all('昭昭姐姐' not in r['intent'] for r in out['dialogue_seed'])


def test_build_dialogue_seed_rejects_persistent_wrong_address(monkeypatch):
    import pytest
    calls = []

    def chat(*args):
        calls.append(1)
        return {'dialogue_seed': [{'speaker': '灿灿', 'intent': '昭昭姐姐，过来。'}]}

    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    with pytest.raises(ValueError, match='H3b角色关系不合格'):
        llm_steps.build_dialogue_seed(story_raw='姐弟在玩手工', h3={}, scene_contract={})
    assert len(calls) == 2


def test_repair_transcript_rejects_all_unusable_even_with_high_confidence(monkeypatch):
    import pytest
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a, **k: {
        "lines": [{"speaker": "未知", "text": "garbled", "source_quote": "无法理解的原始内容", "status": "unusable"}] * 2,
        "repair_confidence": 0.9,
    })
    with pytest.raises(ValueError, match="no usable transcript"):
        llm_steps.repair_transcript(title="真实素材", transcript="无法理解的原始内容\n无法理解的原始内容")


@pytest.mark.parametrize("field,value", [
    ("has_complete_scene", False), ("has_complete_scene", None),
    ("start_index", 0), ("start_index", 3), ("start_index", True),
    ("end_index", 1), ("end_index", 5), ("end_index", "3"),
    ("scene_evidence", ""),
])
def test_repair_requires_grounded_single_scene(monkeypatch, field, value):
    scene = {"has_complete_scene": True, "start_index": 1, "end_index": 3,
             "scene_evidence": "妈妈让孩子关灯，孩子答应了"}
    scene[field] = value
    responses = iter([{"repair_confidence": 0.9, "lines": [
        {"speaker": "未知", "text": t, "source_quote": t, "status": "ok"}
        for t in ["关灯睡觉", "今天太晚了", "知道了", "另一段故事"]]}, scene])
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: next(responses))
    with pytest.raises(ValueError, match="source_unusable" if value is False else "LLM "):
        llm_steps.repair_transcript(title="测试", transcript="关灯睡觉\n今天太晚了\n知道了\n另一段故事", require_complete_scene=True)


def test_repair_selects_range_without_dropping_valid_middle_rows(monkeypatch):
    calls = []
    def chat(system, user):
        calls.append(user)
        if len(calls) == 1:
            return {"repair_confidence": 0.9, "lines": [
                {"speaker": "未知", "text": t, "source_quote": t, "status": status}
                for t, status in [("关灯睡觉", "ok"), ("乱码", "unusable"),
                                  ("我不困", "ok"), ("明天要上学", "ok"), ("知道了", "ok"), ("其他事件", "ok")]]}
        import json
        rows = json.loads(user)
        assert [row['index'] for row in rows] == list(range(1, 7))
        assert rows[1]['text'] == '[听不清]' and rows[2]['text'] == '我不困'
        return {"has_complete_scene": True, "start_index": 1, "end_index": 5,
                "scene_evidence": "劝睡后答应", "scene_line_indices": [1, 5], "lines": []}
    monkeypatch.setattr(llm_steps, "_chat_json", chat)
    result = llm_steps.repair_transcript(title="测试", transcript="关灯睡觉\n乱码\n我不困\n明天要上学\n知道了\n其他事件", require_complete_scene=True)
    assert [row["text"] for row in result["lines"]] == ["关灯睡觉", "我不困", "明天要上学", "知道了"]
    assert result["scene_line_indices"] == [1, 3, 4, 5]


@pytest.mark.parametrize('quotes', [['后说', '先说'], ['先说', '先说']])
def test_repair_rejects_reordered_or_reused_source(monkeypatch, quotes):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'repair_confidence': .9, 'lines': [
            {'speaker': '未知', 'text': t, 'source_quote': t, 'status': 'ok'} for t in quotes]})
    with pytest.raises(llm_steps.ModelOutputError, match='out of order or overlapping'):
        llm_steps.repair_transcript(title='', transcript='先说\n后说')


def test_repair_does_not_truncate_evidence(monkeypatch):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: pytest.fail('must not call'))
    with pytest.raises(llm_steps.ModelOutputError, match='evidence budget'):
        llm_steps.repair_transcript(title='', transcript='字' * 12001)


def test_extract_story_does_not_receive_title_or_adaptation_hints(monkeypatch):
    def chat(system, user):
        assert '错误标题' not in user and '简介增加人物' not in user and '热评虚构结局' not in user
        assert '原始对白' in user
        return {'story_raw': '原文的问答及明确结果。' * 10, 'has_complete_arc': True, 'extract_confidence': .9}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    llm_steps.extract_story_raw(title='错误标题', description='简介增加人物', replies=['热评虚构结局'], transcript='原始对白')


@pytest.mark.parametrize("response", [
    {"faithful": False, "unsupported_claims": ["门铃响了"]},
    {"faithful": True, "unsupported_claims": ["门铃响了"]},
    {"faithful": True}, {},
])
def test_source_audit_rejects_invented_events_or_incomplete_review(monkeypatch, response):
    def review(system, user):
        assert "唯一事实依据" in system and "关灯睡觉" in user and "门铃响了" in user
        return {"child_adaptation_suitable": True, "child_adaptation_evidence": "妈妈：关灯睡觉",
                "child_adaptation_reason": "儿童日常", **response}
    monkeypatch.setattr(llm_steps, "_chat_json", review)
    with pytest.raises(ValueError, match="source_unfaithful" if "unsupported_claims" in response else "LLM "):
        llm_steps.review_story_source(transcript="妈妈：关灯睡觉", story_raw="门铃响了，孩子跑出去开门。")


def test_source_audit_accepts_faithful_role_mapping(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {
        "faithful": True, "speaker_attribution_supported": True, "unsupported_claims": [], "summary": "仅等价转述和角色改名",
        "child_adaptation_suitable": True, "child_adaptation_evidence": "昭昭答应了妈妈。",
        "child_adaptation_reason": "符合儿童年龄的回应",
    })
    assert llm_steps.review_story_source(transcript="宝宝：知道了", story_raw="昭昭答应了妈妈。")['faithful']


def _audit_response(response, monkeypatch, *, default_age=True, **overrides):
    if default_age:
        response = {"source_age_compatible": True, "mapped_roles_age_compatible": True,
                    "core_event_supported": True, "core_event_reason": "核心事件与来源一致",
                    "source_age_evidence": "姐弟一起整理书桌。", "mapped_age_evidence": "昭昭：擦桌子",
                    "age_reason": "姐弟整理书桌，儿童负责擦桌子符合年龄", **response}
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a, **kw: response)
    kwargs = dict(video_title="姐弟日常", title="整理书桌", story_raw="姐弟一起整理书桌。",
        conflict_core="分工", mechanism="M6", structure_type="A", speaker_map_note="",
        dialogue_seed=[{"speaker": "昭昭", "intent": "擦桌子"}], beat=[])
    kwargs.update(overrides)
    return llm_steps.audit_story_fit(**kwargs)


@pytest.mark.parametrize("flag", ["false", "true", 0, 1, None, [], {}])
@pytest.mark.parametrize("stage", ["extract", "audit"])
def test_review_flags_require_json_booleans(monkeypatch, flag, stage):
    if stage == "extract":
        monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {
            "story_raw": "姐弟两人整理书桌，姐姐先收拾书本，弟弟接着把桌子擦干净。" * 4,
            "has_complete_arc": flag, "extract_confidence": 0.9,
        })
        call = lambda: llm_steps.extract_story_raw(title="整理书桌", transcript="真实素材")
    else:
        call = lambda: _audit_response({"pass": flag, "sibling_fit": 0.9, "age_fit": 0.9,
            "conflict_usable": 0.9, "mapping_fit": 0.9, "reject_reasons": []}, monkeypatch)
    with pytest.raises(ValueError, match="LLM .*boolean"):
        call()


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True, None, "bad"])
def test_review_scores_reject_nonfinite_out_of_range_or_invalid_values(monkeypatch, score):
    with pytest.raises(ValueError, match="LLM .*score"):
        _audit_response({"pass": True, "sibling_fit": score, "age_fit": 0.9,
            "conflict_usable": 0.9, "mapping_fit": 0.9, "reject_reasons": []}, monkeypatch)


def test_audit_reject_reasons_cannot_coexist_with_pass(monkeypatch):
    result = _audit_response({"pass": True, "sibling_fit": 0.9, "age_fit": 0.9,
        "conflict_usable": 0.9, "mapping_fit": 0.9, "reject_reasons": ["来源不完整"]}, monkeypatch)
    assert result["pass"] is False


def test_source_audit_schema_failure_does_not_become_source_rejection(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *a: {"error": "incomplete response"})
    with pytest.raises(ValueError, match="LLM "):
        llm_steps.review_story_source(transcript="完整来源", story_raw="来源中的完整故事")


def _high_fit_scores(**changes):
    return {"pass": True, "sibling_fit": 0.95, "age_fit": 0.95,
            "core_event_supported": True, "core_event_reason": "核心事件与来源一致",
            "conflict_usable": 0.95, "mapping_fit": 0.95, "reject_reasons": [], **changes}


@pytest.mark.parametrize("field", ["source_age_compatible", "mapped_roles_age_compatible"])
@pytest.mark.parametrize("age_only", [False, True])
def test_age_veto_cannot_be_overridden_by_high_scores_or_disabled_scoring(monkeypatch, field, age_only):
    result = _audit_response(_high_fit_scores(**{field: False}), monkeypatch, age_only=age_only)
    assert result["pass"] is False
    assert any("age_incompatible" in reason for reason in result["reject_reasons"])


@pytest.mark.parametrize("field", ["source_age_compatible", "mapped_roles_age_compatible"])
@pytest.mark.parametrize("value", [None, "true", 1])
def test_age_audit_requires_explicit_boolean(monkeypatch, field, value):
    with pytest.raises(llm_steps.ModelOutputError, match="JSON boolean"):
        _audit_response(_high_fit_scores(**{field: value}), monkeypatch)


@pytest.mark.parametrize("changes", [
    {"source_age_evidence": "原文不存在的故事"},
    {"mapped_age_evidence": "妈妈：擦桌子"},
    {"mapped_age_evidence": "擦桌子"},
    {"age_reason": ""},
])
def test_age_audit_requires_traceable_source_and_role_action(monkeypatch, changes):
    with pytest.raises(llm_steps.ModelOutputError):
        _audit_response(_high_fit_scores(**changes), monkeypatch)


def test_age_evidence_accepts_whitespace_and_punctuation_variants(monkeypatch):
    result = _audit_response(_high_fit_scores(mapped_age_evidence="昭昭: 擦桌子。"), monkeypatch)
    assert result["pass"] is True


def test_source_age_rejection_precedes_fidelity_repair(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: {
        "faithful": False, "unsupported_claims": ["添写动作"],
        "child_adaptation_suitable": False, "child_adaptation_evidence": "成年女儿临产",
        "child_adaptation_reason": "戏核依赖成年人的生育行为，不能改成儿童亲历",
    })
    with pytest.raises(llm_steps.SourceRejected, match="age_incompatible_core"):
        llm_steps.review_story_source(transcript="成年女儿临产，父亲先拖地。", story_raw="成年女儿临产。")


@pytest.mark.parametrize("value", [None, "true", 1])
def test_source_age_missing_or_invalid_verdict_is_execution_failure(monkeypatch, value):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: {
        "faithful": True, "speaker_attribution_supported": True, "unsupported_claims": [], "child_adaptation_suitable": value,
        "child_adaptation_evidence": "孩子提问", "child_adaptation_reason": "符合年龄",
    })
    with pytest.raises(llm_steps.ModelOutputError, match="JSON boolean"):
        llm_steps.review_story_source(transcript="孩子提问", story_raw="孩子提问")


def test_age_audit_receives_full_seed_contract_and_original_source(monkeypatch):
    marker = "灿灿：妈，我好像要生了"
    seen = []
    def chat(_system, user):
        seen.append(user)
        assert marker in user and "尾部原始事实" in user and "尾部契约事实" in user
        return _high_fit_scores(source_age_compatible=False, mapped_roles_age_compatible=False,
            source_age_evidence="尾部原始事实", mapped_age_evidence=marker, age_reason="儿童承担成人生育行为")
    monkeypatch.setattr(llm_steps, "_chat_json", chat)
    result = llm_steps.audit_story_fit(video_title="家庭趣事", title="趣事", story_raw="叙事" * 2100 + "尾部原始事实",
        conflict_core="亲子", mechanism="M6", structure_type="N", speaker_map_note="能迁成亲子冲突",
        dialogue_seed=[{"speaker": "昭昭", "intent": "旁观" * 2100}, {"speaker": "灿灿", "intent": "妈，我好像要生了"}],
        beat=[], scene_contract={"description": "背景" * 2100 + "尾部契约事实"})
    assert not result["pass"] and len(seen) == 1


def test_oversize_age_audit_fails_before_model_call(monkeypatch):
    monkeypatch.setattr(llm_steps, "_chat_json", lambda *_a: pytest.fail("不能截断后放行"))
    with pytest.raises(llm_steps.ModelOutputError, match="input_budget_exceeded"):
        llm_steps.audit_story_fit(video_title="日常", title="日常", story_raw="字" * 48001,
            conflict_core="争抢", mechanism="M6", structure_type="N", speaker_map_note="",
            dialogue_seed=[{"speaker": "昭昭", "intent": "我先来"}], beat=[])


@pytest.mark.parametrize('proposal', [
    {'start_index': True, 'end_index': 2, 'reason': 'x'},
    {'start_index': 0, 'end_index': 2, 'reason': 'x'},
    {'start_index': 2, 'end_index': 1, 'reason': 'x'},
    {'start_index': 1, 'end_index': 3, 'reason': 'x'},
    {'start_index': 1, 'end_index': 2, 'reason': ''},
])
def test_collection_rejects_fabricated_indices(monkeypatch, proposal):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {'clips': [proposal]})
    with pytest.raises(ValueError, match='collection invalid'):
        llm_steps.select_collection_clips([
            {'start': 10, 'end': 12, 'text': '起因'}, {'start': 13, 'end': 15, 'text': '结果'},
        ], duration_sec=800)


def test_collection_index_proposes_all_bounded_candidates_without_content_veto(monkeypatch):
    calls = []
    def chat(system, user):
        calls.append(user)
        return {'clips': [{'start_index': i, 'end_index': i, 'reason': '候选事件'} for i in range(1, 7)]}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    result = llm_steps.select_collection_clips([
        {'start': i * 20, 'end': i * 20 + 10, 'text': '粗转写可能有错'} for i in range(6)
    ], duration_sec=800)
    assert len(calls) == 1 and len(result) == 6
    assert all('eligible' not in clip for clip in result)
    assert result[0]['start_sec'] == 0 and result[-1]['end_sec'] == 111


@pytest.mark.parametrize('segments,clips', [
    ([{'start': 0, 'end': 10, 'text': 'a'}, {'start': 120, 'end': 130, 'text': 'b'}],
     [{'start_index': 1, 'end_index': 2, 'reason': 'too long'}]),
    ([{'start': 0, 'end': 10, 'text': 'a'}, {'start': 11, 'end': 20, 'text': 'b'}],
     [{'start_index': 1, 'end_index': 2, 'reason': 'a'}, {'start_index': 2, 'end_index': 2, 'reason': 'b'}]),
])
def test_collection_rejects_oversized_or_overlapping_clips(monkeypatch, segments, clips):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'clips': clips, 'single_complete_event': True, 'reason': '完整'})
    with pytest.raises(ValueError, match='overlapping or oversized'):
        llm_steps.select_collection_clips(segments, duration_sec=800)


@pytest.mark.parametrize('index', [True, 0, -1, 3, '1'])
def test_source_age_evidence_index_rejects_invalid_ids(monkeypatch, index):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'faithful': True, 'speaker_attribution_supported': True, 'unsupported_claims': [], 'child_adaptation_suitable': True,
        'child_adaptation_evidence_index': index, 'child_adaptation_reason': '儿童日常',
    })
    with pytest.raises(ValueError, match='invalid evidence index'):
        llm_steps.review_story_source(transcript='你借我点呗', story_raw='有人借钱')


def test_source_age_evidence_index_preserves_exact_original(monkeypatch):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'faithful': True, 'speaker_attribution_supported': True, 'unsupported_claims': [], 'child_adaptation_suitable': True,
        'child_adaptation_evidence_index': 1, 'child_adaptation_reason': '同龄人借钱',
    })
    result = llm_steps.review_story_source(transcript='未知：你借我点呗', story_raw='有人借钱')
    assert result['child_adaptation_evidence'] == '未知：你借我点呗'


def test_collection_sample_padding_stops_at_next_segment(monkeypatch):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'clips': [{'start_index': 1, 'end_index': 2, 'reason': '完成'}],
        'single_complete_event': True, 'reason': '同一个事件',
    })
    result = llm_steps.select_collection_clips([
        {'timestamp_sec': 10, 'end_sec': 10, 'text': '起因'},
        {'timestamp_sec': 12, 'end_sec': 12, 'text': '结果'},
        {'timestamp_sec': 12.5, 'end_sec': 13, 'text': '另一个场景'},
    ], duration_sec=800)
    assert result[0]['end_sec'] == 12.5


@pytest.mark.parametrize('field,index', [
    ('source_age_evidence_index', True), ('source_age_evidence_index', 99),
    ('mapped_age_evidence_index', 0), ('mapped_age_evidence_index', '1'),
])
def test_role_age_audit_rejects_invalid_evidence_indices(monkeypatch, field, index):
    with pytest.raises(ValueError, match='invalid evidence index'):
        _audit_response(_high_fit_scores(**{field: index}), monkeypatch)


def test_role_age_audit_selects_original_evidence_without_rewriting(monkeypatch):
    result = _audit_response(_high_fit_scores(source_age_evidence_index=1, mapped_age_evidence_index=1), monkeypatch)
    assert result['source_age_evidence'] == '姐弟一起整理书桌。'
    assert result['mapped_age_evidence'] == '昭昭：擦桌子'


@pytest.mark.parametrize('changes', [
    {'event_complete': False}, {'event_complete': None}, {'event_complete': 'true'},
    {'omitted_event_evidence': ['后续仍在追问同一承诺']}, {'omitted_event_evidence': None},
])
def test_repair_audit_requires_complete_event_even_when_words_are_faithful(monkeypatch, changes):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {
        'faithful': True, 'event_complete': True, 'omitted_event_evidence': [],
        'reason': '遗漏了同一事件后续结果', **changes})
    with pytest.raises(llm_steps.ModelOutputError):
        llm_steps.review_transcript_repair(transcript='承诺。追问。改口。', repaired='承诺。')


def test_repair_retry_feedback_reaches_scene_selector(monkeypatch):
    calls = []
    def chat(system, user):
        calls.append(user)
        if len(calls) == 1:
            return {'repair_confidence': .9, 'lines': [
                {'speaker': '未知', 'text': t, 'source_quote': t, 'status': 'ok'} for t in ['问句', '回答']]}
        assert '上轮遗漏了后续结果' in user
        assert '"index": 1' in user and '"index": 2' in user
        return {'has_complete_scene': True, 'start_index': 1, 'end_index': 2, 'scene_evidence': '问答完整'}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    llm_steps.repair_transcript(title='', transcript='问句\n回答', require_complete_scene=True, feedback='上轮遗漏了后续结果')


@pytest.mark.parametrize('text', ['来源叠字待确认', '关键半句[听不清]'])
def test_complete_scene_cannot_admit_vague_without_marker(monkeypatch, text):
    answers = iter([
        {'repair_confidence': .8, 'lines': [
            {'speaker': '未知', 'text': '提问', 'source_quote': '提问', 'status': 'ok'},
            {'speaker': '未知', 'text': text, 'source_quote': text, 'status': 'vague'},
            {'speaker': '未知', 'text': '回答', 'source_quote': '回答', 'status': 'ok'}]},
        {'has_complete_scene': True, 'start_index': 1, 'end_index': 3, 'scene_evidence': '声称完整但夹有不确定行'},
    ])
    def chat(system, user, **kwargs):
        if '独立的事实不确定性审核员' in system:
            return {'reviews': [{'index': 2, 'meaning_supported': False, 'uncertain_facts': ['关键事实不明'],
                                 'reason': '内容仍不能确定', 'evidence_quote': text}]}
        return next(answers)
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    with pytest.raises(llm_steps.ModelOutputError, match='uncertain lines') as exc:
        llm_steps.repair_transcript(title='', transcript='提问\n'+text+'\n回答', require_complete_scene=True)
    assert text in str(exc.value)


def test_reconcile_does_not_reuse_old_semantic_policy(monkeypatch):
    import hashlib
    import json
    evidence = _transcript_evidence()
    raw = json.dumps([{'source': x['source'], 'text': x['text'], 'segments': [],
                      'avg_confidence': None, 'engine': None} for x in evidence], ensure_ascii=False, sort_keys=True)
    old = {'version': 'whole_source_v1', 'evidence_hash': hashlib.sha256(('whole_source_v1\n'+raw).encode()).hexdigest(),
           'selection': {'source': 'unresolved', 'reason': '旧规则按错字判断冲突'}}
    calls = []
    def chat(*a):
        calls.append(a)
        return {'source': 'ocr', 'reason': '语义可核实'} if len(calls) == 1 else _transcript_review()
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    result = llm_steps.reconcile_transcripts(evidence, previous=old)
    assert len(calls) == 2 and result['status'] == 'resolved'
    assert result['version'] == 'whole_source_v2' and result['text'] == evidence[0]['text']


@pytest.mark.parametrize('end,next_start,duration,expected', [(20,20.4,800,20.4),(20,25,800,21),(20,19,800,20),(120,125,800,120),(20,None,20.2,20.2)])
def test_collection_tail_margin_is_bounded_by_gap_duration_and_budget(monkeypatch, end, next_start, duration, expected):
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a: {'clips':[{'start_index':1,'end_index':2 if next_start is None else 1,'reason':'完整事件'}]})
    segments=[{'start':0,'end':end,'text':'事件'}]
    if next_start is not None:segments.append({'start':next_start,'end':next_start+1,'text':'下一段'})
    else:segments=[{'start':0,'end':1,'text':'开头'},{'start':2,'end':end,'text':'结尾'}]
    clips=llm_steps.select_collection_clips(segments,duration_sec=duration)
    assert clips[0]['index_end_sec']==end and clips[0]['end_sec']==expected


@pytest.mark.parametrize('supported', [False, None, 'true'])
def test_source_audit_cannot_pass_unsupported_speaker_attribution(monkeypatch, supported):
    monkeypatch.setattr(llm_steps,'_chat_json',lambda *a:{
        'faithful':True,'speaker_attribution_supported':supported,'unsupported_claims':[],
        'summary':'未知被分配给对方','child_adaptation_suitable':True,
        'child_adaptation_evidence_index':1,'child_adaptation_reason':'普通问答'})
    with pytest.raises(llm_steps.ModelOutputError):
        llm_steps.review_story_source(transcript='未知：你先说',story_raw='对方说你先说')


def test_structure_input_does_not_leak_collection_title(monkeypatch):
    story = '弟弟问姐姐借课本。姐姐问上一本还没还，随后答应找一本给弟弟。'
    def chat(system, user, **kwargs):
        assert kwargs.get("thinking_enabled") is True
        assert story in user
        assert '标题独有的滑板比赛' not in system + user
        return {'title': '借课本', 'mechanism': 'M4', 'structure_type': 'G',
                'beat': ['借课本', '追问旧书', '回应追问', '答应找书'], 'structure_confidence': .9}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    result = llm_steps.structurize_story(title='标题独有的滑板比赛', story_raw=story)
    assert result['title'] == '借课本'


def test_core_event_veto_cannot_be_overridden_by_high_scores(monkeypatch):
    result = _audit_response(_high_fit_scores(core_event_supported=False,
        core_event_reason='承诺被写成已经完成'), monkeypatch)
    assert result['pass'] is False
    assert any('core_event_unfaithful' in reason for reason in result['reject_reasons'])


@pytest.mark.parametrize('supported', [None, 'true', 1])
def test_core_event_audit_requires_boolean(monkeypatch, supported):
    with pytest.raises(llm_steps.ModelOutputError, match='boolean'):
        _audit_response(_high_fit_scores(core_event_supported=supported), monkeypatch)


def test_uncertainty_review_changes_only_supported_status_and_keeps_original(monkeypatch):
    lines = [dict(speaker='未知', text='书在那哩', source_quote='书在那哩', status='vague'),
             dict(speaker='未知', text='拿了几本不明', source_quote='拿了几本不明', status='vague')]
    def chat(system, user, **kwargs):
        assert 'vague' not in user and 'repair_notes' not in user
        return {'reviews': [
            dict(index=1, meaning_supported=True, uncertain_facts=[], reason='指的是前文已指出的书包位置', evidence_quote='书在那哩'),
            dict(index=2, meaning_supported=False, uncertain_facts=['数量未知'], reason='原文不能确认本数', evidence_quote='拿了几本不明')]}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    note = llm_steps._review_uncertain_lines('指着书包\n书在那哩\n拿了几本不明', lines)
    assert lines[0] == dict(speaker='未知', text='书在那哩', source_quote='书在那哩', status='ok')
    assert lines[1]['status'] == 'vague' and '数量未知' in note


@pytest.mark.parametrize('change', [
    {'index': True}, {'index': 2}, {'meaning_supported': 'true'}, {'evidence_quote': '编造的证据'},
    {'uncertain_facts': None}, {'reason': ''},
])
def test_uncertainty_review_invalid_result_cannot_change_status(monkeypatch, change):
    lines = [dict(speaker='未知', text='原文', source_quote='原文', status='vague')]
    answer = dict(index=1, meaning_supported=True, uncertain_facts=[], reason='有证据', evidence_quote='原文')
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a, **kw: {'reviews': [{**answer, **change}]})
    with pytest.raises(llm_steps.ModelOutputError):
        llm_steps._review_uncertain_lines('原文', lines)
    assert lines[0]['status'] == 'vague'


def test_uncertainty_review_cannot_override_explicit_missing_content(monkeypatch):
    lines = [dict(speaker='未知', text='拿了[听不清]本', source_quote='拿了[听不清]本', status='vague')]
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a, **kw: pytest.fail('明确缺失不得复核放行'))
    assert llm_steps._review_uncertain_lines('拿了[听不清]本', lines) == ''
    assert lines[0]['status'] == 'vague'


def test_uncertainty_review_true_with_unknown_fact_cannot_pass(monkeypatch):
    lines = [dict(speaker='未知', text='拿了几本', source_quote='拿了几本', status='vague')]
    monkeypatch.setattr(llm_steps, '_chat_json', lambda *a, **kw: {'reviews': [dict(index=1, meaning_supported=True,
        uncertain_facts=['数量不确定'], reason='无法核实数量', evidence_quote='拿了几本')]})
    llm_steps._review_uncertain_lines('拿了几本', lines)
    assert lines[0]['status'] == 'vague'


def test_independent_core_review_overrides_combined_approval(monkeypatch):
    calls = []
    def chat(system, user, **kwargs):
        calls.append(system)
        if len(calls) == 1:
            return {**_high_fit_scores(), 'source_age_compatible': True, 'mapped_roles_age_compatible': True,
                    'source_age_evidence_index': 1, 'mapped_age_evidence_index': 1, 'age_reason': '儿童日常'}
        assert '独立的改编事实审核员' in system
        assert kwargs.get('thinking_enabled') is True
        assert '四维' not in user and '原视频标题' not in user
        return {'core_event_supported': False, 'core_event_reason': '原文只答应，契约却说已完成'}
    monkeypatch.setattr(llm_steps, '_chat_json', chat)
    result = llm_steps.audit_story_fit(video_title='合集标题', title='收书', story_raw='姐姐答应稍后收书。',
        conflict_core='收书', mechanism='M4', structure_type='G', speaker_map_note='',
        dialogue_seed=[{'speaker': '灿灿', 'intent': '我待会收书'}], beat=[],
        scene_contract={'closing_intent': '已经收完书'})
    assert len(calls) == 2 and not result['pass']
    assert result['core_event_reason'] == '原文只答应，契约却说已完成'


@pytest.mark.parametrize('thinking', [False, True])
def test_chat_json_truncation_is_failure_even_with_parseable_json(monkeypatch, thinking):
    class Client:
        def _chat_json(self, system, user, **kwargs):
            assert kwargs['thinking_enabled'] is thinking
            assert kwargs['max_tokens'] == (10000 if thinking else None)
            return {'pass': True}, 'length'
    monkeypatch.setattr(llm_steps, '_client', lambda: Client())
    with pytest.raises(llm_steps.ModelOutputError, match='truncated'):
        llm_steps._chat_json('system', 'user', thinking_enabled=thinking)
