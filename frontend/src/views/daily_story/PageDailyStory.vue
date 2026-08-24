<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchStories">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" @click="showGenerateDialog = true">生成故事</el-button>
      <el-select
        v-model="filterStoryType"
        placeholder="矛盾类型"
        clearable
        class="w-30!"
        @change="onFilterStoryTypeChange"
      >
        <el-option
          v-for="opt in DAILY_STORY_TYPE_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-input
        v-model="filterKey"
        placeholder="搜索关键字"
        clearable
        class="w-48!"
        @keyup.enter="onSearchKey"
        @clear="onSearchKey"
      />
      <el-button type="primary" @click="onSearchKey">搜索</el-button>
      <el-radio-group v-model="filterHasJob" @change="onFilterHasJobChange">
        <el-radio-button value="">不限</el-radio-button>
        <el-radio-button value="yes">有任务</el-radio-button>
        <el-radio-button value="no">无任务</el-radio-button>
      </el-radio-group>
      <el-button
        type="danger"
        :disabled="!selectedIds.length"
        :loading="deleting"
        @click="handleDeleteSelected"
      >
        删除
      </el-button>
    </div>

    <el-table
      :data="stories"
      stripe
      class="w-full"
      v-loading="loading"
      @selection-change="onSelectionChange"
      @row-dblclick="viewStory"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="theme" label="主题" min-width="150" show-overflow-tooltip />
      <el-table-column label="关键字" width="100" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.key || row.story?.key || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="矛盾类型" width="110" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDailyStoryType(row.story_type) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'processing'" type="warning" size="small">生成中</el-tag>
          <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">失败</el-tag>
          <el-tag v-else type="success" size="small">就绪</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="设定" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.story?.setting || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="对话" width="60" align="center">
        <template #default="{ row }">
          {{ row.story?.dialogue?.length || 0 }}
        </template>
      </el-table-column>
      <el-table-column label="评价" width="60" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.story?.quality?.score != null"
            size="small"
            effect="dark"
            :type="scoreTagType(row.story.quality.score)"
            class="inline-flex! w-8! justify-center! px-0! tabular-nums"
          >
            {{ row.story.quality.score }}
          </el-tag>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="字数" width="60" align="center">
        <template #default="{ row }">
          {{ calcWordCount(row.story?.dialogue) }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewStory(row)">查看</el-button>
          <el-button v-if="row.job_id" type="primary" link size="small" @click="gotoJob(row)">任务详情</el-button>
          <el-button type="danger" link size="small" @click="handleDeleteOne(row.id)">删除</el-button>
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

    <DailyStoryDetail
      v-model="showDetailDialog"
      :story="currentStory"
      @updated="onStoryUpdated"
      @closed="onDetailClosed"
    />
    <CreateStory v-model="showGenerateDialog" @created="fetchStories" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, onDeactivated } from "vue";
import { useRouter } from "vue-router";
import { usePageRefresh } from "@/stores/app";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import DailyStoryDetail from "@/views/daily_story/dialogs/DailyStoryDetail.vue";
import CreateStory from "@/views/daily_story/dialogs/CreateStory.vue";
import {
  listDailyStories,
  deleteDailyStories,
  DAILY_STORY_TYPE_OPTIONS,
  formatDailyStoryType,
  type DailyStoryRecord,
  type DialogueLine,
} from "@/api/api-daily-story";

const { handleError } = useErrorHandler();
const router = useRouter();

const stories = ref<DailyStoryRecord[]>([]);
const loading = ref(false);
const deleting = ref(false);
const selectedIds = ref<number[]>([]);
const showDetailDialog = ref(false);
const currentStory = ref<DailyStoryRecord | null>(null);

const showGenerateDialog = ref(false);

const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("dailyStoryPageSize") || "15", 10));
const total = ref(0);
const filterStoryType = ref<string>("");
const filterKey = ref("");
/** 已生效的搜索词（回车/点搜索后才带入请求） */
const appliedKey = ref("");
/** ""=不限, yes=有任务, no=无任务 */
const filterHasJob = ref<"" | "yes" | "no">("");

