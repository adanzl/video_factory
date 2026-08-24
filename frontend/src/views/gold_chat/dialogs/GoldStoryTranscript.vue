<template>
  <el-dialog
    v-model="visible"
    :title="titleText"
    width="900px"
    top="6vh"
    @closed="onClosed"
  >
    <div v-if="loading" class="py-16 text-center text-gray-400">加载中…</div>
    <div v-else-if="data" class="flex flex-col" style="height: 72vh">
      <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
        <span v-if="data.transcript_backend">引擎：{{ data.transcript_backend }}</span>
        <span v-if="data.transcript_chars">{{ data.transcript_chars }} 字</span>
        <span v-if="data.transcript_path" class="truncate" :title="data.transcript_path">
          ASR：{{ data.transcript_path }}
        </span>
        <span
          v-if="data.transcript_repaired_path"
          class="truncate"
          :title="data.transcript_repaired_path"
        >
          修复稿：{{ data.transcript_repaired_path }}
        </span>
      </div>

      <div
        v-if="data.transcript_repair_notes"
        class="mb-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600"
      >
        修复说明：{{ data.transcript_repair_notes }}
      </div>

      <template v-if="data.has_transcript">
        <el-tabs v-if="data.has_repaired" v-model="activeTab" class="min-h-0 flex-1 flex flex-col">
          <el-tab-pane label="修复稿" name="main" class="min-h-0 flex-1">
            <el-scrollbar class="h-full rounded-lg border border-gray-100 bg-gray-50">
              <pre class="whitespace-pre-wrap p-4 text-sm leading-relaxed text-gray-800 font-sans">{{
                data.transcript_repaired || data.transcript
              }}</pre>
            </el-scrollbar>
          </el-tab-pane>
          <el-tab-pane
            :label="`ASR 原文（${data.transcript_raw_chars} 字）`"
            name="raw"
            class="min-h-0 flex-1"
          >
            <el-scrollbar class="h-full rounded-lg border border-gray-100 bg-gray-50">
              <pre class="whitespace-pre-wrap p-4 text-sm leading-relaxed text-gray-800 font-sans">{{
                data.transcript_raw
              }}</pre>
            </el-scrollbar>
          </el-tab-pane>
        </el-tabs>
        <el-scrollbar
          v-else
          class="min-h-0 flex-1 rounded-lg border border-gray-100 bg-gray-50"
        >
          <pre class="whitespace-pre-wrap p-4 text-sm leading-relaxed text-gray-800 font-sans">{{
            data.transcript_raw || data.transcript
          }}</pre>
        </el-scrollbar>
      </template>

      <div
        v-else
        class="flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-gray-200 p-12 text-center text-gray-400"
      >
        <div>暂无逐字稿文件</div>
        <div class="max-w-md text-xs leading-relaxed">
          需先跑 H0b ASR：
          <code class="text-gray-500">scripts.gold_story_transcript one {{ data.source_id }}</code>
        </div>
      </div>
    </div>
    <div v-else class="py-16 text-center text-gray-400">暂无数据</div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  getGoldStoryTranscript,
  type GoldStoryTranscript,
} from "@/api/api-gold-chat";
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  modelValue: boolean;
  goldStoryId?: number | null;
  sourceId?: string | null;
  title?: string | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "closed"): void;
}>();

const { handleError } = useErrorHandler();
const loading = ref(false);
const data = ref<GoldStoryTranscript | null>(null);
const activeTab = ref("main");

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const titleText = computed(() => {
  const t = props.title || data.value?.title || data.value?.source_id;
  return t ? `逐字稿 · ${t}` : "逐字稿";
});

async function loadTranscript() {
  if (!props.goldStoryId && !props.sourceId) {
    data.value = null;
    return;
  }
  loading.value = true;
  try {
    data.value = await getGoldStoryTranscript({
      id: props.goldStoryId ?? undefined,
      sourceId: props.sourceId ?? undefined,
    });
    activeTab.value = "main";
  } catch (e) {
    data.value = null;
    handleError(e, "加载逐字稿失败");
  } finally {
    loading.value = false;
  }
}

function onClosed() {
  data.value = null;
  emit("closed");
}

watch(
  () => [props.modelValue, props.goldStoryId, props.sourceId] as const,
  ([open]) => {
    if (open) void loadTranscript();
  },
);
</script>

<style scoped>
:deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.el-tab-pane) {
  height: 100%;
}
</style>
