"""日常故事对话预览阶段（手动阶段，仅展示对话内容）。"""

from __future__ import annotations

import logging

from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)


class DialogueStage(StageExecutor):
    """对话预览阶段——手动阶段，用户查看对话后触发下一步。

    对应前端 StageChatScript.vue，展示原始对话内容。
    执行时仅作日志记录，不执行实际工作。
    """

    name = "dialogue"

    def run(self, ctx: JobContext) -> None:
        logger.info(
            "[DIALOGUE] dialogue stage completed for job %d",
            ctx.job["id"],
        )
