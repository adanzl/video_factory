<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchTitles">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" @click="showGenerateDialog = true">AI 生成选题</el-button>
      <el-button
        :disabled="!selectedIds.length"
        :loading="scoring"
        @click="handleScoreSelected"
      >
        打分
      </el-button>
      <el-button
        type="success"
        :disabled="!selectedIds.length"
        :loading="enqueuing"
        @click="openEnqueueDialog(selectedIds)"
      >
        入队生产
      </el-button>
      <el-button
        type="danger"
        :disabled="!selectedIds.length"
        :loading="deleting"
        @click="handleDeleteSelected"
      >
        删除
      </el-button>
      <el-button
        type="warning"
        :loading="cleaningLow"
        @click="showCleanLowDialog = true"
      >
        清理低分
      </el-button>
      <el-select
        v-model="statusFilter"
        placeholder="全部状态"
        clearable
        class="w-36!"
        @change="onFilterChange"
      >
        <el-option label="待打分" value="pending" />
        <el-option label="可入队" value="queued" />
        <el-option label="已淘汰" value="rejected" />
        <el-option label="已入队" value="enqueued" />
      </el-select>
    </div>

    <el-table
      :data="titles"
      stripe
      class="w-full"
      v-loading="loading"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="category" label="分类" width="110" show-overflow-tooltip />
      <el-table-column prop="template" label="模板" width="110" />
      <el-table-column prop="hook" label="钩子" min-width="160" show-overflow-tooltip />
      <el-table-column label="分数" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row.score != null">{{ row.score }}</span>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small" effect="dark">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="60" align="center">
        <template #default="{ row }">
          {{ sourceLabel(row.source) }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <div class="flex items-center gap-2 whitespace-nowrap">
            <el-button
              v-if="row.job_id"
              type="warning"
              link
              size="small"
              @click="goToJob(row.job_id!)"
            >
              任务详情
            </el-button>
            <el-button
              v-if="row.status !== 'enqueued'"
              type="warning"
              link
              size="small"
              @click="openOptimizeDialog(row)"
            >
              优化
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              :loading="scoringId === row.id"
              @click="handleScoreOne(row.id)"
            >
              打分
            </el-button>
            <el-button
              v-if="row.status === 'queued'"
              type="success"
              link
              size="small"
              :loading="enqueuing && pendingEnqueueIds.includes(row.id)"
              @click="openEnqueueDialog([row.id])"
            >
              入队
            </el-button>
            <el-button
              type="default"
              link
              size="small"
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDeleteOne(row)"
            >
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[15, 25, 50]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="fetchTitles"
      @size-change="onPageSizeChange"
    />

    <el-dialog v-model="showGenerateDialog" title="AI 生成选题" width="520px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="类型">
          <el-select v-model="generateMode" @change="onGenerateModeChange">
            <el-option label="历史悬案" value="history_mystery" />
            <el-option label="科学原理" value="science" />
            <el-option label="时事科普" value="current_affairs" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="generateMode === 'custom'" label="大分类">
          <el-select v-model="generateForm.category">
            <el-option
              v-for="cat in topicCatalog"
              :key="cat.id"
              :label="cat.label"
              :value="cat.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="主题">
          <el-input
            v-model="generateForm.theme"
            :placeholder="themePlaceholder"
            maxlength="100"
          />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="generateForm.keywords"
            :placeholder="keywordsPlaceholder"
            maxlength="100"
            clearable
          />
        </el-form-item>
        <el-form-item label="数量">
          <div class="flex items-center gap-2">
            <el-input-number v-model="generateForm.count" :min="1" :max="20" />
            <el-button
              v-for="n in quickGenerateCounts"
              :key="n"
              size="small"
              :type="generateForm.count === n ? 'primary' : 'default'"
              @click="generateForm.count = n"
            >
              {{ n }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="入库">
          <el-switch v-model="generateForm.save" active-text="生成后保存" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="handleGenerate">
          生成
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEnqueueDialog" title="入队生产" width="520px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="选题数量">
          <span class="text-sm text-gray-600">{{ pendingEnqueueIds.length }} 条</span>
        </el-form-item>
        <el-form-item label="执行方式">
          <el-radio-group v-model="enqueueRunMode" class="create-job-run-mode">
            <el-radio value="script">仅文案（默认，第一步）</el-radio>
            <el-radio value="none">仅创建任务，暂不执行</el-radio>
            <el-radio value="full">全流程（文案 → 成片）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEnqueueDialog = false">取消</el-button>
        <el-button type="primary" :loading="enqueuing" @click="confirmEnqueue">
          确认入队
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑选题" width="520px" destroy-on-close>
      <el-form label-width="70px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" type="textarea" :rows="2" maxlength="60" show-word-limit />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category" class="w-full!">
            <el-option label="历史悬案" value="历史悬案" />
            <el-option label="科学原理" value="科学原理" />
            <el-option label="时事相关科普" value="时事相关科普" />
          </el-select>
        </el-form-item>
        <el-form-item label="模板">
          <el-select v-model="editForm.template" class="w-full!">
            <el-option label="误区反问式" value="误区反问式" />
            <el-option label="反差好奇式" value="反差好奇式" />
            <el-option label="悬念钩子式" value="悬念钩子式" />
            <el-option label="未解之谜式" value="未解之谜式" />
            <el-option label="实操避坑式" value="实操避坑式" />
          </el-select>
        </el-form-item>
        <el-form-item label="钩子">
          <el-input v-model="editForm.hook" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showCleanLowDialog" title="清理低分选题" width="480px" destroy-on-close>
      <p class="mb-4 text-sm text-gray-500">
        将删除分数低于标准的选题（不含已入队、未打分）。
      </p>
      <el-form label-width="100px">
        <el-form-item label="低分标准">
          <el-input-number v-model="cleanLowMaxScore" :min="0" :max="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCleanLowDialog = false">取消</el-button>
        <el-button type="warning" :loading="cleaningLow" @click="confirmCleanLow">
          确认清理
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showOptimizeDialog" title="优化选题" width="500px" destroy-on-close>
      <div class="mb-4 rounded-lg bg-gray-50 px-4 py-3">
        <div class="mb-1 text-xs text-gray-400">原标题</div>
        <div class="text-sm font-medium text-gray-700">{{ optimizeForm.title }}</div>
      </div>
      <el-form label-width="88px">
        <el-form-item label="优化方向">
          <el-input
            v-model="optimizeForm.direction"
            type="textarea"
            :rows="8"
            maxlength="200"
            show-word-limit
            placeholder="可选，如：更口语化、加强悬念感、突出反差…"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showOptimizeDialog = false">取消</el-button>
        <el-button type="warning" :loading="optimizingId !== undefined" @click="confirmOptimize">
          开始优化
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteLowScoreTopics,
  deleteTopics,
  enqueueTopics,
  fetchTopicCatalog,
  generateTopics,
  listTitles,
  optimizeTopic,
  scoreTopics,
  updateTopic,
} from "@/api/api-topic";
import type {
  EnqueueRunMode,
  TitleRecord,
  TitleStatus,
  TopicCategory,
} from "@/types/topic";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";

const { handleError } = useErrorHandler();
const router = useRouter();

const titles = ref<TitleRecord[]>([]);
const loading = ref(false);
const statusFilter = ref<string>();
const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("topicPageSize") || "15", 10));
const total = ref(0);
const selectedIds = ref<number[]>([]);

