<template>
  <div>
    <StageActionBar :loading="submitting" :disabled="actionDisabled" :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)" @to-end="handleRun(true)" />

    <div class="mb-4 rounded-lg border border-gray-200 p-4">
      <el-descriptions :column="4" border label-width="100px">
        <el-descriptions-item label="原标题" :span="4">
          <div class="flex w-full min-w-0 items-center gap-2">
            <el-input v-model="sourceTitle" placeholder="脚本生成输入标题" clearable class="min-w-0 flex-1!" />
            <span class="text-xs text-gray-400 whitespace-nowrap">{{ sourceTitle.length }} 字</span>
            <el-button :loading="savingSourceTitle"
              :disabled="actionDisabled || !sourceTitle.trim() || sourceTitleUnchanged"
              @click="handleUpdateSourceTitle">
              更新
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="预计时间">
          <span class="text-sm text-gray-600">{{ estimatedDurationMin }} 分</span>
        </el-descriptions-item>
        <el-descriptions-item label="标题上限">
          <el-input-number v-model="maxTitleLength" :min="8" :max="48" :step="1" controls-position="right"
            class="w-28!" />
        </el-descriptions-item>
        <el-descriptions-item label="预估语速">
          <div class="flex items-center gap-1">
            <el-input-number v-model="speechCharsPerSec" :min="1" :max="10" :step="0.1" :precision="1"
              controls-position="right" class="w-28!" />
            <span class="text-xs text-gray-400">字/秒</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="标题优化">
          <el-checkbox v-model="skipTitleOptimize">跳过</el-checkbox>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <el-collapse v-model="promptPanelOpen"
      class="mb-4 overflow-hidden rounded-lg border border-gray-200 [&_.el-collapse-item__content]:p-4 [&_.el-collapse-item__header]:h-11 [&_.el-collapse-item__header]:border-b-0 [&_.el-collapse-item__header]:px-4 [&_.el-collapse-item__wrap]:border-t [&_.el-collapse-item__wrap]:border-gray-200">
      <el-collapse-item name="prompts">
        <template #title>
          <div class="flex w-full items-center justify-between gap-3 p-2">
            <span class="text-sm font-medium text-gray-700">大模型提示词</span>
            <el-button v-if="promptPanelOpen.includes('prompts')" size="small" :loading="promptsLoading"
              @click.stop="loadDailyPrompts">
              刷新
            </el-button>
          </div>
        </template>
        <div v-if="promptsLoading" class="py-6 text-center text-sm text-gray-400">加载中…</div>
        <template v-else-if="dailyPrompts">
          <div class="space-y-3 p-1">
            <div>
              <div class="mb-1 text-xs font-medium text-gray-500">System</div>
              <pre class="m-0 max-h-72 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed wrap-break-word whitespace-pre-wrap">{{ dailyPrompts.system }}</pre>
            </div>
            <div>
              <div class="mb-1 text-xs font-medium text-gray-500">User</div>
              <pre class="m-0 max-h-72 overflow-auto rounded bg-gray-50 p-3 text-xs leading-relaxed wrap-break-word whitespace-pre-wrap">{{ dailyPrompts.user }}</pre>
            </div>
          </div>
        </template>
        <div v-else class="py-6 text-center text-sm text-gray-400">暂无提示词</div>
      </el-collapse-item>
    </el-collapse>

    <div v-if="storyLoading" class="py-4 text-center text-xs text-gray-400">
      加载对话中...
    </div>

    <!-- 两列布局：信息 + 对话（同 DailyStoryDetail.vue 结构） -->
    <template v-if="dailyStory">
      <div class="flex gap-4">
        <!-- 左侧：信息 -->
        <div class="w-64 shrink-0 space-y-4 overflow-y-auto pr-2">
          <div>
            <div class="mb-1 text-xs text-gray-400">主题</div>
            <div class="text-sm">{{ dailyStory.theme }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">场景标题</div>
            <div class="font-bold">{{ dailyStory.story.scene_title }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">设定</div>
            <div class="text-sm text-gray-600">{{ dailyStory.story.setting }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">笑点解析</div>
            <div class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">{{ dailyStory.story.punchline_explain }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">总字数</div>
            <div class="text-sm text-gray-600">{{ totalChars }} 字</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">时长估算</div>
            <div class="text-sm text-gray-600">{{ estimatedDuration }}</div>
          </div>
          <div v-if="script">
            <div class="mb-1 text-xs text-gray-400">分镜数</div>
            <div class="text-sm text-gray-600">{{ (script.segments || []).length }}</div>
          </div>
        </div>

        <!-- 右侧：对话 -->
        <div class="flex-1 space-y-3 overflow-y-auto pl-2 max-h-130" style="border-left: 1px solid #e5e7eb;">
          <div class="mb-2 text-xs text-gray-400">对话</div>
          <div
            v-for="(line, idx) in dailyStory.story.dialogue"
            :key="idx"
            class="rounded-lg p-3"
            :class="line.speaker === '昭昭' ? 'bg-blue-50' : 'bg-pink-50'"
          >
            <div
              class="mb-1 text-xs font-bold"
              :class="line.speaker === '昭昭' ? 'text-blue-600' : 'text-pink-600'"
            >
              {{ line.speaker }}
            </div>
            <div class="text-sm">{{ line.line }}</div>
          </div>
        </div>
      </div>

      <!-- 分镜列表 -->
      <div v-if="script" class="mt-4 space-y-4">
        <div v-for="seg in script.segments || []" :key="seg.segment_index" class="rounded-lg border p-4">
          <div class="mb-2 flex items-center gap-2">
            <el-tag type="primary" size="small">第 {{ seg.segment_index }} 段</el-tag>
            <span class="text-xs text-gray-400">约 {{ seg.duration_sec }} 秒</span>
          </div>

          <div class="mb-2">
            <div class="mb-1 text-xs text-gray-400">台词</div>
            <div class="rounded-md bg-gray-50 p-3 text-sm">{{ seg.text }}</div>
          </div>

          <div v-if="seg.visual_brief" class="mb-2">
            <div class="mb-1 text-xs text-gray-400">画面概要</div>
            <div class="text-sm text-gray-600">{{ seg.visual_brief }}</div>
          </div>

          <div v-if="seg.image_prompt">
            <div class="mb-1 text-xs text-gray-400">文生图提示词</div>
            <pre class="whitespace-pre-wrap rounded-md bg-gray-50 p-3 text-xs text-gray-600">{{ seg.image_prompt }}</pre>
          </div>
        </div>
      </div>
    </template>

    <!-- 只有剧本没有对话（数据兼容） -->
    <template v-else-if="script">
      <div class="space-y-4">
        <div v-for="seg in script.segments || []" :key="seg.segment_index" class="rounded-lg border p-4">
          <div class="mb-2 flex items-center gap-2">
            <el-tag type="primary" size="small">第 {{ seg.segment_index }} 段</el-tag>
            <span class="text-xs text-gray-400">约 {{ seg.duration_sec }} 秒</span>
          </div>

          <div class="mb-2">
            <div class="mb-1 text-xs text-gray-400">台词</div>
            <div class="rounded-md bg-gray-50 p-3 text-sm">{{ seg.text }}</div>
          </div>

          <div v-if="seg.visual_brief" class="mb-2">
            <div class="mb-1 text-xs text-gray-400">画面概要</div>
            <div class="text-sm text-gray-600">{{ seg.visual_brief }}</div>
          </div>

          <div v-if="seg.image_prompt">
            <div class="mb-1 text-xs text-gray-400">文生图提示词</div>
            <pre class="whitespace-pre-wrap rounded-md bg-gray-50 p-3 text-xs text-gray-600">{{ seg.image_prompt }}</pre>
          </div>
        </div>
      </div>
    </template>

    <div v-if="!script && !dailyStory && !storyLoading && !loading" class="py-12 text-center text-gray-400">
      剧本尚未生成，请执行此阶段
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { runJobStageAction, updateJob, previewDailyScriptPrompts } from "@/api/api-jobs";
import { getDailyStory } from "@/api/api-daily-story";
import type { DailyStoryRecord } from "@/api/api-daily-story";
import type { JobDetail, JobSegment } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import type { LlmPromptStep } from "@/types/jobs/script";
import { DEFAULT_SPEECH_CHARS_PER_SEC } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageActionBar from "../detail/StageActionBar.vue";

const props = defineProps<{
  job: JobDetail;
  segments: JobSegment[];
  logs: string[];
  stageActive: boolean;
}>();

const emit = defineEmits<{
  (e: "refresh"): void;
}>();

interface ChatSegment {
  segment_index: number;
  text: string;
  visual_brief?: string;
  image_prompt?: string;
  duration_sec?: number;
}

interface ChatScript {
  title?: string;
  narration?: string;
  word_count?: number;
  segments?: ChatSegment[];
  total_duration_seconds?: number;
  daily_story_id?: number;
  daily_story_theme?: string;
  total_chars?: number;
}

const submitting = ref(false);
const dailyStory = ref<DailyStoryRecord | null>(null);
const storyLoading = ref(false);

const estimatedDurationMin = ref(2.0);
const maxTitleLength = ref(16);
const speechCharsPerSec = ref(DEFAULT_SPEECH_CHARS_PER_SEC);
const skipTitleOptimize = ref(false);
const sourceTitle = ref("");
const savingSourceTitle = ref(false);

const promptPanelOpen = ref<string[]>([]);
const promptsLoading = ref(false);
const dailyPrompts = ref<LlmPromptStep | null>(null);

/** 默认口播语速（字/秒） */
const speechRate = ref(3.1);
/** 句间停留（秒） */
const lineGap = ref(0.3);

const totalChars = computed(() => {
  const dialogue = dailyStory.value?.story?.dialogue;
  if (!dialogue) return 0;
  return dialogue.reduce((sum, line) => sum + (line.line?.length || 0), 0);
});

const estimatedDuration = computed(() => {
  const chars = totalChars.value;
  const dialogue = dailyStory.value?.story?.dialogue;
  if (chars <= 0 || !dialogue || dialogue.length === 0) return "-";
  const speakSec = chars / speechRate.value;
  const gapSec = (dialogue.length - 1) * lineGap.value;
  const secs = Math.round(speakSec + gapSec);
  if (secs < 60) return `约 ${secs} 秒`;
  const mins = Math.floor(secs / 60);
  const remain = secs % 60;
  return remain > 0 ? `约 ${mins} 分 ${remain} 秒` : `约 ${mins} 分钟`;
});

const sourceTitleUnchanged = computed(
  () => sourceTitle.value.trim() === (props.job.title || "").trim()
);

const script = computed<ChatScript | null>(() => {
  const raw = props.job.script_json;
  if (!raw || typeof raw !== "object") return null;
  return raw as ChatScript;
});

async function fetchDailyStory(storyId: number) {
  storyLoading.value = true;
  try {
    dailyStory.value = await getDailyStory(storyId);
  } catch {
    dailyStory.value = null;
  } finally {
    storyLoading.value = false;
  }
}

watch(
  () => props.job.title,
  value => {
    sourceTitle.value = value || "";
  },
  { immediate: true }
);

watch(
  () => props.job.material_id,
  (storyId) => {
    if (storyId) {
      fetchDailyStory(storyId);
    } else {
      dailyStory.value = null;
    }
  },
  { immediate: true }
);

function initScriptParamsFromInfo() {
  const info = props.job.info;
  if (!info?.script) return;
  const p = info.script;
  if (typeof p.estimated_duration_min === "number" && Number.isFinite(p.estimated_duration_min)) {
    estimatedDurationMin.value = p.estimated_duration_min;
  }
  if (typeof p.max_title_length === "number" && Number.isFinite(p.max_title_length)) {
    maxTitleLength.value = p.max_title_length;
  }
  if (typeof p.speech_chars_per_sec === "number" && Number.isFinite(p.speech_chars_per_sec)) {
    speechCharsPerSec.value = p.speech_chars_per_sec;
  }
  if (typeof p.skip_title_optimize === "boolean") {
    skipTitleOptimize.value = p.skip_title_optimize;
  }
}

watch(
  () => props.job.info,
  () => {
    initScriptParamsFromInfo();
  },
  { immediate: true, deep: true }
);

watch(
  () => promptPanelOpen.value,
  (val) => {
    if (val.includes("prompts") && !dailyPrompts.value) {
      loadDailyPrompts();
    }
  },
  { deep: true }
);

async function loadDailyPrompts() {
  if (promptsLoading.value) return;
  promptsLoading.value = true;
  try {
    const result = await previewDailyScriptPrompts(props.job.id);
    dailyPrompts.value = result.length > 0 ? result[0] : null;
  } catch (e: any) {
    handleError(e, "加载提示词失败");
    dailyPrompts.value = null;
  } finally {
    promptsLoading.value = false;
  }
}

const { handleError } = useErrorHandler();

const loading = computed(() => props.job.stage === "script" && props.job.status === "running");

const actionDisabled = computed(() => {
  return loading.value || submitting.value;
});

const actionDisabledReason = computed(() => {
  if (loading.value) return "阶段正在执行中";
  if (submitting.value) return "提交中";
  return "";
});

async function handleUpdateSourceTitle() {
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "更新失败");
  } finally {
    savingSourceTitle.value = false;
  }
}

async function handleRun(toEnd: boolean) {
  submitting.value = true;
  try {
    const payload: RunStageActionPayload = {
      id: props.job.id,
      to_end: toEnd,
      estimated_duration_min: estimatedDurationMin.value,
      speech_chars_per_sec: speechCharsPerSec.value,
    };
    if (Number.isFinite(maxTitleLength.value)) {
      payload.max_title_length = maxTitleLength.value;
    }
    if (skipTitleOptimize.value) {
      payload.skip_title_optimize = true;
    }
    await runJobStageAction("script", payload);
    ElMessage.success("已提交执行");
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "提交失败");
  } finally {
    submitting.value = false;
  }
}
</script>
