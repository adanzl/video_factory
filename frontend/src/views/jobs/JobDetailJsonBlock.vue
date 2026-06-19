<template>
  <div>
    <div class="mb-2 text-sm font-medium text-gray-600">{{ label }}</div>
    <pre v-if="content" class="json-block">{{ content }}</pre>
    <JobDetailEmptyHint v-else text="暂无数据" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import JobDetailEmptyHint from "./JobDetailEmptyHint.vue";

const props = defineProps<{
  label: string;
  value: unknown;
}>();

const content = computed(() => {
  if (props.value === null || props.value === undefined) {
    return "";
  }
  if (typeof props.value === "string") {
    return props.value;
  }
  return JSON.stringify(props.value, null, 2);
});
</script>

<style scoped>
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
