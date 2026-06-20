<template>
  <div>
    <div class="flex flex-wrap items-start gap-4">
      <div class="min-w-[280px] max-w-full shrink-0 basis-80">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">参数配置</div>
          <div>
            <div class="mb-3 flex flex-wrap items-center gap-2">
              <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
                重新生成
              </el-button>
              <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
                从此成片
              </el-button>
              <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
            </div>
          </div>
          <el-form label-width="96px" class="[&_.el-form-item]:mb-2">
            <el-form-item label="封面路径">
              <span class="break-all text-gray-600">{{ job.cover_path || "-" }}</span>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="min-w-[280px] flex-1 basis-[360px]">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">图片预览</div>
          <div
            v-if="imageUrl"
            class="flex h-[405px] w-full items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50"
          >
            <el-image
              :key="imageUrl"
              :src="imageUrl"
              :preview-src-list="[imageUrl]"
              fit="contain"
              class="block h-full w-full [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
              @error="onImageError"
            />
          </div>
          <div v-else-if="!job.cover_path" class="py-8 text-center text-sm text-gray-400">
            暂无封面图片，请先生成
          </div>
          <el-alert
            v-else-if="loadError"
            type="warning"
            :title="loadError"
            :closable="false"
            class="mt-2"
          />
        </div>
      </div>
    </div>

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
import { runJobStageAction } from "@/api/api-jobs";
import { getMediaFileUrl } from "@/api/api-media";
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
const loadError = ref("");

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const imageUrl = computed(() => getMediaFileUrl(props.job.cover_path ?? ""));

const onImageError = () => {
  loadError.value = "图片加载失败，请确认文件已生成且服务可访问";
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「封面」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    await runJobStageAction("cover", { id: props.job.id, to_end: toEnd });
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.cover_path,
  () => {
    loadError.value = "";
  }
);
</script>