const scoring = ref(false);
const enqueuing = ref(false);
const deleting = ref(false);
const cleaningLow = ref(false);
const generating = ref(false);
const scoringId = ref<number>();
const optimizingId = ref<number>();
const editing = ref(false);
const showEditDialog = ref(false);
const editForm = reactive({
  id: 0,
  title: "",
  category: "",
  template: "",
  hook: "",
});

const showGenerateDialog = ref(false);
const showEnqueueDialog = ref(false);
const showCleanLowDialog = ref(false);
const showOptimizeDialog = ref(false);
const optimizeForm = reactive({
  id: 0,
  title: "",
  direction: "",
});
const cleanLowMaxScore = ref(85);
const pendingEnqueueIds = ref<number[]>([]);
const enqueueRunMode = ref<EnqueueRunMode>("script");
const generateMode = ref("history_mystery");
const topicCatalog = ref<TopicCategory[]>([]);

const MODE_CATEGORY: Record<string, string> = {
  history_mystery: "历史悬案",
  science: "科学原理",
  current_affairs: "时事相关科普",
};

const quickGenerateCounts = [1, 5, 10] as const;

const generateForm = reactive({
  category: "科学原理",
  theme: "中国历史悬案",
  keywords: "",
  count: 5,
  save: true,
});

const activeCategoryId = computed(() => {
  if (generateMode.value === "custom") {
    return generateForm.category;
  }
  return MODE_CATEGORY[generateMode.value] ?? "";
});

