"""gold_chat 保真机审与 Pass 2 精修测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.daily_story.gold_story import gold_chat_convert as gc
from app.services.daily_story.gold_story.gold_chat_fidelity import (
    collect_fidelity_issues,
    should_regenerate_pass1,
)

_CLOSING = "灿灿问以后还打不打架，昭昭齐声不打了，妈妈拿碘伏"
_CONFLICT_5 = "灿灿：你干嘛弄坏我的画！"


def _m5h_dialogue_v1() -> list[dict[str, str]]:
    """#5 LLM 首稿（评审前）：21 句结构，仅关键行留 bug。"""
    dlg = _m5h_dialogue_v2()
    dlg[0] = {"speaker": "昭昭", "line": "姐姐，你画啥呢？让我瞅瞅！"}
    dlg[2] = {"speaker": "昭昭", "line": "哼，小气鬼！我偏要弄你的画！"}
    dlg[8] = {"speaker": "灿灿", "line": "谁先动手谁道歉！哼，我不原谅！"}
    dlg[14] = {
        "speaker": "妈妈",
        "line": "灿灿，弟弟都道歉了，你画坏了可以再画，额头破了得先处理。",
    }
    return dlg


def _m5h_refine_fixes() -> list[dict[str, str | int]]:
    """Pass 2 mock 定点修稿 → v2 结构。"""
    return [
        {"no": 1, "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"no": 3, "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"no": 9, "line": "家规就是谁先动手谁道歉！"},
        {"no": 15, "line": "昭昭先弄画不对，灿灿你也别推人。画能重画，额头先处理。"},
        {"no": 17, "line": "以后还打不打架？"},
    ]


