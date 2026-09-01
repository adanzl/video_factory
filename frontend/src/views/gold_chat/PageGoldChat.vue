<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" size="small" :disabled="loading" @click="fetchItems">
        <el-icon>
          <Refresh />
        </el-icon>
      </el-button>
      <el-button type="primary" size="small" :loading="collecting" @click="handleCollect">
        {{ collectButtonLabel }}
      </el-button>
      <el-button type="primary" size="small" :loading="reimporting" @click="handleReimport">
        重新导入
      </el-button>
      <el-button type="success" size="small" :loading="reimporting" @click="handleImportBV">
        从BV导入
      </el-button>
      <el-button type="primary" size="small" :disabled="!selectedIds.length" :loading="batching" @click="handleBatchConvert">
        批量转对话{{ selectedIds.length ? `（${selectedIds.length}）` : "" }}
      </el-button>
      <el-button type="danger" size="small" :disabled="!selectedIds.length" :loading="deleting" @click="handleBatchDelete">
        批量删除{{ selectedIds.length ? `（${selectedIds.length}）` : "" }}
      </el-button>
      <el-checkbox v-model="batchForce" size="small">已导出也重跑</el-checkbox>
      <el-checkbox v-model="filterExcludeArchived" size="small" @change="onFilterChange">
        包含已归档
      </el-checkbox>
      <el-radio-group v-model="filterHasStory" size="small" @change="onFilterChange">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="yes">已导入日常</el-radio-button>
        <el-radio-button value="no">未导入日常</el-radio-button>
      </el-radio-group>
      <span v-if="collecting && collectProgressText" class="text-xs text-gray-500">
        {{ collectProgressText }}
      </span>
    </div>

    <el-table :data="items" stripe class="w-full gold-chat-table" v-loading="loading" row-class-name="gold-chat-row"
      @selection-change="onSelectionChange" @row-click="onRowClick" @row-dblclick="viewItem">
      <el-table-column type="selection" width="30" />
      <el-table-column prop="id" label="ID" width="50" />
      <el-table-column label="状态" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="isReimportProcessing(row)" type="warning" size="small">
            <span class="inline-flex items-center gap-1">
              处理中
            </span>
          </el-tag>
          <el-tag v-else :type="statusTagType(row.status)" size="small">
            {{ formatStoryStatus(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source_id" label="BV" width="135" show-overflow-tooltip />
      <el-table-column prop="title" label="金故事标题" min-width="160" show-overflow-tooltip />
      <el-table-column label="结构" width="120">
        <template #default="{ row }">
          {{ formatDailyStoryType(row.structure_type) }}
        </template>
      </el-table-column>
      <el-table-column label="评分" width="60" align="center">
        <template #default="{ row }">
          {{ formatAutoScore(row.auto_score) }}
        </template>
      </el-table-column>
      <el-table-column label="对话稿" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="isGoldChatConverting(row)" type="warning" size="small">
            <span class="inline-flex items-center gap-1">
              转换中
            </span>
          </el-tag>
          <el-tag v-else-if="row.has_gold_chat" type="success" size="small">已导出</el-tag>
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
          <router-link v-if="row.gold_chat_daily_story_id" :to="`/daily-story`" class="text-blue-600 hover:underline">
            #{{ row.gold_chat_daily_story_id }}
          </router-link>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="150" align="center">
        <template #default="{ row }">
          <el-tooltip :content="row.updated_at || ''" placement="top" :disabled="!row.updated_at">
            <span>{{ row.updated_at ? formatUpdateTime(row.updated_at) : "-" }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click.stop="viewItem(row)">
            查看
          </el-button>
          <el-button type="primary" link size="small" @click.stop="viewTranscript(row)">
            逐字稿
          </el-button>
          <el-button
            v-if="row.status !== 'archived'"
            type="warning"
            link
            size="small"
            :loading="archivingId === row.id"
            @click.stop="handleArchiveOne(row)"
          >
            归档
          </el-button>
          <el-button type="danger" link size="small" :loading="deletingId === row.id"
            @click.stop="handleDeleteOne(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[15, 20, 50]"
      layout="sizes, prev, pager, next" class="mt-4 justify-start" @current-change="onPageChange"
      @size-change="onPageSizeChange" />

    <GoldChatDetail v-model="showDetail" :gold-story-id="currentId" :source-id="currentSourceId"
      @closed="onDetailClosed" @imported="fetchItems" @status-changed="fetchItems" @converting="onDetailConverting"
      @converted="onDetailConverted" @reimported="onDetailReimported"
      @open-transcript="openTranscriptFromDetail" />

    <GoldStoryTranscript v-model="showTranscript" :gold-story-id="transcriptId" :source-id="transcriptSourceId"
      :title="transcriptTitle" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/stores/app";
import { useErrorHandler } from "@/composables/useErrorHandler";
import GoldChatDetail from "@/views/gold_chat/dialogs/GoldChatDetail.vue";
import GoldStoryTranscript from "@/views/gold_chat/dialogs/GoldStoryTranscript.vue";
import {
  archiveGoldStories,
  batchConvertGoldChat,
  collectGoldStories,
  deleteGoldStories,
  formatAutoScore,
  formatDailyStoryType,
  getGoldStoryCollectStatus,
  getGoldStoryReimportStatus,
  listGoldChats,
  reimportGoldStories,
  type GoldChatListItem,
  type GoldStoryCollectResult,
  type GoldStoryReimportResult,
} from "@/api/api-gold-chat";

function formatUpdateTime(value?: string): string {
  if (!value) return "-";
  return value.split(" ")[0];
}

const { handleError } = useErrorHandler();

const items = ref<GoldChatListItem[]>([]);
const loading = ref(false);
const collecting = ref(false);
const reimporting = ref(false);
const POLL_INTERVAL_MS = 3000;
let collectPollTimer: ReturnType<typeof setInterval> | null = null;
let reimportPollTimer: ReturnType<typeof setInterval> | null = null;
const batching = ref(false);
const deleting = ref(false);
const reimportingIds = ref<number[]>([]);
const reimportingSourceIds = ref<string[]>([]);
const convertingIds = ref<number[]>([]);
const convertingSourceIds = ref<string[]>([]);
const archivingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);
const selectedIds = ref<number[]>([]);
const showDetail = ref(false);
const showTranscript = ref(false);
const currentId = ref<number | null>(null);
const currentSourceId = ref<string | null>(null);
const transcriptId = ref<number | null>(null);
const transcriptSourceId = ref<string | null>(null);
const transcriptTitle = ref<string | null>(null);

const FILTER_HAS_STORY_KEY = "goldChatFilterHasStory";
const FILTER_HAS_STORY_VALUES = ["", "yes", "no"];
const FILTER_EXCLUDE_ARCHIVED_KEY = "goldChatFilterExcludeArchived";

function readStoredChoice(key: string, allowed: string[]): string {
  const raw = localStorage.getItem(key);
  if (raw == null) return "";
  return allowed.includes(raw) ? raw : "";
}

const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("goldChatPageSize") || "15", 10));
const total = ref(0);
const filterHasStory = ref(readStoredChoice(FILTER_HAS_STORY_KEY, FILTER_HAS_STORY_VALUES));
const filterExcludeArchived = ref(
  localStorage.getItem(FILTER_EXCLUDE_ARCHIVED_KEY) !== "false",
);
const batchForce = ref(false);
const collectPhase = ref("");
const collectEnqueued = ref(0);
const collectProcessed = ref(0);
const collectCandidates = ref(0);

const collectButtonLabel = computed(() => {
  if (!collecting.value) return "采集（10 条）";
  if (collectPhase.value === "enqueue" || collectPhase.value === "enqueued") {
    return `入队中 ${collectEnqueued.value}/${collectCandidates.value || "?"}`;
  }
  if (collectPhase.value === "process") {
    return `转写中 ${collectProcessed.value}/${collectEnqueued.value || "?"}`;
  }
  return "采集中…";
});

const collectProgressText = computed(() => {
  if (!collecting.value) return "";
  if (collectPhase.value === "enqueue" || collectPhase.value === "enqueued") {
    return `已入队 ${collectEnqueued.value}，随后异步 OCR`;
  }
  if (collectPhase.value === "process") {
    return `队列处理 ${collectProcessed.value}/${collectEnqueued.value || collectCandidates.value || "?"}`;
  }
  return "";
});

function formatStoryStatus(status: string): string {
  if (status === "pending") return "排队中";
  if (status === "processing") return "处理中";
  if (status === "active") return "通过";
  if (status === "rejected") return "驳回";
  if (status === "archived") return "归档";
  if (status === "promoted") return "晋升";
  if (status === "retired") return "淘汰";
  return status || "-";
}

function statusTagType(
  status: string,
): "success" | "danger" | "warning" | "info" {
  if (status === "active" || status === "promoted") return "success";
  if (status === "pending" || status === "processing") return "warning";
  if (status === "rejected") return "info";
  if (status === "archived") return "info";
  if (status === "retired") return "info";
  return "warning";
}

function clearReimportTargets() {
  reimportingIds.value = [];
  reimportingSourceIds.value = [];
}

function clearConvertingTargets() {
  convertingIds.value = [];
  convertingSourceIds.value = [];
}

function setConvertingTargets(opts: {
  ids?: number[] | null;
  sourceIds?: string[] | null;
}) {
  const ids = (opts.ids || []).filter((id) => Number.isFinite(id) && id > 0);
  const sourceIds = (opts.sourceIds || [])
    .map((s) => String(s || "").trim())
    .filter(Boolean);
  convertingIds.value = [...new Set([...convertingIds.value, ...ids])];
  convertingSourceIds.value = [
    ...new Set([...convertingSourceIds.value, ...sourceIds]),
  ];
}

function removeConvertingTargets(opts: {
  ids?: number[] | null;
  sourceIds?: string[] | null;
}) {
  const ids = new Set((opts.ids || []).filter((id) => Number.isFinite(id) && id > 0));
  const sourceIds = new Set(
    (opts.sourceIds || []).map((s) => String(s || "").trim()).filter(Boolean),
  );
  if (ids.size) {
    convertingIds.value = convertingIds.value.filter((id) => !ids.has(id));
  }
  if (sourceIds.size) {
    convertingSourceIds.value = convertingSourceIds.value.filter(
      (sid) => !sourceIds.has(sid),
    );
  }
}

function setReimportTargets(opts: {
  ids?: number[] | null;
  sourceIds?: string[] | null;
}) {
  const ids = (opts.ids || []).filter((id) => Number.isFinite(id) && id > 0);
  const sourceIds = (opts.sourceIds || [])
    .map((s) => String(s || "").trim())
    .filter(Boolean);
  reimportingIds.value = [...new Set(ids)];
  reimportingSourceIds.value = [...new Set(sourceIds)];
}

function isReimportProcessing(row: GoldChatListItem): boolean {
  if (reimportingIds.value.includes(row.id)) return true;
  const sid = String(row.source_id || "").trim();
  return !!sid && reimportingSourceIds.value.includes(sid);
}

function isGoldChatConverting(row: GoldChatListItem): boolean {
  if (convertingIds.value.includes(row.id)) return true;
  const sid = String(row.source_id || "").trim();
  return !!sid && convertingSourceIds.value.includes(sid);
}

function stopCollectPolling() {
  if (collectPollTimer != null) {
    clearInterval(collectPollTimer);
    collectPollTimer = null;
  }
}

function stopReimportPolling() {
  if (reimportPollTimer != null) {
    clearInterval(reimportPollTimer);
    reimportPollTimer = null;
  }
}

function formatCollectDone(res: GoldStoryCollectResult): string {
  return (
    `采集完成：入队 ${res.enqueued ?? res.candidates ?? 0}，` +
    `通过 ${res.inserted ?? 0}，审拒 ${res.inserted_rejected ?? 0}，` +
    `门拒 ${res.gate_rejected ?? 0}，失败 ${res.failed ?? 0}`
  );
}

function applyCollectProgress(res: GoldStoryCollectResult) {
  collectPhase.value = String(res.phase || "");
  collectEnqueued.value = Number(res.enqueued || 0);
  collectProcessed.value = Number(res.processed || 0);
  collectCandidates.value = Number(res.candidates || 0);
}

function resetCollectProgress() {
  collectPhase.value = "";
  collectEnqueued.value = 0;
  collectProcessed.value = 0;
  collectCandidates.value = 0;
}

function showCollectListFilters() {
  // 采集后应能看见 pending，避免「有故事/通过」筛掉
  page.value = 1;
  if (filterHasStory.value === "yes") {
    filterHasStory.value = "";
    localStorage.setItem(FILTER_HAS_STORY_KEY, "");
  }
}

function formatReimportDone(res: GoldStoryReimportResult): string {
  return (
    `重新导入完成：成功 ${res.ok ?? 0}，覆盖 ${res.updated ?? 0}，` +
    `新建 ${res.inserted ?? 0}，驳回 ${res.rejected ?? 0}，失败 ${res.failed ?? 0}`
  );
}

function startCollectPolling() {
  if (collectPollTimer != null) return;
  collectPollTimer = setInterval(() => {
    void pollCollectStatus();
  }, POLL_INTERVAL_MS);
}

function startReimportPolling() {
  if (reimportPollTimer != null) return;
  reimportPollTimer = setInterval(() => {
    void pollReimportStatus();
  }, POLL_INTERVAL_MS);
}

async function fetchItems(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet === true;
  if (!quiet) loading.value = true;
  try {
    const res = await listGoldChats({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
      exclude_archived: !filterExcludeArchived.value,
      ...(filterHasStory.value === "yes"
        ? { has_story: true }
        : filterHasStory.value === "no"
          ? { has_story: false }
          : {}),
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
    applyCollectProgress(res);
    if (res.status === "running") {
      collecting.value = true;
      showCollectListFilters();
      await fetchItems({ quiet: true });
      startCollectPolling();
      return;
    }
    const wasCollecting = collecting.value;
    collecting.value = false;
    stopCollectPolling();
    if (!wasCollecting) {
      resetCollectProgress();
      return;
    }
    showCollectListFilters();
    await fetchItems({ quiet: true });
    if (res.status === "error") {
      ElMessage.error(res.error || "采集失败");
      resetCollectProgress();
      return;
    }
    if (res.status === "done") {
      ElMessage.success(formatCollectDone(res));
      resetCollectProgress();
    }
  } catch (e) {
    handleError(e, "查询采集进度失败");
  }
}

async function pollReimportStatus() {
  try {
    const res = await getGoldStoryReimportStatus();
    if (res.status === "running") {
      reimporting.value = true;
      setReimportTargets({
        ids: res.ids,
        sourceIds: res.source_ids,
      });
      await fetchItems({ quiet: true });
      startReimportPolling();
      return;
    }
    const wasReimporting = reimporting.value;
    reimporting.value = false;
    clearReimportTargets();
    stopReimportPolling();
    if (!wasReimporting) return;
    await fetchItems({ quiet: true });
    if (res.status === "error") {
      ElMessage.error(res.error || "重新导入失败");
      return;
    }
    if (res.status === "done") {
      ElMessage.success(formatReimportDone(res));
    }
  } catch (e) {
    handleError(e, "查询重新导入进度失败");
  }
}

function onFilterChange() {
  localStorage.setItem(FILTER_HAS_STORY_KEY, filterHasStory.value);
  localStorage.setItem(FILTER_EXCLUDE_ARCHIVED_KEY, String(filterExcludeArchived.value));
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

function onDetailConverting(payload?: {
  id?: number | null;
  sourceId?: string | null;
}) {
  setConvertingTargets({
    ids: payload?.id != null ? [payload.id] : currentId.value != null ? [currentId.value] : [],
    sourceIds: payload?.sourceId
      ? [payload.sourceId]
      : currentSourceId.value
        ? [currentSourceId.value]
        : [],
  });
}

function onDetailConverted(payload?: {
  id?: number | null;
  sourceId?: string | null;
}) {
  if (payload?.id != null || payload?.sourceId) {
    removeConvertingTargets({
      ids: payload?.id != null ? [payload.id] : undefined,
      sourceIds: payload?.sourceId ? [payload.sourceId] : undefined,
    });
  } else {
    clearConvertingTargets();
  }
  void fetchItems({ quiet: true });
}

function onDetailClosed() {
  void fetchItems();
}

function onDetailReimported() {
  reimporting.value = true;
  setReimportTargets({
    ids: currentId.value != null ? [currentId.value] : [],
    sourceIds: currentSourceId.value ? [currentSourceId.value] : [],
  });
  startReimportPolling();
  void fetchItems({ quiet: true });
}

function viewItem(row: GoldChatListItem) {
  currentId.value = row.id;
  currentSourceId.value = row.source_id;
  showDetail.value = true;
}

async function handleArchiveOne(row: GoldChatListItem) {
  if (row.status === "archived") return;
  try {
    await ElMessageBox.confirm(
      `确定归档「${row.title || row.source_id}」？仅改状态，不删文件。`,
      "归档金故事",
      { type: "warning" },
    );
  } catch {
    return;
  }
  archivingId.value = row.id;
  try {
    const res = await archiveGoldStories([row.id]);
    if (res.archived > 0) {
      ElMessage.success("已归档");
    } else {
      ElMessage.warning("未归档任何记录");
    }
    await fetchItems();
  } catch (e) {
    handleError(e, "归档失败");
  } finally {
    archivingId.value = null;
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
  setConvertingTargets({
    ids: selectedIds.value,
    sourceIds: items.value
      .filter((row) => selectedIds.value.includes(row.id))
      .map((row) => String(row.source_id || "").trim())
      .filter(Boolean),
  });
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
    clearConvertingTargets();
  }
}

async function startReimportJob(params: {
  ids?: number[];
  sourceId?: string;
}) {
  reimporting.value = true;
  setReimportTargets({
    ids: params.ids,
    sourceIds: params.sourceId ? [params.sourceId] : [],
  });
  try {
    const res = await reimportGoldStories({
      ids: params.ids,
      sourceId: params.sourceId,
      forceTranscript: true,
    });
    if (res.status === "running") {
      setReimportTargets({
        ids: res.ids?.length ? res.ids : params.ids,
        sourceIds: res.source_ids?.length
          ? res.source_ids
          : params.sourceId
            ? [params.sourceId]
            : [],
      });
      ElMessage.success("已开始从 BV 重新导入，完成后列表会自动刷新");
      startReimportPolling();
      return;
    }
    reimporting.value = false;
    clearReimportTargets();
    ElMessage.success(formatReimportDone(res));
    await fetchItems();
  } catch (e) {
    reimporting.value = false;
    clearReimportTargets();
    handleError(e, "重新导入失败");
  }
}

async function handleImportBV() {
  if (selectedIds.value.length) {
    ElMessage.warning("已选中金故事时请使用「重新导入」按钮");
    return;
  }
  let raw = "";
  try {
    const { value } = await ElMessageBox.prompt(
      "输入 BV 号或 B 站视频链接。已入库的会覆盖金稿，未入库的会新导入。",
      "导入BV",
      {
        inputPlaceholder: "BV1xxxx 或视频链接",
        confirmButtonText: "开始导入",
        inputValidator: (val: string) => {
          if (!String(val || "").trim()) return "请输入 BV 号";
          return true;
        },
      },
    );
    raw = String(value || "").trim();
  } catch {
    return;
  }
  if (!raw) return;
  await startReimportJob({ sourceId: raw });
}

async function handleReimport() {
  if (selectedIds.value.length) {
    const n = selectedIds.value.length;
    try {
      await ElMessageBox.confirm(
        `将从 BV 重跑转写与结构化，覆盖选中的 ${n} 条金稿。` +
        "已导出的 gold_chat 不会自动重转。继续？",
        "重新导入",
        { type: "warning" },
      );
    } catch {
      return;
    }
    await startReimportJob({ ids: [...selectedIds.value] });
    return;
  }
  let raw = "";
  try {
    const { value } = await ElMessageBox.prompt(
      "输入 BV 号或 B 站视频链接。已入库的会覆盖金稿，未入库的会新导入。",
      "重新导入金稿",
      {
        inputPlaceholder: "BV1xxxx 或视频链接",
        confirmButtonText: "开始导入",
        inputValidator: (val: string) => {
          if (!String(val || "").trim()) return "请输入 BV 号";
          return true;
        },
      },
    );
    raw = String(value || "").trim();
  } catch {
    return;
  }
  if (!raw) return;
  await startReimportJob({ sourceId: raw });
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
  showCollectListFilters();
  try {
    const res = await collectGoldStories({ max: 10 });
    applyCollectProgress(res);
    if (res.status === "running") {
      ElMessage.success("已开始采集：先入队，再异步转写");
      startCollectPolling();
      await fetchItems({ quiet: true });
      return;
    }
    collecting.value = false;
    ElMessage.success(formatCollectDone(res));
    resetCollectProgress();
    await fetchItems();
  } catch (e) {
    collecting.value = false;
    resetCollectProgress();
    handleError(e, "采集失败");
  }
}

onMounted(() => {
  void fetchItems();
  void pollCollectStatus();
  void pollReimportStatus();
});
onUnmounted(() => {
  stopCollectPolling();
  stopReimportPolling();
});
usePageRefresh(fetchItems);
</script>

<style scoped>
:deep(.gold-chat-row) {
  cursor: pointer;
}
</style>
