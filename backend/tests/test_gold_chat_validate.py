"""gold_chat 保真机审与 Pass 2 精修测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story.gold_chat import convert as gc
from app.services.daily_story.gold_story.gold_chat.validate import (
    collect_align_issues,
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
        "line": "弟弟都道歉了，画能再画，额头先涂。",
    }
    return dlg


def _m5h_refine_fixes() -> list[dict[str, str | int]]:
    """Pass 2 mock 定点修稿 → v2 结构。"""
    return [
        {"no": 1, "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"no": 3, "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"no": 9, "line": "家规就是谁先动手谁道歉！"},
        {"no": 15, "line": "昭昭先弄画不对，灿灿也别推人。"},
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
        {"speaker": "妈妈", "line": "昭昭先弄画不对，灿灿也别推人。"},
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
    return collect_align_issues(
        story,
        structure_type="H",
        mechanism="M5",
        closing_intent=_CLOSING,
        conflict_text=kw.pop("conflict_text", _CONFLICT_5),
        **kw,
    )


def test_collect_align_issues_i_type_contract_without_quality_ready():
    """I quality_ready=False 时，gold_chat 仍须拦缺语塞/末段制敌。"""
    from app.services.daily_story.story_types import type_body_validation_enabled

    assert not type_body_validation_enabled("I")
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "灿灿", "line": "遥控器给我，我要看动画！"},
            {"speaker": "昭昭", "line": "不行，我先看新闻！"},
            {"speaker": "灿灿", "line": "你天天霸占电视，不讲理！"},
            {"speaker": "昭昭", "line": "我爱学习，你爱吗呀？"},
            {"speaker": "灿灿", "line": "我……我也爱学习啊。"},
            {"speaker": "昭昭", "line": "那你怎么不写作业嘛？"},
            {"speaker": "灿灿", "line": "我……我待会写吧。"},
            {"speaker": "昭昭", "line": "哼，就知道看电视呢。"},
            {"speaker": "灿灿", "line": "嘿嘿，一招制敌好不好！"},
            {"speaker": "昭昭", "line": "你等着，我写完作业再来抢！"},
            {"speaker": "灿灿", "line": "写作业还想着抢，你心不诚！"},
            {"speaker": "昭昭", "line": "我诚心诚意，写完就来看！"},
        ],
    }
    issues = collect_align_issues(
        story,
        structure_type="I",
        mechanism="M11",
    )
    kinds = {str(x.get("kind") or "") for x in issues}
    assert "对齐-类型契约" in kinds
    descs = " ".join(str(x.get("desc") or "") for x in issues)
    assert "语塞" in descs or "一招制敌" in descs or "制敌" in descs


def test_collect_align_issues_type_contract_covers_a_to_l_registry():
    """A–L 均进入类型契约机审路径（空对白跳过，有对白则不因未注册漏检）。"""
    from app.services.daily_story.story_types import STORY_TYPE_LABELS

    base_dlg = [
        {"speaker": "昭昭", "line": "这是我的东西，不准抢！"},
        {"speaker": "灿灿", "line": "凭什么你说了算呀？"},
        {"speaker": "昭昭", "line": "我说了算，你听着！"},
        {"speaker": "灿灿", "line": "那我偏不听你的！"},
        {"speaker": "昭昭", "line": "你再抢我就告状！"},
        {"speaker": "灿灿", "line": "你告去呀，我才不怕！"},
        {"speaker": "昭昭", "line": "哼，看你还嘴硬！"},
        {"speaker": "灿灿", "line": "我才不认输呢！"},
    ]
    for code in sorted(STORY_TYPE_LABELS.keys()):
        story = {
            "story_type": code,
            "punchline_explain": f"{code}类测试",
            "dialogue": list(base_dlg),
        }
        # 不应因未知类型抛错；特化类型可能有 issue，也可能没有
        collect_align_issues(story, structure_type=code, mechanism="")


def test_collect_align_issues_tear_not_only_si_huai():
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


def test_collect_align_issues_inverted_role_flags():
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


def test_split_align_issues_warn_kinds():
    from app.services.daily_story.gold_story.gold_chat.validate import (
        split_align_issues,
    )

    issues = [
        {"kind": "保真-M5合并", "lines": [9]},
        {"kind": "保真-互毁前文", "lines": [6]},
        {"kind": "保真-收场Invent", "lines": [20]},
    ]
    blocking, warn = split_align_issues(issues)
    assert {x["kind"] for x in blocking} == {"保真-互毁前文"}
    assert {x["kind"] for x in warn} == {"保真-M5合并", "保真-收场Invent"}


def test_refine_passes_with_only_align_warn(monkeypatch):
    dlg = _m5h_dialogue_v2()
    dlg[8] = {
        "speaker": "灿灿",
        "line": "家规就是谁先动手谁道歉！哼，我不原谅！道歉也没用！",
    }
    story = _m5h_story(dlg)
    from app.services.daily_story.gold_story.gold_chat.validate import (
        split_align_issues,
    )

    blocking, warn = split_align_issues(_issues(story))
    assert not blocking
    assert warn

    def fail_llm(*_a, **_k):
        raise AssertionError("should not call LLM when only warn")

    monkeypatch.setattr(gc, "_align_refine_with_llm", fail_llm)
    out = gc.refine_gold_chat_align(
        story,
        structure_type="H",
        mechanism="M5",
        align_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert out["dialogue"][8]["line"].startswith("家规就是")


def test_collect_align_issues_bad_pass2_flags_speaker_and_invent():
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


def test_collect_align_issues_pipeline_draft_flags_merge_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_pipeline()))}
    assert "保真-M5合并" in kinds
    assert "保真-互毁前文" in kinds or "保真-互毁对象" in kinds
    assert "保真-收场Invent" in kinds


def test_refine_gold_chat_align_applies_spot_fixes(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": _m5h_refine_fixes()}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_align(
        story,
        structure_type="H",
        mechanism="M5",
        align_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert "家规就是" in out["dialogue"][8]["line"]
    assert _issues(out) == []


def test_refine_gold_chat_align_fails_when_llm_noop(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": []}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    with pytest.raises(ValueError, match="align_refine_failed"):
        gc.refine_gold_chat_align(
            story,
            structure_type="H",
            mechanism="M5",
            align_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
            max_rounds=1,
            bail_on_structural=False,
        )


def test_refine_bails_on_structural_by_default():
    story = _m5h_story(_m5h_dialogue_bad_pass2())
    with pytest.raises(ValueError, match="align_structural"):
        gc.refine_gold_chat_align(
            story,
            structure_type="H",
            mechanism="M5",
            align_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
        )


def test_gold_story_to_gold_chat_runs_align_pass(monkeypatch):
    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "对齐精修" in system or "保真精修" in system:
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
    _real_refine = gc.refine_gold_chat_align

    def refine_test(*args, **kwargs):
        kwargs["bail_on_structural"] = False
        return _real_refine(*args, **kwargs)

    monkeypatch.setattr(gc, "refine_gold_chat_align", refine_test)
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    out = gc.gold_story_to_gold_chat(row)
    assert "家规就是" in out["dialogue"][8]["line"]
    assert _issues(out) == []


def test_patch_fix_mom_ask_admission():
    from app.services.daily_story.gold_story.gold_chat.patch import (
        patch_fix_mom_ask_admission,
    )

    dlg = list(_m5h_dialogue_v2())
    dlg[13] = {"speaker": "昭昭", "line": "我不知道……"}
    story = _m5h_story(dlg)
    patched, changed = patch_fix_mom_ask_admission(story)
    assert changed
    assert "弄花" in patched["dialogue"][13]["line"] or "推" in patched["dialogue"][13]["line"]
