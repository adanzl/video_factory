<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchItems">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" :loading="collecting" @click="handleCollect">
        采集（10 条）
      </el-button>
      <el-button
        type="primary"
        :disabled="!selectedIds.length"
        :loading="batching"
        @click="handleBatchConvert"
      >
        批量转 gold_chat{{ selectedIds.length ? `（${selectedIds.length}）` : "" }}
      </el-button>
      <el-button
        type="danger"
        :disabled="!selectedIds.length"
        :loading="deleting"
        @click="handleBatchDelete"
      >
        批量删除{{ selectedIds.length ? `（${selectedIds.length}）` : "" }}
      </el-button>
      <el-checkbox v-model="batchForce">已导出也重跑</el-checkbox>
      <el-select v-model="filterStatus" class="w-28!" @change="onFilterChange">
        <el-option label="active" value="active" />
        <el-option label="rejected" value="rejected" />
        <el-option label="全部" value="" />
      </el-select>
    </div>

    <el-table
      :data="items"
      stripe
      class="w-full gold-chat-table"
      v-loading="loading"
      row-class-name="gold-chat-row"
      @selection-change="onSelectionChange"
      @row-click="onRowClick"
      @row-dblclick="viewItem"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="source_id" label="BV" width="130" show-overflow-tooltip />
      <el-table-column prop="title" label="金故事标题" min-width="160" show-overflow-tooltip />
      <el-table-column label="结构" width="110">
        <template #default="{ row }">
          {{ formatDailyStoryType(row.structure_type) }}
        </template>
      </el-table-column>
      <el-table-column label="评分" width="70" align="center">
        <template #default="{ row }">
          {{ formatAutoScore(row.auto_score) }}
        </template>
      </el-table-column>
      <el-table-column label="gold_chat" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.has_gold_chat" type="success" size="small">已导出</el-tag>
          <el-tag v-else type="info" size="small">未导出</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="场景" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.scene_title || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="对白" width="90" align="center">
        <template #default="{ row }">
          <span v-if="row.has_gold_chat">
            {{ row.chat_lines ?? 0 }} / {{ row.chat_chars ?? 0 }}
          </span>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="日常故事" width="90" align="center">
        <template #default="{ row }">
          <router-link
            v-if="row.gold_chat_daily_story_id"
            :to="`/daily-story`"
            class="text-blue-600 hover:underline"
          >
            #{{ row.gold_chat_daily_story_id }}
          </router-link>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click.stop="viewItem(row)"
          >
            查看
          </el-button>
          <el-button
            type="primary"
            link
            size="small"
            @click.stop="viewTranscript(row)"
          >
            逐字稿
          </el-button>
          <el-button
            v-if="row.has_gold_chat"
            type="primary"
            link
            size="small"
            :loading="importingId === row.id"
            @click.stop="handleImportOne(row)"
          >
            {{ row.gold_chat_daily_story_id ? "重导" : "导入" }}
          </el-button>
          <el-button
            type="primary"
            link
            size="small"
            :loading="convertingId === row.id"
            @click.stop="handleConvertOne(row)"
          >
            {{ row.has_gold_chat ? "重转" : "转换" }}
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            :loading="deletingId === row.id"
            @click.stop="handleDeleteOne(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[15, 20, 50]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="onPageChange"
      @size-change="onPageSizeChange"
    />

    <GoldChatDetail
      v-model="showDetail"
      :gold-story-id="currentId"
      :source-id="currentSourceId"
      @closed="fetchItems"
      @imported="fetchItems"
      @converted="fetchItems"
      @open-transcript="openTranscriptFromDetail"
    />

    <GoldStoryTranscript
      v-model="showTranscript"
      :gold-story-id="transcriptId"
      :source-id="transcriptSourceId"
      :title="transcriptTitle"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/stores/app";
import { useErrorHandler } from "@/composables/useErrorHandler";
import GoldChatDetail from "@/views/gold_chat/dialogs/GoldChatDetail.vue";
import GoldStoryTranscript from "@/views/gold_chat/dialogs/GoldStoryTranscript.vue";
import {
  batchConvertGoldChat,
  collectGoldStories,
  convertGoldChat,
  deleteGoldStories,
  formatAutoScore,
  formatDailyStoryType,
  getGoldStoryCollectStatus,
  importGoldChat,
  listGoldChats,
  type GoldChatListItem,
  type GoldStoryCollectResult,
} from "@/api/api-gold-chat";

const { handleError } = useErrorHandler();

