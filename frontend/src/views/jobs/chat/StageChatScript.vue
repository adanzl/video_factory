<template>
  <div>
    <StageActionBar :loading="submitting" :disabled="actionDisabled" :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)" @to-end="handleRun(true)" />

    <div v-if="storyLoading" class="py-4 text-center text-xs text-gray-400">
      加载对话中...
    </div>

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
        </div>

        <!-- 右侧：对话 -->
        <div class="flex-1 space-y-3 overflow-y-auto pl-2" style="border-left: 1px solid #e5e7eb;">
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
    </template>

    <div v-if="!dailyStory && !storyLoading && !loading" class="py-12 text-center text-gray-400">
      对话尚未加载
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { getDailyStory } from "@/api/api-daily-story";
import type { DailyStoryRecord } from "@/api/api-daily-story";
import type { JobDetail, JobSegment } from "@/types/jobs";
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

const submitting = ref(false);
const dailyStory = ref<DailyStoryRecord | null>(null);
const storyLoading = ref(false);

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

const loading = computed(() => props.job.stage === "dialogue" && props.job.status === "running");

const actionDisabled = computed(() => {
  return loading.value || submitting.value;
});

const actionDisabledReason = computed(() => {
  if (loading.value) return "阶段正在执行中";
  if (submitting.value) return "提交中";
  return "";
});

async function handleRun(toEnd: boolean) {
  submitting.value = true;
  try {
    await runJobStageAction("dialogue", { id: props.job.id, to_end: toEnd });
    ElMessage.success("已提交执行");
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "提交失败");
  } finally {
    submitting.value = false;
  }
}

function formatDuration(sec?: number): string {
  if (!sec || sec <= 0) return "-";
  if (sec < 60) return `约 ${Math.round(sec)} 秒`;
  const mins = Math.floor(sec / 60);
  const remain = Math.round(sec % 60);
  return remain > 0 ? `约 ${mins} 分 ${remain} 秒` : `约 ${mins} 分钟`;
}
</script>
