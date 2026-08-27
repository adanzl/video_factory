<template>
  <el-dialog v-model="visible" title="生成日常故事" width="880px" top="8vh" @closed="onDialogClosed">
    <el-form @submit.prevent="handleGenerate">
      <el-form-item label="场景主题">
        <div class="w-full">
          <div class="flex w-full gap-2">
            <el-input
              v-model="generateTheme"
              placeholder="如：写检查、零花钱花完了、争最后一块饼干"
              clearable
              size="large"
              class="flex-1"
            />
            <el-button size="large" :loading="generatingThemes" @click="handleGenerateThemes">
              AI 推荐主题
            </el-button>
          </div>
          <div class="mt-3 overflow-hidden rounded border border-gray-200">
            <div class="flex items-center justify-between border-b border-gray-100 px-3 py-2">
              <span class="text-sm text-gray-500">建议主题（点选填入并带上推荐类型）</span>
            </div>
            <div class="h-64 overflow-y-auto py-1">
              <div
                v-if="!generatedThemes.length"
                class="flex h-full items-center justify-center text-sm text-gray-400"
              >
                {{ generatingThemes ? "正在生成建议主题…" : "点击「AI 推荐主题」获取建议" }}
              </div>
              <div
                v-for="row in generatedThemes"
                :key="row.theme"
                class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-gray-50"
                :class="{ 'bg-blue-50!': generateTheme === row.theme }"
                @click="onPickTheme(row)"
              >
                <el-tag v-if="row.story_types?.length" size="small" type="info">
                  {{ formatDailyStoryTypes(row.story_types) }}
                </el-tag>
                <span class="truncate">{{ row.theme }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="矛盾类型">
        <div class="w-full">
          <div class="flex flex-wrap gap-2">
            <el-tag
              class="cursor-pointer!"
              :effect="selectedStoryType === '' ? 'dark' : 'plain'"
              :type="selectedStoryType === '' ? 'primary' : 'info'"
              @click="selectedStoryType = ''"
            >
              自动适配
            </el-tag>
            <el-tag
              v-for="opt in DAILY_STORY_TYPE_GENERATE_OPTIONS"
              :key="opt.value"
              class="cursor-pointer!"
              :effect="selectedStoryType === opt.value ? 'dark' : 'plain'"
              :type="selectedStoryType === opt.value ? 'primary' : 'info'"
              @click="selectedStoryType = opt.value"
            >
              {{ opt.label }}
            </el-tag>
          </div>
        </div>
      </el-form-item>
      <div class="flex justify-end">
        <el-button type="primary" size="large" native-type="submit" :loading="generating">
          生成故事
        </el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import {
  generateDailyStory,
  generateDailyStoryThemes,
  formatDailyStoryTypes,
  DAILY_STORY_TYPE_GENERATE_OPTIONS,
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
const selectedStoryType = ref("");
const generating = ref(false);
const generatingThemes = ref(false);
const generatedThemes = ref<DailyStoryThemeItem[]>([]);
/** 本会话已展示过的主题，再次生成时传给后端避重 */
const seenThemes = ref<string[]>([]);

function onDialogClosed() {
  generateTheme.value = "";
  selectedStoryType.value = "";
  generatedThemes.value = [];
  seenThemes.value = [];
}

function onPickTheme(row: DailyStoryThemeItem) {
  generateTheme.value = row.theme;
  selectedStoryType.value = row.story_types?.[0] || "";
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
    ElMessage.success(`已开始生成「${theme}」，可在列表查看进度`);
    emit("created");
    emit("update:modelValue", false);
  } catch (e) {
    handleError(e, "生成故事失败");
  } finally {
    generating.value = false;
  }
}
</script>
