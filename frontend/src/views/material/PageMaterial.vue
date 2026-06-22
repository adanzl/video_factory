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
      <el-table-column label="预览" width="88">
        <template #default="{ row }">
          <el-image
            v-if="thumbUrl(row)"
            :src="thumbUrl(row)"
            :preview-src-list="[thumbUrl(row)]"
            fit="contain"
            preview-teleported
            class="block size-16 cursor-pointer overflow-hidden rounded border border-gray-200 bg-black [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
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
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <div class="flex items-center gap-1 whitespace-nowrap">
            <el-button
              type="primary"
              link
              size="small"
              :disabled="!videoUrl(row)"
              @click="openPlayDialog(row)"
            >
              播放
            </el-button>
            <el-button type="primary" link size="small" @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-button type="success" link size="small" @click="openCreateJobDialog(row)">
              发起任务
            </el-button>
            <el-button
              v-if="row.job_id"
              type="warning"
              link
              size="small"
              @click="goToJob(row.job_id!)"
            >
              跳转任务
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 15]"
      layout="sizes, prev, pager, next"
      class="mt-4 justify-start"
      @current-change="fetchMaterials"
      @size-change="onPageSizeChange"
    />

    <el-dialog v-model="showUploadDialog" title="上传视频素材" width="480px" destroy-on-close>
      <el-form label-width="90px">
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

    <el-dialog v-model="showEditDialog" title="编辑素材" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="素材 ID">
          <span>{{ editMaterialRow?.id }}</span>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="editName" placeholder="素材名称" clearable />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editNote" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
        <el-form-item label="视频文件">
          <input
            ref="editFileInputRef"
            type="file"
            accept="video/*,.mp4,.mov,.webm,.mkv"
            @change="onEditFileChange"
          />
          <p v-if="editMaterialRow?.file_path" class="mt-1 text-xs text-gray-500">
            不选文件则保留当前视频；更换后已关联任务需重新执行「基底准备」才会更新成片基底。
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" :disabled="!editName.trim()" @click="handleEdit">
          保存
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
        <el-form-item label="执行方式">
          <el-radio-group v-model="createJobRunMode" class="create-job-run-mode">
            <el-radio value="prepare">仅基底（默认，第一步）</el-radio>
            <el-radio value="none">仅创建任务，暂不执行</el-radio>
            <el-radio value="full">全流程（基底 → 成片）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateJobDialog = false">取消</el-button>
        <el-button type="primary" :loading="creatingJob" @click="handleCreateJob">确认创建</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showPlayDialog"
      :title="playMaterial ? `${playMaterial.name} (#${playMaterial.id})` : '视频预览'"
      :width="playDialogWidth"
      destroy-on-close
      @closed="onPlayDialogClosed"
    >
      <div v-if="playVideoUrl" class="flex justify-center">
        <div
          class="overflow-hidden rounded-lg border border-gray-200 bg-black"
          :style="playBoxStyle"
        >
          <video
            :key="playVideoUrl"
            class="block h-full w-full object-contain bg-black"
            :src="playVideoUrl"
            controls
            autoplay
            playsinline
            preload="metadata"
            @loadedmetadata="onPlayVideoMetadata"
          />
        </div>
      </div>
      <div v-else class="py-8 text-center text-sm text-gray-400">无法加载视频</div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createJobFromMaterial,
  deleteMaterial,
  editMaterial,
  listMaterials,
  uploadMaterial,
} from "@/api/api-materials";
import type { MaterialJobRunMode, MaterialRecord } from "@/types/material";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { formatDateTime } from "@/utils/date";
import { formatFileSize, formatMediaDuration, getMediaFileUrl } from "@/utils/media";

const router = useRouter();
const { handleError } = useErrorHandler();

const materials = ref<MaterialRecord[]>([]);
const loading = ref(false);
const deleting = ref(false);
const uploading = ref(false);
const editing = ref(false);
const creatingJob = ref(false);
const selectedIds = ref<number[]>([]);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);

const showUploadDialog = ref(false);
const uploadFile = ref<File | null>(null);
const uploadName = ref("");
const uploadNote = ref("");
const fileInputRef = ref<HTMLInputElement | null>(null);

const showEditDialog = ref(false);
const editMaterialRow = ref<MaterialRecord | null>(null);
const editName = ref("");
const editNote = ref("");
const editFile = ref<File | null>(null);
const editFileInputRef = ref<HTMLInputElement | null>(null);

const showCreateJobDialog = ref(false);
const createJobMaterial = ref<MaterialRecord | null>(null);
const createJobTitle = ref("");
const createJobScriptMode = ref<"ai" | "manual">("ai");
const createJobNarration = ref("");
const createJobSkipPublish = ref(true);
const createJobRunMode = ref<MaterialJobRunMode>("prepare");

const showPlayDialog = ref(false);
const playMaterial = ref<MaterialRecord | null>(null);
const playVideoMeta = ref<{ width: number; height: number } | null>(null);

