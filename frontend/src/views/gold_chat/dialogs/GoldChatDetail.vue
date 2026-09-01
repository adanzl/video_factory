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

            <div
              v-if="auditBlock"
              class="rounded-lg border border-red-100 bg-red-50 p-3"
            >
              <div class="mb-2 flex flex-wrap items-center gap-2 text-sm font-medium text-red-700">
                {{ auditTitle }}
                <el-tag v-if="auditBlock.stage" size="small" type="info">
                  {{ formatAuditStage(auditBlock.stage) }}
                </el-tag>
              </div>
              <ul
                v-if="auditBlock.reject_reasons?.length"
                class="list-disc space-y-1 pl-4 text-sm text-red-800"
              >
                <li v-for="(reason, i) in auditBlock.reject_reasons" :key="i">
                  {{ reason }}
                </li>
              </ul>
              <div
                v-if="auditBlock.audit_notes"
                class="mt-2 text-xs leading-relaxed text-red-700"
              >
                {{ auditBlock.audit_notes }}
              </div>
              <div v-if="auditScoreText" class="mt-2 text-xs text-gray-500">
                {{ auditScoreText }}
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
          <div class="text-sm font-medium text-gray-700">对话稿</div>
          <div v-if="chatStory.scene_title" class="text-xs text-gray-500">
            {{ chatStory.scene_title }}
          </div>
        </div>

        <div
          v-if="detail.gold_chat_error?.error"
          class="border-b border-red-100 bg-red-50 px-4 py-2"
        >
          <el-tooltip placement="top" :show-after="300">
            <template #content>
              <div class="max-w-md whitespace-pre-wrap wrap-break-word text-xs">
                {{ detail.gold_chat_error.error }}
              </div>
            </template>
            <div
              class="line-clamp-2 cursor-default text-xs leading-relaxed wrap-break-word text-red-700"
            >
              <span class="font-medium">转换失败：</span>{{ detail.gold_chat_error.error }}
            </div>
          </el-tooltip>
          <div
            v-if="detail.gold_chat_error.failed_at"
            class="mt-1 truncate text-xs text-red-500"
            :title="detail.gold_chat_error.failed_at"
          >
            {{ formatDateTime(detail.gold_chat_error.failed_at) }}
          </div>
        </div>

        <div
          v-if="detail.gold_chat?.export_missing"
          class="border-b border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-700"
        >
          导出文件缺失，请重转 对话稿
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
          <div>尚未转换 对话稿</div>
          <el-button type="primary" :loading="converting" @click="handleConvert">
            转 对话稿
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
        <div class="flex items-center gap-2">
          <el-radio-group
          :model-value="statusChoice"
          size="small"
          :disabled="statusBusy"
          @change="onStatusChoiceChange"
          >
          <el-radio-button value="normal">正常</el-radio-button>
          <el-radio-button value="rejected">驳回</el-radio-button>
          <el-radio-button value="archived">归档</el-radio-button>
        </el-radio-group>
        <div class="text-xs text-gray-400">
          <span v-if="detail.gold_chat_daily_story_id">
            已导入日常故事
            <router-link to="/daily-story" class="text-blue-600 hover:underline">
              #{{ detail.gold_chat_daily_story_id }}
            </router-link>
          </span>
        </div>
        </div>
        <div>
          <el-button @click="openTranscript">逐字稿</el-button>
          <el-button
            type="primary"
            plain
            :loading="reimporting"
            :disabled="converting || importing"
            @click="handleReimportFromBv"
          >
            从 BV 重新导入
          </el-button>
          <el-button
            type="primary"
            plain
            :loading="converting"
            @click="handleConvert"
          >
            {{ detail.has_gold_chat ? "重转 对话稿" : "转 对话稿" }}
          </el-button>
          <el-button
            v-if="detail.has_gold_chat && chatStory.dialogue?.length"
            type="primary"
            :loading="importing"
            @click="handleImport"
          >
            {{ detail.gold_chat_daily_story_id ? "重导日常故事" : "导入日常故事" }}
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
  archiveGoldStories,
  calcChatChars,
  convertGoldChat,
  formatDailyStoryType,
  getGoldChat,
  importGoldChat,
  rejectGoldStories,
  restoreGoldStories,
  reimportGoldStories,
  type GoldStoryAudit,
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
  (e: "status-changed"): void;
  (e: "converting", payload: { id?: number | null; sourceId?: string | null }): void;
  (e: "converted", payload: { id?: number | null; sourceId?: string | null }): void;
  (e: "reimported"): void;
  (e: "open-transcript", payload: { id?: number | null; sourceId?: string | null; title?: string | null }): void;
}>();

const { handleError } = useErrorHandler();
const loading = ref(false);
const importing = ref(false);
const converting = ref(false);
const reimporting = ref(false);
const statusUpdating = ref(false);
const detail = ref<GoldStoryDetail | null>(null);

type StatusChoice = "normal" | "rejected" | "archived";

const statusBusy = computed(
  () => converting.value || importing.value || reimporting.value || statusUpdating.value,
);

