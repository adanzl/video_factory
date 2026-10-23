<template>
  <el-aside
    :width="isCollapse ? '64px' : '200px'"
    class="flex flex-col overflow-hidden transition-all duration-300 border-r"
  >
    <el-scrollbar class="min-h-0 flex-1">
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
          <template #title>金牌故事</template>
        </el-menu-item>
        <el-menu-item index="/materials/audio">
          <el-icon><Headset /></el-icon>
          <template #title>音频素材</template>
        </el-menu-item>
        <el-menu-item index="/clips">
          <el-icon><Search /></el-icon>
          <template #title>片段搜索</template>
        </el-menu-item>
        <el-menu-item index="/tools">
          <el-icon><Tools /></el-icon>
          <template #title>工具</template>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <template #title>配置</template>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>
    <div
      class="flex h-20 shrink-0 pb-4"
      :class="
        isCollapse
          ? 'flex-col items-center justify-end gap-2 px-0.5'
          : 'items-end justify-center gap-3 px-2'
      "
    >
      <el-switch
        v-model="isDark"
        class="theme-switch"
        aria-label="切换暗色主题"
      >
        <template #active-action>
          <el-icon class="dark-icon">
            <svg viewBox="0 0 24 24">
              <path
                d="M11.01 3.05C6.51 3.54 3 7.36 3 12a9 9 0 0 0 9 9c4.63 0 8.45-3.5 8.95-8c.09-.79-.78-1.42-1.54-.95A5.403 5.403 0 0 1 11.1 7.5c0-1.06.31-2.06.84-2.89c.45-.67-.04-1.63-.93-1.56z"
                fill="currentColor"
              />
            </svg>
          </el-icon>
        </template>
        <template #inactive-action>
          <el-icon class="light-icon">
            <svg viewBox="0 0 24 24">
              <path
                d="M6.05 4.14l-.39-.39a.993.993 0 0 0-1.4 0l-.01.01a.984.984 0 0 0 0 1.4l.39.39c.39.39 1.01.39 1.4 0l.01-.01a.984.984 0 0 0 0-1.4zM3.01 10.5H1.99c-.55 0-.99.44-.99.99v.01c0 .55.44.99.99.99H3c.56.01 1-.43 1-.98v-.01c0-.56-.44-1-.99-1zm9-9.95H12c-.56 0-1 .44-1 .99v.96c0 .55.44.99.99.99H12c.56.01 1-.43 1-.98v-.97c0-.55-.44-.99-.99-.99zm7.74 3.21c-.39-.39-1.02-.39-1.41-.01l-.39.39a.984.984 0 0 0 0 1.4l.01.01c.39.39 1.02.39 1.4 0l.39-.39a.984.984 0 0 0 0-1.4zm-1.81 15.1l.39.39a.996.996 0 1 0 1.41-1.41l-.39-.39a.993.993 0 0 0-1.4 0c-.4.4-.4 1.02-.01 1.41zM20 11.49v.01c0 .55.44.99.99.99H22c.55 0 .99-.44.99-.99v-.01c0-.55-.44-.99-.99-.99h-1.01c-.55 0-.99.44-.99.99zM12 5.5c-3.31 0-6 2.69-6 6s2.69 6 6 6s6-2.69 6-6s-2.69-6-6-6zm-.01 16.95H12c.55 0 .99-.44.99-.99v-.96c0-.55-.44-.99-.99-.99h-.01c-.55 0-.99.44-.99.99v.96c0 .55.44.99.99.99zm-7.74-3.21c.39.39 1.02.39 1.41 0l.39-.39a.993.993 0 0 0 0-1.4l-.01-.01a.996.996 0 0 0-1.41 0l-.39.39c-.38.4-.38 1.02.01 1.41z"
                fill="currentColor"
              />
            </svg>
          </el-icon>
        </template>
      </el-switch>
      <el-tooltip
        :content="isCollapse ? '展开菜单' : '折叠菜单'"
        placement="right"
      >
        <button
          type="button"
          class="collapse-btn"
          :aria-label="isCollapse ? '展开菜单' : '折叠菜单'"
          @click="toggleCollapse"
        >
          <el-icon>
            <Expand v-if="isCollapse" />
            <Fold v-else />
          </el-icon>
        </button>
      </el-tooltip>
    </div>
  </el-aside>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  HomeFilled,
  List,
  Document,
  Setting,
  Expand,
  Fold,
  VideoCamera,
  Search,
  Headset,
  ChatDotRound,
  Medal,
  Tools,
} from "@element-plus/icons-vue";
import { useAppStore } from "@/stores/app";

const emit = defineEmits<{
  collapseChange: [collapsed: boolean];
}>();

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const isCollapse = ref(false);

/** 开关状态直接读写主题：关=亮色，开=暗色 */
const isDark = computed({
  get: () => appStore.isDark,
  set: (value: string | number | boolean) => appStore.setTheme(value ? "dark" : "light"),
});

const onMenuSelect = async (index: string) => {
  if (!index) {
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

<style scoped>
/* 竖线由整个侧栏绘制，贯穿上下；菜单自身不再画右边框 */
.el-aside {
  border-right-color: var(--el-border-color);
}

.el-aside :deep(.el-menu) {
  border-right: none;
}

/* 底部工具条：折叠按钮做成与主题开关等宽的胶囊，展开时并排、折叠时上下 */
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 20px;
  padding: 0;
  font-size: 12px;
  line-height: 1;
  color: var(--el-text-color-secondary);
  background-color: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 9999px;
  cursor: pointer;
  transition:
    color 0.2s,
    border-color 0.2s;
}

.collapse-btn:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

/* 开关本体高度收成与胶囊一致，避免自带 32px 高把底部工具条撑歪 */
.theme-switch {
  height: 20px;
}

/* 仿 Element Plus 官网导航栏的主题开关：浅底胶囊 + 太阳/月亮圆点 */
.theme-switch :deep(.el-switch__core) {
  --el-switch-on-color: var(--el-fill-color);
  --el-switch-off-color: var(--el-fill-color);
  --el-switch-border-color: var(--el-border-color);
}

.theme-switch:not(.el-switch--small) :deep(.el-switch__core .el-switch__action) {
  width: 14px;
  height: 14px;
}

.theme-switch :deep(.dark-icon) {
  border-radius: 50%;
  color: #cfd3dc;
  background-color: #141414;
}

.theme-switch :deep(.light-icon) {
  color: #606266;
}
</style>
