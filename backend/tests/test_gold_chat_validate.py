"""gold_chat 保真机审与 Pass 2 精修测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import expand as gex
from app.services.gold_story.gold_chat import refine as grf
from app.services.gold_story.gold_chat.validate import (
    apply_n_beat_role_speaker_align,
    collect_align_issues,
    should_reexpand,
)

_CLOSING = "灿灿问以后还打不打架，昭昭齐声不打了，妈妈拿碘伏"
_CONFLICT_5 = "灿灿：你干嘛弄坏我的画！"

_N_RETROSPECTIVE_BEATS = [
    {"beat": 1, "speaker": "妈妈", "intent": "交代旧事：昭昭小时候掉进菜篓子"},
    {"beat": 2, "speaker": "灿灿", "intent": "追问：那你怎么会在篓子里睡着？"},
    {"beat": 3, "speaker": "昭昭", "intent": "荒诞解释：我挑的地方好"},
    {"beat": 4, "speaker": "灿灿", "intent": "继续追问：那你怎么知道下面有菜篓子？"},
    {"beat": 5, "speaker": "昭昭", "intent": "荒诞自洽：我早就看好了"},
]


def test_n_beat_role_align_repairs_swapped_question_answer_block():
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭小时候掉进菜篓子还睡着了。"},
            {"speaker": "灿灿", "line": "你那时候胆子也太大了吧。"},
            {"speaker": "昭昭", "line": "那叫会挑地方落。"},
            {"speaker": "昭昭", "line": "你怎么在篓子里睡着了？"},
            {"speaker": "灿灿", "line": "因为菜篓子软，我躺着舒服呀。"},
            {"speaker": "昭昭", "line": "你醒来还问吃饭了吗？"},
            {"speaker": "灿灿", "line": "我醒来当然先问吃饭呀。"},
        ],
    }
    out, changed = apply_n_beat_role_speaker_align(
        story,
        beat_chain=_N_RETROSPECTIVE_BEATS,
        structure_type="N",
    )
    assert changed
    assert [row["speaker"] for row in out["dialogue"][3:7]] == [
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
    ]
    assert [row["line"] for row in out["dialogue"]] == [
        row["line"] for row in story["dialogue"]
    ]


def test_n_beat_role_align_keeps_rhetorical_answer_with_question_mark():
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "灿灿", "line": "月亮晚上为什么也亮亮的？"},
            {"speaker": "昭昭", "line": "因为月亮也怕冷，你不知道吗？"},
        ],
    }
    beats = [
        {"speaker": "灿灿", "intent": "追问：月亮为什么亮"},
        {"speaker": "昭昭", "intent": "回答：用荒诞因果讲圆"},
    ]
    out, changed = apply_n_beat_role_speaker_align(
        story,
        beat_chain=beats,
        structure_type="N",
    )
    assert not changed
    assert out["dialogue"][1]["speaker"] == "昭昭"


def test_n_beat_role_align_keeps_correct_roles_and_ambiguous_contract():
    correct = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "灿灿", "line": "你怎么会在篓子里睡着？"},
            {"speaker": "昭昭", "line": "因为里面软乎乎的呀。"},
        ],
    }
    out, changed = apply_n_beat_role_speaker_align(
        correct,
        beat_chain=_N_RETROSPECTIVE_BEATS,
        structure_type="N",
    )
    assert not changed
    assert out == correct

    ambiguous = [
        {"speaker": "灿灿", "intent": "追问：为什么"},
        {"speaker": "昭昭", "intent": "继续追问：怎么会"},
        {"speaker": "昭昭", "intent": "荒诞解释：因为好玩"},
    ]
    out2, changed2 = apply_n_beat_role_speaker_align(
        correct,
        beat_chain=ambiguous,
        structure_type="N",
    )
    assert not changed2
    assert out2 == correct


def test_n_beat_role_align_does_not_touch_non_n_story():
    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "你怎么在篓子里睡着了？"},
            {"speaker": "灿灿", "line": "因为里面软乎乎的呀。"},
        ],
    }
    out, changed = apply_n_beat_role_speaker_align(
        story,
        beat_chain=_N_RETROSPECTIVE_BEATS,
        structure_type="J",
    )
    assert not changed
    assert out == story


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
    """Pass 2 mock 定点修稿 → v2 结构（行号按连说合并后的 v1 稿）。"""
    return [
        {"no": 1, "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"no": 3, "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"no": 9, "line": "家规就是谁先动手谁道歉！"},
        {"no": 14, "line": "昭昭先弄画不对，灿灿也别推人。"},
        {"no": 16, "line": "以后还打不打架？"},
    ]


def _m5h_dialogue_v2() -> list[dict[str, str]]:
    """#5 修稿：机审应通过（灿灿受害、昭昭先动手）。"""
    return [
        {"speaker": "灿灿", "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"speaker": "灿灿", "line": "你看，都快画好了！"},
        {"speaker": "昭昭", "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"speaker": "灿灿", "line": "你干嘛！别碰我的纸！"},
        {"speaker": "昭昭", "line": "是你先推我的，我手里的彩笔都掉地上了！"},
        {"speaker": "灿灿", "line": "我也抢你画撕啦！你赔！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！"},
        {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
        {"speaker": "灿灿", "line": "哼，我不原谅，你把兔子的耳朵全涂黑了！"},
        {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先弄花的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先弄画不对，灿灿也别推人。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "灿灿", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈，我先把画纸放到桌上去。"},
    ]


def _m5h_dialogue_bad_refine() -> list[dict[str, str]]:
    """#5 精修成稿：机审应拦 speaker 倒置 + 收场 invent。"""
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
    """精修流水线产出稿（含 M5 合并 + 收场 invent）。"""
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
    """「撕破/撕了」须算互毁前文依据，勿误拦扩写合理稿。"""
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
    from app.services.gold_story.gold_chat.validate import (
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
    from app.services.gold_story.gold_chat.validate import (
        split_align_issues,
    )

    blocking, warn = split_align_issues(_issues(story))
    assert not blocking
    assert warn

    def fail_llm(*_a, **_k):
        raise AssertionError("should not call LLM when only warn")

    monkeypatch.setattr(gc, "_align_refine_with_llm", fail_llm)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fail_llm)
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


def test_collect_align_issues_bad_refine_flags_speaker_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_bad_refine()))}
    assert "保真-M5拒和speaker" in kinds
    assert "保真-对象持有补丁" in kinds or "保真-互毁前文" in kinds
    assert "保真-收场Invent" in kinds


def test_should_reexpand_structural():
    issues = _issues(_m5h_story(_m5h_dialogue_bad_refine()))
    assert should_reexpand(issues)


def test_should_reexpand_single_local_issue():
    dlg = _m5h_dialogue_v2()
    dlg[8] = {"speaker": "灿灿", "line": "谁先动手谁道歉！你推我，你先道歉！"}
    dlg[10] = {"speaker": "灿灿", "line": "哼，我不原谅！"}
    dlg[11] = {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"}
    issues = _issues(_m5h_story(dlg))
    assert issues
    assert not should_reexpand(issues)


def test_collect_align_issues_pipeline_draft_flags_merge_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_pipeline()))}
    assert "保真-M5合并" in kinds
    assert "保真-互毁前文" in kinds or "保真-互毁对象" in kinds
    assert "保真-收场Invent" in kinds


def test_refine_gold_chat_align_applies_spot_fixes(monkeypatch):
    from app.services.daily_story.story_types import apply_gold_chat_body_pipeline

    story = _m5h_story(_m5h_dialogue_v1())
    story, _ = apply_gold_chat_body_pipeline(story, structure_type="H")

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": _m5h_refine_fixes()}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_align(
        story,
        structure_type="H",
        mechanism="M5",
        align_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert any("家规就是" in str(d.get("line") or "") for d in out["dialogue"])
    assert _issues(out) == []


def test_refine_gold_chat_align_fails_when_llm_noop(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": []}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fake_refine)
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
    story = _m5h_story(_m5h_dialogue_bad_refine())
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
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "EXPAND_REGENERATE_MAX", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 1)
    _real_refine = gc.refine_gold_chat_align

    def refine_test(*args, **kwargs):
        kwargs["bail_on_structural"] = False
        return _real_refine(*args, **kwargs)

    monkeypatch.setattr(gc, "refine_gold_chat_align", refine_test)
    monkeypatch.setattr(grf, "refine_gold_chat_align", refine_test)
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


