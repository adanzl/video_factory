<template>
  <el-dialog v-model="visible" title="故事详情" width="1200px" top="5vh">
    <div v-if="localStory" class="flex gap-4" style="height: 80vh;">
      <!-- 左侧：信息 -->
      <div class="w-64 shrink-0 space-y-4 overflow-y-auto pr-2">
        <div>
          <div class="mb-1 text-xs text-gray-400">主题</div>
          <div class="text-sm">{{ localStory.theme }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">场景标题</div>
          <el-input v-if="editing" v-model="editStory.scene_title" size="small" />
          <div v-else class="font-bold">{{ editStory.scene_title }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">设定</div>
          <el-input v-if="editing" v-model="editStory.setting" type="textarea" :rows="3" size="small" />
          <div v-else class="text-sm text-gray-600">{{ editStory.setting }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">笑点解析</div>
          <el-input v-if="editing" v-model="editStory.punchline_explain" type="textarea" :rows="4" size="small" />
          <div v-else class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">{{ editStory.punchline_explain }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">语速</div>
          <el-input-number
            v-model="speechRate"
            :min="1"
            :max="10"
            :step="0.1"
            :precision="1"
            size="small"
            class="w-28!"
          />
          <span class="ml-1 text-xs text-gray-400">字/秒</span>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">句间停留</div>
          <el-input-number
            v-model="lineGap"
            :min="0"
            :max="3"
            :step="0.1"
            :precision="1"
            size="small"
            class="w-28!"
          />
          <span class="ml-1 text-xs text-gray-400">秒</span>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">总字数</div>
          <div class="text-sm text-gray-600">{{ totalChars }} 字</div>
        </div>
        <div>
          <div class="mb-1 text-xs text-gray-400">时长估算</div>
          <div class="text-sm text-gray-600">{{ estimatedDuration }}</div>
        </div>
        <div class="mt-4">
          <el-button
            v-if="!localStory?.job_id"
            type="primary"
            class="flex-1"
            size="small"
            :loading="submitting"
            :disabled="!localStory?.id"
            @click="handleCreateJob"
          >
            发起任务
          </el-button>
          <el-button
            v-if="localStory?.job_id"
            type="primary"
            size="small"
            @click="handleViewJob"
          >
            任务详情
          </el-button>
          <el-button
            v-if="localStory?.job_id"
            type="warning"
            size="small"
            :loading="syncing"
            @click="handleSyncToJob"
          >
            同步
          </el-button>
        </div>
        <div class="mt-4">
          <el-button
            :disabled="!localStory?.id || regenerating"
            type="success"
            size="small"
            @click="handleSave"
          >
            <template #icon>
              <i-mdi-floppy />
            </template>
          </el-button>
          <el-button
            :disabled="!localStory?.id || regenerating"
            :loading="regenerating"
            size="small"
            @click="handleRegenerate"
          >
            重新生成
          </el-button>
        </div>
      </div>

      <!-- 右侧：对话 -->
      <div class="flex flex-1 flex-col pl-2" style="border-left: 1px solid #e5e7eb;">
        <div class="mb-2 flex shrink-0 items-center justify-between">
          <span class="text-xs text-gray-400">
            对话 <el-tag size="small" type="info" class="ml-3">{{ editStory.dialogue?.length ?? 0 }} 轮</el-tag>
          </span>
          <el-button size="small" :icon="Edit" @click="editing = !editing">
            编辑
          </el-button>
        </div>
        <div class="flex-1 space-y-3 overflow-y-auto px-2">
          <div
            v-for="(line, idx) in editStory.dialogue"
            :key="idx"
            class="rounded-lg p-3 flex items-center gap-2"
            :class="speakerStyle(line.speaker).bg"
          >
            <div
              :class="speakerStyle(line.speaker).text"
              class="text-xs w-8"
            >
              {{ line.speaker }}
            </div>
            <el-input v-if="editing" v-model="line.line" type="text" size="small" />
            <div v-else class="text-sm">{{ line.line }}</div>
            <div class="ml-auto shrink-0 text-xs text-gray-400">{{ line.line?.length || 0 }} </div>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Edit } from "@element-plus/icons-vue";
import type { DailyStoryRecord, StoryContent } from "@/api/api-daily-story";
import { createDailyStoryJob, regenerateDailyStory, updateDailyStory, syncDailyStoryToJob } from "@/api/api-daily-story";

function speakerStyle(speaker: string): { bg: string; text: string } {
  if (speaker === '昭昭') return { bg: 'bg-blue-50', text: 'text-blue-600 font-bold' }
  if (speaker === '妈妈') return { bg: 'bg-emerald-50', text: 'text-emerald-600 font-bold' }
  return { bg: 'bg-pink-50', text: 'text-pink-600 font-bold' }
}

const props = defineProps<{
  modelValue: boolean;
  story: DailyStoryRecord | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void;
  (e: "updated", story?: DailyStoryRecord): void;
}>();

const router = useRouter();

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
});

