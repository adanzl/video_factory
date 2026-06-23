<template>
  <div v-loading="loading">
    <div v-if="!jobId" class="py-12 text-center text-gray-400">
      请从任务列表点击「详情」查看任务
    </div>

    <template v-else-if="job">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <el-button type="primary" :disabled="loading" @click="() => fetchDetail()">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button :loading="resetting" :disabled="loading" @click="handleReset">重置</el-button>
        <span class="font-medium">{{ job.title }}</span>
        <span class="text-gray-500">#{{ job.id }}</span>
        <el-tag size="small" type="info">{{ pipelineLabel(job.pipeline) }}</el-tag>
        <el-tag :type="statusTagType(job.status)" size="small">{{ job.status }}</el-tag>
        <el-tag v-if="job.fail_stage" type="danger" size="small">失败于 {{ job.fail_stage }}</el-tag>
      </div>

      <el-alert
        v-if="job.error_message"
        type="error"
        :title="job.error_message"
        :closable="false"
        class="mb-4"
      />

      <el-tabs v-model="activeStage" type="border-card">
        <el-tab-pane v-for="stage in jobStages" :key="stage.name" :name="stage.name">
          <template #label>
            <span>{{ stage.label }}</span>
            <el-tag v-if="job.stage === stage.name" size="small" type="warning" class="ml-1">
              当前
            </el-tag>
          </template>
          <component
            :is="STAGE_PANELS[stage.name]"
            :job="job"
            :segments="segments"
            :logs="logsByStage[stage.name] || []"
            @refresh="fetchDetail"
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
import { getJob, getJobLogs, getJobSegments, resetJob } from "@/api/api-jobs";
import { JOB_STATUS_RUNNING } from "@/constants/job";
import { pipelineLabel, stageNamesForJob, stagesForJob } from "@/constants/jobStages";
import type { JobDetail, JobLog, JobSegment } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageCover from "./StageCover.vue";
import StageHost from "./StageHost.vue";
import StageIntro from "./StageIntro.vue";
import StageMerge from "./StageMerge.vue";
import StagePrepare from "./StagePrepare.vue";
import StagePublish from "./StagePublish.vue";
import StageScript from "./StageScript.vue";
import StageSegment from "./StageSegment.vue";
import StageTitle from "./StageTitle.vue";
import StageTts from "./StageTts.vue";

const STAGE_PANELS: Record<string, Component> = {
  title: StageTitle,
  prepare: StagePrepare,
  script: StageScript,
  intro: StageIntro,
  cover: StageCover,
  tts: StageTts,
  segment: StageSegment,
  host: StageHost,
  merge: StageMerge,
  publish: StagePublish,
};

const props = defineProps<{
  jobId?: number;
}>();

const { handleError } = useErrorHandler();

const job = ref<JobDetail>();
const segments = ref<JobSegment[]>([]);
const logs = ref<JobLog[]>([]);
const loading = ref(false);
const resetting = ref(false);
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
  const names = stageNamesForJob(detail);
  if (detail.stage && names.has(detail.stage)) {
    activeStage.value = detail.stage;
  } else {
    activeStage.value = stagesForJob(detail)[0]?.name ?? "script";
  }
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

const handleReset = async () => {
  if (!job.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      "将把任务状态强制设为 pending，并清除失败信息。不会删除已生成的文件或重置 stage。",
      "重置任务",
      {
        type: "warning",
        confirmButtonText: "重置",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  resetting.value = true;
  try {
    job.value = await resetJob(job.value.id);
    ElMessage.success("任务已重置为 pending");
    stopRunningPoll();
    await fetchDetail({ silent: true });
  } catch (error) {
    handleError(error, "重置任务失败");
  } finally {
    resetting.value = false;
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
