<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    >
      <span v-if="actionDisabledReason" class="text-sm text-gray-400">
        {{ actionDisabledReason }}
        <template v-if="props.job.status === 'running'">，可在页面上方中止</template>
      </span>
    </StageActionBar>

    <div :class="STAGE_BLOCK_CLASS">
      <el-descriptions :column="3" border label-width="100px" class="w-full">
        <el-descriptions-item label="重跑模式">
          <el-radio-group v-model="segmentScope">
            <el-radio value="segment/all">全部</el-radio>
            <el-radio value="segment/images">分镜静图</el-radio>
            <el-radio value="segment/clips">图生视频</el-radio>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="静图">
          <el-radio-group
            v-model="imageProvider"
            size="small"
            :disabled="segmentScope === 'segment/clips' || actionDisabled || savingImageProvider"
            @change="handleImageProviderChange"
          >
            <el-radio-button value="z_image_t2i" disabled>Z-Image</el-radio-button>
            <el-radio-button value="wan_t2i" disabled>万相</el-radio-button>
            <el-radio-button value="sd15_t2i">本地 SD</el-radio-button>
            <el-radio-button value="agnes_t2i">Agnes</el-radio-button>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="视频">
          <el-radio-group
            v-model="videoProvider"
            size="small"
            :disabled="segmentScope === 'segment/images' || actionDisabled || savingVideoProvider"
            @change="handleVideoProviderChange"
          >
            <el-radio-button value="ffmpeg">Ken Burns</el-radio-button>
            <el-radio-button value="wan_i2v" disabled>万相 I2V</el-radio-button>
            <el-radio-button value="agnes_i2v">Agnes I2V</el-radio-button>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="分镜序号" :span="3">
          <div class="flex w-full flex-nowrap items-center gap-3">
            <el-select
              v-model="selectedSegments"
              multiple
              clearable
              collapse-tags
              collapse-tags-tooltip
              placeholder="留空表示全部"
              class="min-w-0 flex-1!"
            >
              <el-option
                v-for="segment in segments"
                :key="segment.segment_index"
                :label="`#${segment.segment_index} ${truncate(segment.text, 24)}`"
                :value="segment.segment_index"
              />
            </el-select>
            <span class="shrink-0 whitespace-nowrap text-sm text-gray-500">
              共 {{ segments.length }} 分镜
            </span>
          </div>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div v-if="displaySegments.length" class="overflow-x-auto pb-2">
      <div class="flex w-max min-w-full gap-4">
        <article
          v-for="segment in displaySegments"
          :key="segment.segment_index"
          class="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-medium text-gray-800">#{{ segment.segment_index }}</span>
            <el-tag size="small">{{ segment.status }}</el-tag>
          </div>
          <div class="text-xs text-gray-400">
            {{ segment.visual_mode }} · {{ formatSegmentDuration(segment.duration_sec) }}
          </div>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">文案</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.text">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-sm">{{ segment.text }}</div>
              </template>
              <div class="line-clamp-3 min-h-[3lh] cursor-default text-sm leading-relaxed wrap-break-word">
                {{ segment.text }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">画面描述</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.visual_brief">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-sm">{{ segment.visual_brief }}</div>
              </template>
              <div class="line-clamp-4 min-h-[4lh] cursor-default text-sm leading-relaxed wrap-break-word">
                {{ segment.visual_brief || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">文生图提示词</div>
              <el-button
                size="small"
                link
                type="primary"
                :loading="generatingImagePromptIndex === segment.segment_index"
                :disabled="isSegmentImagePromptActionDisabled(segment.segment_index)"
                @click="handleGenerateImagePrompt(segment.segment_index)"
              >
                生成
              </el-button>
            </div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.image_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">{{ segment.image_prompt }}</div>
              </template>
              <div class="line-clamp-2 min-h-[2lh] cursor-default text-xs leading-relaxed wrap-break-word text-gray-500">
                {{ segment.image_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">运动提示词</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.motion_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">{{ segment.motion_prompt }}</div>
              </template>
              <div class="line-clamp-3 min-h-[3lh] cursor-default text-xs leading-relaxed wrap-break-word text-gray-500">
                {{ segment.motion_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">SD15 英文提示词</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.sd15_prompt_en">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">{{ segment.sd15_prompt_en }}</div>
              </template>
              <div class="line-clamp-2 min-h-[2lh] cursor-default text-xs leading-relaxed wrap-break-word text-gray-500">
                {{ segment.sd15_prompt_en || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">分镜图片</div>
              <el-button
                size="small"
                link
                type="primary"
                :loading="regeneratingImageIndex === segment.segment_index"
                :disabled="isSegmentImageActionDisabled(segment.segment_index)"
                @click="handleRegenerateImage(segment.segment_index)"
              >
                重新生成
              </el-button>
            </div>
            <el-image
              v-if="segment.imageUrl"
              :src="segment.imageUrl"
              fit="cover"
              class="w-full rounded border border-gray-100"
              :style="mediaPreviewStyle"
              :preview-src-list="[segment.imageUrl]"
              preview-teleported
            />
            <div
              v-else
              class="flex w-full items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-xs text-gray-400"
              :style="mediaPreviewStyle"
            >
              暂无图片
            </div>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">视频片段</div>
              <div class="flex items-center gap-1">
                <el-button
                  size="small"
                  link
                  type="primary"
                  :loading="generatingClipIndex === segment.segment_index"
                  :disabled="isSegmentClipActionDisabled(segment)"
                  @click="handleGenerateClip(segment.segment_index)"
                >
                  生成
                </el-button>
                <el-button
                  size="small"
                  link
                  type="primary"
                  :disabled="actionDisabled || generatingClipIndex !== null"
                  @click="openClipSearch(segment)"
                >
                  片段搜索
                </el-button>
              </div>
            </div>
            <div
              v-if="segment.clipUrl"
              class="w-full overflow-hidden rounded border border-gray-200 bg-black"
            >
              <video
                :key="segment.clipUrl"
                class="block w-full bg-black"
                :style="mediaPreviewStyle"
                :src="segment.clipUrl"
                :crossorigin="MEDIA_CROSS_ORIGIN"
                controls
                playsinline
                preload="metadata"
              />
            </div>
            <div
              v-else
              class="flex w-full items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-xs text-gray-400"
              :style="mediaPreviewStyle"
            >
              暂无视频
            </div>
          </section>
        </article>
      </div>
    </div>
    <div v-else :class="STAGE_EMPTY_CLASS">暂无分镜数据</div>

    <SegmentClipSearchDialog
      v-model="clipSearchOpen"
      :job-id="job.id"
      :segment-index="clipSearchSegmentIndex"
      :default-keyword="clipSearchKeyword"
      :default-orientation="clipSearchOrientation"
      @imported="emit('refresh')"
    />

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { generateImagePrompts, runJobStageAction, updateJobInfo } from "@/api/api-jobs";
import { getMediaFileUrl } from "@/api/api-media";
import type { JobDetail, JobInfo, JobLog, JobSegment, ScriptJson } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { buildSegmentClipSearchKeyword, type ClipOrientation } from "@/utils/clipSearch";
import { MEDIA_CROSS_ORIGIN } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import SegmentClipSearchDialog from "@/views/clips/SegmentClipSearchDialog.vue";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import { STAGE_BLOCK_CLASS, STAGE_EMPTY_CLASS } from "./stageLayout";

const props = defineProps<{
  job: JobDetail;
  segments: JobSegment[];
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const savingImageProvider = ref(false);
const savingVideoProvider = ref(false);
const regeneratingImageIndex = ref<number | null>(null);
const generatingImagePromptIndex = ref<number | null>(null);
const generatingClipIndex = ref<number | null>(null);
const segmentScope = ref("segment/images");

type ImageProvider = NonNullable<RunStageActionPayload["image_provider"]>;
type VideoProvider = NonNullable<RunStageActionPayload["video_provider"]>;

const defaultImageProvider = (job: JobDetail): ImageProvider =>
  job.info?.image_provider ?? "z_image_t2i";

const defaultVideoProvider = (job: JobDetail): VideoProvider => {
  const provider = job.info?.video_provider ?? "ffmpeg";
  return provider === "wan_i2v" ? "ffmpeg" : provider;
};

const imageProvider = ref<ImageProvider>(defaultImageProvider(props.job));
const videoProvider = ref<VideoProvider>(defaultVideoProvider(props.job));

watch(
  () => props.job.info?.image_provider,
  value => {
    if (value) {
      imageProvider.value = value;
    }
  }
);

watch(
  () => props.job.info?.video_provider,
  value => {
    if (value) {
      videoProvider.value = value === "wan_i2v" ? "ffmpeg" : value;
    }
  }
);

const handleImageProviderChange = (value: ImageProvider) => {
  if (actionDisabled.value) {
    return;
  }
  savingImageProvider.value = true;
  void updateJobInfo(props.job.id, { image_provider: value })
    .then(() => emit("refresh"))
    .catch(error => {
      imageProvider.value = defaultImageProvider(props.job);
      handleError(error, "更新静图模式失败");
    })
    .finally(() => {
      savingImageProvider.value = false;
    });
};

const handleVideoProviderChange = (value: VideoProvider) => {
  if (actionDisabled.value) {
    return;
  }
  savingVideoProvider.value = true;
  void updateJobInfo(props.job.id, { video_provider: value })
    .then(() => emit("refresh"))
    .catch(error => {
      videoProvider.value = defaultVideoProvider(props.job);
      handleError(error, "更新视频模式失败");
    })
    .finally(() => {
      savingVideoProvider.value = false;
    });
};

const selectedSegments = ref<number[]>([]);
const clipSearchOpen = ref(false);
const clipSearchSegmentIndex = ref(1);
const clipSearchKeyword = ref("");
const clipSearchOrientation = ref<ClipOrientation>("");

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const isSegmentImageActionDisabled = (segmentIndex: number) =>
  actionDisabled.value ||
  submitting.value ||
  generatingImagePromptIndex.value !== null ||
  generatingClipIndex.value !== null ||
  (regeneratingImageIndex.value !== null && regeneratingImageIndex.value !== segmentIndex);

const isSegmentImagePromptActionDisabled = (segmentIndex: number) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
  generatingClipIndex.value !== null ||
  (generatingImagePromptIndex.value !== null &&
    generatingImagePromptIndex.value !== segmentIndex);

const isSegmentClipActionDisabled = (segment: { segment_index: number; imageUrl: string }) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
  generatingImagePromptIndex.value !== null ||
  !segment.imageUrl ||
  (generatingClipIndex.value !== null && generatingClipIndex.value !== segment.segment_index);

const mediaPreviewStyle = computed(() => ({
  aspectRatio: props.job.info?.orientation === "landscape" ? "16 / 9" : "9 / 16",
}));

const visualBriefByIndex = computed(() => {
  const script = props.job.script_json as ScriptJson | null;
  const map = new Map<number, string>();
  for (const seg of script?.segments ?? []) {
    if (seg.visual_brief) {
      map.set(seg.segment_index, seg.visual_brief);
    }
  }
  return map;
});

const scriptDurationByIndex = computed(() => {
  const script = props.job.script_json as ScriptJson | null;
  const map = new Map<number, number>();
  for (const seg of script?.segments ?? []) {
    const duration =
      seg.duration_sec ??
      (seg.start_sec != null && seg.end_sec != null ? seg.end_sec - seg.start_sec : undefined);
    if (duration != null && Number.isFinite(duration)) {
      map.set(seg.segment_index, duration);
    }
  }
  return map;
});

const toMediaUrl = getMediaFileUrl;

const displaySegments = computed(() =>
  props.segments.map(segment => {
    const imagePath = segment.image_path?.trim() ?? "";
    const clipPath = segment.clip_path?.trim() ?? "";
    const duration_sec =
      segment.duration_sec ?? scriptDurationByIndex.value.get(segment.segment_index) ?? null;
    return {
      ...segment,
      duration_sec,
      visual_brief: visualBriefByIndex.value.get(segment.segment_index) ?? null,
      imageUrl: toMediaUrl(imagePath),
      clipUrl: clipPath ? toMediaUrl(clipPath) : "",
    };
  })
);

const truncate = (text: string, max: number) => {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max)}…` : normalized;
};

const formatSegmentDuration = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(2)}s`;
};

const resolveClipSearchOrientation = (): ClipOrientation => {
  const orientation = (props.job.info as JobInfo | null | undefined)?.orientation;
  if (orientation === "portrait" || orientation === "landscape") {
    return orientation;
  }
  return "";
};

const openClipSearch = (segment: JobSegment & { visual_brief?: string | null }) => {
  clipSearchSegmentIndex.value = segment.segment_index;
  clipSearchKeyword.value = buildSegmentClipSearchKeyword(segment);
  clipSearchOrientation.value = resolveClipSearchOrientation();
  clipSearchOpen.value = true;
};

const handleGenerateImagePrompt = async (segmentIndex: number) => {
  try {
    await ElMessageBox.confirm(`确定重新生成分镜 #${segmentIndex} 的文生图提示词吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  generatingImagePromptIndex.value = segmentIndex;
  try {
    await generateImagePrompts(props.job.id, { segments: [segmentIndex] });
    ElMessage.success(`已提交分镜 #${segmentIndex} 文生图提示词生成`);
    emit("refresh");
  } catch (error) {
    handleError(error, "文生图提示词生成失败");
  } finally {
    generatingImagePromptIndex.value = null;
  }
};

const handleRegenerateImage = async (segmentIndex: number) => {
  try {
    await ElMessageBox.confirm(`确定重新生成分镜 #${segmentIndex} 的静图吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  regeneratingImageIndex.value = segmentIndex;
  try {
    await runJobStageAction("segment/images", {
      id: props.job.id,
      to_end: false,
      segments: [segmentIndex],
      image_provider: imageProvider.value,
    });
    ElMessage.success(`已提交分镜 #${segmentIndex} 静图重新生成`);
    emit("refresh");
  } catch (error) {
    handleError(error, "静图重新生成失败");
  } finally {
    regeneratingImageIndex.value = null;
  }
};

const handleGenerateClip = async (segmentIndex: number) => {
  try {
    await ElMessageBox.confirm(`确定对分镜 #${segmentIndex} 发起图生视频吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  generatingClipIndex.value = segmentIndex;
  try {
    await runJobStageAction("segment/clips", {
      id: props.job.id,
      to_end: false,
      segments: [segmentIndex],
      video_provider: videoProvider.value,
    });
    ElMessage.success(`已提交分镜 #${segmentIndex} 图生视频`);
    emit("refresh");
  } catch (error) {
    handleError(error, "图生视频失败");
  } finally {
    generatingClipIndex.value = null;
  }
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「分镜」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: RunStageActionPayload = {
      id: props.job.id,
      to_end: toEnd,
    };
    if (selectedSegments.value.length > 0) {
      payload.segments = selectedSegments.value.map(value => Number(value));
    }
    if (segmentScope.value !== "segment/clips") {
      payload.image_provider = imageProvider.value;
    }
    if (segmentScope.value !== "segment/images") {
      payload.video_provider = videoProvider.value;
    }
    await runJobStageAction(segmentScope.value, payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};
</script>
