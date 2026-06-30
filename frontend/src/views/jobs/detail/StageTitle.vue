<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div class="mb-4 rounded-lg border border-gray-200 p-4">
      <el-form label-width="96px">
        <el-form-item label="标题">
          <el-input v-model="title" placeholder="任务标题" clearable class="max-w-xl!" />
        </el-form-item>
      </el-form>
    </div>

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
import { ElMessage } from "element-plus";
import { updateJob } from "@/api/api-jobs";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import StageActionBar from "./StageActionBar.vue";

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
