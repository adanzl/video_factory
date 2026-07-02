<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div :class="STAGE_BLOCK_CLASS">
      <el-form
        :label-width="FORM_LABEL_WIDTH"
        class="[&_.el-form-item]:mb-2 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1 [&_.el-form-item__label]:w-[100px] [&_.el-form-item__label]:min-w-[100px] [&_.el-form-item__label]:shrink-0 [&_.el-form-item__label]:justify-end"
      >
        <el-form-item label="原标题">
          <div class="flex w-full min-w-0 items-center gap-2">
            <el-input
              v-model="sourceTitle"
              placeholder="脚本生成输入标题"
              clearable
              class="min-w-0 flex-1!"
            />
            <el-button
              :loading="savingSourceTitle"
              :disabled="actionDisabled || !sourceTitle.trim() || sourceTitleUnchanged"
              @click="handleUpdateSourceTitle"
            >
              更新
            </el-button>
          </div>
        </el-form-item>

        <el-descriptions
          :column="4"
          border
          :label-width="SCRIPT_CONFIG_LABEL_WIDTH"
          :class="SCRIPT_CONFIG_DESC_CLASS"
        >
          <template v-if="!isMaterialJob">
            <el-descriptions-item label="方向">
              <el-radio-group
                v-model="jobOrientation"
                size="small"
                :disabled="savingProfile || actionDisabled"
                @change="handleOrientationChange"
              >
                <el-radio-button value="portrait">竖屏</el-radio-button>
                <el-radio-button value="landscape">横屏</el-radio-button>
              </el-radio-group>
            </el-descriptions-item>
            <el-descriptions-item label="类型">
              <el-radio-group
                v-model="contentStyle"
                size="small"
                :disabled="savingProfile || actionDisabled"
                @change="handleContentStyleChange"
              >
                <el-radio-button value="science_child">童趣科普</el-radio-button>
                <el-radio-button value="life_experience">生活经验</el-radio-button>
                <el-radio-button value="history_mystery">历史谜案</el-radio-button>
              </el-radio-group>
            </el-descriptions-item>
            <el-descriptions-item label="预计时间">
              <div class="flex items-center gap-1">
                <el-input-number
                  v-model="estimatedDurationMin"
                  :min="0.5"
                  :max="15"
                  :step="0.5"
                  :precision="1"
                  controls-position="right"
                  class="w-28!"
                  @change="syncNarrationFromEstimatedDuration"
                />
                <span class="text-xs text-gray-400">分</span>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="单镜 (秒)">
              <el-input-number
                v-model="segmentTargetSec"
                :min="0"
                :max="60"
                :step="1"
                controls-position="right"
                class="w-28!"
              />
            </el-descriptions-item>
            <el-descriptions-item label="文生图提示词">
              <el-checkbox v-model="includeImagePrompts">生成</el-checkbox>
            </el-descriptions-item>
          </template>
          <template v-else>
            <el-descriptions-item label="预计时间">
              <div class="flex flex-col gap-1">
                <div class="flex items-center gap-1">
                  <el-input-number
                    v-model="estimatedDurationMin"
                    :min="0.1"
                    :max="15"
                    :step="0.1"
                    :precision="1"
                    :disabled="materialDurationLocked"
                    controls-position="right"
                    class="w-32!"
                    @change="syncNarrationFromEstimatedDuration"
                  />
                  <span class="text-xs text-gray-400">分</span>
                </div>
                <span v-if="baseDurationHint" class="text-xs text-gray-400">{{ baseDurationHint }}</span>
              </div>
            </el-descriptions-item>
          </template>
          <el-descriptions-item label="标题上限">
            <el-input-number
              v-model="maxTitleLength"
              :min="8"
              :max="48"
              :step="1"
              controls-position="right"
              class="w-28!"
            />
          </el-descriptions-item>
          <el-descriptions-item label="预估语速">
            <div class="flex items-center gap-1">
              <el-input-number
                v-model="speechCharsPerSec"
                :min="SPEECH_CHARS_PER_SEC_MIN"
                :max="SPEECH_CHARS_PER_SEC_MAX"
                :step="0.1"
                :precision="1"
                controls-position="right"
                class="w-28!"
              />
              <span class="text-xs text-gray-400">字/秒</span>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="口播字数">
            <el-input-number
              v-model="narrationTargetWords"
              :min="NARRATION_WORDS_MIN"
              :max="NARRATION_WORDS_MAX"
              :step="50"
              controls-position="right"
              class="w-32!"
              @change="handleNarrationWordsChange"
            />
          </el-descriptions-item>
          <el-descriptions-item label="标题优化">
            <el-checkbox v-model="skipTitleOptimize">跳过</el-checkbox>
          </el-descriptions-item>
          <el-descriptions-item v-if="isMaterialJob" label="时间表" :span="3">
            <el-input
              v-model="videoTimeline"
              type="textarea"
              :rows="5"
              placeholder="可选：粘贴画面时间表 JSON（含 balls/segments/items 数组与 start_sec、end_sec），口播将逐段对齐"
              clearable
            />
          </el-descriptions-item>
          <el-descriptions-item label="补充信息" :span="3">
            <el-input
              v-model="supplementaryInfo"
              type="textarea"
              :rows="3"
              placeholder="可选：背景知识、必讲要点、表达风格、禁忌表述等（不含时间表 JSON）"
              clearable
            />
          </el-descriptions-item>
        </el-descriptions>
      </el-form>
    </div>

    <el-collapse
      v-model="promptPanelOpen"
      class="mb-4 overflow-hidden rounded-lg border border-gray-200 [&_.el-collapse-item__content]:p-4 [&_.el-collapse-item__header]:h-11 [&_.el-collapse-item__header]:border-b-0 [&_.el-collapse-item__header]:px-4 [&_.el-collapse-item__wrap]:border-t [&_.el-collapse-item__wrap]:border-gray-200"
    >
      <el-collapse-item name="prompts">
        <template #title>
          <div class="flex w-full items-center justify-between gap-3 p-2">
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
          <el-tabs v-model="activePromptTab" class="px-4">
            <el-tab-pane
              v-for="item in displayPrompts"
              :key="item.step"
              :label="promptTabLabel(item.step)"
              :name="item.step"
            >
              <div class="space-y-3 p-1">
                <div v-for="block in PROMPT_BLOCKS" :key="block.key">
                  <div class="mb-1 text-xs font-medium text-gray-500">{{ block.label }}</div>
                  <pre :class="PROMPT_PRE_CLASS">{{ item[block.key] }}</pre>
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
        :class="SCRIPT_RESULT_DESC_CLASS"
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
        <el-descriptions-item
          v-for="field in scriptClampFields"
          :key="field.label"
          :label="field.label"
        >
          <el-tooltip placement="top-start" :show-after="300">
            <template #content>
              <div
                class="max-h-96 max-w-2xl overflow-auto whitespace-pre-wrap wrap-break-word leading-relaxed"
                :class="field.mono ? 'font-mono text-xs' : 'text-sm'"
              >
                {{ field.text }}
              </div>
            </template>
            <div
              class="line-clamp-2 cursor-default leading-relaxed wrap-break-word text-gray-600"
              :class="field.mono ? 'break-all font-mono text-xs' : 'text-sm'"
            >
              {{ field.text }}
            </div>
          </el-tooltip>
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions
        :column="4"
        border
        :label-width="FORM_LABEL_WIDTH"
        :class="[SCRIPT_RESULT_DESC_CLASS, 'mb-4']"
      >
        <el-descriptions-item label="生成耗时">{{ formatCostTime(script.cost_time) }}</el-descriptions-item>
        <el-descriptions-item label="字数">{{ script.word_count ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="分镜数">{{ script.segments?.length ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="预计时长">{{ formatCostTime(scriptEstimatedDurationSec) }}</el-descriptions-item>
      </el-descriptions>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">完整口播</div>
        <div
          v-if="script.narration"
          class="rounded bg-gray-50 px-4 py-3 leading-relaxed wrap-break-word whitespace-pre-wrap"
        >
          {{ script.narration }}
        </div>
        <div v-else :class="STAGE_EMPTY_CLASS">暂无口播文案</div>
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
          <el-table-column label="时间" width="100">
            <template #default="{ row }">
              {{ formatSegmentTimeRange(row.start_sec, row.end_sec) }}
            </template>
          </el-table-column>
          <el-table-column prop="text" label="口播文案" min-width="150">
            <template #default="{ row }">
              <div class="leading-relaxed wrap-break-word whitespace-pre-wrap">{{ row.text }}</div>
            </template>
          </el-table-column>
          <template v-if="!isMaterialJob">
            <el-table-column
              v-for="col in SEGMENT_EXTRA_COLUMNS"
              :key="col.prop"
              :prop="col.prop"
              :label="col.label"
              :min-width="col.minWidth"
            >
              <template #default="{ row }">
                <div
                  class="leading-relaxed wrap-break-word whitespace-pre-wrap"
                  :class="col.muted ? 'text-xs text-gray-500' : ''"
                >
                  {{ row[col.prop] || "-" }}
                </div>
              </template>
            </el-table-column>
          </template>
        </el-table>
        <div v-else :class="STAGE_EMPTY_CLASS">暂无分镜</div>
      </div>

      <el-collapse class="mt-4">
        <el-collapse-item title="原始 JSON" name="raw">
          <pre class="m-0 max-h-[480px] overflow-auto rounded bg-gray-50 p-3 text-xs leading-normal break-all whitespace-pre-wrap">{{ rawJson }}</pre>
        </el-collapse-item>
      </el-collapse>
    </div>
    <div v-else :class="STAGE_EMPTY_CLASS">暂无脚本数据</div>

    <div :class="STAGE_SUBSECTION_CLASS">
      <div :class="STAGE_SECTION_TITLE_CLASS">质量报告</div>
      <div v-if="qualityReportRows.length" class="space-y-4">
        <el-descriptions
          v-for="row in qualityReportRows"
          :key="row.step"
          :title="row.stepLabel"
          :column="3"
          border
          size="small"
          label-width="100px"
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
      <div v-else :class="STAGE_EMPTY_CLASS">暂无数据</div>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { DocumentCopy } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getMediaDuration } from "@/api/api-media";
import {
  previewScriptPrompts,
  generateVideoDescription,
  generateImagePrompts,
  runJobStageAction,
  updateJob,
  updateJobInfo,
} from "@/api/api-jobs";
import type { JobDetail, JobLog, JobScriptParams, LlmPromptStep, ScriptJson, UpdateJobInfoParams } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { isMaterialJob as checkMaterialJob } from "@/constants/jobStages";
import {
  estimateNarrationTargetWords,
  estimatedMinutesFromNarrationWords,
  formatCostTime,
  formatMediaDuration,
  defaultNarrationTargetWords,
  DEFAULT_SPEECH_CHARS_PER_SEC,
  narrationTargetFromEstimatedMinutes,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText } from "@/utils/utils";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import { STAGE_BLOCK_CLASS, STAGE_EMPTY_CLASS, STAGE_SECTION_TITLE_CLASS, STAGE_SUBSECTION_CLASS } from "./stageLayout";

const FORM_LABEL_WIDTH = "100px";
const SCRIPT_CONFIG_LABEL_WIDTH = "120px";
const SCRIPT_CONFIG_DESC_CLASS =
  "w-full [&_.el-descriptions__label]:w-[120px]! [&_.el-descriptions__label]:min-w-[120px]! [&_.el-descriptions__label]:max-w-[120px]! [&_.el-descriptions__content]:min-w-0";
const SCRIPT_RESULT_DESC_CLASS =
  "mb-2 w-full [&_.el-descriptions__label]:w-[100px]! [&_.el-descriptions__label]:min-w-[100px]! [&_.el-descriptions__label]:max-w-[100px]!";
const PROMPT_PRE_CLASS =
  "m-0 max-h-72 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed wrap-break-word whitespace-pre-wrap";
const DEFAULT_SEGMENT_TARGET_SEC = 28;
const DEFAULT_MAX_TITLE_LENGTH = 16;
const DEFAULT_NARRATION_TARGET_WORDS = defaultNarrationTargetWords();
const DEFAULT_MATERIAL_NARRATION_TARGET_WORDS = 800;
const SPEECH_CHARS_PER_SEC_MIN = 1;
const SPEECH_CHARS_PER_SEC_MAX = 10;
const NARRATION_WORDS_MIN = 1;
const NARRATION_WORDS_MAX = 3000;

const PROMPT_BLOCKS = [
  { key: "system" as const, label: "System" },
  { key: "user" as const, label: "User" },
];

const SEGMENT_EXTRA_COLUMNS = [
  { prop: "visual_brief", label: "画面描述", minWidth: 150, muted: false },
  { prop: "image_prompt", label: "文生图提示词", minWidth: 150, muted: true },
  { prop: "motion_prompt", label: "运动提示词", minWidth: 120, muted: true },
  { prop: "sd15_prompt_en", label: "SD15 英文提示词", minWidth: 120, muted: true },
] as const;

const SCRIPT_PARAM_KEYS = [
  "segment_target_sec",
  "max_title_length",
  "estimated_duration_min",
  "narration_target_words",
  "speech_chars_per_sec",
  "skip_title_optimize",
  "generate_image_prompts",
  "supplementary_info",
  "video_timeline",
] as const satisfies readonly (keyof JobScriptParams)[];

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const savingSourceTitle = ref(false);
const regeneratingDescription = ref(false);
const generatingImagePrompts = ref(false);
const sourceTitle = ref("");
const jobOrientation = ref<"portrait" | "landscape">("portrait");
const contentStyle = ref<"science_child" | "life_experience" | "history_mystery">("science_child");
const segmentTargetSec = ref(DEFAULT_SEGMENT_TARGET_SEC);
const maxTitleLength = ref(DEFAULT_MAX_TITLE_LENGTH);
const speechCharsPerSec = ref(DEFAULT_SPEECH_CHARS_PER_SEC);
const narrationTargetWords = ref(DEFAULT_NARRATION_TARGET_WORDS);
const estimatedDurationMin = ref(
  estimatedMinutesFromNarrationWords(DEFAULT_NARRATION_TARGET_WORDS, undefined, DEFAULT_SPEECH_CHARS_PER_SEC)
);
const skipTitleOptimize = ref(false);
const includeImagePrompts = ref(false);
const supplementaryInfo = ref("");
const videoTimeline = ref("");
const baseDurationSec = ref<number | null>(null);
const narrationWordsTouched = ref(false);
const savingProfile = ref(false);
let syncingEstimateWords = false;
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

const PROMPT_TAB_ORDER_INDEX = Object.fromEntries(
  PROMPT_TAB_ORDER.map((step, index) => [step, index])
) as Record<(typeof PROMPT_TAB_ORDER)[number], number>;

const PROMPT_TAB_LABELS: Record<string, string> = {
  storyboard: "分镜",
  material_script: "口播",
  title_optimize: "标题",
  video_description: "介绍",
};

const promptTabLabel = (step: string) => PROMPT_TAB_LABELS[step] ?? step;

const displayPrompts = computed(() =>
  llmPrompts.value
    .filter(item => item.step in PROMPT_TAB_ORDER_INDEX)
    .sort((a, b) => PROMPT_TAB_ORDER_INDEX[a.step as keyof typeof PROMPT_TAB_ORDER_INDEX]
      - PROMPT_TAB_ORDER_INDEX[b.step as keyof typeof PROMPT_TAB_ORDER_INDEX])
);

const actionDisabled = computed(() => props.job.status === "running");
const isMaterialJob = computed(() => checkMaterialJob(props.job));
const materialDurationLocked = computed(
  () => isMaterialJob.value && baseDurationSec.value !== null && baseDurationSec.value > 0
);
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);
const sourceTitleUnchanged = computed(
  () => sourceTitle.value.trim() === (props.job.title || "").trim()
);

const script = computed<ScriptJson | null>(() => {
  const value = props.job.script_json;
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as ScriptJson;
});

/** 口播预计时长（秒）= 实际字数 / 预估语速 */
const scriptEstimatedDurationSec = computed(() => {
  const words = script.value?.word_count;
  if (words == null || !Number.isFinite(words) || words <= 0) {
    return null;
  }
  const params = resolveScriptParams(props.job.info);
  const rate =
    script.value?.speech_chars_per_sec ??
    params?.speech_chars_per_sec ??
    DEFAULT_SPEECH_CHARS_PER_SEC;
  if (!Number.isFinite(rate) || rate <= 0) {
    return null;
  }
  return Math.round((words / rate) * 10) / 10;
});

const rawJson = computed(() => JSON.stringify(props.job.script_json, null, 2));

const scriptClampFields = computed(() => {
  const value = script.value;
  if (!value) {
    return [] as { label: string; text: string; mono?: boolean }[];
  }
  const fields: { label: string; text: string; mono?: boolean }[] = [];
  if (isMaterialJob.value && value.video_timeline) {
    fields.push({ label: "时间表", text: value.video_timeline, mono: true });
  }
  if (value.supplementary_info) {
    fields.push({ label: "补充信息", text: value.supplementary_info });
  }
  return fields;
});

const QUALITY_STEP_LABELS: Record<string, string> = {
  copy: "文案",
  storyboard: "分镜",
  image_prompts: "文生图提示词",
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
  return `基底 ${durationLabel}，推荐约 ${estimated} 字（已同步口播字数）`;
});

const pickString = (...values: unknown[]) => {
  for (const value of values) {
    if (typeof value === "string") {
      return value;
    }
  }
  return "";
};

const applyFiniteNumber = (value: unknown, apply: (next: number) => void) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    apply(value);
  }
};

