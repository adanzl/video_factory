<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div class="py-8 text-center text-sm text-gray-400">讲解人叠图阶段；具体产出见下方日志</div>

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
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import StageActionBar from "./StageActionBar.vue";

defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const submitting = ref(false);

const actionDisabled = computed(() => true);
const actionDisabledReason = computed(() => "讲解人阶段暂无独立 API");

const handleRun = async () => {};
</script>
