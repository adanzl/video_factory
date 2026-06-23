<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="1100px"
    destroy-on-close
    append-to-body
  >
    <ClipSearchPanel
      v-if="visible"
      :key="segmentIndex"
      :initial-keyword="defaultKeyword"
      :initial-orientation="defaultOrientation"
      keyword-input-class="w-64!"
      results-wrapper-class="max-h-[60vh] overflow-y-auto"
      empty-class="py-12 text-center text-sm text-gray-400"
      :show-meta="false"
    >
      <template #actions="{ clip }">
        <el-button
          type="primary"
          size="small"
          :loading="importingClipId === clip.id"
          :disabled="importingClipId !== null && importingClipId !== clip.id"
          @click="handleImport(clip)"
        >
          使用此片段
        </el-button>
      </template>
    </ClipSearchPanel>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { importClipToSegment } from "@/api/api-clips";
import ClipSearchPanel from "@/views/clips/ClipSearchPanel.vue";
import type { StockClip } from "@/types/clipSearch";
import type { ClipOrientation } from "@/utils/clipSearch";
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  modelValue: boolean;
  jobId: number;
  segmentIndex: number;
  defaultKeyword?: string;
  defaultOrientation?: ClipOrientation;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  imported: [];
}>();

const { handleError } = useErrorHandler();

const visible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value),
});

const dialogTitle = computed(() => `片段搜索 · #${props.segmentIndex}`);
const importingClipId = ref<string | null>(null);

const handleImport = async (clip: StockClip) => {
  importingClipId.value = clip.id;
  try {
    await importClipToSegment({
      jobId: props.jobId,
      segmentIndex: props.segmentIndex,
      videoUrl: clip.video_url,
    });
    ElMessage.success(`分段 #${props.segmentIndex} 已导入素材视频`);
    visible.value = false;
    emit("imported");
  } catch (error) {
    handleError(error, "导入片段失败");
  } finally {
    importingClipId.value = null;
  }
};
</script>
