<template>
  <el-dialog v-model="visible" title="生成日常故事" width="600px" top="10vh" @closed="onDialogClosed">
    <el-form @submit.prevent="handleGenerate" label-width="80px">
      <el-form-item label="场景主题">
        <div class="flex w-full gap-2">
          <el-input
            v-model="generateTheme"
            placeholder="如：写检查、零花钱花完了、争最后一块饼干"
            clearable
            size="large"
            class="flex-1"
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


  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import { useErrorHandler } from "@/composables/useErrorHandler";
import {
  generateDailyStory,
  generateDailyStoryThemes,
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
const generating = ref(false);
const generatingThemes = ref(false);
const generatedThemes = ref<string[]>([]);

function onDialogClosed() {
  generateTheme.value = "";
  generatedThemes.value = [];
}

async function handleGenerateThemes() {
  generatingThemes.value = true;
  try {
    generatedThemes.value = await generateDailyStoryThemes(5);
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
    await generateDailyStory(theme);
    ElMessage.success("生成成功");
    emit("created");
    emit("update:modelValue", false);
  } catch (e) {
    handleError(e, "生成故事失败");
  } finally {
    generating.value = false;
  }
}
</script>
