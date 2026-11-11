from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.script.board_timeline import (
    _material_timeline_table,
    hard_max_chars,
    material_timeline_length_budget,
    narration_range_for_timeline,
    parse_video_timeline,
    validate_timeline_script,
)


def test_parse_video_timeline_balls():
    raw = json.dumps(
        {
            "duration_sec": 14.0,
            "balls": [
                {
                    "index": 1,
                    "year": 1930,
                    "country": "乌拉圭",
                    "ball_name": "T-model",
                    "start_sec": 0,
                    "end_sec": 8,
                    "duration_sec": 8,
                },
                {
                    "index": 2,
                    "year": 1934,
                    "country": "意大利",
                    "ball_name": "Federale 102",
                    "start_sec": 8,
                    "end_sec": 14,
                    "duration_sec": 6,
                },
            ],
        },
        ensure_ascii=False,
    )
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    assert len(timeline.slots) == 2
    assert timeline.slots[0].scene == "1930年 乌拉圭 T-model"
    assert timeline.slots[0].max_chars == 32
    assert timeline.slots[1].max_chars == 24


def test_validate_timeline_script_rejects_wrong_count():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    err, warnings = validate_timeline_script({"segments": []}, timeline)
    assert err is not None
    assert "1" in err
    assert warnings == []


def test_validate_timeline_script_slight_over_target_passes_with_warning():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    target = timeline.slots[0].max_chars
    text = "字" * (target + 2)
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, warnings = validate_timeline_script(script, timeline, length_mode="strict")
    assert err is None
    assert warnings


def test_validate_timeline_script_hard_limit_still_retries():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    target = timeline.slots[0].max_chars
    hard = hard_max_chars(target)
    text = "字" * (hard + 5)
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, _ = validate_timeline_script(script, timeline, length_mode="strict")
    assert err is not None
    assert "过长" in err


def test_validate_timeline_script_warn_only_accepts():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 5, "label": "A"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    text = "这是一段明显超过二十五字上限的口播内容，用来测试校验逻辑是否生效。"
    script = {"segments": [{"segment_index": 1, "text": text}]}
    err, warnings = validate_timeline_script(script, timeline, length_mode="warn_only")
    assert err is None
    assert warnings


def test_validate_timeline_script_rejects_total_too_short():
    raw = json.dumps({"items": [{"start_sec": 0, "end_sec": 8, "label": "雪崩"}]})
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    lo, _ = narration_range_for_timeline(timeline)
    short = "哇，雪崩好厉害呀。"
    script = {
        "narration": short,
        "segments": [{"segment_index": 1, "text": short}],
    }
    err, _ = validate_timeline_script(script, timeline, length_mode="strict")
    assert err is not None
    assert "总字数不足" in err
    assert str(lo) in err


def test_material_timeline_table_includes_object_name():
    raw = json.dumps(
        {
            "duration_sec": 12,
            "segments": [
                {
                    "index": 1,
                    "name": "1970年用球",
                    "description": "黑白相间经典足球外观",
                    "start_sec": 0,
                    "end_sec": 12,
                    "duration_sec": 12,
                }
            ],
        },
        ensure_ascii=False,
    )
    timeline = parse_video_timeline(raw)
    assert timeline is not None
    table = _material_timeline_table(timeline)
    assert "1970年用球" in table
    assert "黑白相间经典足球外观" in table
    assert "对象" in table
    budget = material_timeline_length_budget(timeline)
    assert "三层" in budget
    assert "字数预算" in budget


def test_material_prompts_timeline_keeps_object_and_layers():
    from app.services.script.voiceover_material import build_voiceover_material_prompts

    raw = json.dumps(
        {
            "duration_sec": 12,
            "segments": [
                {
                    "index": 1,
                    "name": "1970年用球",
                    "description": "黑白相间经典足球外观",
                    "start_sec": 0,
                    "end_sec": 12,
                    "duration_sec": 12,
                }
            ],
        },
        ensure_ascii=False,
    )
    prompts = build_voiceover_material_prompts(
        "世界杯用球",
        video_timeline=raw,
        chars_per_sec=4.1,
        need_opening=False,
    )
    assert "1970年用球" in prompts["user"]
    assert "三层" in prompts["user"]
    assert "按标点自动切分" not in prompts["system"]
    assert prompts["system"].count("禁止开场钩子") == 1


