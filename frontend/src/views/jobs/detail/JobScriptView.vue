<template>
  <div v-if="script" class="script-view">
    <el-descriptions :column="2" border class="mb-4">
      <el-descriptions-item label="脚本标题" :span="2">{{ script.title || "-" }}</el-descriptions-item>
      <el-descriptions-item label="字数">{{ script.word_count ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="分镜数">{{ script.segments?.length ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="画风定调" :span="2">{{ script.visual_style || "-" }}</el-descriptions-item>
    </el-descriptions>

    <div class="section">
      <div class="section-title">完整口播</div>
      <div v-if="script.narration" class="narration">{{ script.narration }}</div>
      <JobDetailEmptyHint v-else text="暂无口播文案" />
    </div>

    <div class="section">
      <div class="section-title">分镜列表</div>
      <el-table v-if="script.segments?.length" :data="script.segments" stripe class="w-full">
        <el-table-column prop="segment_index" label="#" width="60" />
        <el-table-column prop="text" label="口播文案" min-width="220">
          <template #default="{ row }">
            <div class="cell-text">{{ row.text }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="visual_brief" label="画面描述" min-width="200">
          <template #default="{ row }">
            <div class="cell-text">{{ row.visual_brief || "-" }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="visual_mode" label="模式" width="120" />
        <el-table-column prop="image_prompt" label="文生图提示词" min-width="240">
          <template #default="{ row }">
            <div class="cell-text muted">{{ row.image_prompt || "-" }}</div>
          </template>
        </el-table-column>
      </el-table>
      <JobDetailEmptyHint v-else text="暂无分镜" />
    </div>

    <el-collapse class="mt-4">
      <el-collapse-item title="原始 JSON" name="raw">
        <pre class="json-block">{{ rawJson }}</pre>
      </el-collapse-item>
    </el-collapse>
  </div>
  <JobDetailEmptyHint v-else text="暂无脚本数据" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ScriptJson } from "@/types/jobs";
import JobDetailEmptyHint from "./JobDetailEmptyHint.vue";

const props = defineProps<{
  value: unknown;
}>();

const script = computed<ScriptJson | null>(() => {
  if (!props.value || typeof props.value !== "object") {
    return null;
  }
  return props.value as ScriptJson;
});

const rawJson = computed(() => JSON.stringify(props.value, null, 2));
</script>

<style scoped>
.section {
  margin-bottom: 20px;
}

.section-title {
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.narration {
  padding: 12px 16px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.cell-text {
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.cell-text.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.json-block {
  margin: 0;
  padding: 12px;
  overflow: auto;
  max-height: 480px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
