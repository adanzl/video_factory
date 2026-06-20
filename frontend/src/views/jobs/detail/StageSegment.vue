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
      <el-form label-width="96px">
        <el-form-item label="重跑模式">
          <el-radio-group v-model="segmentScope">
            <el-radio value="segment/all">全部</el-radio>
            <el-radio value="segment/images">分镜静图</el-radio>
            <el-radio value="segment/clips">图生视频</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分段序号">
          <el-select
            v-model="selectedSegments"
            multiple
            clearable
            collapse-tags
            collapse-tags-tooltip
            placeholder="留空表示全部"
            class="max-w-xl!"
          >
            <el-option
              v-for="segment in segments"
              :key="segment.segment_index"
              :label="`#${segment.segment_index} ${truncate(segment.text, 24)}`"
              :value="segment.segment_index"
            />
          </el-select>
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
                <div class="max-w-sm whitespace-pre-wrap break-words text-sm">{{ segment.text }}</div>
              </template>
              <div class="line-clamp-3 min-h-[3lh] cursor-default text-sm leading-relaxed break-words">
                {{ segment.text }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">画面描述</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.visual_brief">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap break-words text-sm">{{ segment.visual_brief }}</div>
              </template>
              <div class="line-clamp-4 min-h-[4lh] cursor-default text-sm leading-relaxed break-words">
                {{ segment.visual_brief || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">文生图提示词</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.image_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap break-words text-xs">{{ segment.image_prompt }}</div>
              </template>
              <div class="line-clamp-2 min-h-[2lh] cursor-default text-xs leading-relaxed break-words text-gray-500">
                {{ segment.image_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">运动提示词</div>
            <el-tooltip placement="top" :show-after="300" :disabled="!segment.motion_prompt">
              <template #content>
                <div class="max-w-sm whitespace-pre-wrap break-words text-xs">{{ segment.motion_prompt }}</div>
              </template>
              <div class="line-clamp-3 min-h-[3lh] cursor-default text-xs leading-relaxed break-words text-gray-500">
                {{ segment.motion_prompt || "-" }}
              </div>
            </el-tooltip>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">分段图片</div>
            <el-image
              v-if="segment.imageUrl"
              :src="segment.imageUrl"
              fit="cover"
              class="aspect-[9/16] w-full rounded border border-gray-100"
              :preview-src-list="[segment.imageUrl]"
              preview-teleported
            />
            <div
              v-else
              class="flex aspect-[9/16] w-full items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-xs text-gray-400"
            >
              暂无图片
            </div>
          </section>

          <section class="flex flex-col gap-1">
            <div class="text-xs font-medium text-gray-600">视频预览</div>
            <div
              v-if="segment.clipUrl"
              class="w-full overflow-hidden rounded border border-gray-200 bg-black"
            >
              <video
                :key="segment.clipUrl"
                class="block aspect-[9/16] w-full bg-black"
                :src="segment.clipUrl"
                controls
                playsinline
                preload="metadata"
              />
            </div>
            <div
              v-else
              class="flex aspect-[9/16] w-full items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-xs text-gray-400"
            >
              暂无视频
            </div>
          </section>
        </article>
      </div>
    </div>
    <div v-else class="py-8 text-center text-sm text-gray-400">暂无分段数据</div>

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
import type { JobDetail, JobLog, JobSegment, ScriptJson } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import { useErrorHandler } from "@/composables/useErrorHandler";

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
const segmentScope = ref("segment/images");
const selectedSegments = ref<number[]>([]);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

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

const resolveSegmentClipPath = (segment: JobSegment): string => {
  const clipPath = segment.clip_path?.trim();
  if (clipPath) {
    return clipPath;
  }
  const imagePath = segment.image_path?.trim();
  if (!imagePath) {
    return "";
  }
  return imagePath.replace(/\/images\/(\d+)\.png$/i, "/segments/$1.mp4");
};

const toMediaUrl = getMediaFileUrl;

const displaySegments = computed(() =>
  props.segments.map(segment => {
    const imagePath = segment.image_path?.trim() ?? "";
    const clipPath = resolveSegmentClipPath(segment);
    return {
      ...segment,
      visual_brief: visualBriefByIndex.value.get(segment.segment_index) ?? null,
      imageUrl: toMediaUrl(imagePath),
      clipUrl: toMediaUrl(clipPath),
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