def test_video_analyzer_rejects_inconsistent_timeline():
    from app.services.material.video_analyzer import VideoAnalyzer

    analyzer = VideoAnalyzer.__new__(VideoAnalyzer)
    analyzer._duration = 20.0
    raw = json.dumps(
        {
            "title": "测试",
            "duration_sec": 20,
            "segments": [
                {
                    "index": 1,
                    "name": "甲",
                    "description": "红色圆形",
                    "start_sec": 0,
                    "end_sec": 12,
                    "duration_sec": 99,
                },
                {
                    "index": 2,
                    "name": "乙",
                    "description": "蓝色方块",
                    "start_sec": 10,
                    "end_sec": 15,
                    "duration_sec": 5,
                },
            ],
        },
        ensure_ascii=False,
    )
    with pytest.raises(ValueError):
        analyzer._validate(raw)



def _material_part(start,end,name='对象'):
    return json.dumps({'title':'素材','segments':[{'name':name,'description':'实际可见物体','start_sec':start,'end_sec':end,'duration_sec':end-start}]},ensure_ascii=False)


def test_material_batches_use_global_times_and_cover_tail():
    from app.services.material.video_analyzer import VideoAnalyzer
    from unittest.mock import patch
    analyzer=VideoAnalyzer(Path('test.mp4'),duration=26.)
    with patch.object(analyzer,'_extract_frames',return_value=([str(i) for i in range(9)],3)),patch.object(analyzer,'_call_multimodal',side_effect=[_material_part(0,12,'甲'),_material_part(12,24,'乙'),_material_part(24,26,'丙')]) as call:
        result=json.loads(analyzer.analyze())
    assert [len(c.args[2]) for c in call.call_args_list]==[4,4,1]
    assert '12.000至24.000' in call.call_args_list[1].args[1]
    assert [(s['start_sec'],s['end_sec']) for s in result['segments']]==[(0,12),(12,24),(24,26)]
    assert [s['index'] for s in result['segments']]==[1,2,3]


@pytest.mark.parametrize('start,end', [(-1,20),(0,21),(1,20),(0,19),(0,float('nan')),(0,float('inf'))])
def test_material_invalid_range_is_not_silently_repaired(start,end):
    from app.services.material.video_analyzer import VideoAnalyzer
    with pytest.raises(ValueError):VideoAnalyzer(Path('test.mp4'),duration=20.)._validate(_material_part(start,end))


def test_material_batch_failure_does_not_return_partial_timeline():
    from app.services.material.video_analyzer import VideoAnalyzer
    from unittest.mock import patch
    analyzer=VideoAnalyzer(Path('test.mp4'),duration=15.)
    with patch.object(analyzer,'_extract_frames',return_value=(['x']*5,3)),patch.object(analyzer,'_call_multimodal',side_effect=[_material_part(0,12),ValueError('truncated')]):
        with pytest.raises(ValueError,match='truncated'):analyzer.analyze()


@pytest.mark.parametrize('finish', ['length',None,'stop'])
def test_material_rejects_truncated_response(finish):
    from app.services.material.video_analyzer import VideoAnalyzer
    from app.services.llm.llm_agnes import AgnesApiKey
    from unittest.mock import patch,MagicMock
    response=MagicMock(ok=True,status_code=200)
    response.json.return_value={'choices':[{'finish_reason':finish,'message':{'content':_material_part(0,3)}}]}
    with patch('app.services.material.video_analyzer.agnes_api_keys',return_value=[AgnesApiKey('free','fake','https://example.invalid')]),patch('requests.post',return_value=response) as post:
        if finish=='stop':assert VideoAnalyzer._call_multimodal('system','user',['image'])
        else:
            with pytest.raises(ValueError,match='截断'):VideoAnalyzer._call_multimodal('system','user',['image'])
    post.assert_called_once()


def test_material_enforces_request_image_limit_before_http():
    from app.services.material.video_analyzer import VideoAnalyzer
    from unittest.mock import patch
    with patch('requests.post') as post,pytest.raises(ValueError,match='1至4'):
        VideoAnalyzer._call_multimodal('s','u',['x']*5)
    post.assert_not_called()


def test_material_frame_budget_and_resize(tmp_path):
    import base64,io
    from PIL import Image
    from unittest.mock import patch
    from app.services.material.video_analyzer import VideoAnalyzer
    source=tmp_path/'frame.jpg';Image.new('RGB',(1920,1080),'white').save(source)
    with patch('app.services.material.video_analyzer.extract_frames_interval',return_value=[source]*32) as extract:
        frames,interval=VideoAnalyzer(Path('test.mp4'),duration=3600.)._extract_frames()
    assert len(frames)==32 and interval==113
    assert extract.call_args.args[2]==113
    image=Image.open(io.BytesIO(base64.b64decode(frames[0])))
    assert max(image.size)==640
