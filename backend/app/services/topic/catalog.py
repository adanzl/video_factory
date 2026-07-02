"""选题大分类、模板与赛道配置（提示词与打分共用）。"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORY_HISTORY = "历史悬案"
CATEGORY_SCIENCE = "科学原理"
CATEGORY_CURRENT = "时事相关科普"

TOPIC_CATEGORIES: frozenset[str] = frozenset(
    {CATEGORY_HISTORY, CATEGORY_SCIENCE, CATEGORY_CURRENT}
)

# 旧库 track 值 → 大分类（兼容历史数据）
LEGACY_TRACK_TO_CATEGORY: dict[str, str] = {
    "历史悬案": CATEGORY_HISTORY,
    "日常科学原理": CATEGORY_SCIENCE,
    "生活避坑实用常识": CATEGORY_SCIENCE,
    "数码小白避坑": CATEGORY_SCIENCE,
    "古代冷门生活史": CATEGORY_SCIENCE,
    CATEGORY_SCIENCE: CATEGORY_SCIENCE,
    CATEGORY_CURRENT: CATEGORY_CURRENT,
}

ALL_TOPIC_TEMPLATES: frozenset[str] = frozenset(
    {"误区反问式", "反差好奇式", "实操避坑式", "悬念钩子式", "未解之谜式"}
)


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    weight: int
    hint: str


@dataclass(frozen=True)
class CategorySpec:
    id: str
    label: str
    role: str
    default_theme: str
    keywords_hint: str
    templates: tuple[TemplateSpec, ...]

    @property
    def template_names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.templates)


CATEGORY_SPECS: dict[str, CategorySpec] = {
    CATEGORY_HISTORY: CategorySpec(
        id=CATEGORY_HISTORY,
        label="历史悬案",
        role="B 站历史悬案视频选题策划",
        default_theme="中国历史悬案",
        keywords_hint="人名/事件/朝代，如：和珅、雍正、烛影斧声",
        templates=(
            TemplateSpec("悬念钩子式", 35, "历史代号 + 一句话悬念"),
            TemplateSpec("未解之谜式", 30, "失踪/暴毙/无人敢近等反常画面"),
            TemplateSpec("误区反问式", 20, "颠覆常识的历史细节"),
            TemplateSpec("反差好奇式", 15, "同一人物/事件的两面反差"),
        ),
    ),
    CATEGORY_SCIENCE: CategorySpec(
        id=CATEGORY_SCIENCE,
        label="科学原理",
        role="B 站科普短视频选题策划",
        default_theme="日常科学冷知识",
        keywords_hint="具象名词，如：空调、芯片、温度、地震波",
        templates=(
            TemplateSpec("误区反问式", 50, "日常误区 + 反问 + 一步反驳"),
            TemplateSpec("反差好奇式", 30, "同样是 XX，为什么结果差很多"),
            TemplateSpec("实操避坑式", 20, "暗藏猫腻 + 正确辨别方法"),
        ),
    ),
    CATEGORY_CURRENT: CategorySpec(
        id=CATEGORY_CURRENT,
        label="时事相关科普",
        role="B 站时事衍生科普选题策划",
        default_theme="",
        keywords_hint="时事锚点词，如：地震、降温、高考志愿",
        templates=(
            TemplateSpec("误区反问式", 60, "剥离时效后讲清原理/规则/误区"),
            TemplateSpec("反差好奇式", 40, "公众认知 vs 科学/规则真相"),
        ),
    ),
}


def resolve_category(value: str | None) -> str:
    """将 category（含旧赛道值）解析为标准大分类。"""
    if not value:
        return CATEGORY_SCIENCE
    key = value.strip()
    if key in TOPIC_CATEGORIES:
        return key
    return LEGACY_TRACK_TO_CATEGORY.get(key, CATEGORY_SCIENCE)


def get_category_spec(category: str | None) -> CategorySpec:
    resolved = resolve_category(category)
    return CATEGORY_SPECS[resolved]


def normalize_category(category: str | None) -> str:
    """入库 category 统一为大分类名。"""
    return resolve_category(category)


def catalog_for_api() -> list[dict]:
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "default_theme": spec.default_theme,
            "keywords_hint": spec.keywords_hint,
            "templates": [
                {"name": t.name, "weight": t.weight, "hint": t.hint}
                for t in spec.templates
            ],
        }
        for spec in CATEGORY_SPECS.values()
    ]


def distribute_templates(
    category: str,
    count: int,
    *,
    template: str | None = None,
) -> list[str]:
    """按分类模板权重分配生成任务用的模板列表。"""
    spec = get_category_spec(category)
    if template and template in spec.template_names:
        return [template] * count

    names = list(spec.template_names)
    weights = [t.weight for t in spec.templates]
    total_w = sum(weights)
    out: list[str] = []
    for i in range(count):
        slot = (i * total_w) // count
        acc = 0
        for name, w in zip(names, weights, strict=True):
            acc += w
            if slot < acc:
                out.append(name)
                break
        else:
            out.append(names[-1])
    return out
