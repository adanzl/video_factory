<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <el-button type="primary" :disabled="loading" @click="fetchMaterials">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button type="primary" @click="showUploadDialog = true">上传音频</el-button>
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
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="时长" width="90">
        <template #default="{ row }">
          {{ row.duration_sec ? formatMediaDuration(row.duration_sec) : "-" }}
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">
          {{ row.size_bytes ? formatFileSize(row.size_bytes) : "-" }}
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="200" show-overflow-tooltip />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ row.created_at ? formatDateTime(row.created_at) : "-" }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openPlayDialog(row)">播放</el-button>
          <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上传弹窗 -->
    <el-dialog v-model="showUploadDialog" title="上传音频" width="480">
      <el-form label-width="80">
        <el-form-item label="名称">
          <el-input v-model="uploadName" placeholder="留空自动使用文件名" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadNote" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="文件">
          <input ref="fileInputRef" type="file" accept="audio/*" @change="onFileChange" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!uploadFile" @click="handleUpload">
          上传
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="showEditDialog" title="编辑音频" width="480">
      <el-form label-width="80">
        <el-form-item label="名称">
          <el-input v-model="editName" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editNote" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="文件">
          <input type="file" accept="audio/*" @change="onEditFileChange" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 播放弹窗 -->
    <el-dialog v-model="showPlayDialog" title="播放音频" width="600">
      <div class="flex flex-col items-center gap-4 py-4">
        <p class="text-lg font-medium">{{ playMaterial?.name }}</p>
        <audio v-if="playAudioUrl" :src="playAudioUrl" controls class="w-full" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  listMaterialAudios,
  uploadMaterialAudio,
  deleteMaterialAudio,
  editMaterialAudio,
} from "@/api/api-materials";
import type { MaterialAudioRecord } from "@/types/material-audio";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import { formatFileSize, formatMediaDuration, getMediaFileUrl } from "@/utils/media";

const { handleError } = useErrorHandler();

const materials = ref<MaterialAudioRecord[]>([]);
const loading = ref(false);
const deleting = ref(false);
const selectedIds = ref<number[]>([]);

// upload
const showUploadDialog = ref(false);
const uploading = ref(false);
const uploadName = ref("");
const uploadNote = ref("");
const uploadFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

// edit
const showEditDialog = ref(false);
const editMaterialRow = ref<MaterialAudioRecord | null>(null);
const editName = ref("");
const editNote = ref("");
const editFile = ref<File | null>(null);

// play
const showPlayDialog = ref(false);
const playMaterial = ref<MaterialAudioRecord | null>(null);

const audioUrl = (row: MaterialAudioRecord) =>
  row.file_path ? getMediaFileUrl(row.file_path) : "";

const playAudioUrl = computed(() =>
  playMaterial.value?.file_path ? getMediaFileUrl(playMaterial.value.file_path) : ""
);

const onSelectionChange = (rows: MaterialAudioRecord[]) => {
  selectedIds.value = rows.map(row => row.id);
};

const fetchMaterials = async () => {
  loading.value = true;
  try {
    const rows = await listMaterialAudios();
    materials.value = rows;
  } catch (error) {
    handleError(error, "加载音频素材失败");
  } finally {
    loading.value = false;
  }
};

const onFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  uploadFile.value = input.files?.[0] ?? null;
};

const onEditFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  editFile.value = input.files?.[0] ?? null;
};

const handleUpload = async () => {
  if (!uploadFile.value) return;
  uploading.value = true;
  try {
    await uploadMaterialAudio({
      file: uploadFile.value,
      name: uploadName.value || undefined,
      note: uploadNote.value || undefined,
    });
    ElMessage.success("上传成功");
    showUploadDialog.value = false;
    uploadFile.value = null;
    uploadName.value = "";
    uploadNote.value = "";
    if (fileInputRef.value) fileInputRef.value.value = "";
    await fetchMaterials();
  } catch (error) {
    handleError(error, "上传失败");
  } finally {
    uploading.value = false;
  }
};

const openEditDialog = (row: MaterialAudioRecord) => {
  editMaterialRow.value = row;
  editName.value = row.name;
  editNote.value = row.note ?? "";
  editFile.value = null;
  showEditDialog.value = true;
};

const handleEdit = async () => {
  if (!editMaterialRow.value || !editName.value.trim()) return;
  editing.value = true;
  try {
    await editMaterialAudio({
      id: editMaterialRow.value.id,
      name: editName.value.trim(),
      note: editNote.value || undefined,
      file: editFile.value || undefined,
    });
    ElMessage.success("保存成功");
    showEditDialog.value = false;
    await fetchMaterials();
  } catch (error) {
    handleError(error, "保存失败");
  } finally {
    editing.value = false;
  }
};

const editing = ref(false);

const handleDelete = async (row: MaterialAudioRecord) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」吗？`, "确认删除", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteMaterialAudio(row.id);
    ElMessage.success("已删除");
    await fetchMaterials();
  } catch (error) {
    handleError(error, "删除失败");
  }
};

const handleDeleteSelected = async () => {
  if (!selectedIds.value.length) return;
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条音频吗？`, "确认删除", {
      type: "warning",
    });
  } catch {
    return;
  }
  deleting.value = true;
  try {
    for (const id of selectedIds.value) {
      await deleteMaterialAudio(id);
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

const openPlayDialog = (row: MaterialAudioRecord) => {
  if (!audioUrl(row)) return;
  playMaterial.value = row;
  showPlayDialog.value = true;
};

onMounted(() => {
  void fetchMaterials();
});
</script>
