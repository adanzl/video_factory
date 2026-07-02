"""选题提示词：JSON 输出格式（与分类无关）。"""


def topic_json_format(*, max_title_len: int, category_value: str) -> str:
    return (
        "输出 JSON，顶层字段 topics（数组）。"
        "每项含 title、keywords（数组）、category、template、hook。"
        f"title 不含空格换行，≤{max_title_len} 字。"
        f"category 固定为「{category_value}」。"
        "template 须与分配模板一致。"
        "hook 为 15-30 字点击动机。"
        "keywords 为 2-6 字核心实体数组（1-3 项）。"
        f'样例：{{"topics": [{{"title": "标题", "keywords": ["关键词"], '
        f'"category": "{category_value}", "template": "误区反问式", "hook": "一句话钩子"}}]}}'
    )


def optimize_json_format(*, max_title_len: int, category_value: str) -> str:
    return (
        "输出 JSON，topics 数组仅 1 项。"
        "每项含 title、keywords、category、template、hook。"
        f"title ≤{max_title_len} 字，不含空格换行，须含中文问号「？」。"
        f"category 固定为「{category_value}」，template 与用户原值一致。"
        f'样例：{{"topics": [{{"title": "动物真能预报地震？监测数据压根对不上", "keywords": ["地震", "动物"], '
        f'"category": "{category_value}", "template": "误区反问式", "hook": "一句话钩子"}}]}}'
    )
