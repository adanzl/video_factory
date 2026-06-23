<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 p-4">
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
        class="[&_.el-form-item__content]:min-w-0 [&_.el-form-item__content]:flex-1"
      >
        <el-form-item label="重跑模式">
          <el-radio-group v-model="segmentScope">
            <el-radio value="segment/all">全部</el-radio>
            <el-radio value="segment/images">分镜静图</el-radio>
            <el-radio value="segment/clips">图生视频</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分段序号">
          <div class="flex w-full max-w-3xl flex-nowrap items-center gap-3">
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
            <span class="shrink-0 whitespace-nowrap text-sm text-gray-500">共 {{ segments.length }} 分镜</span>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <div v-if="displaySegments.length" class="overflow-x-auto pb-2">
      <div class="flex w-max min-w-full gap-4">
        <article
          v-for="segment in displaySegments"
          :key="segment.segment_index"
          class="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-gray-200 bg-white p-3"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-medium text-gray-800">#{{ segment.segment_index }}</span>
            <el-tag size="small">{{ segment.status }}</el-tag>
          </div>
          <div class="text-xs text-gray-400">
            {{ segment.visual_mode }} · {{ formatDuration(segment.duration_sec) }}s
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
            <div class="text-xs font-medium text-gray-600">文生图提示词</div>
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
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-medium text-gray-600">分段图片</div>
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
    <div v-else class="py-8 text-center text-sm text-gray-400">暂无分段数据</div>

    <SegmentClipSearchDialog
      v-model="clipSearchOpen"
      :job-id="job.id"
      :segment-index="clipSearchSegmentIndex"
      :default-keyword="clipSearchKeyword"
      :default-orientation="clipSearchOrientation"
      @imported="emit('refresh')"
    />

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
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { getMediaFileUrl } from "@/api/api-media";
import type { JobDetail, JobInfo, JobLog, JobSegment, ScriptJson } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import { buildSegmentClipSearchKeyword, type ClipOrientation } from "@/utils/clipSearch";
import { useErrorHandler } from "@/composables/useErrorHandler";
import SegmentClipSearchDialog from "@/views/clips/SegmentClipSearchDialog.vue";

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
const regeneratingImageIndex = ref<number | null>(null);
const generatingClipIndex = ref<number | null>(null);
const segmentScope = ref("segment/images");
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
  generatingClipIndex.value !== null ||
  (regeneratingImageIndex.value !== null && regeneratingImageIndex.value !== segmentIndex);

const isSegmentClipActionDisabled = (segment: { segment_index: number; imageUrl: string }) =>
  actionDisabled.value ||
  submitting.value ||
  regeneratingImageIndex.value !== null ||
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

const toMediaUrl = getMediaFileUrl;

const displaySegments = computed(() =>
  props.segments.map(segment => {
    const imagePath = segment.image_path?.trim() ?? "";
    const clipPath = segment.clip_path?.trim() ?? "";
    return {
      ...segment,
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

const formatDuration = (value?: number | null) => {
  if (value === null || value === undefined) {
    return "-";
  }
  return value.toFixed(2);
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
    await ElMessageBox.confirm(`确定对「分段」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: { id: number; to_end: boolean; segments?: number[] } = {
      id: props.job.id,
      to_end: toEnd,
    };
    if (selectedSegments.value.length > 0) {
      payload.segments = selectedSegments.value.map(value => Number(value));
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
