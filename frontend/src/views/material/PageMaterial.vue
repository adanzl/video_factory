<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchMaterials">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" @click="showUploadDialog = true">上传素材</el-button>
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
      :data="materials"
      stripe
      class="w-full"
      v-loading="loading"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column label="预览" width="100">
        <template #default="{ row }">
          <img
            v-if="thumbUrl(row)"
            :src="thumbUrl(row)"
            alt=""
            class="h-16 w-9 rounded border border-gray-200 object-cover"
          />
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="时长" width="90">
        <template #default="{ row }">
          {{ row.duration_sec != null ? formatMediaDuration(row.duration_sec) : "-" }}
        </template>
      </el-table-column>
      <el-table-column label="分辨率" width="110">
        <template #default="{ row }">
          <span v-if="row.width && row.height">{{ row.width }}×{{ row.height }}</span>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ formatFileSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button type="success" link size="small" @click="openCreateJobDialog(row)">
            发起任务
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="fetchMaterials"
      @size-change="onPageSizeChange"
    />

    <el-dialog v-model="showUploadDialog" title="上传视频素材" width="480px" destroy-on-close>
      <el-form label-width="72px">
        <el-form-item label="视频文件" required>
          <input ref="fileInputRef" type="file" accept="video/*,.mp4,.mov,.webm,.mkv" @change="onFileChange" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="uploadName" placeholder="可选，默认取文件名" clearable />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadNote" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!uploadFile" @click="handleUpload">
          上传
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showCreateJobDialog" title="从素材发起任务" width="520px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="素材">
          <span>{{ createJobMaterial?.name }} (#{{ createJobMaterial?.id }})</span>
        </el-form-item>
        <el-form-item label="视频标题" required>
          <el-input v-model="createJobTitle" placeholder="成片标题" clearable />
        </el-form-item>
        <el-form-item label="文案来源">
          <el-radio-group v-model="createJobScriptMode">
            <el-radio value="ai">AI 生成</el-radio>
            <el-radio value="manual">手动粘贴</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createJobScriptMode === 'manual'" label="口播文案" required>
          <el-input v-model="createJobNarration" type="textarea" :rows="6" placeholder="完整口播，至少 200 字" />
        </el-form-item>
        <el-form-item label="跳过投稿">
          <el-switch v-model="createJobSkipPublish" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateJobDialog = false">取消</el-button>
        <el-button type="primary" :loading="creatingJob" @click="handleCreateJob">创建并入队</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createJobFromMaterial,
  deleteMaterial,
  listMaterials,
  uploadMaterial,
} from "@/api/api-materials";
import type { MaterialRecord } from "@/types/material";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import { formatFileSize, formatMediaDuration, getMediaFileUrl } from "@/utils/media";

const { handleError } = useErrorHandler();

const materials = ref<MaterialRecord[]>([]);
const loading = ref(false);
const deleting = ref(false);
const uploading = ref(false);
const creatingJob = ref(false);
const selectedIds = ref<number[]>([]);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const showUploadDialog = ref(false);
const uploadFile = ref<File | null>(null);
const uploadName = ref("");
const uploadNote = ref("");
const fileInputRef = ref<HTMLInputElement | null>(null);

const showCreateJobDialog = ref(false);
const createJobMaterial = ref<MaterialRecord | null>(null);
const createJobTitle = ref("");
const createJobScriptMode = ref<"ai" | "manual">("ai");
const createJobNarration = ref("");
const createJobSkipPublish = ref(true);

const thumbUrl = (row: MaterialRecord) =>
  row.thumbnail_path ? getMediaFileUrl(row.thumbnail_path) : "";

const onSelectionChange = (rows: MaterialRecord[]) => {
  selectedIds.value = rows.map(row => row.id);
};

const fetchMaterials = async () => {
  loading.value = true;
  try {
    const offset = (page.value - 1) * pageSize.value;
    const rows = await listMaterials({ limit: pageSize.value, offset });
    materials.value = rows;
    total.value = rows.length < pageSize.value ? offset + rows.length : offset + pageSize.value + 1;
  } catch (error) {
    handleError(error, "加载素材失败");
  } finally {
    loading.value = false;
  }
};

const onPageSizeChange = () => {
  page.value = 1;
  void fetchMaterials();
};

const onFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  uploadFile.value = input.files?.[0] ?? null;
};

const handleUpload = async () => {
  if (!uploadFile.value) {
    return;
  }
  uploading.value = true;
  try {
    await uploadMaterial({
      file: uploadFile.value,
      name: uploadName.value || undefined,
      note: uploadNote.value || undefined,
    });
    ElMessage.success("上传成功");
    showUploadDialog.value = false;
    uploadFile.value = null;
    uploadName.value = "";
    uploadNote.value = "";
    if (fileInputRef.value) {
      fileInputRef.value.value = "";
    }
    await fetchMaterials();
  } catch (error) {
    handleError(error, "上传失败");
  } finally {
    uploading.value = false;
  }
};

const handleDeleteSelected = async () => {
  if (!selectedIds.value.length) {
    return;
  }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条素材吗？`, "确认删除", {
      type: "warning",
    });
  } catch {
    return;
  }
  deleting.value = true;
  try {
    for (const id of selectedIds.value) {
      await deleteMaterial(id);
    }
    ElMessage.success("已删除");
    selectedIds.value = [];
    await fetchMaterials();
  } catch (error) {
    handleError(error, "删除失败");
  } finally {
    deleting.value = false;
  }
};

const openCreateJobDialog = (row: MaterialRecord) => {
  createJobMaterial.value = row;
  createJobTitle.value = row.name;
  createJobScriptMode.value = "ai";
  createJobNarration.value = "";
  createJobSkipPublish.value = true;
  showCreateJobDialog.value = true;
};

const handleCreateJob = async () => {
  if (!createJobMaterial.value || !createJobTitle.value.trim()) {
    ElMessage.warning("请填写标题");
    return;
  }
  creatingJob.value = true;
  try {
    const job = await createJobFromMaterial({
      material_id: createJobMaterial.value.id,
      title: createJobTitle.value.trim(),
      script_mode: createJobScriptMode.value,
      narration: createJobScriptMode.value === "manual" ? createJobNarration.value : undefined,
      skip_publish: createJobSkipPublish.value,
    });
    ElMessage.success(`任务 #${job.id} 已创建并入队，请在任务队列查看`);
    showCreateJobDialog.value = false;
  } catch (error) {
    handleError(error, "创建任务失败");
  } finally {
    creatingJob.value = false;
  }
};

onMounted(() => {
  void fetchMaterials();
});
</script>
