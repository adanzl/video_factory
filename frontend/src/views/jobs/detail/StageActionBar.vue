<template>
  <div :class="STAGE_ACTION_BAR_CLASS">
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
import { STAGE_ACTION_BAR_CLASS } from "./stageLayout";

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
    primaryLabel: "生成",
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
