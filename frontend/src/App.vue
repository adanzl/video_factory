<template>
  <el-container class="h-screen">
    <Sidebar @collapse-change="handleCollapseChange" />
    <el-container>
      <el-header class="flex justify-between items-center bg-blue-50 px-6">
        <div class="flex items-center gap-2">
          <span class="font-medium">Video Factory</span>
        </div>
        <el-tag type="info" size="small">管理后台</el-tag>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from "vue";
import Sidebar from "@/views/Sidebar.vue";

const isSidebarCollapsed = ref(false);

const handleCollapseChange = (collapsed: boolean) => {
  isSidebarCollapsed.value = collapsed;
};
</script>
