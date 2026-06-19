<template>
  <el-dialog v-model="visible" title="对话框占位" width="480px">
    <el-empty description="对话框内容待实现" />
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";

const visible = ref(false);

defineExpose({
  open: () => {
    visible.value = true;
  },
});
</script>
