<template>
  <div class="mx-auto max-w-2xl">
    <div class="mb-6 flex items-center gap-3">
      <el-button @click="router.push('/daily-story')">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2 class="text-xl font-bold">生成日常故事</h2>
    </div>

    <el-card>
      <el-form @submit.prevent="handleGenerate" label-width="80px">
        <el-form-item label="场景主题">
          <div class="flex w-full gap-2">
            <el-input
              v-model="generateTheme"
              placeholder="如：写检查、零花钱花完了、争最后一块饼干"
              clearable
              class="flex-1"
              size="large"
            />
            <el-button size="large" :loading="generatingThemes" @click="handleGenerateThemes">
              AI 生成
            </el-button>
          </div>
        </el-form-item>
        <div v-if="generatedThemes.length" class="mb-4 ml-20 flex flex-wrap gap-2">
          <el-tag
            v-for="(theme, idx) in generatedThemes"
            :key="idx"
            class="cursor-pointer"
            size="large"
            @click="generateTheme = theme"
          >
            {{ theme }}
          </el-tag>
        </div>
        <el-form-item>
          <el-button type="primary" size="large" :loading="generating" @click="handleGenerate">
            生成故事
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 生成结果展示 -->
    <el-card v-if="generatedStory" class="mt-6">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="font-bold text-lg">{{ generatedStory.story?.scene_title }}</span>
          <span class="text-gray-500 text-sm">{{ generatedStory.story?.setting }}</span>
        </div>
      </template>
      <div class="space-y-3">
        <div
          v-for="(line, idx) in generatedStory.story?.dialogue || []"
          :key="idx"
          class="rounded-lg p-2"
          :class="line.speaker === '昭昭' ? 'bg-blue-50' : 'bg-pink-50'"
        >
          <span
            :class="line.speaker === '昭昭' ? 'text-blue-600 font-bold' : 'text-pink-600 font-bold'"
          >
            {{ line.speaker }}：
          </span>
          <span>{{ line.line }}</span>
        </div>
      </div>
      <div class="mt-4 rounded-lg bg-gray-100 p-3 text-sm text-gray-600">
        <span class="font-bold">笑点解析：</span>{{ generatedStory.story?.punchline_explain }}
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeft } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import {
  generateDailyStory,
  generateDailyStoryThemes,
  type DailyStoryRecord,
} from "@/api/api-daily-story";

const router = useRouter();
const { handleError } = useErrorHandler();

const generateTheme = ref("");
const generating = ref(false);
const generatingThemes = ref(false);
const generatedThemes = ref<string[]>([]);
const generatedStory = ref<DailyStoryRecord | null>(null);

async function handleGenerateThemes() {
  generatingThemes.value = true;
  try {
    generatedThemes.value = await generateDailyStoryThemes(2);
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
  generatedStory.value = null;
  try {
    generatedStory.value = await generateDailyStory(theme);
    ElMessage.success("生成成功");
  } catch (e) {
    handleError(e, "生成故事失败");
  } finally {
    generating.value = false;
  }
}
</script>
