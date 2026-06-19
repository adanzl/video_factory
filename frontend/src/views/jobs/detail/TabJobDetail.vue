<template>
  <div v-loading="loading">
    <div v-if="!jobId" class="py-12 text-center text-gray-400">
      请从任务列表点击「详情」查看任务
    </div>

    <template v-else-if="job">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <el-button type="primary" :loading="loading" @click="fetchDetail">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <span class="font-medium">{{ job.title }}</span>
        <span class="text-gray-500">#{{ job.id }}</span>
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
        <el-tab-pane v-for="stage in JOB_STAGES" :key="stage.name" :name="stage.name">
          <template #label>
            <span>{{ stage.label }}</span>
            <el-tag v-if="job.stage === stage.name" size="small" type="warning" class="ml-1">
              当前
            </el-tag>
          </template>
          <JobDetailStagePanel
            :stage="stage.name"
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
import { computed, ref, watch } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { getJob, getJobLogs, getJobSegments } from "@/api/api-jobs";
import { JOB_STAGE_NAMES, JOB_STAGES } from "@/constants/jobStages";
import type { JobDetail, JobLog, JobSegment } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import JobDetailStagePanel from "./JobDetailStagePanel.vue";

const props = defineProps<{
  jobId?: number;
}>();

const { handleError } = useErrorHandler();

const job = ref<JobDetail>();
const segments = ref<JobSegment[]>([]);
const logs = ref<JobLog[]>([]);
const loading = ref(false);
const activeStage = ref(JOB_STAGES[0].name);

const logsByStage = computed(() => {
  const grouped: Record<string, JobLog[]> = {};
  for (const entry of logs.value) {
    if (!grouped[entry.stage]) {
      grouped[entry.stage] = [];
    }
    grouped[entry.stage].push(entry);
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
  if (detail.stage && JOB_STAGE_NAMES.has(detail.stage)) {
    activeStage.value = detail.stage;
  } else {
    activeStage.value = JOB_STAGES[0].name;
  }
};

const fetchDetail = async () => {
  if (!props.jobId) {
    job.value = undefined;
    segments.value = [];
    logs.value = [];
    return;
  }

  loading.value = true;
  try {
    const [detail, segmentList, logList] = await Promise.all([
      getJob(props.jobId),
      getJobSegments(props.jobId),
      getJobLogs(props.jobId),
    ]);
    job.value = detail;
    segments.value = segmentList;
    logs.value = logList;
    syncActiveStage(detail);
  } catch (error) {
    job.value = undefined;
    segments.value = [];
    logs.value = [];
    handleError(error, "加载任务详情失败");
  } finally {
    loading.value = false;
  }
};

watch(
  () => props.jobId,
  () => {
    fetchDetail();
  },
  { immediate: true }
);
</script>
