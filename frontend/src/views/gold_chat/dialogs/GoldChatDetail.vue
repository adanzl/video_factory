<template>
  <el-dialog
    v-model="visible"
    :title="titleText"
    width="1200px"
    top="4vh"
    @closed="emit('closed')"
  >
    <div v-if="detail" class="flex gap-4" style="height: 76vh">
      <!-- 左侧：金故事 dump -->
      <div class="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-gray-200 bg-white">
        <div class="border-b border-gray-100 px-4 py-2 text-sm font-medium text-gray-700">
          金故事 dump
        </div>
        <el-scrollbar class="min-h-0 flex-1">
          <div class="space-y-4 p-4 text-sm">
            <div class="grid grid-cols-2 gap-3 text-xs">
              <div>
                <div class="mb-1 text-gray-400">BV</div>
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
                <div class="mb-1 text-gray-400">机制 / 结构</div>
                <div>
                  {{ detail.mechanism || "-" }} /
                  {{ formatDailyStoryType(detail.structure_type) }}
                </div>
              </div>
            </div>

            <div>
              <div class="mb-1 text-xs text-gray-400">金故事标题</div>
              <div class="font-medium">{{ detail.title || "-" }}</div>
              <div
                v-if="detail.bili_title && detail.bili_title !== detail.title"
                class="mt-1 text-xs text-gray-400"
              >
                B站原标题：{{ detail.bili_title }}
              </div>
            </div>

            <div>
              <div class="mb-1 text-xs text-gray-400">冲突核</div>
              <div class="text-gray-600">{{ detail.conflict_core || "-" }}</div>
            </div>

            <div v-if="dump.setting">
              <div class="mb-1 text-xs text-gray-400">设定</div>
              <div class="text-gray-600">{{ dump.setting }}</div>
            </div>

            <div v-if="dump.beat?.length">
              <div class="mb-1 text-xs text-gray-400">beat</div>
              <div class="flex flex-wrap gap-1">
                <el-tag
                  v-for="(b, i) in dump.beat"
                  :key="i"
                  size="small"
                  type="info"
                >
                  {{ i + 1 }}. {{ b }}
                </el-tag>
              </div>
            </div>

            <div v-if="dump.dialogue_seed?.length">
              <div class="mb-1 text-xs text-gray-400">dialogue_seed</div>
              <div class="space-y-1 rounded-lg bg-gray-50 p-3">
                <div
                  v-for="(seed, idx) in dump.dialogue_seed"
                  :key="idx"
                  class="text-gray-600"
                >
                  <span class="font-medium text-gray-700">{{ seed.speaker || "?" }}</span>
                  <span class="mx-1 text-gray-300">·</span>
                  {{ seed.intent || "-" }}
                </div>
              </div>
            </div>

            <div v-if="dump.closing_intent">
              <div class="mb-1 text-xs text-gray-400">收束意图</div>
              <div class="text-gray-600">{{ dump.closing_intent }}</div>
            </div>

            <div v-if="dump.funny_why">
              <div class="mb-1 text-xs text-gray-400">funny_why</div>
              <div class="rounded-lg bg-gray-50 p-3 text-gray-600">{{ dump.funny_why }}</div>
            </div>

            <div v-if="dump.banned_literals?.length">
              <div class="mb-1 text-xs text-gray-400">禁词</div>
              <div class="flex flex-wrap gap-1">
                <el-tag
                  v-for="(w, i) in dump.banned_literals"
                  :key="i"
                  size="small"
                  type="danger"
                  effect="plain"
                >
                  {{ w }}
                </el-tag>
              </div>
            </div>

            <div>
              <div class="mb-1 text-xs text-gray-400">story_raw</div>
              <div
                v-if="dump.story_raw"
                class="whitespace-pre-wrap rounded-lg bg-gray-50 p-3 leading-relaxed text-gray-700"
              >
                {{ dump.story_raw }}
              </div>
              <div v-else class="text-gray-400">（无 story_raw）</div>
            </div>

            <div class="flex items-center justify-between gap-2">
              <div class="text-xs text-gray-400">ASR 逐字稿</div>
              <el-button type="primary" link size="small" @click="openTranscript">
                查看逐字稿
              </el-button>
            </div>
            <div v-if="dump.transcript_path" class="truncate text-xs text-gray-400" :title="dump.transcript_path">
              {{ dump.transcript_path }}
            </div>
          </div>
        </el-scrollbar>
      </div>

      <!-- 右侧：gold_chat 生成稿 -->
      <div class="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-gray-200 bg-gray-50">
        <div class="flex items-center justify-between border-b border-gray-100 px-4 py-2">
          <div class="text-sm font-medium text-gray-700">gold_chat</div>
          <div v-if="chatStory.scene_title" class="text-xs text-gray-500">
            {{ chatStory.scene_title }}
          </div>
        </div>

        <div
          v-if="detail.gold_chat?.export_missing"
          class="border-b border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-700"
        >
          导出文件缺失，请重转 gold_chat
        </div>

        <div
          v-if="detail.has_gold_chat && chatStory.dialogue?.length"
          class="border-b border-gray-100 px-4 py-2 text-xs text-gray-500"
        >
          {{ detail.gold_chat?.chat_lines ?? chatStory.dialogue.length }} 句 /
          {{ detail.gold_chat?.chat_chars ?? calcChatChars(chatStory.dialogue) }} 字
          <span v-if="detail.gold_chat?.exported_at" class="ml-2">
            · {{ formatDateTime(detail.gold_chat.exported_at) }}
          </span>
        </div>

        <el-scrollbar v-if="detail.has_gold_chat && chatStory.dialogue?.length" class="min-h-0 flex-1">
          <div class="space-y-2 p-4">
            <div
              v-for="(line, idx) in chatStory.dialogue"
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

        <div
          v-else
          class="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-gray-400"
        >
          <div>尚未转换 gold_chat</div>
          <el-button type="primary" :loading="converting" @click="handleConvert">
            转 gold_chat
          </el-button>
        </div>

        <div
          v-if="chatStory.punchline_explain"
          class="border-t border-gray-100 px-4 py-3 text-xs text-gray-500"
        >
          <span class="text-gray-400">笑点解析 · </span>{{ chatStory.punchline_explain }}
        </div>
      </div>
    </div>
    <div v-else-if="loading" class="py-16 text-center text-gray-400">加载中…</div>
    <div v-else class="py-16 text-center text-gray-400">暂无数据</div>

    <template v-if="detail" #footer>
      <div class="flex w-full items-center justify-between">
        <div class="text-xs text-gray-400">
          <span v-if="detail.gold_chat_daily_story_id">
            已导入日常故事
            <router-link to="/daily-story" class="text-blue-600 hover:underline">
              #{{ detail.gold_chat_daily_story_id }}
            </router-link>
          </span>
        </div>
        <div>
          <el-button @click="openTranscript">逐字稿</el-button>
          <el-button
            type="primary"
            plain
            :loading="converting"
            @click="handleConvert"
          >
            {{ detail.has_gold_chat ? "重转 gold_chat" : "转 gold_chat" }}
          </el-button>
          <el-button @click="visible = false">关闭</el-button>
          <el-button
            v-if="detail.has_gold_chat && chatStory.dialogue?.length"
            type="primary"
            :loading="importing"
            @click="handleImport"
          >
            {{ detail.gold_chat_daily_story_id ? "重新导入日常故事" : "导入日常故事" }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  calcChatChars,
  convertGoldChat,
  formatDailyStoryType,
  getGoldChat,
  importGoldChat,
  type GoldStoryDetail,
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
  (e: "imported"): void;
  (e: "converted"): void;
  (e: "open-transcript", payload: { id?: number | null; sourceId?: string | null; title?: string | null }): void;
}>();

