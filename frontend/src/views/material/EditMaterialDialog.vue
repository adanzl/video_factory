<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="700px" destroy-on-close @closed="onClosed">
    <el-form label-width="90px">
      <el-form-item label="素材 ID">
        <span>{{ material?.id }}</span>
      </el-form-item>
      <el-form-item label="名称" required>
        <el-input v-model="editName" placeholder="素材名称" clearable />
      </el-form-item>
      <el-form-item label="视频文件">
        <input
          ref="fileInputRef"
          type="file"
          accept="video/*,.mp4,.mov,.webm,.mkv"
          @change="onFileChange"
        />
        <p v-if="material?.file_path" class="mt-1 text-xs text-gray-500">
          不选文件则保留当前视频；<br/>
          更换后已关联任务需重新执行「基底准备」才会更新成片基底。<br/>
          {{ material.file_path }}
        </p>
      </el-form-item>
      <el-form-item v-if="isTimelineJson" label="分析结果">
        <div class="w-full">
          <p class="mb-1 text-sm text-gray-600">{{ timelineData?.title }}</p>
          <el-table :data="timelineData?.segments ?? []" size="small" border max-height="360">
            <el-table-column label="#" prop="index" width="48" align="center" />
            <el-table-column label="名称" prop="name" min-width="100" show-overflow-tooltip />
            <el-table-column label="开始" width="70" align="center">
              <template #default="{ row }">{{ fmtSec(row.start_sec) }}</template>
            </el-table-column>
            <el-table-column label="结束" width="70" align="center">
              <template #default="{ row }">{{ fmtSec(row.end_sec) }}</template>
            </el-table-column>
            <el-table-column label="时长" width="70" align="center">
              <template #default="{ row }">{{ fmtSec(row.duration_sec) }}</template>
            </el-table-column>
            <el-table-column label="描述" prop="description" min-width="120" show-overflow-tooltip />
          </el-table>
        </div>
      </el-form-item>
      <el-form-item v-else label="备注">
        <el-input v-model="editNote" type="textarea" :rows="2" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!editName.trim()" @click="handleSave">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { editMaterial } from "@/api/api-materials";
import type { MaterialRecord } from "@/types/material";

interface TimelineSegment {
  index: number;
  name: string;
  description?: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
}

interface TimelineData {
  title?: string;
  segments?: TimelineSegment[];
}

const props = defineProps<{
    modelValue: boolean;
    material: MaterialRecord | null;
}>();

const emit = defineEmits<{
    (e: "update:modelValue", v: boolean): void;
    (e: "saved"): void;
}>();

const visible = ref(false);
const saving = ref(false);
const editName = ref("");
const editNote = ref("");
const editFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

const timelineData = computed<TimelineData | null>(() => {
    try {
        const parsed = JSON.parse(editNote.value);
        if (parsed && Array.isArray(parsed.segments)) {
            return parsed as TimelineData;
        }
        return null;
    } catch {
        return null;
    }
});

const isTimelineJson = computed(() => timelineData.value !== null);

const dialogTitle = computed(() =>
    isTimelineJson.value ? `编辑素材 - ${timelineData.value?.title ?? ""}` : "编辑素材"
);

const fmtSec = (sec: number | undefined): string => {
    if (sec == null) return "-";
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

watch(
    () => props.modelValue,
    async (v) => {
        visible.value = v;
        if (v && props.material) {
            await nextTick();
            editName.value = props.material.name;
            editNote.value = props.material.note ?? "";
            editFile.value = null;
            if (fileInputRef.value) {
                fileInputRef.value.value = "";
            }
        }
    }
);

watch(visible, (v) => {
    if (!v) {
        emit("update:modelValue", false);
    }
});

const onFileChange = (event: Event) => {
    const input = event.target as HTMLInputElement;
    editFile.value = input.files?.[0] ?? null;
};

const handleSave = async () => {
    if (!props.material) {
        return;
    }
    const name = editName.value.trim();
    if (!name) {
        ElMessage.warning("请填写名称");
        return;
    }
    saving.value = true;
    try {
        await editMaterial({
            id: props.material.id,
            name,
            note: editNote.value,
            file: editFile.value ?? undefined,
        });
        ElMessage.success("已保存");
        visible.value = false;
        emit("saved");
    } catch (error) {
        const { useErrorHandler } = await import("@/composables/useErrorHandler");
        useErrorHandler().handleError(error, "保存失败");
    } finally {
        saving.value = false;
    }
};

const onClosed = () => {
    editFile.value = null;
};
</script>