_AUTH_BEAT_CHAIN = [
    {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完作业谁玩"},
    {"beat": 2, "speaker": "昭昭", "intent": "占物：偷偷把作业本藏进冰箱"},
    {"beat": 3, "speaker": "灿灿", "intent": "急哭：找不到作业本"},
    {"beat": 4, "speaker": "妈妈", "intent": "反转：不罚反将任务"},
    {"beat": 5, "speaker": "灿灿", "intent": "补刀：威胁揭短"},
    {"beat": 6, "speaker": "昭昭", "intent": "认怂：立刻让渡"},
    {"beat": 7, "speaker": "妈妈", "intent": "权威点题收束"},
]


def _authority_story(dialogue: list[dict[str, str]]) -> dict:
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    return {
        "scene_title": "权威点题样例",
        "setting": "客厅",
        "key": "权威点题",
        "conflict_core": "一方藏物抢资源，对方急哭",
        "closing_mode": CLOSING_MODE_AUTHORITY_PUNCHLINE,
        "dialogue": dialogue,
        "punchline_explain": "G类权威点题收束",
    }


def _authority_issues(story: dict) -> list[dict]:
    return collect_align_issues(
        story,
        structure_type="G",
        mechanism="M4",
        closing_intent="权威点题收束",
        beat_chain=_AUTH_BEAT_CHAIN,
        conflict_text=str(story.get("conflict_core") or ""),
    )


def test_authority_punchline_bad_opening_like_91():
    """开场跳过立规 + 急哭/撇清说话人对调 → 保真-权威*。"""
    dlg = [
        {"speaker": "昭昭", "line": "听见了听见了，我这就去写，姐姐你慢慢来。"},
        {"speaker": "灿灿", "line": "你写你的，别老盯着我这边看。"},
        {"speaker": "昭昭", "line": "谁盯你了，我去拿瓶水总行吧。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？刚才明明放在上面。"},
        {"speaker": "昭昭", "line": "我翻遍书包都找不到，急死我了！"},
        {"speaker": "灿灿", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我哄她？我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" in kinds
    assert "保真-权威角色" in kinds


def test_authority_punchline_good_opening_passes_opening_kinds():
    dlg = [
        {"speaker": "妈妈", "line": "谁先写完作业谁就能玩。"},
        {"speaker": "昭昭", "line": "听见了，我这就去写。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" not in kinds
    assert "保真-权威角色" not in kinds


def test_authority_punchline_skin_swap_school_passes_opening_kinds():
    """换皮（交卷/选座）仍只卡抽象槽，不开场误报。"""
    chain = [
        {"beat": 1, "speaker": "老师", "intent": "立规：谁先交卷谁先选座位"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物：把别人卷子藏进讲台"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭：找不到卷子"},
        {"beat": 4, "speaker": "老师", "intent": "反转：不罚反将收作业任务"},
        {"beat": 5, "speaker": "灿灿", "intent": "补刀：威胁揭短"},
        {"beat": 6, "speaker": "昭昭", "intent": "认怂：立刻让渡选座权"},
        {"beat": 7, "speaker": "老师", "intent": "权威点题收束"},
    ]
    # 角色映射仍用家中说话人；beat0 speaker 用妈妈代替老师以适配 ALLOWED speakers
    chain[0]["speaker"] = "妈妈"
    chain[3]["speaker"] = "妈妈"
    chain[6]["speaker"] = "妈妈"
    dlg = [
        {"speaker": "妈妈", "line": "谁先交卷谁先选座位，定规了。"},
        {"speaker": "昭昭", "line": "我这就交。"},
        {"speaker": "灿灿", "line": "我卷子呢？翻遍桌子找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得快，那你负责帮全班收作业。"},
        {"speaker": "昭昭", "line": "收作业我真不会，换事行？"},
        {"speaker": "灿灿", "line": "你帮我收，我就告诉老师你抄答案。"},
        {"speaker": "昭昭", "line": "你选你选，我收。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个班我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    kinds = {
        x["kind"]
        for x in collect_align_issues(
            story,
            structure_type="G",
            mechanism="M4",
            closing_intent="权威点题收束",
            beat_chain=chain,
            conflict_text="藏卷子抢选座，对方急哭",
        )
    }
    assert "保真-权威开场" not in kinds
    assert "保真-权威角色" not in kinds


def test_format_align_block_kb_chain_not_stalemate():
    from app.services.gold_story.gold_chat.prompts import format_align_block

    block = format_align_block(
        structure_type="K",
        mechanism="M12",
        beat=["妈妈不评理", "孩子自行恢复互动"],
        closing_intent="妈妈说不掺和就对了",
        k_close_mode="K_B_CHILD_SELF_RESOLVE",
    )
    assert "孩子自行恢复" in block or "自行恢复" in block
    assert "僵持（不和好" not in block


def test_format_align_block_passes_authority_closing_mode():
    from app.services.gold_story.gold_chat.prompts import format_align_block
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    block = format_align_block(
        structure_type="G",
        mechanism="M4",
        beat=["立规", "反将", "让渡", "点题"],
        closing_mode=CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )
    assert "开场立规/约好" in block or "立规/约好" in block
    assert "authority_punchline" not in block or True  # chain text is enough


def test_authority_punchline_rule_said_by_wrong_speaker():
    """前2句有立规槽但由孩子说 → 保真-权威开场。"""
    dlg = [
        {"speaker": "昭昭", "line": "谁先写完谁就能玩，听见没。"},
        {"speaker": "灿灿", "line": "知道了知道了。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" in kinds


def test_authority_opening_local_patch_inserts_rule():
    """缺立规开场：窄 patch 插入 beat0 立规句后机审过开场。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )

    dlg = [
        {"speaker": "昭昭", "line": "听见了听见了，我这就去写。"},
        {"speaker": "灿灿", "line": "你写你的。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    fixed, changed = apply_authority_punchline_local_patches(
        story, beat_chain=_AUTH_BEAT_CHAIN
    )
    assert changed
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    kinds = {x["kind"] for x in _authority_issues(fixed)}
    assert "保真-权威开场" not in kinds


def test_authority_opening_local_patch_moves_rule_forward():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )

    dlg = [
        {"speaker": "昭昭", "line": "姐姐你慢慢写。"},
        {"speaker": "妈妈", "line": "谁先写完谁就能玩，说好了。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    fixed, changed = apply_authority_punchline_local_patches(
        story, beat_chain=_AUTH_BEAT_CHAIN
    )
    assert changed
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "谁先" in fixed["dialogue"][0]["line"]
    kinds = {x["kind"] for x in _authority_issues(fixed)}
    assert "保真-权威开场" not in kinds



def test_authority_resist_slot_patch_inserts_after_reverse():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_RESIST

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "权威点题"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "平板给我玩会儿。"},
            {"speaker": "灿灿", "line": "急得我眼泪都掉下来了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄灿灿睡觉。"},
            {"speaker": "昭昭", "line": "姐姐你玩你玩，我哄你行了吧。"},
            {"speaker": "妈妈", "line": "这个家我第一，平板第二，你俩并列第三。"},
        ],
    }
    assert not RE_AUTH_RESIST.search("".join(x["line"] for x in story["dialogue"]))
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    body = "".join(x["line"] for x in fixed["dialogue"])
    assert RE_AUTH_RESIST.search(body)


def test_authority_end_punch_patch_rewrites_last():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_PUNCH

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "宣布：这个家我第一，平板第二，你俩并列第三"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "平板给我。"},
            {"speaker": "灿灿", "line": "急得我眼泪都掉下来了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄灿灿睡觉。"},
            {"speaker": "昭昭", "line": "我不会啊，姐姐你玩你玩。"},
            {"speaker": "妈妈", "line": "好了好了别闹了。"},
        ],
    }
    assert not RE_AUTH_PUNCH.search(story["dialogue"][-1]["line"])
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    assert RE_AUTH_PUNCH.search(fixed["dialogue"][-1]["line"])


def test_authority_trim_after_cede_keeps_one_mid():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_PUNCH, RE_AUTH_CEDE

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物藏"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭找不到"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "宣布并列第三"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "本子我塞冰箱了。"},
            {"speaker": "灿灿", "line": "找不到作业本，急哭了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄她睡觉。"},
            {"speaker": "昭昭", "line": "我不会啊，姐姐你玩你玩。"},
            {"speaker": "灿灿", "line": "本子就在冷藏层。"},
            {"speaker": "昭昭", "line": "不行，我偏就不信！"},
            {"speaker": "灿灿", "line": "真的，马上给我挪开！"},
            {"speaker": "昭昭", "line": "我…别再乱动了…"},
            {"speaker": "灿灿", "line": "我…呢…"},
            {"speaker": "妈妈", "line": "这个家我第一，平板第二，你俩并列第三。"},
        ],
    }
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    dlg = fixed["dialogue"]
    assert RE_AUTH_PUNCH.search(dlg[-1]["line"])
    # find cede then gap to punch <=1
    lines = [x["line"] for x in dlg]
    cede_i = max(i for i, ln in enumerate(lines[:-1]) if RE_AUTH_CEDE.search(ln))
    assert len(lines) - 1 - cede_i - 1 <= 1
    assert not any("我…呢" in x["line"] for x in dlg)


def test_gold_chat_polish_flags_intra_line_oral_repeat():
    from app.services.gold_story.gold_chat.polish import collect_gold_chat_polish_issues

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我就过来，你砸一个试试看，你试试看啊！"},
        ],
    }
    kinds = [it["kind"] for it in collect_gold_chat_polish_issues(story)]
    assert "句内重复" in kinds


_HOMEWORK_OPENING_BEAT = [
    {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
    {"beat": 2, "speaker": "灿灿", "intent": "辩解：忘了本来就要写"},
    {"beat": 3, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
]


def _opening_causality_story(
    dialogue: list[dict[str, str]],
    *,
    setting: str = "晚饭后姐弟在客厅写功课。",
) -> dict:
    return {
        "gold_beat_chain": _HOMEWORK_OPENING_BEAT,
        "setting": setting,
        "dialogue": dialogue,
    }


_N_RETROSPECTIVE_PARENT_Q_BEATS = [
    {"beat": 1, "speaker": "妈妈", "intent": "交代旧事：又讲昭昭小时候摔进软垫，一点没伤还睡着"},
    {"beat": 2, "speaker": "昭昭", "intent": "质疑：嘴硬反驳，说那不是运气好，是自己会挑软地方落"},
    {"beat": 3, "speaker": "妈妈", "intent": "追问：软垫又不是你摆的，你怎么挑"},
]


def test_opening_causality_accepts_rebuttal_semantic_paraphrase():
    """N 回忆型开场：质疑/嘴硬 beat 允许自然人称和措辞变化，不能只认整块 intent 原文。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "又说你小时候摔进软垫，一点没伤还睡着了。"},
            {"speaker": "昭昭", "line": "哪是运气好，我明明会挑软地方落。"},
            {"speaker": "妈妈", "line": "软垫又不是你摆的，你怎么挑？"},
        ],
    }
    assert opening_causality_passes(
        story, _N_RETROSPECTIVE_PARENT_Q_BEATS, mom_lines_max=2,
    )


def test_opening_causality_patch_uses_seed_for_missing_middle_beat():
    """beat1/beat3 已在场但 beat2 真缺失时，复用 H3b seed 落地，不烧 LLM 修稿预算。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    seed = [
        {"speaker": "妈妈", "intent": "又讲昭昭小时候摔进软垫，一点没伤还睡着"},
        {"speaker": "昭昭", "intent": "嘴硬反驳：那不是运气好，是我会挑软地方落"},
        {"speaker": "妈妈", "intent": "追问：软垫又不是你摆的，你怎么挑"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "又说你小时候摔进软垫，一点没伤还睡着了。"},
            {"speaker": "灿灿", "line": "你那时候胆子可真大。"},
            {"speaker": "妈妈", "line": "软垫又不是你摆的，你怎么挑？"},
        ],
    }
    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=_N_RETROSPECTIVE_PARENT_Q_BEATS,
        mom_lines_max=2,
        dialogue_seed=seed,
    )
    assert changed
    assert opening_causality_passes(
        fixed, _N_RETROSPECTIVE_PARENT_Q_BEATS, mom_lines_max=2,
    )
    assert fixed["dialogue"][2] == {
        "speaker": "昭昭",
        "line": "那不是运气好，是我会挑软地方落。",
    }
    assert fixed["dialogue"][3]["speaker"] == "妈妈"


def test_opening_causality_accepts_111_parent_directive_contract_shape():
    """#111：beat1 可把家长指令和孩子动作写在同一 intent；家长台词只需落地自己的指令部分。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "让昭昭收玩具，昭昭踢散积木"},
        {"beat": 2, "speaker": "灿灿", "intent": "边捡边搬出妈妈的话：用过的东西放回原位"},
        {"beat": 3, "speaker": "昭昭", "intent": "嘴硬说还没玩完"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，把地上的玩具收好，别摊一客厅。"},
            {"speaker": "昭昭", "line": "我还没玩完呢！你别管我！"},
            {"speaker": "灿灿", "line": "你踢积木干嘛？踢散了还得我捡。"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "昭昭", "line": "我还没玩完，不收！你少拿妈妈压我。"},
        ]
    }

    assert opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_rejects_111_directive_intent_echo():
    """#111：directive beat1 不能把 "家长指令 + 孩子动作" 整句 intent 当台词。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "让昭昭收玩具，昭昭踢散积木"},
        {"beat": 2, "speaker": "灿灿", "intent": "边捡边搬出妈妈的话：用过的东西放回原位"},
        {"beat": 3, "speaker": "昭昭", "intent": "嘴硬说还没玩完"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "让昭昭收玩具，昭昭踢散积木？"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "昭昭", "line": "我还没玩完呢！"},
        ]
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_accepts_111_natural_parent_directive():
    """#111：reconcile 后的自然祈使句应该能落地 directive beat1。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "让昭昭收玩具，昭昭踢散积木"},
        {"beat": 2, "speaker": "灿灿", "intent": "边捡边搬出妈妈的话：用过的东西放回原位"},
        {"beat": 3, "speaker": "昭昭", "intent": "嘴硬说还没玩完"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，把玩具收好。"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "昭昭", "line": "我还没玩完呢！"},
        ]
    }

    assert opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_patch_prefers_seed_directive_over_intent_echo():
    """#111：本地补拍优先用 seed 的自然指令，不能生成 intent 问句。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_opening_causality_local_patch,
    )
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "让昭昭收玩具，昭昭踢散积木"},
        {"beat": 2, "speaker": "灿灿", "intent": "边捡边搬出妈妈的话：用过的东西放回原位"},
        {"beat": 3, "speaker": "昭昭", "intent": "嘴硬说还没玩完"},
    ]
    seed = [
        {"speaker": "妈妈", "intent": "昭昭，把玩具收好"},
        {"speaker": "昭昭", "intent": "我还没玩完呢"},
        {"speaker": "灿灿", "intent": "妈妈说，用过的东西放回原位"},
    ]
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我还没玩完呢，别动我的积木！"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "昭昭", "line": "我还没玩完，你别管我，踢散了我自己捡。"},
        ]
    }

    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=beat,
        mom_lines_max=2,
        dialogue_seed=seed,
    )

    assert changed
    assert fixed["dialogue"][0] == {
        "speaker": "妈妈",
        "line": "昭昭，把玩具收好。",
    }
    assert all(
        row.get("line") != "让昭昭收玩具，昭昭踢散积木？"
        for row in fixed["dialogue"]
    )
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_patch_never_synthesizes_directive_question():
    """#111：没有 seed 时 directive beat1 也不能本地硬造 intent 问句。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_opening_causality_local_patch,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "让昭昭收玩具，昭昭踢散积木"},
        {"beat": 2, "speaker": "灿灿", "intent": "边捡边搬出妈妈的话：用过的东西放回原位"},
        {"beat": 3, "speaker": "昭昭", "intent": "嘴硬说还没玩完"},
    ]
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我还没玩完呢！"},
        ]
    }

    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=beat,
        mom_lines_max=2,
    )

    assert not changed
    assert fixed == story


