<template>
  <el-aside :width="isCollapse ? '64px' : '200px'" class="transition-all duration-300">
    <el-scrollbar>
      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        unique-opened
        @select="onMenuSelect"
      >
        <el-menu-item index="/home">
          <el-icon><HomeFilled /></el-icon>
          <template #title>首页</template>
        </el-menu-item>
        <el-menu-item index="/jobs">
          <el-icon><List /></el-icon>
          <template #title>任务队列</template>
        </el-menu-item>
        <el-menu-item index="/materials/video">
          <el-icon><VideoCamera /></el-icon>
          <template #title>视频素材</template>
        </el-menu-item>
        <el-menu-item index="/topic">
          <el-icon><Document /></el-icon>
          <template #title>选题库</template>
        </el-menu-item>
        <el-menu-item index="/daily-story">
          <el-icon><ChatDotRound /></el-icon>
          <template #title>日常故事</template>
        </el-menu-item>
        <el-menu-item index="/gold-chat">
          <el-icon><Medal /></el-icon>
          <template #title>gold_chat</template>
        </el-menu-item>
        <el-menu-item index="/materials/audio">
          <el-icon><Headset /></el-icon>
          <template #title>音频素材</template>
        </el-menu-item>
        <el-menu-item index="/clips">
          <el-icon><Search /></el-icon>
          <template #title>片段搜索</template>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <template #title>配置</template>
        </el-menu-item>
        <el-menu-item index="#" @click="toggleCollapse">
          <el-icon><Expand v-if="isCollapse" /><Fold v-else /></el-icon>
          <template #title>折叠</template>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>
  </el-aside>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { HomeFilled, List, Document, Setting, Expand, Fold, VideoCamera, Search, Headset, ChatDotRound, Medal } from "@element-plus/icons-vue";
import { useAppStore } from "@/stores/app";

const emit = defineEmits<{
  collapseChange: [collapsed: boolean];
}>();

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const isCollapse = ref(false);

const onMenuSelect = async (index: string) => {
  if (!index || index === "#") {
    return;
  }
  if (route.path === index) {
    if (route.fullPath !== index) {
      await router.push(index);
    }
    appStore.requestPageRefresh();
    return;
  }
  await router.push(index);
};

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value;
  emit("collapseChange", isCollapse.value);
};
</script>
