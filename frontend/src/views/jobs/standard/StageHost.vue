<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun()"
      @to-end="handleRun()"
    />

    <div :class="STAGE_PANEL_CLASS">
      <div :class="STAGE_EMPTY_CLASS">讲解人叠图阶段；具体产出见下方日志</div>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { JobDetail, JobLog } from "@/types/jobs";
import StageActionBar from "../detail/StageActionBar.vue";
import StageLogsSection from "../detail/StageLogsSection.vue";
import { STAGE_EMPTY_CLASS, STAGE_PANEL_CLASS } from "../detail/stageLayout";

defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const submitting = ref(false);

const actionDisabled = computed(() => true);
const actionDisabledReason = computed(() => "讲解人阶段暂无独立 API");

const handleRun = async () => {};
</script>
