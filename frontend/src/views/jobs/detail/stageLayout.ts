/** 阶段页签通用布局 class */

export const STAGE_ACTION_BAR_CLASS =
  "mb-4 flex flex-wrap items-center gap-2 border-b border-gray-200 pb-4";

/** 带边框的内容卡片 */
export const STAGE_PANEL_CLASS = "rounded-lg border border-gray-200 p-4";

/** 操作区下方独立配置块（含下边距） */
export const STAGE_BLOCK_CLASS = "mb-4 rounded-lg border border-gray-200 p-4";

/** 紧凑参数块（较小内边距） */
export const STAGE_BLOCK_COMPACT_CLASS =
  "mb-4 rounded-lg border border-gray-200 px-3 py-2";

export const STAGE_TWO_COL_CLASS = "flex flex-wrap items-start gap-4";

export const STAGE_COL_LEFT_CLASS = "min-w-[280px] max-w-full shrink-0 basis-80";

/** 封面等宽预览列（520px 基准） */
export const STAGE_COL_WIDE_LEFT_CLASS =
  "min-w-[280px] max-w-full shrink-0 basis-[520px]";

export const STAGE_COL_RIGHT_CLASS = "min-w-[280px] flex-1 basis-[360px]";

/** 配音等宽预览列（字幕表需要更宽） */
export const STAGE_COL_WIDE_RIGHT_CLASS =
  "min-w-[320px] flex-1 basis-[520px]";

/** 三栏预览列（约 1/3 宽度） */
export const STAGE_COL_THIRD_CLASS =
  "min-w-[240px] max-w-full flex-1 basis-[320px]";

/** 行内单选组（紧凑、可换行） */
export const STAGE_RADIO_INLINE_CLASS =
  "flex flex-wrap items-center gap-x-4 gap-y-1 [&_.el-radio]:mr-0 [&_.el-radio]:h-7";

/** 区块标题（日志、质量报告等） */
export const STAGE_SECTION_TITLE_CLASS = "mb-2 text-sm font-medium text-gray-600";

/** 卡片内小标题 */
export const STAGE_PANEL_TITLE_TEXT_CLASS = "text-sm font-medium text-gray-700";

/** 独立小标题（含下边距） */
export const STAGE_PANEL_TITLE_CLASS = "mb-3 text-sm font-medium text-gray-700";

export const STAGE_PANEL_HEADER_CLASS =
  "mb-3 flex items-baseline justify-between gap-2";

export const STAGE_EMPTY_CLASS = "py-8 text-center text-sm text-gray-400";

export const STAGE_LOGS_SECTION_CLASS = "mt-6";

/** 主内容区下方次级区块（质量报告等） */
export const STAGE_SUBSECTION_CLASS = "mt-4";

export const STAGE_FORM_LABEL_WIDTH = "96px";

export const STAGE_FORM_CLASS =
  "[&_.el-form-item]:mb-3 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1";

export const STAGE_FORM_COMPACT_CLASS =
  "[&_.el-form-item]:mb-0 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1 [&_.el-form-item__label]:h-auto! [&_.el-form-item__label]:leading-snug";