const syncNarrationFromEstimatedDuration = (minutes: number | undefined) => {
  if (minutes == null || !Number.isFinite(minutes) || minutes <= 0) {
    return;
  }
  syncingEstimateWords = true;
  narrationTargetWords.value = narrationTargetFromEstimatedMinutes(
    minutes,
    undefined,
    speechCharsPerSec.value
  );
  narrationWordsTouched.value = true;
  syncingEstimateWords = false;
};

const handleNarrationWordsChange = () => {
  narrationWordsTouched.value = true;
};

const loadBaseDuration = async () => {
  if (!isMaterialJob.value) {
    baseDurationSec.value = null;
    return;
  }
  if (!props.job.base_path) {
    baseDurationSec.value = null;
    if (!narrationWordsTouched.value) {
      narrationTargetWords.value = DEFAULT_MATERIAL_NARRATION_TARGET_WORDS;
      estimatedDurationMin.value = estimatedMinutesFromNarrationWords(
        DEFAULT_MATERIAL_NARRATION_TARGET_WORDS,
        undefined,
        speechCharsPerSec.value
      );
    }
    return;
  }
  const duration = await getMediaDuration(props.job.base_path);
  baseDurationSec.value = duration;
  if (duration !== null && duration > 0) {
    estimatedDurationMin.value = Math.round((duration / 60) * 10) / 10;
  }
  if (narrationWordsTouched.value) {
    return;
  }
  if (duration !== null && duration > 0) {
    narrationTargetWords.value = estimateNarrationTargetWords(duration, speechCharsPerSec.value);
  } else {
    narrationTargetWords.value = DEFAULT_MATERIAL_NARRATION_TARGET_WORDS;
    estimatedDurationMin.value = estimatedMinutesFromNarrationWords(
      DEFAULT_MATERIAL_NARRATION_TARGET_WORDS
    );
  }
};

