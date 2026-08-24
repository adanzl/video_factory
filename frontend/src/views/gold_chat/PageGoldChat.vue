<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchItems">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" :loading="batching" @click="handleBatchConvert">
        批量转 gold_chat（{{ batchMax }} 条）
      </el-button>
      <el-input-number v-model="batchMax" :min="1" :max="50" size="small" class="w-28!" />
      <el-checkbox v-model="batchForce">已导出也重跑</el-checkbox>
      <el-select v-model="filterStatus" class="w-28!" @change="onFilterChange">
        <el-option label="active" value="active" />
        <el-option label="rejected" value="rejected" />
        <el-option label="全部" value="" />
      </el-select>
      <el-button
        type="primary"
        :disabled="!selectedIds.length"
        :loading="converting"
        @click="handleConvertSelected"
      >
        转换选中
      </el-button>
    </div>

    <el-table
      :data="items"
      stripe
      class="w-full"
      v-loading="loading"
      @selection-change="onSelectionChange"
      @row-dblclick="viewItem"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="source_id" label="BV" width="130" show-overflow-tooltip />
      <el-table-column prop="title" label="金故事标题" min-width="160" show-overflow-tooltip />
      <el-table-column label="结构" width="100">
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
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="viewItem(row)"
          >
            查看
          </el-button>
          <el-button
            v-if="row.has_gold_chat"
            type="primary"
            link
            size="small"
            :loading="importingId === row.id"
            @click="handleImportOne(row)"
          >
            {{ row.gold_chat_daily_story_id ? "重导" : "导入" }}
          </el-button>
          <el-button
            type="primary"
            link
            size="small"
            :loading="convertingId === row.id"
            @click="handleConvertOne(row)"
          >
            {{ row.has_gold_chat ? "重转" : "转换" }}
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
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/stores/app";
import { useErrorHandler } from "@/composables/useErrorHandler";
import GoldChatDetail from "@/views/gold_chat/dialogs/GoldChatDetail.vue";
import {
  batchConvertGoldChat,
  convertGoldChat,
  formatAutoScore,
  formatDailyStoryType,
  importGoldChat,
  listGoldChats,
  type GoldChatListItem,
} from "@/api/api-gold-chat";

const { handleError } = useErrorHandler();

const items = ref<GoldChatListItem[]>([]);
const loading = ref(false);
const batching = ref(false);
const converting = ref(false);
const convertingId = ref<number | null>(null);
const importingId = ref<number | null>(null);
const selectedIds = ref<number[]>([]);
const showDetail = ref(false);
const currentId = ref<number | null>(null);
const currentSourceId = ref<string | null>(null);

const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("goldChatPageSize") || "15", 10));
const total = ref(0);
const filterStatus = ref("active");
const batchMax = ref(10);
const batchForce = ref(false);

async function fetchItems() {
  loading.value = true;
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
    loading.value = false;
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

async function handleConvertSelected() {
  if (!selectedIds.value.length) return;
  converting.value = true;
  try {
    const res = await batchConvertGoldChat({
      ids: selectedIds.value,
      max: selectedIds.value.length,
      force: batchForce.value,
    });
    ElMessage.success(`完成：成功 ${res.ok}，跳过 ${res.skipped}，失败 ${res.failed}`);
    await fetchItems();
  } catch (e) {
    handleError(e, "批量转换失败");
  } finally {
    converting.value = false;
  }
}

async function handleBatchConvert() {
  try {
    await ElMessageBox.confirm(
      `将从库内取最多 ${batchMax.value} 条${filterStatus.value || "全部"}金故事转 gold_chat，继续？`,
      "批量转换",
      { type: "info" },
    );
  } catch {
    return;
  }
  batching.value = true;
  try {
    const res = await batchConvertGoldChat({
      max: batchMax.value,
      status: filterStatus.value || "active",
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

onMounted(fetchItems);
usePageRefresh(fetchItems);
</script>
