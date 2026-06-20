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
        <el-form-item label="重跑范围">
          <el-select v-model="segmentScope" class="w-48!">
            <el-option label="分镜静图" value="segment/images" />
            <el-option label="图生视频" value="segment/clips" />
          </el-select>
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

    <el-table v-if="segments.length" :data="segments" stripe class="w-full">
      <el-table-column prop="segment_index" label="#" width="60" />
      <el-table-column prop="text" label="文案" min-width="200" show-overflow-tooltip />
      <el-table-column prop="visual_mode" label="模式" width="120" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时长(s)" width="90">
        <template #default="{ row }">{{ formatDuration(row.duration_sec) }}</template>
      </el-table-column>
      <el-table-column prop="image_path" label="图片" min-width="160" show-overflow-tooltip />
      <el-table-column prop="clip_path" label="片段" min-width="160" show-overflow-tooltip />
    </el-table>
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
import type { JobDetail, JobLog, JobSegment } from "@/types/jobs";
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
