<template>
  <div>

    <div class="space-y-4">
      <!-- 标题 -->
      <section :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_HEADER_CLASS">
          <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">标题</div>
          <span class="flex-1" />
          <el-button
            v-if="publishTitle"
            size="small"
            @click="openUploadPage"
          >
            B站上传
          </el-button>
          <el-button
            v-if="publishTitle"
            size="small"
            type="primary"
            plain
            :icon="DocumentCopy"
            @click="copyPublishTitle"
          >
          </el-button>
        </div>
        <div
          v-if="publishTitle"
          class="rounded bg-gray-50 px-4 py-3 text-base leading-relaxed wrap-break-word"
        >
          {{ publishTitle }}
        </div>
        <div v-else :class="STAGE_EMPTY_CLASS">暂无标题</div>
      </section>

      <!-- 视频介绍 -->
      <section :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_HEADER_CLASS">
          <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">视频介绍</div>
          <div class="flex flex-wrap items-center gap-2">
            <el-button
              v-if="canRegenerateDescription"
              type="primary"
              plain
              size="small"
              :loading="regeneratingDescription"
              :disabled="actionDisabled"
              @click="handleRegenerateDescription"
            >
              生成
            </el-button>
            <el-button
              v-if="videoDescription"
              size="small"
              type="primary"
              :icon="DocumentCopy"
              plain
              @click="copyVideoDescription"
            >
            </el-button>

          </div>
        </div>
        <div
          v-if="videoDescription"
          class="rounded bg-gray-50 px-4 py-3 leading-relaxed wrap-break-word whitespace-pre-wrap"
        >
          {{ videoDescription }}
        </div>
        <div v-else :class="STAGE_EMPTY_CLASS">
          暂无视频介绍
          <span v-if="canRegenerateDescription">，可点击「重新生成」</span>
        </div>
      </section>

      <!-- 封面 / 成片 -->
      <div :class="STAGE_TWO_COL_CLASS">
        <div class="min-w-70 max-w-full shrink-0 basis-130">
          <section :class="STAGE_PANEL_CLASS">
            <div :class="STAGE_PANEL_HEADER_CLASS">
              <div class="flex items-center gap-2">
                <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">封面</div>
                <el-button
                  v-if="coverUrl"
                  size="small"
                  :type="showCover43Guide ? 'primary' : 'default'"
                  @click="showCover43Guide = !showCover43Guide"
                >
                  4:3
                </el-button>
              </div>
              <el-button
                v-if="coverPath"
                size="small"
                :loading="downloadingCover"
                @click="handleDownloadCover"
              >
                下载
              </el-button>
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
                  class="block h-full w-full [&_.el-image__inner]:block [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
                  @load="onCoverLoad"
                  @error="coverLoadError = true"
                />
                <div v-if="showCover43Guide" class="pointer-events-none absolute inset-0 z-10">
                  <template v-if="cover43Guide.mode === 'horizontal'">
                    <div
                      class="absolute inset-x-0 border-t-2 border-amber-400/90"
                      :style="{ top: `${cover43Guide.startPct}%` }"
                    />
                    <div
                      class="absolute inset-x-0 border-t-2 border-amber-400/90"
                      :style="{ top: `${cover43Guide.startPct + cover43Guide.spanPct}%` }"
                    />
                  </template>
                  <template v-else>
                    <div
                      class="absolute inset-y-0 border-l-2 border-amber-400/90"
                      :style="{ left: `${cover43Guide.startPct}%` }"
                    />
                    <div
                      class="absolute inset-y-0 border-l-2 border-amber-400/90"
                      :style="{ left: `${cover43Guide.startPct + cover43Guide.spanPct}%` }"
                    />
                  </template>
                </div>
              </div>
            </div>
            <div v-else :class="STAGE_EMPTY_CLASS">暂无封面，请先在「封面」阶段生成</div>
            <el-alert
              v-if="coverLoadError && coverPath"
              type="warning"
              title="封面加载失败"
              :closable="false"
              class="mt-2"
            />
          </section>
        </div>

        <div :class="STAGE_COL_RIGHT_CLASS">
          <section :class="STAGE_PANEL_CLASS">
            <div :class="STAGE_PANEL_HEADER_CLASS">
              <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">成片</div>
              <el-button
                v-if="finalFilePath"
                size="small"
                :loading="downloadingFinal"
                @click="handleDownloadFinal"
              >
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
                  @error="finalLoadError = true"
                  @loadedmetadata="onVideoMetadata"
                />
              </div>
            </div>
            <div v-else :class="STAGE_EMPTY_CLASS">暂无成片，请先在「合成」阶段生成</div>
            <el-alert
              v-if="finalLoadError && finalFilePath"
              type="warning"
              title="成片加载失败"
              :closable="false"
              class="mt-2"
            />
          </section>
        </div>
      </div>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { DocumentCopy } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { generateVideoDescription } from "@/api/api-jobs";
