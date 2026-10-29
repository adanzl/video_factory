<template>
  <div :class="STAGE_ACTION_BAR_CLASS">
    <el-button
      v-if="showPrimary"
      type="primary"
      :loading="loading"
      :disabled="disabled"
      size="small"
      @click="$emit('primary')"
    >
      {{ primaryLabel }}
    </el-button>
    <el-button
      v-if="showToEnd"
      type="success"
      :loading="loading"
      :disabled="disabled"
      size="small"
      @click="$emit('toEnd')"
    >
      {{ toEndLabel }}
    </el-button>
    <el-button
      v-if="showFill"
      type="warning"
      :loading="loading"
      :disabled="disabled"
      size="small"
      :title="fillTitle"
      @click="$emit('fill')"
    >
      {{ fillLabel }}
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
    fillLabel?: string;
    fillTitle?: string;
    showPrimary?: boolean;
    showToEnd?: boolean;
    showFill?: boolean;
  }>(),
  {
    loading: false,
    disabled: false,
    disabledReason: "",
    primaryLabel: "生成",
    toEndLabel: "从此成片",
    fillLabel: "补全成片",
    fillTitle: "保留已有数据，只补缺失，然后跑完流水线",
    showPrimary: true,
    showToEnd: true,
    showFill: true,
  }
);

defineEmits<{
  primary: [];
  toEnd: [];
  fill: [];
}>();
</script>
