<template>
  <div>
    <div class="mb-4 flex items-center gap-3">
      <el-button type="primary" :loading="loading" @click="fetchJobs">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-select
        v-model="statusFilter"
        placeholder="全部状态"
        clearable
        class="w-40!"
        @change="fetchJobs"
      >
        <el-option label="待处理" value="pending" />
        <el-option label="运行中" value="running" />
        <el-option label="已完成" value="done" />
        <el-option label="失败" value="failed" />
      </el-select>
    </div>

    <el-table :data="jobs" stripe class="w-full" v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="stage" label="阶段" width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">
          {{ formatDateTime(row.updated_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { listJobs } from "@/api/api-jobs";
import type { JobListItem } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";

const { handleError } = useErrorHandler();

const jobs = ref<JobListItem[]>([]);
const loading = ref(false);
const statusFilter = ref<string>();

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

const fetchJobs = async () => {
  loading.value = true;
  try {
    jobs.value = await listJobs({
      status: statusFilter.value || undefined,
      limit: 100,
    });
  } catch (error) {
    handleError(error, "加载任务列表失败");
  } finally {
    loading.value = false;
  }
};

onMounted(fetchJobs);
</script>