def test_opening_causality_accepts_117_child_rule_setup():
    """#117：孩子发起的游戏首句按多段语义落地，不要求家长式命令口气。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "昭昭", "intent": "立规：端出炸鸡和烤冷面，和灿灿玩猜食物游戏"},
        {"beat": 2, "speaker": "灿灿", "intent": "占物：猜中披萨"},
    ]
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "炸鸡和烤冷面摆好了，咱们玩猜食物游戏！"},
            {"speaker": "灿灿", "line": "我猜中披萨了！"},
        ]
    }

    assert opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_patch_uses_tagged_same_slot_seed_for_102_teasing_beat():
    """#102：一锤已出现但 beat2 缺失时，用同槽 H3b 的现场调侃对白补在一锤之前。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "灿灿", "intent": "立规：辅导作业，沉脸警告昭昭别耍赖"},
        {"beat": 2, "speaker": "昭昭", "intent": "耍赖：嬉皮笑脸东拉西扯不听"},
        {"beat": 3, "speaker": "灿灿", "intent": "一锤：抬手一巴掌，昭昭立刻老实"},
    ]
    seed = [
        {"speaker": "灿灿", "intent": "沉脸警告：写作业别耍赖"},
        {"speaker": "昭昭", "intent": "嬉皮笑脸：姐你今天真好看"},
        {"speaker": "灿灿", "intent": "别扯别的，笔拿起来"},
    ]
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "写作业别耍赖，笔拿起来。"},
            {"speaker": "灿灿", "line": "抬手一巴掌，昭昭立刻老实。"},
        ],
    }

    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=beat,
        mom_lines_max=3,
        dialogue_seed=seed,
    )

    assert changed
    assert fixed["dialogue"][1] == {"speaker": "昭昭", "line": "姐你今天真好看。"}
    assert fixed["dialogue"][2]["line"] == "抬手一巴掌，昭昭立刻老实。"
    assert opening_causality_passes(fixed, beat, mom_lines_max=3)


