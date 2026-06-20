<template>
  <div>
    <div class="flex flex-wrap items-start gap-4">
      <div class="min-w-[280px] max-w-full shrink-0 basis-80">
        <div class="mb-4 rounded-lg border border-gray-200 p-4">
          <div class="flex flex-wrap items-center gap-2">
            <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
              重新复制
            </el-button>
            <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
              从此继续
            </el-button>
            <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
          </div>
        </div>

        <el-descriptions :column="1" border label-width="80px">
          <el-descriptions-item label="素材 ID">{{ job.material_id ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="分辨率">{{ resolutionText }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ durationText }}</el-descriptions-item>
          <el-descriptions-item label="路径">
            <span class="break-all">{{ job.base_path || "-" }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="min-w-[200px] max-w-full flex-1 basis-[288px]">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">基底预览</div>
          <div v-if="videoUrl" class="flex justify-center">
            <div
              class="overflow-hidden rounded-lg border border-gray-200 bg-black"
              :style="previewBoxStyle"
            >
              <video
                :key="videoUrl"
                class="block h-full w-full bg-black object-contain"
                :src="videoUrl"
                controls
                playsinline
                preload="metadata"
                @error="onVideoError"
                @loadedmetadata="onVideoMetadata"
              />
            </div>
          </div>
          <div
            v-else-if="!job.base_path"
            class="flex items-center justify-center text-sm text-gray-400"
            :style="previewPlaceholderStyle"
          >
            暂无基底视频，请先执行 prepare
          </div>
          <el-alert
            v-if="loadError"
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
import { getMediaDuration, getMediaFileUrl } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import { formatMediaDuration } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";

const PREVIEW_MAX_VIEWPORT_RATIO = 0.7;
const PREVIEW_MAX_WIDTH_PX = 420;

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
const actualDuration = ref<number | null>(null);
const videoMeta = ref<{ width: number; height: number } | null>(null);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const videoUrl = computed(() => getMediaFileUrl(props.job.base_path ?? ""));

const buildPreviewBoxStyle = (width?: number | null, height?: number | null) => {
  if (width && height && width > 0 && height > 0) {
    const ratio = width / height;
    const maxH =
      (typeof window !== "undefined" ? window.innerHeight : 800) * PREVIEW_MAX_VIEWPORT_RATIO;
    const maxW = Math.min(
      PREVIEW_MAX_WIDTH_PX,
      typeof window !== "undefined" ? window.innerWidth * 0.9 : PREVIEW_MAX_WIDTH_PX
    );

    let boxW: number;
    let boxH: number;
    if (ratio >= 1) {
      boxW = Math.min(maxW, maxH * ratio);
      boxH = boxW / ratio;
    } else {
      boxH = Math.min(maxH, maxW / ratio);
      boxW = boxH * ratio;
    }

    return {
      width: `${Math.round(boxW)}px`,
      height: `${Math.round(boxH)}px`,
    };
  }

  return {
    width: "100%",
    maxWidth: `${PREVIEW_MAX_WIDTH_PX}px`,
    aspectRatio: "16 / 9",
  };
};

const previewBoxStyle = computed(() =>
  buildPreviewBoxStyle(videoMeta.value?.width, videoMeta.value?.height)
);

const previewPlaceholderStyle = computed(() => ({
  ...buildPreviewBoxStyle(null, null),
  minHeight: "120px",
}));

const durationText = computed(() => {
  if (!props.job.base_path) {
    return "-";
  }
  if (actualDuration.value === null) {
    return "加载中…";
  }
  return formatMediaDuration(actualDuration.value);
});

const resolutionText = computed(() => {
  const meta = videoMeta.value;
  if (meta?.width && meta?.height) {
    return `${meta.width}×${meta.height}`;
  }
  return "-";
});

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认基底文件已复制且服务可访问";
};

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
};

const loadDuration = async () => {
  if (!props.job.base_path) {
    actualDuration.value = null;
    videoMeta.value = null;
    return;
  }
  actualDuration.value = await getMediaDuration(props.job.base_path);
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此继续" : "重新复制";
  try {
    await ElMessageBox.confirm(`确定对「基底准备」执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    await runJobStageAction("prepare", { id: props.job.id, to_end: toEnd });
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.base_path,
  () => {
    loadError.value = "";
    videoMeta.value = null;
    void loadDuration();
  },
  { immediate: true }
);
</script>
