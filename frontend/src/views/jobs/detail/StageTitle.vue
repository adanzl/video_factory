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
      <el-form :label-width="STAGE_FORM_LABEL_WIDTH">
        <el-form-item label="标题">
          <el-input v-model="title" placeholder="任务标题" clearable class="max-w-xl!" />
        </el-form-item>
      </el-form>
    </div>

    <div :class="STAGE_PANEL_CLASS">
      <el-descriptions :column="2" border>
      <el-descriptions-item label="任务 ID">{{ job.id }}</el-descriptions-item>
      <el-descriptions-item label="标题">{{ job.title }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="statusTagType(job.status)" size="small">{{ job.status }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="重试次数">{{ job.retry_count ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ formatDateTime(job.created_at) }}</el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ formatDateTime(job.updated_at) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { updateJob } from "@/api/api-jobs";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import { STAGE_BLOCK_CLASS, STAGE_FORM_LABEL_WIDTH, STAGE_PANEL_CLASS } from "./stageLayout";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const title = ref("");
const submitting = ref(false);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() => {
  if (props.job.status === "running") {
    return "任务运行中，请稍后再试";
  }
  return "标题阶段暂无重跑接口，可修改标题后从脚本阶段重跑";
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

const handleRun = async () => {
  submitting.value = true;
  try {
    const nextTitle = title.value.trim();
    if (nextTitle && nextTitle !== props.job.title) {
      await updateJob(props.job.id, { title: nextTitle });
      ElMessage.success("标题已更新");
    } else {
      ElMessage.info("标题阶段无可执行的重跑动作");
    }
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.title,
  value => {
    title.value = value;
  },
  { immediate: true }
);
</script>
