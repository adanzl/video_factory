<template>
  <div>
    <div class="mb-4 flex items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchJobs" :icon="Refresh" size="small" />
      <el-button type="primary" @click="openCreateJobDialog" size="small">创建任务</el-button>
      <!-- 类型筛选 -->
      <el-radio-group v-model="pipelineFilter" size="small" @change="onFilterChange">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button :value="PIPELINE_STANDARD">标准</el-radio-button>
        <el-radio-button :value="PIPELINE_MATERIAL">素材</el-radio-button>
        <el-radio-button :value="PIPELINE_CHAT">对话</el-radio-button>
      </el-radio-group>
      <el-select
        v-model="statusFilter"
        placeholder="全部状态"
        clearable
        class="w-30!"
        size="small"
        @change="onFilterChange"
      >
        <el-option label="待处理" value="pending" />
        <el-option label="运行中" value="running" />
        <el-option label="已完成" value="done" />
        <el-option label="失败" value="failed" />
      </el-select>
    </div>

    <el-table
      :data="jobs"
      stripe
      class="w-full"
      v-loading="loading"
      @row-dblclick="handleRowDblClick"
    >
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.pipeline === PIPELINE_MATERIAL ? 'warning' : row.pipeline === PIPELINE_CHAT ? 'danger' : row.pipeline === PIPELINE_STANDARD ? 'primary' : 'info'">{{ pipelineLabel(row.pipeline) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" width="120" align="center" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时长" width="90" align="center">
        <template #default="{ row }">
          {{ formatJobDuration(row) }}
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">
          {{ formatDateTime(row.updated_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="错误信息" width="100" show-overflow-tooltip />
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
      :page-sizes="[15, 20]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="fetchJobs"
      @size-change="onPageSizeChange"
    />

    <el-dialog v-model="showCreateJobDialog" title="创建任务" width="520px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="视频标题" required>
          <el-input v-model="createJobTitle" placeholder="成片标题" clearable />
        </el-form-item>
        <el-form-item label="跳过投稿">
          <el-switch v-model="createJobSkipPublish" />
        </el-form-item>
        <el-form-item label="执行方式">
          <el-radio-group v-model="createJobRunMode" class="create-job-run-mode">
            <el-radio value="script">仅文案（默认，第一步）</el-radio>
            <el-radio value="none">仅创建任务，暂不执行</el-radio>
            <el-radio value="full">全流程（文案 → 成片）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateJobDialog = false">取消</el-button>
        <el-button type="primary" :loading="creatingJob" @click="handleCreateJob">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createJob, deleteJob, listJobs } from "@/api/api-jobs";
import { pipelineLabel } from "@/constants/jobStages";
import { PIPELINE_CHAT, PIPELINE_MATERIAL, PIPELINE_STANDARD } from "@/constants/jobStages";
import type { CreateJobRunMode, JobListItem } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import { formatMediaDuration, resolveFinalDuration } from "@/utils/media";

const emit = defineEmits<{
  viewDetail: [jobId: number];
}>();

const { handleError } = useErrorHandler();

const jobs = ref<JobListItem[]>([]);
const loading = ref(false);
const statusFilter = ref<string>();
const pipelineFilter = ref("");
const page = ref(1);
const pageSize = ref(15);
const total = ref(0);
const deletingId = ref<number>();
const showCreateJobDialog = ref(false);
const createJobTitle = ref("");
const createJobSkipPublish = ref(true);
const createJobRunMode = ref<CreateJobRunMode>("script");
const creatingJob = ref(false);

const statusTagType = (status: string) => {
  switch (status) {
    case "done":
      return "success";
    case "running":
      return "warning";
    case "failed":
      return "danger";
    case "idle":
      return "info";
    default:
      return "info";
  }
};

const statusLabel = (status: string) => {
  switch (status) {
    case "pending":
    case "idle": // 历史数据兼容
      return "待处理";
    case "running":
      return "运行中";
    case "done":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
};

const formatJobDuration = (row: JobListItem) => {
  const duration = resolveFinalDuration(row.final_path);
  return duration != null ? formatMediaDuration(duration) : "-";
};

const fetchJobs = async () => {
  loading.value = true;
  try {
    const res = await listJobs({
      status: statusFilter.value || undefined,
      pipeline: pipelineFilter.value || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    });
    jobs.value = res.items;
    total.value = res.total;
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

const handleRowDblClick = (row: JobListItem) => {
  handleViewDetail(row.id);
};

const openCreateJobDialog = () => {
  createJobTitle.value = "";
  createJobSkipPublish.value = true;
  createJobRunMode.value = "script";
  showCreateJobDialog.value = true;
};

const createJobRunModeLabel = (mode: CreateJobRunMode) => {
  switch (mode) {
    case "script":
      return "已创建并开始文案生成";
    case "full":
      return "已创建并开始全流程";
    default:
      return "已创建任务";
  }
};

const handleCreateJob = async () => {
  if (!createJobTitle.value.trim()) {
    ElMessage.warning("请填写标题");
    return;
  }
  creatingJob.value = true;
  try {
    const runMode = createJobRunMode.value;
    const job = await createJob({
      title: createJobTitle.value.trim(),
      skip_publish: createJobSkipPublish.value,
      run_mode: runMode,
    });
    ElMessage.success(`${createJobRunModeLabel(runMode)}，任务 #${job.id}`);
    showCreateJobDialog.value = false;
    page.value = 1;
    await fetchJobs();
  } catch (error) {
    handleError(error, "创建任务失败");
  } finally {
    creatingJob.value = false;
  }
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

defineExpose({ refresh: fetchJobs });
</script>
