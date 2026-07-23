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
            :disabled="actionDisabled || savingImageProvider"
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
            :disabled="actionDisabled || savingVideoProvider"
            @change="handleVideoProviderChange"
          >
            <el-radio-button value="ffmpeg">Ken Burns</el-radio-button>
            <el-radio-button value="wan_i2v" disabled>万相 I2V</el-radio-button>
            <el-radio-button value="agnes_i2v">Agnes I2V</el-radio-button>
          </el-radio-group>
        </el-descriptions-item>
        <el-descriptions-item label="分镜序号" :span="3">
          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-3">
              <el-checkbox :model-value="allSelected" @change="toggleSelectAll"> 全选 </el-checkbox>
              <span class="text-sm text-gray-500">共 {{ segments.length }} 分镜，留空表示全部</span>
            </div>
            <el-checkbox-group v-model="selectedSegments" class="flex flex-wrap gap-x-4 gap-y-1">
              <el-checkbox
                v-for="segment in segments"
                :key="segment.segment_index"
                :value="segment.segment_index"
                class="segment-check"
              >
                #{{ segment.segment_index }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div v-if="segments.length" class="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1">
      <span class="text-xs text-gray-400">快速定位：</span>
      <button
        v-for="segment in segments"
        :key="segment.segment_index"
        class="cursor-pointer rounded px-1.5 py-0.5 text-xs transition-colors hover:bg-blue-50 hover:text-blue-600"
        @click="scrollToSegment(segment.segment_index)"
      >
        #{{ segment.segment_index }}
      </button>
    </div>

    <div v-if="displaySegments.length" class="overflow-x-auto pb-2">
      <div class="flex w-max min-w-full gap-4">
        <article
          v-for="segment in displaySegments"
          :key="segment.segment_index"
          :ref="(el: any) => setSegmentRef(segment.segment_index, el)"
          class="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-medium text-gray-800">#{{ segment.segment_index }}</span>
            <div class="flex items-center gap-1">
              <el-button size="small" link type="primary" @click="openEditDialog(segment)">
                编辑
              </el-button>
              <el-tag size="small">{{ segment.status }}</el-tag>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span
              class="text-xs font-medium"
              :class="segmentKeyframeValue(segment) ? 'text-amber-600' : 'text-gray-600'"
            >
              关键帧
            </span>
            <el-select
              size="small"
              class="w-30!"
              :class="{ 'keyframe-select--active': !!segmentKeyframeValue(segment) }"
              :model-value="segmentKeyframeValue(segment)"
              :disabled="actionDisabled || savingKeyframeIndex === segment.segment_index"
              :loading="savingKeyframeIndex === segment.segment_index"
              @change="(value: string) => handleKeyframeChange(segment, value)"
            >
              <el-option label="取消" value="" />
              <el-option label="Ken Burns" value="ffmpeg" />
              <el-option label="I2V" value="agnes_i2v" />
            </el-select>
          </div>
          <div class="text-xs text-gray-400">
            {{ formatSegmentDurationLabel(segment) }}
          </div>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">文案</div>
            <el-tooltip
              placement="top"
              :show-after="500"
              :disabled="!formatSegmentCopyFull(segment)"
            >
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-sm">
                  {{ formatSegmentCopyFull(segment) }}
                </div>
              </template>
              <div
                v-if="segment.dialogue?.length"
                class="flex min-h-[5lh] cursor-default flex-col gap-0.5 text-sm leading-relaxed"
              >
                <template v-if="segment.dialogue.length > 4">
                  <div
                    v-for="(dl, di) in segment.dialogue.slice(0, 3)"
                    :key="di"
                    class="truncate rounded px-1.5 py-0.5"
                    :class="speakerStyle(dl.speaker).full"
                  >
                    <span class="font-bold">{{ dl.speaker }}：</span>{{ dl.text }}
                  </div>
                  <div class="truncate px-1.5 text-gray-400">…</div>
                </template>
                <template v-else>
                  <div
                    v-for="(dl, di) in segment.dialogue"
                    :key="di"
                    class="truncate rounded px-1.5 py-0.5"
                    :class="speakerStyle(dl.speaker).full"
                  >
                    <span class="font-bold">{{ dl.speaker }}：</span>{{ dl.text }}
                  </div>
                </template>
              </div>
              <div
                v-else
                class="line-clamp-4 min-h-[4lh] cursor-default text-sm leading-relaxed wrap-break-word"
              >
                {{ segment.text }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">画面描述</div>
              <el-button
                size="small"
                link
                type="primary"
                :loading="generatingVisualBriefIndex === segment.segment_index"
                :disabled="isSegmentVisualBriefActionDisabled(segment.segment_index)"
                @click="handleGenerateVisualBrief(segment.segment_index)"
              >
                生成
              </el-button>
            </div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.visual_brief">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-sm">
                  {{ segment.visual_brief }}
                </div>
              </template>
              <div
                class="line-clamp-3 min-h-[3lh] cursor-default text-sm leading-relaxed wrap-break-word"
              >
                {{ segment.visual_brief || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">文生图提示词</div>
              <div class="flex items-center gap-1">
                <el-popover
                  placement="bottom"
                  :width="520"
                  trigger="click"
                  @show="handleImagePromptPopoverShow(segment.segment_index)"
                >
                  <template #reference>
                    <el-button
                      size="small"
                      link
                      type="primary"
                      :disabled="!segment.image_prompt && !segment.visual_brief"
                    >
                      提示词
                    </el-button>
                  </template>
                  <div v-if="imagePromptLoading" class="py-4 text-center text-xs text-gray-400">
                    加载中…
                  </div>
                  <div v-else-if="imagePromptError" class="py-2 text-xs text-red-500">
                    {{ imagePromptError }}
                  </div>
                  <div v-else class="space-y-3">
                    <div>
                      <div class="mb-1 text-xs font-medium text-gray-600">System</div>
                      <div
                        class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs leading-relaxed wrap-break-word"
                      >
                        {{ imagePromptSystem || "暂无" }}
                      </div>
                    </div>
                    <div>
                      <div class="mb-1 text-xs font-medium text-gray-600">User</div>
                      <div
                        class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs leading-relaxed wrap-break-word"
                      >
                        {{ imagePromptUser || "暂无" }}
                      </div>
                    </div>
                  </div>
                </el-popover>
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
            </div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.image_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">
                  {{ segment.image_prompt }}
                </div>
              </template>
              <div
                class="line-clamp-2 min-h-[2lh] cursor-default text-xs leading-relaxed wrap-break-word text-gray-500"
              >
                {{ segment.image_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">运动提示词</div>
            </div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.motion_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">
                  {{ segment.motion_prompt }}
                </div>
              </template>
              <div
                class="line-clamp-2 min-h-[2lh] cursor-default text-xs leading-relaxed wrap-break-word text-gray-500"
              >
                {{ segment.motion_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <el-collapse>
              <el-collapse-item>
                <template #title>
                  <span class="text-xs font-medium text-gray-600">SD15 英文提示词</span>
                </template>
                <div
                  class="whitespace-pre-wrap wrap-break-word text-xs leading-relaxed text-gray-500"
                >
                  {{ segment.sd15_prompt_en || "-" }}
                </div>
              </el-collapse-item>
            </el-collapse>
          </section>

          <section class="flex flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1 text-xs font-medium text-gray-600">
                分镜图片
                <span v-if="segment.info?.image_gen_sec != null" class="font-normal text-gray-400">
                  {{ formatGenSec(segment.info.image_gen_sec) }}
                </span>
              </div>
              <div class="flex items-center gap-1">
                <el-button
                  size="small"
                  link
                  type="primary"
                  :loading="regeneratingImageIndex === segment.segment_index"
                  :disabled="isSegmentImageActionDisabled(segment.segment_index)"
                  @click="handleRegenerateImage(segment.segment_index)"
                >
                  生成
                </el-button>
              </div>
            </div>
            <el-image
              v-if="segment.image_path"
              :key="segment.imageUrl"
              :src="lazyMediaSrc(segment.imageUrl, stageActive)"
              fit="cover"
              class="w-full rounded border border-gray-100"
              :style="mediaPreviewStyle"
              :preview-src-list="
                stageActive !== false && segment.imageOriginUrl ? [segment.imageOriginUrl] : []
              "
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
              <div class="flex items-center gap-1 text-xs font-medium text-gray-600">
                视频片段
                <span v-if="segment.info?.clip_gen_sec != null" class="font-normal text-gray-400">
                  {{ formatGenSec(segment.info.clip_gen_sec) }}
                </span>
              </div>
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
              v-if="segment.clip_path"
              class="w-full overflow-hidden rounded border border-gray-200 bg-black"
            >
              <video
                :key="segment.clipUrl"
                class="block w-full bg-black"
                :style="mediaPreviewStyle"
                :src="lazyMediaSrc(segment.clipUrl, stageActive)"
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

    <el-dialog v-model="editDialogOpen" title="编辑分镜文案" width="560px" destroy-on-close>
      <div class="mb-2 text-sm text-gray-600">分镜 #{{ editSegmentIndex }}</div>
      <el-input
        v-model="editText"
        type="textarea"
        :rows="6"
        placeholder="输入口播文案"
        maxlength="500"
        show-word-limit
      />
      <template #footer>
        <el-button @click="editDialogOpen = false">取消</el-button>
        <el-button
          type="primary"
          :loading="editSaving"
          :disabled="!editText.trim()"
          @click="handleSaveSegmentText"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  generatePrompts,
  previewSegmentPrompts,
  runJobStageAction,
  updateJobInfo,
  updateSegmentInfo,
  updateSegmentText,
} from "@/api/api-jobs";
import { getMediaFileUrl, getMediaPicViewUrl } from "@/api/api-media";
import type { JobDetail, JobInfo, JobLog, JobSegment, ScriptJson } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { buildSegmentClipSearchKeyword, type ClipOrientation } from "@/utils/clipSearch";
import { lazyMediaSrc, MEDIA_CROSS_ORIGIN } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import SegmentClipSearchDialog from "@/views/clips/SegmentClipSearchDialog.vue";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import { STAGE_BLOCK_CLASS, STAGE_EMPTY_CLASS } from "./stageLayout";

const props = defineProps<{
  job: JobDetail;
  segments: JobSegment[];
  logs: JobLog[];
  stageActive?: boolean;
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

function speakerStyle(speaker: string): { bg: string; text: string; full: string } {
  if (speaker === "昭昭")
    return { bg: "bg-blue-50", text: "text-blue-600", full: "bg-blue-50 text-blue-800" };
  if (speaker === "妈妈")
    return {
      bg: "bg-emerald-50",
      text: "text-emerald-600",
      full: "bg-emerald-50 text-emerald-800",
    };
  return { bg: "bg-pink-50", text: "text-pink-600", full: "bg-pink-50 text-pink-800" };
}

function formatSegmentCopyFull(segment: JobSegment): string {
  if (segment.dialogue?.length) {
    return segment.dialogue.map(dl => `${dl.speaker}：${dl.text}`).join("\n");
  }
  return segment.text || "";
}

const submitting = ref(false);
const savingImageProvider = ref(false);
const savingVideoProvider = ref(false);
const regeneratingImageIndex = ref<number | null>(null);
const generatingImagePromptIndex = ref<number | null>(null);
const generatingVisualBriefIndex = ref<number | null>(null);
const generatingMotionPromptIndex = ref<number | null>(null);
const generatingClipIndex = ref<number | null>(null);
const savingKeyframeIndex = ref<number | null>(null);
const segmentScope = ref("segment/images");

type ImageProvider = NonNullable<RunStageActionPayload["image_provider"]>;
type VideoProvider = NonNullable<RunStageActionPayload["video_provider"]>;
type KeyframeProvider = "" | "ffmpeg" | "agnes_i2v";

const segmentKeyframeValue = (segment: JobSegment): KeyframeProvider => {
  const provider = segment.info?.video_provider;
  if (provider === "ffmpeg" || provider === "agnes_i2v") {
    return provider;
  }
  return "";
};

const handleKeyframeChange = async (segment: JobSegment, value: string) => {
  if (actionDisabled.value) {
    return;
  }
  const next = (value === "ffmpeg" || value === "agnes_i2v" ? value : "") as KeyframeProvider;
  savingKeyframeIndex.value = segment.segment_index;
  try {
    // 先落库 video_provider，再生成 motion，才会走 keyframe 规则
    await updateSegmentInfo(props.job.id, segment.segment_index, next || null);
    const motion = String(segment.motion_prompt || "").trim();
    const needsKeyframeMotion =
      next === "agnes_i2v" && (!motion || motion.includes("人物姿势保持不变"));
    if (needsKeyframeMotion) {
      await generatePrompts(props.job.id, {
        type: "motion",
        segments: [segment.segment_index],
      });
      ElMessage.info(`分镜 #${segment.segment_index} 已提交关键帧运动提示词生成`);
    }
    emit("refresh");
  } catch (error) {
    handleError(error, "更新关键帧失败");
  } finally {
    savingKeyframeIndex.value = null;
  }
};

const defaultImageProvider = (job: JobDetail): ImageProvider =>
  job.info?.image_provider ?? "agnes_t2i";

const defaultVideoProvider = (job: JobDetail): VideoProvider => {
  const provider = job.info?.video_provider ?? "agnes_i2v";
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

const allSelected = computed(
  () => props.segments.length > 0 && selectedSegments.value.length === props.segments.length
);

const toggleSelectAll = (checked: boolean) => {
  selectedSegments.value = checked ? props.segments.map(s => s.segment_index) : [];
};

const segmentRefs = new Map<number, HTMLElement>();

const setSegmentRef = (index: number, el: any) => {
  if (el) {
    segmentRefs.set(index, el);
  } else {
    segmentRefs.delete(index);
  }
};

const scrollToSegment = (index: number) => {
  const el = segmentRefs.get(index);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }
};
const clipSearchOpen = ref(false);
const clipSearchSegmentIndex = ref(1);
const clipSearchKeyword = ref("");
const clipSearchOrientation = ref<ClipOrientation>("");

const editDialogOpen = ref(false);
const editSegmentIndex = ref(1);
const editText = ref("");
const editSaving = ref(false);

const imagePromptLoading = ref(false);
const imagePromptError = ref("");
const imagePromptSystem = ref("");
const imagePromptUser = ref("");

const handleImagePromptPopoverShow = async (segmentIndex: number) => {
  imagePromptLoading.value = true;
  imagePromptError.value = "";
  imagePromptSystem.value = "";
  imagePromptUser.value = "";
  try {
    const result = await previewSegmentPrompts(props.job.id, segmentIndex, "image_prompts");
    imagePromptSystem.value = result.system;
    imagePromptUser.value = result.user;
  } catch (error) {
    imagePromptError.value = error instanceof Error ? error.message : "加载失败";
  } finally {
    imagePromptLoading.value = false;
  }
};

const openEditDialog = (segment: { segment_index: number; text: string }) => {
  editSegmentIndex.value = segment.segment_index;
  editText.value = segment.text || "";
  editDialogOpen.value = true;
};

const handleSaveSegmentText = async () => {
  const trimmed = editText.value.trim();
  if (!trimmed) {
    ElMessage.warning("文案不能为空");
    return;
  }
  editSaving.value = true;
  try {
    await updateSegmentText(props.job.id, editSegmentIndex.value, trimmed);
    ElMessage.success(`分镜 #${editSegmentIndex.value} 文案已更新`);
    editDialogOpen.value = false;
    emit("refresh");
  } catch (error) {
    handleError(error, "更新文案失败");
  } finally {
    editSaving.value = false;
  }
};

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const isSegmentImageActionDisabled = (segmentIndex: number) =>
  actionDisabled.value ||
  submitting.value ||
  generatingImagePromptIndex.value !== null ||
  generatingClipIndex.value !== null ||
  generatingVisualBriefIndex.value !== null ||
  (regeneratingImageIndex.value !== null && regeneratingImageIndex.value !== segmentIndex);

const isSegmentImagePromptActionDisabled = (segmentIndex: number) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
  generatingClipIndex.value !== null ||
  generatingMotionPromptIndex.value !== null ||
  generatingVisualBriefIndex.value !== null ||
  (generatingImagePromptIndex.value !== null && generatingImagePromptIndex.value !== segmentIndex);

const isSegmentVisualBriefActionDisabled = (segmentIndex: number) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
  generatingImagePromptIndex.value !== null ||
  generatingClipIndex.value !== null ||
  (generatingVisualBriefIndex.value !== null && generatingVisualBriefIndex.value !== segmentIndex);

const isSegmentClipActionDisabled = (segment: { segment_index: number; imageUrl: string }) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
  generatingImagePromptIndex.value !== null ||
  generatingMotionPromptIndex.value !== null ||
  generatingVisualBriefIndex.value !== null ||
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

const displaySegments = computed(() =>
  props.segments.map(segment => {
    const imagePath = segment.image_path?.trim() ?? "";
    const clipPath = segment.clip_path?.trim() ?? "";
    let originUrl = getMediaFileUrl(imagePath);
    if (originUrl) {
      // 用 /view/ 端点预览原图（无 max_age 缓存，确保每次加载最新）
      originUrl = originUrl.replace("/files/", "/view/");
    }
    let imageUrl = originUrl ? getMediaPicViewUrl(imagePath) : "";
    let clipUrl = "";
    if (clipPath) {
      clipUrl = getMediaFileUrl(clipPath);
    }
    // 使用 DB 版本号作为缓存破坏参数
    const ver = segment.version ?? 0;
    const appendVersion = (url: string) => url + (url.includes("?") ? "&" : "?") + `v=${ver}`;
    if (imageUrl) {
      imageUrl = appendVersion(imageUrl);
    }
    if (originUrl) {
      originUrl = appendVersion(originUrl);
    }
    if (clipUrl) {
      clipUrl = appendVersion(clipUrl);
    }
    return {
      ...segment,
      visual_brief: visualBriefByIndex.value.get(segment.segment_index) ?? null,
      imageUrl,
      imageOriginUrl: originUrl,
      clipUrl,
    };
  })
);

const formatSegmentDuration = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(2)}s`;
};

const formatGenSec = (value?: number | null) => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }
  if (value < 1) {
    return `${(value * 1000).toFixed(0)}ms`;
  }
  return `${value.toFixed(1)}s`;
};

const formatSegmentDurationLabel = (segment: JobSegment) => {
  const tts = segment.tts_duration_sec;
  const script =
    segment.script_duration_sec ?? scriptDurationByIndex.value.get(segment.segment_index) ?? null;
  if (tts != null && Number.isFinite(tts)) {
    if (script != null && Number.isFinite(script) && Math.abs(tts - script) >= 0.05) {
      return `TTS ${formatSegmentDuration(tts)} · 预估 ${formatSegmentDuration(script)}`;
    }
    return `TTS ${formatSegmentDuration(tts)}`;
  }
  if (script != null && Number.isFinite(script)) {
    return `预估 ${formatSegmentDuration(script)}`;
  }
  return formatSegmentDuration(segment.duration_sec);
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
    await generatePrompts(props.job.id, { type: "image_prompt", segments: [segmentIndex] });
    ElMessage.success(`已提交分镜 #${segmentIndex} 文生图提示词生成`);
    emit("refresh");
  } catch (error) {
    handleError(error, "文生图提示词生成失败");
  } finally {
    generatingImagePromptIndex.value = null;
  }
};

const handleGenerateVisualBrief = async (segmentIndex: number) => {
  try {
    await ElMessageBox.confirm(`确定重新生成分镜 #${segmentIndex} 的画面描述吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  generatingVisualBriefIndex.value = segmentIndex;
  try {
    await generatePrompts(props.job.id, { type: "visual_brief", segments: [segmentIndex] });
    ElMessage.success(`已提交分镜 #${segmentIndex} 画面描述生成`);
    emit("refresh");
  } catch (error) {
    handleError(error, "画面描述生成失败");
  } finally {
    generatingVisualBriefIndex.value = null;
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

<style scoped>
.segment-check :deep(.el-checkbox__label) {
  display: inline-block;
  min-width: 2.5em;
  text-align: right;
}

.keyframe-select--active :deep(.el-select__wrapper) {
  background-color: #fffbeb;
  box-shadow: 0 0 0 1px #f59e0b inset;
}

.keyframe-select--active :deep(.el-select__selected-item) {
  color: #d97706;
  font-weight: 600;
}
</style>
