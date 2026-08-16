<template>
  <div v-loading="loading" class="flex h-full min-h-0 flex-col">
    <div v-if="!jobId" class="py-12 text-center text-gray-400">
      请从任务列表点击「详情」查看任务
    </div>

    <template v-else-if="job">
      <div class="mb-4 flex shrink-0 flex-wrap items-center gap-0">
        <el-button type="primary" :disabled="loading" @click="() => fetchDetail()" size="small" :icon="Refresh" />
        <span class="flex-1 flex gap-2 px-2" >
          <span class="text-gray-500">#{{ job.id }}</span>
          <span class="font-medium">{{ job.title }}</span>
          <el-tag size="small" type="info">{{ pipelineLabel(job.pipeline) }}</el-tag>
          <el-tag v-if="typeTagLabel" size="small" type="info">{{ typeTagLabel }}</el-tag>
          <el-tag :type="statusTagType(job.status)" size="small">{{ job.status }}</el-tag>
          <el-tag v-if="job.fail_stage" type="danger" size="small">失败于 {{ job.fail_stage }}</el-tag>
        </span>
        <el-button
          :loading="doneLoading"
          :disabled="loading"
          size="small"
          type="primary"
          @click="handleDone"
        >
          Done
        </el-button>
        <el-button
          type="danger"
          :loading="aborting"
          :disabled="loading"
          size="small"
          @click="handleAbort"
        >
          中止
        </el-button>
        <el-button
          :loading="clearingLogs"
          :disabled="loading"
          size="small"
          type="success"
          @click="handleClearLogs"
        >
          清日志
        </el-button>
        <el-button
          :type="job.publish ? 'success' : 'info'"
          :loading="publishing"
          :disabled="loading"
          size="small"
          @click="handleTogglePublish"
        >
          {{ job.publish ? "已发布" : "未发布" }}
        </el-button>
      </div>

      <el-alert
        v-if="job.error_message && job.status === 'failed'"
        type="danger"
        :title="job.error_message"
        :closable="false"
        class="mb-4 shrink-0"
      />

      <el-tabs
        v-model="activeStage"
        type="border-card"
        lazy
        class="stage-tabs flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        <el-tab-pane
          v-for="stage in jobStages"
          :key="stage.name"
          :name="stage.name"
          :disabled="stage.disabled"
          class="h-full min-h-0"
        >
          <template #label>
            <span>{{ stage.label }}</span>
            <el-tag v-if="job.stage === stage.name" size="small" type="warning" class="ml-1">
              当前
            </el-tag>
          </template>
          <component
            :is="stagePanelFor(stage.name, job.pipeline)"
            :job="job"
            :segments="segments"
            :logs="logsForStage(stage.name)"
            :stage-active="activeStage === stage.name"
            @refresh="() => fetchDetail({ silent: true })"
          />
        </el-tab-pane>
      </el-tabs>
    </template>

    <div v-else-if="!loading" class="py-12 text-center text-gray-400">任务不存在或加载失败</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from "vue";
import type { Component } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getJob, getJobLogs, getJobSegments, abortJob, clearJobLogs, updateJob } from "@/api/api-jobs";
import { formatDailyStoryType, getDailyStory } from "@/api/api-daily-story";
import { JOB_STATUS_RUNNING, JOB_STATUS_DONE } from "@/constants/job";
import { pipelineLabel, resolveActiveStageTab, stagesForJob, PIPELINE_CHAT } from "@/constants/jobStages";
import type { JobDetail, JobLog, JobSegment } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageIntro from "./detail/StageIntro.vue";
import StageMerge from "./detail/StageMerge.vue";
import StagePrepare from "./video/StagePrepare.vue";
import StagePublish from "./detail/StagePublish.vue";
import StageStandardScript from "./standard/StageStandardScript.vue";
import StageSegment from "./detail/StageSegment.vue";
import StageTts from "./detail/StageTts.vue";
import StageChatScript from "./chat/StageChatScript.vue";
import StageChatTts from "./chat/StageChatTts.vue";

const CONTENT_STYLE_LABELS: Record<string, string> = {
  science_child: "童趣科普",
  life_experience: "生活经验",
  history_mystery: "历史谜案",
  daily_story: "日常故事",
  tech_science: "科技科普",
};

