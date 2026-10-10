"""金故事 H0c 逐字稿修复测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.collect import llm as llm_steps
from app.services.gold_story.transcript import format_dialogue_transcript


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
                {"speaker": "妈妈", "text": "睡吧"},
                {"speaker": "宝宝", "text": "不睡"},
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
                {"speaker": "妈妈", "text": "十二点了还不睡？"},
                {"speaker": "宝宝", "text": "谁12点不到天亮"},
            ],
            "repair_confidence": 0.82,
            "repair_notes": "标题暗示母子对话",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(
        title="深夜对话",
        transcript="十二点岁 谁12点不到天亮",
        description="宝宝和妈妈",
    )
    assert out["repair_confidence"] == 0.82
    assert len(out["lines"]) == 2
    assert out["lines"][0]["speaker"] == "妈妈"


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
    assert "归属按语义，不按行序" in llm_steps._H0C_USER
    assert "允许同一 speaker 连说多行" in llm_steps._H0C_USER
    assert "孩子不得自称家长身份" in llm_steps._H2_USER
    assert "孩子不得自称家长身份" in llm_steps._H3B_SYSTEM
    assert "回声/回旋镖人称转换" in llm_steps._H3B_USER
    assert "归属自洽（硬）" in llm_steps._H3A_USER


def test_repair_transcript_realigns_child_parent_identity(monkeypatch):
    """H0c：孩子行的家长身份自称归位妈妈，回声句转换人称。"""

    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "speakers": ["妈妈", "宝宝"],
            "lines": [
                {"speaker": "妈妈", "text": "你去关灯", "status": "ok"},
                {
                    "speaker": "宝宝",
                    "text": "我是你妈，你得听我的",
                    "status": "ok",
                },
                {"speaker": "宝宝", "text": "你还知道我是你妈呀？", "status": "ok"},
            ],
            "repair_confidence": 0.6,
            "repair_notes": "交替不可靠，按语义归属",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(title="关灯", transcript="去关灯 我是你妈")
    assert [line["speaker"] for line in out["lines"]] == ["妈妈", "妈妈", "宝宝"]
    assert out["lines"][1]["text"] == "我是你妈，你得听我的"
    assert out["lines"][2]["text"] == "你还知道你是我妈呀？"


def test_repair_transcript_replaces_unusable_line_with_marker(monkeypatch):
    """整行 unusable 只留 [听不清]，ASR 乱码不得留在逐字稿里。"""

    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "speakers": ["妈妈", "宝宝"],
            "lines": [
                {"speaker": "妈妈", "text": "赶紧去关灯", "status": "ok"},
                {
                    "speaker": "宝宝",
                    "text": "嗯嗯嗯呃要你去活动就拿那小活动来打啊",
                    "status": "unusable",
                },
            ],
            "repair_confidence": 0.6,
            "repair_notes": "末行整行语义不可恢复",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.repair_transcript(title="关灯", transcript="呃 关灯啊")
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
