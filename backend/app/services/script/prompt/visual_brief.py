"""分镜画面概述规则。"""

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（80-150字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
    "visual_brief末尾须用括号标注SD15画面类型（五选一）："
    "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图）。"
    "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
)


# ── JSON 样例 ─────────────────────────────────────────────────────

_VISUAL_BRIEF_JSON_EXAMPLE = """{
  "visual_style": "画风定调一句话（可与输入一致或微调）",
  "segments": [
    {"segment_index": 1, "visual_brief": "画面主旨与关键视觉（80-150字）（写实场景）", "visual_mode": "static_motion"},
    {"segment_index": 2, "visual_brief": "画面主旨（结构示意图）", "visual_mode": "static_motion"}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""