def _m5h_dialogue_v2() -> list[dict[str, str]]:
    """#5 修稿：机审应通过（灿灿受害、昭昭先动手）。"""
    return [
        {"speaker": "灿灿", "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"speaker": "灿灿", "line": "你看，都快画好了！"},
        {"speaker": "昭昭", "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"speaker": "灿灿", "line": "你干嘛！别碰我的纸！"},
        {"speaker": "昭昭", "line": "是你先推我的！"},
        {"speaker": "灿灿", "line": "我也抢你画撕啦！你赔！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！"},
        {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
        {"speaker": "灿灿", "line": "哼，我不原谅！"},
        {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先弄花的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先弄画不对，灿灿你也别推人。画能重画，额头先处理。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "灿灿", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
    ]


def _m5h_dialogue_bad_pass2() -> list[dict[str, str]]:
    """#5 Pass2 成稿：机审应拦 speaker 倒置 + 收场 invent。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴那儿弄啥呢？让我瞅瞅。"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你抢坏了我的画！我也有你的画！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规是谁先动手谁道歉！"},
        {"speaker": "昭昭", "line": "哼，我不原谅！"},
        {"speaker": "灿灿", "line": "道歉也没用！你赔我的画！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先动手不对，灿灿你也不该抢，都有错。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "你快点回来！"},
        {"speaker": "昭昭", "line": "嗯，姐姐不疼了。"},
    ]


def _m5h_dialogue_pipeline() -> list[dict[str, str]]:
    """Pass2 流水线产出稿（含 M5 合并 + 收场 invent）。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴那儿画啥呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你把我画抢坏了！再抢我打你了！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！哼，我不原谅！道歉也没用！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先动手不对，但灿灿你抢画也有错。弟弟都道歉了，原谅他吧。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "妈妈，我帮你拿棉签！"},
        {"speaker": "昭昭", "line": "我也去！姐姐，我扶你！"},
    ]


def _m5h_story(dialogue: list[dict[str, str]]) -> dict:
    return {
        "scene_title": "画作争夺战",
        "setting": "客厅，地上散落画纸和彩笔",
        "key": "互毁画作",
        "conflict_core": "昭昭弄坏灿灿的画，互毁扭打，妈妈调解。",
        "dialogue": dialogue,
        "punchline_explain": "H类第三方化解，妈妈定责劝和",
    }


def _issues(story: dict, **kw) -> list[dict]:
    return collect_fidelity_issues(
        story,
        structure_type="H",
        mechanism="M5",
        closing_intent=_CLOSING,
        conflict_text=kw.pop("conflict_text", _CONFLICT_5),
        **kw,
    )


def test_collect_fidelity_issues_m5h_first_draft():
    issues = _issues(_m5h_story(_m5h_dialogue_v1()))
    kinds = {str(x.get("kind") or "") for x in issues}
    assert (
        "保真-互毁前文" in kinds
        or "保真-互毁对象" in kinds
        or "保真-发起方倒置" in kinds
    )
    assert "保真-M5立规" in kinds
    assert "保真-H定责" in kinds


def test_collect_fidelity_issues_tear_not_only_si_huai():
    """「撕破/撕了」须算互毁前文依据，勿误拦 Pass1 合理稿。"""
    dlg = [
        {"speaker": "灿灿", "line": "我的画马上就好，太阳要涂成金色。"},
        {"speaker": "昭昭", "line": "我看看你画的什么嘛！"},
        {"speaker": "灿灿", "line": "别碰！你手脏，会弄脏我的画！"},
        {"speaker": "昭昭", "line": "哼，我偏要碰！哎呀，不小心撕破了。"},
        {"speaker": "灿灿", "line": "你！你故意的！我也要弄坏你的画！"},
    ]
    kinds = {x["kind"] for x in _issues(_m5h_story(dlg))}
    assert "保真-互毁前文" not in kinds


def test_collect_fidelity_issues_m5h_merged_line_passes():
    dlg = list(_m5h_dialogue_v1())
    dlg[5] = {
        "speaker": "昭昭",
        "line": "你把我画抢坏了！我也弄坏你的画！",
    }
    kinds = {x["kind"] for x in _issues(_m5h_story(dlg))}
    assert "保真-互毁前文" not in kinds
    assert "保真-互毁对象" not in kinds


def test_collect_fidelity_issues_m5h_fixed_passes():
    assert _issues(_m5h_story(_m5h_dialogue_v2())) == []


def _m5h_dialogue_no_apology() -> list[dict[str, str]]:
    """无道歉链，仅靠拒和+加码过 M5 机审。"""
    return [
        {"speaker": "灿灿", "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"speaker": "灿灿", "line": "你看，都快画好了！"},
        {"speaker": "昭昭", "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"speaker": "灿灿", "line": "你干嘛！别碰我的纸！"},
        {"speaker": "昭昭", "line": "是你先推我的！"},
        {"speaker": "灿灿", "line": "那我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "灿灿", "line": "家规是谁先动手谁担责！"},
        {"speaker": "昭昭", "line": "哼，不原谅！"},
        {"speaker": "灿灿", "line": "这画我弄了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
    ]


def test_collect_fidelity_issues_m5h_no_apology_passes():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_no_apology()))}
    assert "保真-M5加码" not in kinds


def test_collect_fidelity_issues_inverted_role_flags():
    dlg = [
        {"speaker": "灿灿", "line": "昭昭，你偷偷画什么呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密画！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你走开！再抢我就撕了它！"},
        {"speaker": "灿灿", "line": "你敢！哎呀——你推我！"},
        {"speaker": "灿灿", "line": "不给！我撕——看你还藏！"},
        {"speaker": "昭昭", "line": "哇！我的画！你赔我！"},
        {"speaker": "灿灿", "line": "你把我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "对不起……我不是故意的……"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！我不原谅你！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "是姐姐先抢我画……"},
        {"speaker": "妈妈", "line": "都有错，拉手吧。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！"},
        {"speaker": "妈妈", "line": "来，额头涂点碘伏。"},
    ]
    kinds = {x["kind"] for x in _issues(_m5h_story(dlg))}
    assert "保真-发起方倒置" in kinds


def test_repair_m5_h_scene_contract_fixes_gold5_beat_chain():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        repair_m5_h_conflict_core,
        repair_m5_h_scene_contract,
        validate_contract_role_consistency,
    )

    sc = {
        "conflict": "灿灿：你干嘛弄坏我的画！",
        "beat_chain": [
            {"beat": 1, "speaker": "灿灿", "intent": "抢看/占物：要瞅画作"},
            {"beat": 2, "speaker": "昭昭", "intent": "拒看/推搡：这是我的秘密"},
            {"beat": 3, "speaker": "灿灿", "intent": "互毁升级：抢画/推搡打架"},
        ],
    }
    core = "灿灿抢看昭昭秘密画互毁扭打，姐姐额头蹭破，弟弟道歉，妈妈调解和好。"
    fixed_core, _ = repair_m5_h_conflict_core(core, sc)
    fixed_sc, changed = repair_m5_h_scene_contract(sc, conflict_core=fixed_core)
    assert changed
    assert validate_contract_role_consistency(fixed_sc, conflict_core=fixed_core) == []
    assert fixed_sc["beat_chain"][0]["speaker"] == "灿灿"
    assert "秘密" not in fixed_sc["beat_chain"][0]["intent"]
    assert fixed_sc["beat_chain"][1]["speaker"] == "昭昭"
    assert "弄坏灿灿" in fixed_core


def test_parse_fight_question_asker_from_summary():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        _parse_fight_question_asker,
    )

    assert (
        _parse_fight_question_asker(
            "灿灿得意总结：以后还打不打架？昭昭齐声说不打了"
        )
        == "灿灿"
    )


def test_patch_split_m5_merged_line():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_split_m5_merged_line,
    )

    story = _m5h_story(_m5h_dialogue_v2())
    story["dialogue"][8] = {
        "speaker": "灿灿",
        "line": "家规就是谁先动手谁道歉！你推我，你先道歉！哼，我不原谅！",
    }
    patched, changed = patch_split_m5_merged_line(story)
    assert changed
    assert patched["dialogue"][8]["line"] == "家规就是谁先动手谁道歉！"


def test_patch_fight_question_speaker():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        collect_fidelity_issues,
        patch_fight_question_speaker,
    )

    dlg = _m5h_dialogue_no_apology()
    story = _m5h_story(dlg)
    closing = "灿灿总结：以后还打不打架？昭昭齐声说不打了"
    patched, changed = patch_fight_question_speaker(story, closing_intent=closing)
    assert changed
    assert patched["dialogue"][14]["speaker"] == "灿灿"
    after = collect_fidelity_issues(
        patched,
        structure_type="H",
        mechanism="M5",
        closing_intent=closing,
        conflict_text=_CONFLICT_5,
    )
    assert "保真-齐声问句" not in {x["kind"] for x in after}