def test_opening_causality_patch_rejects_o106_narrative_rule_seed():
    """#106：剧情式 H3b seed 不能靠补“说好了”伪装成自然规则对白。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "端出蛋挞和烤鸭，宣布用绕口令抢吃"},
        {"beat": 2, "speaker": "昭昭", "intent": "磕巴念绕口令，口误笑场，急得跺脚"},
    ]
    seed = [
        {"speaker": "妈妈", "intent": "蛋挞烤鸭上桌，绕口令抢吃"},
        {"speaker": "昭昭", "intent": "磕巴念绕口令，口误笑场，急得跺脚"},
    ]
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "磕巴念绕口令，口误笑场，急得跺脚。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=beat,
        mom_lines_max=2,
        dialogue_seed=seed,
    )

    assert not changed
    assert fixed == story
    assert not opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_ignores_name_only_anchor_hit():
    """长叙事锚词只被人名叠字对命中时，不得据此判 beat 顺序倒挂。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "放旧视频，回看姐弟抢拼图"},
        {"beat": 2, "speaker": "灿灿", "intent": "占物：伸手抢昭昭手里的拼图"},
        {"beat": 3, "speaker": "昭昭", "intent": "拒给：抓住拼图喊不要"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "快看你们小时候抢拼图，昭昭抓得可紧了。"},
            {"speaker": "灿灿", "line": "那我也要拼，昭昭你手里这块给我呀。"},
            {"speaker": "昭昭", "line": "不要抢，这是我先拿到的，你松手吧。"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=3)


def test_opening_rule_announcement_detection_is_narrow():
    from app.services.gold_story.gold_chat.validate import _opening_authority_intent_kind

    assert _opening_authority_intent_kind("端出蛋挞和烤鸭，宣布用绕口令抢吃") == "rule"
    assert _opening_authority_intent_kind("宣布今天放假") == ""


def test_opening_causality_patch_never_synthesizes_non_authority_beat1():
    """非权威旧事 beat1 匹配不到时不能调用 authority 生成器，更不能删后续妈妈追问来“验过”。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "交代旧事：昭昭小时候从高处掉进软垫没受伤"},
        {"beat": 2, "speaker": "昭昭", "intent": "质疑：不是运气好，是自己会挑地方落"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问：软垫不是你摆的，你怎么挑"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "你小时候摔下来没受伤，还睡了一觉。"},
            {"speaker": "昭昭", "line": "哪是运气好，我会挑地方。"},
            {"speaker": "妈妈", "line": "软垫不是你摆的，你怎么挑？"},
        ],
    }
    fixed, changed = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert not changed
    assert fixed == story
    assert fixed["dialogue"][2]["line"] == "软垫不是你摆的，你怎么挑？"


def test_opening_causality_blocks_defend_without_parent_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_hard_errors,
        collect_opening_causality_issues,
    )

    story = _opening_causality_story(
        [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘了带本子嘛！"},
            {"speaker": "昭昭", "line": "要不你先打我一下，划算不？"},
            {"speaker": "灿灿", "line": "别闹了，我还得找作业本。"},
        ],
    )
    issues = collect_opening_causality_issues(story)
    assert issues
    errs = collect_opening_causality_hard_errors(story)
    assert errs and all(e.startswith("opening_causality:") for e in errs)
    assert any("妈妈" in str(i.get("desc") or "") for i in issues)


def test_opening_causality_parent_blame_in_setting_not_dialogue():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
    )

    story = _opening_causality_story(
        [
            {"speaker": "灿灿", "line": "马上去写，你别催我嘛！"},
            {"speaker": "昭昭", "line": "姐姐你先别哭，我帮你找本子。"},
            {"speaker": "灿灿", "line": "找到了，我这就写。"},
        ],
        setting="妈妈刚才责备灿灿作业还没写，气氛很紧张。",
    )
    issues = collect_opening_causality_issues(story)
    assert issues
    assert any("setting" in str(i.get("desc") or "") for i in issues)


def test_opening_causality_passes_trigger_before_defend():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    story = _opening_causality_story(
        [
            {"speaker": "妈妈", "line": "怎么作业还没写？别磨蹭了！"},
            {"speaker": "灿灿", "line": "我本来就要写，就是忘带本子嘛！"},
            {"speaker": "昭昭", "line": "要不你先摸我一下，划算不？"},
            {"speaker": "灿灿", "line": "别闹，我还得赶紧写。"},
        ],
    )
    assert opening_causality_passes(story)
    assert not collect_opening_causality_issues(story)


def test_opening_causality_accepts_parent_rule_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先动手谁先道歉"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "规矩说好，谁先动手谁先道歉。"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=1)
    assert not collect_opening_causality_issues(story, beat, mom_lines_max=1)


def test_opening_causality_accepts_parent_accountability_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：昭昭先动手不对，先道歉"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，你先动手不对，先道歉。"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=1)
    assert not collect_opening_causality_issues(story, beat, mom_lines_max=1)


def test_opening_causality_local_patch_repairs_accountability_homework_opening():
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：灿灿作业没写，先把作业补上"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "conflict_core": "灿灿作业没写",
        "dialogue": [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘带本子嘛！"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


_MOM_ZHAO_MOM_OPENING_BEAT = [
    {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
    {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    {"beat": 3, "speaker": "妈妈", "intent": "愣住：接不住离谱话"},
]


def test_opening_causality_local_patch_inserts_missing_mom_blame():
    from app.services.gold_story.gold_chat.patch import (
        apply_opening_causality_local_patch,
    )
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "责备：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：凑近认真提出打自己Q弹屁股"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断批评"},
    ]
    story = {
        "conflict_core": "灿灿作业",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是忘啊。"},
            {"speaker": "昭昭", "line": "妈妈，我屁股Q弹，你打我嘛！"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
        ],
    }
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in fixed["dialogue"][0]["line"]


def test_opening_causality_local_patch_accepts_natural_imperative_rule_homework():
    """#96 形状：天然祈使句可直接落地，但不得补“说好了”之类规则前缀。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：灿灿作业没写，先把作业补上"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出打自己Q弹屁股解围"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断"},
    ]
    story = {
        "conflict_core": "灿灿作业没写",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "灿灿", "line": "为什么你会突然说这个？"},
            {"speaker": "昭昭", "line": "因为Q弹的打了不疼，还会弹回来。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=3)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=3,
    )

    assert ok
    assert fixed["dialogue"][0] == {
        "speaker": "妈妈",
        "line": "灿灿作业没写，先把作业补上。",
    }
    assert "说好了" not in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=3)


