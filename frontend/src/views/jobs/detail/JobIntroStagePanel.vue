<template>
  <div class="intro-stage">
    <div class="intro-stage__left">
      <div class="intro-stage__config rounded border border-gray-200 p-4">
        <div class="mb-3 text-sm font-medium text-gray-700">参数配置</div>
        <JobStageActionBar
          stage="intro"
          :job="job"
          :segments="segments"
          embedded
          @submitted="emit('submitted')"
        />
        <el-form label-width="96px" class="intro-stage__meta">
          <el-form-item label="成片时长">
            <span class="text-gray-700">{{ actualDurationText }}</span>
          </el-form-item>
          <el-form-item label="片头路径">
            <span class="break-all text-gray-600">{{ job.intro_path || "-" }}</span>
          </el-form-item>
        </el-form>
        <p class="intro-stage__hint text-xs text-gray-400">
          总时长 = 品牌喊声时长 + 尾部停留；调整尾部停留后需重新生成。
        </p>
      </div>
    </div>

    <div class="intro-stage__right">
      <div class="intro-stage__preview rounded border border-gray-200 p-4">
        <div class="mb-3 text-sm font-medium text-gray-700">视频预览</div>
        <JobDetailVideoPreview :path="job.intro_path" empty-text="暂无片头视频，请先生成" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getMediaDuration } from "@/api/api-media";
import type { JobDetail, JobSegment } from "@/types/jobs";
import JobDetailVideoPreview from "./JobDetailVideoPreview.vue";
import JobStageActionBar from "./JobStageActionBar.vue";

const props = defineProps<{
  job: JobDetail;
  segments: JobSegment[];
}>();

const emit = defineEmits<{
  submitted: [];
}>();

const actualDuration = ref<number | null>(null);

const actualDurationText = computed(() => {
  if (actualDuration.value === null) {
    return props.job.intro_path ? "加载中…" : "-";
  }
  return `${actualDuration.value.toFixed(2)} 秒`;
});

const loadDuration = async () => {
  if (!props.job.intro_path) {
    actualDuration.value = null;
    return;
  }
  actualDuration.value = await getMediaDuration(props.job.intro_path);
};

watch(
  () => props.job.intro_path,
  () => {
    void loadDuration();
  },
  { immediate: true }
);
</script>

<style scoped>
.intro-stage {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}

.intro-stage__left {
  flex: 0 0 320px;
  max-width: 100%;
  min-width: 280px;
}

.intro-stage__right {
  flex: 1 1 360px;
  min-width: 280px;
}

.intro-stage__meta :deep(.el-form-item) {
  margin-bottom: 8px;
}

.intro-stage__hint {
  margin: 8px 0 0;
  line-height: 1.5;
}
</style>