def test_patch_m5_rule_authority_adds_prefix():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_m5_rule_authority,
    )

    story = _m5h_story(_m5h_dialogue_v2())
    story["dialogue"][8] = {
        "speaker": "灿灿",
        "line": "谁先动手谁道歉！你推我，你先道歉！",
    }
    kinds = {x["kind"] for x in _issues(story)}
    assert "保真-M5立规" in kinds
    patched, changed = patch_m5_rule_authority(story)
    assert changed
    assert patched["dialogue"][8]["line"].startswith("家规就是")
    assert "保真-M5立规" not in {x["kind"] for x in _issues(patched)}


def test_patch_m5_pre_mom_escalation_adds_escalate():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_m5_pre_mom_escalation,
    )

    dlg = _m5h_dialogue_no_apology()
    dlg[9] = {"speaker": "灿灿", "line": "你赔！还没完呢！"}
    story = _m5h_story(dlg)
    kinds = {x["kind"] for x in _issues(story)}
    assert "保真-M5加码" in kinds
    patched, changed = patch_m5_pre_mom_escalation(story)
    assert changed
    assert "保真-M5加码" not in {x["kind"] for x in _issues(patched)}


def test_split_fidelity_issues_warn_kinds():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        split_fidelity_issues,
    )

    issues = [
        {"kind": "保真-M5合并", "lines": [9]},
        {"kind": "保真-互毁前文", "lines": [6]},
        {"kind": "保真-收场Invent", "lines": [20]},
    ]
    blocking, warn = split_fidelity_issues(issues)
    assert {x["kind"] for x in blocking} == {"保真-互毁前文"}
    assert {x["kind"] for x in warn} == {"保真-M5合并", "保真-收场Invent"}