const STAGE_PANELS: Record<string, Component> = {
  prepare: StagePrepare,
  script: StageStandardScript,
  intro: StageIntro,
  tts: StageTts,
  segment: StageSegment,
  merge: StageMerge,
  publish: StagePublish,
};

function stagePanelFor(stageName: string, pipeline?: string | null): Component {
  if (pipeline === PIPELINE_CHAT) {
    if (stageName === "script") return StageChatScript;
    if (stageName === "tts") return StageChatTts;
  }
  return STAGE_PANELS[stageName] ?? StageStandardScript;
}

const props = defineProps<{
  jobId?: number;
}>();

const { handleError } = useErrorHandler();

const job = ref<JobDetail>();
const segments = ref<JobSegment[]>([]);
const logs = ref<JobLog[]>([]);
const loading = ref(false);
const aborting = ref(false);
const clearingLogs = ref(false);
const publishing = ref(false);
const doneLoading = ref(false);
const activeStage = ref("script");
/** chat 流水线：日常故事矛盾类型展示文案 */
const chatStoryTypeLabel = ref<string | null>(null);

const jobStages = computed(() => (job.value ? stagesForJob(job.value) : []));

const typeTagLabel = computed(() => {
  if (!job.value) return "";
  if (job.value.pipeline === PIPELINE_CHAT) {
    return chatStoryTypeLabel.value || "";
  }
  const style = job.value.info?.content_style;
  return (style && CONTENT_STYLE_LABELS[style]) || "";
});

const RUNNING_POLL_INTERVAL_MS = 3000;
let runningPollTimer: ReturnType<typeof setInterval> | null = null;

const compareLogTimeDesc = (a: JobLog, b: JobLog) => {
  const ta = a.created_at ? Date.parse(a.created_at) : 0;
  const tb = b.created_at ? Date.parse(b.created_at) : 0;
  return tb - ta;
};

const logsByStage = computed(() => {
  const grouped: Record<string, JobLog[]> = {};
  for (const entry of logs.value) {
    if (!grouped[entry.stage]) {
      grouped[entry.stage] = [];
    }
    grouped[entry.stage].push(entry);
  }
  for (const stage of Object.keys(grouped)) {
    grouped[stage].sort(compareLogTimeDesc);
  }
  return grouped;
});

const introLogs = computed(() => {
  const intro = logsByStage.value.intro ?? [];
  const cover = logsByStage.value.cover ?? [];
  const end = logsByStage.value.end ?? [];
  return [...intro, ...cover, ...end].sort(compareLogTimeDesc);
});

const logsForStage = (stageName: string) =>
  stageName === "intro" ? introLogs.value : logsByStage.value[stageName] ?? [];

const statusTagType = (status: string) => {
  switch (status) {
    case "done":
      return "success";
    case "running":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "info";
  }
};

const syncActiveStage = (detail: JobDetail) => {
  activeStage.value = resolveActiveStageTab(detail, detail.stage);
};

async function loadChatStoryType(detail: JobDetail) {
  if (detail.pipeline !== PIPELINE_CHAT) {
    chatStoryTypeLabel.value = null;
    return;
  }
  const storyId = detail.info?.daily_story_id ?? detail.material_id;
  if (!storyId) {
    chatStoryTypeLabel.value = null;
    return;
  }
  try {
    const story = await getDailyStory(storyId);
    const label = formatDailyStoryType(story.story_type);
    chatStoryTypeLabel.value = label === "-" ? null : label;
  } catch {
    chatStoryTypeLabel.value = null;
  }
}

const fetchDetail = async (options: { silent?: boolean } = {}) => {
  const { silent = false } = options;
  if (!props.jobId) {
    job.value = undefined;
    segments.value = [];
    logs.value = [];
    chatStoryTypeLabel.value = null;
    return;
  }

  if (!silent) {
    loading.value = true;
  }
  try {
    const [detail, segmentList, logList] = await Promise.all([
      getJob(props.jobId),
      getJobSegments(props.jobId),
      getJobLogs(props.jobId),
    ]);
    job.value = detail;
    segments.value = segmentList;
    logs.value = logList;
    await loadChatStoryType(detail);
  } catch (error) {
    if (!silent) {
      job.value = undefined;
      segments.value = [];
      logs.value = [];
      chatStoryTypeLabel.value = null;
      handleError(error, "加载任务详情失败");
    }
  } finally {
    if (!silent) {
      loading.value = false;
    }
  }
};

