<template>
  <el-dialog
    v-model="visible"
    :title="titleText"
    width="1100px"
    top="5vh"
    @closed="emit('closed')"
  >
    <div v-if="detail" class="flex gap-4" style="height: 75vh">
      <div class="flex h-full min-h-0 w-80 shrink-0 flex-col pr-2">
        <div class="min-h-0 flex-1 space-y-4 overflow-y-auto text-sm">
          <div>
            <div class="mb-1 text-xs text-gray-400">BV</div>
            <a
              v-if="detail.url"
              :href="detail.url"
              target="_blank"
              rel="noopener noreferrer"
              class="text-blue-600 hover:underline"
            >
              {{ detail.source_id }}
            </a>
            <span v-else>{{ detail.source_id }}</span>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">金故事标题</div>
            <div>{{ detail.title || "-" }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">机制 / 结构</div>
            <div>
              {{ detail.mechanism || "-" }} /
              {{ formatDailyStoryType(detail.structure_type) }}
            </div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">场景标题</div>
            <div class="font-bold">{{ story.scene_title || "-" }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">设定</div>
            <div class="text-gray-600">{{ story.setting || "-" }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">内容标签</div>
            <div>{{ story.key || "-" }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">冲突核</div>
            <div class="text-gray-600">{{ story.conflict_core || detail.conflict_core || "-" }}</div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">笑点解析</div>
            <div class="rounded-lg bg-gray-50 p-3 text-gray-600">
              {{ story.punchline_explain || "-" }}
            </div>
          </div>
          <div>
            <div class="mb-1 text-xs text-gray-400">gold_chat</div>
            <div class="text-gray-500">
              {{ detail.chat_lines ?? story.dialogue?.length ?? 0 }} 句 /
              {{ detail.chat_chars ?? calcChatChars(story.dialogue) }} 字
            </div>
            <div v-if="detail.exported_at" class="mt-1 text-xs text-gray-400">
              {{ formatDateTime(detail.exported_at) }}
            </div>
          </div>
        </div>
      </div>

      <div class="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-gray-100 bg-gray-50">
        <div class="border-b border-gray-100 px-4 py-2 text-sm text-gray-500">日常对白</div>
        <el-scrollbar class="min-h-0 flex-1">
          <div class="space-y-2 p-4">
            <div
              v-for="(line, idx) in story.dialogue || []"
              :key="idx"
              class="rounded-lg bg-white px-3 py-2 text-sm leading-relaxed shadow-sm"
            >
              <span
                class="mr-2 font-medium"
                :class="line.speaker === '昭昭' ? 'text-blue-600' : line.speaker === '灿灿' ? 'text-orange-600' : 'text-gray-600'"
              >
                {{ line.speaker }}
              </span>
              {{ line.line }}
            </div>
          </div>
        </el-scrollbar>
      </div>
    </div>
    <div v-else-if="loading" class="py-16 text-center text-gray-400">加载中…</div>
    <div v-else class="py-16 text-center text-gray-400">暂无数据</div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  calcChatChars,
  formatDailyStoryType,
  getGoldChat,
  type GoldChatExport,
} from "@/api/api-gold-chat";
import type { StoryContent } from "@/api/api-daily-story";
import { formatDateTime } from "@/utils/date";
import { useErrorHandler } from "@/composables/useErrorHandler";

const props = defineProps<{
  modelValue: boolean;
  goldStoryId?: number | null;
  sourceId?: string | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "closed"): void;
}>();

const { handleError } = useErrorHandler();
const loading = ref(false);
const detail = ref<GoldChatExport | null>(null);

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const story = computed<StoryContent>(() => detail.value?.daily_story || ({} as StoryContent));

const titleText = computed(() => {
  const t = story.value.scene_title || detail.value?.title;
  return t ? `gold_chat · ${t}` : "gold_chat 详情";
});

async function loadDetail() {
  if (!props.goldStoryId && !props.sourceId) {
    detail.value = null;
    return;
  }
  loading.value = true;
  try {
    detail.value = await getGoldChat({
      id: props.goldStoryId ?? undefined,
      sourceId: props.sourceId ?? undefined,
    });
  } catch (e) {
    detail.value = null;
    handleError(e, "加载 gold_chat 失败");
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.modelValue, props.goldStoryId, props.sourceId] as const,
  ([open]) => {
    if (open) void loadDetail();
  },
);
</script>