const PLAY_MAX_VIEWPORT_RATIO = 0.7;
const PLAY_MAX_WIDTH_PX = 800;

const playVideoUrl = computed(() =>
  playMaterial.value?.file_path ? getMediaFileUrl(playMaterial.value.file_path) : ""
);

const playVideoDimensions = computed(() => {
  const material = playMaterial.value;
  const width = material?.width ?? playVideoMeta.value?.width;
  const height = material?.height ?? playVideoMeta.value?.height;
  if (width && height && width > 0 && height > 0) {
    return { width, height };
  }
  return null;
});

const playBoxStyle = computed(() => {
  const dims = playVideoDimensions.value;
  if (!dims) {
    return { width: "100%", maxWidth: "420px", aspectRatio: "16 / 9" };
  }

  const ratio = dims.width / dims.height;
  const maxH = (typeof window !== "undefined" ? window.innerHeight : 800) * PLAY_MAX_VIEWPORT_RATIO;
  const maxW = Math.min(
    PLAY_MAX_WIDTH_PX,
    typeof window !== "undefined" ? window.innerWidth * 0.9 : PLAY_MAX_WIDTH_PX
  );

  let boxW: number;
  let boxH: number;
  if (ratio >= 1) {
    boxW = Math.min(maxW, maxH * ratio);
    boxH = boxW / ratio;
  } else {
    boxH = Math.min(maxH, maxW / ratio);
    boxW = boxH * ratio;
  }

  return {
    width: `${Math.round(boxW)}px`,
    height: `${Math.round(boxH)}px`,
  };
});

const playDialogWidth = computed(() => {
  const style = playBoxStyle.value;
  if (typeof style.width === "string" && style.width.endsWith("px")) {
    return `${parseInt(style.width, 10) + 48}px`;
  }
  return "468px";
});

const onPlayVideoMetadata = (event: Event) => {
  const video = event.target as HTMLVideoElement;
  if (!video.videoWidth || !video.videoHeight) {
    return;
  }
  if (playMaterial.value?.width && playMaterial.value?.height) {
    return;
  }
  playVideoMeta.value = { width: video.videoWidth, height: video.videoHeight };
};

const onPlayDialogClosed = () => {
  playMaterial.value = null;
  playVideoMeta.value = null;
};

const thumbUrl = (row: MaterialRecord) =>
  row.thumbnail_path ? getMediaFileUrl(row.thumbnail_path) : "";

const videoUrl = (row: MaterialRecord) =>
  row.file_path ? getMediaFileUrl(row.file_path) : "";

const openPlayDialog = (row: MaterialRecord) => {
  if (!videoUrl(row)) {
    return;
  }
  playMaterial.value = row;
  showPlayDialog.value = true;
};

const goToJob = (jobId: number) => {
  void router.push({ path: "/jobs", query: { id: String(jobId) } });
};

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

const openEditDialog = (row: MaterialRecord) => {
  editMaterialRow.value = row;
  editName.value = row.name;
  editNote.value = row.note ?? "";
  editFile.value = null;
  showEditDialog.value = true;
};

const onEditFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  editFile.value = input.files?.[0] ?? null;
};

const handleEdit = async () => {
  if (!editMaterialRow.value) {
    return;
  }
  const name = editName.value.trim();
  if (!name) {
    ElMessage.warning("请填写名称");
    return;
  }
  editing.value = true;
  try {
    await editMaterial({
      id: editMaterialRow.value.id,
      name,
      note: editNote.value,
      file: editFile.value ?? undefined,
    });
    ElMessage.success("已保存");
    showEditDialog.value = false;
    editFile.value = null;
    if (editFileInputRef.value) {
      editFileInputRef.value.value = "";
    }
    await fetchMaterials();
  } catch (error) {
    handleError(error, "保存失败");
  } finally {
    editing.value = false;
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
  createJobRunMode.value = "prepare";
  showCreateJobDialog.value = true;
};

const createJobRunModeLabel = (mode: MaterialJobRunMode) => {
  switch (mode) {
    case "prepare":
      return "已创建并开始基底准备";
    case "full":
      return "已创建并开始全流程";
    default:
      return "已创建任务";
  }
};

const handleCreateJob = async () => {
  if (!createJobMaterial.value || !createJobTitle.value.trim()) {
    ElMessage.warning("请填写标题");
    return;
  }
  creatingJob.value = true;
  try {
    const runMode = createJobRunMode.value;
    const job = await createJobFromMaterial({
      material_id: createJobMaterial.value.id,
      title: createJobTitle.value.trim(),
      script_mode: createJobScriptMode.value,
      narration: createJobScriptMode.value === "manual" ? createJobNarration.value : undefined,
      skip_publish: createJobSkipPublish.value,
      run_mode: runMode,
    });
    ElMessage.success(`${createJobRunModeLabel(runMode)}，任务 #${job.id}，请在任务队列查看`);
    showCreateJobDialog.value = false;
    await fetchMaterials();
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
