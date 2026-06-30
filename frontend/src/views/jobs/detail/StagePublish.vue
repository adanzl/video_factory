<template>
  <div>
    <el-alert
      type="info"
      title="请手动投稿：复制标题与视频介绍，下载封面与成片后上传到平台。"
      :closable="false"
      class="mb-4"
    />

    <div class="space-y-4">
      <!-- 标题 -->
      <section :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_HEADER_CLASS">
          <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">标题</div>
          <el-button
            v-if="publishTitle"
            size="small"
            type="primary"
            :icon="DocumentCopy"
            @click="copyPublishTitle"
          >
            复制
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
              v-if="videoDescription"
              size="small"
              type="primary"
              :icon="DocumentCopy"
              @click="copyVideoDescription"
            >
              复制
            </el-button>
            <el-button
              v-if="canRegenerateDescription"
              size="small"
              :loading="regeneratingDescription"
              :disabled="actionDisabled"
              @click="handleRegenerateDescription"
            >
              重新生成
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

      <!-- 封面 -->
      <section :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_HEADER_CLASS">
          <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">封面</div>
          <el-button
            v-if="coverPath"
            size="small"
            :loading="downloadingCover"
            @click="handleDownloadCover"
          >
            下载
          </el-button>
        </div>
        <div
          v-if="coverUrl"
          class="mx-auto flex h-[280px] max-w-md items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50"
        >
          <el-image
            :key="coverUrl"
            :src="coverUrl"
            :preview-src-list="[coverUrl]"
            :crossorigin="MEDIA_CROSS_ORIGIN"
            fit="contain"
            class="block h-full w-full [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
            @error="coverLoadError = true"
          />
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

      <!-- 成片 -->
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
              :src="videoUrl"
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

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { DocumentCopy } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { generateVideoDescription } from "@/api/api-jobs";
import { downloadMediaFile, getMediaFileUrl } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import type { ScriptJson } from "@/types/jobs/script";
import { resolveFinalPath, MEDIA_CROSS_ORIGIN } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText } from "@/utils/utils";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_EMPTY_CLASS,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_HEADER_CLASS,
  STAGE_PANEL_TITLE_TEXT_CLASS,
} from "./stageLayout";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
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
const videoMeta = ref<{ width: number; height: number } | null>(null);

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
const coverUrl = computed(() => getMediaFileUrl(coverPath.value));

const finalFilePath = computed(() => resolveFinalPath(props.job.final_path));
const videoUrl = computed(() => getMediaFileUrl(finalFilePath.value));

const previewBoxStyle = computed(() => {
  const meta = videoMeta.value;
  if (meta?.width && meta?.height) {
    const maxW = 480;
    const maxH = 360;
    const scale = Math.min(maxW / meta.width, maxH / meta.height, 1);
    return {
      width: `${Math.round(meta.width * scale)}px`,
      height: `${Math.round(meta.height * scale)}px`,
    };
  }
  return { width: "480px", height: "270px" };
});

const coverDownloadName = computed(() => {
  const fromPath = coverPath.value.split("/").pop();
  return fromPath || `job-${props.job.id}-cover.jpg`;
});

const finalDownloadName = computed(() => {
  const fromPath = finalFilePath.value.split("/").pop();
  return fromPath || `job-${props.job.id}-final.mp4`;
});

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
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
});

watch(finalFilePath, () => {
  finalLoadError.value = false;
  videoMeta.value = null;
});
</script>