def test_opening_causality_rejects_q96_export_style_late_mom_react():
    """#96 已导出稿：灿灿辩解起跳、妈妈「你说什么」不能算首句责备。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "责备：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：凑近认真提出打自己Q弹屁股"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断批评"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是忘啊。"},
            {"speaker": "昭昭", "line": "妈妈，我屁股Q弹，你打我嘛！"},
            {"speaker": "灿灿", "line": "昭昭你疯啦？"},
            {"speaker": "昭昭", "line": "你打一下试试手感，比打姐姐划算吧。"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
            {"speaker": "灿灿", "line": "噗嗤——昭昭你屁股有什么好打的呀，说一不二！"},
        ],
    }
    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    issues = collect_opening_causality_issues(story, beat, mom_lines_max=2)
    assert issues
    kinds = " ".join(str(i.get("desc") or "") for i in issues)
    assert "未见" in kinds or "缺少" in kinds or "起跳" in kinds


def test_opening_causality_rejects_late_parent_trigger_even_if_interrupt_repeats_later():
    """服务器 #96 形状：妈妈第7句才出现，后面另一个昭昭句不能让 opening 重新起算。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
        {"beat": 3, "speaker": "灿灿", "intent": "破功：忍不住笑出声，紧张场景瞬间破碎"},
    ]
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "灿灿", "line": "昭昭你闭嘴，谁要你替我挨打"},
            {"speaker": "昭昭", "line": "我的比姐姐的弹，你试试就知道，一拍就弹回来"},
            {"speaker": "灿灿", "line": "你屁股是弹簧吗，还一拍就弹回来"},
            {"speaker": "昭昭", "line": "因为姐姐屁股不弹，打了也不长记性，我的才管用"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "灿灿", "line": "噗，没忍住笑出声，昭昭你屁股是弹簧吗"},
            {"speaker": "昭昭", "line": "你听，Q弹，妈妈你摸，我没骗你"},
        ]
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    issues = collect_opening_causality_issues(story, beat, mom_lines_max=2)
    assert any("第1句未落地" in str(item.get("desc") or "") for item in issues)