const formatSegmentTimeRange = (start?: number | null, end?: number | null) => {
  if (start == null || end == null || Number.isNaN(start) || Number.isNaN(end)) {
    return "-";
  }
  return `${formatMediaDuration(start)}-${formatMediaDuration(end)}`;
};

function initJobProfileFromInfo() {
  const info = props.job.info;
  if (info?.orientation === "landscape" || info?.orientation === "portrait") {
    jobOrientation.value = info.orientation;
  }
  if (
    info?.content_style === "life_experience" ||
    info?.content_style === "science_child" ||
    info?.content_style === "history_mystery"
  ) {
    contentStyle.value = info.content_style;
  }
}

const persistJobProfile = async (patch: UpdateJobInfoParams) => {
  if (actionDisabled.value) {
    return;
  }
  savingProfile.value = true;
  try {
    await updateJobInfo(props.job.id, patch);
    emit("refresh");
  } catch (error) {
    initJobProfileFromInfo();
    handleError(error, "更新配置失败");
  } finally {
    savingProfile.value = false;
  }
};

const handleUpdateSourceTitle = async () => {
  const trimmedTitle = sourceTitle.value.trim();
  if (!trimmedTitle) {
    ElMessage.warning("请输入原标题");
    return;
  }
  if (trimmedTitle === props.job.title) {
    return;
  }
  savingSourceTitle.value = true;
  try {
    await updateJob(props.job.id, { title: trimmedTitle });
    ElMessage.success("原标题已更新");
    emit("refresh");
  } catch (error) {
    handleError(error, "更新原标题失败");
  } finally {
    savingSourceTitle.value = false;
  }
};

