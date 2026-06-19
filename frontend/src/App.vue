<template>
  <el-container class="h-screen">
    <Sidebar @collapse-change="handleCollapseChange" />
    <el-container>
      <el-header class="flex justify-between items-center bg-blue-50 px-6">
        <div class="flex items-center gap-2">
          <span class="font-medium">Video Factory</span>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <el-tag type="info" size="small">管理后台</el-tag>
          <span class="text-gray-500">服务器:</span>
          <el-tag :type="serverStatusType" size="small">
            {{ serverStatusText }}
          </el-tag>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import Sidebar from "@/views/Sidebar.vue";
import {
  getCurrentLocalPort,
  LOCAL_IP,
  startServerMonitor,
  stopServerMonitor,
  subscribeServerStatus,
} from "@/api/config";
import { logger } from "@/utils/logger";

const isSidebarCollapsed = ref(false);
const localIpStatus = ref<boolean | null>(null);
let unsubscribeServerStatus: (() => void) | null = null;

const handleCollapseChange = (collapsed: boolean) => {
  isSidebarCollapsed.value = collapsed;
};

const serverStatusText = computed(() => {
  if (localIpStatus.value === true) {
    if (import.meta.env.DEV) {
      return "本地 (127.0.0.1:9002)";
    }
    return `本地 (${LOCAL_IP}:${getCurrentLocalPort()})`;
  }
  if (localIpStatus.value === false) {
    return "远程";
  }
  return "检测中...";
});

const serverStatusType = computed(() => {
  if (localIpStatus.value === true) {
    return "success";
  }
  if (localIpStatus.value === false) {
    return "warning";
  }
  return "info";
});

onMounted(async () => {
  unsubscribeServerStatus = subscribeServerStatus((isUsingLocalServer, changed) => {
    const previousStatus = localIpStatus.value;
    localIpStatus.value = isUsingLocalServer;

    if (!changed || previousStatus === null) {
      return;
    }

    if (isUsingLocalServer) {
      logger.info(
        `[Server Switch] 切换到本地服务器: ${import.meta.env.DEV ? "127.0.0.1:9002" : `${LOCAL_IP}:${getCurrentLocalPort()}`}`
      );
      return;
    }

    logger.info("[Server Switch] 切换到远程服务器");
  });

  await startServerMonitor();
});

onBeforeUnmount(() => {
  unsubscribeServerStatus?.();
  unsubscribeServerStatus = null;
  stopServerMonitor();
});
</script>