def test_refine_passes_with_only_fidelity_warn(monkeypatch):
    dlg = _m5h_dialogue_v2()
    dlg[8] = {
        "speaker": "灿灿",
        "line": "家规就是谁先动手谁道歉！哼，我不原谅！道歉也没用！",
    }
    story = _m5h_story(dlg)
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        split_fidelity_issues,
    )

    blocking, warn = split_fidelity_issues(_issues(story))
    assert not blocking
    assert warn

    def fail_llm(*_a, **_k):
        raise AssertionError("should not call LLM when only warn")

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fail_llm)
    out = gc.refine_gold_chat_fidelity(
        story,
        structure_type="H",
        mechanism="M5",
        fidelity_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert out["dialogue"][8]["line"].startswith("家规就是")


def test_collect_fidelity_issues_bad_pass2_flags_speaker_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_bad_pass2()))}
    assert "保真-M5拒和speaker" in kinds
    assert "保真-对象持有补丁" in kinds or "保真-互毁前文" in kinds
    assert "保真-收场Invent" in kinds


def test_should_regenerate_pass1_structural():
    issues = _issues(_m5h_story(_m5h_dialogue_bad_pass2()))
    assert should_regenerate_pass1(issues)


def test_should_regenerate_pass1_single_local_issue():
    dlg = _m5h_dialogue_v2()
    dlg[8] = {"speaker": "灿灿", "line": "谁先动手谁道歉！你推我，你先道歉！"}
    dlg[10] = {"speaker": "灿灿", "line": "哼，我不原谅！"}
    dlg[11] = {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"}
    issues = _issues(_m5h_story(dlg))
    assert issues
    assert not should_regenerate_pass1(issues)


def test_collect_fidelity_issues_pipeline_draft_flags_merge_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_pipeline()))}
    assert "保真-M5合并" in kinds
    assert "保真-互毁前文" in kinds or "保真-互毁对象" in kinds
    assert "保真-收场Invent" in kinds


