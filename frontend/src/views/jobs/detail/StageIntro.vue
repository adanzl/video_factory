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
            <el-form label-width="96px">
              <el-form-item label="尾部停留 (秒)">
                <el-input-number
                  v-model="holdTailSec"
                  :min="0"
                  :max="5"
                  :step="0.05"
                  placeholder="秒"
                  controls-position="right"
                  class="w-40!"
                />
              </el-form-item>
            </el-form>
          </div>
          <el-form label-width="96px" class="[&_.el-form-item]:mb-2">
            <el-form-item label="成片时长">
              <span class="text-gray-700">{{ actualDurationText }}</span>
            </el-form-item>
            <el-form-item label="片头路径">
              <span class="break-all text-gray-600">{{ job.intro_path || "-" }}</span>
            </el-form-item>
          </el-form>
          <p class="mt-2 text-xs leading-normal text-gray-400">
            总时长 = 品牌喊声时长 + 尾部停留；调整尾部停留后需重新生成。
          </p>
        </div>
      </div>

      <div class="min-w-[280px] flex-1 basis-[360px]">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">视频预览</div>
          <div v-if="videoUrl" class="flex justify-center">
            <div
              class="overflow-hidden rounded-lg border border-gray-200 bg-black"
              :style="previewBoxStyle"
            >
              <video
                :key="videoUrl"
                class="block h-full w-full bg-black object-contain"
                :src="videoUrl"
                :poster="posterUrl || undefined"
                controls
                playsinline
                preload="metadata"
                @error="onVideoError"
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
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const PREVIEW_MAX_VIEWPORT_RATIO = 0.7;
const PREVIEW_MAX_WIDTH_PX = 420;

const submitting = ref(false);
const holdTailSec = ref(0.35);
const actualDuration = ref<number | null>(null);
const loadError = ref("");
const videoMeta = ref<{ width: number; height: number } | null>(null);

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

const posterUrl = computed(() => {
  const videoPath = props.job.intro_path?.trim();
  if (!videoPath) {
    return "";
  }
  return getMediaFileUrl(videoPath.replace(/\.mp4$/i, ".png"));
});

const buildPreviewBoxStyle = (width?: number | null, height?: number | null) => {
  if (width && height && width > 0 && height > 0) {
    const ratio = width / height;
    const maxH =
      (typeof window !== "undefined" ? window.innerHeight : 800) * PREVIEW_MAX_VIEWPORT_RATIO;
    const maxW = Math.min(
      PREVIEW_MAX_WIDTH_PX,
      typeof window !== "undefined" ? window.innerWidth * 0.9 : PREVIEW_MAX_WIDTH_PX
    );
    let boxW = maxW;
    let boxH = boxW / ratio;
    if (boxH > maxH) {
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
    aspectRatio: "9 / 16",
  };
};

const previewBoxStyle = computed(() =>
  buildPreviewBoxStyle(videoMeta.value?.width, videoMeta.value?.height)
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

const onVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (video.videoWidth > 0 && video.videoHeight > 0) {
    videoMeta.value = { width: video.videoWidth, height: video.videoHeight };
  }
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「片头」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: { id: number; to_end: boolean; hold_tail_sec?: number } = {
      id: props.job.id,
      to_end: toEnd,
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
  () => props.job.intro_path,
  () => {
    loadError.value = "";
    videoMeta.value = null;
    void loadDuration();
  },
  { immediate: true }
);
</script>
