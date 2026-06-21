<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 p-3">
      <el-form
        label-width="88px"
        class="[&_.el-form-item]:mb-2 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1"
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
        <div v-if="!isMaterialJob" class="flex flex-wrap items-start gap-x-4">
          <el-form-item label="单镜(秒)" class="!mb-0">
            <el-input-number
              v-model="segmentTargetSec"
              :min="0"
              :max="60"
              :step="1"
              controls-position="right"
              class="w-28!"
            />
          </el-form-item>
          <el-form-item label="标题上限" class="!mb-0">
            <el-input-number
              v-model="maxTitleLength"
              :min="8"
              :max="48"
              :step="1"
              controls-position="right"
              class="w-28!"
            />
          </el-form-item>
          <el-form-item label="口播字数" class="!mb-0">
            <el-input-number
              v-model="narrationTargetWords"
              :min="NARRATION_WORDS_MIN"
              :max="NARRATION_WORDS_MAX"
              :step="50"
              controls-position="right"
              class="w-32!"
              @change="narrationWordsTouched = true"
            />
          </el-form-item>
          <el-form-item label="标题优化" class="!mb-0">
            <el-checkbox v-model="skipTitleOptimize">跳过</el-checkbox>
          </el-form-item>
        </div>
        <div v-else class="flex flex-wrap items-start gap-x-4">
          <el-form-item label="标题上限" class="!mb-0">
            <el-input-number
              v-model="maxTitleLength"
              :min="8"
              :max="48"
              :step="1"
              controls-position="right"
              class="w-28!"
            />
          </el-form-item>
          <el-form-item label="口播字数" class="!mb-0">
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
          <el-form-item label="标题优化" class="!mb-0">
            <el-checkbox v-model="skipTitleOptimize">跳过</el-checkbox>
          </el-form-item>
        </div>
        <el-form-item label="补充信息" class="!mb-0">
          <el-input
            v-model="supplementaryInfo"
            type="textarea"
            :rows="3"
            placeholder="可选：背景知识、必讲要点、禁忌表述等，将写入大模型提示词"
            clearable
          />
        </el-form-item>
      </el-form>
    </div>

    <div class="mb-4 rounded-lg border border-gray-200 p-3">
      <el-collapse v-model="promptPanelOpen">
        <el-collapse-item name="prompts">
          <template #title>
            <span class="text-sm font-medium text-gray-700">大模型提示词</span>
          </template>
          <div class="mb-3 flex flex-wrap items-center gap-3">
            <el-radio-group v-model="promptSource" size="small" @change="loadLlmPrompts">
              <el-radio-button value="preview">当前参数预览</el-radio-button>
              <el-radio-button value="saved" :disabled="!hasSavedPrompts">上次生成</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="promptsLoading" @click="loadLlmPrompts">刷新</el-button>
          </div>
          <div v-if="promptsLoading" class="py-6 text-center text-sm text-gray-400">加载中…</div>
          <div v-else-if="llmPrompts.length" class="space-y-3">
            <el-collapse accordion>
              <el-collapse-item
                v-for="item in llmPrompts"
                :key="item.step"
                :title="item.label"
                :name="item.step"
              >
                <div class="space-y-3">
                  <div>
                    <div class="mb-1 text-xs font-medium text-gray-500">System</div>
                    <pre
                      class="m-0 max-h-64 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed break-words whitespace-pre-wrap"
                    >{{ item.system }}</pre>
                  </div>
                  <div>
                    <div class="mb-1 text-xs font-medium text-gray-500">User</div>
                    <pre
                      class="m-0 max-h-64 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed break-words whitespace-pre-wrap"
                    >{{ item.user }}</pre>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
          <div v-else class="py-6 text-center text-sm text-gray-400">
            {{ sourceTitle.trim() ? "暂无提示词" : "请先填写原标题" }}
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div v-if="script">
      <el-descriptions :column="3" border class="mb-4">
        <el-descriptions-item label="脚本标题" :span="3">{{ script.title || "-" }}</el-descriptions-item>
        <el-descriptions-item
          v-if="script.draft_title && script.draft_title !== script.title"
          label="初稿标题"
          :span="3"
        >
          {{ script.draft_title }}
        </el-descriptions-item>
        <el-descriptions-item label="生成耗时">{{ formatCostTime(script.cost_time) }}</el-descriptions-item>
        <el-descriptions-item label="字数">{{ script.word_count ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="分镜数">{{ script.segments?.length ?? 0 }}</el-descriptions-item>
        <el-descriptions-item v-if="!isMaterialJob" label="画风定调" :span="3">
          {{ script.visual_style || "-" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="isMaterialJob && script.script_mode" label="文案模式">
          {{ script.script_mode === "manual" ? "手动" : "AI" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="script.supplementary_info" label="补充信息" :span="3">
          <div class="leading-relaxed break-words whitespace-pre-wrap">{{ script.supplementary_info }}</div>
        </el-descriptions-item>
      </el-descriptions>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">完整口播</div>
        <div
          v-if="script.narration"
          class="rounded bg-gray-50 px-4 py-3 leading-relaxed break-words whitespace-pre-wrap"
        >
          {{ script.narration }}
        </div>
        <div v-else class="py-8 text-center text-sm text-gray-400">暂无口播文案</div>
      </div>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">分镜列表</div>
        <el-table v-if="script.segments?.length" :data="script.segments" stripe class="w-full">
          <el-table-column prop="segment_index" label="#" width="60" />
          <el-table-column prop="text" label="口播文案" min-width="150">
            <template #default="{ row }">
              <div class="leading-relaxed break-words whitespace-pre-wrap">{{ row.text }}</div>
            </template>
          </el-table-column>
          <template v-if="!isMaterialJob">
            <el-table-column prop="visual_brief" label="画面描述" min-width="150">
              <template #default="{ row }">
                <div class="leading-relaxed break-words whitespace-pre-wrap">{{ row.visual_brief || "-" }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="visual_mode" label="模式" width="120" />
            <el-table-column prop="image_prompt" label="文生图提示词" min-width="240">
              <template #default="{ row }">
                <div class="text-xs leading-relaxed break-words whitespace-pre-wrap text-gray-500">
                  {{ row.image_prompt || "-" }}
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="motion_prompt" label="运动提示词" min-width="100">
              <template #default="{ row }">
                <div class="text-xs leading-relaxed break-words whitespace-pre-wrap text-gray-500">
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
              <div class="break-words whitespace-pre-wrap text-sm">{{ value }}</div>
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
import { ElMessage, ElMessageBox } from "element-plus";
import { getMediaDuration } from "@/api/api-media";
import { previewScriptPrompts, runJobStageAction } from "@/api/api-jobs";
import type { JobDetail, JobLog, LlmPromptStep, ScriptJson } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { isMaterialJob as checkMaterialJob } from "@/constants/jobStages";
import { formatDateTime } from "@/utils/date";
import { estimateNarrationTargetWords, formatCostTime, formatMediaDuration } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";

const DEFAULT_SEGMENT_TARGET_SEC = 12;
const DEFAULT_MAX_TITLE_LENGTH = 24;
const DEFAULT_NARRATION_TARGET_WORDS = 1050;
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
const submitting = ref(false);
const sourceTitle = ref("");
const segmentTargetSec = ref(DEFAULT_SEGMENT_TARGET_SEC);
const maxTitleLength = ref(DEFAULT_MAX_TITLE_LENGTH);
const narrationTargetWords = ref(DEFAULT_NARRATION_TARGET_WORDS);
const skipTitleOptimize = ref(false);
const supplementaryInfo = ref("");
const baseDurationSec = ref<number | null>(null);
const narrationWordsTouched = ref(false);
const promptPanelOpen = ref<string[]>([]);
const promptSource = ref<"preview" | "saved">("preview");
const promptsLoading = ref(false);
const llmPrompts = ref<LlmPromptStep[]>([]);

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

const hasSavedPrompts = computed(() => {
  const saved = script.value?.llm_prompts;
  return Array.isArray(saved) && saved.length > 0;
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

const loadSupplementaryFromScript = () => {
  supplementaryInfo.value = normalizeSupplementary(script.value?.supplementary_info);
};

const loadLlmPrompts = async () => {
  const trimmedTitle = sourceTitle.value.trim();
  if (!trimmedTitle) {
    llmPrompts.value = [];
    return;
  }
  if (promptSource.value === "saved" && hasSavedPrompts.value) {
    llmPrompts.value = script.value!.llm_prompts!;
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
      use_saved_script: promptSource.value === "saved",
    });
  } catch (error) {
    handleError(error, "加载提示词失败");
  } finally {
    promptsLoading.value = false;
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
    if (skipTitleOptimize.value) {
      payload.skip_title_optimize = true;
    }
    const extra = supplementaryInfo.value.trim();
    if (extra) {
      payload.supplementary_info = extra;
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
    promptSource.value = "preview";
    llmPrompts.value = [];
    promptPanelOpen.value = [];
    supplementaryInfo.value = "";
  }
);

watch(
  () => script.value?.supplementary_info,
  () => {
    loadSupplementaryFromScript();
  },
  { immediate: true }
);

watch(promptPanelOpen, names => {
  if (names.includes("prompts")) {
    void loadLlmPrompts();
  }
});

watch(
  () => script.value?.llm_prompts,
  saved => {
    if (promptSource.value === "saved" && Array.isArray(saved) && saved.length) {
      llmPrompts.value = saved;
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
</script>
