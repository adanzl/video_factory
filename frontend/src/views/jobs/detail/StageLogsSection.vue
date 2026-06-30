<template>
  <div :class="STAGE_LOGS_SECTION_CLASS">
    <div :class="STAGE_SECTION_TITLE_CLASS">阶段日志</div>
    <el-table v-if="logs.length" :data="logs" stripe size="small" class="w-full">
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="level" label="级别" width="80" />
      <el-table-column prop="message" label="消息" min-width="240" show-overflow-tooltip />
    </el-table>
    <div v-else :class="STAGE_EMPTY_CLASS">暂无日志</div>
  </div>
</template>

<script setup lang="ts">
import type { JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import {
  STAGE_EMPTY_CLASS,
  STAGE_LOGS_SECTION_CLASS,
  STAGE_SECTION_TITLE_CLASS,
} from "./stageLayout";

defineProps<{
  logs: JobLog[];
}>();
</script>