import { downloadMediaFile, getMediaFileUrl, getMediaPicViewUrl } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import type { ScriptJson } from "@/types/jobs/script";
import {
  buildMediaPreviewBoxStyle,
  computeCentered43GuideLines,
  lazyMediaSrc,
  readImageNaturalSize,
  resolveFinalPath,
  MEDIA_CROSS_ORIGIN,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText } from "@/utils/utils";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_COL_RIGHT_CLASS,
  STAGE_EMPTY_CLASS,
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

const regeneratingDescription = ref(false);
const downloadingCover = ref(false);
const downloadingFinal = ref(false);
const coverLoadError = ref(false);
const finalLoadError = ref(false);
const coverMeta = ref<{ width: number; height: number } | null>(null);
const videoMeta = ref<{ width: number; height: number } | null>(null);
const showCover43Guide = ref(false);

const COVER_PREVIEW_OPTIONS = {
  maxWidthPx: 560,
  maxViewportRatio: 0.9,
} as const;

const PUBLISH_PREVIEW_OPTIONS = {
  maxWidthPx: 560,
  maxViewportRatio: 0.85,
} as const;

const actionDisabled = computed(() => props.job.status === "running");

const script = computed(() => {
  const value = props.job.script_json;
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as ScriptJson;
});

const publishTitle = computed(() => {
  const fromScript = script.value?.title?.trim();
  if (fromScript) {
    return fromScript;
  }
  return props.job.title?.trim() || "";
});

const videoDescription = computed(() => script.value?.video_description?.trim() || "");

const canRegenerateDescription = computed(() => Boolean(script.value?.narration?.trim()));

const coverPath = computed(() => props.job.cover_path?.trim() || "");
const coverUrl = computed(() => getMediaPicViewUrl(coverPath.value, 640));

const finalFilePath = computed(() => resolveFinalPath(props.job.final_path));
const videoUrl = computed(() => getMediaFileUrl(finalFilePath.value));
const lazyCoverUrl = computed(() => lazyMediaSrc(coverUrl.value, props.stageActive));
const lazyCoverPreviewList = computed(() => (lazyCoverUrl.value ? [lazyCoverUrl.value] : []));
const lazyVideoUrl = computed(() => lazyMediaSrc(videoUrl.value, props.stageActive));

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    videoMeta.value?.width,
    videoMeta.value?.height,
    "16 / 9",
    PUBLISH_PREVIEW_OPTIONS
  )
);

const coverBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    coverMeta.value?.width ?? videoMeta.value?.width,
    coverMeta.value?.height ?? videoMeta.value?.height,
    "9 / 16",
    COVER_PREVIEW_OPTIONS
  )
);

const cover43Guide = computed(() =>
  computeCentered43GuideLines(
    coverMeta.value?.width ?? videoMeta.value?.width,
    coverMeta.value?.height ?? videoMeta.value?.height
  )
);

const coverDownloadName = computed(() => {
  const fromPath = coverPath.value.split("/").pop();
  return fromPath || `job-${props.job.id}-cover.jpg`;
});

const finalDownloadName = computed(() => {
  const fromPath = finalFilePath.value.split("/").pop();
  return fromPath || `job-${props.job.id}-final.mp4`;
});

const onCoverLoad = (event: Event) => {
  const size = readImageNaturalSize(event);
  if (size) {
    coverMeta.value = size;
  }
  coverLoadError.value = false;
};

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
  finalLoadError.value = false;
};

const copyPublishTitle = async () => {
  if (!publishTitle.value) {
    return;
  }
  try {
    await copyText(publishTitle.value);
    ElMessage.success("已复制标题");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const openUploadPage = () => {
  window.open("https://member.bilibili.com/platform/upload/video/frame", "_blank");
};

const copyVideoDescription = async () => {
  if (!videoDescription.value) {
    return;
  }
  try {
    await copyText(videoDescription.value);
    ElMessage.success("已复制视频介绍");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const handleRegenerateDescription = async () => {
  regeneratingDescription.value = true;
  try {
    await generateVideoDescription(props.job.id);
    ElMessage.success("视频介绍已重新生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "重新生成视频介绍失败");
  } finally {
    regeneratingDescription.value = false;
  }
};

const handleDownloadCover = async () => {
  if (!coverPath.value) {
    return;
  }
  downloadingCover.value = true;
  try {
    await downloadMediaFile(coverPath.value, coverDownloadName.value);
    ElMessage.success("已开始下载封面");
  } catch (error) {
    handleError(error, "下载封面失败");
  } finally {
    downloadingCover.value = false;
  }
};

const handleDownloadFinal = async () => {
  if (!finalFilePath.value) {
    return;
  }
  downloadingFinal.value = true;
  try {
    await downloadMediaFile(finalFilePath.value, finalDownloadName.value);
    ElMessage.success("已开始下载成片");
  } catch (error) {
    handleError(error, "下载成片失败");
  } finally {
    downloadingFinal.value = false;
  }
};

watch(coverPath, () => {
  coverLoadError.value = false;
  coverMeta.value = null;
  showCover43Guide.value = false;
});

watch(finalFilePath, () => {
  finalLoadError.value = false;
  videoMeta.value = null;
});
</script>
