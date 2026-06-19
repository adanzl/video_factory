<template>
  <el-descriptions :column="1" border>
    <el-descriptions-item :label="label">{{ path || "-" }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  path?: string | null;
}>();
</script>
