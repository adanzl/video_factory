<template>
  <div v-loading="loading">
    <div v-if="!jobId" class="py-12 text-center text-gray-400">
      请从任务列表点击「详情」查看任务
    </div>

    <template v-else-if="job">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <el-button type="primary" :disabled="loading" @click="() => fetchDetail()" size="small" :icon="Refresh" />
        <span class="flex-1 flex gap-2" >
          <span class="text-gray-500">#{{ job.id }}</span>
          <span class="font-medium">{{ job.title }}</span>
          <el-tag size="small" type="info">{{ pipelineLabel(job.pipeline) }}</el-tag>
          <el-tag :type="statusTagType(job.status)" size="small">{{ job.status }}</el-tag>
          <el-tag v-if="job.fail_stage" type="danger" size="small">失败于 {{ job.fail_stage }}</el-tag>
        </span>
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
      </div>

      <el-alert
        v-if="job.error_message"
        type="danger"
        :title="job.error_message"
        :closable="false"
        class="mb-4"
      />

      <el-tabs v-model="activeStage" type="border-card" lazy>
        <el-tab-pane
          v-for="stage in jobStages"
          :key="stage.name"
          :name="stage.name"
          :disabled="stage.disabled"
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
import { computed, onUnmounted, ref, watch } from "vue";
import type { Component } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getJob, getJobLogs, getJobSegments, abortJob, clearJobLogs } from "@/api/api-jobs";
import { JOB_STATUS_RUNNING } from "@/constants/job";
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
const activeStage = ref("script");

const jobStages = computed(() => (job.value ? stagesForJob(job.value) : []));

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
  return [...intro, ...cover].sort(compareLogTimeDesc);
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

const fetchDetail = async (options: { silent?: boolean } = {}) => {
  const { silent = false } = options;
  if (!props.jobId) {
    job.value = undefined;
    segments.value = [];
    logs.value = [];
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
  } catch (error) {
    if (!silent) {
      job.value = undefined;
      segments.value = [];
      logs.value = [];
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
    ElMessage.success("任务已中止");
    stopRunningPoll();
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

onUnmounted(stopRunningPoll);
</script>
