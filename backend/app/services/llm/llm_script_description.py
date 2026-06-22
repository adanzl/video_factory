"""B 站视频简介生成：在成稿后根据标题与口播写出有吸引力的投稿介绍。"""

from __future__ import annotations

from typing import Any


def build_video_description_system_prompt() -> str:
    return (
        "你是 B 站科普短视频简介撰写师。根据视频标题与完整口播，输出 JSON，字段 video_description。"
        "video_description 为投稿简介正文，适合粘贴到 B 站视频介绍栏。"
        "视频约 1 分钟，简介宜短：总字数 60～120，2～3 行即可。"
        "第一行一句钩子（反问或反差，引发好奇，勿平淡复述标题）；"
        "第二行点出本集核心收获；"
        "末尾附 1～2 个相关话题标签，格式 #标签名。"
        "勿写长列表、勿堆砌点赞收藏等互动话术；口语自然，事实与口播一致，不得编造口播未涉及的内容。"
        "禁止：医疗养生承诺、理财荐股、时政情感、虚假夸张标题党、外链与联系方式。"
    )


def build_video_description_user_prompt(*, title: str, narration: str) -> str:
    snippet = narration.strip()
    if len(snippet) > 1200:
        snippet = snippet[:1200] + "…"
    return (
        f"视频标题：{title}\n"
        f"完整口播：\n{snippet}\n\n"
        "请输出有吸引力的 B 站视频简介 video_description。"
    )


def parse_video_description_payload(raw: dict[str, Any]) -> str:
    desc = raw.get("video_description")
    if not isinstance(desc, str) or not desc.strip():
        raise ValueError("LLM video description response missing video_description")
    return desc.strip()
