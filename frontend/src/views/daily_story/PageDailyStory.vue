<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchStories">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" @click="showGenerateDialog = true">生成故事</el-button>
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
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="theme" label="主题" min-width="150" show-overflow-tooltip />
      <el-table-column label="场景标题" width="120">
        <template #default="{ row }">
          {{ row.story?.scene_title || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="设定" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.story?.setting || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="对话轮数" width="90" align="center">
        <template #default="{ row }">
          {{ row.story?.dialogue?.length || 0 }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="dark">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewStory(row)">查看</el-button>
          <el-button type="danger" link size="small" @click="handleDeleteOne(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <DailyStoryDetail v-model="showDetailDialog" :story="currentStory" @updated="fetchStories" />
    <CreateStory v-model="showGenerateDialog" @created="fetchStories" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import DailyStoryDetail from "@/views/daily_story/dialogs/DailyStoryDetail.vue";
import CreateStory from "@/views/daily_story/dialogs/CreateStory.vue";
import {
  listDailyStories,
  deleteDailyStories,
  type DailyStoryRecord,
} from "@/api/api-daily-story";

const { handleError } = useErrorHandler();

const stories = ref<DailyStoryRecord[]>([]);
const loading = ref(false);
const deleting = ref(false);
const selectedIds = ref<number[]>([]);
const showDetailDialog = ref(false);
const currentStory = ref<DailyStoryRecord | null>(null);

const showGenerateDialog = ref(false);

async function fetchStories() {
  loading.value = true;
  try {
    stories.value = await listDailyStories();
  } catch (e) {
    handleError(e, "加载故事列表失败");
  } finally {
    loading.value = false;
  }
}

function onSelectionChange(rows: DailyStoryRecord[]) {
  selectedIds.value = rows.map((r) => r.id);
}

function viewStory(row: DailyStoryRecord) {
  currentStory.value = row;
  showDetailDialog.value = true;
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

onMounted(fetchStories);
</script>
