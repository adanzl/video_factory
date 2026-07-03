<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      primary-label="重新复制"
      to-end-label="从此继续"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div :class="STAGE_TWO_COL_CLASS">
      <div :class="STAGE_COL_LEFT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <el-descriptions :column="1" border label-width="80px">
          <el-descriptions-item label="素材 ID">{{ job.material_id ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="分辨率">{{ resolutionText }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ durationText }}</el-descriptions-item>
          <el-descriptions-item label="路径">
            <span class="break-all">{{ job.base_path || "-" }}</span>
          </el-descriptions-item>
        </el-descriptions>
        </div>
      </div>

      <div :class="STAGE_COL_RIGHT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_TITLE_CLASS">基底预览</div>
          <div v-if="videoUrl" class="flex justify-center">
            <div
              class="overflow-hidden rounded-lg border border-gray-200 bg-black"
              :style="previewBoxStyle"
            >
              <video
                :key="videoUrl"
                class="block h-full w-full bg-black object-contain"
                :src="lazyVideoUrl"
                :crossorigin="MEDIA_CROSS_ORIGIN"
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

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { getMediaDuration, getMediaFileUrl } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import {
  buildMediaPreviewBoxStyle,
  formatMediaDuration,
  formatVideoResolution,
  lazyMediaSrc,
  MEDIA_CROSS_ORIGIN,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_COL_LEFT_CLASS,
  STAGE_COL_RIGHT_CLASS,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_TITLE_CLASS,
  STAGE_TWO_COL_CLASS,
} from "./stageLayout";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
  stageActive?: boolean;
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
const lazyVideoUrl = computed(() => lazyMediaSrc(videoUrl.value, props.stageActive));

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(videoMeta.value?.width, videoMeta.value?.height)
);

const previewPlaceholderStyle = computed(() => ({
  ...buildMediaPreviewBoxStyle(null, null),
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

const resolutionText = computed(() =>
  formatVideoResolution(videoMeta.value?.width, videoMeta.value?.height)
);

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
  () => [props.job.base_path, props.stageActive] as const,
  ([path, active]) => {
    loadError.value = "";
    videoMeta.value = null;
    if (active === false || !path) {
      if (!path) {
        actualDuration.value = null;
      }
      return;
    }
    void loadDuration();
  },
  { immediate: true }
);
</script>
