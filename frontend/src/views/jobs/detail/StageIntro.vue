<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div :class="STAGE_BLOCK_COMPACT_CLASS">
      <el-descriptions :column="3" border label-width="96px" class="w-full">
        <el-descriptions-item label="片头风格">
          <el-radio-group
            v-model="introCategory"
            :class="STAGE_RADIO_INLINE_CLASS"
            :disabled="savingIntroCategory || actionDisabled"
            @change="handleIntroCategoryChange"
          >
            <el-radio value="百科">童趣百科</el-radio>
            <el-radio value="历史悬案">历史悬案</el-radio>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="画面方向">
          <el-radio-group v-model="introOrientation" :class="STAGE_RADIO_INLINE_CLASS">
            <el-radio value="auto">自动</el-radio>
            <el-radio value="portrait">竖屏 9:16</el-radio>
            <el-radio value="landscape">横屏 16:9</el-radio>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="尾部停留">
          <el-input-number
            v-model="holdTailSec"
            :min="0"
            :max="5"
            :step="0.05"
            placeholder="秒"
            controls-position="right"
            size="small"
            class="w-32!"
          />
          <span class="ml-1 text-xs text-gray-500">秒</span>
        </el-descriptions-item>
        <el-descriptions-item label="成片时长">
          <span class="text-sm text-gray-700">{{ actualDurationText }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="片头路径" :span="2">
          <span class="break-all text-sm text-gray-600">{{ job.intro_path || "-" }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="封面路径" :span="3">
          <span class="break-all text-sm text-gray-600">{{ job.cover_path || "-" }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <p class="mt-1.5 text-xs leading-snug text-gray-400">
        总时长 = 品牌喊声时长 + 尾部停留；封面由片头预览帧自动生成。「自动」时素材任务跟随基底视频分辨率。
      </p>
    </div>

    <div :class="STAGE_TWO_COL_CLASS">
      <div :class="STAGE_COL_WIDE_LEFT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_HEADER_CLASS">
            <span :class="STAGE_PANEL_TITLE_TEXT_CLASS">封面预览</span>
            <div class="flex items-center gap-2">
              <el-button
                v-if="coverUrl"
                size="small"
                :type="showCover43Guide ? 'primary' : 'default'"
                @click="showCover43Guide = !showCover43Guide"
              >
                4:3
              </el-button>
              <el-button
                v-if="!coverUrl"
                size="small"
                type="primary"
                :loading="regeneratingCover"
                :disabled="actionDisabled"
                @click="handleRegenCover"
              >
                生成
              </el-button>
              <el-button
                v-if="coverUrl"
                size="small"
                :loading="regeneratingCover"
                @click="handleRegenCover"
              >
                重新生成
              </el-button>
              <span class="text-xs text-gray-400">{{ coverResolutionText }}</span>
            </div>
          </div>
          <div v-if="coverUrl" class="flex justify-center">
            <div
              class="relative flex items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50"
              :style="coverBoxStyle"
            >
              <el-image
                :key="coverUrl"
                :src="lazyCoverUrl"
                :preview-src-list="lazyCoverPreviewList"
                :crossorigin="MEDIA_CROSS_ORIGIN"
                fit="contain"
                class="block size-full [&_.el-image__inner]:block [&_.el-image__inner]:size-full [&_.el-image__inner]:object-contain"
                @load="onCoverLoad"
                @error="onCoverError"
              />
              <div v-if="showCover43Guide" class="pointer-events-none absolute inset-0 z-10">
                <div
                  v-for="(line, index) in cover43GuideLines"
                  :key="index"
                  :class="line.class"
                  :style="line.style"
                />
              </div>
            </div>
          </div>
          <div v-else-if="!job.cover_path" :class="STAGE_EMPTY_CLASS">
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

      <div :class="STAGE_COL_RIGHT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_HEADER_CLASS">
            <span :class="STAGE_PANEL_TITLE_TEXT_CLASS">片头预览</span>
            <span class="text-xs text-gray-400">{{ introResolutionText }}</span>
          </div>
          <div v-if="videoUrl" class="flex justify-center">
            <div
              class="relative overflow-hidden rounded-lg border border-gray-200 bg-black"
              :style="previewBoxStyle"
            >
              <video
                :key="videoUrl"
                class="absolute inset-0 size-full bg-black object-contain"
                :src="lazyVideoUrl"
                :poster="lazyPosterUrl || undefined"
                :crossorigin="MEDIA_CROSS_ORIGIN"
                controls
                playsinline
                preload="metadata"
                @error="onVideoError"
                @loadedmetadata="onVideoMetadata"
              />
            </div>
          </div>
          <div v-else-if="!job.intro_path" :class="STAGE_EMPTY_CLASS">
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
      </div>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction, updateJobInfo } from "@/api/api-jobs";
import { getMediaDuration, getMediaFileUrl } from "@/api/api-media";
import type { IntroCategory, JobDetail, JobLog } from "@/types/jobs";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_BLOCK_COMPACT_CLASS,
  STAGE_COL_RIGHT_CLASS,
  STAGE_COL_WIDE_LEFT_CLASS,
  STAGE_EMPTY_CLASS,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_HEADER_CLASS,
  STAGE_PANEL_TITLE_TEXT_CLASS,
  STAGE_RADIO_INLINE_CLASS,
  STAGE_TWO_COL_CLASS,
} from "./stageLayout";
import {
  buildCover43GuideLineStyles,
  buildMediaPreviewBoxStyle,
  computeCentered43GuideLines,
  formatVideoResolution,
  guessIntroPreviewAspectRatio,
  lazyMediaSrc,
  MEDIA_CROSS_ORIGIN,
  parseAspectRatio,
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
const introCategory = ref<IntroCategory>(defaultIntroCategory(props.job));
const savingIntroCategory = ref(false);
const introOrientation = ref<"auto" | "portrait" | "landscape">(
  defaultIntroOrientation(props.job)
);
const actualDuration = ref<number | null>(null);
const loadError = ref("");
const coverLoadError = ref("");
const videoMeta = ref<{ width: number; height: number } | null>(null);
const coverMeta = ref<{ width: number; height: number } | null>(null);
const showCover43Guide = ref(false);
const regeneratingCover = ref(false);
const coverCacheVer = ref(0);
const introCacheVer = ref(0);

const PREVIEW_OPTIONS = { maxWidthPx: 560, maxViewportRatio: 0.85 } as const;
const COVER_PREVIEW_OPTIONS = { maxWidthPx: 560, maxViewportRatio: 0.9 } as const;

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

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const previewFallbackAspectRatio = computed(() =>
  guessIntroPreviewAspectRatio(introOrientation.value, props.job.pipeline)
);

const coverDimensions = computed(() => ({
  width: coverMeta.value?.width ?? videoMeta.value?.width,
  height: coverMeta.value?.height ?? videoMeta.value?.height,
}));

const videoUrl = computed(() => {
  const base = getMediaFileUrl(props.job.intro_path ?? "");
  return base ? `${base}?v=${introCacheVer.value}` : "";
});
const coverUrl = computed(() => {
  const base = getMediaFileUrl(props.job.cover_path ?? "");
  return base ? `${base}?v=${coverCacheVer.value}` : "";
});

const posterUrl = computed(() => {
  const videoPath = props.job.intro_path?.trim();
  const base = videoPath ? getMediaFileUrl(videoPath.replace(/\.mp4$/i, ".png")) : "";
  return base ? `${base}?v=${introCacheVer.value}` : "";
});

const lazyVideoUrl = computed(() => lazyMediaSrc(videoUrl.value, props.stageActive));
const lazyCoverUrl = computed(() => lazyMediaSrc(coverUrl.value, props.stageActive));
const lazyPosterUrl = computed(() => lazyMediaSrc(posterUrl.value, props.stageActive));
const lazyCoverPreviewList = computed(() => (lazyCoverUrl.value ? [lazyCoverUrl.value] : []));

const actualDurationText = computed(() => {
  if (actualDuration.value !== null) {
    return `${actualDuration.value.toFixed(2)} 秒`;
  }
  return props.job.intro_path ? "加载中…" : "-";
});

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    videoMeta.value?.width,
    videoMeta.value?.height,
    previewFallbackAspectRatio.value,
    PREVIEW_OPTIONS
  )
);

const coverBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    coverDimensions.value.width,
    coverDimensions.value.height,
    previewFallbackAspectRatio.value,
    COVER_PREVIEW_OPTIONS
  )
);

const cover43GuideLines = computed(() =>
  buildCover43GuideLineStyles(
    computeCentered43GuideLines(
      coverDimensions.value.width,
      coverDimensions.value.height,
      parseAspectRatio(previewFallbackAspectRatio.value)
    )
  )
);

const introResolutionText = computed(() =>
  formatVideoResolution(videoMeta.value?.width, videoMeta.value?.height)
);

const coverResolutionText = computed(() =>
  formatVideoResolution(coverDimensions.value.width, coverDimensions.value.height)
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
    loadError.value = "";
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
    introCacheVer.value++;
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

const handleRegenCover = async () => {
  try {
    await ElMessageBox.confirm("确定重新生成封面吗？", "确认", {
      type: "warning",
      confirmButtonText: "确定",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  regeneratingCover.value = true;
  try {
    await runJobStageAction("cover", { id: props.job.id, to_end: false });
    coverCacheVer.value++;
    ElMessage.success("封面已重新生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "重新生成封面失败");
  } finally {
    regeneratingCover.value = false;
  }
};

watch(
  () => [props.job.info?.intro_category, props.job.info?.content_style] as const,
  ([category]) => {
    if (category === "百科" || category === "历史悬案") {
      introCategory.value = category;
    } else if (!props.job.info?.intro_category) {
      introCategory.value = defaultIntroCategory(props.job);
    }
  }
);

watch(
  () => props.job.info?.orientation,
  orientation => {
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
    showCover43Guide.value = false;
  }
);

watch(
  () => [props.job.intro_path, props.stageActive] as const,
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