def test_refine_gold_chat_fidelity_applies_spot_fixes(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": _m5h_refine_fixes()}

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_fidelity(
        story,
        structure_type="H",
        mechanism="M5",
        fidelity_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert "家规就是" in out["dialogue"][8]["line"]
    assert _issues(out) == []


def test_refine_gold_chat_fidelity_accepts_merged_retaliation_line(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, issues, **_kw):
        fixes = list(_m5h_refine_fixes())
        for item in issues:
            if item["kind"] in {"保真-互毁前文", "保真-互毁对象"}:
                fixes = [f for f in fixes if f["no"] not in {1, 4}]
                fixes.append({"no": 6, "line": "你把我画抢坏了！抢你画撕啦！"})
        return {"fixes": fixes}

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_fidelity(
        story,
        structure_type="H",
        mechanism="M5",
        fidelity_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert _issues(out) == []


def test_refine_gold_chat_fidelity_fails_when_llm_noop(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": []}

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    with pytest.raises(ValueError, match="fidelity_refine_failed"):
        gc.refine_gold_chat_fidelity(
            story,
            structure_type="H",
            mechanism="M5",
            fidelity_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
            max_rounds=1,
            bail_on_structural=False,
        )


def test_refine_bails_on_structural_by_default():
    story = _m5h_story(_m5h_dialogue_bad_pass2())
    with pytest.raises(ValueError, match="fidelity_structural"):
        gc.refine_gold_chat_fidelity(
            story,
            structure_type="H",
            mechanism="M5",
            fidelity_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
        )


def test_gold_story_to_gold_chat_runs_fidelity_pass(monkeypatch):
    def fake_chat(system: str, _user: str) -> dict:
        if "保真精修" in system:
            return {"fixes": _m5h_refine_fixes()}
        return _m5h_story(_m5h_dialogue_v1())

    row = {
        "id": 5,
        "title": "双胞胎画画互毁",
        "mechanism": "M5",
        "structure_type": "H",
        "conflict_core": "昭昭弄坏灿灿的画，互毁扭打，妈妈调解",
        "story_raw": "哥哥画画弟弟捣乱互毁" * 10,
        "payload": {
            "beat": ["互毁", "妈妈调解", "和好"],
            "dialogue_seed": [{"speaker": "妈妈", "intent": "谁先动手"}],
            "closing_intent": _CLOSING,
            "scene_contract": {
                "mom_lines_max": 4,
                "story_type": "H",
                "conflict": "灿灿：你干嘛弄坏我的画！",
                "beat_chain": [
                    {
                        "beat": 1,
                        "speaker": "灿灿",
                        "intent": "专心画画：展示自己的画",
                    },
                    {
                        "beat": 2,
                        "speaker": "昭昭",
                        "intent": "捣乱毁画：弄坏灿灿的画",
                    },
                ],
            },
        },
    }
    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "PASS1_REGENERATE_MAX", 1)
    _real_refine = gc.refine_gold_chat_fidelity

    def refine_test(*args, **kwargs):
        kwargs["bail_on_structural"] = False
        return _real_refine(*args, **kwargs)

    monkeypatch.setattr(gc, "refine_gold_chat_fidelity", refine_test)
    out = gc.gold_story_to_gold_chat(row)
    assert "家规就是" in out["dialogue"][8]["line"]
    assert _issues(out) == []


def _m5h_dialogue_batch276() -> list[dict[str, str]]:
    """276 字 batch 产出（专家 6/10：收场拖句+齐声问句+扯平）。"""
    return [
        {"speaker": "灿灿", "line": "你看，我画的彩虹桥，漂亮吧？"},
        {"speaker": "昭昭", "line": "哼，我画得更好看！"},
        {"speaker": "灿灿", "line": "你干嘛？别碰我的画！"},
        {"speaker": "昭昭", "line": "我就要画一笔，哎呀，不小心撕破了！"},
        {"speaker": "灿灿", "line": "你故意的！我也撕你的！"},
        {"speaker": "昭昭", "line": "哇，我的小汽车！你赔我！"},
        {"speaker": "灿灿", "line": "你先弄坏我的，你活该！"},
        {"speaker": "昭昭", "line": "我推你！哎哟，你额头破了！"},
        {"speaker": "灿灿", "line": "疼死了！你走开！"},
        {"speaker": "昭昭", "line": "对不起，我不是故意的……"},
        {"speaker": "灿灿", "line": "家规说谁先动手谁道歉。"},
        {"speaker": "灿灿", "line": "我画了好久，彩虹桥变不回来了！我不原谅你！"},
        {"speaker": "妈妈", "line": "谁先动手的？"},
        {"speaker": "昭昭", "line": "是我先撕画的，我错了……"},
        {
            "speaker": "妈妈",
            "line": "灿灿，昭昭都道歉了，你也撕了他的画，扯平吧。",
        },
        {"speaker": "灿灿", "line": "好吧，那拉手。"},
        {"speaker": "昭昭", "line": "拉手！以后还打不打架？"},
        {"speaker": "灿灿", "line": "不打了！"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "妈妈", "line": "来，额头涂点碘伏，消消毒。"},
        {"speaker": "灿灿", "line": "，我以后不撕昭昭的画了。"},
        {"speaker": "昭昭", "line": "我也不撕你的了。"},
        {"speaker": "灿灿", "line": "好呀，你画桥墩，我画桥面。"},
        {"speaker": "昭昭", "line": "拉手，以后还打不打架？不打了！"},
    ]


def test_batch276_flags_pass2_issues():
    """276 字 batch 稿须被机审拦住，交给 Pass2 修，不手改 export。"""
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_batch276()))}
    assert "保真-收场拖句" in kinds
    assert "保真-齐声问句" in kinds
    assert "保真-H定责" in kinds


