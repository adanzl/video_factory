<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 p-3">
      <el-form
        :label-width="FORM_LABEL_WIDTH"
        class="script-stage-form [&_.el-form-item]:mb-2 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1"
      >
        <el-form-item label="原标题">
          <div class="flex w-full min-w-0 items-center gap-2">
            <div class="min-w-0 flex-1">
              <el-input
                v-model="sourceTitle"
                placeholder="脚本生成输入标题"
                clearable
              />
            </div>
            <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
              重新生成
            </el-button>
            <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
              从此成片
            </el-button>
            <span v-if="actionDisabledReason" class="shrink-0 text-xs text-gray-400">{{ actionDisabledReason }}</span>
          </div>
        </el-form-item>
        <template v-if="!isMaterialJob">
          <el-form-item label="内容配置">
            <div class="flex w-full min-w-0 flex-nowrap items-center gap-2 overflow-x-auto pb-0.5">
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">方向</span>
              <el-radio-group v-model="jobOrientation" size="small" class="shrink-0">
                <el-radio-button value="portrait">竖屏</el-radio-button>
                <el-radio-button value="landscape">横屏</el-radio-button>
              </el-radio-group>
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">类型</span>
              <el-radio-group v-model="contentStyle" size="small" class="shrink-0">
                <el-radio-button value="science_child">童趣科普</el-radio-button>
                <el-radio-button value="life_experience">生活经验</el-radio-button>
              </el-radio-group>
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <el-button size="small" plain class="shrink-0" @click="applyLandscapeLifePreset">
                横屏生活 · 6 分钟
              </el-button>
            </div>
          </el-form-item>
          <el-form-item label="生成参数">
            <div class="flex w-full min-w-0 flex-nowrap items-center gap-2 overflow-x-auto pb-0.5">
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">单镜 (秒)</span>
              <el-input-number
                v-model="segmentTargetSec"
                :min="0"
                :max="60"
                :step="1"
                controls-position="right"
                class="w-28! shrink-0"
              />
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">标题上限</span>
              <el-input-number
                v-model="maxTitleLength"
                :min="8"
                :max="48"
                :step="1"
                controls-position="right"
                class="w-28! shrink-0"
              />
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">口播字数</span>
              <el-input-number
                v-model="narrationTargetWords"
                :min="NARRATION_WORDS_MIN"
                :max="NARRATION_WORDS_MAX"
                :step="50"
                controls-position="right"
                class="w-36! shrink-0"
                @change="narrationWordsTouched = true"
              />
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">标题优化</span>
              <el-checkbox v-model="skipTitleOptimize" class="shrink-0">跳过</el-checkbox>
              <span class="mx-1 h-5 w-px shrink-0 bg-gray-200" aria-hidden="true" />
              <span class="shrink-0 text-xs leading-tight whitespace-nowrap text-gray-500">文生图提示词</span>
              <el-checkbox v-model="includeImagePrompts" class="shrink-0">生成</el-checkbox>
            </div>
          </el-form-item>
        </template>
        <div v-else class="flex flex-wrap items-start gap-x-4">
          <el-form-item label="标题上限" :label-width="FORM_LABEL_WIDTH" class="mb-0!">
            <el-input-number
              v-model="maxTitleLength"
              :min="8"
              :max="48"
              :step="1"
              controls-position="right"
              class="w-28!"
            />
          </el-form-item>
          <el-form-item label="口播字数" :label-width="FORM_LABEL_WIDTH" class="mb-0!">
            <div class="flex flex-col gap-1">
              <el-input-number
                v-model="narrationTargetWords"
                :min="NARRATION_WORDS_MIN"
                :max="NARRATION_WORDS_MAX"
                :step="50"
                controls-position="right"
                class="w-32!"
                @change="narrationWordsTouched = true"
              />
              <span v-if="baseDurationHint" class="text-xs text-gray-400">{{ baseDurationHint }}</span>
            </div>
          </el-form-item>
          <el-form-item label="标题优化" :label-width="FORM_LABEL_WIDTH" class="mb-0!">
            <el-checkbox v-model="skipTitleOptimize">跳过</el-checkbox>
          </el-form-item>
        </div>
        <el-form-item v-if="isMaterialJob" label="时间表" class="mb-2!">
          <el-input
            v-model="videoTimeline"
            type="textarea"
            :rows="5"
            placeholder="可选：粘贴画面时间表 JSON（含 balls/segments/items 数组与 start_sec、end_sec），口播将逐段对齐"
            clearable
          />
        </el-form-item>
        <el-form-item label="补充信息" class="mb-0!">
          <el-input
            v-model="supplementaryInfo"
            type="textarea"
            :rows="3"
            placeholder="可选：背景知识、必讲要点、表达风格、禁忌表述等（不含时间表 JSON）"
            clearable
          />
        </el-form-item>
      </el-form>
    </div>

    <el-collapse v-model="promptPanelOpen" class="mb-4 script-prompt-collapse">
      <el-collapse-item name="prompts">
        <template #title>
          <div class="flex w-full items-center justify-between gap-3 pr-2">
            <span class="text-sm font-medium text-gray-700">大模型提示词</span>
            <el-button
              v-if="promptPanelOpen.includes('prompts')"
              size="small"
              :loading="promptsLoading"
              @click.stop="loadLlmPrompts"
            >
              刷新
            </el-button>
          </div>
        </template>
        <div v-if="promptsLoading" class="py-6 text-center text-sm text-gray-400">加载中…</div>
        <template v-else-if="displayPrompts.length">
          <el-tabs v-model="activePromptTab" class="script-prompt-tabs">
            <el-tab-pane
              v-for="item in displayPrompts"
              :key="item.step"
              :label="promptTabLabel(item.step)"
              :name="item.step"
            >
              <div class="space-y-3 pt-1">
                <div>
                  <div class="mb-1 text-xs font-medium text-gray-500">System</div>
                  <pre
                    class="m-0 max-h-72 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed wrap-break-word whitespace-pre-wrap"
                  >{{ item.system }}</pre>
                </div>
                <div>
                  <div class="mb-1 text-xs font-medium text-gray-500">User</div>
                  <pre
                    class="m-0 max-h-72 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed wrap-break-word whitespace-pre-wrap"
                  >{{ item.user }}</pre>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </template>
        <div v-else class="py-6 text-center text-sm text-gray-400">
          {{ sourceTitle.trim() ? "暂无提示词" : "请先填写原标题" }}
        </div>
      </el-collapse-item>
    </el-collapse>

    <div v-if="script">
      <el-descriptions
        :column="1"
        border
        :label-width="FORM_LABEL_WIDTH"
        class="script-meta-desc mb-2"
      >
        <el-descriptions-item label="脚本标题">{{ script.title || "-" }}</el-descriptions-item>
        <el-descriptions-item
          v-if="script.draft_title && script.draft_title !== script.title"
          label="初稿标题"
        >
          {{ script.draft_title }}
        </el-descriptions-item>
        <el-descriptions-item v-if="!isMaterialJob" label="画风定调">
          {{ script.visual_style || "-" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="isMaterialJob && script.script_mode" label="文案模式">
          {{ script.script_mode === "manual" ? "手动" : "AI" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="isMaterialJob && script.video_timeline" label="时间表">
          <el-tooltip placement="top-start" :show-after="300">
            <template #content>
              <div
                class="max-h-96 max-w-2xl overflow-auto whitespace-pre-wrap wrap-break-word font-mono text-xs leading-relaxed"
              >
                {{ script.video_timeline }}
              </div>
            </template>
            <div class="line-clamp-2 cursor-default font-mono text-xs leading-relaxed break-all text-gray-600">
              {{ script.video_timeline }}
            </div>
          </el-tooltip>
        </el-descriptions-item>
        <el-descriptions-item v-if="script.supplementary_info" label="补充信息">
          <el-tooltip placement="top-start" :show-after="300">
            <template #content>
              <div
                class="max-h-96 max-w-2xl overflow-auto whitespace-pre-wrap wrap-break-word text-sm leading-relaxed"
              >
                {{ script.supplementary_info }}
              </div>
            </template>
            <div class="line-clamp-2 cursor-default text-sm leading-relaxed wrap-break-word text-gray-600">
              {{ script.supplementary_info }}
            </div>
          </el-tooltip>
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions
        :column="3"
        border
        :label-width="FORM_LABEL_WIDTH"
        class="script-meta-desc mb-4"
      >
        <el-descriptions-item label="生成耗时">{{ formatCostTime(script.cost_time) }}</el-descriptions-item>
        <el-descriptions-item label="字数">{{ script.word_count ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="分镜数">{{ script.segments?.length ?? 0 }}</el-descriptions-item>
      </el-descriptions>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">完整口播</div>
        <div
          v-if="script.narration"
          class="rounded bg-gray-50 px-4 py-3 leading-relaxed wrap-break-word whitespace-pre-wrap"
        >
          {{ script.narration }}
        </div>
        <div v-else class="py-8 text-center text-sm text-gray-400">暂无口播文案</div>
      </div>

      <div v-if="script.narration" class="mb-5">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <span class="text-sm font-medium text-gray-700">视频介绍</span>
          <el-button
            size="small"
            :loading="regeneratingDescription"
            :disabled="actionDisabled"
            @click="handleRegenerateDescription"
          >
            重新生成
          </el-button>
        </div>
        <div
          v-if="script.video_description"
          class="relative rounded bg-gray-50 px-4 py-3 pr-10 leading-relaxed wrap-break-word whitespace-pre-wrap"
        >
          {{ script.video_description }}
          <el-tooltip content="复制" placement="top">
            <el-button
              class="absolute! top-2 right-2"
              link
              type="primary"
              :icon="DocumentCopy"
              @click="copyVideoDescription(script.video_description)"
            />
          </el-tooltip>
        </div>
        <div v-else class="py-4 text-center text-sm text-gray-400">暂无视频介绍</div>
      </div>

      <div class="mb-5">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <span class="text-sm font-medium text-gray-700">分镜列表</span>
          <el-button
            v-if="!isMaterialJob"
            size="small"
            :loading="generatingImagePrompts"
            :disabled="actionDisabled || !script.segments?.length"
            @click="handleGenerateImagePrompts"
          >
            文生图提示词
          </el-button>
        </div>
        <el-table v-if="script.segments?.length" :data="script.segments" stripe class="w-full">
          <el-table-column prop="segment_index" label="#" width="60" />
          <el-table-column prop="text" label="口播文案" min-width="150">
            <template #default="{ row }">
              <div class="leading-relaxed wrap-break-word whitespace-pre-wrap">{{ row.text }}</div>
            </template>
          </el-table-column>
          <template v-if="!isMaterialJob">
            <el-table-column prop="visual_brief" label="画面描述" min-width="150">
              <template #default="{ row }">
                <div class="leading-relaxed wrap-break-word whitespace-pre-wrap">{{ row.visual_brief || "-" }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="visual_mode" label="模式" width="120" />
            <el-table-column prop="image_prompt" label="文生图提示词" min-width="240">
              <template #default="{ row }">
                <div class="text-xs leading-relaxed wrap-break-word whitespace-pre-wrap text-gray-500">
                  {{ row.image_prompt || "-" }}
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="motion_prompt" label="运动提示词" min-width="100">
              <template #default="{ row }">
                <div class="text-xs leading-relaxed wrap-break-word whitespace-pre-wrap text-gray-500">
                  {{ row.motion_prompt || "-" }}
                </div>
              </template>
            </el-table-column>
          </template>
        </el-table>
        <div v-else class="py-8 text-center text-sm text-gray-400">暂无分镜</div>
      </div>

      <el-collapse class="mt-4">
        <el-collapse-item title="原始 JSON" name="raw">
          <pre class="m-0 max-h-[480px] overflow-auto rounded bg-gray-50 p-3 text-xs leading-normal break-all whitespace-pre-wrap">{{ rawJson }}</pre>
        </el-collapse-item>
      </el-collapse>
    </div>
    <div v-else class="py-8 text-center text-sm text-gray-400">暂无脚本数据</div>

    <div class="mt-4">
      <div class="mb-2 text-sm font-medium text-gray-600">质量报告</div>
      <div v-if="qualityReportRows.length" class="space-y-4">
        <el-descriptions
          v-for="row in qualityReportRows"
          :key="row.step"
          :title="row.stepLabel"
          :column="3"
          border
          size="small"
        >
          <el-descriptions-item label="结果">
            <el-tag :type="qualityLevelTagType(row.level)" size="small">{{ row.levelLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="失败阶段">{{ row.failStage || "-" }}</el-descriptions-item>
          <template v-if="qualityDetailEntries(row.detailFields).length">
            <el-descriptions-item
              v-for="[key, value] in qualityDetailEntries(row.detailFields)"
              :key="key"
              :label="qualityDetailLabel(key)"
              :span="detailFieldSpan(key, value)"
            >
              <div class="wrap-break-word whitespace-pre-wrap text-sm">{{ value }}</div>
            </el-descriptions-item>
          </template>
          <el-descriptions-item v-else label="详情" :span="3">-</el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-else class="py-8 text-center text-sm text-gray-400">暂无数据</div>
    </div>

    <div class="mt-6">
      <div class="mb-2 text-sm font-medium text-gray-600">阶段日志</div>
      <el-table v-if="logs.length" :data="logs" stripe size="small" class="w-full">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80" />
        <el-table-column prop="message" label="消息" min-width="240" show-overflow-tooltip />
      </el-table>
      <div v-else class="py-8 text-center text-sm text-gray-400">暂无日志</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { DocumentCopy } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getMediaDuration } from "@/api/api-media";
import { previewScriptPrompts, generateVideoDescription, generateImagePrompts, runJobStageAction } from "@/api/api-jobs";
import type { JobDetail, JobLog, LlmPromptStep, ScriptJson } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { isMaterialJob as checkMaterialJob } from "@/constants/jobStages";
import { formatDateTime } from "@/utils/date";
import { estimateNarrationTargetWords, formatCostTime, formatMediaDuration, defaultNarrationTargetWords, narrationTargetForMinutes } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText } from "@/utils/utils";

const FORM_LABEL_WIDTH = "88px";
const DEFAULT_SEGMENT_TARGET_SEC = 28;
const DEFAULT_MAX_TITLE_LENGTH = 24;
const DEFAULT_NARRATION_TARGET_WORDS = defaultNarrationTargetWords();
const DEFAULT_MATERIAL_NARRATION_TARGET_WORDS = 800;
const NARRATION_WORDS_MIN = 200;
const NARRATION_WORDS_MAX = 3000;

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();
const DEFAULT_LANDSCAPE_LIFE_SEGMENT_SEC = 28;
const DEFAULT_LANDSCAPE_LIFE_MINUTES = 6;

const submitting = ref(false);
const regeneratingDescription = ref(false);
const generatingImagePrompts = ref(false);
const sourceTitle = ref("");
const jobOrientation = ref<"portrait" | "landscape">("portrait");
const contentStyle = ref<"science_child" | "life_experience">("science_child");
const segmentTargetSec = ref(DEFAULT_SEGMENT_TARGET_SEC);
const maxTitleLength = ref(DEFAULT_MAX_TITLE_LENGTH);
const narrationTargetWords = ref(DEFAULT_NARRATION_TARGET_WORDS);
const skipTitleOptimize = ref(false);
const includeImagePrompts = ref(false);
const supplementaryInfo = ref("");
const videoTimeline = ref("");
const baseDurationSec = ref<number | null>(null);
const narrationWordsTouched = ref(false);
const promptPanelOpen = ref<string[]>([]);
const promptsLoading = ref(false);
const llmPrompts = ref<LlmPromptStep[]>([]);
const activePromptTab = ref("");

const PROMPT_TAB_ORDER = [
  "storyboard",
  "material_script",
  "title_optimize",
  "video_description",
] as const;

const PROMPT_TAB_LABELS: Record<string, string> = {
  storyboard: "分镜",
  material_script: "口播",
  title_optimize: "标题",
  video_description: "介绍",
};

const promptTabLabel = (step: string) => PROMPT_TAB_LABELS[step] ?? step;

const displayPrompts = computed(() =>
  llmPrompts.value
    .filter(item => (PROMPT_TAB_ORDER as readonly string[]).includes(item.step))
    .sort(
      (a, b) =>
        (PROMPT_TAB_ORDER as readonly string[]).indexOf(a.step) -
        (PROMPT_TAB_ORDER as readonly string[]).indexOf(b.step)
    )
);

const actionDisabled = computed(() => props.job.status === "running");
const isMaterialJob = computed(() => checkMaterialJob(props.job));
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const script = computed<ScriptJson | null>(() => {
  const value = props.job.script_json;
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as ScriptJson;
});

const rawJson = computed(() => JSON.stringify(props.job.script_json, null, 2));

const QUALITY_STEP_LABELS: Record<string, string> = {
  copy: "文案",
  storyboard: "分镜",
  tts: "配音",
  visual: "画面",
  clip: "片段",
  final: "成片",
  legacy: "旧版",
};

const QUALITY_LEVEL_LABELS: Record<string, string> = {
  pass: "通过",
  minor: "轻微",
  major: "严重",
};

const QUALITY_DETAIL_LABELS: Record<string, string> = {
  reason: "原因",
  word_count: "字数",
  segment_count: "分镜数",
  title_length: "标题长度",
  max_length: "最大长度",
  min_expected: "最少分镜",
  segment_target_sec: "分镜目标时长",
  segments: "超长分镜",
  bad_segment_indexes: "空文案分镜",
  bad_segment_ids: "问题分镜",
  duration_sec: "时长(秒)",
  integrated_lufs: "响度(LUFS)",
  true_peak_dbtp: "真峰值(dBTP)",
  max_silence_gap_sec: "最大静音间隔",
  limit_sec: "限制值",
  edge_silence_sec: "首尾静音",
  target_lufs: "目标响度",
  delta_lu: "响度偏差",
  tolerance_sec: "容差(秒)",
  clip_count: "片段数",
  min_duration_sec: "最短时长",
  max_duration_sec: "最长时长",
};

interface QualityReportRow {
  step: string;
  stepLabel: string;
  level: string;
  levelLabel: string;
  failStage: string;
  detailFields: Record<string, string>;
}

const qualityLevelTagType = (level: string): "success" | "warning" | "danger" | "info" => {
  if (level === "pass") return "success";
  if (level === "minor") return "warning";
  if (level === "major") return "danger";
  return "info";
};

const qualityDetailLabel = (key: string) => QUALITY_DETAIL_LABELS[key] ?? key;

const qualityDetailEntries = (fields: Record<string, string>) =>
  Object.entries(fields).sort(([a], [b]) => {
    if (a === "reason") return -1;
    if (b === "reason") return 1;
    return a.localeCompare(b);
  });

const detailFieldSpan = (key: string, value: string) => {
  if (key === "reason" || key === "segments" || value.length > 60) {
    return 3;
  }
  return 1;
};

const formatDetailValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "-";
    }
    if (typeof value[0] === "object") {
      return JSON.stringify(value);
    }
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
};

const buildDetailFields = (details: unknown, badSegmentIds: unknown): Record<string, string> => {
  const fields: Record<string, string> = {};
  if (details && typeof details === "object" && !Array.isArray(details)) {
    for (const [key, value] of Object.entries(details as Record<string, unknown>)) {
      fields[key] = formatDetailValue(value);
    }
  } else if (details !== null && details !== undefined && details !== "") {
    fields.reason = String(details);
  }
  if (Array.isArray(badSegmentIds) && badSegmentIds.length) {
    fields.bad_segment_ids = badSegmentIds.join(", ");
  }
  return fields;
};

const parseQualityReport = (value: unknown): QualityReportRow[] => {
  if (value === null || value === undefined) {
    return [];
  }
  if (typeof value === "string") {
    try {
      return parseQualityReport(JSON.parse(value));
    } catch {
      return [
        {
          step: "-",
          stepLabel: "-",
          level: "-",
          levelLabel: "-",
          failStage: "",
          detailFields: { reason: value },
        },
      ];
    }
  }
  if (typeof value !== "object") {
    return [];
  }

  return Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item && typeof item === "object")
    .map(([step, item]) => {
      const report = item as Record<string, unknown>;
      const level = String(report.level ?? "-");
      return {
        step,
        stepLabel: QUALITY_STEP_LABELS[step] ?? step,
        level,
        levelLabel: QUALITY_LEVEL_LABELS[level] ?? level,
        failStage: report.fail_stage != null ? String(report.fail_stage) : "",
        detailFields: buildDetailFields(report.details, report.bad_segment_ids),
      };
    });
};

const qualityReportRows = computed(() => parseQualityReport(props.job.quality_report));

const baseDurationHint = computed(() => {
  if (!isMaterialJob.value || baseDurationSec.value === null) {
    return "";
  }
  const durationLabel = formatMediaDuration(baseDurationSec.value);
  const estimated = estimateNarrationTargetWords(baseDurationSec.value);
  return `基底 ${durationLabel}，推荐约 ${estimated} 字`;
});

const loadBaseDuration = async () => {
  if (!isMaterialJob.value) {
    baseDurationSec.value = null;
    return;
  }
  if (!props.job.base_path) {
    baseDurationSec.value = null;
    if (!narrationWordsTouched.value) {
      narrationTargetWords.value = DEFAULT_MATERIAL_NARRATION_TARGET_WORDS;
    }
    return;
  }
  const duration = await getMediaDuration(props.job.base_path);
  baseDurationSec.value = duration;
  if (narrationWordsTouched.value) {
    return;
  }
  if (duration !== null && duration > 0) {
    narrationTargetWords.value = estimateNarrationTargetWords(duration);
  } else {
    narrationTargetWords.value = DEFAULT_MATERIAL_NARRATION_TARGET_WORDS;
  }
};

const normalizeSupplementary = (value: unknown) =>
  typeof value === "string" ? value : "";

function initJobProfileFromInfo() {
  const info = props.job.info;
  if (info?.orientation === "landscape" || info?.orientation === "portrait") {
    jobOrientation.value = info.orientation;
  }
  if (info?.content_style === "life_experience" || info?.content_style === "science_child") {
    contentStyle.value = info.content_style;
  }
}

const applyLandscapeLifePreset = () => {
  jobOrientation.value = "landscape";
  contentStyle.value = "life_experience";
  segmentTargetSec.value = DEFAULT_LANDSCAPE_LIFE_SEGMENT_SEC;
  narrationTargetWords.value = narrationTargetForMinutes(DEFAULT_LANDSCAPE_LIFE_MINUTES);
  narrationWordsTouched.value = true;
};

const loadSupplementaryFromScript = () => {
  supplementaryInfo.value = normalizeSupplementary(script.value?.supplementary_info);
  videoTimeline.value = normalizeSupplementary(script.value?.video_timeline);
};

const loadLlmPrompts = async () => {
  const trimmedTitle = sourceTitle.value.trim();
  if (!trimmedTitle) {
    llmPrompts.value = [];
    activePromptTab.value = "";
    return;
  }
  promptsLoading.value = true;
  try {
    llmPrompts.value = await previewScriptPrompts({
      id: props.job.id,
      title: trimmedTitle,
      segment_target_sec: segmentTargetSec.value,
      max_title_length: maxTitleLength.value,
      narration_target_words: Math.round(narrationTargetWords.value),
      skip_title_optimize: skipTitleOptimize.value,
      supplementary_info: supplementaryInfo.value.trim() || undefined,
      video_timeline: videoTimeline.value.trim() || undefined,
      orientation: jobOrientation.value,
      content_style: contentStyle.value,
    });
    const first = displayPrompts.value[0];
    if (first && !displayPrompts.value.some(item => item.step === activePromptTab.value)) {
      activePromptTab.value = first.step;
    }
  } catch (error) {
    handleError(error, "加载提示词失败");
  } finally {
    promptsLoading.value = false;
  }
};

const handleRegenerateDescription = async () => {
  if (!script.value?.narration?.trim()) {
    ElMessage.warning("请先生成口播文案");
    return;
  }
  regeneratingDescription.value = true;
  try {
    await generateVideoDescription(props.job.id);
    ElMessage.success("视频介绍已重新生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "重新生成视频介绍失败");
  } finally {
    regeneratingDescription.value = false;
  }
};

const handleGenerateImagePrompts = async () => {
  if (!script.value?.segments?.length) {
    ElMessage.warning("请先生成分镜");
    return;
  }
  try {
    await ElMessageBox.confirm("确定为当前脚本生成文生图提示词吗？", "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  generatingImagePrompts.value = true;
  try {
    await generateImagePrompts(props.job.id);
    ElMessage.success("已提交文生图提示词生成，任务已开始执行");
    emit("refresh");
  } catch (error) {
    handleError(error, "生成文生图提示词失败");
  } finally {
    generatingImagePrompts.value = false;
  }
};

const copyVideoDescription = async (text: string) => {
  try {
    await copyText(text);
    ElMessage.success("已复制");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  const trimmedTitle = sourceTitle.value.trim();
  if (!trimmedTitle) {
    ElMessage.warning("请输入原标题");
    return;
  }
  const words = narrationTargetWords.value;
  if (!Number.isFinite(words) || words < NARRATION_WORDS_MIN || words > NARRATION_WORDS_MAX) {
    ElMessage.warning(`口播字数需在 ${NARRATION_WORDS_MIN}–${NARRATION_WORDS_MAX} 之间`);
    return;
  }
  try {
    await ElMessageBox.confirm(`确定对「脚本」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: RunStageActionPayload = {
      id: props.job.id,
      to_end: toEnd,
      title: trimmedTitle,
    };
    if (Number.isFinite(segmentTargetSec.value)) {
      payload.segment_target_sec = segmentTargetSec.value;
    }
    if (Number.isFinite(maxTitleLength.value)) {
      payload.max_title_length = maxTitleLength.value;
    }
    payload.narration_target_words = Math.round(words);
    if (!isMaterialJob.value) {
      payload.orientation = jobOrientation.value;
      payload.content_style = contentStyle.value;
    }
    if (skipTitleOptimize.value) {
      payload.skip_title_optimize = true;
    }
    if (includeImagePrompts.value) {
      payload.generate_image_prompts = true;
    }
    const extra = supplementaryInfo.value.trim();
    if (extra) {
      payload.supplementary_info = extra;
    }
    const timeline = videoTimeline.value.trim();
    if (timeline) {
      payload.video_timeline = timeline;
    }
    await runJobStageAction("script", payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.title,
  value => {
    sourceTitle.value = value;
  },
  { immediate: true }
);

watch(
  () => props.job.id,
  () => {
    narrationWordsTouched.value = false;
    narrationTargetWords.value = isMaterialJob.value
      ? DEFAULT_MATERIAL_NARRATION_TARGET_WORDS
      : DEFAULT_NARRATION_TARGET_WORDS;
    jobOrientation.value = "portrait";
    contentStyle.value = "science_child";
    segmentTargetSec.value = DEFAULT_SEGMENT_TARGET_SEC;
    initJobProfileFromInfo();
    promptPanelOpen.value = [];
    llmPrompts.value = [];
    activePromptTab.value = "";
    supplementaryInfo.value = "";
    videoTimeline.value = "";
  }
);

watch(
  () => props.job.info,
  () => {
    initJobProfileFromInfo();
  },
  { immediate: true, deep: true }
);

watch(
  () => [script.value?.supplementary_info, script.value?.video_timeline] as const,
  () => {
    loadSupplementaryFromScript();
  },
  { immediate: true }
);

watch(
  () => [
    sourceTitle.value,
    segmentTargetSec.value,
    maxTitleLength.value,
    narrationTargetWords.value,
    skipTitleOptimize.value,
    supplementaryInfo.value,
    videoTimeline.value,
    jobOrientation.value,
    contentStyle.value,
  ],
  () => {
    if (promptPanelOpen.value.includes("prompts")) {
      void loadLlmPrompts();
    }
  }
);

watch(promptPanelOpen, names => {
  if (names.includes("prompts")) {
    void loadLlmPrompts();
  }
});

watch(
  () => [props.job.base_path, isMaterialJob.value] as const,
  () => {
    void loadBaseDuration();
  },
  { immediate: true }
);
</script>

<style scoped>
.script-stage-form :deep(.el-form-item__label) {
  width: v-bind(FORM_LABEL_WIDTH);
  min-width: v-bind(FORM_LABEL_WIDTH);
  flex-shrink: 0;
  justify-content: flex-end;
}

.script-meta-desc :deep(.el-descriptions__label) {
  width: v-bind(FORM_LABEL_WIDTH) !important;
  min-width: v-bind(FORM_LABEL_WIDTH) !important;
  max-width: v-bind(FORM_LABEL_WIDTH) !important;
}

.script-prompt-collapse {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.script-prompt-collapse :deep(.el-collapse-item__header) {
  padding: 0 12px;
  height: 44px;
  border-bottom: none;
}

.script-prompt-collapse :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--el-border-color-lighter);
}

.script-prompt-collapse :deep(.el-collapse-item__content) {
  padding: 12px;
}
</style>
