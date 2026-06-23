<template>
  <ClipSearchPanel>
    <template #actions="{ clip }">
      <div class="flex flex-wrap gap-2">
        <el-button size="small" @click="copyText(clip.video_url, '视频地址')">复制视频 URL</el-button>
        <el-button size="small" link type="primary" @click="openPage(clip.page_url)">来源页</el-button>
      </div>
    </template>
  </ClipSearchPanel>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import ClipSearchPanel from "./ClipSearchPanel.vue";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText as copyToClipboard } from "@/utils/utils";

const { handleError } = useErrorHandler();

const copyText = async (text: string, label: string) => {
  try {
    await copyToClipboard(text);
    ElMessage.success(`${label}已复制`);
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const openPage = (url: string) => {
  window.open(url, "_blank", "noopener,noreferrer");
};
</script>
