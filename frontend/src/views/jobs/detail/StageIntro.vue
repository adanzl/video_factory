<template>
  <div>
    <div class="flex flex-wrap items-start gap-4">
      <div class="min-w-[280px] max-w-full shrink-0 basis-80">
        <div class="rounded-lg border border-gray-200 p-4">
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
              重新生成
            </el-button>
            <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
              从此成片
            </el-button>
            <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
          </div>
          <el-form
            label-width="96px"
            class="[&_.el-form-item]:mb-3 [&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1"
          >
            <el-form-item label="片头风格">
              <el-radio-group
                v-model="introCategory"
                class="intro-orientation-group"
                :disabled="savingIntroCategory || actionDisabled"
                @change="handleIntroCategoryChange"
              >
                <el-radio value="百科">童趣百科</el-radio>
                <el-radio value="历史悬案">历史悬案</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="画面方向">
              <el-radio-group v-model="introOrientation" class="intro-orientation-group">
                <el-radio value="auto">自动</el-radio>
                <el-radio value="portrait">竖屏 9:16</el-radio>
                <el-radio value="landscape">横屏 16:9</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="尾部停留">
              <el-input-number
                v-model="holdTailSec"
                :min="0"
                :max="5"
                :step="0.05"
                placeholder="秒"
                controls-position="right"
                class="w-40!"
              />
              <span class="ml-2 text-sm text-gray-500">秒</span>
            </el-form-item>
            <el-form-item label="成片时长">
              <span class="text-gray-700">{{ actualDurationText }}</span>
            </el-form-item>
            <el-form-item label="片头路径">
              <span class="break-all text-gray-600">{{ job.intro_path || "-" }}</span>
            </el-form-item>
            <el-form-item label="封面路径">
              <span class="break-all text-gray-600">{{ job.cover_path || "-" }}</span>
            </el-form-item>
          </el-form>
          <p class="mt-1 text-xs leading-normal text-gray-400">
            总时长 = 品牌喊声时长 + 尾部停留；封面由片头预览帧自动生成。「自动」时素材任务跟随基底视频分辨率。
          </p>
        </div>
      </div>

      <div class="min-w-[280px] flex-1 basis-[360px]">
        <div class="rounded-lg border border-gray-200 p-4">
          <div class="mb-3 flex items-baseline justify-between gap-2">
            <span class="text-sm font-medium text-gray-700">片头预览</span>
            <span class="text-xs text-gray-400">{{ introResolutionText }}</span>
          </div>
          <div v-if="videoUrl" class="flex justify-center">
            <div
              class="relative overflow-hidden rounded-lg border border-gray-200 bg-black"
              :style="previewBoxStyle"
            >
              <video
                ref="videoRef"
                :key="videoUrl"
                class="absolute inset-0 size-full bg-black object-contain"
                :src="videoUrl"
                :poster="posterUrl || undefined"
                :crossorigin="MEDIA_CROSS_ORIGIN"
                controls
                playsinline
                preload="auto"
                @error="onVideoError"
                @loadeddata="onVideoMetadata"
                @loadedmetadata="onVideoMetadata"
              />
            </div>
          </div>
          <div v-else-if="!job.intro_path" class="py-8 text-center text-sm text-gray-400">
            暂无片头视频，请先生成
          </div>
          <el-alert
            v-else-if="loadError"
            type="warning"
            :title="loadError"
            :closable="false"
            class="mt-2"
          />
        </div>

        <div class="mt-4 rounded-lg border border-gray-200 p-4">
          <div class="mb-3 flex items-baseline justify-between gap-2">
            <span class="text-sm font-medium text-gray-700">封面预览</span>
            <span class="text-xs text-gray-400">{{ coverResolutionText }}</span>
          </div>
          <div v-if="coverUrl" class="flex justify-center">
            <div
              class="flex items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50"
              :style="coverBoxStyle"
            >
              <el-image
                :key="coverUrl"
                :src="coverUrl"
                :preview-src-list="[coverUrl]"
                :crossorigin="MEDIA_CROSS_ORIGIN"
                fit="contain"
                class="block h-full w-full [&_.el-image__inner]:block [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
                @load="onCoverLoad"
                @error="onCoverError"
              />
            </div>
          </div>
          <div v-else-if="!job.cover_path" class="py-8 text-center text-sm text-gray-400">
            暂无封面，生成片头后自动产出
          </div>
          <el-alert
            v-else-if="coverLoadError"
            type="warning"
            :title="coverLoadError"
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
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction, updateJobInfo } from "@/api/api-jobs";
import { getMediaDuration, getMediaFileUrl } from "@/api/api-media";
import type { IntroCategory, JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import {
  buildMediaPreviewBoxStyle,
  formatVideoResolution,
  guessIntroPreviewAspectRatio,
  MEDIA_CROSS_ORIGIN,
  readImageNaturalSize,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";

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
const holdTailSec = ref(0.35);

function defaultIntroOrientation(job: JobDetail): "auto" | "portrait" | "landscape" {
  const saved = job.info?.orientation;
  if (saved === "auto" || saved === "portrait" || saved === "landscape") {
    return saved;
  }
  return job.pipeline === "material" ? "auto" : "portrait";
}

function defaultIntroCategory(job: JobDetail): IntroCategory {
  const saved = job.info?.intro_category;
  if (saved === "百科" || saved === "历史悬案") {
    return saved;
  }
  if (job.info?.content_style === "history_mystery") {
    return "历史悬案";
  }
  return "百科";
}

const introCategory = ref<IntroCategory>(defaultIntroCategory(props.job));
const savingIntroCategory = ref(false);
const introOrientation = ref<"auto" | "portrait" | "landscape">(
  defaultIntroOrientation(props.job)
);
const actualDuration = ref<number | null>(null);
const loadError = ref("");
const coverLoadError = ref("");
const videoRef = ref<HTMLVideoElement | null>(null);
const videoMeta = ref<{ width: number; height: number } | null>(null);
const coverMeta = ref<{ width: number; height: number } | null>(null);

const reloadVideoPreview = () => {
  void nextTick(() => {
    const video = videoRef.value;
    if (!video || !videoUrl.value) {
      return;
    }
    video.load();
  });
};

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const actualDurationText = computed(() => {
  if (actualDuration.value === null) {
    return props.job.intro_path ? "加载中…" : "-";
  }
  return `${actualDuration.value.toFixed(2)} 秒`;
});

const videoUrl = computed(() => getMediaFileUrl(props.job.intro_path ?? ""));

const coverUrl = computed(() => getMediaFileUrl(props.job.cover_path ?? ""));

const posterUrl = computed(() => {
  const videoPath = props.job.intro_path?.trim();
  if (!videoPath) {
    return "";
  }
  return getMediaFileUrl(videoPath.replace(/\.mp4$/i, ".png"));
});

const previewFallbackAspectRatio = computed(() =>
  guessIntroPreviewAspectRatio(introOrientation.value, props.job.pipeline)
);

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    videoMeta.value?.width,
    videoMeta.value?.height,
    previewFallbackAspectRatio.value
  )
);

const coverBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    coverMeta.value?.width ?? videoMeta.value?.width,
    coverMeta.value?.height ?? videoMeta.value?.height,
    previewFallbackAspectRatio.value
  )
);

const introResolutionText = computed(() =>
  formatVideoResolution(videoMeta.value?.width, videoMeta.value?.height)
);

const coverResolutionText = computed(() =>
  formatVideoResolution(
    coverMeta.value?.width ?? videoMeta.value?.width,
    coverMeta.value?.height ?? videoMeta.value?.height
  )
);

const loadDuration = async () => {
  if (!props.job.intro_path) {
    actualDuration.value = null;
    return;
  }
  actualDuration.value = await getMediaDuration(props.job.intro_path);
};

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认文件已生成且服务可访问";
};

const onCoverError = () => {
  coverLoadError.value = "封面加载失败，请确认文件已生成且服务可访问";
};

const onCoverLoad = (event: Event) => {
  const size = readImageNaturalSize(event);
  if (size) {
    coverMeta.value = size;
  }
};

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (video.videoWidth > 0 && video.videoHeight > 0) {
    videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
  }
};

const handleIntroCategoryChange = (value: IntroCategory) => {
  if (actionDisabled.value) {
    return;
  }
  savingIntroCategory.value = true;
  void updateJobInfo(props.job.id, { intro_category: value })
    .then(() => emit("refresh"))
    .catch(error => {
      introCategory.value = defaultIntroCategory(props.job);
      handleError(error, "更新片头风格失败");
    })
    .finally(() => {
      savingIntroCategory.value = false;
    });
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「片头/封面」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: {
      id: number;
      to_end: boolean;
      hold_tail_sec?: number;
      orientation: "auto" | "portrait" | "landscape";
      intro_category: IntroCategory;
    } = {
      id: props.job.id,
      to_end: toEnd,
      orientation: introOrientation.value,
      intro_category: introCategory.value,
    };
    if (Number.isFinite(holdTailSec.value) && holdTailSec.value >= 0) {
      payload.hold_tail_sec = holdTailSec.value;
    }
    await runJobStageAction("intro", payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.info?.intro_category,
  (category) => {
    if (category === "百科" || category === "历史悬案") {
      introCategory.value = category;
    }
  }
);

watch(
  () => props.job.info?.content_style,
  () => {
    if (!props.job.info?.intro_category) {
      introCategory.value = defaultIntroCategory(props.job);
    }
  }
);

watch(
  () => props.job.info?.orientation,
  (orientation) => {
    if (orientation === "auto" || orientation === "portrait" || orientation === "landscape") {
      introOrientation.value = orientation;
    }
  }
);

watch(
  () => props.job.cover_path,
  () => {
    coverLoadError.value = "";
    coverMeta.value = null;
  }
);

watch(
  () => props.job.intro_path,
  () => {
    loadError.value = "";
    videoMeta.value = null;
    void loadDuration();
  },
  { immediate: true }
);

watch(
  () => props.stageActive,
  active => {
    if (active) {
      reloadVideoPreview();
    }
  },
  { immediate: true }
);

watch(videoUrl, () => {
  if (props.stageActive !== false) {
    reloadVideoPreview();
  }
});
</script>

<style scoped>
.intro-orientation-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
}

.intro-orientation-group :deep(.el-radio) {
  margin-right: 0;
  height: 32px;
}
</style>