const items = ref<GoldChatListItem[]>([]);
const loading = ref(false);
const collecting = ref(false);
const POLL_INTERVAL_MS = 3000;
let collectPollTimer: ReturnType<typeof setInterval> | null = null;
const batching = ref(false);
const deleting = ref(false);
const convertingId = ref<number | null>(null);
const importingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);
const selectedIds = ref<number[]>([]);
const showDetail = ref(false);
const showTranscript = ref(false);
const currentId = ref<number | null>(null);
const currentSourceId = ref<string | null>(null);
const transcriptId = ref<number | null>(null);
const transcriptSourceId = ref<string | null>(null);
const transcriptTitle = ref<string | null>(null);

const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("goldChatPageSize") || "15", 10));
const total = ref(0);
const filterStatus = ref("active");
const batchForce = ref(false);

function stopCollectPolling() {
  if (collectPollTimer != null) {
    clearInterval(collectPollTimer);
    collectPollTimer = null;
  }
}

function formatCollectDone(res: GoldStoryCollectResult): string {
  return (
    `采集完成：候选 ${res.candidates ?? 0}，入库 ${res.inserted ?? 0}，` +
    `拒 ${res.inserted_rejected ?? 0}，跳过 ${res.skipped ?? 0}，` +
    `失败 ${res.failed ?? 0}`
  );
}

function startCollectPolling() {
  if (collectPollTimer != null) return;
  collectPollTimer = setInterval(() => {
    void pollCollectStatus();
  }, POLL_INTERVAL_MS);
}

async function fetchItems(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet === true;
  if (!quiet) loading.value = true;
  try {
    const res = await listGoldChats({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
      ...(filterStatus.value ? { status: filterStatus.value } : {}),
    });
    items.value = res.items;
    total.value = res.total;
  } catch (e) {
    handleError(e, "加载 gold_chat 列表失败");
  } finally {
    if (!quiet) loading.value = false;
  }
}

async function pollCollectStatus() {
  try {
    const res = await getGoldStoryCollectStatus();
    if (res.status === "running") {
      collecting.value = true;
      await fetchItems({ quiet: true });
      startCollectPolling();
      return;
    }
    const wasCollecting = collecting.value;
    collecting.value = false;
    stopCollectPolling();
    if (!wasCollecting) return;
    await fetchItems({ quiet: true });
    if (res.status === "error") {
      ElMessage.error(res.error || "采集失败");
      return;
    }
    if (res.status === "done") {
      ElMessage.success(formatCollectDone(res));
    }
  } catch (e) {
    handleError(e, "查询采集进度失败");
  }
}

function onFilterChange() {
  page.value = 1;
  selectedIds.value = [];
  void fetchItems();
}

function onPageChange() {
  selectedIds.value = [];
  void fetchItems();
}

function onPageSizeChange() {
  page.value = 1;
  selectedIds.value = [];
  localStorage.setItem("goldChatPageSize", String(pageSize.value));
  void fetchItems();
}

function onSelectionChange(rows: GoldChatListItem[]) {
  selectedIds.value = rows.map((r) => r.id);
}

function onRowClick(row: GoldChatListItem, _column: unknown, event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  if (target?.closest(".el-checkbox, .el-button, a")) return;
  viewItem(row);
}

function viewTranscript(row: GoldChatListItem) {
  transcriptId.value = row.id;
  transcriptSourceId.value = row.source_id;
  transcriptTitle.value = row.title;
  showTranscript.value = true;
}

function openTranscriptFromDetail(payload: {
  id?: number | null;
  sourceId?: string | null;
  title?: string | null;
}) {
  transcriptId.value = payload.id ?? null;
  transcriptSourceId.value = payload.sourceId ?? null;
  transcriptTitle.value = payload.title ?? null;
  showTranscript.value = true;
}

function viewItem(row: GoldChatListItem) {
  currentId.value = row.id;
  currentSourceId.value = row.source_id;
  showDetail.value = true;
}

async function handleImportOne(row: GoldChatListItem) {
  const reimport = !!row.gold_chat_daily_story_id;
  if (reimport) {
    try {
      await ElMessageBox.confirm(
        `将覆盖日常故事 #${row.gold_chat_daily_story_id} 的对白内容，继续？`,
        "重新导入",
        { type: "warning" },
      );
    } catch {
      return;
    }
  }
  importingId.value = row.id;
  try {
    const res = await importGoldChat({
      id: row.id,
      force: reimport,
    });
    if (res.action === "skip") {
      ElMessage.info("已导入，未重导");
    } else {
      ElMessage.success(
        `${res.action === "update" ? "已重导" : "已导入"} → 日常故事 #${res.daily_story_id}`,
      );
    }
    await fetchItems();
  } catch (e) {
    handleError(e, reimport ? "重导失败" : "导入失败");
  } finally {
    importingId.value = null;
  }
}