const statusChoice = computed<StatusChoice>(() => {
  const st = detail.value?.status;
  if (st === "rejected") return "rejected";
  if (st === "archived") return "archived";
  return "normal";
});

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const dump = computed(() => detail.value?.dump || {});

const chatStory = computed<StoryContent>(
  () => detail.value?.gold_chat?.daily_story || ({} as StoryContent),
);

const titleText = computed(() => {
  const id = detail.value?.id ?? props.goldStoryId;
  const name = detail.value?.title || detail.value?.source_id;
  if (id != null) {
    return name ? `金故事 #${id} · ${name}` : `金故事 #${id}`;
  }
  return name ? `金故事 · ${name}` : "金故事详情";
});

const auditBlock = computed<GoldStoryAudit | null>(() => {
  const audit = detail.value?.audit;
  if (!audit) return null;
  const hasReasons = (audit.reject_reasons?.length ?? 0) > 0;
  const hasNote = !!audit.audit_notes?.trim();
  const rejected = detail.value?.status === "rejected" || audit.pass === false;
  const archived = detail.value?.status === "archived";
  if (!rejected && !archived && !hasReasons && !hasNote) return null;
  return audit;
});

const auditTitle = computed(() => {
  if (detail.value?.status === "archived") return "已归档";
  if (detail.value?.status === "rejected") return "已驳回";
  if (auditBlock.value?.pass === false) return "机审未通过";
  return "机审";
});

const auditScoreText = computed(() => {
  const scores = auditBlock.value?.llm_scores;
  if (!scores) return "";
  const parts: string[] = [];
  if (scores.sibling_fit != null) parts.push(`姐弟适配 ${scores.sibling_fit}`);
  if (scores.age_fit != null) parts.push(`年龄适配 ${scores.age_fit}`);
  if (scores.conflict_usable != null) parts.push(`冲突可用 ${scores.conflict_usable}`);
  if (scores.mapping_fit != null) parts.push(`映射适配 ${scores.mapping_fit}`);
  return parts.join(" · ");
});

function formatAuditStage(stage: string): string {
  if (stage === "rules") return "规则机审";
  if (stage === "llm") return "LLM 机审";
  if (stage === "manual") {
    return detail.value?.status === "archived" ? "人工归档" : "人工驳回";
  }
  if (stage === "funny_signal") return "好笑门控";
  if (stage === "pipeline") return "流水线";
  return stage;
}

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
  const convertTarget = {
    id: props.goldStoryId ?? detail.value?.id ?? null,
    sourceId: props.sourceId ?? detail.value?.source_id ?? null,
  };
  converting.value = true;
  emit("converting", convertTarget);
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
    emit("converted", convertTarget);
    await loadDetail();
  } catch (e) {
    emit("converted", convertTarget);
    handleError(e, "转换失败");
    await loadDetail();
  } finally {
    converting.value = false;
  }
}

async function handleReimportFromBv() {
  if (!props.goldStoryId && !props.sourceId) return;
  const bv = detail.value?.source_id || props.sourceId || "";
  try {
    await ElMessageBox.confirm(
      `将从 ${bv || "BV"} 重跑转写与结构化，覆盖本条金稿。` +
        "已导出的 gold_chat 不会自动重转。继续？",
      "从 BV 重新导入",
      { type: "warning" },
    );
  } catch {
    return;
  }
  reimporting.value = true;
  try {
    const res = await reimportGoldStories({
      ids: props.goldStoryId ? [props.goldStoryId] : undefined,
      sourceId: props.goldStoryId ? undefined : (props.sourceId ?? undefined),
      forceTranscript: true,
    });
    if (res.status === "running") {
      ElMessage.success("已开始从 BV 重新导入");
      emit("reimported");
      visible.value = false;
      return;
    }
    ElMessage.success("重新导入完成");
    emit("reimported");
    await loadDetail();
  } catch (e) {
    handleError(e, "重新导入失败");
  } finally {
    reimporting.value = false;
  }
}

async function onStatusChoiceChange(next: StatusChoice) {
  if (!detail.value || next === statusChoice.value) return;
  const id = detail.value.id ?? props.goldStoryId;
  if (!id) return;
  statusUpdating.value = true;
  try {
    if (next === "rejected") {
      const res = await rejectGoldStories([id]);
      if (res.rejected <= 0) {
        ElMessage.warning("未驳回");
        return;
      }
    } else if (next === "archived") {
      const res = await archiveGoldStories([id]);
      if (res.archived <= 0) {
        ElMessage.warning("未归档");
        return;
      }
    } else if (detail.value.status === "rejected") {
      const res = await restoreGoldStories([id], "rejected");
      if (res.restored <= 0) {
        ElMessage.warning("未恢复");
        return;
      }
    } else if (detail.value.status === "archived") {
      const res = await restoreGoldStories([id], "archived");
      if (res.restored <= 0) {
        ElMessage.warning("未恢复");
        return;
      }
    }
    emit("status-changed");
    await loadDetail();
  } catch (e) {
    handleError(e, "状态更新失败");
  } finally {
    statusUpdating.value = false;
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
