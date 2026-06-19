<template>
  <el-card shadow="never" class="w-96">
    <template #header>登录（占位）</template>
    <el-empty description="登录功能待实现" />
  </el-card>
</template>

<script setup lang="ts">
defineEmits<{
  loginSuccess: [userInfo: { id: number; name: string }];
}>();
</script>