async function handleConvertOne(row: GoldChatListItem) {
  if (row.has_gold_chat) {
    try {
      await ElMessageBox.confirm("重新转换会覆盖已有导出，继续？", "确认", {
        type: "warning",
      });
    } catch {
      return;
    }
  }
  convertingId.value = row.id;
  try {
    const res = await convertGoldChat({
      id: row.id,
      force: row.has_gold_chat,
    });
    if (res.action === "skip") {
      ElMessage.info("已有导出，未重跑");
    } else {
      ElMessage.success(`已转换：${res.chat_lines ?? 0} 句`);
    }
    await fetchItems();
  } catch (e) {
    handleError(e, "转换失败");
  } finally {
    convertingId.value = null;
  }
}

async function handleDeleteOne(row: GoldChatListItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.title || row.source_id}」？关联逐字稿与导出文件将一并删除。`,
      "删除金故事",
      { type: "warning" },
    );
  } catch {
    return;
  }
  deletingId.value = row.id;
  try {
    const res = await deleteGoldStories([row.id]);
    if (res.deleted > 0) {
      ElMessage.success("已删除");
    } else {
      ElMessage.warning("未删除任何记录");
    }
    await fetchItems();
  } catch (e) {
    handleError(e, "删除失败");
  } finally {
    deletingId.value = null;
  }
}

async function handleBatchDelete() {
  if (!selectedIds.value.length) return;
  const n = selectedIds.value.length;
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${n} 条金故事？关联逐字稿与导出文件将一并删除。`,
      "批量删除",
      { type: "warning" },
    );
  } catch {
    return;
  }
  deleting.value = true;
  try {
    const res = await deleteGoldStories(selectedIds.value);
    ElMessage.success(`已删除 ${res.deleted} 条`);
    selectedIds.value = [];
    await fetchItems();
  } catch (e) {
    handleError(e, "批量删除失败");
  } finally {
    deleting.value = false;
  }
}

async function handleBatchConvert() {
  if (!selectedIds.value.length) return;
  const n = selectedIds.value.length;
  const hasExported = items.value.some(
    (row) => selectedIds.value.includes(row.id) && row.has_gold_chat,
  );
  if (hasExported && !batchForce.value) {
    try {
      await ElMessageBox.confirm(
        `选中 ${n} 条中有已导出项，未勾选「已导出也重跑」将跳过它们。继续？`,
        "批量转换",
        { type: "info" },
      );
    } catch {
      return;
    }
  } else {
    try {
      await ElMessageBox.confirm(
        `将转换选中的 ${n} 条金故事为 gold_chat，继续？`,
        "批量转换",
        { type: "info" },
      );
    } catch {
      return;
    }
  }
  batching.value = true;
  try {
    const res = await batchConvertGoldChat({
      ids: selectedIds.value,
      max: n,
      force: batchForce.value,
    });
    ElMessage.success(`完成：成功 ${res.ok}，跳过 ${res.skipped}，失败 ${res.failed}`);
    await fetchItems();
  } catch (e) {
    handleError(e, "批量转换失败");
  } finally {
    batching.value = false;
  }
}

async function handleCollect() {
  try {
    await ElMessageBox.confirm(
      "将从 B 站搜索并采集最多 10 条金故事（含转写与结构化），后台进行，继续？",
      "采集金故事",
      { type: "info" },
    );
  } catch {
    return;
  }
  collecting.value = true;
  try {
    const res = await collectGoldStories({ max: 10 });
    if (res.status === "running") {
      ElMessage.success("已开始采集，完成后列表会自动刷新");
      startCollectPolling();
      return;
    }
    collecting.value = false;
    ElMessage.success(formatCollectDone(res));
    await fetchItems();
  } catch (e) {
    collecting.value = false;
    handleError(e, "采集失败");
  }
}

onMounted(() => {
  void fetchItems();
  void pollCollectStatus();
});
onUnmounted(stopCollectPolling);
usePageRefresh(fetchItems);
</script>

<style scoped>
:deep(.gold-chat-row) {
  cursor: pointer;
}
</style>