def _m5h_dialogue_batch291() -> list[dict[str, str]]:
    """291 字 batch 产出：第 6 句「我也撕你的」缺灿灿先毁昭昭侧物。"""
    return [
        {"speaker": "灿灿", "line": "你看我的画，太阳要下山了，云朵是粉色的。"},
        {"speaker": "昭昭", "line": "我看看，我看看！哎呀，这云画歪了！"},
        {"speaker": "灿灿", "line": "别碰！你手上有颜料！"},
        {"speaker": "昭昭", "line": "我帮你改改……啊，撕坏了！"},
        {"speaker": "灿灿", "line": "你赔我！这是我画了好久的！"},
        {"speaker": "昭昭", "line": "哼，你的画有什么好的，我也撕你的！"},
        {"speaker": "灿灿", "line": "你走开！别碰我的画！"},
        {"speaker": "昭昭", "line": "就不走，我就要撕！"},
        {"speaker": "灿灿", "line": "啊！我的画！你赔我！"},
        {"speaker": "昭昭", "line": "你推我干嘛！我也推你！"},
        {"speaker": "灿灿", "line": "哎哟，我的额头好疼！"},
        {"speaker": "昭昭", "line": "对不起，我不是故意的，你别哭了……"},
        {"speaker": "灿灿", "line": "家规说谁先动手谁道歉，你道歉了我也不原谅！"},
        {"speaker": "灿灿", "line": "我画了好久，现在全毁了，变不回来了！"},
        {"speaker": "妈妈", "line": "谁先动手的？"},
        {"speaker": "昭昭", "line": "是我先撕画的，我错了……"},
        {"speaker": "妈妈", "line": "昭昭先撕不对，灿灿你也别推人。画能重画，额头先处理。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
    ]


def test_batch291_flags_wrong_retaliation_speaker():
    """291 字稿第 6 句「我也撕你的」须 fail：前文只有昭昭毁灿灿的画。"""
    issues = _issues(_m5h_story(_m5h_dialogue_batch291()))
    kinds = {x["kind"] for x in issues}
    assert "保真-互毁前文" in kinds
    hit = [x for x in issues if x["kind"] == "保真-互毁前文"]
    assert any(4 in x.get("lines", []) for x in hit)


def test_patch_ensure_chorus_inserts_missing_closing():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        apply_m5_h_local_patches,
        collect_fidelity_issues,
    )

    dlg = list(_m5h_dialogue_v2())
    dlg = dlg[:16] + dlg[19:]
    story = _m5h_story(dlg)
    before = {x["kind"] for x in _issues(story)}
    assert "保真-齐声问句" in before
    patched, changed = apply_m5_h_local_patches(
        story,
        closing_intent=_CLOSING,
        conflict_text=_CONFLICT_5,
    )
    assert changed
    after = collect_fidelity_issues(
        patched,
        structure_type="H",
        mechanism="M5",
        closing_intent=_CLOSING,
        conflict_text=_CONFLICT_5,
    )
    assert "保真-齐声问句" not in {x["kind"] for x in after}


def test_patch_fix_mom_ask_admission():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_fix_mom_ask_admission,
    )

    dlg = list(_m5h_dialogue_v2())
    dlg[13] = {"speaker": "昭昭", "line": "我不知道……"}
    story = _m5h_story(dlg)
    patched, changed = patch_fix_mom_ask_admission(story)
    assert changed
    assert "弄花" in patched["dialogue"][13]["line"] or "推" in patched["dialogue"][13]["line"]