function onFilterStoryTypeChange() {
  page.value = 1;
  selectedIds.value = [];
  void fetchStories();
}

function onSearchKey() {
  appliedKey.value = filterKey.value.trim();
  page.value = 1;
  selectedIds.value = [];
  void fetchStories();
}

function onFilterHasJobChange() {
  page.value = 1;
  selectedIds.value = [];
  void fetchStories();
}

const POLL_INTERVAL_MS = 3000;
let pollTimer: ReturnType<typeof setInterval> | null = null;

function scoreTagType(score: number): "success" | "warning" | "danger" {
  if (score >= 85) return "success";
  if (score >= 61) return "warning";
  return "danger";
}

function stopPolling() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPollingIfNeeded() {
  const hasProcessing = stories.value.some((s) => s.status === "processing");
  if (!hasProcessing) {
    stopPolling();
    return;
  }
  if (pollTimer != null) return;
  pollTimer = setInterval(() => {
    void fetchStories({ quiet: true });
  }, POLL_INTERVAL_MS);
}

async function fetchStories(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet === true;
  if (!quiet) loading.value = true;
  try {
    const res = await listDailyStories({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
      ...(filterStoryType.value ? { story_type: filterStoryType.value } : {}),
      ...(appliedKey.value ? { key: appliedKey.value } : {}),
      ...(filterHasJob.value === "yes"
        ? { has_job: true }
        : filterHasJob.value === "no"
          ? { has_job: false }
          : {}),
    });
    stories.value = res.items;
    total.value = res.total;
    if (currentStory.value && showDetailDialog.value) {
      const latest = res.items.find((s) => s.id === currentStory.value?.id);
      if (latest) currentStory.value = latest;
    }
    startPollingIfNeeded();
  } catch (e) {
    if (!quiet) handleError(e, "加载故事列表失败");
  } finally {
    if (!quiet) loading.value = false;
  }
}

function onPageChange() {
  selectedIds.value = [];
  fetchStories();
}

function onStoryUpdated(newStory?: DailyStoryRecord) {
  void fetchStories({ quiet: true });
  if (newStory) {
    currentStory.value = newStory;
  }
}

function onDetailClosed() {
  void fetchStories({ quiet: true });
}

function onPageSizeChange() {
  page.value = 1;
  selectedIds.value = [];
  localStorage.setItem("dailyStoryPageSize", String(pageSize.value));
  fetchStories();
}

function onSelectionChange(rows: DailyStoryRecord[]) {
  selectedIds.value = rows.map((r) => r.id);
}

function viewStory(row: DailyStoryRecord) {
  currentStory.value = row;
  showDetailDialog.value = true;
}

async function gotoJob(row: DailyStoryRecord) {
  if (!row.job_id) {
    ElMessage.info("该故事还没有关联的任务");
    return;
  }
  router.push({ path: "/jobs", query: { id: String(row.job_id) } });
}

async function handleDeleteOne(id: number) {
  try {
    await ElMessageBox.confirm("确定删除这条故事？", "确认", { type: "warning" });
    await deleteDailyStories([id]);
    ElMessage.success("已删除");
    await fetchStories();
  } catch (e) {
    if (e !== "cancel") handleError(e, "删除失败");
  }
}

async function handleDeleteSelected() {
  if (!selectedIds.value.length) return;
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条故事？`, "确认", {
      type: "warning",
    });
    deleting.value = true;
    await deleteDailyStories(selectedIds.value);
    ElMessage.success("已删除");
    selectedIds.value = [];
    await fetchStories();
  } catch (e) {
    if (e !== "cancel") handleError(e, "删除失败");
  } finally {
    deleting.value = false;
  }
}

function calcWordCount(dialogue?: DialogueLine[]): number {
  if (!dialogue) return 0;
  return dialogue.reduce((sum, d) => sum + (d.line?.length || 0), 0);
}

onMounted(fetchStories);
usePageRefresh(fetchStories);
onDeactivated(stopPolling);
onUnmounted(stopPolling);
</script>
