<template>
  <div class="tool-page flex h-[calc(100vh-120px)] min-h-0 flex-col overflow-hidden">
    <el-tabs v-model="activeTab" class="tool-page-tabs flex min-h-0 flex-1 flex-col">
      <el-tab-pane label="每日签到" name="checkin" class="h-full min-h-0 overflow-hidden">
        <TabCheckin ref="checkinTabRef" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { usePageRefresh } from "@/stores/app";
import TabCheckin from "./TabCheckin.vue";

const activeTab = ref("checkin");
const checkinTabRef = ref<InstanceType<typeof TabCheckin> | null>(null);

const refreshPage = () => {
  checkinTabRef.value?.refresh();
};

// 首次挂载由 TabCheckin 自己拉数，这里只处理 keep-alive 切回与菜单重复点击
usePageRefresh(refreshPage);
</script>

<style scoped>
.tool-page-tabs :deep(> .el-tabs__header) {
  flex-shrink: 0;
}

.tool-page-tabs :deep(> .el-tabs__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.tool-page-tabs :deep(> .el-tabs__content > .el-tab-pane) {
  flex: 1;
  min-height: 0;
  height: 100%;
}
</style>