const localStory = computed(() => props.story);

/** 本地可编辑副本 */
const editStory = ref<StoryContent>({
  scene_title: "",
  setting: "",
  dialogue: [],
  punchline_explain: "",
});

watch(
  () => props.story,
  (story) => {
    if (story?.story) {
      editStory.value = JSON.parse(JSON.stringify(story.story));
    }
  },
  { immediate: true }
);

/** 默认口播语速（字/秒） */
const speechRate = ref(3.1);
/** 句间停留（秒） */
const lineGap = ref(0.3);

const totalChars = computed(() => {
  const dialogue = editStory.value?.dialogue;
  if (!dialogue) return 0;
  return dialogue.reduce((sum, line) => sum + (line.line?.length || 0), 0);
});

const estimatedDuration = computed(() => {
  const chars = totalChars.value;
  const dialogue = localStory.value?.story?.dialogue;
  if (chars <= 0 || !dialogue || dialogue.length === 0) return "-";
  const speakSec = chars / speechRate.value;
  const gapSec = (dialogue.length - 1) * lineGap.value;
  const secs = Math.round(speakSec + gapSec);
  if (secs < 60) return `约 ${secs} 秒`;
  const mins = Math.floor(secs / 60);
  const remain = secs % 60;
  return remain > 0 ? `约 ${mins} 分 ${remain} 秒` : `约 ${mins} 分钟`;
});

const editing = ref(false);
const submitting = ref(false);
const regenerating = ref(false);
const syncing = ref(false);

async function handleCreateJob() {
  const storyId = props.story?.id;
  if (!storyId) return;
  submitting.value = true;
  try {
    const job = await createDailyStoryJob(storyId, {
      speechRate: speechRate.value,
      lineGap: lineGap.value,
    });
    ElMessage.success(`任务已创建（ID: ${job.id}），即将开始处理`);
    visible.value = false;
    router.push({ path: "/jobs", query: { id: String(job.id) } });
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || "创建任务失败");
  } finally {
    submitting.value = false;
  }
}

function handleViewJob() {
  const jobId = props.story?.job_id;
  if (!jobId) return;
  visible.value = false;
  router.push({ path: "/jobs", query: { id: String(jobId) } });
}

async function handleSave() {
  const storyId = props.story?.id;
  if (!storyId) return;
  try {
    await updateDailyStory(storyId, editStory.value);
    ElMessage.success("已保存");
    emit("updated");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "保存失败");
  }
}

async function handleSyncToJob() {
  const storyId = props.story?.id;
  if (!storyId) return;
  syncing.value = true;
  try {
    await syncDailyStoryToJob(storyId, editStory.value);
    ElMessage.success("已同步到任务，任务脚本阶段已重置");
    emit("updated");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || "同步失败");
  } finally {
    syncing.value = false;
  }
}

async function handleRegenerate() {
  const storyId = props.story?.id;
  if (!storyId) return;
  regenerating.value = true;
  try {
    const newStory = await regenerateDailyStory(storyId);
    ElMessage.success("已重新生成");
    emit("updated", newStory);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "重新生成失败");
  } finally {
    regenerating.value = false;
  }
}
</script>
