<template>
  <div class="mb-4 flex flex-wrap items-center gap-2 border-b border-gray-200 pb-4">
    <el-button
      v-if="showPrimary"
      type="primary"
      :loading="loading"
      :disabled="disabled"
      @click="$emit('primary')"
    >
      {{ primaryLabel }}
    </el-button>
    <el-button
      v-if="showToEnd"
      type="success"
      :loading="loading"
      :disabled="disabled"
      @click="$emit('toEnd')"
    >
      {{ toEndLabel }}
    </el-button>
    <slot name="extra" />
    <span v-if="disabledReason" class="text-sm text-gray-400">{{ disabledReason }}</span>
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    loading?: boolean;
    disabled?: boolean;
    disabledReason?: string;
    primaryLabel?: string;
    toEndLabel?: string;
    showPrimary?: boolean;
    showToEnd?: boolean;
  }>(),
  {
    loading: false,
    disabled: false,
    disabledReason: "",
    primaryLabel: "重新生成",
    toEndLabel: "从此成片",
    showPrimary: true,
    showToEnd: true,
  }
);

defineEmits<{
  primary: [];
  toEnd: [];
}>();
</script>
