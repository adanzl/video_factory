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
          <div :class="STAGE_PANEL_TITLE_CLASS">字幕配置</div>
          <el-form :label-width="STAGE_FORM_LABEL_WIDTH" :class="STAGE_FORM_CLASS">
            <el-form-item label="烧录字幕">
              <el-switch v-model="subtitleEnabled" :disabled="actionDisabled" />
            </el-form-item>
          </el-form>
          <div class="text-xs text-gray-400">关闭后成片不叠加字幕</div>
        </div>

        <div :class="[STAGE_PANEL_CLASS, 'mt-4']">
          <div :class="STAGE_PANEL_TITLE_CLASS">BGM 配置</div>
          <el-form :label-width="STAGE_FORM_LABEL_WIDTH" :class="STAGE_FORM_CLASS">
            <el-form-item label="启用">
              <el-switch v-model="bgmEnabled" :disabled="actionDisabled" />
            </el-form-item>
            <el-form-item label="曲目">
              <el-select
                v-model="bgmMaterialId"
                filterable
                clearable
                placeholder="从音频素材库选择"
                class="w-full!"
                :disabled="actionDisabled || !bgmEnabled"
                :loading="bgmListLoading"
              >
                <el-option
                  v-for="item in bgmOptions"
                  :key="item.id"
                  :label="bgmOptionLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="音量">
              <div class="flex w-full items-center gap-2">
                <el-slider
                  v-model="bgmVolumeDb"
                  :min="-40"
                  :max="0"
                  :step="1"
                  :disabled="actionDisabled || !bgmEnabled"
                  class="mx-2 flex-1"
                />
                <span class="w-14 shrink-0 text-xs text-gray-500">{{ bgmVolumeDb }} dB</span>
              </div>
            </el-form-item>
          </el-form>
          <audio
            v-if="bgmPreviewUrl"
            class="mt-2 block w-full"
            :src="bgmPreviewUrl"
            :crossorigin="MEDIA_CROSS_ORIGIN"
            controls
            preload="metadata"
          />
          <div v-else-if="bgmEnabled" class="mt-2 text-xs text-gray-400">
            选择曲目后可试听
          </div>
        </div>

        <div :class="[STAGE_PANEL_CLASS, 'mt-4']">
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
            type="danger"
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
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { downloadMediaFile } from "@/api/api-media";
import { listMaterialAudios } from "@/api/api-materials";
import type { MaterialAudioRecord } from "@/types/material-audio";
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
  STAGE_FORM_CLASS,
  STAGE_FORM_LABEL_WIDTH,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_HEADER_CLASS,
  STAGE_PANEL_TITLE_CLASS,
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

const subtitleEnabled = ref(true);
const bgmEnabled = ref(false);
const bgmMaterialId = ref<number | undefined>(undefined);
const bgmVolumeDb = ref(-18);
const bgmOptions = ref<MaterialAudioRecord[]>([]);
const bgmListLoading = ref(false);

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

const selectedBgm = computed(() =>
  bgmOptions.value.find((item) => item.id === bgmMaterialId.value)
);
const bgmPreviewUrl = computed(() => {
  if (!bgmEnabled.value || !selectedBgm.value?.file_path) {
    return "";
  }
  return getMediaFileUrl(selectedBgm.value.file_path);
});

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

function bgmOptionLabel(item: MaterialAudioRecord): string {
  const dur =
    item.duration_sec != null ? ` · ${formatMediaDuration(item.duration_sec)}` : "";
  return `#${item.id} ${item.name}${dur}`;
}

function syncSubtitleFromJob() {
  const subtitle = props.job.info?.subtitle;
  if (subtitle && typeof subtitle.enabled === "boolean") {
    subtitleEnabled.value = subtitle.enabled;
  } else {
    subtitleEnabled.value = true;
  }
}

function syncBgmFromJob() {
  const bgm = props.job.info?.bgm;
  bgmEnabled.value = Boolean(bgm?.enabled);
  bgmMaterialId.value =
    typeof bgm?.material_id === "number" ? bgm.material_id : undefined;
  bgmVolumeDb.value =
    typeof bgm?.volume_db === "number" ? bgm.volume_db : -18;
}

async function loadBgmOptions() {
  bgmListLoading.value = true;
  try {
    const res = await listMaterialAudios({ limit: 200, offset: 0 });
    bgmOptions.value = Array.isArray(res.items) ? res.items : [];
  } catch (error) {
    handleError(error, "加载音频素材失败");
  } finally {
    bgmListLoading.value = false;
  }
}

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认文件已生成且服务可访问";
};

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
  loadError.value = "";
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
  if (bgmEnabled.value && !bgmMaterialId.value) {
    ElMessage.warning("已启用 BGM，请先选择曲目");
    return;
  }
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
    await runJobStageAction("merge", {
      id: props.job.id,
      to_end: toEnd,
      subtitle: {
        enabled: subtitleEnabled.value,
      },
      bgm: {
        enabled: bgmEnabled.value,
        material_id: bgmMaterialId.value ?? null,
        volume_db: bgmVolumeDb.value,
      },
    });
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

watch(
  () => props.job.info?.bgm,
  () => syncBgmFromJob(),
  { deep: true }
);

watch(
  () => props.job.info?.subtitle,
  () => syncSubtitleFromJob(),
  { deep: true }
);

onMounted(() => {
  syncSubtitleFromJob();
  syncBgmFromJob();
  void loadBgmOptions();
});
</script>