const activeCategory = computed(() =>
  topicCatalog.value.find((item) => item.id === activeCategoryId.value)
);

const themePlaceholder = computed(() => {
  if (generateMode.value === "custom") {
    return "如：日常用水用电小常识";
  }
  return activeCategory.value?.default_theme || "可选，留空用分类默认";
});

const keywordsPlaceholder = computed(
  () => activeCategory.value?.keywords_hint || "可选，逗号分隔"
);

const onGenerateModeChange = (mode: string) => {
  generateForm.keywords = "";
  if (mode === "history_mystery") {
    generateForm.theme = "中国历史悬案";
    generateForm.count = 5;
  } else if (mode === "science") {
    generateForm.theme = "日常科学冷知识";
    generateForm.count = 5;
  } else if (mode === "current_affairs") {
    generateForm.theme = "";
    generateForm.count = 5;
  } else {
    generateForm.theme = "";
    generateForm.category = "科学原理";
  }
};

const loadTopicCatalog = async () => {
  try {
    const result = await fetchTopicCatalog();
    topicCatalog.value = result.categories ?? [];
  } catch (error) {
    handleError(error, "加载选题分类失败");
  }
};

const statusLabel = (status: TitleStatus) => {
  switch (status) {
    case "pending":
      return "待打分";
    case "queued":
      return "可入队";
    case "rejected":
      return "已淘汰";
    case "enqueued":
      return "已入队";
    default:
      return status;
  }
};

const statusTagType = (status: TitleStatus) => {
  switch (status) {
    case "queued":
      return "warning";
    case "rejected":
      return "danger";
    case "enqueued":
      return "primary";
    default:
      return "info";
  }
};

const sourceLabel = (source?: string) => {
  switch (source) {
    case "llm":
      return "AI";
    default:
      return "手动";
  }
};

const updateTotal = (count: number) => {
  if (count < pageSize.value) {
    total.value = (page.value - 1) * pageSize.value + count;
  } else {
    total.value = page.value * pageSize.value + 1;
  }
};

const fetchTitles = async () => {
  loading.value = true;
  try {
    const list = await listTitles({
      status: statusFilter.value || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    });
    titles.value = list;
    updateTotal(list.length);
  } catch (error) {
    handleError(error, "加载选题列表失败");
  } finally {
    loading.value = false;
  }
};

const onFilterChange = () => {
  page.value = 1;
  fetchTitles();
};

const onPageSizeChange = () => {
  page.value = 1;
  localStorage.setItem("topicPageSize", String(pageSize.value));
  fetchTitles();
};

const onSelectionChange = (rows: TitleRecord[]) => {
  selectedIds.value = rows.map(row => row.id);
};

const goToJob = (jobId: number) => {
  void router.push({ path: "/jobs", query: { id: String(jobId) } });
};

const handleScoreSelected = async () => {
  scoring.value = true;
  try {
    const result = await scoreTopics(selectedIds.value);
    ElMessage.success(`已打分 ${result.count} 条`);
    await fetchTitles();
  } catch (error) {
    handleError(error, "打分失败");
  } finally {
    scoring.value = false;
  }
};

const openOptimizeDialog = (row: TitleRecord) => {
  optimizeForm.id = row.id;
  optimizeForm.title = row.title;
  optimizeForm.direction = "同一题材、同一核心知识点或事件，只润色标题与 hook，不得另起新题。标题表述须与原版不同，但读者应一眼看出是同一主题。";
  showOptimizeDialog.value = true;
};

const confirmOptimize = async () => {
  const id = optimizeForm.id;
  const direction = optimizeForm.direction.trim() || undefined;
  showOptimizeDialog.value = false;
  optimizingId.value = id;
  try {
    const result = await optimizeTopic(id, direction);
    ElMessage.success(`已优化：${result.title.title}`);
    await fetchTitles();
  } catch (error) {
    handleError(error, "优化失败");
  } finally {
    optimizingId.value = undefined;
  }
};

const handleScoreOne = async (id: number) => {
  scoringId.value = id;
  try {
    await scoreTopics([id]);
    ElMessage.success("打分完成");
    await fetchTitles();
  } catch (error) {
    handleError(error, "打分失败");
  } finally {
    scoringId.value = undefined;
  }
};