const handleClearLogs = async () => {
  if (!job.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      "将清空该任务的所有日志记录，此操作不可恢复。",
      "清日志",
      {
        type: "warning",
        confirmButtonText: "清日志",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  clearingLogs.value = true;
  try {
    const result = await clearJobLogs(job.value.id);
    logs.value = [];
    ElMessage.success(`已清空 ${result.deleted_count} 条日志`);
  } catch (error) {
    handleError(error, "清空日志失败");
  } finally {
    clearingLogs.value = false;
  }
};

const handleTogglePublish = async () => {
  if (!job.value) {
    return;
  }
  const next = !job.value.publish;
  publishing.value = true;
  try {
    await updateJob(job.value.id, { publish: next });
    job.value.publish = next;
    ElMessage.success(next ? "已标记为已发布" : "已标记为未发布");
  } catch (error) {
    handleError(error, "更新发布状态失败");
  } finally {
    publishing.value = false;
  }
};

const handleDone = async () => {
  if (!job.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      "将把任务状态标记为已完成（done），确认？",
      "完成任务",
      {
        type: "success",
        confirmButtonText: "确认",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  doneLoading.value = true;
  try {
    job.value = await updateJob(job.value.id, { status: JOB_STATUS_DONE, stage: "done" });
    ElMessage.success("任务已标记为完成");
  } catch (error) {
    handleError(error, "标记任务完成失败");
  } finally {
    doneLoading.value = false;
  }
};

const handleAbort = async () => {
  if (!job.value) {
    return;
  }
  const isRunning = job.value.status === JOB_STATUS_RUNNING;
  try {
    await ElMessageBox.confirm(
      isRunning
        ? "将中止当前正在执行的任务。已完成的步骤会保留，未完成的步骤会在当前操作结束后停止。"
        : "将把任务状态设为 pending，并清除失败信息。不会删除已生成的文件或重置 stage。",
      "中止任务",
      {
        type: "warning",
        confirmButtonText: "中止",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  aborting.value = true;
  try {
    job.value = await abortJob(job.value.id);
    if (job.value.status === JOB_STATUS_RUNNING) {
      ElMessage.success("已请求中止，等待当前步骤结束");
      startRunningPoll();
    } else {
      ElMessage.success("任务已中止");
      stopRunningPoll();
    }
    await fetchDetail({ silent: true });
  } catch (error) {
    handleError(error, "中止任务失败");
  } finally {
    aborting.value = false;
  }
};

const stopRunningPoll = () => {
  if (runningPollTimer !== null) {
    clearInterval(runningPollTimer);
    runningPollTimer = null;
  }
};

const startRunningPoll = () => {
  stopRunningPoll();
  runningPollTimer = setInterval(() => {
    void fetchDetail({ silent: true });
  }, RUNNING_POLL_INTERVAL_MS);
};

watch(
  () => job.value?.status,
  status => {
    if (status === JOB_STATUS_RUNNING) {
      startRunningPoll();
    } else {
      stopRunningPoll();
    }
  }
);

watch(
  () => props.jobId,
  async () => {
    stopRunningPoll();
    await fetchDetail();
    if (job.value) {
      syncActiveStage(job.value);
    }
  },
  { immediate: true }
);

onActivated(() => {
  if (job.value?.status === JOB_STATUS_RUNNING) {
    startRunningPoll();
  }
});
onDeactivated(stopRunningPoll);
onUnmounted(stopRunningPoll);

defineExpose({
  refresh: () => fetchDetail(),
});
</script>

<style scoped>
.stage-tabs :deep(> .el-tabs__header) {
  flex-shrink: 0;
}

.stage-tabs :deep(> .el-tabs__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.stage-tabs :deep(> .el-tabs__content > .el-tab-pane) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
</style>
