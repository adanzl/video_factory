<template>
  <div class="stage-action-bar mb-4 rounded border border-gray-200 p-4">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="actionDisabled"
        @click="handleRun(false)"
      >
        重新生成
      </el-button>
      <el-button
        type="success"
        :loading="submitting"
        :disabled="actionDisabled"
        @click="handleRun(true)"
      >
        从此成片
      </el-button>
      <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
    </div>

    <el-form v-if="config.params.length" label-width="96px" class="stage-action-form">
      <el-form-item v-for="param in config.params" :key="param.key" :label="param.label">
        <el-input
          v-if="param.type === 'text'"
          v-model="paramValues[param.key]"
          :placeholder="param.placeholder"
          clearable
          class="max-w-xl!"
        />
        <el-switch v-else-if="param.type === 'boolean'" v-model="paramValues[param.key]" />
        <el-select
          v-else-if="param.type === 'select'"
          v-model="paramValues[param.key]"
          class="w-48!"
        >
          <el-option
            v-for="option in param.options"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-select
          v-else-if="param.type === 'segment-indices'"
          v-model="paramValues[param.key]"
          multiple
          clearable
          collapse-tags
          collapse-tags-tooltip
          :placeholder="param.placeholder || '留空表示全部'"
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
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction, updateJob } from "@/api/api-jobs";
import { getStageActionConfig, resolveStageEndpoint } from "@/constants/jobStageActions";
import { JOB_STAGES } from "@/constants/jobStages";
import type { JobDetail, JobSegment, StageParamValues } from "@/types/jobs";
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  stage: string;
  job: JobDetail;
  segments: JobSegment[];
}>();

const emit = defineEmits<{
  submitted: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);

const config = computed(() => getStageActionConfig(props.stage));

const paramValues = reactive<StageParamValues>({});

const actionDisabled = computed(() => {
  if (props.job.status === "running") {
    return true;
  }
  return Boolean(config.value.unsupported);
});

const actionDisabledReason = computed(() => {
  if (props.job.status === "running") {
    return "任务运行中，请稍后再试";
  }
  if (config.value.unsupported) {
    return config.value.unsupportedReason;
  }
  return "";
});

const truncate = (text: string, max: number) => {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max)}…` : normalized;
};

const resetParamValues = () => {
  Object.keys(paramValues).forEach(key => {
    delete paramValues[key];
  });

  for (const param of config.value.params) {
    if (param.type === "boolean") {
      if (param.key === "skip_publish") {
        paramValues[param.key] = props.job.skip_publish ?? false;
      } else {
        paramValues[param.key] = Boolean(param.defaultValue);
      }
      continue;
    }
    if (param.type === "segment-indices") {
      paramValues[param.key] = [];
      continue;
    }
    if (param.key === "title") {
      paramValues[param.key] = props.job.title;
      continue;
    }
    paramValues[param.key] = String(param.defaultValue ?? "");
  }
};

const buildSegments = (): number[] | undefined => {
  const raw = paramValues.segments;
  if (!Array.isArray(raw) || raw.length === 0) {
    return undefined;
  }
  return raw.map(value => Number(value));
};

const applySideEffects = async () => {
  if (props.stage === "title") {
    const title = String(paramValues.title ?? "").trim();
    if (title && title !== props.job.title) {
      await updateJob(props.job.id, { title });
      ElMessage.success("标题已更新");
    }
    return;
  }

  if (props.stage === "publish") {
    const skipPublish = Boolean(paramValues.skip_publish);
    if (skipPublish !== props.job.skip_publish) {
      await updateJob(props.job.id, { skip_publish: skipPublish });
    }
  }
};

const handleRun = async (toEnd: boolean) => {
  const endpoint = resolveStageEndpoint(props.stage, paramValues);
  if (!endpoint) {
    await applySideEffects();
    if (props.stage === "title") {
      ElMessage.info("标题阶段无可执行的重跑动作");
    }
    return;
  }

  const actionLabel = toEnd ? "从此成片" : "重新生成";
  const stageLabel = JOB_STAGES.find(item => item.name === props.stage)?.label ?? props.stage;

  try {
    await ElMessageBox.confirm(
      `确定对「${stageLabel}」阶段执行「${actionLabel}」吗？`,
      "确认执行",
      {
        type: "warning",
        confirmButtonText: "执行",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  submitting.value = true;
  try {
    await applySideEffects();

    const payload: { id: number; to_end: boolean; segments?: number[] } = {
      id: props.job.id,
      to_end: toEnd,
    };
    const segments = buildSegments();
    if (segments) {
      payload.segments = segments;
    }

    await runJobStageAction(endpoint, payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("submitted");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => [props.stage, props.job.id, props.job.title, props.job.skip_publish] as const,
  () => {
    resetParamValues();
  },
  { immediate: true }
);
</script>

<style scoped>
.stage-action-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
