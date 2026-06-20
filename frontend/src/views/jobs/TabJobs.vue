<template>
  <div>
    <div class="mb-4 flex items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchJobs">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-select
        v-model="statusFilter"
        placeholder="全部状态"
        clearable
        class="w-40!"
        @change="onFilterChange"
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
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handleViewDetail(row.id)">
            详情
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            :loading="deletingId === row.id"
            @click="handleDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="fetchJobs"
      @size-change="onPageSizeChange"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteJob, listJobs } from "@/api/api-jobs";
import type { JobListItem } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";

const emit = defineEmits<{
  viewDetail: [jobId: number];
}>();

const { handleError } = useErrorHandler();

const jobs = ref<JobListItem[]>([]);
const loading = ref(false);
const statusFilter = ref<string>();
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const deletingId = ref<number>();

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

const updateTotal = (count: number) => {
  if (count < pageSize.value) {
    total.value = (page.value - 1) * pageSize.value + count;
  } else {
    total.value = page.value * pageSize.value + 1;
  }
};

const fetchJobs = async () => {
  loading.value = true;
  try {
    const list = await listJobs({
      status: statusFilter.value || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    });
    jobs.value = list;
    updateTotal(list.length);
  } catch (error) {
    handleError(error, "加载任务列表失败");
  } finally {
    loading.value = false;
  }
};

const onFilterChange = () => {
  page.value = 1;
  fetchJobs();
};

const onPageSizeChange = () => {
  page.value = 1;
  fetchJobs();
};

const handleViewDetail = (jobId: number) => {
  emit("viewDetail", jobId);
};

const handleDelete = async (row: JobListItem) => {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.title}」吗？`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  deletingId.value = row.id;
  try {
    await deleteJob(row.id);
    ElMessage.success("删除成功");
    if (jobs.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await fetchJobs();
  } catch (error) {
    handleError(error, "删除任务失败");
  } finally {
    deletingId.value = undefined;
  }
};

onMounted(fetchJobs);
</script>
