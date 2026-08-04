"""标题文本：标点保留与等价比较。"""

from __future__ import annotations

import re

_TITLE_PUNCT_RE = re.compile(
    r'[\s:：?？!！,，;；·《》「」【】()（）\-"\'""]+'
)


def title_core(text: str) -> str:
    """去掉空白与常见标点后比较标题主干。"""
    return _TITLE_PUNCT_RE.sub("", text.strip())


def collapse_title_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def prefer_source_punctuation(source: str, optimized: str) -> str:
    """优化若仅改标点/空白，保留来源标题（含冒号等）。"""
    src = collapse_title_whitespace(source)
    opt = collapse_title_whitespace(optimized)
    if not src:
        return opt
    if not opt:
        return src
    if title_core(src) != title_core(opt):
        return opt
    return src if len(src) >= len(opt) else opt


def title_degraded_by_truncation(draft: str, optimized: str) -> bool:
    """优化结果若只是初稿的删字/截断版（如「藏玩具同盟」→「藏玩具」），视为退化。

    只判定「截掉末尾若干字」这种机械删减；同义改写（「谁切蛋糕」→「分蛋糕」）
    无法机读判定，靠 prompt 约束。
    """
    dc = title_core(draft)
    oc = title_core(optimized)
    if not dc or not oc:
        return False
    return len(oc) < len(dc) and dc.startswith(oc)


def select_optimized_title(draft: str, optimized: str, *, max_len: int) -> str:
    """从优化结果中选出最终标题。

    - 优化只是初稿删字截断（如「藏玩具同盟」→「藏玩具」）视为退化，回退初稿；
    - 超长硬卡：选择结果超长时，若初稿合法则回退初稿，否则截断到 max_len
      （防 normalize_title 对 ≤12 字不截断的漏洞）；
    - 仅标点/空白变化时保留来源标点。
    """
    draft_len = len(title_core(draft))
    chosen = prefer_source_punctuation(draft, optimized)
    if draft_len <= max_len and title_degraded_by_truncation(draft, chosen):
        chosen = collapse_title_whitespace(draft)
    # 硬上限按原文字数计（含标点，封面排版按原文字符数），防「妈，月饼真不是我俩滚的」
    # 这类带逗号 11 字标题钻 title_core 去标点后 ≤max_len 的空子
    if len(collapse_title_whitespace(chosen)) > max_len:
        chosen = (
            collapse_title_whitespace(draft)
            if draft_len <= max_len
            else collapse_title_whitespace(chosen)[:max_len]
        )
    return collapse_title_whitespace(chosen)