const { handleError } = useErrorHandler();
const loading = ref(false);
const importing = ref(false);
const converting = ref(false);
const detail = ref<GoldStoryDetail | null>(null);

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const dump = computed(() => detail.value?.dump || {});

const chatStory = computed<StoryContent>(
  () => detail.value?.gold_chat?.daily_story || ({} as StoryContent),
);

const titleText = computed(() => {
  const t = detail.value?.title || detail.value?.source_id;
  return t ? `金故事 · ${t}` : "金故事详情";
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
    handleError(e, "加载金故事详情失败");
  } finally {
    loading.value = false;
  }
}

function openTranscript() {
  if (!detail.value) return;
  emit("open-transcript", {
    id: props.goldStoryId ?? detail.value.id ?? null,
    sourceId: props.sourceId ?? detail.value.source_id ?? null,
    title: detail.value.title ?? null,
  });
}

async function handleConvert() {
  if (!props.goldStoryId && !props.sourceId) return;
  const reconvert = !!detail.value?.has_gold_chat;
  if (reconvert) {
    try {
      await ElMessageBox.confirm("重新转换会覆盖已有 gold_chat，继续？", "确认", {
        type: "warning",
      });
    } catch {
      return;
    }
  }
  converting.value = true;
  try {
    const res = await convertGoldChat({
      id: props.goldStoryId ?? undefined,
      sourceId: props.sourceId ?? undefined,
      force: reconvert,
    });
    if (res.action === "skip") {
      ElMessage.info("已有导出，未重跑");
    } else {
      ElMessage.success(`已转换：${res.chat_lines ?? 0} 句`);
    }
    emit("converted");
    await loadDetail();
  } catch (e) {
    handleError(e, "转换失败");
  } finally {
    converting.value = false;
  }
}

async function handleImport() {
  if (!props.goldStoryId && !props.sourceId) return;
  const reimport = !!detail.value?.gold_chat_daily_story_id;
  if (reimport) {
    try {
      await ElMessageBox.confirm(
        `将覆盖日常故事 #${detail.value?.gold_chat_daily_story_id} 的对白，继续？`,
        "重新导入",
        { type: "warning" },
      );
    } catch {
      return;
    }
  }
  importing.value = true;
  try {
    const res = await importGoldChat({
      id: props.goldStoryId ?? undefined,
      sourceId: props.sourceId ?? undefined,
      force: reimport,
    });
    if (res.action === "skip") {
      ElMessage.info("已导入");
    } else {
      ElMessage.success(`已${reimport ? "重导" : "导入"} → #${res.daily_story_id}`);
    }
    emit("imported");
    await loadDetail();
  } catch (e) {
    handleError(e, "导入失败");
  } finally {
    importing.value = false;
  }
}

watch(
  () => [props.modelValue, props.goldStoryId, props.sourceId] as const,
  ([open]) => {
    if (open) void loadDetail();
  },
);
</script>