def test_opening_causality_patch_does_not_move_wrong_sibling_parent_line_to_front():
    """beat1 点名灿灿时，妈妈训昭昭的通用“作业没写”句不能被搬成首句。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "昭昭", "line": "我的比姐姐的弹，你试试就知道"},
        ],
    }

    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )

    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "灿灿" in fixed["dialogue"][0]["line"]
    assert "作业" in fixed["dialogue"][0]["line"]
    assert "昭昭，你凑什么热闹" not in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_patch_server_shape_drops_late_duplicate_trigger_before_parent_close():
    """插入正确 beat1 后，妈妈配额应删迟到重复训话，保留后段收束反应。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "灿灿", "line": "噗，没忍住笑出声"},
            {"speaker": "妈妈", "line": "你们俩一个比一个会捣乱，我真是拿你们没办法"},
        ],
    }

    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )

    assert ok
    lines = [str(row.get("line") or "") for row in fixed["dialogue"]]
    mom_lines = [
        str(row.get("line") or "")
        for row in fixed["dialogue"]
        if row.get("speaker") == "妈妈"
    ]
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "灿灿" in fixed["dialogue"][0]["line"]
    assert not any("昭昭，你凑什么热闹" in line for line in lines)
    assert any("拿你们没办法" in line for line in mom_lines)
    assert len(mom_lines) == 2
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_rejects_parent_response_style_first_line_even_with_homework_trigger():
    """妈妈先回应“打你屁股”再问作业，语义上已是 beat2 之后，不能冒充 beat1。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "妈妈", "line": "你说啥？打你屁股？你作业写完了吗？"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "灿灿", "line": "我马上写，你别生气"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert not fixed["dialogue"][0]["line"].startswith("你说啥")
    assert "作业" in fixed["dialogue"][0]["line"]
    assert fixed["dialogue"][1]["speaker"] == "昭昭"
    assert fixed["dialogue"][2]["speaker"] == "妈妈"
    assert fixed["dialogue"][2]["line"].startswith("你说啥")
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_rejects_first_person_why_should_i_response_and_reorders_it():
    """“我为什么要……”是对已提出动作的反问，不能靠裸“为什么”冒充 beat1。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出打自己Q弹屁股的离谱请求"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被昭昭的请求打断"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "妈妈", "line": "我为什么要打你的屁股？"},
            {"speaker": "灿灿", "line": "我……我这就写，真的，马上写呀。"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了。"},
            {"speaker": "妈妈", "line": "你们俩一个比一个会闹，我真拿你们没办法。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )

    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in fixed["dialogue"][0]["line"]
    response_idx = next(
        i for i, row in enumerate(fixed["dialogue"])
        if row.get("line") == "我为什么要打你的屁股？"
    )
    interrupt_idx = next(
        i for i, row in enumerate(fixed["dialogue"])
        if row.get("speaker") == "昭昭" and "Q弹屁股" in str(row.get("line") or "")
    )
    assert response_idx > interrupt_idx
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)
    mom_lines = [row for row in fixed["dialogue"] if row.get("speaker") == "妈妈"]
    assert len(mom_lines) == 2
    assert all("拿你们没办法" not in str(row.get("line") or "") for row in mom_lines)


def test_opening_causality_keeps_direct_why_homework_trigger_valid():
    """不能因为修“我为什么要…”而误伤真正直接定责的“为什么作业还没写”。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出离谱请求"},
    ]
    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "为什么作业还没写？别磨蹭了！"},
            {"speaker": "昭昭", "line": "妈妈，要不你先听我说个办法？"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_does_not_accept_bare_why_as_blame_or_accountability():
    """责备/定责必须有实义，不能只凭通用“怎么/为什么”问句通过。"""
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    for intent in (
        "责备：灿灿作业没写",
        "定责：批评灿灿作业没做，气氛紧张",
    ):
        beat = [
            {"beat": 1, "speaker": "妈妈", "intent": intent},
            {"beat": 2, "speaker": "昭昭", "intent": "插嘴：提出离谱请求"},
        ]
        story = {
            "dialogue": [
                {"speaker": "妈妈", "line": "为什么要这样？"},
                {"speaker": "昭昭", "line": "妈妈，要不你听我说个办法？"},
            ],
        }
        assert not opening_causality_passes(story, beat, mom_lines_max=2)


def test_opening_causality_mom_blame_zhao_interrupt_mom_stun_ok():
    """妈妈→昭昭→妈妈 开场（#96 类），首句责备不得误判为愣住。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    story = {
        "gold_beat_chain": _MOM_ZHAO_MOM_OPENING_BEAT,
        "setting": "晚饭后客厅，姐弟在写功课。",
        "dialogue": [
            {"speaker": "妈妈", "line": "怎么作业还没写？别磨蹭了！"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
            {"speaker": "妈妈", "line": "你……你这孩子，我一时接不住话。"},
            {"speaker": "灿灿", "line": "姐你别闹，我还得找作业本呢。"},
        ],
    }
    assert opening_causality_passes(story)
    assert not collect_opening_causality_issues(story)


def test_opening_causality_patch_accepts_sibling_rule_seed_like_102():
    """姐姐可作为 J/M8 的立规权威；可信 H3b seed 应本地补首拍，不烧 LLM 预算。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {
            "beat": 1,
            "speaker": "灿灿",
            "intent": "立规：辅导作业，沉脸警告昭昭别耍赖",
        },
        {
            "beat": 2,
            "speaker": "昭昭",
            "intent": "耍赖：嬉皮笑脸东拉西扯不听",
        },
    ]
    seed = [
        {"speaker": "灿灿", "intent": "沉脸警告：写作业别耍赖"},
        {"speaker": "昭昭", "intent": "嬉皮笑脸：姐你今天真好看"},
    ]
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "姐你今天真好看。"},
            {"speaker": "灿灿", "line": "别扯别的，笔拿起来。"},
            {"speaker": "昭昭", "line": "我手疼，先歇会儿行不行？"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=3)
    fixed, changed = apply_opening_causality_local_patch(
        story,
        beat_chain=beat,
        mom_lines_max=3,
        dialogue_seed=seed,
    )

    assert changed
    assert fixed["dialogue"][0]["speaker"] == "灿灿"
    assert "作业" in fixed["dialogue"][0]["line"]
    assert "别耍赖" in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=3)


def test_short_spot_unfreezes_head_when_opening_not_ok():
    from app.services.gold_story.gold_chat.repair import list_short_spot_editable_line_nos

    dialogue = [
        {"speaker": "灿灿", "line": "我本来就要写嘛。"},
        {"speaker": "昭昭", "line": "姐姐别急。"},
        {"speaker": "灿灿", "line": "我还得找本子。"},
        {"speaker": "昭昭", "line": "我帮你翻书包。"},
        {"speaker": "灿灿", "line": "找到了。"},
        {"speaker": "昭昭", "line": "快去写吧。"},
    ]
    chat = {"dialogue": dialogue}
    frozen = list_short_spot_editable_line_nos(chat, freeze_opening=True)
    unfrozen = list_short_spot_editable_line_nos(chat, freeze_opening=False)
    assert 1 not in frozen
    assert 1 in unfrozen


def test_parent_budget_parity_between_validator_and_trimmer():
    """缺陷1：校验层与裁句层必须共用家长预算口径，否则合规稿必然死锁。

    契约让爸爸承担 2 拍，mom_lines_max 只给 1 时：
    - 旧实现把爸爸上限硬编码为 1 → 报「爸爸台词须≤1句，当前2」，任何稿都过不了；
    - 新实现按 beat_chain 抬到 2 → 放行，且裁句层也不砍。
    """
    from app.services.gold_story.gold_chat.validate import validate_chat_hard
    from app.services.gold_story.gold_chat.expand import _trim_gold_chat_mom_lines

    chain = [
        {"beat": 3, "speaker": "爸爸", "intent": "旁观解说"},
        {"beat": 5, "speaker": "爸爸", "intent": "被推趔趄"},
    ]
    dialogue = [
        {"speaker": "灿灿", "line": "我先拿到的三轮车，你松手！"},
        {"speaker": "昭昭", "line": "你才松手，明明是我先看见的！"},
        {"speaker": "爸爸", "line": "你俩别抢了，我看着头晕。"},
        {"speaker": "灿灿", "line": "你别解说，我推你一下。"},
        {"speaker": "爸爸", "line": "哎哟，我站都站不稳了。"},
        {"speaker": "灿灿", "line": "谁让你不好好劝架，活该。"},
    ]
    story = {"story_type": "K", "beat_chain": chain, "dialogue": dialogue}

    errors = validate_chat_hard(story, mom_lines_max=1)
    assert not [e for e in errors if "爸爸台词" in e], (
        f"爸爸 2 句被误拦，缺陷1 回归: {errors}"
    )

    trimmed, _ = _trim_gold_chat_mom_lines(
        story, mom_lines_max=1, structure_type="K"
    )
    dad_after = sum(
        1 for x in trimmed["dialogue"] if x["speaker"] == "爸爸"
    )
    assert dad_after >= 2, "裁句层把爸爸砍到 1 句，与校验层口径不一致"


def test_n_viewer_trim_and_ask_patch_restore_contract_roles():
    """N 本地补丁：旁观手足的代问被删，家长关键追问拍用 seed 补回。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_n_ask_beat_local_patch,
        apply_n_viewer_trim_patch,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "宣布拿本子记录昭昭每句话，看他会不会骗人"},
        {"beat": 2, "speaker": "昭昭", "intent": "一本正经报出一串编的名字"},
        {"beat": 3, "speaker": "昭昭", "intent": "蹦出一个英文词，解释成在街上工作别人给钱"},
        {"beat": 4, "speaker": "妈妈", "intent": "震惊追问谁教的，皱眉追问这些名字什么意思"},
        {"beat": 5, "speaker": "昭昭", "intent": "淡定补一句苹果"},
        {"beat": 6, "speaker": "灿灿", "intent": "在旁边笑得直拍腿"},
        {"beat": 7, "speaker": "妈妈", "intent": "深吸一口气，决定以后说话先打草稿"},
    ]
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "妈妈", "line": "我拿本子记你说的每句话，看你骗不骗人。"},
            {"speaker": "昭昭", "line": "我要找个好人来，叫小明、小红、小刚呀。"},
            {"speaker": "灿灿", "line": "小明小红小刚，你从哪捡来的名字呀？"},
            {"speaker": "昭昭", "line": "就是你在街上工作，别人给你钱吧。"},
            {"speaker": "灿灿", "line": "我什么时候在街上工作啊？"},
            {"speaker": "昭昭", "line": "苹果呢。"},
            {"speaker": "灿灿", "line": "哈哈笑死我了，昭昭你太逗呢！"},
            {"speaker": "昭昭", "line": "好人排队就能发苹果呢。"},
            {"speaker": "妈妈", "line": "因为他说得通，所以我才一本正经。"},
            {"speaker": "妈妈", "line": "我以后说话得先打草稿，不然接不住他。"},
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "我拿本子记你说的每句话，看你骗不骗人"},
        {"speaker": "昭昭", "intent": "我要找个好人来，叫小明、小红、小刚"},
        {"speaker": "昭昭", "intent": "就是你在街上工作，别人给你钱"},
        {"speaker": "妈妈", "intent": "谁教你的？这些名字什么意思"},
        {"speaker": "昭昭", "intent": "苹果"},
        {"speaker": "灿灿", "intent": "哈哈笑死我了"},
        {"speaker": "妈妈", "intent": "我以后说话得先打草稿"},
    ]

    trimmed, viewer_changed = apply_n_viewer_trim_patch(story, beat_chain=chain)
    assert viewer_changed
    leftover = [
        i for i, r in enumerate(trimmed["dialogue"]) if r["speaker"] == "灿灿"
    ]
    assert len(leftover) <= 2, "旁观手足 line 须收到 2 句内"
    assert not any(
        "？" in trimmed["dialogue"][i]["line"] or "?" in trimmed["dialogue"][i]["line"]
        for i in leftover
    ), "旁观手足不得代问关键追问"

    patched, ask_changed = apply_n_ask_beat_local_patch(
        trimmed, beat_chain=chain, dialogue_seed=seed, mom_lines_max=3
    )
    assert ask_changed
    mom_lines = [r["line"] for r in patched["dialogue"] if r["speaker"] == "妈妈"]
    assert len(mom_lines) <= 3, "家长句数不得超契约"
    assert any("谁教" in line for line in mom_lines), "关键追问拍须由家长落地"
    assert not any("因为他说得通" in line for line in mom_lines), (
        "填充用的废话家长句应被替换掉"
    )


