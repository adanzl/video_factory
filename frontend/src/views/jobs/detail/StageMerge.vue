<template>
  <div>
    <div class="flex flex-wrap items-start gap-4">
      <div class="min-w-[280px] max-w-full shrink-0 basis-80">
        <div class="mb-4 rounded-lg border border-gray-200 p-4">
          <div class="flex flex-wrap items-center gap-2">
            <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
              重新生成
            </el-button>
            <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
              从此成片
            </el-button>
            <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
          </div>
        </div>

        <el-descriptions :column="1" border label-width="70px">
          <el-descriptions-item label="时长">{{ durationText }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ sizeText }}</el-descriptions-item>
          <el-descriptions-item label="路径">
            <span class="break-all">{{ finalFilePath || "-" }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="job.fail_stage === 'merge' && job.error_message"
          type="error"
          :title="job.error_message"
          :closable="false"
          class="mt-4"
        />
      </div>

      <div class="min-w-[200px] max-w-xs flex-1 basis-[288px]">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 flex items-center justify-between gap-2">
            <div class="text-sm font-medium text-gray-700">成片预览</div>
            <el-button v-if="videoUrl" size="small" :loading="downloading" @click="handleDownload">
              下载
            </el-button>
          </div>
          <div v-if="videoUrl" class="w-full overflow-hidden rounded-lg border border-gray-200 bg-black">
            <video
              :key="videoUrl"
              class="block aspect-[9/16] w-full bg-black"
              :src="videoUrl"
              controls
              playsinline
              preload="metadata"
              @error="onVideoError"
            />
          </div>
          <div
            v-else-if="!finalFilePath"
            class="flex aspect-[9/16] items-center justify-center text-sm text-gray-400"
          >
            暂无成片，请先生成
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
import { downloadMediaFile } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import {
  formatFileSize,
  formatMediaDuration,
  getMediaFileUrl,
  resolveFinalPath,
} from "@/utils/media";
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
const downloading = ref(false);
const loadError = ref("");

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const finalAsset = computed(() => props.job.final_path);
const finalFilePath = computed(() => resolveFinalPath(props.job.final_path));
const videoUrl = computed(() => getMediaFileUrl(finalFilePath.value));

const durationText = computed(() => {
  if (!finalAsset.value) {
    return "-";
  }
  const duration =
    typeof finalAsset.value === "object" ? finalAsset.value.duration : null;
  if (duration === null || duration === undefined) {
    return "-";
  }
  return formatMediaDuration(duration);
});

const sizeText = computed(() => {
  if (!finalAsset.value || typeof finalAsset.value !== "object") {
    return "-";
  }
  return formatFileSize(finalAsset.value.size);
});

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认文件已生成且服务可访问";
};

const downloadFilename = computed(() => {
  const fromPath = finalFilePath.value.split("/").pop();
  return fromPath || `job-${props.job.id}-final.mp4`;
});

const handleDownload = async () => {
  if (!finalFilePath.value) {
    return;
  }
  downloading.value = true;
  try {
    await downloadMediaFile(finalFilePath.value, downloadFilename.value);
    ElMessage.success("已开始下载");
  } catch (error) {
    handleError(error, "下载失败");
  } finally {
    downloading.value = false;
  }
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「合成」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    await runJobStageAction("merge", { id: props.job.id, to_end: toEnd });
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(finalFilePath, () => {
  loadError.value = "";
});
</script>
