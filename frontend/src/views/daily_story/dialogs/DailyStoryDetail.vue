<template>
  <el-dialog v-model="visible" title="故事详情" width="1200px" top="5vh">
    <div v-if="localStory" class="flex gap-4" style="height: 80vh;">
      <!-- 左侧：信息 -->
      <div class="w-64 shrink-0 space-y-4 overflow-y-auto pr-2">
        <div>
          <div class="mb-1 text-xs text-gray-400">主题</div>
          <div class="text-sm">{{ localStory.theme }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">场景标题</div>
          <div class="font-bold">{{ localStory.story?.scene_title }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">设定</div>
          <div class="text-sm text-gray-600">{{ localStory.story?.setting }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">笑点解析</div>
          <div class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
            {{ localStory.story?.punchline_explain }}
          </div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">语速</div>
          <el-input-number
            v-model="speechRate"
            :min="1"
            :max="10"
            :step="0.1"
            :precision="1"
            size="small"
            class="!w-28"
          />
          <span class="ml-1 text-xs text-gray-400">字/秒</span>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">句间停留</div>
          <el-input-number
            v-model="lineGap"
            :min="0"
            :max="3"
            :step="0.1"
            :precision="1"
            size="small"
            class="!w-28"
          />
          <span class="ml-1 text-xs text-gray-400">秒</span>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">总字数</div>
          <div class="text-sm text-gray-600">{{ totalChars }} 字</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">时长估算</div>
          <div class="text-sm text-gray-600">{{ estimatedDuration }}</div>
        </div>
      </div>

      <!-- 右侧：对话 -->
      <div class="flex-1 space-y-3 overflow-y-auto pl-2" style="border-left: 1px solid #e5e7eb;">
        <div
          v-for="(line, idx) in localStory.story?.dialogue || []"
          :key="idx"
          class="rounded-lg p-3"
          :class="line.speaker === '昭昭' ? 'bg-blue-50' : 'bg-pink-50'"
        >
          <div
            :class="line.speaker === '昭昭' ? 'text-blue-600 font-bold' : 'text-pink-600 font-bold'"
            class="mb-1 text-xs"
          >
            {{ line.speaker }}
          </div>
          <div class="text-sm">{{ line.line }}</div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import type { DailyStoryRecord } from "@/api/api-daily-story";

const props = defineProps<{
  modelValue: boolean;
  story: DailyStoryRecord | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
});

const localStory = computed(() => props.story);

/** 默认口播语速（字/秒） */
const speechRate = ref(4.1);
/** 句间停留（秒） */
const lineGap = ref(0.3);

const totalChars = computed(() => {
  const dialogue = localStory.value?.story?.dialogue;
  if (!dialogue) return 0;
  return dialogue.reduce((sum, line) => sum + (line.line?.length || 0), 0);
});

const estimatedDuration = computed(() => {
  const chars = totalChars.value;
  const dialogue = localStory.value?.story?.dialogue;
  if (chars <= 0 || !dialogue || dialogue.length === 0) return "-";
  const speakSec = chars / speechRate.value;
  const gapSec = (dialogue.length - 1) * lineGap.value;
  const secs = Math.round(speakSec + gapSec);
  if (secs < 60) return `约 ${secs} 秒`;
  const mins = Math.floor(secs / 60);
  const remain = secs % 60;
  return remain > 0 ? `约 ${mins} 分 ${remain} 秒` : `约 ${mins} 分钟`;
});
</script>