const openEnqueueDialog = (ids: number[]) => {
  if (!ids.length) {
    return;
  }
  pendingEnqueueIds.value = ids;
  enqueueRunMode.value = "script";
  showEnqueueDialog.value = true;
};

const enqueueModeLabel = (mode: EnqueueRunMode) => {
  switch (mode) {
    case "script":
      return "已创建并开始文案生成";
    case "full":
      return "已创建并开始全流程";
    default:
      return "已创建任务";
  }
};

const confirmEnqueue = async () => {
  enqueuing.value = true;
  try {
    const result = await enqueueTopics({
      ids: pendingEnqueueIds.value,
      run_mode: enqueueRunMode.value,
    });
    ElMessage.success(`${enqueueModeLabel(result.run_mode)}，共 ${result.count} 个`);
    showEnqueueDialog.value = false;
    await fetchTitles();
  } catch (error) {
    handleError(error, "入队失败");
  } finally {
    enqueuing.value = false;
  }
};

const handleDeleteSelected = async () => {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条选题吗？`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  deleting.value = true;
  try {
    await deleteTopics(selectedIds.value);
    ElMessage.success("删除成功");
    if (titles.value.length === selectedIds.value.length && page.value > 1) {
      page.value -= 1;
    }
    await fetchTitles();
  } catch (error) {
    handleError(error, "删除失败");
  } finally {
    deleting.value = false;
  }
};

const handleDeleteOne = async (row: TitleRecord) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」吗？`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  try {
    await deleteTopics([row.id]);
    ElMessage.success("删除成功");
    if (titles.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await fetchTitles();
  } catch (error) {
    handleError(error, "删除失败");
  }
};

const confirmCleanLow = async () => {
  cleaningLow.value = true;
  try {
    const result = await deleteLowScoreTopics(cleanLowMaxScore.value);
    if (result.deleted === 0) {
      ElMessage.info(`没有分数低于 ${result.max_score} 的选题`);
    } else {
      ElMessage.success(`已清理 ${result.deleted} 条低分选题`);
    }
    showCleanLowDialog.value = false;
    if (titles.value.length <= result.deleted && page.value > 1) {
      page.value -= 1;
    }
    await fetchTitles();
  } catch (error) {
    handleError(error, "清理低分失败");
  } finally {
    cleaningLow.value = false;
  }
};

const openEditDialog = (row: TitleRecord) => {
  editForm.id = row.id;
  editForm.title = row.title;
  editForm.category = row.category || "";
  editForm.template = row.template || "";
  editForm.hook = row.hook || "";
  showEditDialog.value = true;
};

const confirmEdit = async () => {
  if (!editForm.title.trim()) {
    ElMessage.warning("标题不能为空");
    return;
  }
  editing.value = true;
  try {
    await updateTopic({ id: editForm.id, title: editForm.title, category: editForm.category || undefined, template: editForm.template || undefined, hook: editForm.hook || undefined });
    ElMessage.success("已保存");
    showEditDialog.value = false;
    await fetchTitles();
  } catch (error) {
    handleError(error, "保存失败");
  } finally {
    editing.value = false;
  }
};

const handleGenerate = async () => {
  if (!generateForm.theme.trim() && !generateForm.keywords.trim()) {
    ElMessage.warning("请填写主题或关键词");
    return;
  }

  const category = activeCategoryId.value;
  if (!category) {
    ElMessage.warning("请选择大分类");
    return;
  }

  generating.value = true;
  try {
    const result = await generateTopics({
      category,
      theme: generateForm.theme.trim() || undefined,
      keywords: generateForm.keywords.trim() || undefined,
      count: generateForm.count,
      save: generateForm.save,
    });
    if (generateForm.save && "added" in result) {
      ElMessage.success(`已生成并入库 ${result.count} 条，跳过 ${result.skipped} 条重复`);
    } else if ("topics" in result) {
      ElMessage.success(`已生成 ${result.count} 条（未入库）`);
    }
    showGenerateDialog.value = false;
    onGenerateModeChange(generateMode.value);
    await fetchTitles();
  } catch (error) {
    handleError(error, "生成选题失败");
  } finally {
    generating.value = false;
  }
};


onMounted(() => {
  loadTopicCatalog();
  fetchTitles();
});
</script>