const handleOrientationChange = (value: "portrait" | "landscape") => {
  void persistJobProfile({ orientation: value });
};

const handleContentStyleChange = (
  value: "science_child" | "life_experience" | "history_mystery"
) => {
  void persistJobProfile({ content_style: value });
};

function resolveScriptParams(info: JobDetail["info"]): JobScriptParams | null {
  if (!info || typeof info !== "object") {
    return null;
  }
  if (info.script && typeof info.script === "object") {
    return info.script;
  }
  const legacy = info as Record<string, unknown>;
  const params: JobScriptParams = {};
  for (const key of SCRIPT_PARAM_KEYS) {
    if (key in legacy) {
      params[key] = legacy[key] as never;
    }
  }
  return Object.keys(params).length ? params : null;
}

function initScriptParamsFromInfo() {
  const scriptParams = resolveScriptParams(props.job.info);
  if (!scriptParams) {
    return;
  }
  applyFiniteNumber(scriptParams.segment_target_sec, value => {
    segmentTargetSec.value = value;
  });
  applyFiniteNumber(scriptParams.max_title_length, value => {
    maxTitleLength.value = value;
  });
  applyFiniteNumber(scriptParams.speech_chars_per_sec, value => {
    speechCharsPerSec.value = value;
  });
  applyFiniteNumber(scriptParams.estimated_duration_min, value => {
    estimatedDurationMin.value = value;
    narrationTargetWords.value = narrationTargetFromEstimatedMinutes(
      value,
      undefined,
      speechCharsPerSec.value
    );
    narrationWordsTouched.value = true;
  });
  if (scriptParams.estimated_duration_min == null) {
    applyFiniteNumber(scriptParams.narration_target_words, value => {
      narrationTargetWords.value = value;
      estimatedDurationMin.value = estimatedMinutesFromNarrationWords(
        value,
        undefined,
        speechCharsPerSec.value
      );
      narrationWordsTouched.value = true;
    });
  }
  if (typeof scriptParams.skip_title_optimize === "boolean") {
    skipTitleOptimize.value = scriptParams.skip_title_optimize;
  }
  if (typeof scriptParams.generate_image_prompts === "boolean") {
    includeImagePrompts.value = scriptParams.generate_image_prompts;
  }
}

