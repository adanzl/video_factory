"""打印 job 28 完整有时间表提示词"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.script.board import build_material_script_prompts

TIMELINE = {
  "title": "美国建国250周年无人机庆典",
  "duration_sec": 189.0,
  "scenes": [
    {"index": 1, "chapter": "序幕 — 星条旗永不落", "description": "无人机编队升空，形成大型星条旗图案，动态飘扬效果，烟花散开重组，最终组成\"250\"字样", "start_sec": 0.0, "end_sec": 40.0, "duration_sec": 40.0},
    {"index": 2, "chapter": "致敬国父与山姆大叔", "description": "乔治·华盛顿肖像无人机编队，精细侧面像；山姆大叔经典\"I want you\"招贴画造型", "start_sec": 40.0, "end_sec": 60.0, "duration_sec": 20.0},
    {"index": 3, "chapter": "二战荣光 — 飞虎队与珍珠港", "description": "P-40战斧战斗机鲨鱼嘴涂装出现，多机编队飞行，珍珠港场景再现，纪念二战中美合作", "start_sec": 60.0, "end_sec": 85.0, "duration_sec": 25.0},
    {"index": 4, "chapter": "太空辉煌 — 从土星5号到SLS", "description": "土星5号火箭升空，尾焰细节；SLS新一代重型火箭；小女孩仰望火箭画面；火箭发射烟火融合", "start_sec": 85.0, "end_sec": 120.0, "duration_sec": 35.0},
    {"index": 5, "chapter": "阿波罗与阿尔忒弥斯 — 人类登月之路", "description": "阿波罗飞船月球轨道，宇航员月球行走，地球升起经典画面，新老航天员同框，阿尔忒弥斯计划标识，月球基地概念图", "start_sec": 120.0, "end_sec": 150.0, "duration_sec": 30.0},
    {"index": 6, "chapter": "自由之鹰 — 白头海雕", "description": "白头海雕展翅，头部特写，翱翔天空，目光锐利，美国国鸟国家象征", "start_sec": 150.0, "end_sec": 170.0, "duration_sec": 20.0},
    {"index": 7, "chapter": "致敬与终章 — 三千次致敬", "description": "\"THANK YOU 3000\"字样，万国旗帜，星条旗再次升起，USA字样编队", "start_sec": 170.0, "end_sec": 189.0, "duration_sec": 19.0}
  ]
}

p = build_material_script_prompts(
    "美国建国250周年庆典无人机表演",
    video_timeline=json.dumps(TIMELINE, ensure_ascii=False),
    max_title_length=16, narration_target_words=785, chars_per_sec=4.1,
)
print("=== SYSTEM ===")
print(p["system"])
print("\n=== USER ===")
print(p["user"])