def test_patch_dedupe_ne_suffix():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_dedupe_ne_suffix,
    )

    story = _m5h_story(_m5h_dialogue_v2())
    story["dialogue"][7] = {"speaker": "昭昭", "line": "呜……对不起嘛呢呢"}
    patched, changed = patch_dedupe_ne_suffix(story)
    assert changed
    assert patched["dialogue"][7]["line"].endswith("呢")
    assert not patched["dialogue"][7]["line"].endswith("呢呢")


def test_format_m5_h_pass1_beat_block():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        format_m5_h_pass1_beat_block,
    )

    block = format_m5_h_pass1_beat_block(
        conflict_text=_CONFLICT_5,
        closing_intent=_CLOSING,
    )
    assert "固定节拍表" in block
    assert "灿灿 立规" in block
    assert "还打不打架" in block


def test_patch_m5_retaliation_action():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        apply_m5_h_local_patches,
        collect_fidelity_issues,
        patch_m5_retaliation_action,
    )

    dlg = list(_m5h_dialogue_v2())
    dlg[5] = {"speaker": "灿灿", "line": "那我也撕你的画！"}
    story = _m5h_story(dlg)
    kinds = {x["kind"] for x in _issues(story)}
    assert "保真-互毁动作" in kinds
    patched, changed = patch_m5_retaliation_action(story, conflict_text=_CONFLICT_5)
    assert changed
    assert "撕啦" in patched["dialogue"][5]["line"]
    full, _ = apply_m5_h_local_patches(
        story,
        closing_intent=_CLOSING,
        conflict_text=_CONFLICT_5,
    )
    assert "撕啦" in full["dialogue"][5]["line"]
    assert "保真-互毁动作" not in {
        x["kind"]
        for x in collect_fidelity_issues(
            full,
            structure_type="H",
            mechanism="M5",
            closing_intent=_CLOSING,
            conflict_text=_CONFLICT_5,
        )
    }


def test_patch_m5_soften_premature_push_blame():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        patch_m5_soften_premature_push_blame,
    )

    dlg = [
        {"speaker": "灿灿", "line": "别碰！还没干呢！"},
        {"speaker": "昭昭", "line": "哎呀，不小心弄花了你的画！"},
        {"speaker": "灿灿", "line": "你故意的！"},
        {"speaker": "昭昭", "line": "我就碰了一下，你推我干嘛！"},
        {"speaker": "灿灿", "line": "我也抢你画撕啦！你赔！"},
        {"speaker": "灿灿", "line": "哎哟，你推我，额头蹭破皮了，好疼！"},
    ]
    story = _m5h_story(dlg)
    patched, changed = patch_m5_soften_premature_push_blame(
        story,
        conflict_text=_CONFLICT_5,
    )
    assert changed
    assert "推我" not in patched["dialogue"][3]["line"]
    assert "凶我" in patched["dialogue"][3]["line"]


def test_exported_pipeline_json_passes_fidelity():
    from app.services.daily_story.gold_story.gold_chat_fidelity import (
        split_fidelity_issues,
    )

    p = Path(__file__).resolve().parents[2] / "data/gold_story/gold_chat/BV1sh411G7aX.json"
    if not p.is_file():
        pytest.skip("no local export")
    data = json.loads(p.read_text(encoding="utf-8"))
    if str(data.get("mechanism") or "").upper() != "M5":
        pytest.skip("local export not M5+H pipeline draft")
    story = data["daily_story"]
    sc = data.get("gold_meta", {}).get("scene_contract") or {}
    closing = sc.get("closing_intent") or data.get("gold_meta", {}).get("closing_intent") or _CLOSING
    issues = collect_fidelity_issues(
        story,
        structure_type="H",
        mechanism="M5",
        closing_intent=closing,
        conflict_text=str(sc.get("conflict") or ""),
        beat_chain=sc.get("beat_chain"),
    )
    blocking, _warn = split_fidelity_issues(issues)
    assert not blocking, f"export blocking issues: {blocking}"