const loadSupplementaryFields = () => {
  const scriptParams = resolveScriptParams(props.job.info);
  supplementaryInfo.value = pickString(scriptParams?.supplementary_info, script.value?.supplementary_info);
  videoTimeline.value = pickString(scriptParams?.video_timeline, script.value?.video_timeline);
};

const buildScriptPreviewParams = (title: string) => ({
  id: props.job.id,
  title,
  segment_target_sec: segmentTargetSec.value,
  max_title_length: maxTitleLength.value,
  estimated_duration_min: estimatedDurationMin.value,
  narration_target_words: Math.round(narrationTargetWords.value),
  speech_chars_per_sec: speechCharsPerSec.value,
  skip_title_optimize: skipTitleOptimize.value,
  supplementary_info: supplementaryInfo.value.trim() || undefined,
  video_timeline: videoTimeline.value.trim() || undefined,
  orientation: jobOrientation.value,
  content_style: contentStyle.value,
});

const buildRunPayload = (toEnd: boolean, trimmedTitle: string, words: number): RunStageActionPayload => {
  const payload: RunStageActionPayload = {
    id: props.job.id,
    to_end: toEnd,
    title: trimmedTitle,
    estimated_duration_min: estimatedDurationMin.value,
    narration_target_words: Math.round(words),
    speech_chars_per_sec: speechCharsPerSec.value,
  };
  if (Number.isFinite(segmentTargetSec.value)) {
    payload.segment_target_sec = segmentTargetSec.value;
  }
  if (Number.isFinite(maxTitleLength.value)) {
    payload.max_title_length = maxTitleLength.value;
  }
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
  return payload;
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
    llmPrompts.value = await previewScriptPrompts(buildScriptPreviewParams(trimmedTitle));
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
    await runJobStageAction("script", buildRunPayload(toEnd, trimmedTitle, words));
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

function resetJobLocalState() {
  narrationWordsTouched.value = false;
  speechCharsPerSec.value = DEFAULT_SPEECH_CHARS_PER_SEC;
  narrationTargetWords.value = isMaterialJob.value
    ? DEFAULT_MATERIAL_NARRATION_TARGET_WORDS
    : DEFAULT_NARRATION_TARGET_WORDS;
  estimatedDurationMin.value = estimatedMinutesFromNarrationWords(
    narrationTargetWords.value,
    undefined,
    speechCharsPerSec.value
  );
  jobOrientation.value = "portrait";
  contentStyle.value = "science_child";
  segmentTargetSec.value = DEFAULT_SEGMENT_TARGET_SEC;
  maxTitleLength.value = DEFAULT_MAX_TITLE_LENGTH;
  skipTitleOptimize.value = false;
  includeImagePrompts.value = false;
  promptPanelOpen.value = [];
  llmPrompts.value = [];
  activePromptTab.value = "";
  supplementaryInfo.value = "";
  videoTimeline.value = "";
  initJobProfileFromInfo();
  initScriptParamsFromInfo();
}

watch(
  () => props.job.id,
  () => {
    resetJobLocalState();
  }
);

watch(
  () => props.job.info,
  () => {
    initJobProfileFromInfo();
    initScriptParamsFromInfo();
    loadSupplementaryFields();
  },
  { immediate: true, deep: true }
);

watch(
  () => [script.value?.supplementary_info, script.value?.video_timeline] as const,
  () => {
    loadSupplementaryFields();
  },
  { immediate: true }
);

watch(
  [
    promptPanelOpen,
    () => sourceTitle.value,
    () => segmentTargetSec.value,
    () => maxTitleLength.value,
    () => speechCharsPerSec.value,
    () => narrationTargetWords.value,
    () => skipTitleOptimize.value,
    () => supplementaryInfo.value,
    () => videoTimeline.value,
    () => jobOrientation.value,
    () => contentStyle.value,
  ],
  () => {
    if (promptPanelOpen.value.includes("prompts")) {
      void loadLlmPrompts();
    }
  }
);

watch(
  () => [props.job.base_path, isMaterialJob.value] as const,
  () => {
    void loadBaseDuration();
  },
  { immediate: true }
);

watch(narrationTargetWords, words => {
  if (syncingEstimateWords || !Number.isFinite(words) || words <= 0) {
    return;
  }
  estimatedDurationMin.value = estimatedMinutesFromNarrationWords(
    words,
    undefined,
    speechCharsPerSec.value
  );
});

watch(speechCharsPerSec, rate => {
  if (!Number.isFinite(rate) || rate <= 0) {
    return;
  }
  syncNarrationFromEstimatedDuration(estimatedDurationMin.value);
});
</script>
