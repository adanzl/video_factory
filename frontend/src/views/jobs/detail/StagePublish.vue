<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 p-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
          重新生成
        </el-button>
        <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
          从此成片
        </el-button>
        <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
      </div>
      <el-form label-width="96px">
        <el-form-item label="跳过发布">
          <el-switch v-model="skipPublish" />
        </el-form-item>
      </el-form>
    </div>

    <el-descriptions :column="1" border class="mb-4">
      <el-descriptions-item label="跳过发布">{{ job.skip_publish ? "是" : "否" }}</el-descriptions-item>
      <el-descriptions-item label="成片路径">{{ job.final_path || "-" }}</el-descriptions-item>
    </el-descriptions>

    <el-alert v-if="job.skip_publish" type="info" title="该任务配置为跳过发布" :closable="false" />

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
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction, updateJob } from "@/api/api-jobs";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const skipPublish = ref(false);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「发布」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    if (skipPublish.value !== props.job.skip_publish) {
      await updateJob(props.job.id, { skip_publish: skipPublish.value });
    }
    await runJobStageAction("publish", { id: props.job.id, to_end: toEnd });
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.skip_publish,
  value => {
    skipPublish.value = value ?? false;
  },
  { immediate: true }
);
</script>
