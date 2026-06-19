<template>
  <div class="stage-panel">
    <JobStageActionBar
      :stage="stage"
      :job="job"
      :segments="segments"
      @submitted="emit('refresh')"
    />

    <template v-if="stage === 'title'">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务 ID">{{ job.id }}</el-descriptions-item>
        <el-descriptions-item label="标题">{{ job.title }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTagType(job.status)" size="small">{{ job.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="重试次数">{{ job.retry_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(job.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDateTime(job.updated_at) }}</el-descriptions-item>
      </el-descriptions>
    </template>

    <template v-else-if="stage === 'script'">
      <JobScriptView :value="job.script_json" />
      <JsonBlock label="质量报告" :value="job.quality_report" class="mt-4" />
    </template>

    <template v-else-if="stage === 'intro'">
      <PathField label="片头路径" :path="job.intro_path" />
    </template>

    <template v-else-if="stage === 'cover'">
      <PathField label="封面路径" :path="job.cover_path" />
    </template>

    <template v-else-if="stage === 'tts'">
      <el-descriptions :column="1" border class="mb-4">
        <el-descriptions-item label="音频路径">{{ job.audio_path || "-" }}</el-descriptions-item>
        <el-descriptions-item label="字幕路径">{{ job.subtitle_path || "-" }}</el-descriptions-item>
      </el-descriptions>
      <JsonBlock label="TTS 用量" :value="job.tts_usage_json" />
    </template>

    <template v-else-if="stage === 'segment'">
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
      <EmptyHint v-else text="暂无分段数据" />
    </template>

    <template v-else-if="stage === 'host'">
      <EmptyHint text="讲解人叠图阶段；具体产出见下方日志" />
    </template>

    <template v-else-if="stage === 'merge'">
      <PathField label="成片路径" :path="job.final_path" />
      <el-alert
        v-if="job.fail_stage === 'merge' && job.error_message"
        type="error"
        :title="job.error_message"
        :closable="false"
        class="mt-4"
      />
    </template>

    <template v-else-if="stage === 'publish'">
      <el-descriptions :column="1" border class="mb-4">
        <el-descriptions-item label="跳过发布">{{ job.skip_publish ? "是" : "否" }}</el-descriptions-item>
        <el-descriptions-item label="成片路径">{{ job.final_path || "-" }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="job.skip_publish"
        type="info"
        title="该任务配置为跳过发布"
        :closable="false"
      />
    </template>

    <div class="mt-6">
      <div class="mb-2 text-sm font-medium text-gray-600">阶段日志</div>
      <el-table v-if="logs.length" :data="logs" stripe size="small" class="w-full">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80" />
        <el-table-column prop="message" label="消息" min-width="240" show-overflow-tooltip />
      </el-table>
      <EmptyHint v-else text="暂无日志" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { JobDetail, JobLog, JobSegment } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import EmptyHint from "./JobDetailEmptyHint.vue";
import JsonBlock from "./JobDetailJsonBlock.vue";
import PathField from "./JobDetailPathField.vue";
import JobScriptView from "./JobScriptView.vue";
import JobStageActionBar from "./JobStageActionBar.vue";

defineProps<{
  stage: string;
  job: JobDetail;
  segments: JobSegment[];
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const statusTagType = (status: string) => {
  switch (status) {
    case "done":
      return "success";
    case "running":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "info";
  }
};

const formatDuration = (value?: number | null) => {
  if (value === null || value === undefined) {
    return "-";
  }
  return value.toFixed(2);
};
</script>