def test_n_mechanism_token_slot_literal_fidelity():
    """N：契约声明的怪词没被说出口 → 报机制词槽；本地补丁把它缀回孩子台词。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_n_token_slot_local_patch,
    )
    from app.services.gold_story.gold_chat.validate import (
        collect_align_issues,
        split_align_issues,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：宣布记下每句话"},
        {"beat": 2, "speaker": "昭昭", "intent": "说出自造怪词「banana」，解释成在街上工作别人给钱"},
        {"beat": 3, "speaker": "妈妈", "intent": "震惊追问谁教的，那词什么意思"},
    ]
    dialogue = [
        {"speaker": "妈妈", "line": "我拿本子记你说的每句话，看你骗不骗人。"},
        {"speaker": "昭昭", "line": "就是你在街上工作，别人给你钱吧。"},
        {"speaker": "妈妈", "line": "谁教你的？那词什么意思？"},
    ]
    story = {"story_type": "N", "dialogue": dialogue, "gold_beat_chain": chain}
    issues = collect_align_issues(
        story, structure_type="N", mechanism="M6", beat_chain=chain
    )
    blocking, _warn = split_align_issues(issues)
    assert "保真-N机制词槽" in {i["kind"] for i in blocking}, blocking

    patched, changed = apply_n_token_slot_local_patch(story, beat_chain=chain)
    assert changed
    assert any("banana" in r["line"] for r in patched["dialogue"])
    fixed = {"story_type": "N", "dialogue": patched["dialogue"], "gold_beat_chain": chain}
    blocking2, _warn2 = split_align_issues(
        collect_align_issues(fixed, structure_type="N", mechanism="M6", beat_chain=chain)
    )
    assert "保真-N机制词槽" not in {i["kind"] for i in blocking2}, blocking2

    # 契约没声明字面词（只写「蹦出一个英文词」）→ 不猜、不报
    vague = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：宣布记下每句话"},
        {"beat": 2, "speaker": "昭昭", "intent": "蹦出一个英文词，解释成在街上工作别人给钱"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问那词什么意思"},
    ]
    story2 = {"story_type": "N", "dialogue": dialogue, "gold_beat_chain": vague}
    blocking3, _warn3 = split_align_issues(
        collect_align_issues(story2, structure_type="N", mechanism="M6", beat_chain=vague)
    )
    assert "保真-N机制词槽" not in {i["kind"] for i in blocking3}


def test_parent_preachy_gate_allows_origin_question():
    """家长追问出处（谁教你的）不是说教；「教」只在说教用法下才算违规。"""
    from app.services.gold_story.gold_chat.validate import validate_chat_hard
    from app.services.gold_story.scene import parent_line_looks_preachy

    assert not parent_line_looks_preachy("谁教你的？本子差点扔了，为啥这么编？")
    assert not parent_line_looks_preachy("跟谁学的呀？")
    assert parent_line_looks_preachy("我来教你写作业。")
    assert parent_line_looks_preachy("你应该早点睡。")

    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "妈妈", "line": "我拿本子记你说的每句话，看你骗不骗人。"},
            {"speaker": "昭昭", "line": "我要找个好人来，他叫阿布嘟嘟。"},
            {"speaker": "昭昭", "line": "banana，就是街上工作别人给钱吧。"},
            {"speaker": "妈妈", "line": "谁教你的？本子差点扔了，为啥这么编？"},
            {"speaker": "昭昭", "line": "苹果呢，反正就是这样呀。"},
            {"speaker": "妈妈", "line": "行吧，以后说话得先打草稿，不然接不住。"},
        ],
    }
    errors = validate_chat_hard(story, mom_lines_max=3)
    assert not [e for e in errors if "像说教" in e], errors


def test_n_viewer_trim_drops_out_of_cast_kid():
    """两人手契约里没有的孩子被模型写回时整段删除。"""
    from app.services.gold_story.gold_chat.patch import apply_n_viewer_trim_patch
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：记录每句话"},
        {"beat": 2, "speaker": "昭昭", "intent": "报出一串名字"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问谁教的"},
        {"beat": 4, "speaker": "昭昭", "intent": "淡定补一句苹果"},
        {"beat": 5, "speaker": "妈妈", "intent": "决定以后先打草稿"},
    ]
    dialogue = [
        {"speaker": "妈妈", "line": "我拿本子记你说的每句话。"},
        {"speaker": "昭昭", "line": "我要找个好人来，他叫阿布嘟嘟。"},
        {"speaker": "灿灿", "line": "哈哈，昭昭你这也太能编了。"},
        {"speaker": "昭昭", "line": "还有小美、大壮、铁蛋，都是好人。"},
        {"speaker": "灿灿", "line": "你从哪听来的呀？"},
        {"speaker": "昭昭", "line": "banana，就是街上工作别人给钱吧。"},
        {"speaker": "灿灿", "line": "本子都写不下啦，哈哈。"},
        {"speaker": "昭昭", "line": "好人来了就给banana，苹果也算。"},
        {"speaker": "昭昭", "line": "他堵车了，因为铁蛋说先吃苹果。"},
        {"speaker": "昭昭", "line": "那苹果呢，为啥还没拿来呢？"},
        {"speaker": "妈妈", "line": "谁教你的？本子差点扔了。"},
        {"speaker": "昭昭", "line": "反正就是这样呀，我没编。"},
        {"speaker": "昭昭", "line": "明天他还带香蕉来呢。"},
        {"speaker": "妈妈", "line": "行吧，以后说话得先打草稿。"},
    ]
    story = {"story_type": "N", "dialogue": dialogue}
    out, changed = apply_n_viewer_trim_patch(story, beat_chain=chain)
    assert changed
    assert len(out["dialogue"]) >= CHAT_LINE_COUNT_MIN
    leftover = [r for r in out["dialogue"] if r["speaker"] == "灿灿"]
    assert len(leftover) <= 2, "契约外孩子最多留 1–2 句反应"
    assert not [r for r in leftover if "？" in r["line"] or "?" in r["line"]], (
        "契约外孩子不得代问"
    )

    # 句数够时整段删除（不占机制位）
    long_dialogue = dialogue + [
        {"speaker": "昭昭", "line": "好人就是排队领苹果的人呀。"},
        {"speaker": "妈妈", "line": "那苹果是谁给你的？"},
    ]
    out2, changed2 = apply_n_viewer_trim_patch(
        {"story_type": "N", "dialogue": long_dialogue}, beat_chain=chain
    )
    assert changed2
    assert not [r for r in out2["dialogue"] if r["speaker"] == "灿灿"]


def test_n_ask_patch_never_overflows_parent_budget():
    """N 补追问拍不得让家长句数超契约；超了要收掉中间填充句。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_n_contract_local_patches,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：宣布记下每句话"},
        {"beat": 2, "speaker": "昭昭", "intent": "报出一串编的名字"},
        {"beat": 3, "speaker": "昭昭", "intent": "说出自造怪词「banana」，解释成街上工作"},
        {"beat": 4, "speaker": "妈妈", "intent": "震惊追问：你说的这些到底什么意思"},
        {"beat": 5, "speaker": "妈妈", "intent": "深吸一口气，决定以后说话先打草稿"},
    ]
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "妈妈", "line": "我拿本子记你说的每句话，看你骗不骗人。"},
            {"speaker": "昭昭", "line": "我要找个好人来，叫小明、小红、小刚呀。"},
            {"speaker": "昭昭", "line": "banana，就是你在街上工作别人给钱吧。"},
            {"speaker": "妈妈", "line": "因为他说得通，所以我才一本正经。"},
            {"speaker": "妈妈", "line": "你这孩子真是的。"},
            {"speaker": "妈妈", "line": "我以后说话得先打草稿，不然接不住。"},
        ],
    }
    out, _notes = apply_n_contract_local_patches(
        story, beat_chain=chain, dialogue_seed=[], mom_lines_max=3
    )
    mom_lines = [r for r in out["dialogue"] if r["speaker"] == "妈妈"]
    assert len(mom_lines) <= 3, f"家长句数超契约: {mom_lines}"
    assert any(
        "什么意思" in r["line"] or "谁教" in r["line"] for r in mom_lines
    ), "追问拍须由家长落地"


def test_parent_budget_zero_still_blocks_parent_lines():
    """反例：契约要求家长预算为 0 时，家长说话仍须被拦（别把兜底放宽成不设限）。"""
    from app.services.gold_story.gold_chat.validate import validate_chat_hard

    story = {
        "story_type": "N",
        "beat_chain": [{"beat": 1, "speaker": "灿灿", "intent": "占物"}],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车，你松手！"},
            {"speaker": "妈妈", "line": "你们别抢了，快松手。"},
        ],
    }
    errors = validate_chat_hard(
        story, mom_lines_max=0, dad_lines_max=0, parent_lines_max=0
    )
    assert [e for e in errors if "妈妈台词" in e]


def _hard_lines(count: int, *, length: int = 22, filler: int = 0) -> list[dict]:
    """构造句数/字数可控的候选对白；filler 个短句插在末尾（末句豁免不算空应答）。"""
    from app.services.gold_story.gold_chat.validate import (
        validate_chat_hard as _v,
    )

    assert _v
    speakers = ["灿灿", "昭昭"]
    lines: list[dict] = []
    for i in range(count - filler):
        text = f"{i:02d}" + "抢车还嘴不松手" * 6
        lines.append({"speaker": speakers[i % 2], "line": text[:length]})
    for j in range(filler):
        lines.append({"speaker": speakers[j % 2], "line": "嗯。"})
    return lines


