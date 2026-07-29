<template>
  <el-dialog v-model="visible" title="生成日常故事" width="680px" top="8vh" @closed="onDialogClosed">
    <div class="h-100">
      <el-form @submit.prevent="handleGenerate" label-width="80px">
        <el-form-item label="场景主题">
          <div class="flex w-full gap-2">
            <el-input
              v-model="generateTheme"
              placeholder="如：写检查、零花钱花完了、争最后一块饼干"
              clearable
              size="large"
              class="flex-1"
              @input="onThemeInput"
            />
            <el-button size="large" :loading="generatingThemes" @click="handleGenerateThemes">
              生成
            </el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="candidateTypes.length" label="矛盾类型">
          <el-radio-group v-model="selectedStoryType" size="small">
            <el-radio
              v-for="code in candidateTypes"
              :key="code"
              :value="code"
            >
              {{ formatDailyStoryType(code) }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <div v-if="generatedThemes.length" class="mb-4 ml-20">
          <div class="mb-2 text-sm text-gray-500">备选主题（点选填入；多类型可再选）</div>
          <el-table
            :data="generatedThemes"
            size="small"
            max-height="280"
            highlight-current-row
            class="w-full cursor-pointer"
            @row-click="onPickTheme"
          >
            <el-table-column label="可适配类型" width="200">
              <template #default="{ row }">
                {{ formatDailyStoryTypes(row.story_types) }}
              </template>
            </el-table-column>
            <el-table-column prop="theme" label="主题" min-width="220" show-overflow-tooltip />
          </el-table>
        </div>
        <el-form-item>
          <el-button type="primary" size="large" :loading="generating" @click="handleGenerate">
            生成故事
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import {
  generateDailyStory,
  generateDailyStoryThemes,
  formatDailyStoryType,
  formatDailyStoryTypes,
  type DailyStoryThemeItem,
} from "@/api/api-daily-story";

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void;
  (e: "created"): void;
}>();

const props = defineProps<{
  modelValue: boolean;
}>();

const { handleError } = useErrorHandler();

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
});

const generateTheme = ref("");
const candidateTypes = ref<string[]>([]);
const selectedStoryType = ref<string>("");
const generating = ref(false);
const generatingThemes = ref(false);
const generatedThemes = ref<DailyStoryThemeItem[]>([]);
/** 本会话已展示过的主题，再次点生成时传给后端避重 */
const seenThemes = ref<string[]>([]);

function onDialogClosed() {
  generateTheme.value = "";
  candidateTypes.value = [];
  selectedStoryType.value = "";
  generatedThemes.value = [];
  seenThemes.value = [];
}

function onThemeInput() {
  candidateTypes.value = [];
  selectedStoryType.value = "";
}

function onPickTheme(row: DailyStoryThemeItem) {
  generateTheme.value = row.theme;
  candidateTypes.value = [...(row.story_types || [])];
  selectedStoryType.value = candidateTypes.value[0] || "";
}

async function handleGenerateThemes() {
  generatingThemes.value = true;
  try {
    const next = await generateDailyStoryThemes(15, {
      exclude: seenThemes.value,
    });
    generatedThemes.value = next;
    const merged = new Set([
      ...seenThemes.value,
      ...next.map((item) => item.theme),
    ]);
    seenThemes.value = [...merged];
  } catch (e) {
    handleError(e, "生成主题失败");
  } finally {
    generatingThemes.value = false;
  }
}

async function handleGenerate() {
  const theme = generateTheme.value.trim();
  if (!theme) {
    ElMessage.warning("请输入场景主题");
    return;
  }
  generating.value = true;
  try {
    await generateDailyStory(theme, {
      storyType: selectedStoryType.value || null,
    });
    ElMessage.success("已开始生成，列表稍后刷新");
    emit("created");
    emit("update:modelValue", false);
  } catch (e) {
    handleError(e, "生成故事失败");
  } finally {
    generating.value = false;
  }
}
</script>
