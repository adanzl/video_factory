<template>
  <div class="py-8 text-center text-sm text-gray-400">{{ text }}</div>
</template>

<script setup lang="ts">
defineProps<{
  text: string;
}>();
</script>