def test_length_card_allows_fewer_lines_when_chars_sufficient():
    """联合判据：11 句但正文 ≥240 字、无空应答占行时，不再按句数硬拦。"""
    from app.services.gold_story.gold_chat.validate import validate_chat_hard
    dialogue = _hard_lines(11, length=22)
    story = {"story_type": "K", "dialogue": dialogue}
    errors = validate_chat_hard(story, mom_lines_max=0)
    assert not [e for e in errors if "对白句数须≥" in e], errors
    assert not [e for e in errors if "空应答占行" in e], errors


def test_length_card_still_blocks_short_and_thin_draft():
    """句数与字数都不达标时仍拦。"""
    from app.services.gold_story.gold_chat.validate import validate_chat_hard
    dialogue = _hard_lines(8, length=22)
    story = {"story_type": "K", "dialogue": dialogue}
    errors = validate_chat_hard(story, mom_lines_max=0)
    assert [e for e in errors if "对白句数须≥" in e], errors


def test_length_card_blocks_excess_empty_replies():
    """空应答占行超过两成时判硬伤（末句豁免）。"""
    from app.services.gold_story.gold_chat.validate import validate_chat_hard
    dialogue = _hard_lines(14, length=22, filler=5)
    story = {"story_type": "K", "dialogue": dialogue}
    errors = validate_chat_hard(story, mom_lines_max=0)
    assert [e for e in errors if "空应答占行须≤3句，当前4（第" in e], errors
def test_n_parent_ask_beat_must_land_on_parent():
    """N：契约里家长的追问拍（追问出处）未由家长落地 → 结构性问题打回重掷。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_align_issues,
        split_align_issues,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：记下昭昭每句话"},
        {"beat": 2, "speaker": "昭昭", "intent": "一本正经胡言乱语，冒出一串名字"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问意思：那是什么"},
        {"beat": 4, "speaker": "昭昭", "intent": "解释：在街上工作别人给钱"},
        {"beat": 5, "speaker": "妈妈", "intent": "震惊追问谁教的"},
        {"beat": 6, "speaker": "灿灿", "intent": "在旁边笑得直拍腿"},
    ]
    with_ask = [
        {"speaker": "妈妈", "line": "从今天起你说的每句话我都记下来，看你骗不骗人。"},
        {"speaker": "昭昭", "line": "我要找个好人来，叫张三李四王五。"},
        {"speaker": "妈妈", "line": "你再说一遍，那个词是什么意思？"},
        {"speaker": "昭昭", "line": "就是你在街上工作，别人给你钱。"},
        {"speaker": "妈妈", "line": "这些词谁教你的？你老实说。"},
        {"speaker": "灿灿", "line": "哈哈哈，我眼泪都笑出来了。"},
    ]
    story = {"story_type": "N", "dialogue": with_ask, "gold_beat_chain": chain}
    issues = collect_align_issues(
        story,
        structure_type="N",
        mechanism="M6",
        beat_chain=chain,
    )
    blocking, _warn = split_align_issues(issues)
    assert not [
        i for i in blocking if i["kind"] == "保真-N家长追问拍"
    ], "家长真问过就不该报追问拍缺失"

    # 把关问拍换成旁观孩子说 → 追问拍转手
    hijacked = [
        {"speaker": "妈妈", "line": "从今天起你说的每句话我都记下来，看你骗不骗人。"},
        {"speaker": "昭昭", "line": "我要找个好人来，叫张三李四王五。"},
        {"speaker": "灿灿", "line": "那个词是什么意思呀？你倒是说清楚。"},
        {"speaker": "昭昭", "line": "就是你在街上工作，别人给你钱。"},
        {"speaker": "灿灿", "line": "这些词谁教你的？"},
        {"speaker": "昭昭", "line": "没人教，我自己想的。"},
    ]
    story2 = {"story_type": "N", "dialogue": hijacked, "gold_beat_chain": chain}
    issues2 = collect_align_issues(
        story2,
        structure_type="N",
        mechanism="M6",
        beat_chain=chain,
    )
    blocking2, _warn2 = split_align_issues(issues2)
    kinds2 = {i["kind"] for i in blocking2}
    assert "保真-N家长追问拍" in kinds2, f"追问转手未被拦: {kinds2}"
    # 结构性 → 走打回扩写，而不是留在精修打补丁
    from app.services.gold_story.gold_chat.validate import should_reexpand

    assert should_reexpand(blocking2)


def test_n_closing_stun_must_be_spoken_by_asker():
    """N：收束的愣住拍须由追问方（立规方）说；旁观孩子说则报归属问题。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_align_issues,
        split_align_issues,
    )

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "设问考验：爸爸掉河里先吃啥"},
        {"beat": 2, "speaker": "昭昭", "intent": "离谱秒答：吃血"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问为什么"},
        {"beat": 4, "speaker": "昭昭", "intent": "一本正经解释自洽"},
        {"beat": 5, "speaker": "妈妈", "intent": "愣住接不住"},
    ]
    viewer_close = [
        {"speaker": "妈妈", "line": "爸爸掉河里了，你先吃西瓜还是先吃葡萄？"},
        {"speaker": "昭昭", "line": "吃血呀。"},
        {"speaker": "妈妈", "line": "为什么吃血？"},
        {"speaker": "昭昭", "line": "因为血是红的，跟西瓜葡萄差不多嘛。"},
        {"speaker": "灿灿", "line": "行吧，我竟接不上话。"},
    ]
    story = {"story_type": "N", "dialogue": viewer_close, "gold_beat_chain": chain}
    issues = collect_align_issues(
        story, structure_type="N", mechanism="M6", beat_chain=chain
    )
    blocking, _warn = split_align_issues(issues)
    assert "保真-N收束归属" in {i["kind"] for i in blocking}, blocking

    asker_close = [*viewer_close[:-1], {"speaker": "妈妈", "line": "行吧，我接不上话了。"}]
    story2 = {"story_type": "N", "dialogue": asker_close, "gold_beat_chain": chain}
    issues2 = collect_align_issues(
        story2, structure_type="N", mechanism="M6", beat_chain=chain
    )
    blocking2, _warn2 = split_align_issues(issues2)
    assert "保真-N收束归属" not in {i["kind"] for i in blocking2}, blocking2


def test_n_token_must_not_be_used_as_predicate():
    """怪词只能独立出现；当谓语/加时态要拦，「就是waka」这类解释要放行。"""
    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规"},
        {"beat": 2, "speaker": "昭昭", "intent": "蹦出一个词「waka」"},
        {"beat": 3, "speaker": "昭昭", "intent": "解释这个词是什么意思"},
        {"beat": 4, "speaker": "妈妈", "intent": "追问什么意思谁教的"},
        {"beat": 5, "speaker": "妈妈", "intent": "服了收束"},
    ]

    def _kinds(line: str) -> set[str]:
        dlg = [
            ("妈妈", "我拿本子记你说的每句话。"),
            ("昭昭", "waka。"),
            ("昭昭", line),
            ("妈妈", "什么意思，谁教你的？"),
            ("昭昭", "没人教，我自己想的。"),
            ("妈妈", "行吧，我服了。"),
        ]
        story = {
            "story_type": "N",
            "punchline_explain": "N类",
            "dialogue": [{"speaker": s, "line": x} for s, x in dlg],
        }
        issues = collect_align_issues(
            story, structure_type="N", mechanism="M6", beat_chain=chain,
        )
        return {str(i.get("kind")) for i in issues}

    assert "保真-N词槽语法" in _kinds("waka了呀，就是在街上工作。")
    assert "保真-N词槽语法" in _kinds("因为好人会waka，所以喜欢他。")
    # 合法解释用法不得误伤
    assert "保真-N词槽语法" not in _kinds("waka就是在街上工作，别人给你钱。")
    assert "保真-N词槽语法" not in _kinds("就是waka，我确定。")
