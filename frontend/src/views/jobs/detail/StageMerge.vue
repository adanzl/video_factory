<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div :class="STAGE_TWO_COL_CLASS">
      <div :class="STAGE_COL_LEFT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <el-descriptions :column="1" border label-width="70px">
          <el-descriptions-item label="分辨率">{{ resolutionText }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ durationText }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ sizeText }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ costTimeText }}</el-descriptions-item>
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
      </div>

      <div :class="STAGE_COL_RIGHT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_HEADER_CLASS">
            <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">成片预览</div>
            <el-button v-if="videoUrl" size="small" :loading="downloading" @click="handleDownload">
              下载
            </el-button>
          </div>
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
            v-else-if="!finalFilePath"
            class="flex items-center justify-center text-sm text-gray-400"
            :style="previewPlaceholderStyle"
          >
            暂无成片，请先生成
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
import { downloadMediaFile } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import {
  buildMediaPreviewBoxStyle,
  formatCostTime,
  formatFileSize,
  formatMediaDuration,
  formatVideoResolution,
  getMediaFileUrl,
  lazyMediaSrc,
  MEDIA_CROSS_ORIGIN,
  resolveFinalDuration,
  resolveFinalPath,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_COL_LEFT_CLASS,
  STAGE_COL_RIGHT_CLASS,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_HEADER_CLASS,
  STAGE_PANEL_TITLE_TEXT_CLASS,
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
const downloading = ref(false);
const loadError = ref("");
const videoMeta = ref<{ width: number; height: number } | null>(null);

const MERGE_PREVIEW_OPTIONS = {
  maxWidthPx: 560,
  maxViewportRatio: 0.85,
} as const;

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    videoMeta.value?.width,
    videoMeta.value?.height,
    "16 / 9",
    MERGE_PREVIEW_OPTIONS
  )
);

const previewPlaceholderStyle = computed(() =>
  buildMediaPreviewBoxStyle(null, null, "16 / 9", MERGE_PREVIEW_OPTIONS)
);

const resolutionText = computed(() =>
  formatVideoResolution(videoMeta.value?.width, videoMeta.value?.height)
);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const finalAsset = computed(() => props.job.final_path);
const finalFilePath = computed(() => resolveFinalPath(props.job.final_path));
const videoUrl = computed(() => getMediaFileUrl(finalFilePath.value));
const lazyVideoUrl = computed(() => lazyMediaSrc(videoUrl.value, props.stageActive));

const durationText = computed(() => {
  const duration = resolveFinalDuration(props.job.final_path);
  return duration != null ? formatMediaDuration(duration) : "-";
});

const sizeText = computed(() => {
  if (!finalAsset.value || typeof finalAsset.value !== "object") {
    return "-";
  }
  return formatFileSize(finalAsset.value.size);
});

const costTimeText = computed(() => {
  if (!finalAsset.value || typeof finalAsset.value !== "object") {
    return "-";
  }
  return formatCostTime(finalAsset.value.cost_time);
});

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认文件已生成且服务可访问";
};

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
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
  videoMeta.value = null;
});
</script>
